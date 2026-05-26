/**
 * CondorRouter — navegação entre as 4 telas.
 */
const CondorRouter = (() => {
  let current = 'projetos';

  function init() {
    // Tabs
    document.querySelectorAll('.top-tab').forEach(btn => {
      btn.addEventListener('click', () => go(btn.dataset.screen));
    });

    // Botão ERROS
    document.getElementById('errosBtn').addEventListener('click', () => go('erros'));

    // Botão VOLTAR
    document.getElementById('backBtn').addEventListener('click', () => go('projetos'));
  }

  function go(screen) {
    // Esconde todas as telas
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));

    // Mostra a tela alvo
    const el = document.getElementById(`screen-${screen}`);
    if (el) el.classList.add('active');
    current = screen;

    const frame     = document.getElementById('frame');
    const topNav    = document.getElementById('topNav');
    const errosBtn  = document.getElementById('errosBtn');
    const backBtn   = document.getElementById('backBtn');
    const diagBadge = document.getElementById('diagBadge');

    if (screen === 'erros') {
      frame.classList.add('is-erros');
      topNav.style.display    = 'none';
      errosBtn.style.display  = 'none';
      backBtn.style.display   = 'flex';
      diagBadge.style.display = 'flex';
    } else {
      frame.classList.remove('is-erros');
      topNav.style.display    = 'flex';
      errosBtn.style.display  = 'flex';
      backBtn.style.display   = 'none';
      diagBadge.style.display = 'none';

      // Atualiza aba ativa
      document.querySelectorAll('.top-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.screen === screen);
      });
    }

    CondorWS.send({ type: 'screen.change', screen });
  }

  return { init, go, current: () => current };
})();
