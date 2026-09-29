/**
 * Reserva dos gestos: detector antigo por cor de pele (OpenCV no core).
 * Só entra quando o MediaPipe não carrega. Ele confunde rosto e parede, então
 * fica restrito a apontar e segurar DENTRO do Condor — nunca controla o PC.
 */
const CondorGestosReserva = (() => {
  const $ = (id) => document.getElementById(id);
  const BLOCKED_GESTURE_ACTIONS = '#programRun,#programConfirmYes,#deviceCommandSend,#deviceCommandConfirmYes,#systemPermissionSubmit,[data-permission-decision],[data-device-disconnect],button[type="submit"]';
  let token = '';
  let video = null;
  let render = () => {};
  let timer = null;
  let processing = false;
  let canvas = null;
  let context = null;
  let previousGesture = 'none';
  let grabbed = null;
  let grabStart = null;

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
      pointer.hidden = true; previousGesture = 'none'; render('RESERVA', 'SEM MÃO'); return;
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
    render('RESERVA', gesture === 'grab' ? 'SEGURANDO' : 'APONTANDO');
  }

  async function captureFrame() {
    if (!token || processing || !video || video.readyState < 2 || document.hidden) return;
    processing = true;
    try {
      if (!canvas) { canvas = document.createElement('canvas'); canvas.width = 320; canvas.height = 240; context = canvas.getContext('2d', { alpha: false }); }
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      // O quadro vai só até o core local, é analisado em memória e descartado.
      const image = canvas.toDataURL('image/jpeg', .62);
      await CondorSession.ready;
      const response = await fetch('/api/gestures/frame', { method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token, image }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.erro || 'Reserva indisponível.');
      applyGesture(data);
    } catch (error) { render('PAUSADO', String(error.message).toUpperCase()); }
    finally { processing = false; }
  }

  function iniciar(options) {
    parar();
    token = options.token; video = options.video; render = options.render || render;
    $('gesturePointer').hidden = false;
    timer = setInterval(captureFrame, 130);
  }

  function parar() {
    clearInterval(timer); timer = null; processing = false;
    const pointer = $('gesturePointer');
    releaseAt(parseFloat(pointer?.style.left) || 0, parseFloat(pointer?.style.top) || 0);
    if (pointer) pointer.hidden = true;
    token = ''; video = null; previousGesture = 'none';
  }

  return { iniciar, parar };
})();
