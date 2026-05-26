/**
 * CondorWS — cliente WebSocket com reconexão automática.
 * Despacha eventos para os módulos registrados via CondorWS.on(type, handler).
 */
const CondorWS = (() => {
  let ws = null;
  let reconnectTimer = null;
  const handlers = {};
  const WS_URL = `ws://${location.host}/ws`;

  function connect() {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      console.log('[WS] conectado');
      clearTimeout(reconnectTimer);
      dispatch('ws.connected', {});
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        dispatch(msg.type, msg);
      } catch (e) {
        console.error('[WS] parse error', e);
      }
    };

    ws.onerror = (e) => {
      console.warn('[WS] erro', e);
    };

    ws.onclose = () => {
      console.log('[WS] desconectado — reconectando em 3s');
      dispatch('ws.disconnected', {});
      reconnectTimer = setTimeout(connect, 3000);
    };
  }

  function dispatch(type, msg) {
    (handlers[type] || []).forEach(fn => fn(msg));
    (handlers['*'] || []).forEach(fn => fn(msg));
  }

  function on(type, fn) {
    if (!handlers[type]) handlers[type] = [];
    handlers[type].push(fn);
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  }

  function sendText(text) {
    send({ type: 'text.message', text });
  }

  return { connect, on, send, sendText };
})();
