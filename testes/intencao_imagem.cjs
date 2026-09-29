// Pedido de imagem no chat x pergunta sobre a capacidade de gerar imagem.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const contexto = {
  window: { addEventListener() {} },
  document: { readyState: 'complete', addEventListener() {}, getElementById() {} },
  console,
};
vm.createContext(contexto);
vm.runInContext(`${fs.readFileSync(path.join(__dirname, '..', 'condor', 'ui', 'scripts', 'media.js'), 'utf8')}\nthis.M = CondorMedia;`, contexto);

const casos = {
  'voce consegue gerar imagem?': false,
  'você sabe criar imagens?': false,
  'essa img que vc gerou e do deus verdadeiro ?': false,
  'gere a IMG do rosto de Deus': true,
  'pode gerar uma imagem de um gato astronauta?': true,
  'Condor, cria uma imagem de um dragão': true,
  'gera imagem': true,
};

for (const [frase, esperado] of Object.entries(casos)) {
  test(`"${frase}" -> ${esperado ? 'gera' : 'conversa'}`, () => {
    assert.strictEqual(contexto.M.imageIntent(frase), esperado);
  });
}
