/**
 * CondorConversation — gerencia balões de chat e streaming de tokens.
 */
const CondorConversation = (() => {
  let turnCount  = 0;
  let tokenCount = 0;
  let aiEl       = null;    // elemento do balão atual do assistente
  let _muted     = false;

  // ── Renderiza texto com formatação básica ────────────────────────────────
  function _renderText(el, text) {
    // Remove blocos ◆ do display (código executado não aparece no balão)
    const clean = text.replace(/◆\w+:[\s\S]*?(?=◆|$)/g, '').trim();
    el.textContent = clean || text;
  }

  // ── Cria um balão de mensagem ────────────────────────────────────────────
  function addMessage(role, text) {
    const wrap = document.getElementById('chatWrap');

    const row = document.createElement('div');
    row.className = 'msg-row';

    const bubble = document.createElement('div');
    bubble.className = `msg-bubble ${role === 'user' ? 'msg-user' : 'msg-ai'}`;

    // Label com horário
    const lbl = document.createElement('div');
    lbl.className = 'msg-lbl';
    const now = new Date();
    const ts  = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`;
    lbl.style.color     = role === 'user' ? 'var(--violet-soft)' : 'var(--cyan)';
    lbl.style.textAlign = role === 'user' ? 'right' : 'left';
    lbl.textContent     = role === 'user' ? `VOCÊ · ${ts}` : `CONDOR · ${ts}`;

    const txt = document.createElement('div');
    txt.className = 'msg-text';
    if (text) _renderText(txt, text);

    bubble.appendChild(lbl);
    bubble.appendChild(txt);
    row.appendChild(bubble);
    wrap.appendChild(row);
    wrap.scrollTop = wrap.scrollHeight;

    if (role === 'assistant') aiEl = txt;
    return txt;
  }

  // ── Streaming de tokens ──────────────────────────────────────────────────
  let _streamRaw = '';   // texto cru acumulado durante streaming

  function appendToken(token) {
    if (!aiEl) {
      aiEl = addMessage('assistant', '');
      aiEl.classList.add('streaming');
      _streamRaw = '';
    }
    _streamRaw += token;
    tokenCount += token.length;

    // Mostra texto sem os blocos ◆ durante o streaming
    const visible = _streamRaw.replace(/◆\w+:[\s\S]*?(?=◆|$)/g, '').trim();
    aiEl.textContent = visible || _streamRaw;

    document.getElementById('chatWrap').scrollTop =
      document.getElementById('chatWrap').scrollHeight;
  }

  function startAiMessage() {
    aiEl = null;
    _streamRaw = '';
    document.getElementById('typingIndicator').style.display = 'block';
  }

  function finishAiMessage() {
    document.getElementById('typingIndicator').style.display = 'none';

    // Remove cursor piscante e render final limpo
    if (aiEl) {
      aiEl.classList.remove('streaming');
      if (_streamRaw) _renderText(aiEl, _streamRaw);
    }

    turnCount++;
    document.getElementById('tokenCount').textContent =
      `${tokenCount.toLocaleString()} tokens · ${turnCount} turnos`;
    aiEl = null;
    _streamRaw = '';
  }

  // ── Botão de mudo ────────────────────────────────────────────────────────
  function setupMuteBtn() {
    const btn = document.getElementById('muteBtn');
    if (!btn) return;
    btn.addEventListener('click', () => {
      _muted = !_muted;
      btn.textContent = _muted ? '🔇' : '🔊';
      btn.style.borderColor = _muted ? 'rgba(244,114,182,0.5)' : 'rgba(255,255,255,0.2)';
    });
  }
  setupMuteBtn();

  // ── Campo de texto ───────────────────────────────────────────────────────
  function setupTextInput() {
    const input = document.getElementById('textInput');
    const btn   = document.getElementById('sendBtn');
    if (!input || !btn) return;

    function send() {
      const text = input.value.trim();
      if (!text) return;
      addMessage('user', text);
      CondorWS.sendText(text);
      input.value = '';
    }

    btn.addEventListener('click', send);
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); send(); }
    });
  }
  setupTextInput();

  // ── Handlers WebSocket ───────────────────────────────────────────────────
  CondorWS.on('stt.final', msg => {
    if (msg.text && msg.text.trim()) addMessage('user', msg.text);
  });

  CondorWS.on('llm.token', msg => {
    if (!aiEl) startAiMessage();
    appendToken(msg.token);
  });

  CondorWS.on('llm.done', () => {
    finishAiMessage();
  });

  CondorWS.on('action.executing', msg => {
    addMessage('assistant', `⚙️  Executando: ${msg.action}…`);
  });

  CondorWS.on('action.result', msg => {
    if (msg.result?.result) {
      addMessage('assistant', `✓ ${msg.result.result}`);
    }
  });

  // Resultado do executor ◆ (CMD, PY, READ, WRITE, GET, PIP)
  CondorWS.on('exec.result', msg => {
    if (!msg.output) return;
    const wrap = document.getElementById('chatWrap');
    const row  = document.createElement('div');
    row.className = 'msg-row';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble msg-ai';
    bubble.style.background   = 'rgba(0,200,120,0.06)';
    bubble.style.borderColor  = 'rgba(0,200,120,0.2)';

    const lbl = document.createElement('div');
    lbl.className   = 'msg-lbl';
    lbl.style.color = '#00c878';
    lbl.textContent = '⚙ EXECUÇÃO';

    const pre = document.createElement('pre');
    pre.style.cssText = [
      'margin:6px 0 0',
      'font-size:11px',
      'white-space:pre-wrap',
      'word-break:break-all',
      'color:#a0ffca',
      'font-family:monospace',
      'max-height:220px',
      'overflow-y:auto',
      'line-height:1.5',
    ].join(';');
    pre.textContent = msg.output;

    bubble.appendChild(lbl);
    bubble.appendChild(pre);
    row.appendChild(bubble);
    wrap.appendChild(row);
    wrap.scrollTop = wrap.scrollHeight;
  });

  return { addMessage };
})();
