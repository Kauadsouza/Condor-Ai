window.addEventListener('DOMContentLoaded', async () => {
  // Sem a prova local da janela nativa, nada do sistema interno e iniciado ou
  // exposto como uma pre-visualizacao navegavel.
  try {
    await CondorSession.ready;
  } catch (_) {
    return;
  }
  // A sessao local ja foi provada. A tela de boot nao pode ficar por cima do
  // aplicativo caso um modulo secundario demore ou falhe durante seu init.
  document.getElementById('coreBoot')?.classList.add('done');
  CondorSeguranca.init();
  CondorRouter.init();
  CondorConversa.init();
  CondorVoz.init();
  CondorMemoria.init();
  CondorCell.init();
  CondorProjetos.init();
  CondorCoreUI.init();
  CondorErros.init();
  CondorWS.conectar();
  // Descarta tambem dados de memoria/projetos exibidos por outras abas.
  CondorWS.ao('seguranca.bloqueado', () => {
    CondorVoz.stopForSecurity();
    document.getElementById('frame').hidden = true;
    location.reload();
  });

  const agora = new Date();
  document.getElementById('sessionLabel').textContent =
    `SESSÃO · ${String(agora.getHours()).padStart(2, '0')}:${String(agora.getMinutes()).padStart(2, '0')}`;
});
