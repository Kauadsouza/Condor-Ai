/** Sessao local HttpOnly. O segredo nunca fica disponivel ao JavaScript. */
const CondorSession = (() => {
  const rawFetch = window.fetch.bind(window);

  // A janela do Condor entrega o segredo de boot no fragmento da URL. Fragmento
  // nunca viaja pro servidor, entao ele so existe aqui dentro. Lemos, limpamos
  // da barra de endereco e do historico, e usamos uma unica vez pra abrir a
  // sessao. Sem ele, a API recusa: e o que impede outro programa da maquina de
  // pedir uma sessao so mandando cabecalho fixo.
  const lerSegredoDeBoot = () => {
    const bruto = window.location.hash || '';
    const achado = bruto.match(/(?:^#|&)t=([A-Za-z0-9_-]+)/);
    if (!achado) return '';
    history.replaceState(null, '', window.location.pathname + window.location.search);
    return achado[1];
  };

  const abrirSessao = (segredo = '') => {
    const headers = { 'X-Condor-Client': 'desktop-ui' };
    if (segredo) headers['X-Condor-Token'] = segredo;
    return rawFetch('/api/session', {
      method: 'POST', credentials: 'same-origin', headers,
    });
  };

  const segredoDaJanelaNativa = async () => {
    if (!window.pywebview?.api?.condor_boot_token) {
      await new Promise((resolve) => {
        const timer = setTimeout(resolve, 1200);
        window.addEventListener('pywebviewready', () => { clearTimeout(timer); resolve(); }, { once: true });
      });
    }
    try {
      return await window.pywebview?.api?.condor_boot_token?.() || '';
    } catch (_) {
      return '';
    }
  };

  const ready = (async () => {
    let response = await abrirSessao(lerSegredoDeBoot());
    // Uma janela antiga pode sobreviver ao reinício do servidor. Somente a
    // ponte nativa consegue ler o segredo novo e repetir a abertura da sessão.
    if (response.status === 403) {
      const renovado = await segredoDaJanelaNativa();
      if (renovado) response = await abrirSessao(renovado);
    }
    if (!response.ok) {
      throw new Error(
        response.status === 403
          ? 'Abra o Condor pela janela do aplicativo: esta pagina nao tem o segredo local desta execucao.'
          : 'O servidor recusou a origem local do Condor.',
      );
    }
    return response.json();
  })();

  const bloquearInterface = () => {
    const aplicar = () => {
      document.body.classList.add('condor-session-denied');
      const boot = document.getElementById('coreBoot');
      if (!boot) return;
      boot.classList.remove('done');
      boot.setAttribute('aria-label', 'Condor bloqueado');
      boot.innerHTML = `
        <div class="core-boot-panel">
          <div class="core-boot-brand">CONDOR</div>
          <div class="core-boot-title">ACESSO BLOQUEADO</div>
        </div>`;
    };
    if (document.readyState === 'loading') {
      window.addEventListener('DOMContentLoaded', aplicar, { once: true });
    } else {
      aplicar();
    }
  };
  ready.catch(bloquearInterface);

  window.fetch = (...args) => ready.then(async () => {
    let response = await rawFetch(...args);
    // Também cobre o caso em que o servidor reinicia depois de a tela já estar
    // aberta: o cookie antigo recebe 401, a janela nativa prova sua identidade
    // de novo e a requisição original é repetida uma única vez.
    if (response.status === 401) {
      const renovado = await segredoDaJanelaNativa();
      if (renovado) {
        const sessionResponse = await abrirSessao(renovado);
        if (sessionResponse.ok) response = await rawFetch(...args);
      }
    }
    return response;
  });
  return { ready };
})();
