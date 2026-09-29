/**
 * Áudio do CONDOR no iPhone.
 *
 * - Voz: toca, em fila, os trechos que o PC sintetiza frase a frase. Com fone
 *   conectado (AirPods ou com fio), o iOS manda o som para ele sozinho.
 * - Microfone: um detector de fala simples corta cada frase (começo = voz acima
 *   do ruído, fim = silêncio) e entrega um WAV 16 kHz mono. Nada é gravado no
 *   celular; só a frase falada vai para o PC.
 */
const CondorAudio = (() => {
  const TAXA_SAIDA = 16000;
  let contexto = null;
  let microfone = null;          // { stream, fonte, no }
  let ouvinte = null;            // callback(wav, meta)
  let modo = 'parado';           // 'parado' | 'frase' (botão) | 'escuta' (contínua)
  let tocando = 0;
  let fila = [];
  let turnoAtual = '';
  let fonteAtual = null;
  let mudoAte = 0;
  let inicioFrase = 0;

  // Detector de fala
  let ruido = 0.004;
  let falando = false;
  let blocosVoz = 0;
  let silencioMs = 0;
  let duracaoMs = 0;
  let preRoll = [];
  let frase = [];
  let aoMudarNivel = null;
  let aoFimFrase = null;

  function sessao(tipo) {
    try { if (navigator.audioSession) navigator.audioSession.type = tipo; } catch (_) { /* Safari antigo */ }
  }

  async function ligar() {
    if (!contexto) {
      const Contexto = window.AudioContext || window.webkitAudioContext;
      contexto = new Contexto({ latencyHint: 'interactive' });
    }
    // "playback" toca mesmo com o iPhone no silencioso.
    if (!microfone) sessao('playback');
    if (contexto.state !== 'running') await contexto.resume();
    return contexto;
  }

  // ── Voz do CONDOR ─────────────────────────────────────────────────────

  function base64ParaBuffer(b64) {
    const binario = atob(b64);
    const bytes = new Uint8Array(binario.length);
    for (let i = 0; i < binario.length; i += 1) bytes[i] = binario.charCodeAt(i);
    return bytes.buffer;
  }

  async function receber(msg) {
    if (!contexto || !msg.wav) return;
    if (msg.turno !== turnoAtual) { parar(); turnoAtual = msg.turno; }
    try {
      const buffer = await contexto.decodeAudioData(base64ParaBuffer(msg.wav));
      if (msg.turno !== turnoAtual) return;
      fila.push(buffer);
      if (!fonteAtual) tocarProximo();
    } catch (_) { /* trecho corrompido: segue o próximo */ }
  }

  function tocarProximo() {
    const buffer = fila.shift();
    if (!buffer) { fonteAtual = null; tocando = 0; mudoAte = performance.now() + 500; avisarNivel(); return; }
    const fonte = contexto.createBufferSource();
    fonte.buffer = buffer;
    fonte.connect(contexto.destination);
    fonte.onended = () => { if (fonteAtual === fonte) tocarProximo(); };
    fonteAtual = fonte;
    tocando = 1;
    avisarNivel();
    fonte.start();
  }

  function parar() {
    fila = [];
    const fonte = fonteAtual;
    fonteAtual = null;
    tocando = 0;
    if (fonte) { try { fonte.stop(); } catch (_) { /* já parou */ } }
    mudoAte = performance.now() + 300;
    avisarNivel();
  }

  const estaTocando = () => Boolean(fonteAtual);

  // ── Microfone ─────────────────────────────────────────────────────────

  async function abrirMicrofone() {
    // Em segundo plano o iOS encerra a faixa do microfone: reabre em vez de ouvir o nada.
    if (microfone && microfone.stream.getAudioTracks().some((faixa) => faixa.readyState === 'live')) return;
    if (microfone) fecharMicrofone();
    await ligar();
    sessao('play-and-record');
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
    if (!contexto.audioWorklet) throw new Error('este iPhone não tem AudioWorklet');
    await contexto.audioWorklet.addModule('gravador-worklet.js');
    const fonte = contexto.createMediaStreamSource(stream);
    const no = new AudioWorkletNode(contexto, 'condor-gravador');
    no.port.onmessage = (evento) => quadro(evento.data);
    fonte.connect(no);
    // O nó precisa estar ligado na saída para o Safari chamar process(); volume zero.
    const mudo = contexto.createGain();
    mudo.gain.value = 0;
    no.connect(mudo).connect(contexto.destination);
    microfone = { stream, fonte, no, mudo };
  }

  function fecharMicrofone() {
    if (!microfone) return;
    microfone.stream.getTracks().forEach((faixa) => faixa.stop());
    try { microfone.fonte.disconnect(); microfone.no.disconnect(); microfone.mudo.disconnect(); } catch (_) { /* ok */ }
    microfone = null;
    sessao('playback');
  }

  function reiniciarFrase() {
    falando = false; blocosVoz = 0; silencioMs = 0; duracaoMs = 0; frase = []; preRoll = [];
  }

  function quadro(amostras) {
    if (modo === 'parado' || !contexto) return;
    limiteDaFrase();
    if (modo === 'parado') return;
    // Enquanto o CONDOR fala, não escuta (a própria voz dispararia a escuta).
    if (modo === 'escuta' && (fonteAtual || performance.now() < mudoAte)) { reiniciarFrase(); return; }
    const ms = (amostras.length / contexto.sampleRate) * 1000;
    let soma = 0;
    for (let i = 0; i < amostras.length; i += 1) soma += amostras[i] * amostras[i];
    const rms = Math.sqrt(soma / amostras.length);
    const limiar = Math.max(0.012, ruido * 3.2);
    const voz = rms > limiar;
    if (aoMudarNivel) aoMudarNivel(Math.min(1, rms / 0.12), falando);

    if (!falando) {
      ruido = ruido * 0.97 + Math.min(rms, 0.05) * 0.03;
      preRoll.push(amostras);
      while (preRoll.length > 20) preRoll.shift();   // ~300 ms antes da fala
      blocosVoz = voz ? blocosVoz + 1 : 0;
      if (blocosVoz >= 4) { falando = true; frase = preRoll.slice(); preRoll = []; duracaoMs = 0; silencioMs = 0; }
      return;
    }
    frase.push(amostras);
    duracaoMs += ms;
    silencioMs = voz ? 0 : silencioMs + ms;
    const fimSilencio = modo === 'frase' ? 1300 : 950;
    if (silencioMs >= fimSilencio || duracaoMs >= 12000) finalizarFrase();
  }

  function limiteDaFrase() {
    // Tocou no microfone e não falou nada: fecha sozinho em 15 s.
    if (modo === 'frase' && !falando && performance.now() - inicioFrase > 15000) {
      modo = 'parado';
      reiniciarFrase();
      if (aoFimFrase) aoFimFrase(true);
    }
  }

  function finalizarFrase() {
    const blocos = frase;
    const taxa = contexto.sampleRate;
    const duracao = duracaoMs;
    reiniciarFrase();
    if (duracao < 350) return;
    const wav = paraWav(blocos, taxa);
    const eraFrase = modo === 'frase';
    if (eraFrase) modo = 'parado';
    if (ouvinte) ouvinte(wav, { comNome: !eraFrase });
    if (aoFimFrase) aoFimFrase(eraFrase);
  }

  function paraWav(blocos, taxaEntrada) {
    let total = 0;
    blocos.forEach((bloco) => { total += bloco.length; });
    const entrada = new Float32Array(total);
    let pos = 0;
    blocos.forEach((bloco) => { entrada.set(bloco, pos); pos += bloco.length; });
    // Reamostra para 16 kHz pela média de cada janela (filtra o grosso do aliasing).
    const razao = taxaEntrada / TAXA_SAIDA;
    const saida = new Int16Array(Math.floor(entrada.length / razao));
    for (let i = 0; i < saida.length; i += 1) {
      const inicio = Math.floor(i * razao);
      const fim = Math.min(entrada.length, Math.floor((i + 1) * razao));
      let soma = 0;
      for (let j = inicio; j < fim; j += 1) soma += entrada[j];
      const valor = Math.max(-1, Math.min(1, soma / Math.max(1, fim - inicio)));
      saida[i] = valor < 0 ? valor * 0x8000 : valor * 0x7fff;
    }
    const buffer = new ArrayBuffer(44 + saida.length * 2);
    const vista = new DataView(buffer);
    const escrever = (offset, texto) => { for (let i = 0; i < texto.length; i += 1) vista.setUint8(offset + i, texto.charCodeAt(i)); };
    escrever(0, 'RIFF'); vista.setUint32(4, 36 + saida.length * 2, true); escrever(8, 'WAVE');
    escrever(12, 'fmt '); vista.setUint32(16, 16, true); vista.setUint16(20, 1, true); vista.setUint16(22, 1, true);
    vista.setUint32(24, TAXA_SAIDA, true); vista.setUint32(28, TAXA_SAIDA * 2, true);
    vista.setUint16(32, 2, true); vista.setUint16(34, 16, true);
    escrever(36, 'data'); vista.setUint32(40, saida.length * 2, true);
    new Int16Array(buffer, 44).set(saida);
    let binario = '';
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.length; i += 0x8000) binario += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(binario);
  }

  function avisarNivel() { if (aoMudarNivel) aoMudarNivel(0, falando); }

  async function ouvirFrase() {
    await abrirMicrofone();
    parar();
    reiniciarFrase();
    inicioFrase = performance.now();
    modo = 'frase';
  }

  function cancelarFrase(manterMicrofone) {
    if (modo === 'frase') {
      if (falando && duracaoMs >= 350) { finalizarFrase(); } else { reiniciarFrase(); modo = 'parado'; }
    }
    if (!manterMicrofone && modo === 'parado') fecharMicrofone();
  }

  async function ligarEscuta() {
    await abrirMicrofone();
    reiniciarFrase();
    modo = 'escuta';
  }

  function desligarEscuta() {
    if (modo === 'escuta') modo = 'parado';
    reiniciarFrase();
    fecharMicrofone();
  }

  return {
    ligar, receber, parar, ativo: () => Boolean(contexto && contexto.state === 'running'), estaTocando, ouvirFrase, cancelarFrase, ligarEscuta, desligarEscuta,
    paraWav,
    get modo() { return modo; },
    set ouvinte(fn) { ouvinte = fn; },
    set aoMudarNivel(fn) { aoMudarNivel = fn; },
    set aoFimFrase(fn) { aoFimFrase = fn; },
    get tocando() { return tocando; },
  };
})();
