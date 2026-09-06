/** Geracao de imagens local pedida naturalmente no chat. */
const CondorMedia = (() => {
  let pendingIntent = null;
  const $ = (id) => document.getElementById(id);

  async function api(url, options = {}) {
    await CondorSession.ready;
    const response = await fetch(url, { cache: 'no-store', ...options });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.erro || 'Operacao de midia indisponivel.');
      error.data = data; error.status = response.status; throw error;
    }
    return data;
  }

  async function ensurePermission(capability, reason, source, options = {}) {
    const data = await api('/api/permissions/request', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        capability, reason, source,
        require_persistent: options.requireAlways === true,
      }),
    });
    if (data.allowed) return true;
    CondorRouter.ir('sistema');
    await CondorCoreUI.loadStatus();
    CondorConversa.mostrarAviso('ESCOLHA BLOQUEAR, SÓ UMA VEZ OU SEMPRE PERMITIR');
    return false;
  }

  async function generateImage(prompt, permissionConfirmed = false) {
    let loading = null;
    try {
      if (!permissionConfirmed && !await ensurePermission(
        'ai_media', 'Gerar esta imagem inteiramente neste PC.', 'chat_image_generation',
      )) {
        return await new Promise((resolve) => {
          pendingIntent = { type: 'image', prompt, resolve };
        });
      }
      pendingIntent = null;
      loading = CondorConversa.adicionarCarregando('CONDOR ESTÁ CRIANDO A IMAGEM');
      CondorPet.setState('thinking');
      const result = await api('/api/media/images/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, size: '1024x1024', quality: 'high' }),
      });
      loading.remove();
      CondorConversa.adicionarMidia(
        `data:${result.mime_type};base64,${result.image_b64}`,
        `${prompt} · ${result.model}`,
        'generated',
      );
    } catch (error) {
      loading?.remove();
      CondorConversa.adicionarCondor(`Não consegui gerar a imagem agora: ${error.message}`);
      CondorPet.setState('error', 2600);
    }
  }

  function normalize(text) {
    return String(text || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  function imageIntent(text) {
    return /\b(cria|crie|criar|gera|gere|gerar|faz|faca|fazer|produza|produzir|desenha|desenhe)\b[^.!?]*\b(img|imagem|imagens|foto|fotografia|ilustracao|arte|desenho|poster|capa|thumbnail)\b/
      .test(normalize(text));
  }

  function extractImagePrompt(text) {
    const stripped = String(text).replace(
      /^\s*(?:condor[, ]+)?(?:cria|crie|criar|gera|gere|gerar|faz|faça|fazer|produza|produzir|desenha|desenhe)\s+(?:para mim\s+)?(?:uma?s?\s+)?(?:img|imagem|imagens|foto|fotografia|ilustra(?:ção|cao)|arte|desenho|poster|capa|thumbnail)\s*(?:de|do|da|com|:|-)?\s*/i,
      '',
    ).trim();
    return stripped || String(text).trim();
  }

  function handleChatPrompt(text) {
    if (imageIntent(text)) {
      return generateImage(extractImagePrompt(text));
    }
    return null;
  }

  async function permissionResolved(event) {
    if (!pendingIntent) return;
    if (event.detail?.capability !== 'ai_media') return;
    const intent = pendingIntent;
    if (event.detail.decision === 'block') {
      pendingIntent = null;
      CondorConversa.adicionarCondor('Permissão bloqueada. Não executei essa ação.');
      intent.resolve();
      return;
    }
    pendingIntent = null;
    if (intent.type === 'image') await generateImage(intent.prompt, true);
    intent.resolve();
  }

  function init() {
    window.addEventListener('condor-permission-resolved', permissionResolved);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
  return { ensurePermission, handleChatPrompt };
})();
