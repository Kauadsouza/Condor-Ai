/** Painel local do protótipo Condor X. */
const CondorProjetos = (() => {
  const MODULOS = {
    head: {
      zone: 'ANATOMIA CRANIOFACIAL', title: 'Cabeça',
      text: 'Crânio humano, mandíbula definida, olhos completos, nariz, orelhas e proporções faciais naturais.',
      items: ['Crânio e mandíbula', 'Olhos e pálpebras', 'Interface facial técnica'],
    },
    chest: {
      zone: 'ESTRUTURA CENTRAL', title: 'Tórax',
      text: 'Volume humano atlético, cintura anatômica, clavículas, peitoral e superfície tecnológica integrada.',
      items: ['Caixa torácica proporcional', 'Postura neutra real', 'Núcleo C integrado'],
    },
    'left-arm': {
      zone: 'MEMBRO SUPERIOR', title: 'Braço esquerdo',
      text: 'Ombro arredondado, bíceps, tríceps, antebraço orgânico, punho articulado e mão com cinco dedos.',
      items: ['Deltoide anatômico', 'Volume muscular contínuo', 'Mão humana completa'],
    },
    'right-arm': {
      zone: 'MEMBRO SUPERIOR', title: 'Braço direito',
      text: 'Ombro arredondado, bíceps, tríceps, antebraço orgânico, punho articulado e mão com cinco dedos.',
      items: ['Deltoide anatômico', 'Volume muscular contínuo', 'Mão humana completa'],
    },
    legs: {
      zone: 'BASE E LOCOMOÇÃO', title: 'Pernas',
      text: 'Quadril, coxas, joelhos, panturrilhas, tornozelos e pés seguem uma linha corporal humana contínua.',
      items: ['Quadríceps e posteriores', 'Patelas definidas', 'Pés e dedos proporcionais'],
    },
    power: {
      zone: 'IDENTIDADE CONDOR', title: 'Núcleo C',
      text: 'A letra C permanece como assinatura visual do Condor X, integrada ao centro do peito.',
      items: ['Marca C permanente', 'Halo de telemetria', 'Pulso visual local'],
    },
  };

  function selecionar(id) {
    const modulo = MODULOS[id] || MODULOS.chest;
    document.querySelectorAll('[data-cx-part]').forEach((button) => {
      button.classList.toggle('active', button.dataset.cxPart === id);
    });
    document.getElementById('cxDetailZone').textContent = modulo.zone;
    document.getElementById('cxDetailTitle').textContent = modulo.title;
    document.getElementById('cxDetailText').textContent = modulo.text;
    document.getElementById('cxDetailList').innerHTML = modulo.items.map((item) => `<li>${item}</li>`).join('');
    window.dispatchEvent(new CustomEvent('condor-x-select', { detail: { id } }));
  }

  function init() {
    document.querySelectorAll('[data-cx-part]').forEach((button) => {
      button.addEventListener('click', () => selecionar(button.dataset.cxPart));
    });
    window.addEventListener('condor-x-picked', (event) => selecionar(event.detail.id));
    selecionar('chest');
  }

  function atualizar() {
    window.dispatchEvent(new Event('condor-x-resize'));
  }

  return { init, atualizar, selecionar };
})();
