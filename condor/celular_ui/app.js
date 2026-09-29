/**
 * CONDOR no iPhone: a mesma conversa do PC, por texto ou voz.
 *
 * - Mensagem: escreve e envia; a resposta vem em texto.
 * - Microfone: toca, fala, ele percebe quando você parou e responde em voz.
 * - Escuta "Condor": com a tela aberta, fale "Condor, ..." a qualquer hora.
 *   O iPhone não deixa site ouvir com a tela bloqueada; por isso a tela fica
 *   acesa enquanto a escuta está ligada.
 */
(() => {
  const $ = (id) => document.getElementById(id);
  const telas = ['telaCarregando', 'telaParear', 'telaTrancado', 'telaConversa'];
  const ROTULOS = { dormindo: 'DORMINDO', ouvindo: 'OUVINDO', pensando: 'PENSANDO', falando: 'FALANDO', senha: 'APROVAÇÃO' };

  let codigoConvite = '';
  let socket = null;
  let tentativas = 0;
  let bolhaAtual = null;
  let escutaLigada = false;
  let wakeLock = null;
  let somLiberado = false;
  let estado = 'dormindo';

  // ── Telas ───────────────────────────────────────────────────────────────

  function mostrar(id) { telas.forEach((tela) => { $(tela).hidden = tela !== id; }); }

  async function pedir(caminho, corpo) {
    const resposta = await fetch(caminho, corpo === undefined ? { cache: 'no-store', credentials: 'same-origin' } : {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo),
    });
    const json = await resposta.json().catch(() => ({}));
    return { ok: resposta.ok, status: resposta.status, json };
  }

  async function iniciar() {
    const hash = new URLSearchParams(location.hash.slice(1));
    codigoConvite = hash.get('c') || '';
    if (codigoConvite) history.replaceState(null, '', location.pathname);   // o código não fica no histórico

    let eu;
    try { eu = await pedir('/api/eu'); } catch (_) { return falhaRede(); }
    if (eu.status === 401) return telaParear();
    if (!eu.ok) return falhaRede();
    if (!eu.json.pronto && eu.json.motivo === 'trancado') return mostrar('telaTrancado');
    entrarNaConversa();
    if (!eu.json.pronto && eu.json.motivo) sistema(eu.json.motivo);
  }

  function falhaRede() {
    mostrar('telaCarregando');
    document.querySelector('#telaCarregando .aviso').textContent =
      'Não achei o PC. Ele está ligado e o Tailscale está ativo no iPhone?';
    setTimeout(iniciar, 5000);
  }

  function telaParear() {
    mostrar('telaParear');
    const semCodigo = !codigoConvite;
    $('formParear').hidden = semCodigo;
    $('parearSemCodigo').hidden = !semCodigo;
    $('parearAviso').hidden = semCodigo;
  }

  $('formParear').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    $('parearBotao').disabled = true; $('parearErro').textContent = '';
    try {
      const r = await pedir('/api/parear', { codigo: codigoConvite, senha: $('parearSenha').value, nome: $('parearNome').value });
      $('parearSenha').value = '';
      if (!r.ok) { $('parearErro').textContent = r.json.erro || 'não deu certo'; return; }
      codigoConvite = '';
      await iniciar();
    } finally { $('parearBotao').disabled = false; }
  });

  $('formDestrancar').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    $('destrancarBotao').disabled = true; $('destrancarErro').textContent = '';
    try {
      const r = await pedir('/api/destrancar', { senha: $('destrancarSenha').value });
      $('destrancarSenha').value = '';
      if (!r.ok) { $('destrancarErro').textContent = r.json.erro || 'não deu certo'; return; }
      if (socket) { socket.close(); socket = null; }
      await iniciar();
    } finally { $('destrancarBotao').disabled = false; }
  });

  // ── Conversa ────────────────────────────────────────────────────────────

  function entrarNaConversa() {
    mostrar('telaConversa');
    if (!somLiberado) $('toque').hidden = false;
    conectar();
  }

  function conectar() {
    if (socket && socket.readyState <= 1) return;
    socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
    socket.onopen = () => {
      tentativas = 0;
      if (somLiberado) enviar({ tipo: 'voz.player', ativo: true });
      enviar({ tipo: 'escuta', ativa: escutaLigada });
    };
    socket.onmessage = (evento) => { try { tratar(JSON.parse(evento.data)); } catch (_) { /* ignora */ } };
    socket.onclose = (evento) => {
      socket = null;
      if (evento.code === 1008) { iniciar(); return; }        // pareamento revogado ou expirado
      tentativas += 1;
      pintarEstado('dormindo', 'RECONECTANDO');
      // Pelo caminho completo: se o PC trancou ou reiniciou, cai na tela de destrancar.
      setTimeout(iniciar, Math.min(15000, 1000 * tentativas));
    };
  }

  function enviar(msg) {
    if (socket && socket.readyState === 1) { socket.send(JSON.stringify(msg)); return true; }
    return false;
  }

  function tratar(msg) {
    switch (msg.tipo) {
      case 'estado': pintarEstado(msg.estado); break;
      case 'conversa.historico': $('mensagens').innerHTML = ''; (msg.mensagens || []).forEach((m) => bolha(m.role === 'user' ? 'eu' : 'condor', m.content)); rolar(); break;
      case 'conversa.limpa': $('mensagens').innerHTML = ''; break;
      case 'transcricao':
        if (msg.digitado && msg.origem === 'celular') break;       // já apareceu quando você enviou
        bolha('eu', msg.texto, msg.origem === 'pc' ? 'NO PC' : '');
        break;
      case 'resposta.token':
        if (!bolhaAtual) bolhaAtual = bolha('condor', '');
        bolhaAtual.textContent += msg.texto || '';
        rolar();
        break;
      case 'resposta.fim':
        if (!bolhaAtual) bolhaAtual = bolha('condor', '');
        bolhaAtual.textContent = msg.texto || bolhaAtual.textContent;
        bolhaAtual = null; rolar();
        break;
      case 'ferramenta.inicio': pintarEstado('pensando', (msg.rotulo || 'TRABALHANDO').toUpperCase()); break;
      case 'erro': case 'ocupado': bolhaAtual = null; sistema(msg.mensagem || 'Algo deu errado.'); break;
      case 'senha.pedido': $('formSenha').hidden = false; $('senhaMotivo').textContent = msg.motivo || $('senhaMotivo').textContent; $('senhaTexto').focus(); break;
      case 'senha.fim': $('formSenha').hidden = true; break;
      case 'voz.audio': CondorAudio.receber(msg); break;
      case 'voz.parar': CondorAudio.parar(); break;
      case 'seguranca.bloqueado': if (socket) socket.close(); mostrar('telaTrancado'); break;
      case 'dormiu': pintarEstado('dormindo'); break;
      default: break;
    }
  }

  function bolha(quem, texto, etiqueta = '') {
    const div = document.createElement('div');
    div.className = `bolha ${quem}`;
    div.textContent = texto;
    if (etiqueta) div.dataset.etiqueta = etiqueta;
    $('mensagens').appendChild(div);
    rolar();
    return div;
  }

  function sistema(texto) { bolha('sistema', texto); }
  function rolar() { const lista = $('mensagens'); lista.scrollTop = lista.scrollHeight; }

  function pintarEstado(novo, rotulo) {
    estado = novo || estado;
    const visual = escutaLigada && estado === 'dormindo' ? 'ouvindo' : estado;
    $('orbe').dataset.estado = visual;
    $('estadoTexto').textContent = rotulo || (escutaLigada && estado === 'dormindo' ? 'DIGA "CONDOR"' : ROTULOS[estado] || estado.toUpperCase());
  }

  $('formCompor').addEventListener('submit', (evento) => {
    evento.preventDefault();
    const campo = $('texto');
    const texto = campo.value.trim();
    if (!texto) return;
    if (!enviar({ tipo: 'texto', texto })) { sistema('Sem conexão com o PC agora.'); return; }
    bolha('eu', texto);
    campo.value = ''; ajustarCampo();
  });
  $('texto').addEventListener('keydown', (evento) => {
    if (evento.key === 'Enter' && !evento.shiftKey) { evento.preventDefault(); $('formCompor').requestSubmit(); }
  });
  function ajustarCampo() { const campo = $('texto'); campo.style.height = 'auto'; campo.style.height = `${Math.min(120, campo.scrollHeight)}px`; }
  $('texto').addEventListener('input', ajustarCampo);

  $('formSenha').addEventListener('submit', (evento) => {
    evento.preventDefault();
    const texto = $('senhaTexto').value;
    if (texto) enviar({ tipo: 'senha', texto });
    $('senhaTexto').value = '';
    $('formSenha').hidden = true;
  });

  // ── Som e microfone ────────────────────────────────────────────────────

  $('toque').addEventListener('click', async () => {
    try { await CondorAudio.ligar(); somLiberado = true; enviar({ tipo: 'voz.player', ativo: true }); } catch (_) { /* tenta no próximo toque */ }
    $('toque').hidden = true;
    // Abriu o app, um toque e já está ouvindo "Condor", se a escuta estava ligada da última vez.
    if (!escutaLigada && lembrarEscuta()) await ligarEscuta();
  });

  function lembrarEscuta(valor) {
    try {
      if (valor === undefined) return localStorage.getItem('condor.escuta') === '1';
      localStorage.setItem('condor.escuta', valor ? '1' : '0');
    } catch (_) { /* navegação privada: só não lembra */ }
    return false;
  }

  CondorAudio.ouvinte = (wav, meta) => {
    if (!enviar({ tipo: 'audio', wav, com_nome: meta.comNome })) sistema('Sem conexão com o PC agora.');
    else if (!meta.comNome) pintarEstado('pensando');
  };
  CondorAudio.aoMudarNivel = (nivel, falando) => {
    $('micBotao').style.setProperty('--nivel', String(nivel));
    $('micBotao').classList.toggle('falando', falando);
  };
  CondorAudio.aoFimFrase = async (eraFrase) => {
    if (!eraFrase) return;
    $('micBotao').setAttribute('aria-pressed', 'false');
    if (escutaLigada) await CondorAudio.ligarEscuta(); else CondorAudio.cancelarFrase(false);
  };

  $('micBotao').addEventListener('click', async () => {
    if (CondorAudio.modo === 'frase') {           // tocou de novo: manda o que já falou
      $('micBotao').setAttribute('aria-pressed', 'false');
      CondorAudio.cancelarFrase(escutaLigada);
      if (escutaLigada) await CondorAudio.ligarEscuta();
      return;
    }
    try {
      await CondorAudio.ligar(); somLiberado = true; enviar({ tipo: 'voz.player', ativo: true });
      if (CondorAudio.estaTocando()) enviar({ tipo: 'voz.parar' });   // falou por cima: ele cala
      await CondorAudio.ouvirFrase();
      $('micBotao').setAttribute('aria-pressed', 'true');
      pintarEstado(estado, 'FALE AGORA');
    } catch (erro) {
      sistema(`Microfone indisponível: ${erro.message || erro}. Libere o microfone para este site nos Ajustes.`);
    }
  });

  $('escutaBotao').addEventListener('click', async () => {
    if (escutaLigada) { desligarEscuta(); lembrarEscuta(false); return; }
    await ligarEscuta();
  });

  async function ligarEscuta() {
    try {
      await CondorAudio.ligar(); somLiberado = true; enviar({ tipo: 'voz.player', ativo: true });
      await CondorAudio.ligarEscuta();
      escutaLigada = true;
      lembrarEscuta(true);
      enviar({ tipo: 'escuta', ativa: true });
      $('escutaBotao').setAttribute('aria-pressed', 'true');
      await manterTelaAcesa();
      pintarEstado(estado);
    } catch (erro) {
      sistema(`Microfone indisponível: ${erro.message || erro}.`);
    }
  }

  function desligarEscuta() {
    escutaLigada = false;
    enviar({ tipo: 'escuta', ativa: false });
    CondorAudio.desligarEscuta();
    $('escutaBotao').setAttribute('aria-pressed', 'false');
    soltarTela();
    pintarEstado(estado);
  }

  async function manterTelaAcesa() {
    try { if ('wakeLock' in navigator) wakeLock = await navigator.wakeLock.request('screen'); } catch (_) { wakeLock = null; }
  }
  function soltarTela() { try { wakeLock?.release(); } catch (_) { /* ok */ } wakeLock = null; }

  document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState === 'visible') {
      conectar();
      // Voltando do segundo plano o iOS pode ter pausado o som: só um toque religa.
      if (somLiberado && !CondorAudio.ativo()) $('toque').hidden = false;
      if (escutaLigada) { await manterTelaAcesa(); try { await CondorAudio.ligarEscuta(); } catch (_) { desligarEscuta(); } }
    }
  });

  setInterval(() => enviar({ tipo: 'ping' }), 25000);
  iniciar();
})();
