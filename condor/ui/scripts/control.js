/** Painel operacional exclusivo do aplicativo local Condor. */
const CondorControle = (() => {
  let initialized = false;

  function text(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  }

  function render(state) {
    text('controlStateBadge', state.emergency_stop ? 'INTERROMPIDO' : 'LOCAL ATIVO');
    text('controlVault', state.vault_unlocked ? 'desbloqueado' : 'bloqueado');
    text('controlProfile', state.profile || '—');
    text('controlModel', `${state.provider || 'local'} · ${state.model || 'sem modelo'}`);
    text('controlIntegrity', state.code_integrity?.ok === true ? 'código verificado' : (state.code_integrity?.detail || 'aguardando cofre'));
    text('controlAudit', state.audit_ok ? `${state.audit_events || 0} eventos íntegros` : 'revisão necessária');
    text('controlSimulation', state.simulation ? 'simulação' : 'operações reais confirmadas');

    const profile = document.getElementById('controlProfileInput');
    const simulation = document.getElementById('controlSimulationInput');
    if (profile) profile.value = state.profile || 'assistant';
    if (simulation) simulation.checked = Boolean(state.simulation);

    const roots = document.getElementById('controlRoots');
    if (roots) {
      roots.innerHTML = '';
      (state.allowed_roots || []).forEach((root) => {
        const chip = document.createElement('span');
        chip.textContent = root;
        chip.title = root;
        roots.appendChild(chip);
      });
    }
  }

  async function atualizar() {
    await CondorSession.ready;
    try {
      const response = await fetch('/api/seguranca/estado');
      if (!response.ok) throw new Error('estado indisponível');
      render(await response.json());
    } catch {
      text('controlStateBadge', 'INDISPONÍVEL');
      text('controlFeedback', 'Não foi possível consultar o núcleo local.');
    }
  }

  function init() {
    if (initialized) return;
    initialized = true;
    const form = document.getElementById('controlForm');
    form?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const feedback = document.getElementById('controlFeedback');
      const values = new FormData(form);
      const passphrase = String(values.get('passphrase') || '');
      if (passphrase.length < 12) {
        feedback.textContent = 'Digite sua frase secreta para confirmar.';
        return;
      }
      feedback.textContent = 'Aplicando no núcleo local...';
      const response = await fetch('/api/seguranca/politica', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile: values.get('profile'),
          simulation: values.get('simulation') === 'on',
          passphrase,
        }),
      });
      const result = await response.json();
      form.querySelector('input[name="passphrase"]').value = '';
      if (!response.ok) {
        feedback.textContent = result.erro || 'Não foi possível alterar o perfil.';
        return;
      }
      feedback.textContent = 'Controle local atualizado.';
      await atualizar();
    });
    document.getElementById('controlIntegrityRefresh')?.addEventListener('click', async () => {
      const feedback = document.getElementById('controlFeedback');
      const passphraseInput = form?.querySelector('input[name="passphrase"]');
      const passphrase = String(passphraseInput?.value || '');
      if (passphrase.length < 12) {
        feedback.textContent = 'Digite sua frase secreta para reconhecer a atualização.';
        return;
      }
      feedback.textContent = 'Assinando a versão instalada...';
      const response = await fetch('/api/seguranca/integridade/recriar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase }),
      });
      const result = await response.json();
      passphraseInput.value = '';
      if (!response.ok) {
        feedback.textContent = result.erro || 'Não foi possível reconhecer a atualização.';
        return;
      }
      feedback.textContent = `${result.files} arquivos verificados e assinados.`;
      await atualizar();
    });
    void atualizar();
  }

  return { init, atualizar };
})();
