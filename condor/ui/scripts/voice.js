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
  let capturePending = false;
  let securityGeneration = 0;

  // ── A voz do Condor tocada pela própria janela ──────────────────────────
  // O servidor manda uma frase por vez enquanto ainda gera o resto. Tocar
  // aqui (e não pelo Python) deixa o cancelamento de eco do microfone
  // funcionar e permite interromper o Condor no meio da fala.
  const Tocador = (() => {
    let ctx = null;
    let turno = null;
    let turnoCancelado = null;
    let fimPrevisto = 0;
    let fontes = [];
    let cadeia = Promise.resolve();
    let anunciado = null;

    function contexto() {
      if (ctx) return ctx;
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      ctx = new Ctx();
      ctx.addEventListener('statechange', () => anunciar());
      return ctx;
    }

    // Só se declara tocador com o áudio liberado; antes disso o servidor
    // continua falando pelas caixas do PC e nada se perde.
    function anunciar(forcar = false) {
      const pronto = !!ctx && ctx.state === 'running';
      if (!forcar && pronto === anunciado) return;
      anunciado = pronto;
      CondorWS.enviar({ tipo: 'voz.player', ativo: pronto });
    }

    function liberar() {
      const c = contexto();
      if (!c) return;
      if (c.state === 'running') anunciar();
      else c.resume().then(() => anunciar()).catch(() => {});
    }

    function bytes(base64) {
      const bruto = atob(base64);
      const saida = new Uint8Array(bruto.length);
      for (let i = 0; i < bruto.length; i += 1) saida[i] = bruto.charCodeAt(i);
      return saida.buffer;
    }

    function receber(m) {
      const c = contexto();
      if (!c || !m.wav || m.turno === turnoCancelado) return;
      if (m.turno !== turno) { pararFontes(); turno = m.turno; }
      cadeia = cadeia.then(async () => {
        const audio = await c.decodeAudioData(bytes(m.wav));
        if (m.turno !== turno || m.turno === turnoCancelado) return;
        const fonte = c.createBufferSource();
        fonte.buffer = audio;
        fonte.connect(c.destination);
        const inicio = Math.max(c.currentTime + 0.03, fimPrevisto);
        fonte.start(inicio);
        fimPrevisto = inicio + audio.duration;
        fontes.push(fonte);
        fonte.addEventListener('ended', () => { fontes = fontes.filter(f => f !== fonte); });
      }).catch((erro) => console.warn('[voz] não consegui tocar a frase', erro));
    }

    function pararFontes() {
      fontes.forEach((fonte) => { try { fonte.stop(); } catch (_) { /* já parou */ } });
      fontes = [];
      fimPrevisto = 0;
    }

    function parar(avisarServidor) {
      // Entre uma frase e outra "fontes" fica vazio, mas o servidor ainda está
      // falando: o que importa é haver um turno de fala não cancelado.
      const ativo = !!turno && turno !== turnoCancelado;
      if (turno) turnoCancelado = turno;
      pararFontes();
      if (avisarServidor && ativo) CondorWS.enviar({ tipo: 'voz.parar' });
      return ativo;
    }

    function cancelarTurno(m) {
      turnoCancelado = m?.turno || turno;
      pararFontes();
    }

    return { liberar, anunciar, receber, parar, cancelarTurno, tocando: () => fontes.length > 0 };
  })();

  function init() {
    CondorWS.ao('voz.audio', Tocador.receber);
    CondorWS.ao('voz.parar', Tocador.cancelarTurno);
    CondorWS.ao('ws.ligado', () => Tocador.anunciar(true));
    // Navegadores só liberam áudio depois de um gesto do dono.
    ['pointerdown', 'keydown'].forEach((tipo) => document.addEventListener(tipo, Tocador.liberar, { capture: true }));
    Tocador.liberar();
    pintarOrbe();
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
      stopForSecurity();
      $('listenStatus').textContent = 'SEM CONEXÃO';
      $('listenStatus').style.color = 'var(--pink)';
    });

    // Clique uma vez para começar e outra para enviar. O limite de vinte
    // segundos encerra sozinho para o microfone nunca ficar aberto sem querer.
    $('voiceOrb').addEventListener('click', alternarGravacaoLocal);
    $('continuousVoiceBtn').addEventListener('click', toggleContinuous);
    CondorWS.ao('seguranca.bloqueado', stopForSecurity);
    CondorWS.ao('erro', stopForSecurity);
    window.addEventListener('pagehide', stopForSecurity);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') { Tocador.parar(true); stopForSecurity(); }
    });
    window.addEventListener('condor-permission-resolved', (event) => {
      if (!microphonePending || event.detail?.capability !== 'microphone') return;
      microphonePending = false;
      microphoneAuthorized = event.detail.decision !== 'block';
      if (microphoneAuthorized) iniciarGravacaoLocal(continuous);
      else stopForSecurity();
    });

    relogio = setInterval(() => {
      if (restam > 0) { restam -= 1; pintarRelogio(); }
    }, 1000);
  }

  // Cor do botão de falar: verde quando dá para falar, verde forte gravando,
  // violeta pensando, ciano falando. Dormindo também está pronto: basta clicar.
  let estadoSessao = 'dormindo';
  function pintarOrbe(forcado) {
    const orbe = $('voiceOrb');
    if (!orbe) return;
    let voz = forcado;
    if (!voz) {
      if (gravador && gravador.state === 'recording') voz = 'gravando';
      else if (estadoSessao === 'pensando') voz = 'pensando';
      else if (estadoSessao === 'falando') voz = 'falando';
      else if (estadoSessao === 'senha') voz = 'pensando';
      else voz = 'pronto';
    }
    orbe.setAttribute('data-voz', voz);
    orbe.setAttribute('title', {
      pronto: 'Clique para falar', gravando: 'Gravando · clique para enviar',
      pensando: 'Pensando...', falando: 'Falando · clique para interromper',
    }[voz] || '');
  }

  function aplicar(m) {
    const nome = m.estado || 'dormindo';
    const e = ESTADOS[nome] || ESTADOS.dormindo;
    if (nome !== 'ouvindo') clearTimeout(restartTimer);
    estadoSessao = nome;
    pintarOrbe();

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
    // Clicar enquanto ele fala interrompe a fala e já abre o microfone.
    Tocador.parar(true);
    if (gravador && gravador.state === 'recording') {
      gravador.stop();
      return;
    }
    await iniciarGravacaoLocal(false);
  }

  async function autorizarMicrofone() {
    if (typeof CondorMedia === 'undefined') return false;
    microphoneAuthorized = await CondorMedia.ensurePermission(
      'microphone', 'Ouvir somente enquanto o modo de voz estiver ativo.', 'voice_chat',
      { requireAlways: continuous },
    );
    microphonePending = !microphoneAuthorized;
    return microphoneAuthorized;
  }

  async function iniciarGravacaoLocal(autoStop) {
    if (gravador || capturePending) return;
    capturePending = true;
    const generation = securityGeneration;
    try {
    if (!await autorizarMicrofone() || generation !== securityGeneration) return;
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
      if (generation !== securityGeneration) { fluxo.getTracks().forEach(t=>t.stop()); fluxo=null; return; }
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
      pintarOrbe('gravando');
      CondorPet.setState('listening');
    } catch (erro) {
      stopForSecurity();
      $('voiceHint').textContent = 'PERMISSÃO DO MICROFONE NÃO CONCEDIDA';
      $('listenStatus').textContent = 'MICROFONE BLOQUEADO';
      $('listenStatus').style.color = 'var(--pink)';
    }
    } catch (error) {
      stopForSecurity(); $('voiceHint').textContent='VOZ INDISPONÍVEL · VERIFIQUE AS PERMISSÕES NO SISTEMA';
    } finally { capturePending=false; }
  }

  async function toggleContinuous() {
    if (continuous) { stopForSecurity(); $('voiceHint').textContent='CONVERSA CONTÍNUA ENCERRADA'; return; }
    continuous=true;
    $('continuousVoiceBtn').textContent='ENCERRAR VOZ';
    $('continuousVoiceBtn').setAttribute('aria-pressed','true');
    await iniciarGravacaoLocal(true);
  }

  async function enviarGravacaoLocal() {
    const generation = securityGeneration;
    clearTimeout(limiteGravacao);
    pararMonitorSilencio();
    if (fluxo) fluxo.getTracks().forEach((trilha) => trilha.stop());
    if (cancelRecording) {
      partes = []; gravador = null; fluxo = null; cancelRecording = false; pintarOrbe(); return;
    }
    pintarOrbe('pensando');
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
      if (generation !== securityGeneration) return;
      if (!resposta.ok) throw new Error(dados.erro || 'não entendi a fala');
      CondorConversa.adicionarUsuario(dados.texto);
      $('voiceHint').textContent = 'CONDOR ESTÁ PROCESSANDO LOCALMENTE';
      CondorPet.setState('thinking');
    } catch (erro) {
      $('voiceStatus').textContent = '● VOZ LOCAL';
      $('voiceStatus').style.color = 'var(--cyan)';
      $('voiceHint').textContent = String(erro.message || erro).toUpperCase();
      stopForSecurity();
    } finally {
      partes = [];
      gravador = null;
      fluxo = null;
      pintarOrbe();
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
      if (!heardSpeech && now - started > 8000) {
        stopForSecurity(); $('voiceHint').textContent='VOZ PAUSADA · NENHUMA FALA DETECTADA';
      } else if (heardSpeech && now - lastSpeech > 1050) gravador.stop();
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
    Tocador.parar(false);
    securityGeneration++; microphoneAuthorized=false; microphonePending=false;
    continuous = false; cancelRecording = true;
    if ($('continuousVoiceBtn')) { $('continuousVoiceBtn').textContent='CONVERSA CONTÍNUA'; $('continuousVoiceBtn').setAttribute('aria-pressed','false'); }
    clearTimeout(restartTimer); clearTimeout(limiteGravacao); pararMonitorSilencio();
    if (gravador?.state === 'recording') gravador.stop();
    fluxo?.getTracks().forEach((track) => track.stop()); fluxo = null;
    setTimeout(() => pintarOrbe(), 0);
  }

  return {
    init, pedirSenha, fecharSenha, stopForSecurity, toggleLocalVoice: alternarGravacaoLocal,
    calar: () => Tocador.parar(true),
  };
})();
