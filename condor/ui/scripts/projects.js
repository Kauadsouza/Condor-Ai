/**
 * CondorProjetos — os cards que orbitam a esfera central.
 *
 * Cada card é um projeto que o Condor identificou sozinho conversando com você.
 * Sem projeto nenhum, a esfera fica lá girando e o texto convida a falar.
 */
const CondorProjetos = (() => {
  const ORBITAS = ['ob-a', 'ob-b', 'ob-c', 'ob-d'];

  function init() {
    atualizar();
    setInterval(() => {
      if (CondorRouter.atual() === 'projetos') atualizar();
    }, 60000);
  }

  async function atualizar() {
    try {
      const [proj, fluxo] = await Promise.all([
        fetch('/api/projetos').then(r => r.json()),
        fetch('/api/memoria/fluxo').then(r => r.json()),
      ]);
      pintarOrbitas(proj.projetos || []);
      pintarEtiquetas((fluxo.itens || []).slice(0, 6));
    } catch (e) {
      console.warn('[projetos] não consegui carregar', e);
    }
  }

  function pintarOrbitas(projetos) {
    const alvo = document.getElementById('projectOrbiters');
    alvo.innerHTML = projetos.slice(0, 4).map((p, i) => `
      <div class="proj-orbiter ${ORBITAS[i]}">
        <div class="proj-card">
          <div class="pc-inner">
            <span class="pc-dot ${i % 2 ? 'v' : ''}"></span>
            <span class="pc-lbl ${i % 2 ? 'v' : ''}">${escapar((p.cluster || 'PROJETO').toUpperCase())}</span>
          </div>
          <div class="pc-title">${escapar(corta(p.nome, 26))}</div>
        </div>
      </div>`).join('');
  }

  function pintarEtiquetas(itens) {
    const alvo = document.getElementById('memTagsContainer');
    const cantos = [
      { top: '18%', left: '12%' }, { top: '28%', right: '14%' },
      { top: '62%', left: '9%' }, { top: '72%', right: '11%' },
      { top: '44%', left: '6%' }, { top: '52%', right: '7%' },
    ];
    alvo.innerHTML = itens.map((it, i) => {
      const pos = cantos[i % cantos.length];
      const estilo = Object.entries(pos).map(([k, v]) => `${k}:${v}`).join(';');
      return `<div class="mem-tag" style="${estilo};animation-delay:${i * 0.7}s">
        ${escapar(corta(it.texto, 34))}</div>`;
    }).join('');
  }

  const corta = (t, n) => (t || '').length > n ? t.slice(0, n - 1) + '…' : (t || '');

  function escapar(t) {
    const d = document.createElement('div');
    d.textContent = t == null ? '' : String(t);
    return d.innerHTML;
  }

  return { init, atualizar };
})();
