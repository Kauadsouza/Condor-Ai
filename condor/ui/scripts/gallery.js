/**
 * CondorGaleria — tudo que o Condor já criou, guardado cifrado no PC.
 *
 * Cada imagem guarda o pedido original, o prompt final e a seed: dá para
 * refazer a mesma imagem ou pedir uma variação. As imagens criadas pelo
 * cérebro (por voz ou quando ele decide) também aparecem no chat na hora.
 */
const CondorGaleria = (() => {
  const $ = (id) => document.getElementById(id);
  let itens = [];
  let selecionada = null;
  let carregando = false;
  const mostradasNoChat = new Set();

  const escapar = (valor) => String(valor ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
  const url = (id) => `/api/media/images/${encodeURIComponent(id)}`;

  function init() {
    $('galleryRefresh')?.addEventListener('click', atualizar);
    CondorWS.ao('core.event', (mensagem) => {
      const evento = mensagem.event || {};
      if (evento.type !== 'IMAGE_GENERATED') return;
      const imagem = evento.payload?.image;
      if (!imagem) return;
      // Pedido feito direto no chat já aparece pela própria resposta HTTP.
      if (imagem.origem === 'cerebro') mostrarNoChat(imagem);
      if (CondorRouter.atual() === 'galeria') atualizar();
    });
  }

  function mostrarNoChat(imagem) {
    if (!imagem?.id || mostradasNoChat.has(imagem.id)) return;
    mostradasNoChat.add(imagem.id);
    CondorConversa.adicionarMidia(url(imagem.id), `${imagem.pedido} · ${imagem.modelo}`, 'generated');
  }

  async function atualizar() {
    if (carregando) return;
    carregando = true;
    try {
      const resposta = await fetch('/api/media/images', { cache: 'no-store' });
      const dados = await resposta.json();
      if (!resposta.ok) throw new Error(dados.erro || 'galeria indisponível');
      itens = dados.itens || [];
      pintar();
    } catch (erro) {
      $('galleryGrid').innerHTML = `<div class="gallery-empty">GALERIA INDISPONÍVEL · ${escapar(erro.message)}</div>`;
    } finally {
      carregando = false;
    }
  }

  function pintar() {
    $('galleryCount').textContent = `${itens.length} IMAGE${itens.length === 1 ? 'M' : 'NS'}`;
    if (!itens.length) {
      $('galleryGrid').innerHTML = '<div class="gallery-empty">NENHUMA IMAGEM AINDA · PEÇA "CONDOR, CRIA UMA IMAGEM DE..."</div>';
      pintarDetalhe(null);
      return;
    }
    $('galleryGrid').innerHTML = itens.map((item) => `
      <button type="button" class="gallery-item${item.id === selecionada ? ' selected' : ''}" data-id="${escapar(item.id)}">
        <img loading="lazy" src="${url(item.id)}" alt="${escapar(item.pedido)}">
        <span>${escapar(item.pedido)}</span>
      </button>`).join('');
    $('galleryGrid').querySelectorAll('[data-id]').forEach((botao) => {
      botao.addEventListener('click', () => selecionar(botao.dataset.id));
    });
    pintarDetalhe(itens.find((item) => item.id === selecionada) || null);
  }

  function selecionar(id) {
    selecionada = id;
    $('galleryGrid').querySelectorAll('[data-id]').forEach((b) => b.classList.toggle('selected', b.dataset.id === id));
    pintarDetalhe(itens.find((item) => item.id === id) || null);
  }

  function pintarDetalhe(item) {
    const alvo = $('galleryDetail');
    if (!item) {
      alvo.innerHTML = '<p>Clique numa imagem para ver o pedido, o prompt final e a seed.</p>';
      return;
    }
    const data = new Date(item.criado * 1000).toLocaleString('pt-BR');
    alvo.innerHTML = `
      <img src="${url(item.id)}" alt="${escapar(item.pedido)}">
      <h3>${escapar(item.pedido)}</h3>
      <div class="gallery-meta">
        <span>MODELO<b>${escapar(item.modelo)}</b></span>
        <span>TAMANHO<b>${item.largura}×${item.altura}</b></span>
        <span>SEED<b>${item.seed}</b></span>
        <span>ORIGEM<b>${item.origem === 'cerebro' ? 'CÉREBRO' : 'CHAT'}</b></span>
        <span>CRIADA<b>${escapar(data)}</b></span>
      </div>
      <details><summary>PROMPT FINAL</summary><p>${escapar(item.prompt_final)}</p></details>
      <div class="gallery-actions">
        <button type="button" data-acao="variacao">NOVA VARIAÇÃO</button>
        <button type="button" data-acao="igual">REFAZER IGUAL</button>
        <button type="button" data-acao="apagar" class="danger">APAGAR</button>
      </div>`;
    alvo.querySelector('[data-acao="variacao"]').addEventListener('click', () => refazer(item, false));
    alvo.querySelector('[data-acao="igual"]').addEventListener('click', () => refazer(item, true));
    alvo.querySelector('[data-acao="apagar"]').addEventListener('click', (e) => apagar(item, e.currentTarget));
  }

  async function refazer(item, mesmaSeed) {
    const botoes = $('galleryDetail').querySelectorAll('button');
    botoes.forEach((b) => { b.disabled = true; });
    $('galleryCount').textContent = 'CRIANDO...';
    try {
      const formato = item.largura > item.altura ? '1536x1024' : item.largura < item.altura ? '1024x1536' : '1024x1024';
      const resposta = await fetch('/api/media/images/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: item.pedido, size: formato, quality: 'high', seed: mesmaSeed ? item.seed : null }),
      });
      const dados = await resposta.json();
      if (!resposta.ok) throw new Error(dados.erro || 'não consegui criar');
      selecionada = dados.image?.id || selecionada;
      await atualizar();
    } catch (erro) {
      CondorConversa.mostrarAviso(String(erro.message).toUpperCase(), true);
      botoes.forEach((b) => { b.disabled = false; });
      pintar();
    }
  }

  async function apagar(item, botao) {
    if (botao.dataset.confirmar !== '1') {
      botao.dataset.confirmar = '1'; botao.textContent = 'CONFIRMAR: APAGAR';
      setTimeout(() => { if (botao.isConnected) { botao.dataset.confirmar = ''; botao.textContent = 'APAGAR'; } }, 4000);
      return;
    }
    botao.disabled = true;
    const resposta = await fetch(url(item.id), { method: 'DELETE' });
    if (resposta.ok) { selecionada = null; await atualizar(); }
    else { botao.disabled = false; CondorConversa.mostrarAviso('NÃO CONSEGUI APAGAR', true); }
  }

  return { init, atualizar, marcarMostrada: (id) => mostradasNoChat.add(id) };
})();
