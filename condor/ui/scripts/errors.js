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
      const s = await fetch('/api/saude').then(r => r.json());
      pintarSaude(s);
      pintarLista(s);
      $('errCount').textContent = (s.criticos || 0) + (s.avisos || 0);
    } catch (e) {
      console.warn('[erros] não consegui carregar', e);
    }
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
    if (!s.escuta) {
      cartoes.push(cartao('warn', 'ESCUTA DESLIGADA', 'VOZ',
        s.motivo_escuta || 'O detector de voz não subiu.',
        'Adicione a chave opcional ao cofre e um arquivo condor*.ppn em ~/.condor/wake.'));
    }

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
