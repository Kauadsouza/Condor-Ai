window.addEventListener('DOMContentLoaded', () => {
  CondorSeguranca.init();
  CondorRouter.init();
  CondorConversa.init();
  CondorVoz.init();
  CondorMemoria.init();
  CondorProjetos.init();
  CondorErros.init();
  CondorWS.conectar();

  const agora = new Date();
  document.getElementById('sessionLabel').textContent =
    `SESSÃO · ${String(agora.getHours()).padStart(2, '0')}:${String(agora.getMinutes()).padStart(2, '0')}`;
});
