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
  let historicoCarregado = false;
  let avisoTimer = null;
  let turnoAtivo = null;
  let conectado = false;
  const fila = [];
  const LIMITE_FILA = 20;

  function init() {
    CondorWS.ao('ws.ligado', () => { conectado=true; });
    CondorWS.ao('ws.caiu', () => {
      conectado=false; fila.length=0; turnoAtivo=null; fecharBolha(); mostrarDigitando(false); atualizarFila();
      mostrarAviso('CONEXÃO INTERROMPIDA · A FILA NÃO SERÁ REENVIADA', true);
      CondorVoz.stopForSecurity();
    });
    const campo = $('textInput');
    const botao = $('sendBtn');
    const limpar = $('clearChatBtn');
    const dialogo = $('clearChatDialog');
    const confirmarLimpeza = $('confirmClearChatBtn');

    const enviar = () => {
      const texto = campo.value.trim();
      if (!texto) return;
      if (!conectado) { mostrarAviso('AGUARDE A CONEXÃO · SEU TEXTO FOI PRESERVADO',true); return; }
      campo.value = '';
      solicitarEnvio(texto);
    };

    botao.addEventListener('click', enviar);
    limpar.addEventListener('click', () => {
      const mensagem = $('clearChatDialogMessage');
      const total = area().querySelectorAll('.msg-row').length;
      mensagem.textContent = `${total ? `${total} mensagem${total === 1 ? '' : 's'}` : 'Nenhuma mensagem'} nesta conversa. Memórias aprendidas, projetos e configurações continuarão salvos.`;
      mensagem.classList.remove('error');
      confirmarLimpeza.disabled = false; confirmarLimpeza.textContent = 'LIMPAR E COMEÇAR';
      if (!dialogo.open) dialogo.showModal();
    });
    confirmarLimpeza.addEventListener('click', limparHistorico);
    campo.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(); }
    });
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'l') {
        e.preventDefault(); limpar.click();
      }
    });

    CondorWS.ao('transcricao', (m) => {
      if (!turnoAtivo) turnoAtivo = { texto: m.texto, tipo: 'voz' };
      adicionarUsuario(m.texto); mostrarDigitando(true); atualizarFila();
    });
    CondorWS.ao('conversa.historico', carregarHistorico);
    CondorWS.ao('conversa.limpa', limparTela);
    CondorWS.ao('resposta.token', (m) => acrescentar(m.texto));
    CondorWS.ao('resposta.fim', (m) => {
      finalizar(m.texto, m.fontes || []); concluirTurno();
    });
    CondorWS.ao('ferramenta.inicio', (m) => acaoIniciou(m));
    CondorWS.ao('ferramenta.fim', (m) => acaoTerminou(m));
    CondorWS.ao('erro', (m) => {
      finalizar(m.mensagem || 'Deu ruim aqui.'); concluirTurno();
    });
    // O servidor recusa um pedido novo enquanto termina o anterior. Sem isto a
    // mensagem digitada sumia da tela sem explicacao nenhuma.
    CondorWS.ao('ocupado', (m) => {
      finalizar(m.mensagem || 'Ainda estou no pedido anterior.'); concluirTurno();
    });
    CondorWS.ao('dormiu', () => { marcarSessao('DORMIU'); fecharBolha(); });
    CondorWS.ao('acordou', () => marcarSessao('ACORDOU'));
  }

  // ── Bolhas ────────────────────────────────────────────────────────────

  function area() { return $('chatWrap'); }

  // ── Fila de turnos ───────────────────────────────────────────────────

  function solicitarEnvio(texto) {
    if (!conectado) { mostrarAviso('SEM CONEXÃO COM O NÚCLEO',true); return; }
    const item = { texto: String(texto || '').trim(), tipo: 'texto' };
    if (!item.texto) return;
    if (turnoAtivo) {
      if (fila.length >= LIMITE_FILA) {
        mostrarAviso(`FILA CHEIA · LIMITE DE ${LIMITE_FILA} MENSAGENS`, true);
        return;
      }
      fila.push(item);
      atualizarFila();
      mostrarAviso(`${fila.length} MENSAGEM${fila.length === 1 ? '' : 'S'} NA FILA`);
      return;
    }
    despacharTurno(item);
  }

  function despacharTurno(item) {
    turnoAtivo = item;
    atualizarFila();
    adicionarUsuario(item.texto);
    const mediaTask = typeof CondorMedia !== 'undefined'
      ? CondorMedia.handleChatPrompt(item.texto)
      : null;
    if (mediaTask) {
      Promise.resolve(mediaTask).finally(concluirTurno);
      return;
    }
    CondorWS.mandarTexto(item.texto);
    mostrarDigitando(true);
    CondorPet.setState('thinking');
  }

  function concluirTurno() {
    if (!turnoAtivo) return;
    turnoAtivo = null;
    atualizarFila();
    queueMicrotask(() => {
      if (turnoAtivo || !fila.length) return;
      despacharTurno(fila.shift());
    });
  }

  function atualizarFila() {
    const status = $('chatQueueStatus');
    const compose = $('chatCompose');
    const botao = $('sendBtn');
    const campo = $('textInput');
    const total = fila.length;
    if (status) {
      status.hidden = total === 0;
      status.textContent = total
        ? `FILA · ${total} MENSAGEM${total === 1 ? '' : 'S'} · ENVIO AUTOMÁTICO`
        : '';
    }
    compose?.classList.toggle('has-queue', total > 0);
    if (botao) botao.textContent = turnoAtivo ? 'COLOCAR NA FILA' : 'ENVIAR';
    if (campo) campo.placeholder = turnoAtivo
      ? 'digite a próxima mensagem — ela será enviada na ordem...'
      : 'converse, peça uma imagem ou descreva o que quer analisar...';
  }

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
    atualizarPresenca();
    rolar();
  }

  function adicionarCondor(texto) {
    abrirBolhaCondor();
    textoAtual = String(texto || '');
    bolhaAtual.textContent = textoAtual;
    fecharBolha();
    atualizarPresenca();
    CondorPet.setState('happy', 1200);
  }

  function adicionarMidia(imageUrl, caption, kind = 'image') {
    const linha = document.createElement('div');
    linha.className = 'msg-row';
    const figure = document.createElement('figure');
    figure.className = `msg-media msg-${kind}`;
    const image = document.createElement('img'); image.src = imageUrl; image.alt = caption || 'Imagem no chat do Condor';
    const text = document.createElement('figcaption'); text.textContent = caption || '';
    figure.append(image, text); linha.appendChild(figure); area().appendChild(linha);
    atualizarPresenca(); rolar(); CondorPet.setState('happy', 1800);
    return figure;
  }

  function adicionarCarregando(texto = 'CRIANDO IMAGEM') {
    const linha = document.createElement('div'); linha.className = 'msg-row';
    const card = document.createElement('div'); card.className = 'msg-media loading'; card.textContent = texto;
    linha.appendChild(card); area().appendChild(linha); atualizarPresenca(); rolar();
    return linha;
  }

  function carregarHistorico(mensagem) {
    if (historicoCarregado) return;
    const itens = Array.isArray(mensagem.mensagens) ? mensagem.mensagens : [];
    if (!itens.length) return;
    historicoCarregado = true;
    itens.forEach((item) => {
      if (item.role === 'user') adicionarUsuario(item.content || '');
      else if (item.role === 'assistant') adicionarCondor(item.content || '');
    });
    marcarSessao('AGORA');
    atualizarPresenca();
  }

  function limparTela() {
    mostrarDigitando(false);
    fecharBolha();
    area().querySelectorAll('.msg-row').forEach((item) => item.remove());
    const marcas = [...area().querySelectorAll('.session-mark')];
    marcas.slice(1).forEach((item) => item.remove());
    const hora = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    const rotulo = marcas[0]?.querySelector('.lbl');
    if (rotulo) rotulo.textContent = `NOVA CONVERSA · ${hora}`;
    historicoCarregado = true;
    fila.splice(0, fila.length);
    atualizarFila();
    atualizarPresenca();
    $('textInput').focus();
    CondorPet.setState('happy', 1000);
  }

  async function limparHistorico() {
    const dialogo = $('clearChatDialog'); const confirmar = $('confirmClearChatBtn');
    const mensagem = $('clearChatDialogMessage');
    confirmar.disabled = true; confirmar.textContent = 'LIMPANDO...'; mensagem.classList.remove('error');
    try {
      await CondorSession.ready;
      const response = await fetch('/api/conversa/historico', { method: 'DELETE', cache: 'no-store' });
      const data = await response.json();
      if (response.status === 404) throw new Error('O núcleo do Condor precisa ser reiniciado para ativar esta função.');
      if (!response.ok) throw new Error(data.erro || 'Não foi possível limpar o chat agora.');
      limparTela();
      dialogo.close();
      mostrarAviso('NOVA CONVERSA INICIADA');
    } catch (error) {
      mensagem.textContent = error.message || 'Não foi possível limpar o chat agora.';
      mensagem.classList.add('error');
    } finally {
      confirmar.disabled = false; confirmar.textContent = 'LIMPAR E COMEÇAR';
    }
  }

  function mostrarAviso(texto, erro = false) {
    const aviso = $('chatNotice');
    if (avisoTimer) clearTimeout(avisoTimer);
    aviso.textContent = texto; aviso.classList.toggle('error', erro); aviso.classList.add('show');
    avisoTimer = setTimeout(() => aviso.classList.remove('show'), 2600);
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
    CondorPet.setState('speaking');
    rolar();
  }

  function finalizar(texto, fontes = []) {
    mostrarDigitando(false);
    // Quando o modelo usou ferramentas, o texto do meio não vira resposta —
    // o que vale é o texto final que o servidor manda aqui.
    if (texto && texto !== textoAtual) {
      abrirBolhaCondor();
      textoAtual = texto;
      bolhaAtual.textContent = texto;
    }
    mostrarFontes(fontes);
    fecharBolha();
    atualizarPresenca();
    CondorPet.setState('happy', 1400);
  }

  function mostrarFontes(fontes) {
    if (!bolhaAtual || !Array.isArray(fontes) || !fontes.length) return;
    const host = document.createElement('div');
    host.className = 'msg-sources';
    const label = document.createElement('span');
    label.textContent = 'FONTES';
    host.appendChild(label);
    fontes.slice(0, 8).forEach((source, index) => {
      try {
        const url = new URL(String(source.url || ''));
        if (!['http:', 'https:'].includes(url.protocol)) return;
        const link = document.createElement('a');
        link.href = url.href;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = `${index + 1} · ${String(source.title || url.hostname).slice(0, 100)}`;
        link.title = url.href;
        host.appendChild(link);
      } catch (_) { /* fonte invalida e ignorada */ }
    });
    if (host.querySelector('a')) bolhaAtual.parentElement.appendChild(host);
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
    // O id da chamada é o que casa início e fim. Sem ele, duas ferramentas
    // iguais rodando em paralelo fechariam a linha errada.
    linha.dataset.id = m.id || '';
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
    let alvo = m.id
      ? blocoAcoes.querySelector(`.acao-linha[data-id="${CSS.escape(m.id)}"]`)
      : null;
    if (!alvo) {
      const iguais = blocoAcoes.querySelectorAll(
        `.acao-linha[data-ferramenta="${CSS.escape(m.ferramenta)}"]:not(.ok):not(.falhou)`);
      alvo = iguais[0];
    }
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
    if (ligado) CondorPet.setState('thinking');
  }

  function atualizarPresenca() {
    CondorPet.messageCount(area().querySelectorAll('.msg-row').length);
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

  return {
    init, adicionarUsuario, adicionarCondor, adicionarMidia, adicionarCarregando,
    mostrarAviso, marcarSessao, solicitarEnvio,
  };
})();
