/**
 * CondorProjects — projetos e memory tags dinâmicos.
 * Só aparecem quando o Condor aprender sobre eles via conversa.
 * Enquanto não há dados: globo vazio, sem cards, sem tags.
 */
const CondorProjects = (() => {
  const ORBITS    = ['ob-a', 'ob-b', 'ob-c', 'ob-d'];
  const TAG_SPOTS = [
    { top: '18%', left: '14%',  delay: '0s',    color: '' },
    { top: '26%', right: '16%', delay: '1.2s',  color: 'rgba(94,234,212,.5)' },
    { top: '72%', left: '18%',  delay: '2.4s',  color: '' },
    { top: '78%', right: '20%', delay: '3.6s',  color: 'rgba(139,124,255,.5)' },
    { top: '12%', left: '42%',  delay: '1.8s',  color: 'rgba(94,234,212,.4)' },
    { top: '88%', left: '46%',  delay: '0.6s',  color: '' },
  ];

  function init() {
    loadProjects();
    loadMemTags();

    // Atualiza quando o Condor aprende algo novo
    CondorWS.on('memory.learned', () => {
      loadProjects();
      loadMemTags();
    });

    // Atualiza a cada 30s enquanto na tela de projetos
    setInterval(() => {
      loadProjects();
      loadMemTags();
    }, 30_000);
  }

  async function loadProjects() {
    try {
      const data = await fetch('/api/projects').then(r => r.json());
      renderProjects(data.projects || []);
    } catch (_) {}
  }

  async function loadMemTags() {
    try {
      const items = await fetch('/api/memory/stream').then(r => r.json());
      renderMemTags(items || []);
    } catch (_) {}
  }

  function renderProjects(projects) {
    const container = document.getElementById('projectOrbiters');
    if (!container) return;
    container.innerHTML = '';

    if (projects.length === 0) return;  // globo vazio — normal no início

    projects.slice(0, 4).forEach((proj, i) => {
      const isViolet = i % 2 === 1;
      const orbit    = ORBITS[i % ORBITS.length];

      const orbiter = document.createElement('div');
      orbiter.className = `proj-orbiter ${orbit}`;
      orbiter.innerHTML = `
        <div class="proj-card">
          <div class="pc-inner">
            <span class="pc-dot ${isViolet ? 'v' : ''}"></span>
            <div>
              <div class="pc-lbl ${isViolet ? 'v' : ''}">PROJETO · ${String(i + 1).padStart(2, '0')}</div>
              <div class="pc-title">${_esc(proj.name)}</div>
            </div>
          </div>
        </div>`;
      container.appendChild(orbiter);
    });
  }

  function renderMemTags(items) {
    const container = document.getElementById('memTagsContainer');
    if (!container) return;
    container.innerHTML = '';

    if (items.length === 0) return;

    items.slice(0, TAG_SPOTS.length).forEach((item, i) => {
      const spot = TAG_SPOTS[i];
      const tag  = document.createElement('div');
      tag.className = 'mem-tag';

      // Posição
      if (spot.left)  tag.style.left  = spot.left;
      if (spot.right) tag.style.right = spot.right;
      tag.style.top            = spot.top;
      tag.style.animationDelay = spot.delay;
      if (spot.color) tag.style.color = spot.color;

      // Texto: mostra o nome da entidade aprendida
      const prefix = item.cluster === 'TRABALHO' ? '+' : '·';
      tag.textContent = `${prefix} ${item.name.toLowerCase().replace(/\s+/g, '_')}`;
      container.appendChild(tag);
    });
  }

  function _esc(s) {
    return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  return { init };
})();
