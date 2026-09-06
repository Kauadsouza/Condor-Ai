import type { SupabaseClient } from "@supabase/supabase-js";
import { seal, sealJson, unseal, unsealJson } from "@/lib/crypto";

export type CloudMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
};

export type CloudConversation = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
};

export type CloudNote = {
  id: string;
  title: string;
  body: string;
  createdAt: string;
  updatedAt: string;
};

type ConversationRow = { id: string; title_ciphertext: string; created_at: string; updated_at: string };
type MessageRow = { id: string; role: "user" | "assistant"; content_ciphertext: string; created_at: string };
type NoteRow = { id: string; title_ciphertext: string; body_ciphertext: string; created_at: string; updated_at: string };

function safeOpen(value: string): string {
  try { return unseal(value); } catch { return "[CONTEUDO CIFRADO INDISPONIVEL]"; }
}

export async function listConversations(supabase: SupabaseClient, userId: string): Promise<CloudConversation[]> {
  const { data, error } = await supabase
    .from("condor_conversations")
    .select("id,title_ciphertext,created_at,updated_at")
    .eq("user_id", userId)
    .is("archived_at", null)
    .order("updated_at", { ascending: false })
    .limit(40);
  if (error) throw error;
  return ((data || []) as ConversationRow[]).map((row) => ({
    id: row.id,
    title: safeOpen(row.title_ciphertext),
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }));
}

export async function ensureConversation(
  supabase: SupabaseClient,
  userId: string,
  conversationId: string | undefined,
  firstMessage: string,
): Promise<string> {
  if (conversationId) {
    const { data } = await supabase.from("condor_conversations").select("id").eq("user_id", userId).eq("id", conversationId).maybeSingle();
    if (data?.id) return String(data.id);
  }
  const title = firstMessage.replace(/\s+/g, " ").slice(0, 72) || "Nova conversa";
  const { data, error } = await supabase
    .from("condor_conversations")
    .insert({ user_id: userId, title_ciphertext: seal(title) })
    .select("id")
    .single();
  if (error || !data) throw error || new Error("conversa nao criada");
  return String(data.id);
}

export async function listMessages(
  supabase: SupabaseClient,
  userId: string,
  conversationId: string,
  limit = 80,
): Promise<CloudMessage[]> {
  const { data, error } = await supabase
    .from("condor_messages")
    .select("id,role,content_ciphertext,created_at")
    .eq("user_id", userId)
    .eq("conversation_id", conversationId)
    .order("created_at", { ascending: false })
    .limit(Math.min(Math.max(limit, 1), 200));
  if (error) throw error;
  return ((data || []) as MessageRow[]).reverse().map((row) => ({
    id: row.id,
    role: row.role,
    content: safeOpen(row.content_ciphertext),
    createdAt: row.created_at,
  }));
}

export async function insertMessage(
  supabase: SupabaseClient,
  userId: string,
  conversationId: string,
  role: "user" | "assistant",
  content: string,
  clientMessageId?: string,
): Promise<{ id: string; createdAt: string }> {
  if (clientMessageId) {
    const { data: existing } = await supabase
      .from("condor_messages")
      .select("id,created_at")
      .eq("user_id", userId)
      .eq("client_message_id", clientMessageId)
      .maybeSingle();
    if (existing) return { id: String(existing.id), createdAt: String(existing.created_at) };
  }
  const { data, error } = await supabase
    .from("condor_messages")
    .insert({
      user_id: userId,
      conversation_id: conversationId,
      role,
      content_ciphertext: seal(content),
      client_message_id: clientMessageId || null,
    })
    .select("id,created_at")
    .single();
  if (error || !data) throw error || new Error("mensagem nao salva");
  await supabase.from("condor_conversations").update({ updated_at: new Date().toISOString() }).eq("id", conversationId).eq("user_id", userId);
  return { id: String(data.id), createdAt: String(data.created_at) };
}

