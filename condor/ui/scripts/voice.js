/**
 * CondorVoz — o estado da voz na tela.
 *
 * O clique no orbe ou no Condor Pet grava somente a fala atual e envia ao STT local. Se o dono
 * configurar um detector passivo, a palavra Condor também pode acordar o app.
 * Em ambos os casos o áudio permanece no próprio PC.
 */
const CondorVoz = (() => {
  const $ = (id) => document.getElementById(id);

  const ESTADOS = {
    dormindo: { rotulo: '● DORMINDO', cor: 'var(--text-dim)', dica: 'DIGA "CONDOR" PRA ME CHAMAR' },
    ouvindo:  { rotulo: '● NA ESCUTA', cor: 'var(--cyan)',    dica: 'PODE FALAR' },
    pensando: { rotulo: '● PENSANDO',  cor: 'var(--violet)',  dica: 'PROCESSANDO' },
    falando:  { rotulo: '● FALANDO',   cor: 'var(--cyan)',    dica: 'FALANDO' },
    senha:    { rotulo: '● SENHA',     cor: 'var(--pink)',    dica: 'CONFIRME A SENHA' },
  };

  let restam = 0;
  let relogio = null;
  let palavra = 'condor';
  let gravador = null;
  let fluxo = null;
  let partes = [];
  let limiteGravacao = null;
  let continuous = false;
  let microphoneAuthorized = false;
  let microphonePending = false;
  let restartTimer = null;
  let silenceMonitor = null;
  let cancelRecording = false;

  function init() {
    CondorWS.ao('estado', aplicar);
    CondorWS.ao('tique', (m) => { restam = m.restam; pintarRelogio(); });
    CondorWS.ao('acordou', () => aplicar({ estado: 'ouvindo', acordado: true }));
    CondorWS.ao('dormiu', () => aplicar({ estado: 'dormindo', acordado: false }));
    CondorWS.ao('custo', pintarCusto);
    CondorWS.ao('memoria.stats', (m) => {
      $('tokenCount').textContent = `${m.fatos ?? 0} fatos · ${m.turnos ?? 0} turnos`;
    });
    CondorWS.ao('senha.pedido', pedirSenha);
    CondorWS.ao('senha.fim', fecharSenha);
    CondorWS.ao('ws.caiu', () => {
      $('listenStatus').textContent = 'SEM CONEXÃO';
      $('listenStatus').style.color = 'var(--pink)';
    });

    // Clique uma vez para começar e outra para enviar. O limite de vinte
    // segundos encerra sozinho para o microfone nunca ficar aberto sem querer.
    $('voiceOrb').addEventListener('click', alternarGravacaoLocal);
    window.addEventListener('condor-permission-resolved', (event) => {
      if (!microphonePending || event.detail?.capability !== 'microphone') return;
      microphonePending = false;
      microphoneAuthorized = event.detail.decision !== 'block';
      if (microphoneAuthorized) iniciarGravacaoLocal(false);
    });

    relogio = setInterval(() => {
      if (restam > 0) { restam -= 1; pintarRelogio(); }
    }, 1000);
  }

  function aplicar(m) {
    const nome = m.estado || 'dormindo';
    const e = ESTADOS[nome] || ESTADOS.dormindo;
    if (nome !== 'ouvindo') clearTimeout(restartTimer);

    const status = $('voiceStatus');
    status.textContent = e.rotulo;
    status.style.color = e.cor;

    $('orbCore').classList.toggle('active', nome === 'ouvindo' || nome === 'falando');
    $('frame').classList.toggle('is-dormindo', nome === 'dormindo');
    $('voiceHint').textContent = e.dica;

    if (m.palavra) palavra = m.palavra;
    if (typeof m.restam === 'number') restam = m.restam;
    if (m.modelo) $('modelName').textContent = m.modelo;

    if (m.stt_local_pronto) {
      $('listenStatus').textContent = m.escuta_ativa
        ? `ESPERANDO "${palavra.toUpperCase()}"`
        : 'VOZ LOCAL PRONTA';
      $('listenStatus').style.color = 'var(--cyan)';
      if (!gravador || gravador.state !== 'recording') {
        $('voiceHint').textContent = 'CLIQUE NO ORBE PARA FALAR — ÁUDIO LOCAL';
      }
    } else if (m.escuta_ativa === false && m.motivo_escuta) {
      $('listenStatus').textContent = 'VOZ INDISPONÍVEL';
      $('listenStatus').style.color = 'var(--pink)';
      $('voiceHint').textContent = m.motivo_escuta.toUpperCase();
    } else if (m.escuta_ativa) {
      $('listenStatus').style.color = 'var(--cyan)';
      pintarRelogio();
    }
    if (m.cerebro_pronto === false) {
      $('modelName').textContent = 'modo apresentação';
      $('modelName').style.color = 'var(--amber)';
    }
    if (nome === 'ouvindo' && continuous && (!gravador || gravador.state !== 'recording')) {
      clearTimeout(restartTimer);
      restartTimer = setTimeout(() => iniciarGravacaoLocal(true), 520);
    }
  }

  async function alternarGravacaoLocal() {
    if (gravador && gravador.state === 'recording') {
      gravador.stop();
      return;
    }
    await iniciarGravacaoLocal(false);
  }

  async function autorizarMicrofone() {
    if (microphoneAuthorized) return true;
    if (typeof CondorMedia === 'undefined') return false;
    microphoneAuthorized = await CondorMedia.ensurePermission(
      'microphone', 'Ouvir somente enquanto o modo de voz estiver ativo.', 'voice_chat',
    );
    microphonePending = !microphoneAuthorized;
    return microphoneAuthorized;
  }

  async function iniciarGravacaoLocal(autoStop) {
    if (gravador?.state === 'recording') return;
    if (!await autorizarMicrofone()) return;
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      CondorWS.enviar({ tipo: 'acordar' });
      $('voiceHint').textContent = 'NAVEGADOR SEM CAPTURA DE ÁUDIO';
      return;
    }
    try {
      fluxo = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
        video: false,
      });
      const preferido = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
        .find((tipo) => MediaRecorder.isTypeSupported(tipo));
      gravador = new MediaRecorder(fluxo, preferido ? { mimeType: preferido } : undefined);
      partes = [];
      cancelRecording = false;
      gravador.addEventListener('dataavailable', (evento) => {
        if (evento.data.size) partes.push(evento.data);
      });
      gravador.addEventListener('stop', enviarGravacaoLocal, { once: true });
      gravador.start(250);
      if (autoStop) monitorarSilencio(fluxo);
      limiteGravacao = setTimeout(() => {
        if (gravador && gravador.state === 'recording') gravador.stop();
      }, 20000);
      $('voiceStatus').textContent = '● GRAVANDO';
      $('voiceStatus').style.color = 'var(--pink)';
      $('voiceHint').textContent = 'FALE AGORA · CLIQUE DE NOVO PARA ENVIAR';
      if (continuous) $('voiceHint').textContent = 'CONVERSA CONTÍNUA · PODE FALAR';
      $('orbCore').classList.add('active');
      CondorPet.setState('listening');
    } catch (erro) {
      $('voiceHint').textContent = 'PERMISSÃO DO MICROFONE NÃO CONCEDIDA';
      $('listenStatus').textContent = 'MICROFONE BLOQUEADO';
      $('listenStatus').style.color = 'var(--pink)';
    }
  }

  async function enviarGravacaoLocal() {
    clearTimeout(limiteGravacao);
    pararMonitorSilencio();
    if (fluxo) fluxo.getTracks().forEach((trilha) => trilha.stop());
    if (cancelRecording) {
      partes = []; gravador = null; fluxo = null; cancelRecording = false; return;
    }
    $('voiceStatus').textContent = '● TRANSCREVENDO';
    $('voiceStatus').style.color = 'var(--violet)';
    $('voiceHint').textContent = 'FASTER WHISPER · PROCESSAMENTO LOCAL';
    try {
      const tipo = gravador && gravador.mimeType ? gravador.mimeType : 'audio/webm';
      const audio = new Blob(partes, { type: tipo });
      if (audio.size < 256) throw new Error('gravação vazia');
      const resposta = await fetch('/api/voice/transcribe', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': tipo },
        body: audio,
      });
      const dados = await resposta.json();
      if (!resposta.ok) throw new Error(dados.erro || 'não entendi a fala');
      CondorConversa.adicionarUsuario(dados.texto);
      $('voiceHint').textContent = 'CONDOR ESTÁ PROCESSANDO LOCALMENTE';
      CondorPet.setState('thinking');
    } catch (erro) {
      $('voiceStatus').textContent = '● VOZ LOCAL';
      $('voiceStatus').style.color = 'var(--cyan)';
      $('voiceHint').textContent = String(erro.message || erro).toUpperCase();
      if (continuous) restartTimer = setTimeout(() => iniciarGravacaoLocal(true), 900);
    } finally {
      partes = [];
      gravador = null;
      fluxo = null;
    }
  }

  function monitorarSilencio(stream) {
    pararMonitorSilencio();
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const context = new AudioCtx(); const analyser = context.createAnalyser();
    analyser.fftSize = 512; context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize); const started = performance.now();
    let heardSpeech = false; let lastSpeech = started;
    const timer = setInterval(() => {
      if (!gravador || gravador.state !== 'recording') return pararMonitorSilencio();
      analyser.getByteTimeDomainData(samples);
      let energy = 0; for (const value of samples) { const normalized = (value - 128) / 128; energy += normalized * normalized; }
      const rms = Math.sqrt(energy / samples.length); const now = performance.now();
      if (rms > .035) { heardSpeech = true; lastSpeech = now; }
      if ((heardSpeech && now - lastSpeech > 1050) || (!heardSpeech && now - started > 8000)) gravador.stop();
    }, 120);
    silenceMonitor = { timer, context };
  }

  function pararMonitorSilencio() {
    if (!silenceMonitor) return;
    clearInterval(silenceMonitor.timer); silenceMonitor.context.close().catch(() => {}); silenceMonitor = null;
  }

  function pintarRelogio() {
    const alvo = $('listenStatus');
    if (restam > 0) {
      const min = Math.floor(restam / 60);
      const seg = String(restam % 60).padStart(2, '0');
      alvo.textContent = `DORME EM ${min}:${seg}`;
      alvo.style.color = restam <= 20 ? 'var(--amber)' : 'var(--cyan)';
    } else {
      alvo.textContent = `ESPERANDO "${palavra.toUpperCase()}"`;
      alvo.style.color = 'var(--text-dim)';
    }
  }

  function pintarCusto(m) {
    const el = $('custoHoje');
    if (el) el.textContent = `US$ ${(m.hoje_usd ?? 0).toFixed(3)} hoje`;
  }

  // ── Senha ─────────────────────────────────────────────────────────────

  function pedirSenha(m) {
    fecharSenha();
    const caixa = document.createElement('div');
    caixa.id = 'senhaBox';
    caixa.className = 'senha-box';
    caixa.innerHTML = `
      <div class="senha-titulo"><span aria-hidden="true">▣</span> AÇÃO TRAVADA</div>
      <div class="senha-motivo"></div>
      <div class="senha-linha">
        <input id="senhaInput" type="password" placeholder="digite sua palavra de acesso" autocomplete="off">
        <button id="senhaOk">CONFIRMAR</button>
        <button id="senhaNao" class="secundario">CANCELAR</button>
      </div>
      <div class="senha-dica">por segurança, voz nunca autoriza esta ação</div>`;
    caixa.querySelector('.senha-motivo').textContent = m.motivo || '';
    document.getElementById('frame').appendChild(caixa);

    const campo = caixa.querySelector('#senhaInput');
    campo.focus();
    const mandar = () => {
      const v = campo.value.trim();
      if (v) { CondorWS.mandarSenha(v); fecharSenha(); }
    };
    caixa.querySelector('#senhaOk').addEventListener('click', mandar);
    caixa.querySelector('#senhaNao').addEventListener('click', () => {
      CondorWS.mandarSenha('cancelar');
      fecharSenha();
    });
    campo.addEventListener('keydown', (e) => { if (e.key === 'Enter') mandar(); });
  }

  function fecharSenha() {
    const antigo = document.getElementById('senhaBox');
    if (antigo) antigo.remove();
  }

  function stopForSecurity() {
    continuous = false; cancelRecording = true;
    clearTimeout(restartTimer); clearTimeout(limiteGravacao); pararMonitorSilencio();
    if (gravador?.state === 'recording') gravador.stop();
    fluxo?.getTracks().forEach((track) => track.stop()); fluxo = null;
  }

  return { init, pedirSenha, fecharSenha, stopForSecurity, toggleLocalVoice: alternarGravacaoLocal };
})();
