/**
 * CondorConversa — as bolhas da tela de conversação.
 *
 * Fluxo de um turno por voz:
 *   transcricao      → bolha do usuário
 *   ferramenta.*     → linhas de ação dentro da bolha do Condor
 *   resposta.token   → texto vai aparecendo letra a letra
 *   resposta.fim     → fecha a bolha
 */
const CondorConversa = (() => {
  const $ = (id) => document.getElementById(id);
  let bolhaAtual = null;
  let textoAtual = '';
  let blocoAcoes = null;

  function init() {
    const campo = $('textInput');
    const botao = $('sendBtn');

    const enviar = () => {
      const texto = campo.value.trim();
      if (!texto) return;
      adicionarUsuario(texto);
      CondorWS.mandarTexto(texto);
      campo.value = '';
      mostrarDigitando(true);
    };

    botao.addEventListener('click', enviar);
    campo.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(); }
    });

    CondorWS.ao('transcricao', (m) => { adicionarUsuario(m.texto); mostrarDigitando(true); });
    CondorWS.ao('resposta.token', (m) => acrescentar(m.texto));
    CondorWS.ao('resposta.fim', (m) => finalizar(m.texto));
    CondorWS.ao('ferramenta.inicio', (m) => acaoIniciou(m));
    CondorWS.ao('ferramenta.fim', (m) => acaoTerminou(m));
    CondorWS.ao('erro', (m) => finalizar(m.mensagem || 'Deu ruim aqui.'));
    CondorWS.ao('dormiu', () => { marcarSessao('DORMIU'); fecharBolha(); });
    CondorWS.ao('acordou', () => marcarSessao('ACORDOU'));
  }

  // ── Bolhas ────────────────────────────────────────────────────────────

  function area() { return $('chatWrap'); }

  function rolar() {
    const a = area();
    a.scrollTop = a.scrollHeight;
  }

  function adicionarUsuario(texto) {
    const linha = document.createElement('div');
    linha.className = 'msg-row';
    linha.innerHTML = `
      <div class="msg-bubble msg-user">
        <div class="msg-lbl" style="color:var(--violet-soft);">VOCÊ</div>
        <div class="msg-text"></div>
      </div>`;
    linha.querySelector('.msg-text').textContent = texto;
    area().appendChild(linha);
    rolar();
  }

  function abrirBolhaCondor() {
    if (bolhaAtual) return;
    const linha = document.createElement('div');
    linha.className = 'msg-row';
    linha.innerHTML = `
      <div class="msg-bubble msg-ai">
        <div class="msg-lbl" style="color:var(--cyan);">CONDOR</div>
        <div class="acoes"></div>
        <div class="msg-text streaming"></div>
      </div>`;
    area().appendChild(linha);
    bolhaAtual = linha.querySelector('.msg-text');
    blocoAcoes = linha.querySelector('.acoes');
    textoAtual = '';
    rolar();
  }

  function acrescentar(pedaco) {
    mostrarDigitando(false);
    abrirBolhaCondor();
    textoAtual += pedaco;
    bolhaAtual.textContent = textoAtual;
    rolar();
  }

  function finalizar(texto) {
    mostrarDigitando(false);
    // Quando o modelo usou ferramentas, o texto do meio não vira resposta —
    // o que vale é o texto final que o servidor manda aqui.
    if (texto && texto !== textoAtual) {
      abrirBolhaCondor();
      textoAtual = texto;
      bolhaAtual.textContent = texto;
    }
    fecharBolha();
  }

  function fecharBolha() {
    if (bolhaAtual) bolhaAtual.classList.remove('streaming');
    bolhaAtual = null;
    blocoAcoes = null;
    textoAtual = '';
    rolar();
  }

  // ── Ações (ferramentas) ───────────────────────────────────────────────

  function acaoIniciou(m) {
    mostrarDigitando(false);
    abrirBolhaCondor();
    const linha = document.createElement('div');
    linha.className = 'acao-linha';
    linha.dataset.ferramenta = m.ferramenta;
    linha.innerHTML = `
      <span class="acao-ponto"></span>
      <span class="acao-nome">${escapar(m.rotulo || m.ferramenta)}</span>
      <span class="acao-arg">${escapar(m.argumentos || '')}</span>`;
    blocoAcoes.appendChild(linha);
    rolar();
  }

  function acaoTerminou(m) {
    if (!blocoAcoes) return;
    const linhas = blocoAcoes.querySelectorAll(
      `.acao-linha[data-ferramenta="${CSS.escape(m.ferramenta)}"]`);
    const alvo = linhas[linhas.length - 1];
    if (!alvo) return;
    alvo.classList.add(m.ok ? 'ok' : 'falhou');
    alvo.querySelector('.acao-ponto').textContent = m.ok ? '✓' : '✕';
    if (!m.ok && m.saida) {
      alvo.querySelector('.acao-arg').textContent = m.saida.slice(0, 120);
    }
  }

  // ── Auxiliares ────────────────────────────────────────────────────────

  function mostrarDigitando(ligado) {
    $('typingIndicator').style.display = ligado ? 'block' : 'none';
  }

  function marcarSessao(rotulo) {
    const marca = document.createElement('div');
    marca.className = 'session-mark';
    const hora = new Date().toLocaleTimeString('pt-BR',
      { hour: '2-digit', minute: '2-digit' });
    marca.innerHTML = `<div class="line"></div>
      <span class="lbl">${rotulo} · ${hora}</span><div class="line"></div>`;
    area().appendChild(marca);
    rolar();
  }

  function escapar(t) {
    const d = document.createElement('div');
    d.textContent = t == null ? '' : String(t);
    return d.innerHTML;
  }

  return { init, adicionarUsuario, marcarSessao };
})();
