/**
 * CondorVisor — abre uma imagem em tela cheia com zoom, como no Claude/ChatGPT.
 *
 * Clique em qualquer imagem do chat ou da galeria. Rodinha do mouse dá zoom no
 * ponto do cursor, clique duplo alterna 1x/2,5x, arrastar move a imagem, setas
 * +/−/0 no teclado, Esc ou clique fora fecha.
 */
const CondorVisor = (() => {
  const MIN = 1;
  const MAX = 8;
  let raiz = null;
  let imagem = null;
  let legenda = null;
  let rotuloZoom = null;
  let escala = 1;
  let x = 0;
  let y = 0;
  let arrasto = null;

  function montar() {
    if (raiz) return;
    raiz = document.createElement('div');
    raiz.className = 'image-viewer';
    raiz.hidden = true;
    raiz.setAttribute('role', 'dialog');
    raiz.setAttribute('aria-modal', 'true');
    raiz.setAttribute('aria-label', 'Imagem em tela cheia');
    raiz.innerHTML = `
      <div class="image-viewer-stage"><img alt="" draggable="false"></div>
      <div class="image-viewer-bar">
        <button type="button" data-acao="menos" title="Diminuir (−)">−</button>
        <button type="button" data-acao="ajustar" title="Tamanho da tela (0)"><span>100%</span></button>
        <button type="button" data-acao="mais" title="Aumentar (+)">+</button>
        <span class="image-viewer-caption"></span>
        <button type="button" data-acao="fechar" class="close" title="Fechar (Esc)">✕</button>
      </div>`;
    document.body.append(raiz);
    imagem = raiz.querySelector('img');
    legenda = raiz.querySelector('.image-viewer-caption');
    rotuloZoom = raiz.querySelector('[data-acao="ajustar"] span');
    const palco = raiz.querySelector('.image-viewer-stage');

    raiz.querySelector('[data-acao="menos"]').addEventListener('click', () => zoomNoCentro(escala / 1.4));
    raiz.querySelector('[data-acao="mais"]').addEventListener('click', () => zoomNoCentro(escala * 1.4));
    raiz.querySelector('[data-acao="ajustar"]').addEventListener('click', ajustar);
    raiz.querySelector('[data-acao="fechar"]').addEventListener('click', fechar);
    // Clique no fundo escuro (fora da imagem) fecha.
    palco.addEventListener('click', (e) => { if (e.target === palco && !arrasto?.moveu) fechar(); });

    palco.addEventListener('wheel', (e) => {
      e.preventDefault();
      const fator = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      zoomEm(escala * fator, e.clientX, e.clientY);
    }, { passive: false });

    imagem.addEventListener('dblclick', (e) => {
      if (escala > 1.01) ajustar();
      else zoomEm(2.5, e.clientX, e.clientY);
    });

    imagem.addEventListener('pointerdown', (e) => {
      if (escala <= 1) return;
      arrasto = { id: e.pointerId, px: e.clientX, py: e.clientY, x, y, moveu: false };
      imagem.setPointerCapture(e.pointerId);
      raiz.classList.add('dragging');
    });
    imagem.addEventListener('pointermove', (e) => {
      if (!arrasto || arrasto.id !== e.pointerId) return;
      const dx = e.clientX - arrasto.px;
      const dy = e.clientY - arrasto.py;
      if (Math.abs(dx) + Math.abs(dy) > 3) arrasto.moveu = true;
      x = arrasto.x + dx;
      y = arrasto.y + dy;
      aplicar();
    });
    const soltar = () => { raiz.classList.remove('dragging'); setTimeout(() => { arrasto = null; }, 0); };
    imagem.addEventListener('pointerup', soltar);
    imagem.addEventListener('pointercancel', soltar);

    document.addEventListener('keydown', (e) => {
      if (raiz.hidden) return;
      if (e.key === 'Escape') { e.stopPropagation(); fechar(); }
      else if (e.key === '+' || e.key === '=') zoomNoCentro(escala * 1.4);
      else if (e.key === '-') zoomNoCentro(escala / 1.4);
      else if (e.key === '0') ajustar();
    }, true);
  }

  function aplicar() {
    // Não deixa a imagem sair inteira da tela ao arrastar.
    const caixa = imagem.getBoundingClientRect();
    const largura = caixa.width / escala;
    const altura = caixa.height / escala;
    const folgaX = Math.max(0, (largura * escala - window.innerWidth) / 2 + 80);
    const folgaY = Math.max(0, (altura * escala - window.innerHeight) / 2 + 80);
    if (escala <= 1) { x = 0; y = 0; }
    x = Math.max(-folgaX, Math.min(folgaX, x));
    y = Math.max(-folgaY, Math.min(folgaY, y));
    imagem.style.transform = `translate(${x}px, ${y}px) scale(${escala})`;
    rotuloZoom.textContent = `${Math.round(escala * 100)}%`;
    raiz.classList.toggle('zoomed', escala > 1.01);
  }

  // Zoom mantendo parado o ponto que está embaixo do cursor.
  function zoomEm(nova, cx, cy) {
    const alvo = Math.max(MIN, Math.min(MAX, nova));
    const caixa = imagem.getBoundingClientRect();
    const centroX = caixa.left + caixa.width / 2;
    const centroY = caixa.top + caixa.height / 2;
    const razao = alvo / escala;
    x += (cx - centroX) * (1 - razao);
    y += (cy - centroY) * (1 - razao);
    escala = alvo;
    aplicar();
  }

  function zoomNoCentro(nova) {
    zoomEm(nova, window.innerWidth / 2, window.innerHeight / 2);
  }

  function ajustar() {
    escala = 1; x = 0; y = 0;
    aplicar();
  }

  function abrir(src, texto = '') {
    if (!src) return;
    montar();
    imagem.src = src;
    imagem.alt = texto || 'Imagem do Condor';
    legenda.textContent = texto || '';
    raiz.hidden = false;
    document.body.classList.add('viewer-open');
    ajustar();
    raiz.querySelector('[data-acao="fechar"]').focus();
  }

  function fechar() {
    if (!raiz || raiz.hidden) return;
    raiz.hidden = true;
    document.body.classList.remove('viewer-open');
    imagem.removeAttribute('src');
  }

  function init() {
    // Delegado: vale para imagens que ainda vão aparecer no chat e na galeria.
    document.addEventListener('click', (e) => {
      const alvo = e.target.closest('.msg-media img, .gallery-detail > img');
      if (!alvo) return;
      const legendaAlvo = alvo.closest('figure')?.querySelector('figcaption')?.textContent
        || alvo.closest('.gallery-detail')?.querySelector('h3')?.textContent || alvo.alt;
      abrir(alvo.currentSrc || alvo.src, legendaAlvo);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
  return { abrir, fechar };
})();
