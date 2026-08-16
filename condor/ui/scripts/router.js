/**
 * CondorRouter — navegação entre as quatro telas.
 */
const CondorRouter = (() => {
  let atual = 'conversacao';

  function init() {
    document.querySelectorAll('.top-tab').forEach(btn => {
      btn.addEventListener('click', () => ir(btn.dataset.screen));
    });
    document.getElementById('errosBtn').addEventListener('click', () => ir('erros'));
    document.getElementById('backBtn').addEventListener('click', () => ir('conversacao'));
  }

  function ir(tela) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    const el = document.getElementById(`screen-${tela}`);
    if (el) el.classList.add('active');
    atual = tela;

    const frame = document.getElementById('frame');
    const nav = document.getElementById('topNav');
    const btnErros = document.getElementById('errosBtn');
    const btnVoltar = document.getElementById('backBtn');
    const selo = document.getElementById('diagBadge');

    const naTelaErros = tela === 'erros';
    frame.classList.toggle('is-erros', naTelaErros);
    nav.style.display = naTelaErros ? 'none' : 'flex';
    btnErros.style.display = naTelaErros ? 'none' : 'flex';
    btnVoltar.style.display = naTelaErros ? 'flex' : 'none';
    selo.style.display = naTelaErros ? 'flex' : 'none';

    if (!naTelaErros) {
      document.querySelectorAll('.top-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.screen === tela);
      });
    }
    // Recarrega os dados da tela que acabou de abrir. Chamada direta: os
    // módulos são `const` de topo de script, então não existem em `window`.
    if (naTelaErros) CondorErros.atualizar();
    else if (tela === 'memoria') CondorMemoria.atualizar();
    else if (tela === 'projetos') CondorProjetos.atualizar();
    else if (tela === 'controle') CondorControle.atualizar();
  }

  return { init, ir, atual: () => atual };
})();
