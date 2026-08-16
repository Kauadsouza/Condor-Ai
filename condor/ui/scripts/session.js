/** Sessao local HttpOnly. O segredo nunca fica disponivel ao JavaScript. */
const CondorSession = (() => {
  const rawFetch = window.fetch.bind(window);
  const ready = rawFetch('/api/session', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-Condor-Client': 'desktop-ui' },
  }).then((response) => {
    if (!response.ok) throw new Error('O servidor recusou a origem local do Condor.');
    return response.json();
  });

  window.fetch = (...args) => ready.then(() => rawFetch(...args));
  return { ready };
})();
