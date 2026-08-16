const pairView = document.getElementById('pairView');
const mobileApp = document.getElementById('mobileApp');
const pairForm = document.getElementById('pairForm');
const pairCode = document.getElementById('pairCode');
const pairError = document.getElementById('pairError');

const MODULES = {
  head: ['ANATOMIA CRANIOFACIAL', 'Cabeça', 'Crânio humano, mandíbula definida, olhos completos, nariz, orelhas e proporções faciais naturais.', ['Crânio e mandíbula', 'Olhos e pálpebras', 'Interface facial técnica']],
  chest: ['ESTRUTURA CENTRAL', 'Tórax', 'Volume humano atlético, cintura anatômica, clavículas, peitoral e superfície tecnológica integrada.', ['Caixa torácica proporcional', 'Postura neutra real', 'Núcleo C integrado']],
  'left-arm': ['MEMBRO SUPERIOR', 'Braço esquerdo', 'Ombro, braço, antebraço, punho articulado e mão com cinco dedos.', ['Deltoide anatômico', 'Volume muscular contínuo', 'Mão humana completa']],
  'right-arm': ['MEMBRO SUPERIOR', 'Braço direito', 'Ombro, braço, antebraço, punho articulado e mão com cinco dedos.', ['Deltoide anatômico', 'Volume muscular contínuo', 'Mão humana completa']],
  legs: ['BASE E LOCOMOÇÃO', 'Pernas', 'Quadril, coxas, joelhos, panturrilhas, tornozelos e pés seguem uma linha corporal humana contínua.', ['Quadríceps e posteriores', 'Patelas definidas', 'Pés proporcionais']],
  power: ['IDENTIDADE CONDOR', 'Núcleo C', 'A letra C permanece como assinatura visual do Condor X, integrada ao centro do peito.', ['Marca C permanente', 'Halo de telemetria', 'Pulso visual local']],
};

function selectModule(id) {
  const module = MODULES[id] || MODULES.chest;
  document.querySelectorAll('[data-cx-part]').forEach((button) => {
    button.classList.toggle('active', button.dataset.cxPart === id);
  });
  document.getElementById('cxDetailZone').textContent = module[0];
  document.getElementById('cxDetailTitle').textContent = module[1];
  document.getElementById('cxDetailText').textContent = module[2];
  document.getElementById('cxDetailList').innerHTML = module[3].map((item) => `<li>${item}</li>`).join('');
  window.dispatchEvent(new CustomEvent('condor-x-select', { detail: { id } }));
}

function showApp() {
  pairView.hidden = true;
  mobileApp.hidden = false;
  refreshStatus();
}

function showPair() {
  mobileApp.hidden = true;
  pairView.hidden = false;
}

async function refreshStatus() {
  try {
    const response = await fetch('/api/status', { credentials: 'same-origin', cache: 'no-store' });
    if (response.status === 401) {
      showPair();
      return;
    }
    if (!response.ok) throw new Error('Estado indisponível');
    const data = await response.json();
    document.getElementById('mobileState').textContent = data.estado || 'local';
    document.getElementById('mobileSummary').textContent = data.acordado
      ? 'O Condor está acordado e processando apenas neste PC.'
      : 'O núcleo está protegido e aguardando no seu computador.';
    document.getElementById('statusPc').textContent = 'CONECTADO';
    document.getElementById('statusAi').textContent = data.cerebro_pronto ? 'PRONTA' : 'LOCAL';
    document.getElementById('statusModel').textContent = data.modelo || 'modo protegido';
    document.getElementById('statusVoice').textContent = data.voz_local_pronta ? 'PRONTA' : 'EM ESPERA';
    document.getElementById('statusIntegrity').textContent = data.integridade_ok ? 'ÍNTEGRA' : 'VERIFICAR';
    document.getElementById('lastUpdate').textContent = `ATUALIZADO · ${new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
  } catch (error) {
    document.getElementById('statusPc').textContent = 'SEM SINAL';
    document.getElementById('lastUpdate').textContent = 'O PC NÃO RESPONDEU';
  }
}

pairForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  pairError.textContent = '';
  const code = pairCode.value.replace(/\D/g, '').slice(0, 8);
  try {
    const response = await fetch('/api/pair', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.erro || 'Código recusado');
    }
    pairCode.value = '';
    showApp();
  } catch (error) {
    pairError.textContent = error.message;
  }
});

pairCode.addEventListener('input', () => {
  pairCode.value = pairCode.value.replace(/\D/g, '').slice(0, 8);
});

document.querySelectorAll('[data-mobile-screen]').forEach((button) => {
  button.addEventListener('click', () => {
    const screen = button.dataset.mobileScreen;
    document.querySelectorAll('[data-mobile-screen]').forEach((item) => item.classList.toggle('active', item === button));
    document.getElementById('mobile-overview').hidden = screen !== 'overview';
    document.getElementById('mobile-projects').hidden = screen !== 'projects';
    if (screen === 'projects') {
      window.dispatchEvent(new CustomEvent('condor-x-visibility', { detail: { active: true } }));
      requestAnimationFrame(() => window.dispatchEvent(new Event('condor-x-resize')));
    } else {
      window.dispatchEvent(new CustomEvent('condor-x-visibility', { detail: { active: false } }));
    }
  });
});

document.querySelectorAll('[data-cx-part]').forEach((button) => {
  button.addEventListener('click', () => selectModule(button.dataset.cxPart));
});
window.addEventListener('condor-x-picked', (event) => selectModule(event.detail.id));

fetch('/api/status', { credentials: 'same-origin', cache: 'no-store' })
  .then((response) => response.ok ? showApp() : showPair())
  .catch(showPair);
setInterval(() => {
  if (!mobileApp.hidden) refreshStatus();
}, 3000);
