/**
 * Memória no celular: o mesmo mapa orbital do PC (núcleo → áreas → memórias,
 * com as associações que o PC sabe explicar), números, filtros por área, lista
 * com busca e o que ele está aprendendo agora.
 *
 * O SVG é montado nó a nó com atributos (fill/stroke), sem estilo inline: a
 * página do celular tem CSP estrita e não aceita style="...".
 */
const CondorMemoriaCel = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  const CORES = {
    pessoal: '#8b7cff', trabalho: '#5eead4', preferencia: '#f472b6',
    rotina: '#94a3b8', projeto: '#48df9b', tecnico: '#fac775', geral: '#c4b5fd',
  };
  const NOMES = {
    pessoal: 'PESSOAL', trabalho: 'TRABALHO', preferencia: 'PREFERÊNCIAS',
    rotina: 'ROTINA', projeto: 'PROJETOS', tecnico: 'TÉCNICO', geral: 'GERAL',
  };
  const ORDEM = ['trabalho', 'pessoal', 'projeto', 'preferencia', 'rotina', 'tecnico', 'geral'];
  const $ = (id) => document.getElementById(id);

  let mapa = null;
  let categoria = 'todos';
  let modo = 'mapa';
  let zoom = 1;
  let desloc = { x: 0, y: 0 };    // arrasto com o dedo, só com zoom
  let layout = null;
  let aoAbrirFato = () => {};

  const nome = (c) => NOMES[c] || String(c || 'geral').replaceAll('_', ' ').toUpperCase();
  const cor = (c) => CORES[c] || CORES.geral;
  const resumir = (v, n) => { const t = String(v || '').replace(/\s+/g, ' ').trim(); return t.length > n ? `${t.slice(0, n - 1)}…` : t; };

  function no(tipo, atributos = {}, filhos = []) {
    const el = document.createElementNS(NS, tipo);
    Object.entries(atributos).forEach(([k, v]) => el.setAttribute(k, String(v)));
    filhos.forEach((f) => el.appendChild(f));
    return el;
  }
  function texto(conteudo, atributos) { const el = no('text', atributos); el.textContent = conteudo; return el; }

  function visiveis() {
    return (mapa?.fatos || []).filter((f) => categoria === 'todos' || f.categoria === categoria);
  }

  function construir(fatos) {
    const grupos = new Map();
    fatos.forEach((f) => { const c = f.categoria || 'geral'; if (!grupos.has(c)) grupos.set(c, []); grupos.get(c).push(f); });
    const entradas = [...grupos.entries()].sort((a, b) => {
      const ia = ORDEM.indexOf(a[0]), ib = ORDEM.indexOf(b[0]);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a[0].localeCompare(b[0]);
    });
    const maior = Math.max(...entradas.map(([, i]) => i.length), 1);
    let resto = maior, aneis = 0;
    while (resto > 0) { resto -= 6 + aneis * 4; aneis += 1; }
    const alcance = 120 + Math.max(0, aneis - 1) * 72;
    // Celular é em pé: o mapa cresce para baixo, não para os lados.
    const raioX = Math.max(165, 110 + alcance * 0.5);
    const raioY = Math.max(400, 280 + alcance * 1.1);
    const largura = Math.ceil((raioX + alcance + 90) * 2);
    const altura = Math.ceil((raioY + alcance + 90) * 2);
    const centro = { x: largura / 2, y: altura / 2 };
    const categorias = entradas.map(([nomeCat, itens], i) => {
      const angulo = -Math.PI / 2 + i * (Math.PI * 2 / entradas.length);
      return { nome: nomeCat, fatos: itens, angulo, x: centro.x + Math.cos(angulo) * raioX, y: centro.y + Math.sin(angulo) * raioY };
    });
    const pontos = [];
    categorias.forEach((c) => {
      let cursor = 0, anel = 0;
      while (cursor < c.fatos.length) {
        const capacidade = 6 + anel * 4;
        const itens = c.fatos.slice(cursor, cursor + capacidade);
        const raio = 122 + anel * 72;
        itens.forEach((fato, p) => {
          // Leque virado para fora: nada aponta para o núcleo nem para a área vizinha.
          const passo = Math.PI * 2 / (itens.length + 2);
          const a = c.angulo + (p - (itens.length - 1) / 2) * passo + (anel % 2 ? passo / 2 : 0);
          pontos.push({ fato, x: c.x + Math.cos(a) * raio, y: c.y + Math.sin(a) * raio });
        });
        cursor += itens.length; anel += 1;
      }
    });
    // Enquadra pelo que existe de fato: com poucas áreas o mapa não fica minúsculo.
    const xs = [centro.x - 104, centro.x + 104, ...categorias.flatMap((c) => [c.x - 62, c.x + 62]), ...pontos.flatMap((p) => [p.x - 64, p.x + 64])];
    const ys = [centro.y - 104, centro.y + 104, ...categorias.flatMap((c) => [c.y - 62, c.y + 62]), ...pontos.flatMap((p) => [p.y - 30, p.y + 30])];
    const caixa = { x: Math.min(...xs) - 12, y: Math.min(...ys) - 12 };
    caixa.w = Math.max(...xs) + 12 - caixa.x; caixa.h = Math.max(...ys) + 12 - caixa.y;
    return { largura, altura, centro, caixa, categorias, pontos,
      porCategoria: new Map(categorias.map((c) => [c.nome, c])),
      porFato: new Map(pontos.map((p) => [Number(p.fato.id), p])) };
  }

  function desenharMapa() {
    const area = $('memoriaMapa');
    area.innerHTML = '';
    const fatos = visiveis();
    if (!fatos.length) {
      area.textContent = mapa?.fatos?.length ? 'Nenhuma memória nesta área.' : 'Ainda não há memórias no cofre.';
      return;
    }
    layout = construir(fatos);
    const svg = no('svg', { class: 'mapa-svg', role: 'img', 'aria-label': 'Memórias organizadas por área ao redor do núcleo do Condor' });
    const linhas = no('g', { 'aria-hidden': 'true' });
    layout.categorias.forEach((c) => {
      linhas.appendChild(no('path', { class: 'tronco',
        d: `M ${layout.centro.x} ${layout.centro.y} Q ${(layout.centro.x + c.x) / 2} ${(layout.centro.y + c.y) / 2 - 24} ${c.x} ${c.y}` }));
    });
    layout.pontos.forEach((p) => {
      const c = layout.porCategoria.get(p.fato.categoria || 'geral');
      linhas.appendChild(no('path', { class: 'galho', stroke: cor(p.fato.categoria), d: `M ${c.x} ${c.y} L ${p.x.toFixed(1)} ${p.y.toFixed(1)}` }));
    });
    const ids = new Set(fatos.map((f) => Number(f.id)));
    (mapa.associacoes_sugeridas || []).forEach((l) => {
      if (!ids.has(Number(l.de)) || !ids.has(Number(l.para))) return;
      const a = layout.porFato.get(Number(l.de)), b = layout.porFato.get(Number(l.para));
      if (a && b) linhas.appendChild(no('path', { class: 'associacao', d: `M ${a.x.toFixed(1)} ${a.y.toFixed(1)} L ${b.x.toFixed(1)} ${b.y.toFixed(1)}` }));
    });
    svg.appendChild(linhas);

    layout.categorias.forEach((c) => {
      const g = no('g', { class: 'no-area', transform: `translate(${c.x.toFixed(1)} ${c.y.toFixed(1)})` }, [
        no('circle', { r: 58, fill: cor(c.nome), 'fill-opacity': 0.08, stroke: cor(c.nome), 'stroke-opacity': 0.35 }),
        no('circle', { r: 42, fill: '#0a1220', stroke: cor(c.nome), 'stroke-width': 2 }),
        texto(nome(c.nome), { class: 'area-nome', y: -2, fill: cor(c.nome) }),
        texto(`${c.fatos.length} MEMÓRIAS`, { class: 'area-conta', y: 16 }),
      ]);
      g.addEventListener('click', () => { categoria = categoria === c.nome ? 'todos' : c.nome; desenhar(); });
      svg.appendChild(g);
    });

    layout.pontos.forEach((p) => {
      const g = no('g', { class: 'no-fato', transform: `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)})` }, [
        no('rect', { x: -60, y: -26, width: 120, height: 52, rx: 12, fill: '#0b1424', stroke: cor(p.fato.categoria), 'stroke-opacity': 0.75 }),
        texto(resumir(String(p.fato.chave || '').replaceAll('_', ' '), 18).toUpperCase(), { class: 'fato-chave', y: -5, fill: cor(p.fato.categoria) }),
        texto(resumir(p.fato.valor, 24), { class: 'fato-valor', y: 13 }),
      ]);
      g.addEventListener('click', () => aoAbrirFato(p.fato, ligacoesDe(p.fato)));
      svg.appendChild(g);
    });

    svg.appendChild(no('g', { class: 'nucleo', transform: `translate(${layout.centro.x} ${layout.centro.y})` }, [
      no('circle', { r: 100, class: 'anel' }), no('circle', { r: 80, class: 'anel' }),
      no('circle', { r: 64, class: 'orbe-nucleo' }),
      texto('CONDOR', { class: 'nucleo-titulo', y: 5 }),
      texto(`${fatos.length} MEMÓRIAS`, { class: 'nucleo-sub', y: 25 }),
    ]));
    area.appendChild(svg);
    ligarArrasto(svg);
    aplicarZoom();
  }

  function aplicarZoom() {
    const svg = $('memoriaMapa').querySelector('svg');
    if (!svg || !layout) return;
    const { caixa } = layout;
    const w = caixa.w / zoom, h = caixa.h / zoom;
    const cx = caixa.x + caixa.w / 2 + desloc.x, cy = caixa.y + caixa.h / 2 + desloc.y;
    svg.classList.toggle('arrastavel', zoom > 1);
    svg.setAttribute('viewBox', `${(cx - w / 2).toFixed(1)} ${(cy - h / 2).toFixed(1)} ${w.toFixed(1)} ${h.toFixed(1)}`);
  }

  function ligarArrasto(svg) {
    let inicio = null;
    svg.addEventListener('pointerdown', (e) => {
      if (zoom <= 1) return;
      inicio = { x: e.clientX, y: e.clientY, dx: desloc.x, dy: desloc.y, moveu: false };
    });
    svg.addEventListener('pointermove', (e) => {
      if (!inicio || !layout) return;
      const escala = (layout.caixa.w / zoom) / Math.max(1, svg.clientWidth);
      const mx = e.clientX - inicio.x, my = e.clientY - inicio.y;
      if (Math.abs(mx) + Math.abs(my) > 6) inicio.moveu = true;
      desloc = { x: inicio.dx - mx * escala, y: inicio.dy - my * escala };
      aplicarZoom();
    });
    const soltar = () => { if (inicio?.moveu) svg.dataset.arrastou = '1'; inicio = null; };
    svg.addEventListener('pointerup', soltar);
    svg.addEventListener('pointercancel', soltar);
    // Soltar depois de arrastar não conta como toque numa memória.
    svg.addEventListener('click', (e) => { if (svg.dataset.arrastou) { e.stopPropagation(); delete svg.dataset.arrastou; } }, true);
  }

  function ligacoesDe(fato) {
    const porId = new Map((mapa?.fatos || []).map((f) => [Number(f.id), f]));
    return (mapa?.associacoes_sugeridas || [])
      .filter((l) => Number(l.de) === Number(fato.id) || Number(l.para) === Number(fato.id))
      .map((l) => ({ ligacao: l, fato: porId.get(Number(l.de) === Number(fato.id) ? Number(l.para) : Number(l.de)) }))
      .filter((item) => item.fato);
  }

  function desenharNumeros() {
    const i = mapa?.inteligencia || {};
    const numeros = [
      [visiveis().length, 'MEMÓRIAS'], [i.entidades || 0, 'ENTIDADES'], [i.cadeias || 0, 'CADEIAS'],
      [i.associacoes_sugeridas || 0, 'LIGAÇÕES'], [`${i.cobertura_semantica || 0}/${i.fatos || 0}`, 'COM SENTIDO'],
    ];
    const alvo = $('memoriaNumeros');
    alvo.innerHTML = '';
    numeros.forEach(([valor, rotulo]) => {
      const caixa = document.createElement('div');
      const b = document.createElement('b'); b.textContent = valor;
      const s = document.createElement('span'); s.textContent = rotulo;
      caixa.append(b, s); alvo.appendChild(caixa);
    });
  }

  function desenharFiltros() {
    const contagem = {};
    (mapa?.fatos || []).forEach((f) => { contagem[f.categoria] = (contagem[f.categoria] || 0) + 1; });
    const alvo = $('memoriaFiltros');
    alvo.innerHTML = '';
    [['todos', (mapa?.fatos || []).length], ...Object.entries(contagem).sort()].forEach(([c, n]) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = categoria === c ? 'ativa' : '';
      b.textContent = `${c === 'todos' ? 'TUDO' : nome(c)} · ${n}`;
      b.addEventListener('click', () => { categoria = c; desenhar(); });
      alvo.appendChild(b);
    });
  }

  function desenhar() {
    if (!mapa) return;
    desenharNumeros();
    desenharFiltros();
    $('memoriaMapaBloco').hidden = modo !== 'mapa';
    $('memoriaListaBloco').hidden = modo !== 'lista';
    if (modo === 'mapa') desenharMapa();
  }

  function desenharFluxo(itens) {
    const alvo = $('memoriaFluxo');
    alvo.innerHTML = '';
    (itens || []).forEach((item) => {
      const linha = document.createElement('div'); linha.className = 'fluxo';
      const c = document.createElement('b'); c.textContent = nome(item.categoria);
      const t = document.createElement('span'); t.textContent = item.texto;
      linha.append(c, t); alvo.appendChild(linha);
    });
    if (!alvo.childElementCount) alvo.textContent = 'Nada novo agora.';
  }

  function carregar(dados) {
    mapa = dados.mapa || { fatos: [] };
    desenhar();
    desenharFluxo(dados.fluxo);
  }

  function init(opcoes) {
    aoAbrirFato = opcoes.aoAbrirFato;
    document.querySelectorAll('[data-memoria-modo]').forEach((b) => b.addEventListener('click', () => {
      modo = b.dataset.memoriaModo;
      document.querySelectorAll('[data-memoria-modo]').forEach((x) => x.classList.toggle('ativa', x === b));
      desenhar();
      if (modo === 'lista' && opcoes.aoMostrarLista) opcoes.aoMostrarLista();
    }));
    document.querySelectorAll('[data-zoom]').forEach((b) => b.addEventListener('click', () => {
      const z = b.dataset.zoom;
      zoom = z === '0' ? 1 : Math.max(0.6, Math.min(4, zoom * (z === '+' ? 1.3 : 0.77)));
      if (z === '0' || zoom <= 1) desloc = { x: 0, y: 0 };
      aplicarZoom();
    }));
  }

  return { init, carregar, nome, fatos: () => mapa?.fatos || [], esquecido(id) {
    if (!mapa) return;
    mapa.fatos = mapa.fatos.filter((f) => Number(f.id) !== Number(id));
    desenhar();
  } };
})();
