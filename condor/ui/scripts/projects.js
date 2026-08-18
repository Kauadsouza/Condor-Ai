/** Catálogo local de projetos e ambientes anatômicos do Condor X. */
const CondorProjetos = (() => {
  let projetoAberto = null;

  const NOMES = {
    'head-group': 'Cabeça e pescoço', head: 'Cabeça', neck: 'Pescoço', chest: 'Tórax', torso: 'Tronco', abdomen: 'Abdômen', pelvis: 'Quadril', power: 'Centro',
    'left-arm': 'Braço esquerdo', 'left-shoulder': 'Ombro esquerdo', 'left-upper-arm': 'Braço esquerdo', 'left-elbow': 'Cotovelo esquerdo', 'left-forearm': 'Antebraço esquerdo', 'left-hand': 'Mão esquerda',
    'right-arm': 'Braço direito', 'right-shoulder': 'Ombro direito', 'right-upper-arm': 'Braço direito', 'right-elbow': 'Cotovelo direito', 'right-forearm': 'Antebraço direito', 'right-hand': 'Mão direita',
    legs: 'Pernas', 'left-thigh': 'Coxa esquerda', 'left-knee': 'Joelho esquerdo', 'left-shin': 'Canela esquerda', 'left-foot': 'Pé esquerdo', 'right-thigh': 'Coxa direita', 'right-knee': 'Joelho direito', 'right-shin': 'Canela direita', 'right-foot': 'Pé direito',
  };

  function selecionar(id) {
    const title = NOMES[id] || NOMES.chest;
    document.querySelectorAll('[data-cx-part]').forEach((button) => button.classList.toggle('active', button.dataset.cxPart === id));
    document.getElementById('cxDetailZone').textContent = 'AMBIENTE ANATÔMICO';
    document.getElementById('cxDetailTitle').textContent = title;
    document.getElementById('cxDetailText').textContent = 'Região preparada para organizar componentes, requisitos, notas e testes sem preencher informações automaticamente.';
    document.getElementById('cxDetailList').innerHTML = '<li>Estado: não iniciado</li><li>Registros: armazenados no cofre local</li><li>Dados: somente quando adicionados pelo proprietário</li>';
    window.dispatchEvent(new CustomEvent('condor-x-select', { detail: { id } }));
  }

  async function abrirProjeto(id) {
    if (id !== 'condor-x') return;
    try {
      await CondorSession.ready;
      await fetch(`/api/projects/${encodeURIComponent(id)}/open`, { method: 'POST' });
      if (typeof CondorCoreUI !== 'undefined') CondorCoreUI.loadStatus();
    } catch (_) { /* a interface ainda abre; o cofre mostrará o erro ao gravar */ }
    projetoAberto = id;
    document.getElementById('projectsCatalog').hidden = true;
    document.getElementById('projectDetail').hidden = false;
    selecionar('chest');
    window.dispatchEvent(new CustomEvent('condor-x-visibility', { detail: { active: true } }));
    requestAnimationFrame(() => requestAnimationFrame(() => window.dispatchEvent(new Event('condor-x-resize'))));
  }

  function voltarAoCatalogo() {
    projetoAberto = null;
    window.dispatchEvent(new Event('condor-x-region-close'));
    document.getElementById('projectDetail').hidden = true;
    document.getElementById('projectsCatalog').hidden = false;
    window.dispatchEvent(new CustomEvent('condor-x-visibility', { detail: { active: false } }));
  }

  function init() {
    document.querySelectorAll('[data-project-open]').forEach((button) => button.addEventListener('click', () => abrirProjeto(button.dataset.projectOpen)));
    document.getElementById('projectDetailBack').addEventListener('click', voltarAoCatalogo);
    document.querySelectorAll('[data-cx-part]').forEach((button) => button.addEventListener('click', () => selecionar(button.dataset.cxPart)));
    window.addEventListener('condor-x-picked', (event) => selecionar(event.detail.id));
    selecionar('chest');
    voltarAoCatalogo();
  }

  function atualizar() { voltarAoCatalogo(); }

  function esconder() {
    if (projetoAberto) window.dispatchEvent(new CustomEvent('condor-x-visibility', { detail: { active: false } }));
  }

  return { init, atualizar, selecionar, abrirProjeto, voltarAoCatalogo, esconder };
})();
