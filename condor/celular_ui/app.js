/**
 * CONDOR no iPhone: a mesma conversa do PC, com tudo que o chat do PC tem.
 *
 * - Mensagem, foto (a visão local analisa no PC) e microfone.
 * - Escuta: diga "Condor, na escuta" e converse; depois de 2 minutos sem falar
 *   com ele, precisa chamar de novo. Quem decide é o PC (mesma regra lá).
 * - Menu: nova conversa, conversas anteriores, galeria, memória (mapa igual
 *   ao do PC) e treino.
 * - Segure (ou toque) numa mensagem: copiar, apagar, 👍/👎 e melhorar a resposta.
 */
(() => {
  const $ = (id) => document.getElementById(id);
  const telas = ['telaCarregando', 'telaParear', 'telaTrancado', 'telaConversa'];
  const vistas = { vistaChat: 'CONDOR', vistaAnteriores: 'ANTERIORES', vistaGaleria: 'GALERIA', vistaMemoria: 'MEMÓRIA', vistaTreino: 'TREINO' };
  const ROTULOS = { dormindo: 'DORMINDO', ouvindo: 'OUVINDO', pensando: 'PENSANDO', falando: 'FALANDO', senha: 'APROVAÇÃO' };

  let codigoConvite = '';
  let socket = null;
  let tentativas = 0;
  let bolhaAtual = null;
  let escutaLigada = false;
  let wakeLock = null;
  let somLiberado = false;
  let estado = 'dormindo';
  let acordado = false;          // conversa aberta no PC (até 2 min sem falar)
  let fotoAnexada = '';          // JPEG base64 pronto para ir junto
  let mensagemDaFolha = null;
  let confirmarAcao = null;

  // ── Utilidades ──────────────────────────────────────────────────────────

  function mostrar(id) { telas.forEach((tela) => { $(tela).hidden = tela !== id; }); }

  async function pedir(caminho, corpo) {
    const resposta = await fetch(caminho, corpo === undefined ? { cache: 'no-store', credentials: 'same-origin' } : {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo),
    });
    const json = await resposta.json().catch(() => ({}));
    return { ok: resposta.ok, status: resposta.status, json };
  }

  function avisar(texto) {
    const caixa = $('avisoFlutuante');
    caixa.textContent = texto;
    caixa.hidden = false;
    clearTimeout(avisar.relogio);
    avisar.relogio = setTimeout(() => { caixa.hidden = true; }, 2200);
  }

  function confirmar(texto, acao) {
    $('confirmaTexto').textContent = texto;
    confirmarAcao = acao;
    $('confirma').hidden = false;
  }
  $('confirmaSim').addEventListener('click', async () => { $('confirma').hidden = true; const a = confirmarAcao; confirmarAcao = null; if (a) await a(); });
  $('confirmaNao').addEventListener('click', () => { $('confirma').hidden = true; confirmarAcao = null; });

  // ── Entrada, pareamento e destrancar ───────────────────────────────────

  async function iniciar() {
    const hash = new URLSearchParams(location.hash.slice(1));
    if (hash.get('c')) { codigoConvite = hash.get('c'); history.replaceState(null, '', location.pathname); }

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

  // ── Conexão ao vivo ─────────────────────────────────────────────────────

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
      if (evento.code !== 1000) setTimeout(() => diag(`conexão caiu (${evento.code})`), 1500);
      if (evento.code === 1008) { iniciar(); return; }
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
      case 'estado':
        if (typeof msg.acordado === 'boolean') acordado = msg.acordado;
        pintarEstado(msg.estado);
        break;
      case 'acordou': acordado = true; pintarEstado(estado); break;
      case 'dormiu': acordado = false; pintarEstado('dormindo'); break;
      case 'conversa.historico': desenharHistorico(msg.mensagens || []); break;
      case 'conversa.limpa': $('mensagens').innerHTML = ''; bolhaAtual = null; sistema('Nova conversa.'); break;
      case 'mensagem.apagada': tirarMensagem(msg); break;
      case 'transcricao':
        if (msg.digitado && msg.origem === 'celular') break;       // já apareceu quando você enviou
        bolha('eu', msg.texto, { etiqueta: msg.origem === 'pc' ? 'NO PC' : '' });
        break;
      case 'resposta.token':
        if (!bolhaAtual) bolhaAtual = bolha('condor', '', { aoVivo: true });
        bolhaAtual.dataset.bruto = (bolhaAtual.dataset.bruto || '') + (msg.texto || '');
        pintarTexto(bolhaAtual);
        rolar();
        break;
      case 'resposta.fim':
        if (!bolhaAtual) bolhaAtual = bolha('condor', '', { aoVivo: true });
        bolhaAtual.dataset.bruto = msg.texto || bolhaAtual.dataset.bruto || '';
        if (msg.treino_id) bolhaAtual.dataset.treino = msg.treino_id;
        pintarTexto(bolhaAtual);
        mostrarFontes(bolhaAtual, msg.fontes);
        bolhaAtual = null; rolar();
        break;
      case 'imagem.nova': bolhaImagem(msg.id, msg.pedido); break;
      case 'ferramenta.inicio': pintarEstado('pensando', (msg.rotulo || 'TRABALHANDO').toUpperCase()); break;
      case 'erro': case 'ocupado': bolhaAtual = null; sistema(msg.mensagem || 'Algo deu errado.'); break;
      case 'senha.pedido': $('formSenha').hidden = false; $('senhaMotivo').textContent = msg.motivo || $('senhaMotivo').textContent; $('senhaTexto').focus(); break;
      case 'senha.fim': $('formSenha').hidden = true; break;
      case 'voz.audio': CondorAudio.receber(msg); break;
      case 'voz.parar': CondorAudio.parar(); break;
      case 'seguranca.bloqueado': if (socket) socket.close(); mostrar('telaTrancado'); break;
      default: break;
    }
  }

  // ── Mensagens ───────────────────────────────────────────────────────────

  function desenharHistorico(mensagens) {
    // Reconectou no meio de uma resposta: não perde a bolha que ainda chega.
    const emAndamento = bolhaAtual;
    $('mensagens').innerHTML = '';
    mensagens.forEach((m) => bolha(m.role === 'user' ? 'eu' : 'condor', m.content, { id: m.id }));
    if (emAndamento) $('mensagens').appendChild(emAndamento);
    rolar();
  }

  function bolha(quem, texto, opcoes = {}) {
    const div = document.createElement('div');
    div.className = `bolha ${quem}`;
    div.dataset.quem = quem;
    if (opcoes.id) div.dataset.id = opcoes.id;
    if (opcoes.etiqueta) div.dataset.etiqueta = opcoes.etiqueta;
    div.dataset.bruto = texto || '';
    if (opcoes.foto) {
      const img = document.createElement('img');
      img.className = 'miniatura'; img.src = opcoes.foto; img.alt = 'Foto enviada';
      div.appendChild(img);
    }
    const corpo = document.createElement('div');
    corpo.className = 'corpo';
    div.appendChild(corpo);
    pintarTexto(div);
    if (quem !== 'sistema') ligarAcoes(div);
    $('mensagens').appendChild(div);
    rolar();
    return div;
  }

  function pintarTexto(div) {
    const corpo = div.querySelector('.corpo');
    if (!corpo) return;
    // Mensagem do dono fica como ele escreveu; a do Condor ganha formatação.
    if (div.dataset.quem === 'condor') corpo.innerHTML = CondorTexto.html(div.dataset.bruto);
    else corpo.textContent = div.dataset.bruto;
  }

  function mostrarFontes(div, fontes) {
    if (!Array.isArray(fontes) || !fontes.length) return;
    const host = document.createElement('div');
    host.className = 'fontes';
    fontes.slice(0, 8).forEach((fonte, i) => {
      try {
        const url = new URL(String(fonte.url || ''));
        if (!['http:', 'https:'].includes(url.protocol)) return;
        const link = document.createElement('a');
        link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
        link.textContent = `${i + 1}. ${fonte.titulo || fonte.title || url.hostname}`;
        host.appendChild(link);
      } catch (_) { /* fonte inválida */ }
    });
    if (host.childElementCount) div.appendChild(host);
  }

  function bolhaImagem(id, pedido) {
    if (!/^img_[0-9a-f]{20}$/.test(String(id || ''))) return;
    const div = document.createElement('div');
    div.className = 'bolha condor imagem';
    div.dataset.quem = 'imagem';
    const img = document.createElement('img');
    img.src = `/api/imagens/${id}`; img.alt = pedido || 'Imagem criada pelo Condor'; img.loading = 'lazy';
    img.addEventListener('click', () => abrirVisor(img.src, pedido));
    div.appendChild(img);
    if (pedido) { const legenda = document.createElement('small'); legenda.textContent = pedido; div.appendChild(legenda); }
    $('mensagens').appendChild(div);
    rolar();
  }

  function sistema(texto) { bolha('sistema', texto); }
  function rolar() { const lista = $('mensagens'); lista.scrollTop = lista.scrollHeight; }

  function tirarMensagem(msg) {
    const porId = msg.id && $('mensagens').querySelector(`.bolha[data-id="${Number(msg.id)}"]`);
    if (porId) { porId.remove(); return; }
    const quem = msg.role === 'user' ? 'eu' : 'condor';
    const alvo = String(msg.content || '').trim();
    const achada = [...$('mensagens').querySelectorAll(`.bolha.${quem}`)].reverse()
      .find((b) => (b.dataset.bruto || '').trim() === alvo);
    if (achada) achada.remove();
  }

  // ── Ações de uma mensagem ───────────────────────────────────────────────

  function ligarAcoes(div) {
    let relogio = null;
    div.addEventListener('touchstart', () => { relogio = setTimeout(() => abrirFolha(div), 450); }, { passive: true });
    ['touchend', 'touchmove', 'touchcancel'].forEach((nome) => div.addEventListener(nome, () => clearTimeout(relogio), { passive: true }));
    div.addEventListener('contextmenu', (evento) => { evento.preventDefault(); abrirFolha(div); });
    div.addEventListener('dblclick', () => abrirFolha(div));
  }

  function abrirFolha(div) {
    mensagemDaFolha = div;
    const folha = $('folha');
    const condor = div.dataset.quem === 'condor';
    folha.querySelector('[data-acao="gostei"]').hidden = !(condor && div.dataset.treino);
    folha.querySelector('[data-acao="naogostei"]').hidden = !(condor && div.dataset.treino);
    folha.querySelector('[data-acao="melhorar"]').hidden = !(condor && div.dataset.treino);
    folha.hidden = false;
    if (navigator.vibrate) navigator.vibrate(12);
  }

  $('folha').addEventListener('click', async (evento) => {
    const botao = evento.target.closest('[data-acao]');
    if (!botao && evento.target !== $('folha')) return;
    const acao = botao ? botao.dataset.acao : 'fechar';
    const div = mensagemDaFolha;
    $('folha').hidden = true;
    if (!div || acao === 'fechar') return;
    if (acao === 'copiar') {
      try { await navigator.clipboard.writeText(div.dataset.bruto || ''); avisar('Copiado'); } catch (_) { avisar('Não deu para copiar'); }
    } else if (acao === 'gostei') {
      const r = await pedir('/api/avaliar', { id: div.dataset.treino, nota: 1 });
      avisar(r.ok ? 'Obrigado, anotei para o treino' : 'Não salvei a avaliação');
    } else if (acao === 'naogostei' || acao === 'melhorar') {
      // Não gostou: já abre para escrever como deveria ser. Sem correção vale só o 👎.
      abrirCorrecao({ id: div.dataset.treino, pedido: pedidoAntes(div), resposta: div.dataset.bruto || '', soNota: acao === 'naogostei' });
    } else if (acao === 'apagar') {
      confirmar('Apagar esta mensagem? Ela some do PC e do celular e ele esquece essa troca.', () => apagar(div));
    }
  });

  function pedidoAntes(div) {
    let anterior = div.previousElementSibling;
    while (anterior && anterior.dataset.quem !== 'eu') anterior = anterior.previousElementSibling;
    return anterior ? anterior.dataset.bruto || '' : '';
  }

  // ── Corrigir uma resposta (vira exemplo de treino) ──────────────────────

  let correcaoAtual = null;
  function abrirCorrecao(item) {
    correcaoAtual = item;
    $('corrigirPedido').textContent = item.pedido ? `Você: ${item.pedido.slice(0, 300)}` : '';
    $('corrigirPedido').hidden = !item.pedido;
    $('corrigirTexto').value = item.correcao || item.resposta || '';
    $('corrigir').hidden = false;
    $('corrigirTexto').focus();
  }
  $('corrigirCancelar').addEventListener('click', async () => {
    const item = correcaoAtual;
    $('corrigir').hidden = true; correcaoAtual = null;
    if (item && item.soNota) {
      const r = await pedir('/api/avaliar', { id: item.id, nota: -1 });
      avisar(r.ok ? 'Anotei que não ficou bom' : 'Não salvei a avaliação');
      if (item.aoSalvar) item.aoSalvar();
    }
  });
  $('formCorrigir').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const item = correcaoAtual;
    if (!item) return;
    const texto = $('corrigirTexto').value.trim();
    // Texto igual à resposta dele não é correção: fica só o 👎.
    const correcao = texto && texto !== String(item.resposta || '').trim() ? texto : '';
    const r = await pedir('/api/avaliar', { id: item.id, nota: -1, correcao });
    if (!r.ok) { avisar(r.json.erro ? `Não salvei: ${r.json.erro}` : 'Não salvei a correção'); return; }
    $('corrigir').hidden = true; correcaoAtual = null;
    avisar(correcao ? 'Correção salva. Ele aprende com isso' : 'Anotei que não ficou bom');
    if (item.aoSalvar) item.aoSalvar();
  });

  async function apagar(div) {
    let id = Number(div.dataset.id || 0);
    if (!id) {
      // Mensagem desta sessão ainda sem número: procura no histórico do PC.
      const r = await pedir('/api/historico');
      const papel = div.dataset.quem === 'eu' ? 'user' : 'assistant';
      const alvo = (div.dataset.bruto || '').trim();
      const achada = (r.json.mensagens || []).slice().reverse()
        .find((m) => m.role === papel && String(m.content || '').trim().startsWith(alvo.slice(0, 200)));
      id = achada ? Number(achada.id) : 0;
    }
    if (!id) { div.remove(); avisar('Removida da tela'); return; }
    const r = await pedir('/api/mensagem/apagar', { id });
    if (r.ok) { div.remove(); avisar('Mensagem apagada'); } else avisar('Não consegui apagar');
  }

  // ── Escrever, foto e senha ──────────────────────────────────────────────

  $('formCompor').addEventListener('submit', (evento) => {
    evento.preventDefault();
    const campo = $('texto');
    const texto = campo.value.trim();
    if (!texto && !fotoAnexada) return;
    const msg = { tipo: 'texto', texto };
    if (fotoAnexada) msg.foto = fotoAnexada;
    if (!enviar(msg)) { sistema('Sem conexão com o PC agora.'); return; }
    bolha('eu', texto || (fotoAnexada ? 'O que você acha desta foto?' : ''),
      { foto: fotoAnexada ? `data:image/jpeg;base64,${fotoAnexada}` : '' });
    campo.value = ''; ajustarCampo(); tirarFoto();
  });
  $('texto').addEventListener('keydown', (evento) => {
    if (evento.key === 'Enter' && !evento.shiftKey) { evento.preventDefault(); $('formCompor').requestSubmit(); }
  });
  function ajustarCampo() { const campo = $('texto'); campo.style.height = 'auto'; campo.style.height = `${Math.min(120, campo.scrollHeight)}px`; }
  $('texto').addEventListener('input', ajustarCampo);

  $('fotoBotao').addEventListener('click', () => $('fotoArquivo').click());
  $('fotoArquivo').addEventListener('change', async () => {
    const arquivo = $('fotoArquivo').files[0];
    $('fotoArquivo').value = '';
    if (!arquivo) return;
    try {
      fotoAnexada = await reduzirFoto(arquivo);
      $('anexoFoto').src = `data:image/jpeg;base64,${fotoAnexada}`;
      $('anexo').hidden = false;
      $('texto').focus();
    } catch (_) { avisar('Não consegui abrir essa foto'); }
  });
  $('anexoTirar').addEventListener('click', tirarFoto);
  function tirarFoto() { fotoAnexada = ''; $('anexo').hidden = true; $('anexoFoto').removeAttribute('src'); }

  // Foto do iPhone tem 12 MP: reduz para 1280 px em JPEG antes de mandar.
  function reduzirFoto(arquivo) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(arquivo);
      const img = new Image();
      img.onload = () => {
        const escala = Math.min(1, 1280 / Math.max(img.width, img.height));
        const tela = document.createElement('canvas');
        tela.width = Math.round(img.width * escala); tela.height = Math.round(img.height * escala);
        tela.getContext('2d').drawImage(img, 0, 0, tela.width, tela.height);
        URL.revokeObjectURL(url);
        resolve(tela.toDataURL('image/jpeg', 0.82).split(',')[1]);
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('foto')); };
      img.src = url;
    });
  }

  $('formSenha').addEventListener('submit', (evento) => {
    evento.preventDefault();
    const texto = $('senhaTexto').value;
    if (texto) enviar({ tipo: 'senha', texto });
    $('senhaTexto').value = '';
    $('formSenha').hidden = true;
  });

  // ── Estado e escuta ─────────────────────────────────────────────────────

  function pintarEstado(novo, rotulo) {
    estado = novo || estado;
    const livre = escutaLigada && acordado && !CondorAudio.estaTocando() && estado !== 'pensando';
    const visual = escutaLigada && (estado === 'dormindo' || livre) ? 'ouvindo' : estado;
    $('orbe').dataset.estado = visual;
    let padrao = ROTULOS[estado] || String(estado).toUpperCase();
    if (livre) padrao = 'PODE FALAR';
    else if (escutaLigada && !acordado && estado === 'dormindo') padrao = 'DIGA "CONDOR, NA ESCUTA"';
    $('estadoTexto').textContent = rotulo || padrao;
  }

  $('toque').addEventListener('click', async () => {
    try { await CondorAudio.ligar(); somLiberado = true; enviar({ tipo: 'voz.player', ativo: true }); } catch (_) { /* tenta no próximo toque */ }
    $('toque').hidden = true;
    CondorAudio.retomar();                 // voz que o iOS segurou continua de onde parou
    // Abriu o app, um toque e já está ouvindo, se a escuta estava ligada da última vez.
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
    // Escuta contínua manda tudo com com_nome: o PC decide se a conversa está
    // aberta ou se precisa de "Condor, na escuta". Pelo botão vai direto.
    if (!enviar({ tipo: 'audio', wav, com_nome: meta.comNome })) sistema('Sem conexão com o PC agora.');
    else if (!meta.comNome) pintarEstado('pensando');
  };
  CondorAudio.aoFimFala = () => pintarEstado(estado);
  CondorAudio.aoPrecisarToque = () => { $('toque').hidden = false; };
  CondorAudio.aoErro = (texto) => diag(texto);
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

  // ── Menu e outras telas ─────────────────────────────────────────────────

  function abrirMenu(aberto) { $('gaveta').hidden = !aberto; $('veu').hidden = !aberto; }
  $('menuBotao').addEventListener('click', () => abrirMenu(true));
  $('veu').addEventListener('click', () => abrirMenu(false));
  $('menuFechar').addEventListener('click', () => abrirMenu(false));
  $('gaveta').addEventListener('click', (evento) => {
    const botao = evento.target.closest('[data-vista]');
    if (botao) { abrirMenu(false); irPara(botao.dataset.vista); }
  });
  $('menuNova').addEventListener('click', () => {
    abrirMenu(false);
    confirmar('Começar uma conversa nova? A atual fica guardada em "Conversas anteriores" e ele não esquece nada do que sabe de você.', async () => {
      const r = await pedir('/api/conversa/nova', {});
      if (r.ok) irPara('vistaChat'); else avisar('Não consegui começar outra conversa');
    });
  });

  function irPara(vista) {
    Object.keys(vistas).forEach((id) => { $(id).hidden = id !== vista; });
    $('tituloVista').textContent = vistas[vista];
    if (vista === 'vistaAnteriores') carregarAnteriores(true);
    if (vista === 'vistaGaleria') carregarGaleria(true);
    if (vista === 'vistaMemoria') carregarMemoria();
    if (vista === 'vistaTreino') carregarTreino();
    if (vista === 'vistaChat') rolar();
  }

  let anterioresProximo = null;
  async function carregarAnteriores(doZero) {
    if (doZero) { $('anterioresLista').innerHTML = ''; anterioresProximo = null; }
    const r = await pedir(`/api/anteriores${anterioresProximo ? `?antes=${anterioresProximo}` : ''}`);
    if (!r.ok) { $('anterioresLista').textContent = r.json.erro || 'Indisponível agora.'; return; }
    let diaAnterior = $('anterioresLista').dataset.ultimoDia || '';
    (r.json.itens || []).forEach((item) => {
      const dia = new Date(item.ts * 1000).toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: 'short' });
      if (dia !== diaAnterior) {
        const titulo = document.createElement('h3'); titulo.textContent = dia; $('anterioresLista').appendChild(titulo);
        diaAnterior = dia;
      }
      const linha = document.createElement('div');
      linha.className = `antiga ${item.papel === 'user' ? 'eu' : 'condor'}`;
      const quem = document.createElement('b'); quem.textContent = item.papel === 'user' ? 'Você' : 'Condor';
      const texto = document.createElement('span'); texto.textContent = String(item.conteudo || '').slice(0, 600);
      linha.append(quem, texto);
      $('anterioresLista').appendChild(linha);
    });
    $('anterioresLista').dataset.ultimoDia = diaAnterior;
    anterioresProximo = r.json.proximo;
    $('anterioresMais').hidden = !anterioresProximo;
    if (!$('anterioresLista').childElementCount) $('anterioresLista').textContent = 'Nenhuma conversa guardada ainda.';
  }
  $('anterioresMais').addEventListener('click', () => carregarAnteriores(false));

  let galeriaProximo = null;
  async function carregarGaleria(doZero) {
    if (doZero) { $('galeriaGrade').innerHTML = ''; galeriaProximo = null; }
    const r = await pedir(`/api/imagens${galeriaProximo ? `?antes=${galeriaProximo}` : ''}`);
    if (!r.ok) { $('galeriaGrade').textContent = r.json.erro || 'Indisponível agora.'; return; }
    (r.json.itens || []).forEach((item) => {
      if (!/^img_[0-9a-f]{20}$/.test(String(item.id || ''))) return;
      const img = document.createElement('img');
      img.src = `/api/imagens/${item.id}`; img.loading = 'lazy'; img.alt = item.pedido || 'Imagem';
      img.addEventListener('click', () => abrirVisor(img.src, item.pedido));
      $('galeriaGrade').appendChild(img);
    });
    galeriaProximo = r.json.proximo;
    $('galeriaMais').hidden = !galeriaProximo;
    if (!$('galeriaGrade').childElementCount) $('galeriaGrade').textContent = 'Nenhuma imagem ainda. Peça: "Condor, gera uma imagem de...".';
  }
  $('galeriaMais').addEventListener('click', () => carregarGaleria(false));

  async function carregarMemoria() {
    const r = await pedir('/api/memoria/mapa');
    if (!r.ok) { $('memoriaMapa').textContent = r.json.erro || 'Indisponível agora.'; return; }
    CondorMemoriaCel.carregar(r.json);
    desenharMemoria();
  }
  function desenharMemoria() {
    const busca = $('memoriaBusca').value.trim().toLowerCase();
    const lista = $('memoriaLista');
    lista.innerHTML = '';
    const visiveis = CondorMemoriaCel.fatos()
      .filter((f) => !busca || `${f.categoria} ${f.chave} ${f.valor}`.toLowerCase().includes(busca))
      .sort((x, y) => String(x.categoria).localeCompare(String(y.categoria)));
    let categoria = '';
    visiveis.forEach((fato) => {
      if (fato.categoria !== categoria) {
        categoria = fato.categoria;
        const titulo = document.createElement('h3'); titulo.textContent = CondorMemoriaCel.nome(categoria);
        lista.appendChild(titulo);
      }
      const linha = document.createElement('div'); linha.className = 'fato';
      const texto = document.createElement('span'); texto.textContent = fato.valor;
      const botao = document.createElement('button'); botao.type = 'button'; botao.textContent = 'Esquecer';
      botao.addEventListener('click', () => esquecerFato(fato));
      linha.append(texto, botao);
      lista.appendChild(linha);
    });
    if (!visiveis.length) lista.textContent = busca ? 'Nada com isso.' : 'Ele ainda não guardou nada sobre você.';
  }
  function esquecerFato(fato) {
    confirmar(`Esquecer isto?\n"${fato.valor}"`, async () => {
      const resposta = await pedir('/api/memoria/esquecer', { id: fato.id });
      if (resposta.ok && resposta.json.ok) { CondorMemoriaCel.esquecido(fato.id); desenharMemoria(); avisar('Esquecido'); }
      else avisar('Não consegui esquecer');
    });
  }

  let fatoAberto = null;
  CondorMemoriaCel.init({
    aoMostrarLista: desenharMemoria,
    aoAbrirFato(fato, ligacoes) {
      fatoAberto = fato;
      $('fatoTitulo').textContent = fato.valor;
      $('fatoMeta').innerHTML = '';
      [[CondorMemoriaCel.nome(fato.categoria), 'ÁREA'], [String(fato.chave || '').replaceAll('_', ' '), 'CHAVE'],
        [fato.origem || '—', 'ORIGEM'], [fato.acessos || 0, 'USOS']].forEach(([valor, rotulo]) => {
        const caixa = document.createElement('div');
        const s = document.createElement('span'); s.textContent = rotulo;
        const b = document.createElement('b'); b.textContent = valor;
        caixa.append(s, b); $('fatoMeta').appendChild(caixa);
      });
      const lista = $('fatoLigacoes');
      lista.innerHTML = '';
      ligacoes.slice(0, 8).forEach(({ ligacao, fato: outro }) => {
        const linha = document.createElement('div'); linha.className = 'fluxo';
        const r = document.createElement('b'); r.textContent = String(ligacao.rotulo || 'LIGADO').toUpperCase();
        const v = document.createElement('span'); v.textContent = outro.valor;
        linha.append(r, v); lista.appendChild(linha);
      });
      if (!ligacoes.length) lista.textContent = 'Sem ligações com outras memórias ainda.';
      $('fatoFolha').hidden = false;
    },
  });
  $('fatoFechar').addEventListener('click', () => { $('fatoFolha').hidden = true; fatoAberto = null; });
  $('fatoEsquecer').addEventListener('click', () => {
    const fato = fatoAberto;
    $('fatoFolha').hidden = true; fatoAberto = null;
    if (fato) esquecerFato(fato);
  });

  // ── Treino: avaliar e corrigir pelo celular ─────────────────────────────

  let treinoPendentes = true;
  async function carregarTreino() {
    const r = await pedir(`/api/treino?pendentes=${treinoPendentes ? 1 : 0}`);
    const lista = $('treinoLista');
    if (!r.ok) { lista.textContent = r.json.erro || 'Indisponível agora.'; return; }
    const resumo = r.json.resumo || {};
    $('treinoNumeros').innerHTML = '';
    [[resumo.total || 0, 'EXEMPLOS'], [resumo.positivos || 0, 'BONS'], [resumo.negativos || 0, 'RUINS'],
      [resumo.corrigidos || 0, 'CORRIGIDOS'], [resumo.prontos || 0, 'PRONTOS']].forEach(([valor, rotulo]) => {
      const caixa = document.createElement('div');
      const b = document.createElement('b'); b.textContent = valor;
      const s = document.createElement('span'); s.textContent = rotulo;
      caixa.append(b, s); $('treinoNumeros').appendChild(caixa);
    });
    lista.innerHTML = '';
    (r.json.exemplos || []).forEach((ex) => lista.appendChild(cartaoTreino(ex)));
    if (!lista.childElementCount) {
      lista.textContent = treinoPendentes ? 'Tudo avaliado. Converse mais com ele e volte aqui.' : 'Nenhuma resposta guardada para treino ainda.';
    }
  }

  function cartaoTreino(ex) {
    const cartao = document.createElement('div');
    cartao.className = `treino${ex.nota > 0 ? ' bom' : ex.nota < 0 ? ' ruim' : ''}`;
    const pedido = document.createElement('p'); pedido.className = 'treino-pedido';
    const voce = document.createElement('b'); voce.textContent = 'Você';
    pedido.append(voce, document.createTextNode(String(ex.pedido || '').slice(0, 400)));
    const resposta = document.createElement('div'); resposta.className = 'treino-resposta corpo';
    resposta.innerHTML = CondorTexto.html(String(ex.resposta || '').slice(0, 1500));
    cartao.append(pedido, resposta);
    if (ex.correcao) {
      const correcao = document.createElement('div'); correcao.className = 'treino-correcao';
      const rotulo = document.createElement('b'); rotulo.textContent = 'Como deveria ser';
      const texto = document.createElement('span'); texto.textContent = ex.correcao;
      correcao.append(rotulo, texto); cartao.appendChild(correcao);
    }
    const acoes = document.createElement('div'); acoes.className = 'treino-acoes';
    const botao = (rotulo, classe, acao) => {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = rotulo;
      if (classe) b.className = classe;
      b.addEventListener('click', acao); acoes.appendChild(b);
    };
    botao('👍 Boa', ex.nota > 0 ? 'ativa' : '', async () => {
      const r = await pedir('/api/avaliar', { id: ex.id, nota: 1 });
      if (r.ok) { avisar('Anotado como boa'); carregarTreino(); } else avisar('Não salvei');
    });
    botao('👎 Ruim', ex.nota < 0 && !ex.correcao ? 'ativa' : '', () => abrirCorrecao({ id: ex.id, pedido: ex.pedido, resposta: ex.resposta, soNota: true, aoSalvar: carregarTreino }));
    botao('✏️ Corrigir', ex.correcao ? 'ativa' : '', () => abrirCorrecao({ id: ex.id, pedido: ex.pedido, resposta: ex.resposta, correcao: ex.correcao, aoSalvar: carregarTreino }));
    cartao.appendChild(acoes);
    return cartao;
  }

  document.querySelectorAll('[data-treino-filtro]').forEach((b) => b.addEventListener('click', () => {
    treinoPendentes = b.dataset.treinoFiltro === '1';
    document.querySelectorAll('[data-treino-filtro]').forEach((x) => x.classList.toggle('ativa', x === b));
    carregarTreino();
  }));
  $('memoriaBusca').addEventListener('input', desenharMemoria);

  // ── Imagem em tela cheia ────────────────────────────────────────────────

  function abrirVisor(src, legenda) {
    $('visorImg').src = src;
    $('visorImg').classList.remove('zoom');
    $('visorLegenda').textContent = legenda || '';
    $('visor').hidden = false;
  }
  $('visorFechar').addEventListener('click', () => { $('visor').hidden = true; });
  // Toque duplo aproxima; dois dedos também funcionam (zoom do próprio iPhone).
  $('visorImg').addEventListener('dblclick', () => $('visorImg').classList.toggle('zoom'));

  // ── Diagnóstico e manutenção ────────────────────────────────────────────

  // Erro no celular vai para o log do PC: dá para descobrir o motivo depois.
  const diagsEnviados = new Set();
  function diag(texto) {
    const linha = String(texto || '').slice(0, 280);
    if (!linha || diagsEnviados.has(linha) || diagsEnviados.size > 40) return;
    diagsEnviados.add(linha);
    enviar({ tipo: 'diag', texto: linha });
  }
  window.addEventListener('error', (evento) => diag(`erro: ${evento.message} @${evento.lineno}`));
  window.addEventListener('unhandledrejection', (evento) => diag(`promessa: ${evento.reason && (evento.reason.message || evento.reason)}`));

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
