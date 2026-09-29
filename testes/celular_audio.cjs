// O WAV que o iPhone manda precisa sair 16 kHz mono PCM16, do tamanho certo.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function carregar() {
  const codigo = fs.readFileSync(path.join(__dirname, '..', 'condor', 'celular_ui', 'audio.js'), 'utf8');
  const contexto = { window: {}, navigator: {}, performance: { now: () => 0 }, atob, btoa, console };
  vm.createContext(contexto);
  vm.runInContext(`${codigo}\nthis.CondorAudio = CondorAudio;`, contexto);
  return contexto.CondorAudio;
}

test('fala de 1 s a 48 kHz vira WAV 16 kHz mono PCM16', () => {
  const audio = carregar();
  const bloco = new Float32Array(48000);
  for (let i = 0; i < bloco.length; i += 1) bloco[i] = Math.sin((2 * Math.PI * 220 * i) / 48000) * 0.5;
  const bytes = Buffer.from(audio.paraWav([bloco], 48000), 'base64');
  assert.strictEqual(bytes.toString('ascii', 0, 4), 'RIFF');
  assert.strictEqual(bytes.toString('ascii', 8, 12), 'WAVE');
  assert.strictEqual(bytes.readUInt16LE(22), 1);           // mono
  assert.strictEqual(bytes.readUInt32LE(24), 16000);       // 16 kHz
  assert.strictEqual(bytes.readUInt16LE(34), 16);          // 16 bits
  assert.strictEqual(bytes.readUInt32LE(40), 16000 * 2);   // 1 s de amostras
  const pico = Math.max(...Array.from({ length: 200 }, (_, i) => Math.abs(bytes.readInt16LE(44 + i * 2))));
  assert.ok(pico > 10000 && pico < 17000, `pico ${pico}`);
});

test('44,1 kHz também reamostra para 16 kHz', () => {
  const audio = carregar();
  const bytes = Buffer.from(audio.paraWav([new Float32Array(44100), new Float32Array(22050)], 44100), 'base64');
  assert.strictEqual(bytes.readUInt32LE(24), 16000);
  assert.ok(Math.abs(bytes.readUInt32LE(40) / 2 - 24000) <= 2);
});
