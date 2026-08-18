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

  const segredo = lerSegredoDeBoot();
  const headers = { 'X-Condor-Client': 'desktop-ui' };
  if (segredo) headers['X-Condor-Token'] = segredo;

  const ready = rawFetch('/api/session', {
    method: 'POST',
    credentials: 'same-origin',
    headers,
  }).then((response) => {
    if (!response.ok) {
      throw new Error(
        response.status === 403
          ? 'Abra o Condor pela janela do aplicativo: esta pagina nao tem o segredo local desta execucao.'
          : 'O servidor recusou a origem local do Condor.',
      );
    }
    return response.json();
  });

  window.fetch = (...args) => ready.then(() => rawFetch(...args));
  return { ready };
})();
