/** CondorCell — painel local da mente privada compartilhada com o celular. */
const CondorCell = (() => {
  let conversationId = '';
  let busy = false;

  const el = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  })[char]);

  async function api(path, options = {}) {
    await CondorSession.ready;
    const response = await fetch(path, {
      cache: 'no-store',
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.erro || 'Condor Cloud indisponível.');
    return data;
  }

  function setState(text, online = false) {
    const state = el('cellState');
    state?.classList.toggle('online', online);
    const label = state?.querySelector('span');
    if (label) label.textContent = text;
  }

  function setSetupMessage(text, error = false) {
    const message = el('cellSetupMessage');
    if (!message) return;
    message.textContent = text;
    message.classList.toggle('error', error);
  }

  function showConnected(connected) {
    el('cellSetup').hidden = connected;
    el('cellConnected').hidden = !connected;
    el('cellSync').disabled = !connected || busy;
    el('cellLogout').hidden = !connected;
  }

  function renderMessages(messages = []) {
    const stream = el('cellChatStream');
    if (!stream) return;
    if (!messages.length) {
      stream.innerHTML = '<div class="cell-empty"><strong>MESMA MENTE</strong>O que você conversar aqui também poderá aparecer no celular.</div>';
      return;
    }
    stream.innerHTML = messages.map((item) => `
      <article class="cell-bubble ${item.role === 'user' ? 'user' : ''}">
        <small>${item.role === 'user' ? 'VOCÊ' : 'CONDOR'}</small>
        <p>${escapeHtml(item.content)}</p>
      </article>`).join('');
    stream.scrollTop = stream.scrollHeight;
  }

  function renderNotes(notes = []) {
    const list = el('cellNotesList');
    if (!list) return;
    el('cellNotesCount').textContent = `${notes.length} ${notes.length === 1 ? 'NOTA' : 'NOTAS'}`;
    list.innerHTML = notes.length ? notes.map((note) => `
      <article class="cell-note">
        <small>${escapeHtml(new Date(note.updatedAt || note.createdAt).toLocaleString('pt-BR'))}</small>
        <h3>${escapeHtml(note.title)}</h3><p>${escapeHtml(note.body)}</p>
      </article>`).join('') : '<div class="cell-empty">Nenhuma anotação compartilhada.</div>';
  }

  async function loadCloudData() {
    const [history, notes] = await Promise.all([
      api(`/api/cloud/history${conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : ''}`),
      api('/api/cloud/notes'),
    ]);
    conversationId = history.conversationId || conversationId || '';
    el('cellConversationLabel').textContent = conversationId ? 'SINCRONIZADA' : 'NOVA CONVERSA';
    renderMessages(history.messages || []);
    renderNotes(notes.notes || []);
  }

  async function atualizar() {
    try {
      const status = await api('/api/cloud/status');
      const connected = Boolean(status.configured && status.authenticated);
      showConnected(connected);
      setState(connected ? (status.last_error ? 'CONEXÃO INTERROMPIDA' : 'MENTE CONECTADA') : 'NÃO CONECTADO', connected && !status.last_error);
      if (status.api_url) el('cellApiUrl').value = status.api_url;
      if (status.supabase_url) el('cellSupabaseUrl').value = status.supabase_url;
      if (status.supabase_publishable_key) el('cellSupabaseKey').value = status.supabase_publishable_key;
      if (connected) await loadCloudData();
    } catch (error) {
      showConnected(false);
      setState('INDISPONÍVEL');
      setSetupMessage(error.message, true);
    }
  }

  async function connect(event) {
    event.preventDefault();
    if (busy) return;
    busy = true;
    const button = el('cellConnect');
    button.disabled = true;
    setSetupMessage('CONECTANDO E SINCRONIZANDO...');
    try {
      await api('/api/cloud/configure', {
        method: 'POST',
        body: JSON.stringify({
          api_url: el('cellApiUrl').value.trim(),
          supabase_url: el('cellSupabaseUrl').value.trim(),
          supabase_publishable_key: el('cellSupabaseKey').value.trim(),
          email: el('cellEmail').value.trim(),
          password: el('cellPassword').value,
          interval_seconds: 30,
        }),
      });
      el('cellPassword').value = '';
      el('cellSupabaseKey').value = '';
      setSetupMessage('CONECTADO. A MESMA MENTE ESTÁ ATIVA.');
      showConnected(true);
      setState('MENTE CONECTADA', true);
      await loadCloudData();
    } catch (error) {
      el('cellPassword').value = '';
      setSetupMessage(error.message, true);
    } finally {
      busy = false;
      button.disabled = false;
    }
  }

  async function sync() {
    if (busy) return;
    busy = true; el('cellSync').disabled = true; setState('SINCRONIZANDO...');
    try {
      await api('/api/cloud/sync', { method: 'POST' });
      await loadCloudData(); setState('MENTE SINCRONIZADA', true);
    } catch (error) { setState('FALHA NA SINCRONIZAÇÃO'); setSetupMessage(error.message, true); }
    finally { busy = false; el('cellSync').disabled = false; }
  }

  async function send(event) {
    event.preventDefault();
    const input = el('cellChatInput');
    const message = input.value.trim();
    if (!message || busy) return;
    busy = true; el('cellSend').disabled = true; input.value = ''; setState('CONDOR PENSANDO...');
    const stream = el('cellChatStream');
    if (stream.querySelector('.cell-empty')) stream.innerHTML = '';
    stream.insertAdjacentHTML('beforeend', `<article class="cell-bubble user"><small>VOCÊ</small><p>${escapeHtml(message)}</p></article><article class="cell-bubble" id="cellThinking"><small>CONDOR</small><p>Pensando...</p></article>`);
    stream.scrollTop = stream.scrollHeight;
    try {
      const result = await api('/api/cloud/chat', { method: 'POST', body: JSON.stringify({ message, conversation_id: conversationId }) });
      conversationId = result.conversationId || conversationId;
      el('cellThinking').querySelector('p').textContent = result.answer || 'Resposta concluída no Condor Cloud.';
      await loadCloudData(); setState('MENTE SINCRONIZADA', true);
    } catch (error) {
      const thinking = el('cellThinking'); if (thinking) thinking.querySelector('p').textContent = `Falha: ${error.message}`;
      setState('CONEXÃO INTERROMPIDA');
    } finally { busy = false; el('cellSend').disabled = false; input.focus(); }
  }

  async function createNote(event) {
    event.preventDefault();
    const title = el('cellNoteTitle').value.trim();
    const body = el('cellNoteBody').value.trim();
    if (!title || !body || busy) return;
    busy = true;
    try {
      await api('/api/cloud/notes', { method: 'POST', body: JSON.stringify({ title, body }) });
      el('cellNoteTitle').value = ''; el('cellNoteBody').value = '';
      const notes = await api('/api/cloud/notes'); renderNotes(notes.notes || []); setState('NOTA SINCRONIZADA', true);
    } catch (error) { setState('NOTA NÃO SINCRONIZADA'); setSetupMessage(error.message, true); }
    finally { busy = false; }
  }

  async function logout() {
    if (busy) return;
    busy = true;
    try { await api('/api/cloud/logout', { method: 'POST' }); conversationId = ''; renderMessages([]); renderNotes([]); showConnected(false); setState('NÃO CONECTADO'); }
    catch (error) { setSetupMessage(error.message, true); }
    finally { busy = false; }
  }

  function init() {
    el('cellSetupForm')?.addEventListener('submit', connect);
    el('cellSync')?.addEventListener('click', sync);
    el('cellLogout')?.addEventListener('click', logout);
    el('cellChatForm')?.addEventListener('submit', send);
    el('cellNoteForm')?.addEventListener('submit', createNote);
    el('cellChatInput')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); el('cellChatForm').requestSubmit(); }
    });
  }

  return { init, atualizar };
})();