export async function appendSyncEvent(
  supabase: SupabaseClient,
  userId: string,
  clientEventId: string,
  deviceKey: string,
  eventType: "message" | "fact" | "note" | "conversation" | "device",
  payload: unknown,
): Promise<void> {
  const { error } = await supabase.from("condor_sync_events").upsert({
    user_id: userId,
    client_event_id: clientEventId,
    device_key: deviceKey,
    event_type: eventType,
    payload_ciphertext: sealJson(payload),
  }, { onConflict: "user_id,client_event_id", ignoreDuplicates: true });
  if (error) throw error;
}

export async function memoryContext(supabase: SupabaseClient, userId: string): Promise<string> {
  const [factsResult, notesResult] = await Promise.all([
    supabase.from("condor_facts").select("category,fact_key,value_ciphertext,confidence").eq("user_id", userId).order("updated_at", { ascending: false }).limit(30),
    supabase.from("condor_notes").select("title_ciphertext,body_ciphertext").eq("user_id", userId).is("archived_at", null).order("updated_at", { ascending: false }).limit(10),
  ]);
  if (factsResult.error) throw factsResult.error;
  if (notesResult.error) throw notesResult.error;
  const facts = (factsResult.data || []).map((row) => `- [${String(row.category)}] ${String(row.fact_key)}: ${safeOpen(String(row.value_ciphertext))}`);
  const notes = (notesResult.data || []).map((row) => `- NOTA ${safeOpen(String(row.title_ciphertext))}: ${safeOpen(String(row.body_ciphertext)).slice(0, 600)}`);
  return [...facts, ...notes].join("\n").slice(0, 12000);
}

export function extractNoteIntent(text: string): { title: string; body: string } | null {
  const match = String(text || "").match(/^\s*(?:condor[,\s]*)?(?:anote|anota|guarde como nota|crie uma nota)\s*(?:isso)?\s*[:,-]?\s*(.+)$/i);
  if (!match?.[1]?.trim()) return null;
  const body = match[1].trim().slice(0, 8000);
  return { title: body.replace(/\s+/g, " ").slice(0, 72), body };
}

export async function createNote(
  supabase: SupabaseClient,
  userId: string,
  title: string,
  body: string,
  sourceMessageId?: string,
): Promise<CloudNote> {
  const { data, error } = await supabase.from("condor_notes").insert({
    user_id: userId,
    title_ciphertext: seal(title.slice(0, 160)),
    body_ciphertext: seal(body.slice(0, 16000)),
    source_message_id: sourceMessageId || null,
  }).select("id,title_ciphertext,body_ciphertext,created_at,updated_at").single();
  if (error || !data) throw error || new Error("nota nao criada");
  const row = data as NoteRow;
  return { id: row.id, title: safeOpen(row.title_ciphertext), body: safeOpen(row.body_ciphertext), createdAt: row.created_at, updatedAt: row.updated_at };
}

export async function listNotes(supabase: SupabaseClient, userId: string): Promise<CloudNote[]> {
  const { data, error } = await supabase.from("condor_notes")
    .select("id,title_ciphertext,body_ciphertext,created_at,updated_at")
    .eq("user_id", userId).is("archived_at", null).order("updated_at", { ascending: false }).limit(100);
  if (error) throw error;
  return ((data || []) as NoteRow[]).map((row) => ({ id: row.id, title: safeOpen(row.title_ciphertext), body: safeOpen(row.body_ciphertext), createdAt: row.created_at, updatedAt: row.updated_at }));
}

export async function listSyncEvents(supabase: SupabaseClient, userId: string, since: number) {
  const { data, error } = await supabase.from("condor_sync_events")
    .select("sequence,client_event_id,device_key,event_type,payload_ciphertext,created_at")
    .eq("user_id", userId).gt("sequence", Math.max(0, since)).order("sequence", { ascending: true }).limit(500);
  if (error) throw error;
  return (data || []).map((row) => ({
    sequence: Number(row.sequence), clientEventId: String(row.client_event_id), deviceKey: String(row.device_key),
    type: String(row.event_type), payload: unsealJson<unknown>(String(row.payload_ciphertext)), createdAt: String(row.created_at),
  }));
}
