/** Existing Sistema tab: resident preferences and owner-validated updates. */
(() => {
  const el=id=>document.getElementById(id);
  async function api(path, options={}) {
    const response=await fetch(path,{cache:'no-store',...options});
    const data=await response.json();
    if(!response.ok) throw new Error(data.erro || 'Não foi possível concluir.');
    return data;
  }
  async function refresh() {
    const state=await api('/api/assistant/status');
    el('residentState').textContent= !state.unlocked ? 'Núcleo ligado · desbloqueie seu cofre.' : `${state.modelo} · ${state.integrity_ok ? 'Integridade validada' : 'Atualização aguardando validação do dono'}. Disponível com o Windows ativo; suspensão e desligamento interrompem o núcleo.`;
    el('residentKeepOpen').checked=state.keep_window_open;
    el('residentKeepOpen').disabled=!state.unlocked;
    el('residentIntegrityForm').hidden=state.integrity_ok!==false;
    if(!state.unlocked) el('residentIntegrityPassword').value='';
  }
  window.addEventListener('DOMContentLoaded', async()=>{
    try { await CondorSession.ready; } catch { return; }
    const update=()=>refresh().catch(e=>{el('residentResult').textContent=e.message;});
    el('residentKeepOpen').addEventListener('change',async()=>{
      const input=el('residentKeepOpen');input.disabled=true;
      try { await api('/api/assistant/preferences',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({keep_window_open:input.checked})}); }
      catch(e) { el('residentResult').textContent=e.message; }
      finally { await update(); }
    });
    el('residentIntegrityForm').addEventListener('submit',async event=>{
      event.preventDefault();const button=event.submitter;button.disabled=true;
      try {
        await api('/api/seguranca/integridade/recriar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({passphrase:el('residentIntegrityPassword').value})});
        el('residentResult').textContent='Atualização validada. A detecção de alterações permanece ativa.';
      } catch(e) { el('residentResult').textContent=e.message; }
      finally { el('residentIntegrityPassword').value='';button.disabled=false;await update(); }
    });
    window.addEventListener('condor-security-ready',update);
    el('systemRefresh').addEventListener('click',update);
    await update();
    setInterval(()=>{if(CondorRouter.atual()==='sistema')void update();},15000);
  });
})();
