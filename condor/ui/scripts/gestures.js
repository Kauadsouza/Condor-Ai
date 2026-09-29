/**
 * Gestos reais: MediaPipe GestureRecognizer roda aqui dentro (WebAssembly
 * local em vendor/mediapipe). Os quadros da câmera nunca saem da página; ao
 * core só chega o NOME de uma ação da lista fixa (/api/gestures/action).
 *
 *   mão aberta (segura)      → Condor ouve
 *   punho fechado            → Condor para de falar
 *   polegar para cima        → play/pause
 *   mão aberta indo p/ lado  → próxima / anterior
 *   indicador + subir/descer → rolar
 *   "V" + subir/descer       → volume
 */
const CondorGestures = (() => {
  const $ = (id) => document.getElementById(id);
  const VENDOR = 'vendor/mediapipe';
  const HOLD_MS = 350;          // tempo segurando o gesto antes de disparar
  const PALM_HOLD_MS = 500;     // mão aberta é o gesto mais "acidental"; pede mais
  const COOLDOWN_MS = 800;      // mesma ação não repete antes disso
  const REPEAT_MS = 380;        // rolagem/volume repetem enquanto a mão se move
  const INFER_MS = 50;          // ~20 fps: basta para gesto e poupa a CPU
  const MIN_SCORE = 0.6;
  const SWIPE_WINDOW_MS = 420;
  const SWIPE_DISTANCE = 0.2;   // fração da largura do quadro
  const VERTICAL_STEP = 0.07;   // fração da altura por passo de rolagem/volume
  const PING_MS = 45_000;
  const NAMES = {
    Open_Palm: '✋ MÃO ABERTA', Closed_Fist: '✊ PUNHO', Thumb_Up: '👍 POLEGAR',
    Pointing_Up: '☝ APONTANDO', Victory: '✌ V', Thumb_Down: '👎', ILoveYou: '🤟', None: '· MÃO',
  };
  const ACTION_LABELS = {
    ouvir: 'OUVINDO', calar: 'SILÊNCIO', playpause: 'PLAY/PAUSE', proximo: 'PRÓXIMA', anterior: 'ANTERIOR',
    rolar_cima: 'ROLAR ↑', rolar_baixo: 'ROLAR ↓', volume_mais: 'VOLUME +', volume_menos: 'VOLUME −',
  };

  let stream = null;
  let token = '';
  let engine = 'none';
  let active = false;
  let paused = false;
  let starting = false;
  let recognizer = null;
  let loader = null;
  let frameRequest = 0;
  let pingTimer = null;
  let lastInfer = 0;
  let lastVideoTime = -1;
  let candidate = 'None';
  let candidateSince = 0;
  let candidateFired = false;
  let anchorY = null;
  let history = [];
  let lastFired = {};
  let permissionAsked = false;
  let feedbackTimer = null;

  const post = async (url, body) => {
    await CondorSession.ready;
    const response = await fetch(url, {
      method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.erro || 'Controle gestual indisponível.');
      error.status = response.status; error.data = data;
      throw error;
    }
    return data;
  };

  function renderState(state, detail = '') {
    const host = $('gestureVisual');
    if (!host) return;
    const on = active && !paused;
    host.innerHTML = [
      ['ESTADO', state], ['MOTOR', engine === 'mediapipe' ? 'MEDIAPIPE' : engine === 'opencv' ? 'RESERVA' : '—'],
      ['GESTO', detail || 'AGUARDANDO'],
    ].map(([name, value]) => `<div class="signal-step"><span>${name}</span><b class="${on ? '' : 'off'}">${value}</b></div>`).join('');
    $('gestureCard')?.classList.toggle('gestures-live', on);
  }

  // Selo flutuante: o dono vê o gesto reconhecido e o que ele disparou.
  function feedback(gesture, action = '') {
    const host = $('gestureFeedback');
    if (!host) return;
    host.hidden = !active;
    host.querySelector('span').textContent = gesture || 'GESTOS ATIVOS';
    const target = host.querySelector('b');
    if (action) {
      target.textContent = action; host.classList.add('fired');
      clearTimeout(feedbackTimer);
      feedbackTimer = setTimeout(() => { host.classList.remove('fired'); target.textContent = ''; }, 1200);
    }
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const tag = document.createElement('script');
      tag.src = src; tag.async = true;
      tag.onload = resolve; tag.onerror = () => reject(new Error('arquivo local do MediaPipe ausente'));
      document.head.appendChild(tag);
    });
  }

  // Carrega uma vez só; os ~12 MB do WebAssembly ficam em memória até fechar.
  function loadRecognizer() {
    if (!loader) {
      loader = (async () => {
        if (typeof Vision === 'undefined') await loadScript(`${VENDOR}/vision_bundle.js`);
        const base = new URL(`${VENDOR}/`, location.href);
        const fileset = await Vision.FilesetResolver.forVisionTasks(new URL('wasm', base).href);
        const options = (delegate) => ({
          baseOptions: { modelAssetPath: new URL('gesture_recognizer.task', base).href, delegate },
          runningMode: 'VIDEO', numHands: 1,
          minHandDetectionConfidence: 0.6, minHandPresenceConfidence: 0.6, minTrackingConfidence: 0.5,
        });
        try { return await Vision.GestureRecognizer.createFromOptions(fileset, options('GPU')); }
        catch (_) { return Vision.GestureRecognizer.createFromOptions(fileset, options('CPU')); }
      })();
      loader.catch(() => { loader = null; });
    }
    return loader;
  }

  async function runPc(action) {
    try {
      await post('/api/gestures/action', { token, action });
    } catch (error) {
      if (error.status === 403 && error.data?.permission_request !== undefined) {
        feedback('CONTROLE DO PC', 'LIBERE NO SISTEMA');
        if (!permissionAsked) {
          permissionAsked = true;
          CondorRouter.ir('sistema');
          CondorCoreUI.loadStatus?.();
        }
      } else if (error.status === 403) {
        stop(true, 'SESSÃO ENCERRADA');
      } else if (error.status !== 429) {
        feedback('CONTROLE DO PC', 'FALHOU');
      }
    }
  }

  function fire(action, gestureName, now, cooldown = COOLDOWN_MS) {
    if (now - (lastFired[action] || 0) < cooldown) return false;
    lastFired[action] = now;
    feedback(gestureName, ACTION_LABELS[action]);
    renderState('ATIVO', `${gestureName} → ${ACTION_LABELS[action]}`);
    if (action === 'ouvir') CondorVoz.toggleLocalVoice();
    else if (action === 'calar') CondorVoz.calar();
    else runPc(action);
    return true;
  }

  // A prévia é espelhada, mas os pontos do MediaPipe vêm na imagem crua:
  // a direita do dono é x DIMINUINDO.
  function detectSwipe(now) {
    const recent = history.filter((point) => now - point.t <= SWIPE_WINDOW_MS);
    if (recent.length < 3) return '';
    const first = recent[0];
    const last = recent[recent.length - 1];
    const dx = first.x - last.x;
    const dy = last.y - first.y;
    if (Math.abs(dx) < SWIPE_DISTANCE || Math.abs(dx) < Math.abs(dy) * 2) return '';
    return dx > 0 ? 'proximo' : 'anterior';
  }

  function handleResult(result, now) {
    const landmarks = result.landmarks?.[0];
    if (!landmarks) {
      candidate = 'None'; candidateFired = false; anchorY = null; history = [];
      feedback('SEM MÃO');
      return;
    }
    const top = result.gestures?.[0]?.[0];
    const name = top && top.score >= MIN_SCORE ? top.categoryName : 'None';
    const wrist = landmarks[0];
    history.push({ t: now, x: wrist.x, y: wrist.y });
    history = history.filter((point) => now - point.t <= SWIPE_WINDOW_MS);

    if (name !== candidate) {
      candidate = name; candidateSince = now; candidateFired = false; anchorY = null;
    }
    const held = now - candidateSince;
    const label = NAMES[name] || name;
    feedback(label);

    if (['Open_Palm', 'Pointing_Up', 'None'].includes(name)) {
      const swipe = detectSwipe(now);
      if (swipe && fire(swipe, label, now)) { history = []; candidateFired = true; return; }
    }
    if (held < HOLD_MS) return;

    if (name === 'Pointing_Up' || name === 'Victory') {
      // Ao firmar o gesto, a altura atual vira a âncora; cada passo acima ou
      // abaixo dela dispara uma rolagem (ou um degrau de volume).
      if (anchorY === null) { anchorY = wrist.y; return; }
      const delta = anchorY - wrist.y;
      if (Math.abs(delta) < VERTICAL_STEP) return;
      const up = delta > 0;
      const action = name === 'Pointing_Up' ? (up ? 'rolar_cima' : 'rolar_baixo') : (up ? 'volume_mais' : 'volume_menos');
      if (fire(action, label, now, REPEAT_MS)) anchorY = wrist.y;
      return;
    }
    if (candidateFired) return;
    if (name === 'Open_Palm') {
      // Mão parada: se ela está andando, provavelmente é o começo de um swipe.
      const still = history.every((point) => Math.hypot(point.x - wrist.x, point.y - wrist.y) < 0.06);
      if (held >= PALM_HOLD_MS && still) candidateFired = fire('ouvir', label, now);
    } else if (name === 'Closed_Fist') candidateFired = fire('calar', label, now);
    else if (name === 'Thumb_Up') candidateFired = fire('playpause', label, now);
  }

  function tick() {
    frameRequest = 0;
    if (!active || paused || engine !== 'mediapipe') return;
    frameRequest = requestAnimationFrame(tick);
    const video = $('gesturePreview');
    const now = performance.now();
    if (!video || video.readyState < 2 || now - lastInfer < INFER_MS || video.currentTime === lastVideoTime) return;
    lastInfer = now; lastVideoTime = video.currentTime;
    try { handleResult(recognizer.recognizeForVideo(video, now), now); }
    catch (error) { renderState('PAUSADO', String(error.message || error).toUpperCase().slice(0, 60)); }
  }

  function physicalCameraConstraints() {
    return { video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 24, max: 30 }, facingMode: 'user' }, audio: false };
  }

  async function ping() {
    if (!token) return;
    try { await post('/api/gestures/ping', { token }); }
    catch (error) { if (error.status === 403 || error.status === 423) stop(true, 'PERMISSÃO REVOGADA'); }
  }

  async function start() {
    if (active || starting) return;
    starting = true;
    const button = $('gestureToggle'); button.disabled = true; renderState('AUTORIZANDO', 'CÂMERA LOCAL');
    try {
      await post('/api/gestures/authorize');
      stream = await navigator.mediaDevices.getUserMedia(physicalCameraConstraints());
      const track = stream.getVideoTracks()[0];
      renderState('CARREGANDO', 'MODELO LOCAL');
      try { recognizer = await loadRecognizer(); engine = 'mediapipe'; }
      catch (error) {
        console.warn('MediaPipe indisponível; usando reserva OpenCV.', error);
        recognizer = null; engine = 'opencv';
      }
      const session = await post('/api/gestures/session', { camera_label: track?.label || '', engine });
      token = session.token; active = true; paused = false;
      const video = $('gesturePreview'); video.srcObject = stream; video.hidden = false; await video.play();
      button.textContent = 'DESATIVAR GESTOS';
      pingTimer = setInterval(ping, PING_MS);
      if (engine === 'mediapipe') {
        renderState('ATIVO', 'MOSTRE A MÃO');
        feedback('GESTOS ATIVOS');
        frameRequest = requestAnimationFrame(tick);
      } else {
        renderState('RESERVA', 'SÓ DENTRO DO CONDOR');
        feedback('GESTOS · RESERVA');
        CondorGestosReserva.iniciar({ token, video, render: renderState });
      }
    } catch (error) {
      await stop(false); renderState('BLOQUEADO', String(error.message).toUpperCase());
      if (String(error.message).toLowerCase().includes('permiss')) button.textContent = 'LIBERAR NO SISTEMA';
    } finally { starting = false; button.disabled = false; }
  }

  async function stop(notify = true, reason = 'CÂMERA DESLIGADA') {
    active = false; paused = false;
    cancelAnimationFrame(frameRequest); frameRequest = 0;
    clearInterval(pingTimer); pingTimer = null;
    CondorGestosReserva.parar();
    stream?.getTracks().forEach((track) => track.stop()); stream = null;
    if ($('gesturePreview')) { $('gesturePreview').srcObject = null; $('gesturePreview').hidden = true; }
    const ending = token; token = '';
    if (ending) { try { await post('/api/gestures/stop', { token: ending }); } catch (_) { /* sessão já expirou */ } }
    candidate = 'None'; anchorY = null; history = []; lastFired = {};
    if ($('gestureFeedback')) $('gestureFeedback').hidden = true;
    if ($('gestureToggle')) $('gestureToggle').textContent = 'ATIVAR GESTOS';
    if (notify) renderState('DESATIVADO', reason);
    engine = recognizer ? 'mediapipe' : 'none';
  }

  // O WebView congela páginas escondidas; em vez de desligar, pausa e volta
  // sozinho. A trilha fica desabilitada: nenhum quadro é lido em segundo plano.
  function onVisibility() {
    if (!active) return;
    const track = stream?.getVideoTracks()[0];
    if (document.hidden) {
      paused = true; if (track) track.enabled = false;
      cancelAnimationFrame(frameRequest); frameRequest = 0;
      renderState('PAUSADO', 'JANELA OCULTA');
    } else {
      paused = false; if (track) track.enabled = true;
      history = []; candidate = 'None'; lastVideoTime = -1;
      renderState(engine === 'mediapipe' ? 'ATIVO' : 'RESERVA', 'MOSTRE A MÃO');
      if (engine === 'mediapipe' && !frameRequest) frameRequest = requestAnimationFrame(tick);
    }
  }

  function toggle() { return active ? stop() : start(); }
  function init() {
    $('gestureToggle')?.addEventListener('click', toggle);
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('beforeunload', () => { stream?.getTracks().forEach((track) => track.stop()); });
    if (typeof CondorWS !== 'undefined') {
      CondorWS.ao('seguranca.bloqueado', () => { if (active) stop(true, 'CONDOR BLOQUEADO'); });
      CondorWS.ao('core.event', (message) => {
        const event = message.event || {};
        if (event.type === 'PERMISSION_REVOKED' && event.payload?.capability === 'gesture_camera' && active) stop(true, 'PERMISSÃO REVOGADA');
        if (event.type === 'PERMISSION_GRANTED' && event.payload?.capability === 'gesture_pc_control') permissionAsked = false;
      });
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
  // cameraInUse: a câmera amiga (camera.js) não abre a câmera enquanto os gestos usam.
  return { start, stop, toggle, ativo: () => active, cameraInUse: () => Boolean(stream) };
})();
