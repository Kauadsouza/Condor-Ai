/** Entrega o endereço e o código da visualização móvel apenas à sessão local. */
(() => {
  const button = document.getElementById('mobileAccessBtn');
  const modal = document.getElementById('mobileAccessModal');
  const close = document.getElementById('mobileAccessClose');
  const url = document.getElementById('mobileAccessUrl');
  const code = document.getElementById('mobileAccessCode');
  const error = document.getElementById('mobileAccessError');

  if (!button) return;

  async function open() {
    modal.hidden = false;
    error.textContent = '';
    url.textContent = 'carregando...';
    code.textContent = '--------';
    try {
      const response = await fetch('/api/mobile/access', { cache: 'no-store' });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.erro || 'Acesso móvel indisponível');
      url.textContent = payload.url || 'Rede Wi-Fi privada não encontrada';
      code.textContent = payload.code;
    } catch (failure) {
      error.textContent = failure.message;
    }
  }

  async function copyValue(kind, copyButton) {
    const value = kind === 'url' ? url.textContent : code.textContent;
    if (!value || value.includes('carregando') || value.includes('não encontrada')) return;
    try {
      await navigator.clipboard.writeText(value);
      const previous = copyButton.textContent;
      copyButton.textContent = 'COPIADO';
      setTimeout(() => { copyButton.textContent = previous; }, 1200);
    } catch {
      error.textContent = 'Não consegui copiar. Selecione o valor manualmente.';
    }
  }

  button.addEventListener('click', open);
  close.addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (event) => {
    if (event.target === modal) modal.hidden = true;
  });
  document.querySelectorAll('[data-copy-mobile]').forEach((copyButton) => {
    copyButton.addEventListener('click', () => copyValue(copyButton.dataset.copyMobile, copyButton));
  });
})();
