const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
function setup(permission, getUserMedia) {
  const nodes=new Map(), events={}, windowEvents={};
  const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',style:{},classList:{add(){},toggle(){}},setAttribute(){},addEventListener(name,fn){this[name]=fn;}});return nodes.get(id);};
  const context={document:{getElementById:node,addEventListener(){}},window:{addEventListener(name,fn){windowEvents[name]=fn;},MediaRecorder:true},navigator:{mediaDevices:{getUserMedia}},CondorWS:{ao(name,fn){events[name]=fn;},enviar(){}},CondorMedia:{ensurePermission:permission},setInterval(){return 1;},clearInterval(){},setTimeout(){return 1;},clearTimeout(){},console};
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../condor/ui/scripts/voice.js'),'utf8')+';CondorVoz.init();globalThis.voice=CondorVoz;',context);
  return {context,node,events,windowEvents};
}
test('failed permission lookup never opens microphone or leaves continuous mode enabled',async()=>{
  let captures=0;const s=setup(async()=>{throw Error('locked');},async()=>{captures++;});
  await s.node('continuousVoiceBtn').click();
  assert.equal(captures,0);assert.equal(s.node('continuousVoiceBtn').textContent,'CONVERSA CONTÍNUA');
});
test('a late browser microphone grant is closed after lock',async()=>{
  let resolveCapture,stopped=0;
  const s=setup(async()=>true,()=>new Promise(resolve=>{resolveCapture=resolve;}));
  const pending=s.node('continuousVoiceBtn').click();
  for(let i=0;i<5&&!resolveCapture;i++) await Promise.resolve();
  s.events['seguranca.bloqueado']();
  resolveCapture({getTracks:()=>[{stop(){stopped++;}}]});await pending;
  assert.equal(stopped,1);assert.equal(s.node('continuousVoiceBtn').textContent,'CONVERSA CONTÍNUA');
});
test('continuous voice explicitly requests persistent permission in existing Sistema flow',async()=>{
  let options;const s=setup(async(...args)=>{options=args[3];return false;},async()=>{throw Error('must not capture');});
  await s.node('continuousVoiceBtn').click();assert.equal(options.requireAlways,true);
  s.events['ws.caiu']();assert.equal(s.node('continuousVoiceBtn').textContent,'CONVERSA CONTÍNUA');
});
