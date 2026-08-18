/** Interface visual das camadas centrais do Condor Core. */
const CondorCoreUI = (() => {
  let status = null;
  let programProjectId = 'condor-x';
  let loadedProgramProject = null;
  let saveTimer = null;
  let permissionTarget = null;
  let arduinoDetection = null;
  const commands = [
    { label: 'Abrir Condor X · Modelo 01', hint: 'PROJETO', run: () => openProject() },
    { label: 'Abrir programação e conexões', hint: 'ÁREA', run: () => CondorRouter.ir('programacao') },
    { label: 'Procurar Arduino / Serial', hint: 'CONEXÕES', run: () => { CondorRouter.ir('programacao'); scanDevices(); } },
    { label: 'Abrir laboratório', hint: 'EXPERIMENTOS', run: () => CondorRouter.ir('laboratorio') },
    { label: 'Abrir sistema', hint: 'ESTADO', run: () => CondorRouter.ir('sistema') },
    { label: 'Conversar com o Condor', hint: 'CHAT', run: () => CondorRouter.ir('conversacao') },
  ];

  const safeFetch = async (url, options) => {
    await CondorSession.ready;
    const response = await fetch(url, { cache: 'no-store', ...options });
    const data = await response.json();
    if (!response.ok) throw new Error(data.erro || 'Operação indisponível.');
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
    clearTimeout(saveTimer); updateProgramVisual(); setSaveState('SALVANDO', 'saving');
    try {
      const data = await safeFetch('/api/programming/buffer', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: programProjectId, name: document.getElementById('programFile').value, content: document.getElementById('programBuffer').value }) });
      document.getElementById('programFile').value = data.buffer.name; document.getElementById('programLanguage').textContent = `AUTO · ${label(data.detected.language)}`; document.getElementById('programRevision').textContent = `R${data.buffer.revision}`;
      setSaveState('SINCRONIZADO', 'saved'); status.context = data.context; renderContext(data.context); renderSystem(); return data;
    } catch (error) { setSaveState(error.message.toUpperCase()); throw error; }
  }

  function scheduleSave() { updateProgramVisual(); setSaveState('ALTERADO', 'saving'); clearTimeout(saveTimer); saveTimer = setTimeout(() => saveProgram().catch(() => {}), 700); }

  async function loadProgram() {
    await loadStatus(); programProjectId = status?.context?.project_id || 'condor-x'; document.getElementById('programProject').textContent = label(status?.context?.project_name, 'CONDOR X');
    await loadArduinoStatus();
    if (loadedProgramProject === programProjectId) return;
    try {
      const data = await safeFetch(`/api/programming/buffer?project_id=${encodeURIComponent(programProjectId)}`); const buffer = data.buffer;
      document.getElementById('programBuffer').value = buffer?.content || ''; document.getElementById('programFile').value = buffer?.name || 'programa.txt'; document.getElementById('programRevision').textContent = `R${buffer?.revision || 0}`;
      loadedProgramProject = programProjectId; updateProgramVisual(); setSaveState(buffer ? 'SINCRONIZADO' : 'PRONTO', buffer ? 'saved' : '');
    } catch (error) { setSaveState(error.message.toUpperCase()); }
  }

  function renderContext(context = {}) {
    document.getElementById('ctxProject').textContent = label(context.project_name); document.getElementById('ctxRegion').textContent = label(context.region_id, 'NENHUMA'); document.getElementById('ctxPart').textContent = label(context.part_id, 'NENHUMA'); document.getElementById('ctxDevice').textContent = label(context.device_name || context.device_id);
    const matrix = document.getElementById('systemContext'); if (!matrix) return;
    const entries = [['PROJETO', context.project_name], ['MODO', context.mode], ['ARQUIVO', context.current_file], ['LINGUAGEM', context.code_language], ['DISPOSITIVO', context.device_name], ['CONEXÃO', context.connection_state], ['REGIÃO', context.region_id], ['REVISÃO', context.code_revision ? `R${context.code_revision}` : null]];
    matrix.innerHTML = entries.map(([key, value]) => `<div class="context-node"><small>${key}</small><strong>${escapeHtml(label(value))}</strong></div>`).join('');
  }

  function stateTile(name, value, detail, online) { return `<article class="system-tile ${online ? '' : 'off'}"><div class="system-tile-top"><span>${name}</span><i class="system-tile-dot"></i></div><strong>${escapeHtml(label(value, 'INDISPONÍVEL'))}</strong><small>${escapeHtml(detail)}</small></article>`; }

  function renderConnectorHealth(connector = {}) {
    const selected = connector.preferred === 'auto' ? status?.ai?.provider : connector.preferred; const providers = connector.providers || {};
    document.getElementById('systemConnectorHealth').innerHTML = ['openai', 'claude', 'local'].map((name) => {
      const item = providers[name] || {}; const verified = item.verified; const state = !item.configured ? 'NÃO CONFIGURADO' : verified === true ? 'CONECTADO' : verified === false ? 'FALHA' : 'AGUARDANDO TESTE';
      const css = verified === true ? 'ok' : verified === false ? 'error' : '';
      return `<article class="connector-health ${css} ${selected === name ? 'selected' : ''}"><header><strong>${label(name)}</strong><i></i></header><span>${escapeHtml(state)}${selected === name ? ' · ATIVO' : ''}</span><small>${escapeHtml(item.model || 'SEM MODELO')}</small></article>`;
    }).join('');
  }

  function renderSystem() {
    if (!status) return; const voiceReady = Boolean(status.voice?.stt && status.voice?.tts); const connected = status.device_bridge?.connected?.[0];
    const webResearch = status.ai?.connector?.web_research;
    document.getElementById('systemStatus').innerHTML = [stateTile('CONDOR CORE', status.core, 'PROCESSO LOCAL', status.core === 'online'), stateTile('MENTE', status.ai?.ready ? 'online' : 'indisponível', label(status.ai?.model), Boolean(status.ai?.ready)), stateTile('INTERNET', webResearch, 'PESQUISA COM FONTES', Boolean(status.ai?.ready && webResearch !== 'unavailable')), stateTile('DEVICE BRIDGE', status.device_bridge?.bridge, `${status.device_bridge?.connected?.length || 0} CONECTADO`, status.device_bridge?.bridge === 'online'), stateTile('VOZ', voiceReady ? 'pronta' : 'incompleta', 'STT + TTS LOCAL', voiceReady), stateTile('VISÃO', status.vision, 'MODELO LOCAL', status.vision === 'ready'), stateTile('GESTOS', status.gesture, 'ENTRADA DE MÃO', status.gesture === 'ready'), stateTile('CONEXÃO ATIVA', connected?.name || 'nenhuma', connected?.connection || 'SEM PORTA', Boolean(connected)), stateTile('CONTEXTO', status.context?.project_name || 'livre', label(status.context?.mode), true)].join('');
    const permissions = status.permissions || []; document.getElementById('systemPermissions').innerHTML = permissions.map((item) => `<button type="button" class="permission-tile ${item.allowed ? '' : 'off'}" data-permission-capability="${escapeHtml(item.capability)}" data-permission-allowed="${item.allowed ? '1' : '0'}"><span>${escapeHtml(label(item.capability))}</span><b>${item.allowed ? 'ATIVO' : 'BLOQUEADO'}</b></button>`).join('') || '<div class="core-empty">BLOQUEADO</div>'; renderContext(status.context || {});
    const connector = status.ai?.connector || {}; const aiForm = document.getElementById('systemAiForm');
    renderConnectorHealth(connector);
    if (aiForm?.hidden) { const chosen = connector.preferred === 'auto' ? status.ai?.provider : connector.preferred; document.getElementById('systemAiProvider').value = ['openai', 'claude', 'local'].includes(chosen) ? chosen : 'local'; setSelectValue('systemOpenAiModel', connector.external_model, 'gpt-5.6-terra'); setSelectValue('systemClaudeModel', connector.claude_model, 'claude-sonnet-5'); setSelectValue('systemLocalModel', connector.providers?.local?.model, 'qwen3:4b-instruct'); document.getElementById('systemLocalEndpoint').value = connector.providers?.local?.endpoint || 'http://127.0.0.1:11434/v1'; syncAiProviderFields(); }
  }

  function setSelectValue(id, value, fallback) { const select = document.getElementById(id); const allowed = Array.from(select.options).some((option) => option.value === value); select.value = allowed ? value : fallback; }

  function syncAiProviderFields() { const selected = document.getElementById('systemAiProvider').value; document.querySelectorAll('[data-provider-field]').forEach((field) => { field.hidden = field.dataset.providerField !== selected; }); }

  function toggleAiConfig() { const form = document.getElementById('systemAiForm'); form.hidden = !form.hidden; document.getElementById('systemAiMessage').textContent = ''; if (!form.hidden) { syncAiProviderFields(); document.getElementById('systemAiProvider').focus(); } }
  async function saveAiConfig(event) {
    event.preventDefault(); const submit = event.currentTarget.querySelector('button[type="submit"]'); const message = document.getElementById('systemAiMessage');
    const providerMode = document.getElementById('systemAiProvider').value; const payload = { provider_mode: providerMode };
    if (providerMode === 'openai') { payload.external_model = document.getElementById('systemOpenAiModel').value; const key = document.getElementById('systemOpenAiKey').value.trim(); if (key) payload.openai_api_key = key; }
    if (providerMode === 'claude') { payload.claude_model = document.getElementById('systemClaudeModel').value; const key = document.getElementById('systemClaudeKey').value.trim(); if (key) payload.anthropic_api_key = key; }
    if (providerMode === 'local') { payload.local_model = document.getElementById('systemLocalModel').value; payload.local_endpoint = document.getElementById('systemLocalEndpoint').value; }
    submit.disabled = true; message.textContent = 'SALVANDO';
    try { await safeFetch('/api/seguranca/segredos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); document.getElementById('systemOpenAiKey').value = ''; document.getElementById('systemClaudeKey').value = ''; message.textContent = 'TESTANDO TODOS'; const test = await safeFetch('/api/ai/test', { method: 'POST' }); const failures = Object.values(test.results || {}).filter((item) => item.configured && item.verified !== true).length; message.textContent = test.ok && failures === 0 ? 'TUDO OK · IA CONECTADA' : `DIAGNÓSTICO · ${failures || 1} FALHA`; await loadStatus(); if (typeof CondorErros !== 'undefined') CondorErros.atualizar(); } catch (error) { message.textContent = `ERRO · ${error.message.toUpperCase()}`; if (typeof CondorErros !== 'undefined') CondorErros.atualizar(); } finally { submit.disabled = false; }
  }
  function showPermission(button) { permissionTarget = { capability: button.dataset.permissionCapability, allowed: button.dataset.permissionAllowed === '1' }; const form = document.getElementById('systemPermissionForm'); document.getElementById('systemPermissionName').textContent = label(permissionTarget.capability); document.getElementById('systemPermissionSubmit').textContent = permissionTarget.allowed ? 'BLOQUEAR' : 'ATIVAR'; document.getElementById('systemPermissionMessage').textContent = ''; form.hidden = false; document.getElementById('systemPermissionPassphrase').value = ''; document.getElementById('systemPermissionPassphrase').focus(); }
  async function savePermission(event) { event.preventDefault(); if (!permissionTarget) return; const message = document.getElementById('systemPermissionMessage'); const desired = !permissionTarget.allowed; try { await safeFetch(`/api/permissions/${encodeURIComponent(permissionTarget.capability)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ allowed: desired, passphrase: document.getElementById('systemPermissionPassphrase').value }) }); event.currentTarget.hidden = true; permissionTarget = null; await loadStatus(); } catch (error) { message.textContent = `ERRO · ${error.message.toUpperCase()}`; } }

  function signalStep(name, value, online) { return `<div class="signal-step"><span>${name}</span><b class="${online ? '' : 'off'}">${value}</b></div>`; }
  function renderInteractions() {
    if (!status) return; const voice = status.voice || {}; const gestureReady = status.gesture === 'ready';
    document.getElementById('voiceVisual').innerHTML = [signalStep('OUVIDOS', voice.stt ? 'PRONTO' : 'OFF', voice.stt), signalStep('VOZ', voice.tts ? 'PRONTA' : 'OFF', voice.tts), signalStep('ATIVAÇÃO', voice.wake_word ? 'CONDOR' : 'OFF', voice.wake_word)].join('');
    document.getElementById('gestureVisual').innerHTML = [signalStep('ENTRADA', gestureReady ? 'CÂMERA' : 'NÃO CONFIGURADA', gestureReady), signalStep('MODELO DE MÃO', gestureReady ? 'PRONTO' : 'AUSENTE', gestureReady), signalStep('GESTOS ATIVOS', gestureReady ? 'ATIVOS' : '0', gestureReady)].join('');
  }

  function renderDevices() {
    const bridge = status?.device_bridge; if (!bridge) return;
    document.getElementById('deviceBridgeState').textContent = label(bridge.bridge); document.getElementById('deviceTransports').innerHTML = Object.entries(bridge.transport || {}).map(([name, state]) => `<div class="core-status-row"><span>${label(name)}</span><b class="${String(state).includes('not_') ? 'off' : ''}">${label(state)}</b></div>`).join(''); document.getElementById('deviceFamilies').innerHTML = ['USB / SERIAL', 'BLUETOOTH · BUSCA', 'WI-FI'].map((name) => `<span>${name}</span>`).join('');
    const connected = bridge.connected?.[0]; document.getElementById('connectedDevice').innerHTML = connected ? `<strong>${escapeHtml(connected.name)}</strong><span>${escapeHtml(label(connected.connection))}</span><button type="button" data-device-disconnect="${escapeHtml(connected.id)}">DESCONECTAR</button>` : '<strong>NENHUM DISPOSITIVO</strong><span>SEM CONEXÃO ATIVA</span>';
  }

  function renderArduinoTargets(arduino = {}, serialPorts = []) {
    arduinoDetection = arduino;
    const portSelect = document.getElementById('programPort'); const boardSelect = document.getElementById('programBoard');
    const previousPort = portSelect.value; const previousBoard = boardSelect.value;
    const detected = arduino.detected || [];
    const portMap = new Map();
    serialPorts.forEach((item) => portMap.set(item.port, `${item.port} · ${item.family}`));
    detected.forEach((item) => { if (item.port) portMap.set(item.port, `${item.port}${item.boards?.[0]?.name ? ` · ${item.boards[0].name}` : ''}`); });
    portSelect.innerHTML = '<option value="">SELECIONE A PORTA</option>' + Array.from(portMap.entries()).map(([value, name]) => `<option value="${escapeHtml(value)}">${escapeHtml(name)}</option>`).join('');
    if (portMap.has(previousPort)) portSelect.value = previousPort;
    const boardMap = new Map();
    (arduino.common_boards || []).forEach((item) => boardMap.set(item.fqbn, item.name));
    detected.forEach((item) => (item.boards || []).forEach((board) => boardMap.set(board.fqbn, board.name)));
    boardSelect.innerHTML = '<option value="">SELECIONE A PLACA</option>' + Array.from(boardMap.entries()).map(([fqbn, name]) => `<option value="${escapeHtml(fqbn)}">${escapeHtml(name)}</option>`).join('');
    if (boardMap.has(previousBoard)) boardSelect.value = previousBoard;
    selectDetectedBoard();
  }

  function selectDetectedBoard() {
    const port = document.getElementById('programPort').value; if (!port || !arduinoDetection) return;
    const match = (arduinoDetection.detected || []).find((item) => item.port === port);
    if (match?.boards?.length === 1) document.getElementById('programBoard').value = match.boards[0].fqbn;
  }

  async function loadArduinoStatus() {
    try { const data = await safeFetch('/api/programming/arduino/status'); renderArduinoTargets(data); document.getElementById('programExecutionState').textContent = data.installed ? `ARDUINO CLI ${data.version || 'PRONTO'}` : 'ARDUINO CLI AUSENTE'; }
    catch (error) { document.getElementById('programExecutionState').textContent = 'ARDUINO INDISPONÍVEL'; }
  }

  function showRunOutput(text, type = '') {
    const output = document.getElementById('programRunOutput'); output.hidden = false; output.className = `program-output ${type}`.trim(); output.textContent = text;
  }

  async function runArduino() {
    const button = document.getElementById('programRun'); const port = document.getElementById('programPort').value; const board = document.getElementById('programBoard'); const fqbn = board.value;
    if (detectLanguage(document.getElementById('programBuffer').value).language !== 'arduino') { showRunOutput('RUN FÍSICO BLOQUEADO\nO código precisa conter setup() e loop().', 'error'); return; }
    if (!port || !fqbn) { showRunOutput('SELECIONE O ALVO\nEscolha a porta USB e o modelo exato da placa.', 'error'); return; }
    const boardName = board.options[board.selectedIndex]?.textContent || fqbn;
    if (!window.confirm(`Compilar e gravar ${boardName} na porta ${port}?\n\nA placa será reprogramada com o código atual.`)) return;
    button.disabled = true; button.textContent = 'COMPILANDO'; document.getElementById('programExecutionState').textContent = 'COMPILANDO'; showRunOutput(`ALVO · ${boardName}\nPORTA · ${port}\n\nCompilando código...`);
    try {
      await saveProgram();
      const data = await safeFetch('/api/programming/arduino/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: programProjectId, port, fqbn }) });
      if (!data.success) { const compileFailed = data.phase === 'compile'; const phase = compileFailed ? 'COMPILAÇÃO FALHOU · NADA FOI GRAVADO' : 'GRAVAÇÃO FALHOU'; const details = (compileFailed ? data.compile?.output : data.upload?.output) || 'Sem detalhes.'; showRunOutput(`${phase}\n\n${details}`, 'error'); document.getElementById('programExecutionState').textContent = phase; return; }
      showRunOutput(`GRAVAÇÃO CONCLUÍDA E VERIFICADA\n\n${data.upload?.output || 'Arduino respondeu sem mensagens adicionais.'}`, 'success'); document.getElementById('programExecutionState').textContent = 'ARDUINO ATUALIZADO'; await loadStatus();
    } catch (error) { showRunOutput(`RUN INTERROMPIDO\n\n${error.message}`, 'error'); document.getElementById('programExecutionState').textContent = 'RUN INTERROMPIDO'; }
    finally { button.disabled = false; button.textContent = '▶ RUN'; }
  }

  async function scanDevices() {
    const list = document.getElementById('serialPortList'); list.innerHTML = '<div class="core-empty">PROCURANDO...</div>';
    try {
      const data = await safeFetch('/api/devices/scan', { method: 'POST' }); document.getElementById('deviceScanCount').textContent = `${data.count} ENCONTRADA${data.count === 1 ? '' : 'S'}`; renderArduinoTargets(data.arduino || {}, data.serial_ports || []);
      list.innerHTML = data.serial_ports.length ? data.serial_ports.map((port) => `<article class="serial-card"><div class="serial-card-head"><strong>${escapeHtml(port.family)}</strong><small>${escapeHtml(port.port)}</small></div><span>${escapeHtml(port.description)}</span><div class="serial-actions"><select data-baud-for="${escapeHtml(port.port)}"><option value="115200">115200</option><option value="9600">9600</option><option value="57600">57600</option></select><button type="button" data-device-connect="${escapeHtml(port.port)}">CONECTAR</button></div></article>`).join('') : '<div class="core-empty">NENHUMA PORTA SERIAL</div>';
    } catch (error) { list.innerHTML = `<div class="core-empty">${escapeHtml(error.message)}</div>`; }
  }

  async function connectDevice(port, button) {
    const select = Array.from(document.querySelectorAll('[data-baud-for]')).find((item) => item.dataset.baudFor === port); const baud = select?.value || 115200; button.disabled = true; button.textContent = 'CONECTANDO';
    try { const data = await safeFetch('/api/devices/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ port, baud_rate: Number(baud), project_id: programProjectId }) }); status.context = data.context; await loadStatus(); button.textContent = 'CONECTADO'; } catch (error) { button.disabled = false; button.textContent = 'TENTAR NOVAMENTE'; button.title = error.message; }
  }
  async function disconnectDevice(deviceId) { await safeFetch(`/api/devices/${encodeURIComponent(deviceId)}/disconnect`, { method: 'POST' }); await loadStatus(); }

  async function loadStatus() { try { status = await safeFetch('/api/core/status'); renderContext(status.context); renderSystem(); renderDevices(); renderInteractions(); } catch (_) { /* tela bloqueada controla o acesso */ } }
  async function loadEvents() { try { const data = await safeFetch('/api/events?limite=30'); document.getElementById('systemEvents').innerHTML = data.events.length ? data.events.map((event) => `<article><div><strong>${escapeHtml(label(event.type))}</strong><span>${escapeHtml(label(event.source))}</span></div><span>${new Date(event.timestamp * 1000).toLocaleTimeString('pt-BR')}</span></article>`).join('') : '<div class="core-empty">NENHUM EVENTO</div>'; } catch (_) { /* cofre bloqueado */ } }

  function experimentCard(item) { return `<article class="experiment-card"><strong>${escapeHtml(item.title)}</strong><span>${item.origin === 'condor' ? 'CONDOR' : 'KAUÃ'} · ${new Date(item.updated * 1000).toLocaleDateString('pt-BR')}</span></article>`; }
  async function loadExperiments() {
    try {
      const data = await safeFetch(`/api/lab/experiments?project_id=${encodeURIComponent(status?.context?.project_id || 'condor-x')}`); const groups = { proposed: [], testing: [], done: [] }; data.experiments.forEach((item) => (groups[item.status] || groups.proposed).push(item));
      for (const [statusName, id, countId] of [['proposed', 'labProposed', 'labProposedCount'], ['testing', 'labTesting', 'labTestingCount'], ['done', 'labDone', 'labDoneCount']]) { document.getElementById(id).innerHTML = groups[statusName].map(experimentCard).join('') || '<div class="core-empty">VAZIO</div>'; document.getElementById(countId).textContent = groups[statusName].length; }
    } catch (_) { /* cofre bloqueado */ }
  }
  async function createExperiment(event) { event.preventDefault(); await safeFetch('/api/lab/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: status?.context?.project_id || 'condor-x', title: document.getElementById('labTitle').value, objective: document.getElementById('labObjective').value, origin: 'owner' }) }); event.target.reset(); event.target.hidden = true; await loadExperiments(); await loadStatus(); }
  function askCondorExperiment() { CondorRouter.ir('conversacao'); const input = document.getElementById('textInput'); input.value = 'Condor, analise o projeto atual e proponha um experimento seguro para o Laboratório.'; input.focus(); }

  function renderCommands(query = '') { const normalized = query.trim().toLowerCase(); const visible = commands.filter((command) => command.label.toLowerCase().includes(normalized)); document.getElementById('commandResults').innerHTML = visible.map((command) => `<button type="button" data-command-index="${commands.indexOf(command)}"><span>${command.label}</span><small>${command.hint}</small></button>`).join(''); }
  function openPalette() { document.getElementById('commandPalette').hidden = false; renderCommands(); requestAnimationFrame(() => document.getElementById('commandInput').focus()); }
  function closePalette() { document.getElementById('commandPalette').hidden = true; }

  function init() {
    setTimeout(() => document.getElementById('coreBoot').classList.add('done'), 1450); document.addEventListener('keydown', (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openPalette(); } if (event.key === 'Escape') closePalette(); });
    document.getElementById('deviceScan').addEventListener('click', scanDevices); document.getElementById('serialPortList').addEventListener('click', (event) => { const button = event.target.closest('[data-device-connect]'); if (button) connectDevice(button.dataset.deviceConnect, button); }); document.getElementById('connectedDevice').addEventListener('click', (event) => { const button = event.target.closest('[data-device-disconnect]'); if (button) disconnectDevice(button.dataset.deviceDisconnect); });
    document.getElementById('programBuffer').addEventListener('input', scheduleSave); document.getElementById('programFile').addEventListener('change', scheduleSave); document.getElementById('programRun').addEventListener('click', runArduino); document.getElementById('programPort').addEventListener('change', selectDetectedBoard); document.getElementById('labNew').addEventListener('click', () => { document.getElementById('labForm').hidden = false; document.getElementById('labTitle').focus(); }); document.getElementById('labAskCondor').addEventListener('click', askCondorExperiment); document.getElementById('labForm').addEventListener('submit', createExperiment); document.getElementById('systemRefresh').addEventListener('click', async () => { await loadStatus(); await loadEvents(); }); document.getElementById('systemAiConfig').addEventListener('click', toggleAiConfig); document.getElementById('systemAiProvider').addEventListener('change', syncAiProviderFields); document.getElementById('systemAiForm').addEventListener('submit', saveAiConfig); document.getElementById('systemPermissions').addEventListener('click', (event) => { const button = event.target.closest('[data-permission-capability]'); if (button) showPermission(button); }); document.getElementById('systemPermissionForm').addEventListener('submit', savePermission);
    document.getElementById('commandInput').addEventListener('input', (event) => renderCommands(event.target.value)); document.getElementById('commandResults').addEventListener('click', (event) => { const target = event.target.closest('[data-command-index]'); if (!target) return; closePalette(); commands[Number(target.dataset.commandIndex)]?.run(); }); document.getElementById('commandPalette').addEventListener('click', (event) => { if (event.target.id === 'commandPalette') closePalette(); });
    CondorWS.ao('core.event', (message) => { const type = message.event?.type || ''; if (['CONTEXT_UPDATED', 'PART_SELECTED', 'PROJECT_OPENED', 'CODE_BUFFER_UPDATED', 'DEVICE_CONNECTED', 'DEVICE_DISCONNECTED', 'EXPERIMENT_CREATED'].includes(type)) loadStatus(); if (CondorRouter.atual() === 'sistema') loadEvents(); if (CondorRouter.atual() === 'laboratorio' && type.startsWith('EXPERIMENT_')) loadExperiments(); }); loadStatus();
  }

  function atualizar(screen) { if (screen === 'programacao') loadProgram(); if (screen === 'laboratorio') { loadStatus().then(loadExperiments); } if (screen === 'sistema') { loadStatus(); loadEvents(); } }
  return { init, atualizar, openProject, loadStatus };
})();
