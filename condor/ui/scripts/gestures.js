/** Controle gestual local: aponta, segura e arrasta somente dentro do Condor. */
const CondorGestures = (() => {
  const $ = (id) => document.getElementById(id);
  const BLOCKED_GESTURE_ACTIONS = '#programRun,#deviceCommandSend,#systemPermissionSubmit,[data-permission-decision],[data-device-disconnect],button[type="submit"]';
  let stream = null;
  let token = '';
  let active = false;
  let processing = false;
  let timer = null;
  let canvas = null;
  let context = null;
  let previousGesture = 'none';
  let grabbed = null;
  let grabStart = null;

  const safeFetch = async (url, options = {}) => {
    await CondorSession.ready;
    const response = await fetch(url, { cache: 'no-store', ...options });
    const data = await response.json();
    if (!response.ok) throw new Error(data.erro || 'Controle gestual indisponível.');
    return data;
  };

  function renderState(state, detail = '') {
    const host = $('gestureVisual');
    if (!host) return;
    const ready = ['ATIVO', 'APONTANDO', 'SEGURANDO'].includes(state);
    host.innerHTML = [
      ['ESTADO', state], ['GESTO', detail || 'AGUARDANDO'], ['PRIVACIDADE', '0 QUADROS SALVOS'],
    ].map(([name, value]) => `<div class="signal-step"><span>${name}</span><b class="${ready ? '' : 'off'}">${value}</b></div>`).join('');
  }

  function physicalCameraConstraints() {
    return { video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 15, max: 24 }, facingMode: 'user' }, audio: false };
  }

  function eventAt(type, x, y, buttons = 0) {
    return new PointerEvent(type, { clientX: x, clientY: y, pointerId: 77, pointerType: 'pen', isPrimary: true, bubbles: true, cancelable: true, buttons });
  }

  function releaseAt(x, y) {
    if (!grabbed) return;
    grabbed.dispatchEvent(eventAt('pointerup', x, y, 0));
    grabbed.dispatchEvent(new MouseEvent('mouseup', { clientX: x, clientY: y, bubbles: true, cancelable: true }));
    const travel = grabStart ? Math.hypot(x - grabStart.x, y - grabStart.y) : 999;
    const elapsed = grabStart ? performance.now() - grabStart.at : 999;
    if (travel < 24 && elapsed < 850 && !grabbed.closest?.(BLOCKED_GESTURE_ACTIONS)) grabbed.click?.();
    grabbed = null; grabStart = null;
  }

  function applyGesture(result) {
    const pointer = $('gesturePointer');
    if (!result.present) {
      if (previousGesture === 'grab') releaseAt(parseFloat(pointer.style.left) || 0, parseFloat(pointer.style.top) || 0);
      pointer.hidden = true; previousGesture = 'none'; renderState('ATIVO', 'MÃO NÃO ENCONTRADA'); return;
    }
    const x = Math.max(8, Math.min(innerWidth - 8, Number(result.x) * innerWidth));
    const y = Math.max(8, Math.min(innerHeight - 8, Number(result.y) * innerHeight));
    const gesture = result.stable_gesture || result.gesture || 'point';
    pointer.hidden = false; pointer.style.left = `${x}px`; pointer.style.top = `${y}px`; pointer.classList.toggle('grab', gesture === 'grab');
    if (gesture === 'grab' && previousGesture !== 'grab') {
      const target = document.elementFromPoint(x, y);
      if (target && !target.closest?.(BLOCKED_GESTURE_ACTIONS)) {
        grabbed = target.closest?.('[data-gesture-draggable],button,input,textarea,canvas,[role="button"]') || target;
        grabStart = { x, y, at: performance.now() };
        grabbed.dispatchEvent(eventAt('pointerdown', x, y, 1));
        grabbed.dispatchEvent(new MouseEvent('mousedown', { clientX: x, clientY: y, bubbles: true, cancelable: true, buttons: 1 }));
      }
    } else if (gesture === 'grab' && grabbed) {
      grabbed.dispatchEvent(eventAt('pointermove', x, y, 1));
      grabbed.dispatchEvent(new MouseEvent('mousemove', { clientX: x, clientY: y, bubbles: true, cancelable: true, buttons: 1 }));
    } else if (gesture !== 'grab' && previousGesture === 'grab') releaseAt(x, y);
    previousGesture = gesture;
    renderState(gesture === 'grab' ? 'SEGURANDO' : 'APONTANDO', `${Math.round((result.confidence || 0) * 100)}% CONFIANÇA`);
  }

  async function captureFrame() {
    if (!active || processing || !stream) return;
    const video = $('gesturePreview');
    if (video.readyState < 2) return;
    processing = true;
    try {
      if (!canvas) { canvas = document.createElement('canvas'); canvas.width = 320; canvas.height = 240; context = canvas.getContext('2d', { alpha: false }); }
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const image = canvas.toDataURL('image/jpeg', .62);
      const result = await safeFetch('/api/gestures/frame', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token, image }) });
      applyGesture(result);
    } catch (error) { renderState('PAUSADO', error.message.toUpperCase()); }
    finally { processing = false; }
  }

  async function start() {
    const button = $('gestureToggle'); button.disabled = true; renderState('AUTORIZANDO', 'CÂMERA LOCAL');
    try {
      await safeFetch('/api/gestures/authorize', { method: 'POST' });
      stream = await navigator.mediaDevices.getUserMedia(physicalCameraConstraints());
      const track = stream.getVideoTracks()[0];
      const session = await safeFetch('/api/gestures/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ camera_label: track?.label || '' }) });
      token = session.token; active = true;
      const video = $('gesturePreview'); video.srcObject = stream; video.hidden = false; await video.play();
      $('gesturePointer').hidden = false; button.textContent = 'DESATIVAR GESTOS'; renderState('ATIVO', 'ABRA A MÃO PARA APONTAR');
      timer = setInterval(captureFrame, 130);
    } catch (error) {
      await stop(false); renderState('BLOQUEADO', error.message.toUpperCase());
      if (error.message.toLowerCase().includes('permiss')) button.textContent = 'LIBERAR NO SISTEMA';
    } finally { button.disabled = false; }
  }

  async function stop(notify = true) {
    active = false; clearInterval(timer); timer = null; processing = false;
    const pointer = $('gesturePointer'); if (pointer) pointer.hidden = true;
    releaseAt(parseFloat(pointer?.style.left) || 0, parseFloat(pointer?.style.top) || 0);
    stream?.getTracks().forEach((track) => track.stop()); stream = null;
    if ($('gesturePreview')) { $('gesturePreview').srcObject = null; $('gesturePreview').hidden = true; }
    if (token) { try { await safeFetch('/api/gestures/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) }); } catch (_) { /* sessão já expirou */ } }
    token = ''; previousGesture = 'none';
    if ($('gestureToggle')) $('gestureToggle').textContent = 'ATIVAR GESTOS';
    if (notify) renderState('DESATIVADO', 'CÂMERA DESLIGADA');
  }

  function toggle() { return active ? stop() : start(); }
  function init() {
    $('gestureToggle')?.addEventListener('click', toggle);
    document.addEventListener('visibilitychange', () => { if (document.hidden && active) stop(); });
    window.addEventListener('beforeunload', () => { stream?.getTracks().forEach((track) => track.stop()); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
  return { start, stop, toggle };
})();
