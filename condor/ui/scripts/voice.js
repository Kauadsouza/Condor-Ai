/**
 * CondorVoz — o estado da voz na tela.
 *
 * Diferente da versão antiga, o microfone NÃO fica no navegador: quem escuta
 * é o servidor, o tempo todo, mesmo com a janela fechada. Aqui a gente só
 * reflete o que ele está fazendo e cuida do pedido de senha.
 */
const CondorVoz = (() => {
  const $ = (id) => document.getElementById(id);

  const ESTADOS = {
    dormindo: { rotulo: '● DORMINDO', cor: 'var(--text-dim)', dica: 'DIGA "CONDOR" PRA ME CHAMAR' },
    ouvindo:  { rotulo: '● NA ESCUTA', cor: 'var(--cyan)',    dica: 'PODE FALAR' },
    pensando: { rotulo: '● PENSANDO',  cor: 'var(--violet)',  dica: 'PROCESSANDO' },
    falando:  { rotulo: '● FALANDO',   cor: 'var(--cyan)',    dica: 'FALANDO' },
    senha:    { rotulo: '● SENHA',     cor: 'var(--pink)',    dica: 'CONFIRME A SENHA' },
  };

  let restam = 0;
  let relogio = null;
  let palavra = 'condor';

  function init() {
    CondorWS.ao('estado', aplicar);
    CondorWS.ao('tique', (m) => { restam = m.restam; pintarRelogio(); });
    CondorWS.ao('acordou', () => aplicar({ estado: 'ouvindo', acordado: true }));
    CondorWS.ao('dormiu', () => aplicar({ estado: 'dormindo', acordado: false }));
    CondorWS.ao('custo', pintarCusto);
    CondorWS.ao('memoria.stats', (m) => {
      $('tokenCount').textContent = `${m.fatos ?? 0} fatos · ${m.turnos ?? 0} turnos`;
    });
    CondorWS.ao('senha.pedido', pedirSenha);
    CondorWS.ao('senha.fim', fecharSenha);
    CondorWS.ao('ws.caiu', () => {
      $('listenStatus').textContent = 'SEM CONEXÃO';
      $('listenStatus').style.color = 'var(--pink)';
    });

    // Clicar no orbe acorda na marra — útil pra testar sem falar.
    $('voiceOrb').addEventListener('click', () => CondorWS.enviar({ tipo: 'acordar' }));

    relogio = setInterval(() => {
      if (restam > 0) { restam -= 1; pintarRelogio(); }
    }, 1000);
  }

  function aplicar(m) {
    const nome = m.estado || 'dormindo';
    const e = ESTADOS[nome] || ESTADOS.dormindo;

    const status = $('voiceStatus');
    status.textContent = e.rotulo;
    status.style.color = e.cor;

    $('orbCore').classList.toggle('active', nome === 'ouvindo' || nome === 'falando');
    $('frame').classList.toggle('is-dormindo', nome === 'dormindo');
    $('voiceHint').textContent = e.dica;

    if (m.palavra) palavra = m.palavra;
    if (typeof m.restam === 'number') restam = m.restam;
    if (m.modelo) $('modelName').textContent = m.modelo;

    if (m.escuta_ativa === false && m.motivo_escuta) {
      $('listenStatus').textContent = 'MICROFONE OFF';
      $('listenStatus').style.color = 'var(--pink)';
      $('voiceHint').textContent = `ESCUTA DESLIGADA — ${m.motivo_escuta.toUpperCase()}`;
    } else if (m.escuta_ativa) {
      $('listenStatus').style.color = 'var(--cyan)';
      pintarRelogio();
    }
    if (m.cerebro_pronto === false) {
      $('modelName').textContent = 'sem chave da OpenAI';
      $('modelName').style.color = 'var(--pink)';
    }
  }

  function pintarRelogio() {
    const alvo = $('listenStatus');
    if (restam > 0) {
      const min = Math.floor(restam / 60);
      const seg = String(restam % 60).padStart(2, '0');
      alvo.textContent = `DORME EM ${min}:${seg}`;
      alvo.style.color = restam <= 20 ? 'var(--amber)' : 'var(--cyan)';
    } else {
      alvo.textContent = `ESPERANDO "${palavra.toUpperCase()}"`;
      alvo.style.color = 'var(--text-dim)';
    }
  }

  function pintarCusto(m) {
    const el = $('custoHoje');
    if (el) el.textContent = `US$ ${(m.hoje_usd ?? 0).toFixed(3)} hoje`;
  }

  // ── Senha ─────────────────────────────────────────────────────────────

  function pedirSenha(m) {
    fecharSenha();
    const caixa = document.createElement('div');
    caixa.id = 'senhaBox';
    caixa.className = 'senha-box';
    caixa.innerHTML = `
      <div class="senha-titulo"><i class="ti ti-lock"></i> AÇÃO TRAVADA</div>
      <div class="senha-motivo"></div>
      <div class="senha-linha">
        <input id="senhaInput" type="password" placeholder="fale ou digite a senha" autocomplete="off">
        <button id="senhaOk">CONFIRMAR</button>
        <button id="senhaNao" class="secundario">CANCELAR</button>
      </div>
      <div class="senha-dica">pode responder falando — estou ouvindo</div>`;
    caixa.querySelector('.senha-motivo').textContent = m.motivo || '';
    document.getElementById('frame').appendChild(caixa);

    const campo = caixa.querySelector('#senhaInput');
    campo.focus();
    const mandar = () => {
      const v = campo.value.trim();
      if (v) { CondorWS.mandarSenha(v); fecharSenha(); }
    };
    caixa.querySelector('#senhaOk').addEventListener('click', mandar);
    caixa.querySelector('#senhaNao').addEventListener('click', () => {
      CondorWS.mandarSenha('cancelar');
      fecharSenha();
    });
    campo.addEventListener('keydown', (e) => { if (e.key === 'Enter') mandar(); });
  }

  function fecharSenha() {
    const antigo = document.getElementById('senhaBox');
    if (antigo) antigo.remove();
  }

  return { init, pedirSenha, fecharSenha };
})();
