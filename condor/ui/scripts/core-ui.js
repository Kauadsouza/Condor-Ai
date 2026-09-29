/** Interface visual das camadas centrais do Condor Core. */
const CondorCoreUI = (() => {
  let status = null;
  let programProjectId = 'condor-x';
  let loadedProgramProject = null;
  let saveTimer = null;
  let permissionTarget = null;
  let permissionCooldownTimer = null;
  let programSaving = false;
  const TARGET_KEY = 'condor.programacao.alvo';
  let chosenTarget = null;
  let scanTargets = [];
  let commonBoards = [];
  let activeCommandDeviceId = '';
  let deviceScanBusy = false;
  let wsOnline = false;
  let chatTurn = null;
  let micRecorder = null;
  let micStream = null;
  let micParts = [];
  let micTimer = null;
  const commands = [
    { label: 'Abrir Condor X · Modelo 01', hint: 'PROJETO', run: () => openProject() },
    { label: 'Abrir programação e conexões', hint: 'ÁREA', run: () => CondorRouter.ir('programacao') },
    { label: 'Pesquisar Arduino / Serial', hint: 'CONEXÕES', run: () => { CondorRouter.ir('programacao'); scanDevices(); } },
    { label: 'Experimentos do projeto', hint: 'PROJETOS', run: () => CondorRouter.ir('projetos') },
    { label: 'Abrir sistema', hint: 'ESTADO', run: () => CondorRouter.ir('sistema') },
    { label: 'Conversar com o Condor', hint: 'CHAT', run: () => CondorRouter.ir('conversacao') },
  ];

  const safeFetch = async (url, options) => {
    await CondorSession.ready;
    const response = await fetch(url, { cache: 'no-store', ...options });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.erro || 'Operação indisponível.');
      error.status = response.status;
      error.retryAfter = Number(response.headers.get('Retry-After') || 0);
      throw error;
    }
    return data;
  };
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  const label = (value, fallback = 'NENHUM') => String(value || fallback).replaceAll('-', ' ').replaceAll('_', ' ').toUpperCase();

  function openProject() { CondorRouter.ir('projetos'); CondorProjetos.abrirProjeto('condor-x'); }

  function detectLanguage(content) {
    const source = String(content || '');
    const scores = { arduino: 0, python: 0, typescript: 0, javascript: 0, cpp: 0, c: 0, rust: 0, html: 0, css: 0, shell: 0 };
    const hit = (name, pattern, score) => { if (pattern.test(source)) scores[name] += score; };
    hit('arduino', /\bvoid\s+setup\s*\(/i, 8); hit('arduino', /\bvoid\s+loop\s*\(/i, 8); hit('arduino', /\b(pinMode|digitalWrite|analogRead|Serial\.begin)\s*\(/i, 5);
    hit('python', /^\s*(def|class|from|import)\s+/im, 4); hit('python', /\b(print|asyncio|self)\b/i, 2);
    hit('typescript', /\b(interface|type|enum)\s+\w+/i, 5); hit('typescript', /\b(string|number|boolean)\s*[;=,)\]]/i, 2);
    hit('javascript', /\b(const|let|function)\s+/i, 3); hit('javascript', /=>|console\.log|document\./i, 2);
    hit('cpp', /#include\s*<(iostream|vector|string|memory)>/i, 6); hit('cpp', /\bstd::|cout\s*<</i, 4);
    hit('c', /#include\s*<(stdio|stdlib|string)\.h>/i, 6); hit('c', /\bprintf\s*\(|\bstruct\s+/i, 3);
    hit('rust', /^\s*fn\s+\w+/im, 5); hit('rust', /\b(let\s+mut|impl|match|println!)\b/i, 4);
    hit('html', /<!doctype\s+html|<html\b|<body\b/i, 8); hit('css', /^\s*[.#]?[\w-]+\s*\{/im, 5); hit('shell', /^#!.*\b(bash|sh|zsh)\b/im, 8);
    const extensions = { arduino: '.ino', python: '.py', typescript: '.ts', javascript: '.js', cpp: '.cpp', c: '.c', rust: '.rs', html: '.html', css: '.css', shell: '.sh', text: '.txt' };
    const top = Object.entries(scores).sort((a, b) => b[1] - a[1])[0];
    const language = source.trim() && top[1] ? top[0] : 'text';
    return { language, extension: extensions[language] };
  }

  function updateProgramVisual() {
    const editor = document.getElementById('programBuffer'); const file = document.getElementById('programFile'); const detected = detectLanguage(editor.value);
    document.getElementById('programLanguage').textContent = `AUTO · ${label(detected.language, 'TEXTO')}`;
    const stem = String(file.value || 'programa').replace(/\.[a-z0-9]+$/i, '') || 'programa'; file.value = `${stem}${detected.extension}`;
    const bytes = new TextEncoder().encode(editor.value).length; const lines = editor.value ? editor.value.split('\n').length : 0;
    document.getElementById('programMetrics').textContent = `${lines} LINHAS · ${bytes} BYTES`; return detected;
  }

  function setSaveState(text, className = '') { const element = document.getElementById('programSaveState'); element.textContent = text; element.className = `code-save-state ${className}`.trim(); }

  async function saveProgram() {
    clearTimeout(saveTimer); saveTimer = null; programSaving = true; updateProgramVisual(); setSaveState('SALVANDO', 'saving');
    try {
      const data = await safeFetch('/api/programming/buffer', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: programProjectId, name: document.getElementById('programFile').value, content: document.getElementById('programBuffer').value }) });
      document.getElementById('programFile').value = data.buffer.name; document.getElementById('programLanguage').textContent = `AUTO · ${label(data.detected.language)}`; document.getElementById('programRevision').textContent = `R${data.buffer.revision}`;
      setSaveState('SINCRONIZADO', 'saved'); status.context = data.context; renderContext(data.context); renderSystem(); return data;
    } catch (error) { setSaveState(error.message.toUpperCase()); throw error; }
    finally { programSaving = false; }
  }

  function scheduleSave() { updateProgramVisual(); setSaveState('ALTERADO', 'saving'); clearTimeout(saveTimer); saveTimer = setTimeout(() => saveProgram().catch(() => {}), 700); }

  async function loadProgram() {
    await loadStatus(); programProjectId = status?.context?.project_id || 'condor-x'; document.getElementById('programProject').textContent = label(status?.context?.project_name, 'CONDOR X');
    renderTarget();
    if (loadedProgramProject === programProjectId) return;
    try {
      const data = await safeFetch(`/api/programming/buffer?project_id=${encodeURIComponent(programProjectId)}`); const buffer = data.buffer;
      document.getElementById('programBuffer').value = buffer?.content || ''; document.getElementById('programFile').value = buffer?.name || 'programa.txt'; document.getElementById('programRevision').textContent = `R${buffer?.revision || 0}`;
      loadedProgramProject = programProjectId; updateProgramVisual(); setSaveState(buffer ? 'SINCRONIZADO' : 'PRONTO', buffer ? 'saved' : '');
    } catch (error) { setSaveState(error.message.toUpperCase()); }
  }

  function renderContext(context = {}) {
    [['ctxProject', label(context.project_name)], ['ctxRegion', label(context.region_id, 'NENHUMA')], ['ctxPart', label(context.part_id, 'NENHUMA')], ['ctxDevice', label(context.device_name || context.device_id)]].forEach(([id, text]) => { const node = document.getElementById(id); if (node) node.textContent = text; });
    const matrix = document.getElementById('systemContext'); if (!matrix) return;
    const entries = [['PROJETO', context.project_name], ['MODO', context.mode], ['ARQUIVO', context.current_file], ['LINGUAGEM', context.code_language], ['DISPOSITIVO', context.device_name], ['CONEXÃO', context.connection_state], ['REGIÃO', context.region_id], ['REVISÃO', context.code_revision ? `R${context.code_revision}` : null]];
    const populated = entries.filter(([key, value]) => value && !(key === 'MODO' && value === 'chat'));
    const card = document.getElementById('systemContextCard');
    if (card) card.hidden = populated.length === 0;
    matrix.innerHTML = populated.map(([key, value]) => `<div class="context-node"><small>${key}</small><strong>${escapeHtml(label(value))}</strong></div>`).join('');
  }

  function stateTile(name, value, detail, online) { return `<article class="system-tile ${online ? '' : 'off'}"><div class="system-tile-top"><span>${name}</span><i class="system-tile-dot"></i></div><strong>${escapeHtml(label(value, 'INDISPONÍVEL'))}</strong><small>${escapeHtml(detail)}</small></article>`; }

  function renderConnectorHealth(connector = {}) {
    const selected = connector.preferred === 'auto' ? status?.ai?.provider : connector.preferred; const providers = connector.providers || {};
    const host = document.getElementById('systemConnectorHealth');
    const problems = ['openai', 'claude', 'local'].filter((name) => {
      const item = providers[name] || {};
      return (name === selected && (!item.configured || item.verified === false)) || (item.configured && item.verified === false);
    });
    host.hidden = problems.length === 0;
    host.innerHTML = problems.map((name) => {
      const item = providers[name] || {}; const verified = item.verified; const state = !item.configured ? 'NÃO CONFIGURADO' : verified === true ? 'CONECTADO' : verified === false ? 'FALHA' : 'AGUARDANDO TESTE';
      const css = verified === true ? 'ok' : verified === false ? 'error' : '';
      return `<article class="connector-health ${css} ${selected === name ? 'selected' : ''}"><header><strong>${label(name)}</strong><i></i></header><span>${escapeHtml(state)}${selected === name ? ' · ATIVO' : ''}</span><small>${escapeHtml(item.model || 'SEM MODELO')}</small></article>`;
    }).join('');
  }

  function renderSystem() {
    if (!status) return; const voiceReady = Boolean(status.voice?.stt && status.voice?.tts); const connected = status.device_bridge?.connected?.[0];
    const webResearch = status.ai?.connector?.web_research;
    const problemTiles = [];
    if (status.core !== 'online') problemTiles.push(stateTile('CONDOR CORE', status.core, 'PROCESSO LOCAL', false));
    if (!status.ai?.ready) problemTiles.push(stateTile('MENTE', 'indisponível', label(status.ai?.model), false));
    if (!status.ai?.ready || webResearch === 'unavailable') problemTiles.push(stateTile('INTERNET', webResearch, 'PESQUISA COM FONTES', false));
    if (status.device_bridge?.bridge !== 'online') problemTiles.push(stateTile('DEVICE BRIDGE', status.device_bridge?.bridge, 'PONTE LOCAL', false));
    if (!voiceReady) problemTiles.push(stateTile('VOZ', 'incompleta', 'STT + TTS LOCAL', false));
    if (status.vision !== 'ready') problemTiles.push(stateTile('VISÃO', status.vision, 'MODELO LOCAL', false));
    // Só o MediaPipe conta como "gestos prontos"; a reserva OpenCV aparece
    // como problema porque reconhece mal e não controla o PC.
    const gesture = typeof status.gesture === 'object' && status.gesture ? status.gesture : { state: status.gesture };
    if (!gesture.mediapipe?.available) problemTiles.push(stateTile('GESTOS', gesture.state === 'ready' ? 'só reserva' : gesture.state, gesture.mediapipe?.reason ? `MEDIAPIPE: ${label(gesture.mediapipe.reason)}` : 'MEDIAPIPE AUSENTE', false));
    // "Conexão ativa" saiu a pedido do dono: dispositivo conectado aparece na aba Programação.
    const statusHost = document.getElementById('systemStatus'); statusHost.hidden = problemTiles.length === 0; statusHost.innerHTML = problemTiles.join('');
    const requests = status.permission_requests || []; const permissionCard = document.getElementById('systemPermissionCard'); permissionCard.hidden = requests.length === 0;
    document.getElementById('systemPermissions').innerHTML = requests.map((item) => `<article class="permission-request"><div><span>${escapeHtml(label(item.capability))}</span><p>${escapeHtml(item.reason)}</p><small>${escapeHtml(label(item.source))}</small></div><div class="permission-request-actions"><button type="button" data-permission-capability="${escapeHtml(item.capability)}" data-permission-request-id="${escapeHtml(item.id)}" data-permission-decision="block">BLOQUEAR</button><button type="button" class="allow-once" data-permission-capability="${escapeHtml(item.capability)}" data-permission-request-id="${escapeHtml(item.id)}" data-permission-decision="allow_once">SÓ UMA VEZ</button><button type="button" class="allow" data-permission-capability="${escapeHtml(item.capability)}" data-permission-request-id="${escapeHtml(item.id)}" data-permission-decision="allow_always">SEMPRE PERMITIR</button></div></article>`).join(''); renderContext(status.context || {});
    const connector = status.ai?.connector || {}; const aiForm = document.getElementById('systemAiForm');
    renderConnectorHealth(connector);
    if (aiForm?.hidden) { const chosen = connector.preferred; document.getElementById('systemAiProvider').value = ['auto', 'openai', 'claude', 'local'].includes(chosen) ? chosen : 'auto'; setSelectValue('systemOpenAiModel', connector.external_model, 'gpt-5.6-terra'); setSelectValue('systemClaudeModel', connector.claude_model, 'claude-sonnet-5'); setSelectValue('systemLocalModel', connector.providers?.local?.model, 'qwen3:4b-instruct'); document.getElementById('systemLocalEndpoint').value = connector.providers?.local?.endpoint || 'http://127.0.0.1:11434/v1'; syncAiProviderFields(); }
  }

  function setSelectValue(id, value, fallback) { const select = document.getElementById(id); const allowed = Array.from(select.options).some((option) => option.value === value); select.value = allowed ? value : fallback; }

  function syncAiProviderFields() { const selected = document.getElementById('systemAiProvider').value; document.querySelectorAll('[data-provider-field]').forEach((field) => { field.hidden = selected !== 'auto' && field.dataset.providerField !== selected; }); }

  function toggleAiConfig() { const form = document.getElementById('systemAiForm'); form.hidden = !form.hidden; document.getElementById('systemAiMessage').textContent = ''; if (!form.hidden) { syncAiProviderFields(); markInstalledModels(); document.getElementById('systemAiProvider').focus(); } }

  // Só dá pra escolher o que o Ollama tem baixado: modelo ausente deixava o chat
  // mudo. O "CONDOR TREINADO" só aparece depois de instalado.
  async function markInstalledModels() {
    let data; try { data = await safeFetch('/api/modelos-locais'); } catch (_) { return; }
    if (!data.disponivel) return;
    const installed = new Set(data.modelos);
    const select = document.getElementById('systemLocalModel');
    Array.from(select.options).forEach((option) => {
      if (!option.dataset.label) option.dataset.label = option.textContent;
      const ok = installed.has(option.value);
      option.disabled = !ok && option.value !== select.value;
      option.hidden = !ok && option.value === 'condor-treinado' && option.value !== select.value;
      option.textContent = ok ? option.dataset.label : `${option.dataset.label} · NÃO INSTALADO`;
    });
  }
  async function saveAiConfig(event) {
    event.preventDefault(); const submit = event.currentTarget.querySelector('button[type="submit"]'); const message = document.getElementById('systemAiMessage');
    const providerMode = document.getElementById('systemAiProvider').value; const payload = { provider_mode: providerMode };
    // Automático: grava o que estiver preenchido; com chave, usa a API e volta
    // sozinho ao modelo local se ela falhar.
    if (providerMode === 'auto') {
      payload.external_model = document.getElementById('systemOpenAiModel').value;
      payload.claude_model = document.getElementById('systemClaudeModel').value;
      payload.local_model = document.getElementById('systemLocalModel').value;
      payload.local_endpoint = document.getElementById('systemLocalEndpoint').value;
      const openai = document.getElementById('systemOpenAiKey').value.trim(); if (openai) payload.openai_api_key = openai;
      const claude = document.getElementById('systemClaudeKey').value.trim(); if (claude) payload.anthropic_api_key = claude;
    }
    if (providerMode === 'openai') { payload.external_model = document.getElementById('systemOpenAiModel').value; const key = document.getElementById('systemOpenAiKey').value.trim(); if (key) payload.openai_api_key = key; }
    if (providerMode === 'claude') { payload.claude_model = document.getElementById('systemClaudeModel').value; const key = document.getElementById('systemClaudeKey').value.trim(); if (key) payload.anthropic_api_key = key; }
    if (providerMode === 'local') { payload.local_model = document.getElementById('systemLocalModel').value; payload.local_endpoint = document.getElementById('systemLocalEndpoint').value; }
    submit.disabled = true; message.textContent = 'SALVANDO';
    try { await safeFetch('/api/seguranca/segredos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); document.getElementById('systemOpenAiKey').value = ''; document.getElementById('systemClaudeKey').value = ''; message.textContent = 'TESTANDO TODOS'; const test = await safeFetch('/api/ai/test', { method: 'POST' }); const failures = Object.values(test.results || {}).filter((item) => item.configured && item.verified !== true).length; message.textContent = test.ok && failures === 0 ? 'TUDO OK · IA CONECTADA' : `DIAGNÓSTICO · ${failures || 1} FALHA`; await loadStatus(); if (typeof CondorErros !== 'undefined') CondorErros.atualizar(); } catch (error) { message.textContent = `ERRO · ${error.message.toUpperCase()}`; if (typeof CondorErros !== 'undefined') CondorErros.atualizar(); } finally { submit.disabled = false; }
  }
  function showPermission(button) { permissionTarget = { capability: button.dataset.permissionCapability, requestId: button.dataset.permissionRequestId, decision: button.dataset.permissionDecision }; const wording = { block: ['BLOQUEAR', 'CONFIRMAR BLOQUEIO'], allow_once: ['PERMITIR UMA VEZ', 'CONFIRMAR UMA VEZ'], allow_always: ['SEMPRE PERMITIR', 'CONFIRMAR SEMPRE'] }[permissionTarget.decision]; const form = document.getElementById('systemPermissionForm'); const submit = document.getElementById('systemPermissionSubmit'); clearInterval(permissionCooldownTimer); permissionCooldownTimer = null; submit.disabled = false; document.getElementById('systemPermissionName').textContent = `${wording[0]} · ${label(permissionTarget.capability)}`; submit.textContent = wording[1]; document.getElementById('systemPermissionMessage').textContent = 'DIGITE MANUALMENTE A MESMA PALAVRA USADA PARA ENTRAR'; form.hidden = false; document.getElementById('systemPermissionPassphrase').value = ''; document.getElementById('systemPermissionPassphrase').focus(); }

  function startPermissionCooldown(submit, message, seconds) {
    clearInterval(permissionCooldownTimer);
    let remaining = Math.max(1, Number(seconds) || 1);
    submit.disabled = true;
    const tick = () => {
      message.textContent = `AGUARDE ${remaining}s · NÃO ENVIE NOVAMENTE`;
      remaining -= 1;
      if (remaining >= 0) return;
      clearInterval(permissionCooldownTimer); permissionCooldownTimer = null;
      submit.disabled = false; message.textContent = 'PRONTO · DIGITE A PALAVRA MANUALMENTE';
      document.getElementById('systemPermissionPassphrase').focus();
    };
    tick(); permissionCooldownTimer = setInterval(tick, 1000);
  }

  async function savePermission(event) {
    event.preventDefault(); if (!permissionTarget) return;
    const target = permissionTarget; const form = event.currentTarget;
    const input = document.getElementById('systemPermissionPassphrase');
    const submit = document.getElementById('systemPermissionSubmit');
    const message = document.getElementById('systemPermissionMessage');
    const passphrase = input.value; input.value = ''; submit.disabled = true;
    message.textContent = 'VALIDANDO UMA ÚNICA VEZ';
    try {
      await safeFetch(`/api/permissions/${encodeURIComponent(target.capability)}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: target.decision, request_id: target.requestId, passphrase }),
      });
      form.hidden = true; permissionTarget = null;
      window.dispatchEvent(new CustomEvent('condor-permission-resolved', {
        detail: { capability: target.capability, decision: target.decision },
      }));
      await loadStatus();
    } catch (error) {
      if (error.status === 429) startPermissionCooldown(submit, message, error.retryAfter);
      else {
        submit.disabled = false;
        message.textContent = `ERRO · ${error.message.toUpperCase()} · DIGITE NOVAMENTE`;
        input.focus();
      }
    }
  }

  function signalStep(name, value, online) { return `<div class="signal-step"><span>${name}</span><b class="${online ? '' : 'off'}">${value}</b></div>`; }
  function renderInteractions() {
    if (!status) return; const voice = status.voice || {}; const gesture = typeof status.gesture === 'object' && status.gesture ? status.gesture : {}; const mediapipe = Boolean(gesture.mediapipe?.available); const gestureReady = (gesture.state || status.gesture) === 'ready';
    document.getElementById('voiceVisual').innerHTML = [signalStep('OUVIDOS', voice.stt ? 'PRONTO' : 'OFF', voice.stt), signalStep('VOZ', voice.tts ? 'PRONTA' : 'OFF', voice.tts), signalStep('ATIVAÇÃO', voice.wake_word ? 'CONDOR' : 'OFF', voice.wake_word)].join('');
    // Com os gestos ligados, o próprio controle gestual escreve o estado ao vivo.
    if (typeof CondorGestures !== 'undefined' && CondorGestures.ativo()) return;
    document.getElementById('gestureVisual').innerHTML = [signalStep('ENTRADA', gestureReady ? 'CÂMERA LOCAL' : 'INDISPONÍVEL', gestureReady), signalStep('MOTOR', mediapipe ? `MEDIAPIPE ${escapeHtml(gesture.mediapipe.version || '')}`.trim() : gestureReady ? 'SÓ RESERVA' : 'AUSENTE', mediapipe), signalStep('QUADROS', mediapipe ? 'FICAM NA JANELA' : 'SÓ LOCAL', gestureReady)].join('');
  }

  // ── Dispositivos: só alvos úteis (portas seriais e placas Arduino) ──────────

  function loadChosenTarget() {
    try { const saved = JSON.parse(localStorage.getItem(TARGET_KEY) || 'null'); return saved && saved.port ? saved : null; } catch (_) { return null; }
  }

  function setChosenTarget(target) {
    chosenTarget = target ? { port: String(target.port || ''), fqbn: String(target.fqbn || ''), name: String(target.name || target.port || '') } : null;
    try { if (chosenTarget) localStorage.setItem(TARGET_KEY, JSON.stringify(chosenTarget)); else localStorage.removeItem(TARGET_KEY); } catch (_) { /* só conveniência */ }
    renderTarget(); renderConnected();
  }

  function renderTarget() {
    const target = document.getElementById('programTarget');
    target.classList.toggle('ready', Boolean(chosenTarget?.fqbn));
    target.querySelector('span').textContent = chosenTarget
      ? `${chosenTarget.name} · ${chosenTarget.port}${chosenTarget.fqbn ? '' : ' · SEM MODELO'}`
      : 'NENHUMA PLACA ESCOLHIDA';
  }

  /** Junta portas seriais e placas do arduino-cli; ignora HID, áudio e afins. */
  function buildTargets(data = {}) {
    const boardsByPort = new Map();
    (data.arduino?.detected || []).forEach((item) => { if (item.port) boardsByPort.set(item.port, item); });
    const targets = (data.serial_ports || []).map((port) => {
      const board = boardsByPort.get(port.port)?.boards?.[0]; boardsByPort.delete(port.port);
      const bluetooth = port.family === 'Serial Bluetooth' || /bluetooth|bthenum/i.test(`${port.description} ${port.hardware_id}`);
      return { port: port.port, name: board?.name || port.description || port.port, fqbn: board?.fqbn || '', bluetooth, serial: true };
    });
    boardsByPort.forEach((item) => {
      const board = item.boards?.[0];
      if (board) targets.push({ port: item.port, name: board.name, fqbn: board.fqbn, bluetooth: false, serial: false });
    });
    return targets.sort((a, b) => Number(a.bluetooth) - Number(b.bluetooth) || Number(!a.fqbn) - Number(!b.fqbn) || a.port.localeCompare(b.port));
  }

  function renderScanResults() {
    const list = document.getElementById('serialPortList');
    if (!scanTargets.length) { list.innerHTML = '<div class="core-empty">NENHUMA PLACA OU PORTA SERIAL</div>'; return; }
    list.innerHTML = scanTargets.map((target, index) => {
      const active = chosenTarget?.port === target.port;
      const boardPicker = !target.fqbn && !target.bluetooth
        ? `<select data-board-for="${index}" aria-label="Modelo da placa"><option value="">MODELO DA PLACA...</option>${commonBoards.map((board) => `<option value="${escapeHtml(board.fqbn)}">${escapeHtml(board.name)}</option>`).join('')}</select>`
        : '';
      return `<article class="serial-card ${active ? 'active' : ''} ${target.bluetooth ? 'bluetooth' : ''}"><div class="serial-card-head"><strong>${escapeHtml(target.name)}</strong><small>${escapeHtml(target.port)}${target.bluetooth ? ' · BLUETOOTH' : ''}</small></div><span>${escapeHtml(target.fqbn || 'PLACA NÃO IDENTIFICADA')}</span>${boardPicker}<button class="device-card-button" type="button" data-device-connect="${index}">${active ? 'CONECTADO' : 'CONECTAR'}</button></article>`;
    }).join('');
  }

  async function scanDevices() {
    if (deviceScanBusy) return; deviceScanBusy = true;
    const button = document.getElementById('deviceScan'); const list = document.getElementById('serialPortList');
    button.disabled = true; button.textContent = 'PESQUISANDO...'; list.innerHTML = '';
    try {
      const data = await safeFetch('/api/devices/scan', { method: 'POST' });
      commonBoards = data.arduino?.common_boards || commonBoards;
      scanTargets = buildTargets(data); renderScanResults();
    } catch (error) { list.innerHTML = `<div class="core-empty">${escapeHtml(error.message)}</div>`; }
    finally { deviceScanBusy = false; button.disabled = false; button.textContent = 'PESQUISAR DISPOSITIVOS'; }
  }

  async function connectTarget(index) {
    const found = scanTargets[index]; if (!found) return;
    const target = { ...found };
    const picker = document.querySelector(`[data-board-for="${index}"]`);
    if (picker?.value) { target.fqbn = picker.value; target.name = picker.selectedOptions[0].textContent; }
    setChosenTarget(target); renderScanResults();
    if (!target.serial) return;
    try {
      await safeFetch('/api/devices/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ port: target.port, baud_rate: 115200, project_id: programProjectId }) });
    } catch (error) {
      // A gravação não precisa da serial aberta; o alvo continua escolhido.
      document.getElementById('programExecutionState').textContent = /serial/i.test(error.message) ? 'SERIAL BLOQUEADA · PERMITA EM SISTEMA' : `SERIAL · ${error.message.toUpperCase()}`;
    }
    await loadStatus();
  }

  async function disconnectDevice(deviceId) {
    const device = (status?.device_bridge?.connected || []).find((item) => item.id === deviceId);
    try { await safeFetch(`/api/devices/${encodeURIComponent(deviceId)}/disconnect`, { method: 'POST' }); } catch (_) { /* segue limpando o alvo */ }
    if (device && chosenTarget && String(device.connection || '').startsWith(`serial:${chosenTarget.port}@`)) setChosenTarget(null);
    renderScanResults(); await loadStatus();
  }

  function renderConnected() {
    const host = document.getElementById('connectedDevice'); if (!host) return;
    const connected = status?.device_bridge?.connected || [];
    const isTarget = (device) => chosenTarget && String(device.connection || '').startsWith(`serial:${chosenTarget.port}@`);
    const rows = connected.map((device) => `<div class="device-live-row"><strong>${escapeHtml(device.name)}</strong><span>${escapeHtml(label(device.connection))}${isTarget(device) && chosenTarget.fqbn ? ` · ${escapeHtml(chosenTarget.fqbn)}` : ''}</span><button type="button" data-device-disconnect="${escapeHtml(device.id)}">DESCONECTAR</button></div>`);
    if (chosenTarget && !connected.some(isTarget)) rows.push(`<div class="device-live-row"><strong>${escapeHtml(chosenTarget.name)}</strong><span>${escapeHtml(chosenTarget.port)} · ${escapeHtml(chosenTarget.fqbn || 'SEM MODELO')}</span><button type="button" data-target-clear>DESCONECTAR</button></div>`);
    host.innerHTML = rows.join('') || '<strong>NENHUM CONECTADO</strong>';
    const card = document.getElementById('deviceCommandCard'); card.hidden = connected.length === 0;
    activeCommandDeviceId = connected[0]?.id || '';
    document.getElementById('deviceCommandTarget').textContent = connected[0] ? `ALVO · ${label(connected[0].name)}` : 'ALVO · NENHUM';
  }

  /** Confirmação dentro da página (o pywebview não mostra o confirm nativo). */
  function confirmInline(id, text) {
    const box = document.getElementById(id); const yes = document.getElementById(`${id}Yes`); const no = document.getElementById(`${id}No`);
    if (typeof box._resolve === 'function') box._resolve(false);
    document.getElementById(`${id}Text`).textContent = text; box.hidden = false; yes.focus();
    return new Promise((resolve) => {
      box._resolve = (value) => { box.hidden = true; box._resolve = null; yes.onclick = null; no.onclick = null; resolve(value); };
      yes.onclick = () => box._resolve(true); no.onclick = () => box._resolve(false);
    });
  }

  function showRunOutput(text, type = '') {
    const output = document.getElementById('programRunOutput'); output.hidden = false; output.className = `program-output ${type}`.trim(); output.textContent = text;
  }

  /** Mostra só as linhas de erro (ou o fim) da saída do arduino-cli. */
  function compactOutput(text) {
    const lines = String(text || '').split('\n').map((line) => line.trimEnd()).filter(Boolean);
    const errors = lines.filter((line) => /error|erro|fatal/i.test(line));
    return (errors.length ? errors : lines.slice(-12)).slice(0, 12).join('\n') || 'Sem detalhes.';
  }

  function arduinoReady(action) {
    if (detectLanguage(document.getElementById('programBuffer').value).language !== 'arduino') { showRunOutput('O código precisa ter setup() e loop().', 'error'); return false; }
    if (action === 'run' && !chosenTarget?.port) { showRunOutput('Pesquise e conecte uma placa primeiro.', 'error'); return false; }
    if (!chosenTarget?.fqbn) { showRunOutput('Conecte uma placa e escolha o modelo dela.', 'error'); return false; }
    return true;
  }

  function setArduinoBusy(busy, text) {
    document.getElementById('programRun').disabled = busy; document.getElementById('programVerify').disabled = busy;
    if (text) document.getElementById('programExecutionState').textContent = text;
  }

  async function verifyArduino() {
    if (!arduinoReady('verify')) return;
    setArduinoBusy(true, 'VERIFICANDO'); showRunOutput(`Compilando para ${chosenTarget.fqbn}...`);
    try {
      await saveProgram();
      const data = await safeFetch('/api/programming/arduino/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: programProjectId, fqbn: chosenTarget.fqbn }) });
      if (data.success) { showRunOutput('COMPILA SEM ERROS', 'success'); setArduinoBusy(false, 'VERIFICADO'); return; }
      showRunOutput(`ERRO DE COMPILAÇÃO\n\n${compactOutput(data.compile?.output)}`, 'error'); setArduinoBusy(false, 'ERRO DE COMPILAÇÃO');
    } catch (error) { showRunOutput(`NÃO VERIFICADO\n${error.message}`, 'error'); setArduinoBusy(false, 'NÃO VERIFICADO'); }
  }

  async function runArduino() {
    if (!arduinoReady('run')) return;
    const target = { ...chosenTarget };
    if (!await confirmInline('programConfirm', `Gravar em ${target.name} (${target.port})? O programa atual da placa será substituído.`)) return;
    setArduinoBusy(true, 'GRAVANDO'); showRunOutput(`${target.name} · compilando e gravando...`);
    try {
      await saveProgram();
      const data = await safeFetch('/api/programming/arduino/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: programProjectId, port: target.port, fqbn: target.fqbn, confirmed: true }) });
      if (!data.success) {
        const compileFailed = data.phase === 'compile'; const phase = compileFailed ? 'ERRO DE COMPILAÇÃO · NADA FOI GRAVADO' : 'FALHA NA GRAVAÇÃO';
        showRunOutput(`${phase}\n\n${compactOutput(compileFailed ? data.compile?.output : data.upload?.output)}`, 'error'); setArduinoBusy(false, phase); return;
      }
      showRunOutput(`GRAVADO EM ${target.name}`, 'success'); setArduinoBusy(false, 'GRAVADO'); await loadStatus();
    } catch (error) {
      if (error.status === 403) { showRunOutput('GRAVAÇÃO BLOQUEADA\nPermita "arduino upload" em Sistema.', 'error'); setArduinoBusy(false, 'BLOQUEADO'); await loadStatus(); return; }
      showRunOutput(`NÃO GRAVADO\n${error.message}`, 'error'); setArduinoBusy(false, 'NÃO GRAVADO');
    }
  }

  async function sendDeviceCommand() {
    const command = document.getElementById('deviceCommand').value.trim(); const state = document.getElementById('deviceCommandState'); const button = document.getElementById('deviceCommandSend');
    if (!command) { state.textContent = 'ESCREVA UM TEXTO'; return; }
    button.disabled = true; state.textContent = 'VERIFICANDO';
    const route = (confirmed, deviceId) => safeFetch('/api/devices/commands/route', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: programProjectId, device_id: deviceId, command, confirmed }) });
    try {
      const plan = await route(false, activeCommandDeviceId);
      if (plan.requires_confirmation && !await confirmInline('deviceCommandConfirm', `Enviar para ${plan.device.name}?`)) { state.textContent = 'CANCELADO'; return; }
      const result = plan.executed ? plan : await route(true, plan.device.device_id);
      state.textContent = result.executed ? `ENVIADO · ${result.bytes} BYTES` : 'NÃO ENVIADO'; document.getElementById('deviceCommand').value = ''; await loadStatus();
    } catch (error) { state.textContent = error.status === 403 ? 'SERIAL BLOQUEADA · PERMITA EM SISTEMA' : error.message.toUpperCase(); }
    finally { button.disabled = false; }
  }

  // ── Condor dentro da aba: conversa, voz e código para o editor ──────────────

  /** Último bloco ```cpp/ino/c (ou o último com setup()) de uma resposta. */
  function extractSketch(text) {
    const blocks = [...String(text || '').matchAll(/```([\w+#-]*)[^\n]*\n([\s\S]*?)```/g)];
    const typed = blocks.filter((block) => /^(cpp|c\+\+|ino|arduino|c)$/i.test(block[1]));
    const chosen = typed.length ? typed : blocks.filter((block) => /\bvoid\s+setup\s*\(/.test(block[2]));
    const last = chosen[chosen.length - 1];
    return last ? `${last[2].replace(/\s+$/, '')}\n` : '';
  }

  /** No chat o código aparece resumido; ele vai inteiro para o editor. */
  function chatVisibleText(text) {
    return String(text || '').replace(/```[\s\S]*?```/g, '[código → editor]').replace(/```[\s\S]*$/, '[escrevendo código...]').trim();
  }

  function chatAdd(kind, text) {
    const log = document.getElementById('programChatLog'); const item = document.createElement('div');
    item.className = `prog-msg ${kind}`; item.textContent = text; log.append(item); log.scrollTop = log.scrollHeight; return item;
  }

  function setOrb(state, text) { document.getElementById('programOrb').dataset.state = state; document.getElementById('programChatState').textContent = text; }

  function sendChat(raw) {
    const text = String(raw || '').trim(); if (!text) return;
    if (!wsOnline) { chatAdd('note', 'SEM CONEXÃO COM O NÚCLEO'); return; }
    if (chatTurn) { chatAdd('note', 'AGUARDE A RESPOSTA ATUAL'); return; }
    chatAdd('user', text); chatTurn = { bubble: null, text: '' };
    const alvo = chosenTarget ? { fqbn: chosenTarget.fqbn, name: chosenTarget.name, port: chosenTarget.port } : {};
    alvo.projeto = programProjectId;   // o servidor lê o código salvo deste projeto
    CondorWS.enviar({ tipo: 'texto', texto: text, contexto: 'programacao', alvo });
    setOrb('thinking', 'PENSANDO');
  }

  function chatToken(message) {
    if (message.contexto !== 'programacao') return;
    if (!chatTurn) chatTurn = { bubble: null, text: '' };
    if (!chatTurn.bubble) chatTurn.bubble = chatAdd('condor', '');
    chatTurn.text += message.texto || ''; chatTurn.bubble.textContent = chatVisibleText(chatTurn.text);
    document.getElementById('programChatLog').scrollTop = 1e9; setOrb('speaking', 'ESCREVENDO');
  }

  function chatFinished(message) {
    if (message.contexto !== 'programacao') return;
    const text = message.texto || chatTurn?.text || '';
    const bubble = chatTurn?.bubble || chatAdd('condor', ''); bubble.textContent = chatVisibleText(text) || '...';
    chatTurn = null; setOrb('idle', 'PRONTO');
    const code = extractSketch(text); if (!code) return;
    clearTimeout(saveTimer); document.getElementById('programBuffer').value = code; updateProgramVisual();
    saveProgram().then(() => chatAdd('note', 'CÓDIGO NO EDITOR · REVISE E CLIQUE ENVIAR')).catch(() => chatAdd('note', 'CÓDIGO NO EDITOR · NÃO SALVO'));
  }

  function chatFailed(message) {
    if (message.contexto !== 'programacao') return;
    chatTurn = null; setOrb('idle', 'PRONTO'); chatAdd('note', String(message.mensagem || 'Falhou.').toUpperCase());
  }

  function setMicPressed(pressed) { document.getElementById('programChatMic').setAttribute('aria-pressed', pressed ? 'true' : 'false'); }

  async function toggleMic() {
    if (micRecorder) { if (micRecorder.state === 'recording') micRecorder.stop(); return; }
    if (chatTurn) { chatAdd('note', 'AGUARDE A RESPOSTA ATUAL'); return; }
    if (typeof CondorMedia !== 'undefined' && !await CondorMedia.ensurePermission('microphone', 'Ouvir o pedido feito na aba Programação.', 'programming_chat')) return;
    if (!navigator.mediaDevices || !window.MediaRecorder) { chatAdd('note', 'SEM CAPTURA DE ÁUDIO'); return; }
    try { micStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false }); }
    catch (_) { chatAdd('note', 'MICROFONE BLOQUEADO'); return; }
    const preferred = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'].find((type) => MediaRecorder.isTypeSupported(type));
    micRecorder = new MediaRecorder(micStream, preferred ? { mimeType: preferred } : undefined); micParts = [];
    micRecorder.addEventListener('dataavailable', (event) => { if (event.data.size) micParts.push(event.data); });
    micRecorder.addEventListener('stop', transcribeMic, { once: true });
    micRecorder.start(250); micTimer = setTimeout(() => { if (micRecorder?.state === 'recording') micRecorder.stop(); }, 20000);
    setMicPressed(true); setOrb('listening', 'OUVINDO · CLIQUE PARA ENVIAR');
  }

  async function transcribeMic() {
    clearTimeout(micTimer); if (micStream) micStream.getTracks().forEach((track) => track.stop());
    const type = micRecorder?.mimeType || 'audio/webm'; const audio = new Blob(micParts, { type });
    micRecorder = null; micStream = null; micParts = []; setMicPressed(false);
    if (audio.size < 256) { setOrb('idle', 'PRONTO'); chatAdd('note', 'NÃO OUVI NADA'); return; }
    setOrb('thinking', 'TRANSCREVENDO');
    try {
      await CondorSession.ready;
      const response = await fetch('/api/voice/transcribe?dispatch=false', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': type }, body: audio });
      const data = await response.json(); if (!response.ok) throw new Error(data.erro || 'não entendi a fala');
      setOrb('idle', 'PRONTO'); sendChat(data.texto);
    } catch (error) { setOrb('idle', 'PRONTO'); chatAdd('note', String(error.message || error).toUpperCase()); }
  }

  /** Código salvo por outra origem (Condor no chat, outra janela): recarrega. */
  function onCodeBufferUpdated(event) {
    if (event.project_id && event.project_id !== programProjectId) return;
    const revision = Number(event.payload?.revision || 0);
    const shown = Number(String(document.getElementById('programRevision').textContent).replace(/\D/g, '') || 0);
    if (!revision || revision === shown || saveTimer || programSaving) return;
    loadedProgramProject = null; loadProgram();
  }

  async function loadStatus() { try { status = await safeFetch('/api/core/status'); renderContext(status.context); renderSystem(); renderConnected(); renderInteractions(); await CondorFaceGuard.status(); } catch (_) { /* tela bloqueada controla o acesso */ } }

  function experimentCard(item) { return `<article class="experiment-card"><strong>${escapeHtml(item.title)}</strong><span>${item.origin === 'condor' ? 'CONDOR' : 'KAUÃ'} · ${new Date(item.updated * 1000).toLocaleDateString('pt-BR')}</span></article>`; }
  async function loadExperiments() {
    try {
      const data = await safeFetch(`/api/lab/experiments?project_id=${encodeURIComponent(status?.context?.project_id || 'condor-x')}`); const groups = { proposed: [], testing: [], done: [] }; data.experiments.forEach((item) => (groups[item.status] || groups.proposed).push(item));
      for (const [statusName, id, countId] of [['proposed', 'labProposed', 'labProposedCount'], ['testing', 'labTesting', 'labTestingCount'], ['done', 'labDone', 'labDoneCount']]) { document.getElementById(id).innerHTML = groups[statusName].map(experimentCard).join('') || '<div class="core-empty">VAZIO</div>'; document.getElementById(countId).textContent = groups[statusName].length; }
    } catch (_) { /* cofre bloqueado */ }
  }
  async function createExperiment(event) { event.preventDefault(); await safeFetch('/api/lab/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: status?.context?.project_id || 'condor-x', title: document.getElementById('labTitle').value, objective: document.getElementById('labObjective').value, origin: 'owner' }) }); event.target.reset(); event.target.hidden = true; await loadExperiments(); await loadStatus(); }
  function askCondorExperiment() { CondorRouter.ir('conversacao'); const input = document.getElementById('textInput'); input.value = 'Condor, analise o projeto atual e proponha um experimento seguro para ele.'; input.focus(); }

  function renderCommands(query = '') { const normalized = query.trim().toLowerCase(); const visible = commands.filter((command) => command.label.toLowerCase().includes(normalized)); document.getElementById('commandResults').innerHTML = visible.map((command) => `<button type="button" data-command-index="${commands.indexOf(command)}"><span>${command.label}</span><small>${command.hint}</small></button>`).join(''); }
  function openPalette() { document.getElementById('commandPalette').hidden = false; renderCommands(); requestAnimationFrame(() => document.getElementById('commandInput').focus()); }
  function closePalette() { document.getElementById('commandPalette').hidden = true; }

  function init() {
    setTimeout(() => document.getElementById('coreBoot').classList.add('done'), 1450); document.addEventListener('keydown', (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openPalette(); } if (event.key === 'Escape') closePalette(); });
    chosenTarget = loadChosenTarget(); renderTarget();
    document.getElementById('deviceScan').addEventListener('click', () => scanDevices()); document.getElementById('serialPortList').addEventListener('click', (event) => { const button = event.target.closest('[data-device-connect]'); if (button) connectTarget(Number(button.dataset.deviceConnect)); });
    document.getElementById('connectedDevice').addEventListener('click', (event) => { const button = event.target.closest('[data-device-disconnect]'); if (button) disconnectDevice(button.dataset.deviceDisconnect); else if (event.target.closest('[data-target-clear]')) { setChosenTarget(null); renderScanResults(); } });
    document.getElementById('programChatForm').addEventListener('submit', (event) => { event.preventDefault(); const input = document.getElementById('programChatInput'); sendChat(input.value); input.value = ''; }); document.getElementById('programChatMic').addEventListener('click', toggleMic);
    CondorWS.ao('ws.ligado', () => { wsOnline = true; }); CondorWS.ao('ws.caiu', () => { wsOnline = false; if (chatTurn) chatFailed({ contexto: 'programacao', mensagem: 'Conexão caiu.' }); });
    CondorWS.ao('resposta.token', chatToken); CondorWS.ao('resposta.fim', chatFinished); CondorWS.ao('erro', chatFailed); CondorWS.ao('ocupado', chatFailed);
    CondorWS.ao('ferramenta.inicio', (message) => { if (message.contexto === 'programacao' && chatTurn) setOrb('thinking', label(message.rotulo, 'TRABALHANDO')); });
    document.getElementById('programBuffer').addEventListener('input', scheduleSave); document.getElementById('programFile').addEventListener('change', scheduleSave); document.getElementById('programRun').addEventListener('click', runArduino); document.getElementById('programVerify').addEventListener('click', verifyArduino); document.getElementById('deviceCommandSend').addEventListener('click', sendDeviceCommand); document.getElementById('labNew').addEventListener('click', () => { document.getElementById('labForm').hidden = false; document.getElementById('labTitle').focus(); }); document.getElementById('labAskCondor').addEventListener('click', askCondorExperiment); document.getElementById('labForm').addEventListener('submit', createExperiment); document.getElementById('systemRefresh').addEventListener('click', () => loadStatus()); document.getElementById('systemAiConfig').addEventListener('click', toggleAiConfig); document.getElementById('systemAiProvider').addEventListener('change', syncAiProviderFields); document.getElementById('systemAiForm').addEventListener('submit', saveAiConfig); document.getElementById('systemPermissions').addEventListener('click', (event) => { const button = event.target.closest('[data-permission-capability]'); if (button) showPermission(button); }); document.getElementById('systemPermissionForm').addEventListener('submit', savePermission);
    document.getElementById('commandInput').addEventListener('input', (event) => renderCommands(event.target.value)); document.getElementById('commandResults').addEventListener('click', (event) => { const target = event.target.closest('[data-command-index]'); if (!target) return; closePalette(); commands[Number(target.dataset.commandIndex)]?.run(); }); document.getElementById('commandPalette').addEventListener('click', (event) => { if (event.target.id === 'commandPalette') closePalette(); });
    CondorWS.ao('core.event', (message) => { const type = message.event?.type || ''; if (type === 'CODE_BUFFER_UPDATED' && loadedProgramProject) onCodeBufferUpdated(message.event); if (['CONTEXT_UPDATED', 'PART_SELECTED', 'PROJECT_OPENED', 'CODE_BUFFER_UPDATED', 'DEVICE_CONNECTED', 'DEVICE_DISCONNECTED', 'EXPERIMENT_CREATED', 'PERMISSION_REQUESTED', 'PERMISSION_GRANTED', 'PERMISSION_REVOKED'].includes(type)) loadStatus(); if (CondorRouter.atual() === 'projetos' && type.startsWith('EXPERIMENT_')) loadExperiments(); }); loadStatus();
  }

  function atualizar(screen) { if (screen === 'programacao') loadProgram(); if (screen === 'projetos') { loadStatus().then(loadExperiments); } if (screen === 'sistema') loadStatus(); }
  return { init, atualizar, openProject, loadStatus, extractSketch };
})();
