/**
 * CondorErrors — tela de erros e saúde do sistema.
 */
const CondorErrors = (() => {
  function init() {
    CondorWS.on('health.update', renderHealth);

    // Carrega estado inicial
    fetch('/api/health').then(r => r.json()).then(renderHealth).catch(() => {});

    // Botões de ordenação
    document.querySelectorAll('.sp').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.sp').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });
  }

  function renderHealth(data) {
    // Score e status
    document.getElementById('healthScore').textContent  = data.score ?? '--';
    document.getElementById('healthStatus').textContent =
      `${data.status ?? 'VERIFICANDO'} · ${data.critical ?? 0} crítico(s)`;

    document.getElementById('statCritical').textContent = data.critical ?? 0;
    document.getElementById('statWarning').textContent  = data.warning  ?? 0;

    // Botão de erros no topo
    const total = (data.critical ?? 0) + (data.warning ?? 0);
    document.getElementById('errCount').textContent = total;

    // Lista de erros
    const list   = document.getElementById('errList');
    const errors = data.errors || [];
    list.innerHTML = '';

    if (errors.length === 0) {
      list.innerHTML = `<div style="font-size:12px;color:var(--text-dim);padding:20px 0;">Nenhum erro detectado. O Condor está operando normalmente.</div>`;
      return;
    }

    errors.forEach(err => {
      const isCrit = err.severity === 'critical';
      const card   = document.createElement('div');
      card.className = `err-card ${isCrit ? '' : 'warn'}`;
      card.innerHTML = `
        <div class="err-bar ${isCrit ? '' : 'amb'}"></div>
        <div class="err-head">
          <div class="err-hl">
            <span class="tag ${isCrit ? 'tag-crit' : 'tag-warn'}">${err.severity.toUpperCase()}</span>
            <span class="err-id">${err.id}</span>
            <span class="err-cat">${err.category}</span>
          </div>
          <span class="err-meta">${_ago(err.ts)}</span>
        </div>
        <div class="err-title"><i class="ti ${isCrit ? 'ti-alert-circle' : 'ti-alert-triangle'}"></i> ${_esc(err.title)}</div>
        <div class="err-desc">${_esc(err.description)}</div>
        ${err.detail ? `<div class="code-block">${_esc(err.detail)}</div>` : ''}
        <div class="err-actions">
          <button class="act-btn" onclick="CondorConversation.addMessage('user','Explica o erro ${err.id} e como corrigir');CondorRouter.go('conversacao');CondorWS.sendText('Explica o erro ${err.id}: ${err.title}')">
            <i class="ti ti-bulb"></i> SUGERIR CORREÇÃO
          </button>
          <button class="act-btn ${isCrit ? '' : 'amb'}">
            <i class="ti ti-file-text"></i> VER LOG
          </button>
        </div>`;
      list.appendChild(card);
    });
  }

  function _esc(s) {
    return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function _ago(ts) {
    if (!ts) return '';
    const diff = Math.floor((Date.now() / 1000) - ts);
    if (diff < 60) return 'agora';
    if (diff < 3600) return `${Math.floor(diff / 60)}min`;
    return `${Math.floor(diff / 3600)}h`;
  }

  return { init };
})();
