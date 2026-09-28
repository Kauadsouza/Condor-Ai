/** CondorTreino — progresso dos exemplos de treino e exportação para o Colab. */
const CondorTreino = (() => {
  const $ = (id) => document.getElementById(id);

  async function atualizar() {
    if (!$('systemTrainingCard')) return;
    try {
      const resposta = await fetch('/api/treino/resumo', { cache: 'no-store' });
      const dados = await resposta.json();
      if (!resposta.ok) throw new Error(dados.erro || 'indisponível');
      $('trainingReady').textContent = dados.prontos;
      $('trainingGoal').textContent = `META ${dados.meta}`;
      $('trainingBar').style.width = `${Math.min(100, Math.round((dados.prontos / dados.meta) * 100))}%`;
      $('trainingPositive').textContent = dados.positivos;
      $('trainingNegative').textContent = dados.negativos;
      $('trainingFixed').textContent = dados.corrigidos;
      $('trainingTeacher').textContent = dados.professor_api;
      $('trainingModel').textContent = dados.modelo_local || '—';
    } catch (erro) {
      $('trainingMessage').textContent = `TREINO INDISPONÍVEL · ${String(erro.message).toUpperCase()}`;
    }
  }

  async function exportar() {
    const botao = $('trainingExport');
    botao.disabled = true;
    $('trainingMessage').textContent = 'EXPORTANDO...';
    try {
      const resposta = await fetch('/api/treino/exportar', { method: 'POST' });
      const dados = await resposta.json();
      if (!resposta.ok) throw new Error(dados.erro || 'não consegui exportar');
      $('trainingMessage').textContent =
        `${dados.exemplos} EXEMPLOS EM ${dados.pasta.toUpperCase()}` + (dados.exemplos < dados.meta ? ` · IDEAL: ${dados.meta}+` : '');
    } catch (erro) {
      $('trainingMessage').textContent = String(erro.message).toUpperCase();
    } finally {
      botao.disabled = false;
    }
  }

  function init() {
    $('trainingExport')?.addEventListener('click', exportar);
    document.querySelectorAll('.top-tab[data-screen="sistema"]').forEach((aba) => aba.addEventListener('click', atualizar));
    window.addEventListener('condor-security-ready', atualizar);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
  return { atualizar };
})();
