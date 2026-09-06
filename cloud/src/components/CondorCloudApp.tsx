"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { Cloud, LogOut, MessageCircle, Monitor, NotebookPen, Plus, RefreshCw, Send, ShieldCheck, Smartphone, Trash2, Wifi, WifiOff } from "lucide-react";
import { browserSupabase } from "@/lib/supabase-browser";
import type { CloudConversation, CloudMessage, CloudNote } from "@/lib/cloud-data";

type Tab = "chat" | "notes" | "devices";
type Device = { id: string; device_key: string; name: string; kind: string; trust_state: string; capabilities: string[]; last_seen: string | null; created_at: string };

function localDeviceKey() {
  const stored = localStorage.getItem("condor-cloud-device-key");
  if (stored) return stored;
  const created = `web-${crypto.randomUUID()}`;
  localStorage.setItem("condor-cloud-device-key", created);
  return created;
}

export function CondorCloudApp() {
  const supabase = useMemo(() => browserSupabase(), []);
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [tab, setTab] = useState<Tab>("chat");
  const [conversations, setConversations] = useState<CloudConversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<CloudMessage[]>([]);
  const [notes, setNotes] = useState<CloudNote[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("CONECTANDO");
  const [noteTitle, setNoteTitle] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const api = useCallback(async (path: string, init?: RequestInit) => {
    if (!session?.access_token) throw new Error("sessao ausente");
    const response = await fetch(path, {
      ...init,
      cache: "no-store",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.access_token}`, ...(init?.headers || {}) },
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({})) as { error?: string };
      throw new Error(data.error || "operacao recusada");
    }
    return response;
  }, [session?.access_token]);

  const loadHistory = useCallback(async (selected?: string | null) => {
    const query = selected ? `?conversationId=${encodeURIComponent(selected)}` : "";
    const response = await api(`/api/history${query}`);
    const data = await response.json() as { conversations: CloudConversation[]; conversationId: string | null; messages: CloudMessage[] };
    setConversations(data.conversations); setConversationId(data.conversationId); setMessages(data.messages);
  }, [api]);

  const loadNotes = useCallback(async () => {
    const response = await api("/api/notes");
    const data = await response.json() as { notes: CloudNote[] };
    setNotes(data.notes);
  }, [api]);

  const loadDevices = useCallback(async () => {
    const response = await api("/api/devices");
    const data = await response.json() as { devices: Device[] };
    setDevices(data.devices);
  }, [api]);

  useEffect(() => {
    if (!supabase) { setAuthReady(true); return; }
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setAuthReady(true); });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => { setSession(next); setAuthReady(true); });
    return () => data.subscription.unsubscribe();
  }, [supabase]);

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!session) return;
    const deviceKey = localDeviceKey();
    api("/api/devices", { method: "POST", body: JSON.stringify({ deviceKey, name: navigator.userAgent.includes("Mobile") ? "Celular de Kaua" : "Navegador de Kaua", kind: navigator.userAgent.includes("Mobile") ? "phone" : "browser", capabilities: ["chat", "notes", "sync"] }) })
      .then(() => Promise.all([loadHistory(), loadNotes(), loadDevices()]))
      .then(() => setStatus("MENTE SINCRONIZADA"))
      .catch((error: Error) => setStatus(error.message.toUpperCase()));
  }, [api, loadDevices, loadHistory, loadNotes, session]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function login(event: React.FormEvent) {
    event.preventDefault(); setAuthError("");
    if (!supabase) { setAuthError("Variaveis do Supabase nao configuradas."); return; }
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    setPassword("");
    if (error) setAuthError("Login recusado. Verifique o usuario privado.");
  }

  async function logout() { await supabase?.auth.signOut(); setMessages([]); setNotes([]); setDevices([]); }

  async function sendMessage() {
    const text = message.trim();
    if (!text || busy) return;
    setMessage(""); setBusy(true); setStatus("CONDOR PENSANDO");
    const optimisticId = `local-${crypto.randomUUID()}`;
    const now = new Date().toISOString();
    setMessages((items) => [...items, { id: optimisticId, role: "user", content: text, createdAt: now }, { id: "streaming", role: "assistant", content: "", createdAt: now }]);
    try {
      const response = await api("/api/chat", { method: "POST", body: JSON.stringify({ message: text, conversationId: conversationId || undefined, clientMessageId: crypto.randomUUID(), deviceKey: localDeviceKey() }) });
      const reader = response.body?.getReader();
      if (!reader) throw new Error("stream indisponivel");
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";
        for (const block of blocks) {
          const event = block.match(/^event:\s*(.+)$/m)?.[1];
          const raw = block.match(/^data:\s*(.+)$/m)?.[1];
          if (!event || !raw) continue;
          const payload = JSON.parse(raw) as { text?: string; message?: string; conversationId?: string; note?: CloudNote };
          if (event === "meta" && payload.conversationId) { setConversationId(payload.conversationId); if (payload.note) setNotes((items) => [payload.note as CloudNote, ...items]); }
          if (event === "delta" && payload.text) setMessages((items) => items.map((item) => item.id === "streaming" ? { ...item, content: item.content + payload.text } : item));
          if (event === "error") throw new Error(payload.message || "resposta interrompida");
        }
      }
      await loadHistory(conversationId); await loadNotes(); setStatus("MENTE SINCRONIZADA");
    } catch (error) {
      setMessages((items) => items.map((item) => item.id === "streaming" ? { ...item, content: `Falha: ${error instanceof Error ? error.message : "indisponivel"}` } : item));
      setStatus("CONEXAO INTERROMPIDA");
    } finally { setBusy(false); }
  }

  async function createManualNote(event: React.FormEvent) {
    event.preventDefault();
    if (!noteTitle.trim() || !noteBody.trim()) return;
    await api("/api/notes", { method: "POST", body: JSON.stringify({ title: noteTitle, body: noteBody, clientEventId: crypto.randomUUID(), deviceKey: localDeviceKey() }) });
    setNoteTitle(""); setNoteBody(""); await loadNotes();
  }

  async function archiveNote(id: string) { await api(`/api/notes?id=${encodeURIComponent(id)}`, { method: "DELETE" }); await loadNotes(); }
  async function revokeDevice(deviceKey: string) { await api(`/api/devices?deviceKey=${encodeURIComponent(deviceKey)}`, { method: "DELETE" }); await loadDevices(); }

  if (!authReady) return <main className="boot"><div className="boot-mark">C</div><span>INICIANDO CONDOR AI CLOUD</span></main>;
  if (!session) return <main className="login-shell"><section className="login-card"><div className="brand-orb">C</div><small>CONDOR AI CLOUD · ACESSO PRIVADO</small><h1>A mesma mente.<br/>Em qualquer lugar.</h1><p>Entre com o usuário exclusivo do Condor. Não existe cadastro público.</p><form onSubmit={login}><label>E-MAIL<input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required/></label><label>SENHA<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required/></label><button type="submit">ENTRAR NO CONDOR</button></form><div className="auth-error" role="alert">{authError}</div><footer><ShieldCheck size={15}/> Conteúdo privado e cifrado no banco</footer></section></main>;

  const pc = devices.find((device) => device.kind === "desktop" && device.trust_state === "trusted");
  const pcOnline = Boolean(pc?.last_seen && Date.now() - new Date(pc.last_seen).getTime() < 90_000);

  return <main className="cloud-shell">
    <header className="app-header"><div className="app-brand"><div className="mini-orb">C</div><div><small>CONDOR AI CLOUD</small><strong>MESMA MENTE</strong></div></div><div className="cloud-state"><span className="live-dot"/>{status}</div><button className="icon-button" onClick={logout} title="Sair"><LogOut size={18}/></button></header>
    <aside className="sidebar"><button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}><MessageCircle/><span>Chat</span></button><button className={tab === "notes" ? "active" : ""} onClick={() => setTab("notes")}><NotebookPen/><span>Notas</span></button><button className={tab === "devices" ? "active" : ""} onClick={() => { setTab("devices"); void loadDevices(); }}><Smartphone/><span>Aparelhos</span></button><div className={`pc-state ${pcOnline ? "online" : ""}`}>{pcOnline ? <Wifi/> : <WifiOff/>}<div><strong>PC {pcOnline ? "ONLINE" : "OFFLINE"}</strong><small>{pcOnline ? "Ferramentas locais disponíveis" : "A mente cloud continua ativa"}</small></div></div></aside>

    <section className="workspace">
      {tab === "chat" && <div className="chat-layout"><aside className="conversation-list"><button className="new-chat" onClick={() => { setConversationId(null); setMessages([]); }}><Plus size={16}/> NOVA CONVERSA</button>{conversations.map((item) => <button key={item.id} className={item.id === conversationId ? "active" : ""} onClick={() => { setConversationId(item.id); void loadHistory(item.id); }}><strong>{item.title}</strong><small>{new Date(item.updatedAt).toLocaleDateString("pt-BR")}</small></button>)}</aside><section className="chat-panel"><div className="chat-heading"><div><small>CONDOR · CONVERSA CONTÍNUA</small><h1>{pcOnline ? "PC e celular sincronizados" : "O PC está desligado. Eu continuo aqui."}</h1></div><Cloud size={24}/></div><div className="message-stream">{messages.length === 0 && <div className="empty-chat"><div className="brand-orb small">C</div><h2>O que vamos construir hoje?</h2><p>Converse normalmente ou diga “Condor, anote...” para criar uma nota compartilhada.</p></div>}{messages.map((item) => <article key={item.id} className={`message ${item.role}`}><small>{item.role === "user" ? "VOCÊ" : "CONDOR"}</small><p>{item.content || (busy ? "Pensando..." : "")}</p></article>)}<div ref={bottomRef}/></div><div className="composer"><textarea value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} placeholder="Converse com o mesmo Condor do seu PC..." maxLength={8000}/><button disabled={busy || !message.trim()} onClick={() => void sendMessage()}><Send size={19}/></button></div></section></div>}

      {tab === "notes" && <section className="content-panel"><header className="section-head"><div><small>CAPTURA COMPARTILHADA</small><h1>Notas do Condor</h1><p>Tudo que você anotar aqui aparece no PC depois da sincronização.</p></div><NotebookPen/></header><form className="note-form" onSubmit={createManualNote}><input placeholder="Título da nota" value={noteTitle} onChange={(event) => setNoteTitle(event.target.value)} maxLength={160}/><textarea placeholder="Escreva a anotação..." value={noteBody} onChange={(event) => setNoteBody(event.target.value)} maxLength={16000}/><button>CRIAR NOTA</button></form><div className="note-grid">{notes.map((note) => <article key={note.id}><button title="Arquivar nota" onClick={() => void archiveNote(note.id)}><Trash2 size={15}/></button><small>{new Date(note.updatedAt).toLocaleString("pt-BR")}</small><h2>{note.title}</h2><p>{note.body}</p></article>)}</div></section>}

      {tab === "devices" && <section className="content-panel"><header className="section-head"><div><small>DEVICE MESH · CONFIANÇA</small><h1>Aparelhos conectados</h1><p>Cada aparelho pode ser revogado sem apagar sua memória.</p></div><button className="refresh" onClick={() => void loadDevices()}><RefreshCw/></button></header><div className="device-grid">{devices.map((device) => <article key={device.id}><div className="device-icon">{device.kind === "desktop" ? <Monitor/> : <Smartphone/>}</div><div><small>{device.kind.toUpperCase()}</small><h2>{device.name}</h2><p>{device.trust_state.toUpperCase()} · {device.last_seen ? `visto ${new Date(device.last_seen).toLocaleString("pt-BR")}` : "ainda não sincronizou"}</p><div className="capabilities">{device.capabilities.map((item) => <span key={item}>{item}</span>)}</div></div>{device.device_key !== localDeviceKey() && device.trust_state !== "revoked" && <button className="revoke" onClick={() => void revokeDevice(device.device_key)}>REVOGAR</button>}</article>)}</div></section>}
    </section>
  </main>;
}
