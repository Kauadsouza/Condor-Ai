/**
 * CondorErros — a tela de saúde.
 *
 * Mostra o que está impedindo o Condor de funcionar direito (sem chave da
 * OpenAI, microfone off) e as ações que falharam quando ele tentou mexer no PC.
 */
const CondorErros = (() => {
  const $ = (id) => document.getElementById(id);

  function init() {
    atualizar();
    setInterval(() => {
      if (CondorRouter.atual() === 'erros') atualizar();
    }, 20000);
  }

  async function atualizar() {
    try {
      const response = await fetch('/api/saude', { cache: 'no-store' });
      if (!response.ok) throw new Error(`saúde indisponível (${response.status})`);
      const s = normalizeHealth(await response.json());
      pintarSaude(s);
      pintarLista(s);
      $('errCount').textContent = (s.criticos || 0) + (s.avisos || 0);
    } catch (e) {
      console.warn('[erros] não consegui carregar', e);
    }
  }

  function isExpectedSecurityDenial(action) {
    if (String(action?.ferramenta || '').toLowerCase() !== 'security') return false;
    let result = '';
    let actionName = '';
    try {
      const payload = JSON.parse(String(action?.entrada || ''));
      result = String(payload?.result || '');
      actionName = String(payload?.input || '').trim().toLowerCase();
    } catch (_) {
      result = String(action?.entrada || '');
    }
    const normalized = result.trim().toUpperCase();
    return normalized === 'DENIED' || normalized.startsWith('DENIED:')
      || (actionName === 'face_presence' && normalized.startsWith('BLOQUEADO:'));
  }

  function normalizeHealth(snapshot) {
    const s = { ...(snapshot || {}) };
    const received = Array.isArray(s.falhas) ? s.falhas : [];
    s.falhas = received.filter((action) => !isExpectedSecurityDenial(action));
    const ignored = received.length - s.falhas.length;
    if (ignored) {
      // Compatibilidade com respostas produzidas por nucleos anteriores: eles
      // descontavam ate 20 pontos e somavam ate 9 avisos por recusas normais
      // e por bloqueios biometricos que funcionaram corretamente.
      s.pontos = Math.min(100, Number(s.pontos || 0) + Math.min(20, ignored * 3));
      s.avisos = Math.max(0, Number(s.avisos || 0) - Math.min(9, ignored));
    }
    return s;
  }

  function pintarSaude(s) {
    $('healthScore').textContent = s.pontos ?? '--';
    $('statCritical').textContent = s.criticos ?? 0;
    $('statWarning').textContent = s.avisos ?? 0;
    const p = s.pontos ?? 0;
    $('healthStatus').textContent =
      p >= 90 ? 'TUDO CERTO' : p >= 60 ? 'FUNCIONANDO COM RESSALVAS' : 'PRECISO DE AJUSTE';
  }

  function pintarLista(s) {
    const cartoes = [];

    if (!s.cerebro) {
      cartoes.push(cartao('warn', 'MODO LOCAL', 'CONDOR',
        'Nenhum conector generativo está ativo. Os comandos locais seguros continuam disponíveis.',
        'Desbloqueie o cofre e adicione uma chave opcional se quiser raciocínio generativo.'));
    }
    if (!s.voz_local) {
      cartoes.push(cartao('warn', 'VOZ LOCAL INDISPONÍVEL', 'VOZ',
        'O microfone ou a fala local não estão prontos.',
        'Confira o microfone do Windows e reinicie o Condor para testar os módulos locais.'));
    }

    (s.connector_issues || []).forEach(issue => {
      cartoes.push(cartao(
        issue.level === 'critical' ? 'crit' : 'warn',
        issue.title || 'CONECTOR COM FALHA',
        (issue.provider || 'IA').toUpperCase(),
        issue.detail || 'O teste do conector não terminou corretamente.',
        'Abra Sistema → Conectar IA, confira chave, modelo e provedor ativo, depois salve para testar novamente.'
      ));
    });

    (s.falhas || []).forEach(f => {
      const quando = new Date((f.ts || 0) * 1000)
        .toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      cartoes.push(cartao('warn', 'AÇÃO FALHOU', (f.ferramenta || '').toUpperCase(),
        `${f.entrada || ''}`, '', quando));
    });

    if (!cartoes.length) {
      cartoes.push(`<div class="err-card" style="border-color:rgba(94,234,212,.2)">
        <div class="err-title">Nenhum problema. Tudo rodando.</div>
        <div class="err-desc">${escapar((s.sistema || '').split('\n')[0] || '')}</div>
      </div>`);
    }
    $('errList').innerHTML = cartoes.join('');
  }

  function cartao(nivel, titulo, categoria, descricao, comoResolver, quando) {
    const critico = nivel === 'crit';
    return `
      <div class="err-card ${critico ? '' : 'warn'}">
        <div class="err-bar ${critico ? '' : 'amb'}"></div>
        <div class="err-head">
          <div class="err-hl">
            <span class="tag ${critico ? 'tag-crit' : 'tag-warn'}">${critico ? 'CRÍTICO' : 'AVISO'}</span>
            <span class="err-cat">${escapar(categoria)}</span>
          </div>
          ${quando ? `<span class="err-meta">${quando}</span>` : ''}
        </div>
        <div class="err-title">${escapar(titulo)}</div>
        <div class="err-desc">${escapar(descricao)}</div>
        ${comoResolver ? `<div class="code-block">${escapar(comoResolver)}</div>` : ''}
      </div>`;
  }

  function escapar(t) {
    const d = document.createElement('div');
    d.textContent = t == null ? '' : String(t);
    return d.innerHTML;
  }

  return { init, atualizar };
})();
