/**
 * CondorMemory — renderiza o grafo de constelação e o stream recente.
 */
const CondorMemory = (() => {
  const CLUSTER_COLOR = {
    TRABALHO: '#5EEAD4',
    PESSOAL:  '#8B7CFF',
    ESTUDOS:  '#F472B6',
    HÁBITOS:  '#6B7088',
    GERAL:    '#8B8FA8',
  };

  function init() {
    CondorWS.on('memory.stats', updateStats);
    CondorWS.on('memory.learned', msg => {
      if (msg.entity) prependStream(msg.entity);
      refreshGraph();
    });

    // Carrega dados iniciais via REST
    fetch('/api/memory/graph').then(r => r.json()).then(renderGraph).catch(() => {});
    fetch('/api/memory/stream').then(r => r.json()).then(items => items.forEach(prependStream)).catch(() => {});
    fetch('/api/memory/stats').then(r => r.json()).then(updateStats).catch(() => {});
  }

  function updateStats(data) {
    document.getElementById('statNodes').textContent = data.nodes ?? 0;
    document.getElementById('statEdges').textContent = data.edges ?? 0;
    document.getElementById('errCount').textContent  = '—'; // atualizado por errors.js
  }

  function prependStream(entity) {
    const container = document.getElementById('memStream');
    const cluster   = entity.cluster || 'GERAL';
    const color     = CLUSTER_COLOR[cluster] || '#8B8FA8';
    const cls       = cluster === 'PESSOAL' ? 'vio' : cluster === 'ESTUDOS' ? 'pnk' : '';

    const line = document.createElement('div');
    line.className = `stream-line ${cls}`;
    line.innerHTML = `
      <div class="sl-time">agora</div>
      <div style="color:var(--text-mid);margin-top:3px;">${entity.name}</div>`;
    container.prepend(line);

    // Mantém no máximo 10 itens
    while (container.children.length > 10) container.lastChild.remove();
  }

  function refreshGraph() {
    fetch('/api/memory/graph').then(r => r.json()).then(renderGraph).catch(() => {});
  }

  function renderGraph(data) {
    const svg   = document.getElementById('memGraph');
    const W = 600, H = 520;
    const nodes = data.nodes || [];
    const edges = data.edges || [];

    if (nodes.length === 0) {
      svg.innerHTML = `<text x="${W/2}" y="${H/2}" text-anchor="middle" fill="#5A5F78" font-size="12" font-family="Inter">Nenhuma memória ainda — converse com o Condor!</text>`;
      return;
    }

    // Layout em círculo simples
    const positions = {};
    nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
      const r = Math.min(W, H) * 0.35;
      positions[node.name] = {
        x: W / 2 + r * Math.cos(angle),
        y: H / 2 + r * Math.sin(angle),
        cluster: node.cluster,
      };
    });

    let html = '';

    // Linhas
    edges.forEach(e => {
      const f = positions[e.from];
      const t = positions[e.to];
      if (!f || !t) return;
      html += `<line x1="${f.x}" y1="${f.y}" x2="${t.x}" y2="${t.y}" stroke="rgba(255,255,255,0.12)" stroke-width="0.5"/>`;
    });

    // Nós
    nodes.forEach(node => {
      const p   = positions[node.name];
      if (!p) return;
      const col = CLUSTER_COLOR[p.cluster] || '#8B8FA8';
      const r   = node.cluster === 'TRABALHO' ? 6 : 4;
      html += `
        <circle cx="${p.x}" cy="${p.y}" r="${r + 6}" fill="${col}" opacity="0.15"/>
        <circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${col}" opacity="0.9"/>
        <text x="${p.x}" y="${p.y + r + 12}" text-anchor="middle" fill="#C8CADD" font-size="9" font-family="Inter">${_trunc(node.name, 14)}</text>`;
    });

    svg.innerHTML = html;
  }

  function _trunc(s, n) {
    return s.length > n ? s.slice(0, n) + '…' : s;
  }

  return { init };
})();
