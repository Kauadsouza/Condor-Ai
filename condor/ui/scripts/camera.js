/**
 * Câmera amiga — o dono pede ("o que você vê?", "como eu tô?") e o núcleo
 * manda camera.capturar. Aqui a webcam liga, tira UMA foto e desliga na hora.
 * Nada fica guardado: o quadro vai só para a visão local no núcleo.
 */
const CondorCamera = (() => {
  // Mesma regra da trava facial: câmera virtual (Camo, OBS...) nunca vale.
  const banned = /camo|virtual|obs|manycam|droidcam|snap camera|xsplit/i;
  const preferredPhysical = /acer|integrated|user facing|front|hd webcam|webcam|camera/i;
  const MAX_LADO = 960;
  const EXPOSICAO_MS = 600;
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  let capturando = false;

  function physicalCandidates(devices) {
    return devices
      .filter((device) => device.kind === 'videoinput' && device.label && !banned.test(device.label))
      .sort((left, right) => Number(preferredPhysical.test(right.label)) - Number(preferredPhysical.test(left.label)));
  }

  // No Windows a webcam é exclusiva: se a biometria ou os gestos estão com
  // ela, a foto falharia de qualquer jeito e ainda derrubaria o outro uso.
  // const no topo do script não vira window.X: por isso o typeof.
  function cameraOcupada() {
    return capturando
      || (typeof CondorFaceGuard !== 'undefined' && Boolean(CondorFaceGuard.cameraInUse?.()))
      || (typeof CondorGestures !== 'undefined' && Boolean(CondorGestures.cameraInUse?.()));
  }

  async function abrirFisica(video) {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('câmera indisponível');
    const base = { width: { ideal: 1280 }, height: { ideal: 720 } };
    const devices = await navigator.mediaDevices.enumerateDevices();
    const physical = physicalCandidates(devices)[0];
    // Sem rótulos ainda, peça a frontal; nunca a câmera padrão, que pode ser virtual.
    const constraints = physical
      ? { ...base, deviceId: { exact: physical.deviceId } }
      : { ...base, facingMode: { exact: 'user' } };
    const stream = await navigator.mediaDevices.getUserMedia({ video: constraints, audio: false });
    const label = stream.getVideoTracks()[0]?.label || physical?.label || '';
    if (!label || banned.test(label)) {
      stream.getTracks().forEach((track) => track.stop());
      throw new Error('câmera virtual recusada');
    }
    video.srcObject = stream;
    await video.play();
    return stream;
  }

  function quadro(video) {
    if (!video.videoWidth) throw new Error('quadro da câmera indisponível');
    const escala = Math.min(1, MAX_LADO / Math.max(video.videoWidth, video.videoHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(video.videoWidth * escala);
    canvas.height = Math.round(video.videoHeight * escala);
    canvas.getContext('2d', { alpha: false }).drawImage(video, 0, 0, canvas.width, canvas.height);
    const jpeg = canvas.toDataURL('image/jpeg', 0.8).split(',', 2)[1];
    canvas.width = canvas.height = 0;
    return jpeg;
  }

  function motivo(error) {
    const name = String(error?.name || '');
    if (['NotReadableError', 'AbortError', 'TrackStartError'].includes(name)) return 'câmera ocupada';
    if (name === 'NotAllowedError' || name === 'SecurityError') return 'câmera bloqueada pelo Windows';
    if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'nenhuma câmera física encontrada';
    return String(error?.message || error || 'câmera indisponível').slice(0, 180);
  }

  async function capturar(msg) {
    const id = String(msg?.id || '');
    if (!id) return;
    if (cameraOcupada()) { CondorWS.enviar({ tipo: 'camera.quadro', id, erro: 'câmera ocupada' }); return; }
    capturando = true;
    let stream = null;
    let abriu = false;
    const video = document.createElement('video');
    video.muted = true; video.playsInline = true;
    try {
      stream = await abrirFisica(video);
      abriu = true;
      await wait(EXPOSICAO_MS);  // a webcam ajusta luz e foco nos primeiros quadros
      const image_b64 = quadro(video);
      stream.getTracks().forEach((track) => track.stop()); stream = null;
      CondorWS.enviar({ tipo: 'camera.quadro', id, image_b64 });
    } catch (error) {
      CondorWS.enviar({ tipo: 'camera.quadro', id, erro: motivo(error) });
    } finally {
      stream?.getTracks().forEach((track) => track.stop());
      video.srcObject = null;
      capturando = false;
      // Aviso visível sempre que a câmera ligou, mesmo que a foto tenha falhado.
      if (abriu && typeof CondorConversa !== 'undefined') CondorConversa.mostrarAviso('📷 câmera usada agora · nada foi salvo');
    }
  }

  function init() {
    CondorWS.ao('camera.capturar', capturar);
  }

  init();
  return { capturar, emUso: () => capturando };
})();
