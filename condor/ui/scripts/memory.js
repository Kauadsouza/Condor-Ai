/**
 * CondorMemoria — a tela do grafo: o que ele sabe e como as coisas se ligam.
 *
 * O layout é radial simples: os nós mais mencionados ficam no miolo e o resto
 * se espalha em anéis. Sem física, sem biblioteca — só trigonometria e SVG.
 */
const CondorMemoria = (() => {
  const $ = (id) => document.getElementById(id);
  const CORES = {
    TRABALHO: '#5EEAD4', PESSOAL: '#8B7CFF', ESTUDOS: '#F472B6',
    HABITOS: '#8B8FA8', 'HÁBITOS': '#8B8FA8', GERAL: '#C4B5FD',
  };

  function init() {
    atualizar();
    CondorWS.ao('memoria.stats', pintarNumeros);
    // A memória só muda quando ele aprende — recarregar de minuto em minuto basta.
    setInterval(() => {
      if (CondorRouter.atual() === 'memoria') atualizar();
    }, 60000);
  }

  async function atualizar() {
    try {
      const [grafo, fluxo] = await Promise.all([
        fetch('/api/memoria/grafo').then(r => r.json()),
        fetch('/api/memoria/fluxo').then(r => r.json()),
      ]);
      desenhar(grafo);
      pintarFluxo(fluxo.itens || []);
    } catch (e) {
      console.warn('[memoria] não consegui carregar', e);
    }
  }

  function desenhar(grafo) {
    const svg = $('memGraph');
    svg.innerHTML = '';
    const nos = grafo.nos || [];
    if (!nos.length) {
      svg.innerHTML = `<text x="300" y="255" text-anchor="middle" fill="#5A5F78"
        font-size="11" letter-spacing="2">AINDA NÃO APRENDI NADA SOBRE VOCÊ</text>`;
      return;
    }

    const cx = 300, cy = 250;
    const posicoes = {};
    nos.forEach((no, i) => {
      if (i === 0) { posicoes[no.id] = { x: cx, y: cy }; return; }
      const anel = Math.floor((i - 1) / 8);
      const naVolta = (i - 1) % 8;
      const raio = 85 + anel * 78;
      const angulo = (naVolta / 8) * Math.PI * 2 + anel * 0.4;
      posicoes[no.id] = {
        x: cx + Math.cos(angulo) * raio,
        y: cy + Math.sin(angulo) * raio * 0.85,
      };
    });

    const partes = [];
    (grafo.arestas || []).forEach(a => {
      const p1 = posicoes[a.de], p2 = posicoes[a.para];
      if (!p1 || !p2) return;
      partes.push(`<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}"
        stroke="rgba(139,124,255,.28)" stroke-width="1" stroke-dasharray="3 4"/>`);
    });

    nos.forEach((no, i) => {
      const p = posicoes[no.id];
      const cor = CORES[(no.cluster || 'GERAL').toUpperCase()] || CORES.GERAL;
      const r = i === 0 ? 9 : Math.min(7, 3.5 + (no.mencoes || 1) * 0.6);
      partes.push(`
        <g class="mem-no" data-nome="${escapar(no.nome)}" data-tipo="${escapar(no.tipo)}">
          <circle cx="${p.x}" cy="${p.y}" r="${r + 6}" fill="${cor}" opacity=".10"/>
          <circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${cor}" opacity=".9"/>
          <text x="${p.x}" y="${p.y + r + 13}" text-anchor="middle" fill="#C8CADD"
                font-size="9.5" letter-spacing=".4">${escapar(corta(no.nome, 18))}</text>
        </g>`);
    });

    svg.innerHTML = partes.join('');

    const dica = $('memTooltip');
    svg.querySelectorAll('.mem-no').forEach(g => {
      g.style.cursor = 'pointer';
      g.addEventListener('mouseenter', () => {
        $('tooltipText').textContent =
          `${g.dataset.nome} — ${g.dataset.tipo}`;
        dica.style.display = 'block';
      });
      g.addEventListener('mouseleave', () => { dica.style.display = 'none'; });
    });
  }

  function pintarFluxo(itens) {
    const alvo = $('memStream');
    if (!itens.length) {
      alvo.innerHTML = `<div class="stream-line">nada aprendido ainda</div>`;
      return;
    }
    alvo.innerHTML = itens.map((it, i) => {
      const classe = ['', 'vio', 'pnk'][i % 3];
      const hora = new Date((it.ts || 0) * 1000)
        .toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      return `<div class="stream-line ${classe}">
        <span class="sl-time">${hora}</span> ${escapar(it.texto)}</div>`;
    }).join('');
  }

  function pintarNumeros(m) {
    if (m.nos != null) $('statNodes').textContent = m.nos;
    if (m.conexoes != null) $('statEdges').textContent = m.conexoes;
  }

  const corta = (t, n) => (t || '').length > n ? t.slice(0, n - 1) + '…' : (t || '');

  function escapar(t) {
    const d = document.createElement('div');
    d.textContent = t == null ? '' : String(t);
    return d.innerHTML;
  }

  return { init, atualizar };
})();
