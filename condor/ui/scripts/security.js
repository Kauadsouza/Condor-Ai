/** Configuracao do cofre proprio e interruptor de emergencia. */
const CondorSeguranca = (() => {
  function overlay(html) {
    let box = document.getElementById('securitySetup');
    if (!box) {
      box = document.createElement('div');
      box.id = 'securitySetup';
      box.style.cssText = 'position:fixed;z-index:9999;inset:0;background:#02030af5;display:grid;place-items:center;padding:24px';
      document.body.appendChild(box);
    }
    box.innerHTML = `<section style="width:min(560px,100%);padding:28px;border:1px solid #564be0;border-radius:18px;background:#090b18;color:#eef;font-family:Inter,system-ui;box-shadow:0 25px 100px #000">${html}</section>`;
    return box;
  }

  function setPreviewMode(active, locked = false) {
    const input = document.getElementById('textInput');
    const send = document.getElementById('sendBtn');
    if (input) {
      input.disabled = active;
      input.placeholder = active
        ? (locked
          ? 'Prévia visual — desbloqueie o cofre para conversar com o Condor'
          : 'Prévia visual — crie o cofre para conversar com o Condor')
        : 'escreva aqui e pressione Enter...';
    }
    if (send) send.disabled = active;

    let banner = document.getElementById('condorPreviewBanner');
    if (!active) {
      if (banner) banner.remove();
      return;
    }
    if (!banner) {
      banner = document.createElement('aside');
      banner.id = 'condorPreviewBanner';
      banner.style.cssText = 'position:fixed;z-index:8500;left:50%;top:76px;transform:translateX(-50%);display:flex;align-items:center;gap:12px;padding:9px 12px;border:1px solid #8b7cff66;border-radius:10px;background:#090b18ee;color:#c9c6ff;font:600 10px Inter,system-ui;letter-spacing:1px;box-shadow:0 12px 40px #0008';
      banner.innerHTML = `<span>PRÉVIA VISUAL · ${locked ? 'COFRE BLOQUEADO' : 'COFRE AINDA NÃO CRIADO'}</span><button type="button" style="background:#594cff;color:white;border:0;border-radius:7px;padding:7px 10px;font:700 9px Inter;letter-spacing:1px;cursor:pointer">${locked ? 'DESBLOQUEAR' : 'CONFIGURAR AGORA'}</button>`;
      banner.querySelector('button').addEventListener('click', () => {
        banner.remove();
        if (locked) unlockScreen();
        else setupScreen();
      });
      document.body.appendChild(banner);
    }
  }

  function setupScreen() {
    const box = overlay(`
      <p style="letter-spacing:3px;color:#8b7cff;font-size:11px">CONDOR · PRIMEIRO ACESSO</p>
      <h1 style="margin:10px 0 8px">Crie a identidade do Condor</h1>
      <p style="color:#aeb3ca;line-height:1.55">Esta frase cifra o cofre e autoriza ações sensíveis. Ela não pertence ao Windows nem a qualquer empresa. Não existe recuperação externa.</p>
      <form id="securityForm" style="display:grid;gap:12px;margin-top:20px">
        <input name="owner" value="Kaua" placeholder="Nome do dono" required>
        <input name="passphrase" type="password" minlength="12" placeholder="Frase secreta (mínimo 12 caracteres)" required>
        <input name="confirm" type="password" minlength="12" placeholder="Repita a frase secreta" required>
        <input name="openai" type="password" placeholder="Chave da API de IA (opcional agora)">
        <input name="picovoice" type="password" placeholder="Chave da wake word (opcional agora)">
        <input name="localModel" value="qwen3:4b-instruct" placeholder="Modelo local (opcional, tem prioridade)">
        <input name="localEndpoint" value="http://127.0.0.1:11434/v1" placeholder="Endpoint local Responses API">
        <button type="submit">CRIAR COFRE DO CONDOR</button>
        <button type="button" id="previewCondor">VER A INTERFACE PRIMEIRO</button>
        <small style="color:#858ba8;text-align:center">A prévia não libera conversas, memória nem ações.</small>
        <small id="securityError" style="color:#ff8faf"></small>
      </form>`);
    box.querySelectorAll('input').forEach((input) => input.style.cssText = 'background:#11152a;border:1px solid #303653;border-radius:9px;padding:12px;color:#eef');
    box.querySelectorAll('button').forEach((button) => {
      button.style.cssText = 'background:#594cff;color:white;border:0;border-radius:9px;padding:13px;font-weight:700;cursor:pointer';
    });
    box.querySelector('#previewCondor').style.cssText = 'background:transparent;color:#aaa4ff;border:1px solid #393365;border-radius:9px;padding:12px;font-weight:700;cursor:pointer';
    box.querySelector('#previewCondor').addEventListener('click', () => {
      box.remove();
      setPreviewMode(true);
    });
    box.querySelector('#securityForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const error = box.querySelector('#securityError');
      if (form.get('passphrase') !== form.get('confirm')) {
        error.textContent = 'As frases secretas não são iguais.';
        return;
      }
      const response = await fetch('/api/seguranca/configurar', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          owner: form.get('owner'), passphrase: form.get('passphrase'),
          openai_api_key: form.get('openai'), picovoice_access_key: form.get('picovoice'),
          local_model: form.get('localModel'), local_endpoint: form.get('localEndpoint'),
        }),
      });
      const result = await response.json();
      if (!response.ok) { error.textContent = result.erro || 'Não foi possível criar o cofre.'; return; }
      box.innerHTML = '<section style="color:#eef;font-family:system-ui"><h2>Cofre criado.</h2><p>O Condor já pertence a este PC.</p><button id="enterCondor" style="background:#594cff;color:white;border:0;border-radius:9px;padding:13px">ENTRAR NO CONDOR</button></section>';
      box.querySelector('#enterCondor').addEventListener('click', () => {
        box.remove();
        setPreviewMode(false);
      });
    });
  }

  function unlockScreen() {
    const box = overlay(`
      <p style="letter-spacing:3px;color:#8b7cff;font-size:11px">CONDOR · COFRE BLOQUEADO</p>
      <h1>Desbloquear</h1><form id="unlockForm" style="display:grid;gap:12px">
      <input name="passphrase" type="password" minlength="12" placeholder="Sua frase secreta" required style="background:#11152a;border:1px solid #303653;border-radius:9px;padding:12px;color:#eef">
      <button type="submit" style="background:#594cff;color:white;border:0;border-radius:9px;padding:13px">DESBLOQUEAR</button>
      <button type="button" id="previewLockedCondor" style="background:transparent;color:#aaa4ff;border:1px solid #393365;border-radius:9px;padding:12px;font-weight:700;cursor:pointer">VER O APP BLOQUEADO</button>
      <small id="unlockError" style="color:#ff8faf"></small></form>`);
    box.querySelector('#previewLockedCondor').addEventListener('click', () => {
      box.remove();
      setPreviewMode(true, true);
    });
    box.querySelector('#unlockForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const passphrase = new FormData(event.currentTarget).get('passphrase');
      const response = await fetch('/api/seguranca/desbloquear', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase }),
      });
      if (response.ok) box.remove();
      else box.querySelector('#unlockError').textContent = 'Frase incorreta ou cofre alterado.';
    });
  }

  async function init() {
    await CondorSession.ready;
    const state = await fetch('/api/seguranca/estado').then((response) => response.json());
    if (!state.owner_configured || !state.vault_exists) setupScreen();
    else if (!state.vault_unlocked) unlockScreen();

    const stop = document.createElement('button');
    stop.textContent = '■ PARAR CONDOR';
    stop.title = 'Bloqueia imediatamente todas as ferramentas';
    stop.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:8000;background:#2b0c18;color:#ff8faf;border:1px solid #7f2444;border-radius:9px;padding:9px 12px;font:700 10px Inter;letter-spacing:1px;cursor:pointer';
    function setStopped(stopped) {
      stop.dataset.stopped = stopped ? '1' : '0';
      stop.textContent = stopped ? '▶ RETOMAR CONDOR' : '■ PARAR CONDOR';
      stop.style.background = stopped ? '#172a1d' : '#2b0c18';
      stop.style.color = stopped ? '#89f0ac' : '#ff8faf';
    }
    setStopped(Boolean(state.emergency_stop));
    stop.addEventListener('click', async () => {
      if (stop.dataset.stopped === '0') {
        await fetch('/api/emergencia/parar', { method: 'POST' });
        setStopped(true);
        return;
      }
      const passphrase = window.prompt('Digite sua frase secreta para retomar o Condor:');
      if (!passphrase) return;
      const response = await fetch('/api/emergencia/retomar', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase }),
      });
      if (response.ok) {
        setStopped(false);
        window.location.reload();
      }
      else window.alert('Frase secreta incorreta. O Condor continua parado.');
    });
    document.body.appendChild(stop);
  }
  return { init };
})();
