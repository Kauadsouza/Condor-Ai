/** Porta local do cofre do CONDOR. Sem modo de prévia ou acesso parcial. */
const CondorSeguranca = (() => {
  function ensureStyles() {
    if (document.getElementById('condorGateStyles')) return;
    const styles = document.createElement('style');
    styles.id = 'condorGateStyles';
    styles.textContent = `
      :root {
        --gate-cyan: #5ef7e7;
        --gate-magenta: #ff3bbd;
        --gate-violet: #705cff;
        --gate-ink: #02030a;
        --gate-panel: #080b18;
        --gate-line: rgba(94, 247, 231, .22);
      }
      html.condor-locked, html.condor-locked body { overflow: hidden !important; }
      #securitySetup {
        position: fixed;
        z-index: 9999;
        inset: 0;
        display: grid;
        place-items: center;
        overflow: auto;
        padding: 28px;
        color: #eefcff;
        background:
          radial-gradient(circle at 12% 18%, rgba(255, 59, 189, .15), transparent 25%),
          radial-gradient(circle at 86% 76%, rgba(94, 247, 231, .12), transparent 27%),
          linear-gradient(135deg, #02030a 0%, #070717 48%, #02050b 100%);
        font-family: Inter, system-ui, sans-serif;
        isolation: isolate;
      }
      #securitySetup::before {
        content: '';
        position: fixed;
        inset: 0;
        z-index: -2;
        background-image:
          linear-gradient(rgba(94, 247, 231, .035) 1px, transparent 1px),
          linear-gradient(90deg, rgba(94, 247, 231, .035) 1px, transparent 1px);
        background-size: 42px 42px;
        perspective: 500px;
        transform: scale(1.05);
      }
      #securitySetup::after {
        content: '';
        position: fixed;
        inset: 0;
        z-index: 8;
        pointer-events: none;
        opacity: .16;
        background: repeating-linear-gradient(0deg, transparent 0 3px, rgba(255,255,255,.04) 3px 4px);
        mix-blend-mode: screen;
      }
      .cyber-orbit {
        position: fixed;
        width: min(78vw, 980px);
        aspect-ratio: 1;
        border: 1px solid rgba(112, 92, 255, .12);
        border-radius: 50%;
        z-index: -1;
        animation: gate-spin 42s linear infinite;
      }
      .cyber-orbit::before, .cyber-orbit::after {
        content: '';
        position: absolute;
        border-radius: inherit;
        border: 1px dashed rgba(94, 247, 231, .12);
      }
      .cyber-orbit::before { inset: 11%; }
      .cyber-orbit::after { inset: 27%; border-color: rgba(255, 59, 189, .12); }
      @keyframes gate-spin { to { transform: rotate(360deg); } }
      @keyframes gate-scan { from { transform: translateY(-100%); } to { transform: translateY(900%); } }
      @keyframes gate-pulse { 50% { opacity: .38; box-shadow: 0 0 28px currentColor; } }
      @keyframes gate-shake { 20%, 60% { transform: translateX(-7px); } 40%, 80% { transform: translateX(7px); } }
      .cyber-gate {
        position: relative;
        width: min(920px, 100%);
        min-height: 510px;
        display: grid;
        grid-template-columns: minmax(260px, .82fr) minmax(360px, 1.18fr);
        overflow: hidden;
        border: 1px solid rgba(94, 247, 231, .34);
        border-radius: 3px 26px 3px 26px;
        background: rgba(5, 8, 19, .96);
        box-shadow:
          0 40px 120px rgba(0,0,0,.72),
          0 0 0 1px rgba(255,59,189,.08),
          0 0 70px rgba(112,92,255,.12);
        backdrop-filter: blur(24px);
      }
      .cyber-gate::before {
        content: '';
        position: absolute;
        left: 0;
        right: 0;
        top: 0;
        height: 2px;
        z-index: 6;
        background: linear-gradient(90deg, transparent, var(--gate-magenta), var(--gate-cyan), transparent);
        box-shadow: 0 0 16px rgba(94,247,231,.7);
        animation: gate-scan 7s linear infinite;
      }
      .cyber-identity {
        position: relative;
        display: grid;
        place-items: center;
        padding: 34px;
        border-right: 1px solid rgba(94,247,231,.14);
        background:
          linear-gradient(160deg, rgba(112,92,255,.12), transparent 46%),
          linear-gradient(25deg, rgba(255,59,189,.07), transparent 50%),
          #050817;
      }
      .cyber-identity::after {
        content: none;
      }
      .cyber-kicker, .cyber-label, .cyber-status, .cyber-meta, .cyber-error {
        font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
        text-transform: uppercase;
        letter-spacing: 2px;
      }
      .cyber-kicker { color: var(--gate-cyan); font-size: 9px; }
      .cyber-mark {
        position: relative;
        width: 124px;
        height: 124px;
        margin: 38px auto 30px;
        display: grid;
        place-items: center;
        color: var(--gate-cyan);
        border: 1px solid rgba(94,247,231,.4);
        border-radius: 50%;
        box-shadow: inset 0 0 34px rgba(94,247,231,.08), 0 0 34px rgba(94,247,231,.1);
      }
      .cyber-mark::before, .cyber-mark::after {
        content: '';
        position: absolute;
        border-radius: 50%;
      }
      .cyber-mark::before { inset: -12px; border: 1px dashed rgba(255,59,189,.36); animation: gate-spin 14s linear infinite reverse; }
      .cyber-mark::after { inset: 13px; border: 1px solid rgba(112,92,255,.42); }
      .cyber-mark span { position: relative; z-index: 2; font: 700 58px Georgia, serif; text-shadow: 0 0 28px rgba(94,247,231,.6); }
      .cyber-identity h2 { font-size: 25px; line-height: 1.08; letter-spacing: -.5px; }
      .cyber-identity p { margin-top: 10px; color: #77819d; font-size: 10px; line-height: 1.65; }
      .cyber-node {
        position: relative;
        z-index: 2;
        display: grid;
        gap: 7px;
      }
      .cyber-node span { display: flex; align-items: center; gap: 8px; color: #77819d; font: 8px ui-monospace, monospace; letter-spacing: 1.4px; }
      .cyber-node span::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: var(--gate-cyan); box-shadow: 0 0 9px var(--gate-cyan); }
      .cyber-auth { padding: 46px 48px; display: flex; flex-direction: column; justify-content: center; }
      .cyber-auth-header { margin-bottom: 30px; }
      .cyber-status { display: inline-flex; align-items: center; gap: 8px; color: var(--gate-magenta); font-size: 9px; }
      .cyber-status::before { content: ''; width: 7px; height: 7px; background: currentColor; box-shadow: 0 0 12px currentColor; animation: gate-pulse 1.8s ease-in-out infinite; }
      .cyber-auth h1 { margin-top: 12px; font-size: clamp(32px, 4vw, 48px); line-height: .95; letter-spacing: -2px; }
      .cyber-auth-header p { margin-top: 14px; max-width: 410px; color: #7f89a4; font-size: 11px; line-height: 1.65; }
      .cyber-form { display: grid; gap: 13px; }
      .cyber-form.denied { animation: gate-shake .34s ease; }
      .cyber-label { color: #9ca8c5; font-size: 8px; }
      .cyber-input-shell { position: relative; }
      .cyber-input-shell::before, .cyber-input-shell::after {
        content: '';
        position: absolute;
        width: 12px;
        height: 12px;
        pointer-events: none;
      }
      .cyber-input-shell::before { left: -1px; top: -1px; border-left: 2px solid var(--gate-magenta); border-top: 2px solid var(--gate-magenta); }
      .cyber-input-shell::after { right: -1px; bottom: -1px; border-right: 2px solid var(--gate-cyan); border-bottom: 2px solid var(--gate-cyan); }
      .cyber-input {
        width: 100%;
        outline: none;
        border: 1px solid rgba(112,92,255,.32);
        border-radius: 2px;
        padding: 15px 16px;
        color: #f3fbff;
        background: rgba(8,12,27,.9);
        font: 13px Inter, system-ui;
        letter-spacing: 1.5px;
        caret-color: var(--gate-cyan);
        transition: border-color .2s, box-shadow .2s, background .2s;
      }
      .cyber-input:focus { border-color: var(--gate-cyan); background: rgba(8,18,31,.96); box-shadow: 0 0 0 3px rgba(94,247,231,.07), inset 0 0 24px rgba(94,247,231,.025); }
      .cyber-input::placeholder { color: #454d68; letter-spacing: .5px; }
      .cyber-submit {
        position: relative;
        overflow: hidden;
        margin-top: 5px;
        border: 1px solid rgba(94,247,231,.62);
        border-radius: 2px;
        padding: 15px 18px;
        color: #02090b;
        background: linear-gradient(90deg, #53e9dc, #70ffe5);
        font: 800 10px ui-monospace, monospace;
        letter-spacing: 2.4px;
        cursor: pointer;
        box-shadow: 0 0 28px rgba(94,247,231,.14);
        transition: transform .18s, box-shadow .18s, filter .18s;
      }
      .cyber-submit::after { content: ''; position: absolute; inset: 0; transform: translateX(-110%); background: linear-gradient(100deg, transparent, rgba(255,255,255,.55), transparent); transition: transform .45s; }
      .cyber-submit:hover { transform: translateY(-2px); box-shadow: 0 0 34px rgba(94,247,231,.3); filter: saturate(1.2); }
      .cyber-submit:hover::after { transform: translateX(110%); }
      .cyber-submit:disabled { cursor: wait; filter: grayscale(.5); transform: none; }
      .cyber-error { min-height: 16px; color: #ff6fc7; font-size: 8px; line-height: 1.5; }
      .cyber-meta { display: flex; justify-content: space-between; gap: 12px; margin-top: 12px; color: #444d67; font-size: 7px; }
      .cyber-setup { width: min(980px, 100%); grid-template-columns: 260px minmax(440px, 1fr); }
      .cyber-setup .cyber-auth { padding: 34px 40px; }
      .cyber-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 11px; }
      .cyber-form-grid .wide { grid-column: 1 / -1; }
      .cyber-success { text-align: center; align-items: center; }
      @media (max-width: 760px) {
        #securitySetup { padding: 14px; align-items: start; }
        .cyber-gate, .cyber-setup { grid-template-columns: 1fr; min-height: auto; margin: auto 0; }
        .cyber-identity { min-height: 210px; border-right: 0; border-bottom: 1px solid rgba(94,247,231,.14); padding: 24px; }
        .cyber-mark { width: 82px; height: 82px; margin: 18px auto; }
        .cyber-mark span { font-size: 38px; }
        .cyber-node { display: none; }
        .cyber-auth, .cyber-setup .cyber-auth { padding: 30px 24px; }
        .cyber-form-grid { grid-template-columns: 1fr; }
        .cyber-form-grid .wide { grid-column: auto; }
      }
    `;
    document.head.appendChild(styles);
  }

  function blockInterface() {
    const frame = document.getElementById('frame');
    if (frame) {
      frame.setAttribute('inert', '');
      frame.setAttribute('aria-hidden', 'true');
    }
    document.documentElement.classList.add('condor-locked');
  }

  function releaseInterface(box) {
    const frame = document.getElementById('frame');
    if (frame) {
      frame.removeAttribute('inert');
      frame.removeAttribute('aria-hidden');
    }
    document.documentElement.classList.remove('condor-locked');
    box.remove();
  }

  function overlay(html, extraClass = '') {
    ensureStyles();
    blockInterface();
    let box = document.getElementById('securitySetup');
    if (!box) {
      box = document.createElement('div');
      box.id = 'securitySetup';
      document.body.appendChild(box);
    }
    box.innerHTML = `
      <div class="cyber-orbit" aria-hidden="true"></div>
      <section class="cyber-gate ${extraClass}" aria-label="Acesso seguro ao CONDOR">
        ${html}
      </section>`;
    return box;
  }

  function identityPanel() {
    return `
      <aside class="cyber-identity">
        <div class="cyber-mark" aria-hidden="true"><span>C</span></div>
      </aside>`;
  }

  function setupScreen() {
    const box = overlay(`
      ${identityPanel()}
      <main class="cyber-auth">
        <header class="cyber-auth-header">
          <div class="cyber-status">PRIMEIRO ACESSO</div>
          <h1>CRIAR<br>IDENTIDADE</h1>
          <p>Esta frase cifra o cofre e autoriza ações sensíveis. Não existe recuperação externa.</p>
        </header>
        <form id="securityForm" class="cyber-form">
          <div class="cyber-form-grid">
            <label><span class="cyber-label">PROPRIETÁRIO</span><div class="cyber-input-shell"><input class="cyber-input" name="owner" value="Kaua" placeholder="Nome do dono" required></div></label>
            <label><span class="cyber-label">MODELO LOCAL</span><div class="cyber-input-shell"><input class="cyber-input" name="localModel" value="qwen3:4b-instruct" placeholder="Modelo local"></div></label>
            <label><span class="cyber-label">PALAVRA DE ACESSO</span><div class="cyber-input-shell"><input class="cyber-input" name="passphrase" type="password" minlength="12" autocomplete="new-password" placeholder="Mínimo de 12 caracteres" required></div></label>
            <label><span class="cyber-label">CONFIRMAR PALAVRA</span><div class="cyber-input-shell"><input class="cyber-input" name="confirm" type="password" minlength="12" autocomplete="new-password" placeholder="Repita a palavra de acesso" required></div></label>
            <label><span class="cyber-label">API DE IA · OPCIONAL</span><div class="cyber-input-shell"><input class="cyber-input" name="openai" type="password" autocomplete="off" placeholder="Chave opcional"></div></label>
            <label><span class="cyber-label">WAKE WORD · OPCIONAL</span><div class="cyber-input-shell"><input class="cyber-input" name="picovoice" type="password" autocomplete="off" placeholder="Chave opcional"></div></label>
            <label class="wide"><span class="cyber-label">ENDPOINT LOCAL</span><div class="cyber-input-shell"><input class="cyber-input" name="localEndpoint" value="http://127.0.0.1:11434/v1" placeholder="Endpoint local Responses API"></div></label>
          </div>
          <button class="cyber-submit" type="submit">CRIAR COFRE DO CONDOR</button>
          <small class="cyber-error" id="securityError" role="alert"></small>
        </form>
      </main>`, 'cyber-setup');

    box.querySelector('#securityForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const formElement = event.currentTarget;
      const form = new FormData(formElement);
      const error = box.querySelector('#securityError');
      const submit = formElement.querySelector('button[type="submit"]');
      if (form.get('passphrase') !== form.get('confirm')) {
        error.textContent = 'ERRO // AS PALAVRAS DE ACESSO NÃO SÃO IGUAIS';
        formElement.classList.remove('denied');
        void formElement.offsetWidth;
        formElement.classList.add('denied');
        return;
      }
      submit.disabled = true;
      submit.textContent = 'CRIANDO IDENTIDADE...';
      error.textContent = '';
      try {
        const response = await fetch('/api/seguranca/configurar', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            owner: form.get('owner'), passphrase: form.get('passphrase'),
            openai_api_key: form.get('openai'), picovoice_access_key: form.get('picovoice'),
            local_model: form.get('localModel'), local_endpoint: form.get('localEndpoint'),
          }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.erro || 'Não foi possível criar o cofre.');
        box.querySelector('.cyber-gate').innerHTML = `
          ${identityPanel()}
          <main class="cyber-auth cyber-success">
            <div class="cyber-status">AUTORIZAÇÃO CONCLUÍDA</div>
            <h1>COFRE<br>ATIVO</h1>
            <p>O CONDOR agora pertence a este dispositivo.</p>
            <button id="enterCondor" class="cyber-submit" type="button">ENTRAR NO CONDOR</button>
          </main>`;
        box.querySelector('#enterCondor').addEventListener('click', () => releaseInterface(box));
      } catch (failure) {
        error.textContent = `ERRO // ${failure.message}`;
        formElement.classList.remove('denied');
        void formElement.offsetWidth;
        formElement.classList.add('denied');
        submit.disabled = false;
        submit.textContent = 'CRIAR COFRE DO CONDOR';
      }
    });
  }

  function unlockScreen() {
    const box = overlay(`
      ${identityPanel()}
      <main class="cyber-auth">
        <header class="cyber-auth-header">
          <div class="cyber-status">SISTEMA BLOQUEADO</div>
          <h1>IDENTIDADE<br>NECESSÁRIA</h1>
        </header>
        <form id="unlockForm" class="cyber-form">
          <label for="ownerPassphrase" class="cyber-label">PALAVRA DE ACESSO</label>
          <div class="cyber-input-shell">
            <input id="ownerPassphrase" class="cyber-input" name="passphrase" type="password" minlength="12" autocomplete="current-password" spellcheck="false" placeholder="Digite sua palavra de acesso" required>
          </div>
          <button class="cyber-submit" type="submit">AUTORIZAR ACESSO</button>
          <small class="cyber-error" id="unlockError" role="alert"></small>
        </form>
      </main>`);

    const formElement = box.querySelector('#unlockForm');
    const input = box.querySelector('#ownerPassphrase');
    requestAnimationFrame(() => input.focus());
    formElement.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submit = formElement.querySelector('button[type="submit"]');
      const error = box.querySelector('#unlockError');
      const passphrase = new FormData(formElement).get('passphrase');
      submit.disabled = true;
      submit.textContent = 'VALIDANDO IDENTIDADE...';
      error.textContent = '';
      try {
        const response = await fetch('/api/seguranca/desbloquear', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ passphrase }),
        });
        if (!response.ok) {
          const result = await response.json().catch(() => ({}));
          throw new Error(result.erro || 'Palavra incorreta ou cofre alterado.');
        }
        releaseInterface(box);
      } catch (failure) {
        error.textContent = `ACESSO NEGADO // ${failure.message}`;
        input.value = '';
        formElement.classList.remove('denied');
        void formElement.offsetWidth;
        formElement.classList.add('denied');
        submit.disabled = false;
        submit.textContent = 'AUTORIZAR ACESSO';
        input.focus();
      }
    });
  }

  async function init() {
    await CondorSession.ready;
    const state = await fetch('/api/seguranca/estado').then((response) => response.json());
    if (!state.owner_configured || !state.vault_exists) setupScreen();
    else if (!state.vault_unlocked) unlockScreen();
  }

  return { init };
})();
