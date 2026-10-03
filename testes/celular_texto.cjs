// Texto formatado no celular: negrito, listas e código, sem deixar HTML passar.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const contexto = {};
vm.createContext(contexto);
vm.runInContext(`${fs.readFileSync(path.join(__dirname, '..', 'condor', 'celular_ui', 'texto.js'), 'utf8')}\nthis.T = CondorTexto;`, contexto);
const html = (texto) => contexto.T.html(texto);

test('formata negrito, lista, código e link', () => {
  const saida = html('**Oi**\n- um\n- dois\n```js\nconst a = 1;\n```\nveja https://exemplo.com');
  assert.match(saida, /<strong>Oi<\/strong>/);
  assert.match(saida, /<ul><li>um<\/li><li>dois<\/li><\/ul>/);
  assert.match(saida, /<pre><code>const a = 1;<\/code><\/pre>/);
  assert.match(saida, /<a href="https:\/\/exemplo.com" target="_blank" rel="noopener noreferrer">/);
});

test('HTML e javascript: nunca passam', () => {
  const saida = html('<img src=x onerror=alert(1)> [clique](javascript:alert(1)) <script>x</script>');
  assert.doesNotMatch(saida, /<img|<script|href="javascript/);
  assert.match(saida, /&lt;img/);
});

test('aspas não quebram o atributo do link', () => {
  const saida = html('https://a.com/"onmouseover="x');
  assert.doesNotMatch(saida, /" onmouseover=/);
});
