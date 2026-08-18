window.addEventListener('DOMContentLoaded', async () => {
  // Sem a prova local da janela nativa, nada do sistema interno e iniciado ou
  // exposto como uma pre-visualizacao navegavel.
  try {
    await CondorSession.ready;
  } catch (_) {
    return;
  }
  CondorSeguranca.init();
  CondorRouter.init();
  CondorConversa.init();
  CondorVoz.init();
  CondorMemoria.init();
  CondorProjetos.init();
  CondorCoreUI.init();
  CondorErros.init();
  CondorWS.conectar();

  const agora = new Date();
  document.getElementById('sessionLabel').textContent =
    `SESSÃO · ${String(agora.getHours()).padStart(2, '0')}:${String(agora.getMinutes()).padStart(2, '0')}`;
});
