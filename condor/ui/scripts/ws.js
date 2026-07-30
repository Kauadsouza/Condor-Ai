/**
 * CondorWS — canal com o servidor, com reconexão automática.
 *
 * O servidor manda tudo com a chave "tipo". Cada módulo se inscreve no que
 * lhe interessa via CondorWS.ao('estado', fn). O '*' recebe tudo.
 */
const CondorWS = (() => {
  let ws = null;
  let timerReconexao = null;
  let tentativas = 0;
  const inscritos = {};
  const URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;

  function conectar() {
    ws = new WebSocket(URL);

    ws.onopen = () => {
      tentativas = 0;
      clearTimeout(timerReconexao);
      despachar('ws.ligado', {});
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        despachar(msg.tipo, msg);
      } catch (e) {
        console.error('[ws] mensagem inválida', e);
      }
    };

    ws.onclose = () => {
      despachar('ws.caiu', {});
      // Espera progressiva: 1s, 2s, 4s... até 10s. Evita martelar o servidor
      // enquanto ele ainda está subindo.
      const espera = Math.min(10000, 1000 * Math.pow(2, tentativas++));
      timerReconexao = setTimeout(conectar, espera);
    };

    ws.onerror = () => { /* o onclose já cuida da reconexão */ };
  }

  function despachar(tipo, msg) {
    (inscritos[tipo] || []).forEach(fn => fn(msg));
    (inscritos['*'] || []).forEach(fn => fn(msg));
  }

  function ao(tipo, fn) {
    (inscritos[tipo] = inscritos[tipo] || []).push(fn);
  }

  function enviar(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  }

  return {
    conectar,
    ao,
    enviar,
    mandarTexto: (texto) => enviar({ tipo: 'texto', texto }),
    mandarSenha: (texto) => enviar({ tipo: 'senha', texto }),
  };
})();
