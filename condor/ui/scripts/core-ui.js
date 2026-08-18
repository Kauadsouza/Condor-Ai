/** Interface das camadas centrais do Condor Core. */
const CondorCoreUI = (() => {
  let status = null;
  let cameraState = null;
  const commands = [
    { label: 'Abrir Condor X · Modelo 01', hint: 'PROJETO', run: () => openProject() },
    { label: 'Abrir programação e hardware', hint: 'ÁREA', run: () => CondorRouter.ir('programacao') },
    { label: 'Procurar Arduino / Serial', hint: 'DEVICE BRIDGE', run: () => { CondorRouter.ir('programacao'); scanDevices(); } },
    { label: 'Abrir sistema', hint: 'ÁREA', run: () => CondorRouter.ir('sistema') },
    { label: 'Conversar com o Condor', hint: 'CHAT', run: () => CondorRouter.ir('conversacao') },
  ];

  const safeFetch = async (url, options) => {
    await CondorSession.ready;
    const response = await fetch(url, { cache: 'no-store', ...options });
    const data = await response.json();
    if (!response.ok) throw new Error(data.erro || 'Operação indisponível.');
    return data;
  };

  function openProject() {
    CondorRouter.ir('projetos');
    CondorProjetos.abrirProjeto('condor-x');
  }

  function contextLabel(value, fallback) {
    return String(value || fallback).replaceAll('-', ' ').toUpperCase();
  }

  function renderContext(context = {}) {
    document.getElementById('ctxProject').textContent = contextLabel(context.project_name, 'NENHUM');
    document.getElementById('ctxRegion').textContent = contextLabel(context.region_id, 'NENHUMA');
    document.getElementById('ctxPart').textContent = contextLabel(context.part_id, 'NENHUMA');
    document.getElementById('ctxDevice').textContent = contextLabel(context.device_id, 'NENHUM');
  }

  function renderSystem() {
    if (!status) return;
    const voiceReady = status.voice?.stt && status.voice?.tts;
    const rows = [
      ['CONDOR CORE', status.core], ['AI GATEWAY', status.ai?.ready ? 'READY' : 'NOT READY'],
      ['DEVICE BRIDGE', status.device_bridge?.bridge], ['VOICE', voiceReady ? 'READY' : 'NOT READY'],
      ['WAKE WORD', status.voice?.wake_word ? 'READY' : 'MODEL MISSING'],
      ['GESTURE', status.gesture], ['WEARABLE', status.wearable],
    ];
    document.getElementById('systemStatus').innerHTML = rows.map(([label, value]) => `<div class="core-status-row"><span>${label}</span><b class="${String(value).includes('NOT') || String(value).includes('MISSING') || String(value).includes('not_') ? 'off' : ''}">${String(value || 'unknown').replaceAll('_', ' ').toUpperCase()}</b></div>`).join('');
    const permissions = status.permissions || [];
    document.getElementById('systemPermissions').innerHTML = permissions.length ? permissions.map((item) => `<div class="permission-row"><strong>${item.capability.replaceAll('_', ' ')}</strong><span>${item.allowed ? 'PERMITIDO' : 'NÃO PERMITIDO'}</span></div>`).join('') : '<div class="core-empty">Cofre bloqueado ou permissões indisponíveis.</div>';
  }

  function renderDevices() {
    const bridge = status?.device_bridge;
    if (!bridge) return;
    document.getElementById('deviceBridgeState').textContent = String(bridge.bridge || 'unknown').toUpperCase();
    document.getElementById('deviceTransports').innerHTML = Object.entries(bridge.transport || {}).map(([name, state]) => `<div class="core-status-row"><span>${name.toUpperCase()}</span><b class="${String(state).includes('not_') ? 'off' : ''}">${String(state).replaceAll('_', ' ').toUpperCase()}</b></div>`).join('');
    document.getElementById('deviceFamilies').innerHTML = (bridge.supported_families || []).map((name) => `<span>${name}</span>`).join('');
    const voice = status.voice || {};
    const interactionRows = [
      ['TRANSCRIÇÃO LOCAL', voice.stt ? 'PRONTA' : 'INDISPONÍVEL'],
      ['VOZ DO CONDOR', voice.tts ? 'PRONTA' : 'INDISPONÍVEL'],
      ['ATIVAÇÃO “CONDOR”', voice.wake_word ? 'PRONTA' : 'MODELO AUSENTE'],
      ['ENTENDIMENTO DA MÃO', 'AINDA NÃO IMPLEMENTADO'],
      ['MODELO DE VISÃO', status.vision === 'ready' ? 'PRONTO' : 'INDISPONÍVEL'],
    ];
    document.getElementById('interactionStatus').innerHTML = interactionRows.map(([label, value]) => `<div class="core-status-row"><span>${label}</span><b class="${value.includes('AUSENTE') || value.includes('INDISPONÍVEL') || value.includes('NÃO') ? 'off' : ''}">${value}</b></div>`).join('');
  }

  async function scanDevices() {
    const list = document.getElementById('serialPortList');
    list.innerHTML = '<div class="core-empty">Procurando portas seriais...</div>';
    try {
      const data = await safeFetch('/api/devices/scan', { method: 'POST' });
      list.innerHTML = data.serial_ports.length ? data.serial_ports.map((port) => `<article><strong>${port.port} · ${port.family}</strong><span>${port.description}</span></article>`).join('') : '<div class="core-empty">Nenhuma porta serial encontrada. Conecte o Arduino por USB e procure novamente.</div>';
    } catch (error) { list.innerHTML = `<div class="core-empty">${error.message}</div>`; }
  }

  function renderCameras() {
    if (!cameraState) return;
    const cameras = cameraState.sources || [];
    const alerts = cameraState.alerts || [];
    document.getElementById('cameraList').innerHTML = cameras.length ? cameras.map((camera) => `<article><strong>${camera.name}</strong><span>${camera.zone || 'ÁREA NÃO INFORMADA'} · ${camera.protocol.toUpperCase()} · ${camera.status.toUpperCase()}</span></article>`).join('') : '<div class="core-empty">Nenhuma câmera conectada.</div>';
    document.getElementById('cameraAlerts').innerHTML = alerts.length ? alerts.map((alert) => `<article><strong>${alert.summary}</strong><span>${new Date(alert.created * 1000).toLocaleString('pt-BR')}</span></article>`).join('') : '<div class="core-empty">Nenhum alerta registrado.</div>';
  }

  async function loadCameras() {
    try { cameraState = await safeFetch('/api/cameras'); renderCameras(); } catch (_) { /* cofre bloqueado */ }
  }

  async function addCamera(event) {
    event.preventDefault();
    const message = document.getElementById('cameraMessage');
    message.classList.remove('error');
    message.textContent = 'Salvando configuração no cofre local...';
    try {
      await safeFetch('/api/cameras', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
          name: document.getElementById('cameraName').value.trim(),
          zone: document.getElementById('cameraZone').value.trim(),
          protocol: document.getElementById('cameraProtocol').value,
          endpoint: document.getElementById('cameraEndpoint').value.trim(),
        }),
      });
      event.target.reset(); event.target.hidden = true;
      message.textContent = 'Câmera configurada. O endereço permanece no cofre cifrado.';
      await loadCameras();
    } catch (error) { message.textContent = error.message; message.classList.add('error'); }
  }

  function showSecurityAlert(event) {
    const alert = event.payload?.alert;
    if (!alert) return;
    document.getElementById('cameraAlertText').textContent = alert.summary;
    document.getElementById('cameraAlertToast').hidden = false;
    loadCameras();
  }

  async function loadStatus() {
    try {
      status = await safeFetch('/api/core/status');
      renderContext(status.context); renderSystem(); renderDevices();
    } catch (_) { /* a tela bloqueada controla o acesso */ }
  }

  async function loadEvents() {
    try {
      const data = await safeFetch('/api/events?limite=30');
      document.getElementById('systemEvents').innerHTML = data.events.length ? data.events.map((event) => `<article><strong>${event.type}</strong><span>${event.source} · ${new Date(event.timestamp * 1000).toLocaleTimeString('pt-BR')}</span></article>`).join('') : '<div class="core-empty">Nenhum evento técnico registrado nesta sessão.</div>';
    } catch (_) { /* cofre bloqueado */ }
  }

  function renderCommands(query = '') {
    const normalized = query.trim().toLowerCase();
    const visible = commands.filter((command) => command.label.toLowerCase().includes(normalized));
    document.getElementById('commandResults').innerHTML = visible.map((command) => `<button type="button" data-command-index="${commands.indexOf(command)}"><span>${command.label}</span><small>${command.hint}</small></button>`).join('');
  }

  function openPalette() {
    const palette = document.getElementById('commandPalette');
    palette.hidden = false; renderCommands();
    requestAnimationFrame(() => document.getElementById('commandInput').focus());
  }

  function closePalette() { document.getElementById('commandPalette').hidden = true; }

  function init() {
    setTimeout(() => document.getElementById('coreBoot').classList.add('done'), 1450);
    document.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openPalette(); }
      if (event.key === 'Escape') closePalette();
    });
    document.getElementById('deviceScan').addEventListener('click', scanDevices);
    document.getElementById('cameraAddToggle').addEventListener('click', () => { document.getElementById('cameraForm').hidden = false; document.getElementById('cameraName').focus(); });
    document.getElementById('cameraCancel').addEventListener('click', () => { document.getElementById('cameraForm').hidden = true; document.getElementById('cameraForm').reset(); });
    document.getElementById('cameraForm').addEventListener('submit', addCamera);
    document.getElementById('cameraAlertClose').addEventListener('click', () => { document.getElementById('cameraAlertToast').hidden = true; });
    document.getElementById('commandInput').addEventListener('input', (event) => renderCommands(event.target.value));
    document.getElementById('commandResults').addEventListener('click', (event) => {
      const target = event.target.closest('[data-command-index]');
      if (!target) return;
      closePalette(); commands[Number(target.dataset.commandIndex)]?.run();
    });
    document.getElementById('commandPalette').addEventListener('click', (event) => { if (event.target.id === 'commandPalette') closePalette(); });
    CondorWS.ao('core.event', (message) => {
      if (message.event?.type === 'CONTEXT_UPDATED' || message.event?.type === 'PART_SELECTED') loadStatus();
      if (message.event?.type === 'SECURITY_ALERT') showSecurityAlert(message.event);
      if (message.event?.type?.startsWith('CAMERA_')) loadCameras();
      if (CondorRouter.atual() === 'sistema') loadEvents();
    });
    loadStatus(); loadCameras();
  }

  function atualizar(screen) {
    if (screen === 'programacao') { loadStatus(); loadCameras(); }
    if (screen === 'sistema') { loadStatus(); loadEvents(); }
  }

  return { init, atualizar, openProject, loadStatus };
})();
