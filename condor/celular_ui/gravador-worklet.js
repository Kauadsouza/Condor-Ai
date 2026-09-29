// Roda na thread de áudio: só repassa os quadros do microfone, sem guardar nada.
class Gravador extends AudioWorkletProcessor {
  process(entradas) {
    const canal = entradas[0] && entradas[0][0];
    if (canal && canal.length) this.port.postMessage(canal.slice(0));
    return true;
  }
}
registerProcessor('condor-gravador', Gravador);
