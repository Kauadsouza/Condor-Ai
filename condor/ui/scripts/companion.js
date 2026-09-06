/** CondorPet — ninho local, voo, voz compartilhada, carinho e movimento livre. */
const CondorPet = (() => {
  const PET_STROKE_DISTANCE = 72;
  const DRAG_THRESHOLD = 9;
  const FLIGHT_MS = 720;
  let state = 'sleeping';
  let placement = 'nest';
  let resetTimer = null;
  let flightTimer = null;
  let pointer = null;
  let strokeDistance = 0;
  let lastHeartAt = 0;
  let suppressClickUntil = 0;

  const labels = {
    listening: 'TE OUVINDO', thinking: 'PENSANDO JUNTO',
    speaking: 'FALANDO COM VOCÊ', happy: 'GOSTEI DO CARINHO',
    camera: 'OBSERVANDO COM CUIDADO', sleeping: 'EM REPOUSO',
    error: 'PRECISO DE AJUDA',
  };

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const element = () => document.getElementById('condorCompanion');
  const petButton = () => document.getElementById('condorPet');
  const nest = () => document.getElementById('condorPetNest');
  const stage = () => document.getElementById('screen-conversacao');

  function greetingForHour(hour = new Date().getHours()) {
    if (hour >= 5 && hour < 12) return 'BOM DIA, SENHOR';
    if (hour >= 12 && hour < 18) return 'BOA TARDE, SENHOR';
    return 'BOA NOITE, SENHOR';
  }

  function labelFor(next) { return next === 'idle' ? greetingForHour() : labels[next]; }

  function refreshGreeting() {
    if (state !== 'idle') return;
    const label = document.getElementById('condorPetStatus');
    if (label) label.textContent = greetingForHour();
  }

  function setState(next, temporaryMs = 0) {
    const host = element();
    if (!host) return;
    state = next === 'idle' || labels[next] ? next : 'idle';
    host.dataset.state = state;
    const label = document.getElementById('condorPetStatus');
    if (label) label.textContent = labelFor(state);
    clearTimeout(resetTimer);
    if (temporaryMs) resetTimer = setTimeout(
      () => setState(placement === 'nest' ? 'sleeping' : 'idle'), temporaryMs);
  }

  function stageSize() {
    const host = stage();
    return { width: host?.clientWidth || window.innerWidth, height: host?.clientHeight || window.innerHeight };
  }

  function clampPosition(x, y) {
    const { width, height } = stageSize();
    const mobile = width <= 700;
    return {
      x: clamp(x, mobile ? 66 : 96, width - (mobile ? 66 : 96)),
      y: clamp(y, mobile ? 94 : 112, height - (mobile ? 176 : 205)),
    };
  }

  function nestPosition() {
    const home = nest();
    const host = stage();
    if (!home || !host) {
      const { width } = stageSize();
      return { x: width - 116, y: 177 };
    }
    const homeRect = home.getBoundingClientRect();
    const stageRect = host.getBoundingClientRect();
    return {
      x: homeRect.left - stageRect.left + homeRect.width / 2,
      y: homeRect.top - stageRect.top + homeRect.height * .44,
    };
  }

  function activePosition() {
    const { width, height } = stageSize();
    if (width <= 700) return clampPosition(width * .68, height - 275);
    return clampPosition(width - 300, height - 335);
  }

  function applyPosition(x, y, nextPlacement = placement) {
    const host = element();
    if (!host) return;
    const point = nextPlacement === 'nest' ? { x, y } : clampPosition(x, y);
    placement = nextPlacement;
    host.dataset.placement = placement;
    host.style.left = `${Math.round(point.x)}px`;
    host.style.top = `${Math.round(point.y)}px`;
    host.style.right = 'auto';
    host.style.bottom = 'auto';
    nest()?.classList.toggle('is-empty', placement !== 'nest');
  }

  function flyTo(x, y, nextPlacement, onArrive) {
    const host = element();
    if (!host) return;
    clearTimeout(flightTimer);
    host.classList.add('is-flying');
    const label = document.getElementById('condorPetStatus');
    if (label) label.textContent = nextPlacement === 'nest' ? 'VOLTANDO AO NINHO' : 'VOANDO ATÉ VOCÊ';
    requestAnimationFrame(() => applyPosition(x, y, nextPlacement));
    flightTimer = window.setTimeout(() => {
      host.classList.remove('is-flying');
      if (label) label.textContent = labelFor(state);
      onArrive?.();
    }, FLIGHT_MS);
  }

  function dock(animate = true) {
    const point = nestPosition();
    if (animate && placement !== 'nest') flyTo(point.x, point.y, 'nest');
    else applyPosition(point.x, point.y, 'nest');
  }

  function deploy(startVoiceAfterFlight = false) {
    const point = activePosition();
    setState('idle');
    flyTo(point.x, point.y, 'active', () => {
      if (startVoiceAfterFlight && typeof CondorVoz !== 'undefined'
          && typeof CondorVoz.toggleLocalVoice === 'function') {
        CondorVoz.toggleLocalVoice();
      }
    });
  }

  function setLook(clientX, clientY) {
    const button = petButton();
    const host = element();
    if (!button || !host) return;
    const rect = button.getBoundingClientRect();
    const relativeX = clamp((clientX - rect.left - rect.width / 2) / (rect.width / 2), -1, 1);
    const relativeY = clamp((clientY - rect.top - rect.height / 2) / (rect.height / 2), -1, 1);
    host.style.setProperty('--pet-look-x', `${(relativeX * 5.5).toFixed(1)}px`);
    host.style.setProperty('--pet-look-y', `${(relativeY * 3.5).toFixed(1)}px`);
    host.style.setProperty('--pet-tilt', `${(relativeX * 2.6).toFixed(1)}deg`);
  }

  function resetLook() {
    const host = element();
    if (!host || pointer) return;
    host.style.setProperty('--pet-look-x', '0px');
    host.style.setProperty('--pet-look-y', '0px');
    host.style.setProperty('--pet-tilt', '0deg');
  }

  function createHeart(clientX, clientY) {
    const layer = document.getElementById('petHeartLayer');
    const button = petButton();
    if (!layer || !button) return;
    const rect = button.getBoundingClientRect();
    const heart = document.createElement('i');
    heart.className = 'pet-heart';
    heart.textContent = '♥';
    heart.style.left = `${clamp(clientX - rect.left, 36, rect.width - 36)}px`;
    heart.style.top = `${clamp(clientY - rect.top, 28, rect.height - 48)}px`;
    heart.style.setProperty('--heart-drift', `${Math.round((Math.random() - 0.5) * 52)}px`);
    heart.style.setProperty('--heart-rise', `${Math.round(Math.random() * 28)}px`);
    layer.appendChild(heart);
    heart.addEventListener('animationend', () => heart.remove(), { once: true });
  }

  function reactToPet(event) {
    const now = performance.now();
    if (now - lastHeartAt < 430) return;
    lastHeartAt = now;
    suppressClickUntil = now + 520;
    const host = element();
    host?.classList.add('is-petted');
    createHeart(event.clientX, event.clientY);
    setState('happy', 1700);
    window.setTimeout(() => host?.classList.remove('is-petted'), 780);
  }

  function onPointerDown(event) {
    if (event.button !== 0 || event.isPrimary === false) return;
    const button = petButton();
    const rect = button?.getBoundingClientRect();
    const headGesture = rect ? (event.clientY - rect.top) / rect.height <= .47 : true;
    const host = element();
    pointer = {
      id: event.pointerId, x: event.clientX, y: event.clientY,
      startX: event.clientX, startY: event.clientY, total: 0,
      mode: headGesture ? 'pet' : 'move', dragging: false,
      originX: Number.parseFloat(host?.style.left) || nestPosition().x,
      originY: Number.parseFloat(host?.style.top) || nestPosition().y,
    };
    strokeDistance = 0;
    button?.setPointerCapture?.(event.pointerId);
    if (pointer.mode === 'pet') host?.classList.add('is-petting');
    setLook(event.clientX, event.clientY);
  }

  function onPointerMove(event) {
    setLook(event.clientX, event.clientY);
    if (!pointer || pointer.id !== event.pointerId) return;
    const distance = Math.hypot(event.clientX - pointer.x, event.clientY - pointer.y);
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    pointer.total += distance;
    if (pointer.mode === 'move') {
      const dx = event.clientX - pointer.startX;
      const dy = event.clientY - pointer.startY;
      if (!pointer.dragging && Math.hypot(dx, dy) >= DRAG_THRESHOLD) {
        pointer.dragging = true;
        clearTimeout(flightTimer);
        element()?.classList.remove('is-flying');
        element()?.classList.add('is-dragging');
        nest()?.classList.add('is-empty');
      }
      if (pointer.dragging) {
        suppressClickUntil = performance.now() + 520;
        applyPosition(pointer.originX + dx, pointer.originY + dy, 'custom');
      }
      return;
    }
    strokeDistance += distance;
    if (strokeDistance >= PET_STROKE_DISTANCE) {
      strokeDistance = 0;
      reactToPet(event);
    }
  }

  function finishPointer(event) {
    if (!pointer || pointer.id !== event.pointerId) return;
    const wasDragging = pointer.dragging;
    const homeRect = nest()?.getBoundingClientRect();
    const droppedAtNest = wasDragging && homeRect
      && event.clientX >= homeRect.left - 24 && event.clientX <= homeRect.right + 24
      && event.clientY >= homeRect.top - 24 && event.clientY <= homeRect.bottom + 24;
    if (pointer.total > 26 || wasDragging) suppressClickUntil = performance.now() + 520;
    const button = petButton();
    if (button?.hasPointerCapture?.(event.pointerId)) button.releasePointerCapture(event.pointerId);
    pointer = null;
    strokeDistance = 0;
    element()?.classList.remove('is-petting', 'is-dragging');
    if (droppedAtNest) {
      setState('sleeping');
      dock(true);
    }
    window.setTimeout(resetLook, 240);
  }

  function startVoice(event) {
    if (performance.now() < suppressClickUntil) {
      event.preventDefault();
      return;
    }
    if (placement === 'nest') {
      event.preventDefault();
      deploy(true);
      return;
    }
    if (typeof CondorVoz !== 'undefined' && typeof CondorVoz.toggleLocalVoice === 'function') {
      CondorVoz.toggleLocalVoice();
    }
  }

  function bindInteraction() {
    const button = petButton();
    if (!button) return;
    button.addEventListener('pointerdown', onPointerDown);
    button.addEventListener('pointermove', onPointerMove);
    button.addEventListener('pointerup', finishPointer);
    button.addEventListener('pointercancel', finishPointer);
    button.addEventListener('pointerleave', resetLook);
    button.addEventListener('click', startVoice);
  }

  function messageCount(count) {
    element()?.classList.toggle('has-messages', Number(count) > 0);
  }

  function init() {
    setState('sleeping');
    bindInteraction();
    requestAnimationFrame(() => dock(false));
    window.setInterval(refreshGreeting, 60_000);
    window.addEventListener('focus', refreshGreeting);
    document.addEventListener('visibilitychange', refreshGreeting);
    CondorWS.ao('estado', (message) => {
      const mapped = { dormindo: 'sleeping', ouvindo: 'listening', pensando: 'thinking', falando: 'speaking' };
      const next = mapped[message.estado] || state;
      setState(next);
      if (next === 'sleeping') dock(true);
    });
    CondorWS.ao('memoria.stats', () => setState('happy', 1300));
    CondorWS.ao('erro', () => setState('error', 2600));
    window.addEventListener('resize', () => {
      if (placement === 'nest') dock(false);
      else {
        const host = element();
        applyPosition(Number.parseFloat(host?.style.left) || activePosition().x,
          Number.parseFloat(host?.style.top) || activePosition().y, placement);
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
  return { setState, messageCount, greetingForHour, dock, deploy };
})();
