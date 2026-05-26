/**
 * CondorVoice — modo de conversa por voz contínua.
 *
 * Fluxo:
 *  1. Usuário clica no orb → entra em MODO CONVERSA
 *  2. Microfone abre, captura fala
 *  3. VAD client-side: após 1.8s de silêncio (com fala detectada) → envia áudio
 *  4. Condor transcreve, pensa, responde por voz (TTS)
 *  5. Quando TTS termina → microfone abre sozinho (volta ao passo 2)
 *  6. Usuário clica no orb de novo → sai do MODO CONVERSA
 *
 * Enquanto FORA do modo conversa: só digitação normal funciona.
 */
const CondorVoice = (() => {

  // ── Estado ────────────────────────────────────────────────────────────────
  let _convMode    = false;   // modo conversa ativo?
  let _listening   = false;   // mic aberto capturando?
  let _waitingResp = false;   // esperando resposta do Condor?
  let _engineReady = false;   // modelo LLM carregado?

  let _mediaRecorder = null;
  let _stream        = null;
  let _audioCtx      = null;
  let _analyser      = null;
  let _rafId         = null;

  // VAD — detecção de silêncio client-side
  let _hasSpeech    = false;  // já captou pelo menos um frame de fala
  let _silenceMs    = 0;      // ms acumulados de silêncio
  let _vadTimer     = null;
  const VAD_INTERVAL      = 60;    // ms entre checagens de nível de áudio
  const VAD_SPEECH_THRESH = 12;    // amplitude mínima para considerar fala (0–255)
  const VAD_SILENCE_CUT   = 1800;  // ms de silêncio antes de encerrar captura

  // ── Init ──────────────────────────────────────────────────────────────────
  function init() {
    _setLoading(true);

    // Orb = botão de modo conversa
    document.getElementById('voiceOrb').addEventListener('click', _onOrbClick);

    // Espaço também aciona (quando não está digitando)
    document.addEventListener('keydown', e => {
      if (e.code === 'Space' && e.target.tagName !== 'INPUT') {
        e.preventDefault();
        _onOrbClick();
      }
    });

    // Modelo pronto
    CondorWS.on('engine.ready', () => {
      _engineReady = true;
      _setLoading(false);
    });
    CondorWS.on('health.update', msg => {
      if (msg.model_loaded) { _engineReady = true; _setLoading(false); }
    });

    // TTS terminou → no modo conversa, reabre o mic automaticamente
    CondorWS.on('tts.done', () => {
      _waitingResp = false;
      if (_convMode && !_listening) {
        _updateHint('OUVINDO VOCÊ...');
        setTimeout(_startListening, 350);
      }
    });

    // STT retornou vazio (ruído, sem fala) → no modo conversa, reabre o mic
    CondorWS.on('stt.final', msg => {
      if (_convMode && !msg.text?.trim() && !_waitingResp) {
        _updateHint('NÃO ENTENDI — FALE DE NOVO');
        setTimeout(_startListening, 500);
      }
    });

    // Primeiro token do LLM chegou → para de escutar (Condor está respondendo)
    let _firstToken = true;
    CondorWS.on('llm.token', () => {
      if (_firstToken && _convMode && _listening) {
        _firstToken = false;
        _stopListening(false); // para mic, NÃO envia audio.end de novo
      }
    });
    CondorWS.on('llm.done', () => {
      _firstToken = true;
      _waitingResp = true;
      if (_convMode) _updateHint('CONDOR RESPONDENDO...');
    });

    // Reproduz TTS (se não estiver mutado)
    CondorWS.on('tts.audio', async msg => {
      const muteBtn = document.getElementById('muteBtn');
      if (muteBtn && muteBtn.textContent.trim() === '🔇') return;
      try {
        const bytes  = Uint8Array.from(atob(msg.data), c => c.charCodeAt(0));
        const blob   = new Blob([bytes], { type: 'audio/wav' });
        const url    = URL.createObjectURL(blob);
        const audio  = new Audio(url);
        audio.play();
        audio.onended = () => URL.revokeObjectURL(url);
      } catch (e) { console.error('[TTS]', e); }
    });
  }

  // ── Click no orb ──────────────────────────────────────────────────────────
  function _onOrbClick() {
    if (!_engineReady) {
      _updateHint('MODELO CARREGANDO — AGUARDE');
      return;
    }
    if (_convMode) {
      _exitConvMode();
    } else {
      _enterConvMode();
    }
  }

  // ── Entra no modo conversa ────────────────────────────────────────────────
  function _enterConvMode() {
    _convMode    = true;
    _waitingResp = false;
    _setOrbConvMode(true);
    _updateHint('MODO CONVERSA ATIVO — CLIQUE PARA SAIR');
    _startListening();
  }

  // ── Sai do modo conversa ──────────────────────────────────────────────────
  function _exitConvMode() {
    _convMode = false;
    if (_listening) _stopListening(false);
    clearInterval(_vadTimer);
    _vadTimer   = null;
    _hasSpeech  = false;
    _silenceMs  = 0;
    _setOrbConvMode(false);
    _updateHint('CLIQUE NO ORB PARA CONVERSAR POR VOZ');
    _setStatus('● VOZ INATIVA', 'PRONTO');
  }

  // ── Abre o microfone ──────────────────────────────────────────────────────
  async function _startListening() {
    if (_listening || !_convMode) return;

    try {
      _stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      _mediaRecorder = new MediaRecorder(_stream, { mimeType: _pickMime() });

      // Analisador para VAD e animação
      _audioCtx = new AudioContext();
      _analyser = _audioCtx.createAnalyser();
      _analyser.fftSize = 64;
      _audioCtx.createMediaStreamSource(_stream).connect(_analyser);

      _mediaRecorder.ondataavailable = async e => {
        if (e.data.size > 0 && _convMode) {
          const buf = await e.data.arrayBuffer();
          const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
          CondorWS.send({ type: 'audio.chunk', data: b64 });
        }
      };

      _mediaRecorder.onstop = () => {
        _stream?.getTracks().forEach(t => t.stop());
        cancelAnimationFrame(_rafId);
        if (_audioCtx) { _audioCtx.close(); _audioCtx = null; }
        _analyser = null;
        document.getElementById('orbCore').style.transform = 'scale(1)';
      };

      _mediaRecorder.start(200);
      _listening  = true;
      _hasSpeech  = false;
      _silenceMs  = 0;
      _setStatus('● OUVINDO', 'GRAVANDO');
      document.getElementById('orbCore').classList.add('active');
      _startVAD();
      _animateOrb();

    } catch (err) {
      console.error('[MIC]', err);
      _exitConvMode();
      alert('Acesso ao microfone negado. Permita nas configurações do browser.');
    }
  }

  // ── Fecha o microfone (e opcionalmente envia audio.end) ───────────────────
  function _stopListening(sendEnd = true) {
    if (!_listening) return;
    _listening = false;

    clearInterval(_vadTimer);
    _vadTimer  = null;
    document.getElementById('orbCore').classList.remove('active');
    _setStatus('● PROCESSANDO', 'AGUARDE');

    if (_mediaRecorder && _mediaRecorder.state !== 'inactive') {
      _mediaRecorder.stop();
    }
    if (sendEnd) {
      CondorWS.send({ type: 'audio.end' });
    }
    _mediaRecorder = null;
    _stream        = null;
  }

  // ── VAD — detecta silêncio e encerra captura automaticamente ─────────────
  function _startVAD() {
    clearInterval(_vadTimer);
    _vadTimer = setInterval(() => {
      if (!_analyser || !_listening) return;

      const buf = new Uint8Array(_analyser.frequencyBinCount);
      _analyser.getByteFrequencyData(buf);
      const avg = buf.reduce((a, b) => a + b, 0) / buf.length;

      if (avg >= VAD_SPEECH_THRESH) {
        // Fala detectada
        _hasSpeech = true;
        _silenceMs = 0;
      } else {
        // Silêncio
        if (_hasSpeech) {
          _silenceMs += VAD_INTERVAL;
          if (_silenceMs >= VAD_SILENCE_CUT) {
            // Silêncio suficiente após fala → envia
            _silenceMs = 0;
            _hasSpeech = false;
            _stopListening(true);
          }
        }
      }
    }, VAD_INTERVAL);
  }

  // ── Animação do orb (pulsação com nível de áudio) ─────────────────────────
  function _animateOrb() {
    const core = document.getElementById('orbCore');
    function loop() {
      if (!_analyser) return;
      const buf = new Uint8Array(_analyser.frequencyBinCount);
      _analyser.getByteFrequencyData(buf);
      const avg = buf.reduce((a, b) => a + b, 0) / buf.length;
      core.style.transform = `scale(${1 + (avg / 255) * 0.3})`;
      _rafId = requestAnimationFrame(loop);
    }
    loop();
  }

  // ── Helpers de UI ─────────────────────────────────────────────────────────
  function _setOrbConvMode(active) {
    const core = document.getElementById('orbCore');
    const icon = core.querySelector('i');
    if (active) {
      core.style.background = 'radial-gradient(circle at 35% 30%, #F472B6 0%, #8B7CFF 60%, #4A3FCC 100%)';
      core.style.boxShadow  = '0 0 30px rgba(244,114,182,.6), inset 0 0 12px rgba(255,255,255,.2)';
      if (icon) icon.className = 'ti ti-wave-saw-tool';
    } else {
      core.style.background = 'radial-gradient(circle at 35% 30%, var(--cyan) 0%, var(--violet) 60%, #4A3FCC 100%)';
      core.style.boxShadow  = '0 0 20px rgba(94,234,212,.5), inset 0 0 12px rgba(255,255,255,.2)';
      if (icon) icon.className = 'ti ti-microphone';
    }
  }

  function _setStatus(voiceText, listenText) {
    const vs = document.getElementById('voiceStatus');
    const ls = document.getElementById('listenStatus');
    if (vs) vs.textContent = voiceText;
    if (ls) ls.textContent = listenText;
  }

  function _updateHint(text) {
    const h = document.getElementById('voiceHint');
    if (h) h.textContent = text;
  }

  function _setLoading(loading) {
    const core = document.getElementById('orbCore');
    const orb  = document.getElementById('voiceOrb');
    if (!core) return;
    if (loading) {
      core.style.opacity = '0.45';
      orb.style.cursor   = 'not-allowed';
      _setStatus('● CARREGANDO', 'AGUARDE...');
      _updateHint('MODELO CARREGANDO...');
    } else {
      core.style.opacity = '1';
      orb.style.cursor   = 'pointer';
      _setStatus('● VOZ INATIVA', 'PRONTO');
      _updateHint('CLIQUE NO ORB PARA CONVERSAR POR VOZ');
    }
  }

  function _pickMime() {
    const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
    return types.find(t => MediaRecorder.isTypeSupported(t)) || '';
  }

  return { init };
})();
