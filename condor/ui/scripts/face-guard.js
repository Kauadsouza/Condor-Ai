/** Biometria facial sob demanda: câmera somente durante cadastro/autenticação. */
const CondorFaceGuard = (() => {
  let stream = null;
  let cameraLabel = '';
  let gateOpen = false;
  let challengeRunning = false;
  let releasing = null;
  let awaitingEnrollmentPermission = false;
  const banned = /camo|virtual|obs|manycam|droidcam|snap camera|xsplit/i;
  const preferredPhysical = /acer|integrated|user facing|front|hd webcam|webcam|camera/i;
  const $ = (id) => document.getElementById(id);
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function api(url, options = {}) {
    await CondorSession.ready;
    const response = await fetch(url, { cache: 'no-store', ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.erro || 'trava facial indisponível');
      error.status = response.status; error.data = data; throw error;
    }
    return data;
  }

  function cameraErrorMessage(error) {
    const name = String(error?.name || '');
    const message = String(error?.message || error || '');
    if (['NotReadableError', 'AbortError', 'TrackStartError'].includes(name)
        || /could not start video source|device.*(?:busy|in use)|ocupad|indispon/i.test(message)) {
      return 'Câmera física ocupada. Feche Camo Studio, Teams, navegador ou outro aplicativo que esteja usando a câmera e tente novamente.';
    }
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      return 'A câmera foi bloqueada pelo Windows ou pela janela do Condor. Autorize o acesso e tente novamente.';
    }
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      return 'Nenhuma câmera física foi encontrada neste computador.';
    }
    return message || 'Câmera física indisponível.';
  }

  function physicalCandidates(devices) {
    return devices
      .filter((device) => device.kind === 'videoinput' && device.label && !banned.test(device.label))
      .sort((left, right) => Number(preferredPhysical.test(right.label)) - Number(preferredPhysical.test(left.label)));
  }

  async function useCamera(video, constraints, expectedLabel = '') {
    const candidate = await navigator.mediaDevices.getUserMedia({ video: constraints, audio: false });
    const track = candidate.getVideoTracks()[0];
    const label = track?.label || expectedLabel;
    if (!label || banned.test(label)) {
      candidate.getTracks().forEach((item) => item.stop());
      throw new Error('Câmera virtual recusada. Selecione a câmera física deste computador.');
    }
    stream = candidate; cameraLabel = label; video.srcObject = stream;
    await video.play(); await wait(350);
    return cameraLabel;
  }

  async function openPhysicalCamera(video) {
    stopCamera();
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('câmera indisponível');
    try {
      let devices = await navigator.mediaDevices.enumerateDevices();
      let physical = physicalCandidates(devices)[0];
      if (physical) {
        return await useCamera(video, {
          deviceId: { exact: physical.deviceId }, width: { ideal: 640 },
          height: { ideal: 480 }, frameRate: { ideal: 12, max: 15 },
        }, physical.label);
      }

      // Sem rótulos, peça diretamente uma câmera frontal. Nunca abra a câmera
      // padrão: ela pode ser a câmera virtual do Camo e tomar a webcam física.
      try {
        return await useCamera(video, {
          facingMode: { exact: 'user' }, width: { ideal: 640 },
          height: { ideal: 480 }, frameRate: { ideal: 12, max: 15 },
        });
      } catch (firstError) {
        if (!['OverconstrainedError', 'NotFoundError'].includes(String(firstError?.name || ''))) throw firstError;
      }

      devices = await navigator.mediaDevices.enumerateDevices();
      physical = physicalCandidates(devices)[0];
      if (!physical) throw new Error('Nenhuma câmera física confiável foi encontrada.');
      return await useCamera(video, {
        deviceId: { exact: physical.deviceId }, width: { ideal: 640 },
        height: { ideal: 480 }, frameRate: { ideal: 12, max: 15 },
      }, physical.label);
    } catch (error) {
      stopCamera();
      throw new Error(cameraErrorMessage(error));
    }
  }

  function stopCamera() {
    stream?.getTracks().forEach((track) => track.stop());
    stream = null; cameraLabel = '';
  }

  function capture(video, canvas) {
    if (!stream || !video.videoWidth) throw new Error('quadro da câmera indisponível');
    const scale = Math.min(1, 640 / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext('2d', { alpha: false }).drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', .74).split(',', 2)[1];
  }

  async function status() {
    const card = $('systemFaceGuardCard');
    const state = $('systemFaceGuardState'); const detail = $('systemFaceGuardDetail');
    let data;
    try {
      data = await api('/api/biometria/status');
    } catch (error) {
      if (card) card.hidden = false;
      if (state) state.textContent = 'VERIFICAÇÃO FACIAL INDISPONÍVEL';
      if (detail) detail.textContent = String(error.message || error);
      throw error;
    }
    const healthy = data.available && data.enrolled && data.enabled
      && !['models_unavailable', 'invalid_template'].includes(String(data.reason || ''));
    if (card) card.hidden = healthy;
    if (state) state.textContent = !data.available ? 'MODELOS LOCAIS AUSENTES' : data.enabled ? 'ATIVA · NA ENTRADA' : data.enrolled ? 'CADASTRADA · DESATIVADA' : 'NÃO CONFIGURADA';
    if (detail) detail.textContent = data.enabled
      ? 'Seu vetor está cifrado. A câmera abre somente para confirmar seu rosto e fecha logo depois.'
      : 'Use a câmera física. Nenhuma fotografia é armazenada.';
    if ($('systemFaceEnroll')) $('systemFaceEnroll').textContent = data.enrolled ? 'CORRIGIR CADASTRO' : 'CADASTRAR ROSTO';
    if ($('systemFaceDisable')) $('systemFaceDisable').hidden = !data.enabled;
    return data;
  }

  async function prepareEnrollmentCamera() {
    const instruction = $('faceEnrollInstruction'); const message = $('faceEnrollMessage');
    const button = $('faceEnrollStart');
    instruction.textContent = 'ABRINDO A CÂMERA FÍSICA';
    message.textContent = 'Selecionando diretamente a webcam física; câmeras virtuais serão ignoradas.';
    resetEnrollmentVisual();
    button.disabled = true;
    try {
      await openPhysicalCamera($('faceEnrollVideo'));
      instruction.textContent = 'OLHE DIRETAMENTE PARA A CÂMERA';
      message.textContent = `${cameraLabel} · quadros descartados após o cadastro`;
      button.textContent = 'COMEÇAR';
      return true;
    } catch (error) {
      instruction.textContent = 'CÂMERA FÍSICA INDISPONÍVEL';
      message.textContent = String(error.message || error);
      button.textContent = 'TENTAR CÂMERA';
      return false;
    } finally {
      button.disabled = false;
    }
  }

  async function openEnrollment() {
    try {
      awaitingEnrollmentPermission = true;
      if (!await CondorMedia.ensurePermission(
        'camera', 'Usar a câmera somente durante cadastro ou autenticação facial.', 'face_guard', { requireAlways: true },
      )) return;
      awaitingEnrollmentPermission = false;
      const dialog = $('faceEnrollDialog');
      if (!dialog.open) dialog.showModal();
      await prepareEnrollmentCamera();
    } catch (error) {
      awaitingEnrollmentPermission = false;
      const dialog = $('faceEnrollDialog');
      if (!dialog.open) dialog.showModal();
      $('faceEnrollInstruction').textContent = 'CADASTRO INDISPONÍVEL';
      $('faceEnrollMessage').textContent = String(error.message || error);
    }
  }

  function closeEnrollment() {
    stopCamera();
    if ($('faceEnrollPassphrase')) $('faceEnrollPassphrase').value = '';
    if ($('faceEnrollDialog')?.open) $('faceEnrollDialog').close();
    resetEnrollmentVisual();
  }

  function resetEnrollmentVisual() {
    const dialog = $('faceEnrollDialog'); const success = $('faceEnrollSuccess');
    if (dialog) dialog.dataset.state = 'ready';
    if (success) success.hidden = true;
    if ($('faceEnrollProgressFill')) $('faceEnrollProgressFill').style.width = '0%';
    if ($('faceEnrollStep')) $('faceEnrollStep').textContent = 'PRONTO PARA ESCANEAR';
  }

  function setEnrollmentProgress(captured, total = 8) {
    const percent = Math.round((captured / total) * 100);
    if ($('faceEnrollDialog')) $('faceEnrollDialog').dataset.state = 'scanning';
    if ($('faceEnrollProgressFill')) $('faceEnrollProgressFill').style.width = `${percent}%`;
    if ($('faceEnrollStep')) $('faceEnrollStep').textContent = `CAPTURA BIOMÉTRICA · ${captured}/${total}`;
  }

  async function prepareEnrollmentStage(text, stage, totalStages) {
    const instruction = $('faceEnrollInstruction'); const message = $('faceEnrollMessage');
    for (let remaining = 3; remaining >= 1; remaining -= 1) {
      instruction.textContent = `${text} · ${remaining}`;
      message.textContent = 'Mova o rosto com calma. A captura ainda não começou.';
      if ($('faceEnrollStep')) $('faceEnrollStep').textContent = `ETAPA ${stage}/${totalStages} · PREPARE-SE`;
      await wait(1000);
    }
    instruction.textContent = text;
    message.textContent = 'Agora mantenha esta posição por dois segundos.';
  }

  async function collectEnrollmentSamples() {
    const video = $('faceEnrollVideo'); const canvas = $('faceEnrollCanvas');
    const instruction = $('faceEnrollInstruction'); const message = $('faceEnrollMessage');
    const sequence = [
      ['center', 'OLHE DIRETAMENTE PARA A CÂMERA'],
      ['side', 'VIRE O ROSTO PARA UM DOS LADOS'],
      ['opposite', 'AGORA VIRE PARA O OUTRO LADO'],
      ['center', 'VOLTE A OLHAR PARA O CENTRO'],
    ];
    const samples = [];
    let firstSide = 0;
    for (let stageIndex = 0; stageIndex < sequence.length; stageIndex += 1) {
      const [step, text] = sequence[stageIndex];
      await prepareEnrollmentStage(text, stageIndex + 1, sequence.length);
      let stableFrames = 0;
      let stableSamples = [];
      const deadline = Date.now() + 45_000;
      while (stableFrames < 4) {
        if (Date.now() > deadline) throw new Error(`Não consegui confirmar esta posição. ${text.toLowerCase()} e tente novamente.`);
        await wait(560);
        const image_b64 = capture(video, canvas);
        const checked = await api('/api/biometria/enroll/check', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            camera_label: cameraLabel, image_b64, step, first_side: firstSide,
          }),
        });
        firstSide = Number(checked.first_side || firstSide || 0);
        if (!checked.accepted) {
          stableFrames = 0;
          stableSamples = [];
          message.textContent = `${checked.guidance || 'Ajuste seu rosto dentro do oval.'} · sem pressa`;
          if ($('faceEnrollStep')) $('faceEnrollStep').textContent = `ETAPA ${stageIndex + 1}/4 · AGUARDANDO POSIÇÃO`;
          continue;
        }
        stableFrames += 1;
        stableSamples.push(image_b64);
        message.textContent = 'Posição correta. Continue parado até completar.';
        if ($('faceEnrollStep')) $('faceEnrollStep').textContent = `MANTENHA A POSIÇÃO · ${stableFrames}/4`;
      }
      samples.push({ step, image_b64: stableSamples[0] });
      samples.push({ step, image_b64: stableSamples[stableSamples.length - 1] });
      setEnrollmentProgress(samples.length);
      instruction.textContent = 'ETAPA CONFIRMADA ✓';
      message.textContent = stageIndex < sequence.length - 1
        ? 'Pode relaxar. A próxima posição aparecerá em instantes.'
        : 'Prova de vida concluída. Salvando sua identidade local.';
      await wait(stageIndex < sequence.length - 1 ? 1500 : 700);
    }
    return samples;
  }

  async function enroll() {
    const button = $('faceEnrollStart');
    if (!stream) { await prepareEnrollmentCamera(); return; }
    const passphrase = $('faceEnrollPassphrase').value;
    if (!passphrase) { $('faceEnrollMessage').textContent = 'Digite sua frase para confirmar o cadastro.'; return; }
    button.disabled = true; button.textContent = 'CADASTRANDO';
    try {
      const samples = await collectEnrollmentSamples();
      const result = await api('/api/biometria/enroll', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase, camera_label: cameraLabel, samples }),
      });
      $('faceEnrollPassphrase').value = '';
      $('faceEnrollInstruction').textContent = 'ROSTO CADASTRADO';
      $('faceEnrollMessage').textContent = `${result.sample_count} amostras convertidas em um vetor cifrado local.`;
      $('faceEnrollDialog').dataset.state = 'success';
      $('faceEnrollProgressFill').style.width = '100%';
      $('faceEnrollStep').textContent = 'IDENTIDADE CONFIRMADA';
      $('faceEnrollSuccess').hidden = false;
      await wait(1400); closeEnrollment(); await status();
    } catch (error) {
      $('faceEnrollMessage').textContent = String(error.message || error);
      $('faceEnrollInstruction').textContent = 'CADASTRO NÃO CONCLUÍDO · TENTE NOVAMENTE';
    } finally { button.disabled = false; button.textContent = 'COMEÇAR'; }
  }

  function createGate() {
    let gate = $('facePresenceGate');
    if (gate) return gate;
    gate = document.createElement('section'); gate.id = 'facePresenceGate'; gate.className = 'face-gate';
    gate.innerHTML = `<div class="face-gate-card" data-state="scanning"><div class="face-gate-copy"><span class="core-kicker">BIOMETRIA DO DONO · PROCESSAMENTO LOCAL</span><h2>Olhe para o Condor</h2><p id="faceGateInstruction">PROCURANDO SEU ROSTO</p></div><div class="face-gate-viewport"><video id="faceGateVideo" autoplay playsinline muted></video><canvas id="faceGateCanvas" hidden></canvas><div class="face-biometric-shade"></div><div class="face-biometric-guide"><span class="face-scan-line"></span><i class="corner corner-tl"></i><i class="corner corner-tr"></i><i class="corner corner-bl"></i><i class="corner corner-br"></i></div><div class="face-progress"><span id="faceGateStep">ALINHE O ROSTO NA MOLDURA</span><b><i id="faceGateProgressFill"></i></b></div><div class="face-success" id="faceGateSuccess" hidden><span>✓</span><strong>OK</strong><small>ACESSO LIBERADO</small></div></div><div class="face-gate-actions"><button type="button" id="faceGateRetry">TENTAR NOVAMENTE</button><button type="button" id="faceGateRecovery">RECUPERAR COM FRASE</button></div><form class="face-recovery" id="faceRecoveryForm" hidden><input id="faceRecoveryPassphrase" type="password" autocomplete="off" spellcheck="false" data-1p-ignore="true" data-lpignore="true" placeholder="Digite manualmente a palavra de acesso"><button type="submit">DESATIVAR TRAVA E ENTRAR</button></form></div>`;
    document.body.appendChild(gate);
    $('faceGateRetry').addEventListener('click', runChallenge);
    $('faceGateRecovery').addEventListener('click', () => { $('faceRecoveryForm').hidden = false; $('faceRecoveryPassphrase').focus(); });
    $('faceRecoveryForm').addEventListener('submit', recoverWithPassphrase);
    return gate;
  }

  async function showGate(onRelease) {
    if (onRelease) releasing = onRelease;
    if (gateOpen) return;
    if (typeof CondorVoz !== 'undefined') CondorVoz.stopForSecurity();
    gateOpen = true;
    createGate();
    try { await openPhysicalCamera($('faceGateVideo')); await runChallenge(); }
    catch (error) {
      const card = $('facePresenceGate')?.querySelector('.face-gate-card');
      if (card) card.dataset.state = 'error';
      $('faceGateInstruction').textContent = `CÂMERA BLOQUEADA · ${error.message}`.toUpperCase();
    }
  }

  async function runChallenge() {
    if (challengeRunning) return;
    challengeRunning = true;
    const instruction = $('faceGateInstruction'); const video = $('faceGateVideo'); const canvas = $('faceGateCanvas');
    const card = $('facePresenceGate')?.querySelector('.face-gate-card');
    try {
      if (card) card.dataset.state = 'scanning';
      if ($('faceGateSuccess')) $('faceGateSuccess').hidden = true;
      if ($('faceGateProgressFill')) $('faceGateProgressFill').style.width = '4%';
      if (!stream) await openPhysicalCamera(video);
      let challenge = await api('/api/biometria/challenge', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ camera_label: cameraLabel }),
      });
      while (!challenge.verified && gateOpen) {
        instruction.textContent = challenge.instruction;
        const progress = Math.min(92, Math.round(((challenge.step_index || 0) / (challenge.total_steps || 4)) * 100) + (challenge.accepted ? 12 : 4));
        if ($('faceGateProgressFill')) $('faceGateProgressFill').style.width = `${progress}%`;
        if ($('faceGateStep')) $('faceGateStep').textContent = `PROVA DE VIDA · ETAPA ${(challenge.step_index || 0) + 1}/${challenge.total_steps || 4}`;
        await wait(520);
        challenge = await api('/api/biometria/challenge/frame', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: challenge.token, camera_label: cameraLabel, image_b64: capture(video, canvas) }),
        });
      }
      if (!challenge.verified) return;
      instruction.textContent = 'IDENTIDADE CONFIRMADA';
      if (card) card.dataset.state = 'success';
      if ($('faceGateProgressFill')) $('faceGateProgressFill').style.width = '100%';
      if ($('faceGateStep')) $('faceGateStep').textContent = 'IDENTIDADE CONFIRMADA';
      if ($('faceGateSuccess')) $('faceGateSuccess').hidden = false;
      await wait(1100);
      stopCamera();
      $('facePresenceGate')?.remove(); gateOpen = false;
      const release = releasing; releasing = null; if (release) release();
    } catch (error) {
      if (card) card.dataset.state = 'error';
      instruction.textContent = `VERIFICAÇÃO INTERROMPIDA · ${error.message}`.toUpperCase();
    } finally {
      challengeRunning = false;
    }
  }

  async function recoverWithPassphrase(event) {
    event.preventDefault();
    try {
      await api('/api/biometria/disable', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase: $('faceRecoveryPassphrase').value }),
      });
      stopCamera(); $('facePresenceGate')?.remove(); gateOpen = false;
      const release = releasing; releasing = null; if (release) release(); await status();
    } catch (error) { $('faceGateInstruction').textContent = `ACESSO NEGADO · ${error.message}`.toUpperCase(); }
  }

  async function disableFromSystem() {
    const passphrase = window.prompt('Digite sua frase de acesso para desativar a trava facial:');
    if (!passphrase) return;
    try {
      await api('/api/biometria/disable', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ passphrase }),
      });
      stopCamera(); await status();
    } catch (error) { CondorConversa.mostrarAviso(String(error.message || error).toUpperCase(), true); }
  }

  function init() {
    $('systemFaceEnroll')?.addEventListener('click', openEnrollment);
    $('systemFaceDisable')?.addEventListener('click', disableFromSystem);
    $('faceEnrollStart')?.addEventListener('click', enroll);
    $('faceEnrollClose')?.addEventListener('click', closeEnrollment);
    $('faceEnrollDialog')?.addEventListener('cancel', (event) => { event.preventDefault(); closeEnrollment(); });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) return;
      stopCamera();
      if (gateOpen && $('faceGateInstruction')) {
        $('faceGateInstruction').textContent = 'CÂMERA FECHADA · VOLTE E CLIQUE EM TENTAR NOVAMENTE';
      }
    });
    window.addEventListener('pagehide', stopCamera);
    window.addEventListener('condor-permission-resolved', (event) => {
      if (!awaitingEnrollmentPermission || event.detail?.capability !== 'camera') return;
      if (event.detail.decision === 'allow_always') openEnrollment();
      else awaitingEnrollmentPermission = false;
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true }); else init();
  return { status, showGate, openEnrollment };
})();
