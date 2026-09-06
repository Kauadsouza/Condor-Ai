import { NextResponse } from "next/server";
import { z } from "zod";
import { authFailure, requireCloudUser } from "@/lib/auth";
import { appendSyncEvent, listSyncEvents } from "@/lib/cloud-data";
import { seal } from "@/lib/crypto";
import { redactSecrets } from "@/lib/redaction";
import { CONDOR_MIND_ID } from "@/lib/identity";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const base = z.object({ clientEventId: z.string().min(8).max(180), type: z.enum(["message", "fact", "note"]) });
const messageEvent = base.extend({ type: z.literal("message"), payload: z.object({ originId: z.string().min(1).max(180), conversationOriginId: z.string().min(1).max(180).default("desktop-primary"), role: z.enum(["user", "assistant"]), content: z.string().max(8000), createdAt: z.string().datetime().optional() }) });
const factEvent = base.extend({ type: z.literal("fact"), payload: z.object({ originId: z.string().min(1).max(180), category: z.string().min(1).max(40), key: z.string().min(1).max(80), value: z.string().max(2000), confidence: z.number().min(0).max(1).default(0.8), updatedAt: z.string().datetime().optional() }) });
const noteEvent = base.extend({ type: z.literal("note"), payload: z.object({ originId: z.string().min(1).max(180), title: z.string().min(1).max(160), body: z.string().min(1).max(16000), updatedAt: z.string().datetime().optional() }) });
const syncSchema = z.object({ deviceKey: z.string().min(8).max(160), events: z.array(z.discriminatedUnion("type", [messageEvent, factEvent, noteEvent])).max(500) });

async function trustedDevice(supabase: Awaited<ReturnType<typeof requireCloudUser>>["supabase"], userId: string, deviceKey: string) {
  const { data } = await supabase.from("condor_devices").select("trust_state").eq("user_id", userId).eq("device_key", deviceKey).maybeSingle();
  return data?.trust_state === "trusted";
}

export async function GET(request: Request) {
  try {
    const { user, supabase } = await requireCloudUser(request);
    const url = new URL(request.url);
    const deviceKey = url.searchParams.get("deviceKey") || "";
    if (!(await trustedDevice(supabase, user.id, deviceKey))) return NextResponse.json({ error: "dispositivo nao confiavel" }, { status: 403 });
    await supabase.from("condor_devices").update({ last_seen: new Date().toISOString() }).eq("user_id", user.id).eq("device_key", deviceKey);
    const events = await listSyncEvents(supabase, user.id, Number(url.searchParams.get("since") || 0));
    return NextResponse.json({ mindId: CONDOR_MIND_ID, events, cursor: events.at(-1)?.sequence || Number(url.searchParams.get("since") || 0) }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) { return authFailure(error) || NextResponse.json({ error: "sincronizacao indisponivel" }, { status: 500 }); }
}

export async function POST(request: Request) {
  try {
    const { user, supabase } = await requireCloudUser(request);
    const parsed = syncSchema.safeParse(await request.json());
    if (!parsed.success) return NextResponse.json({ error: "lote de sincronizacao invalido", detail: parsed.error.issues.slice(0, 4) }, { status: 400 });
    if (!(await trustedDevice(supabase, user.id, parsed.data.deviceKey))) return NextResponse.json({ error: "dispositivo nao confiavel" }, { status: 403 });

    const importedConversations = new Map<string, string>();
    let accepted = 0;
    for (const event of parsed.data.events) {
      const { data: duplicate } = await supabase.from("condor_sync_events").select("sequence").eq("user_id", user.id).eq("client_event_id", event.clientEventId).maybeSingle();
      if (duplicate) continue;

      if (event.type === "message") {
        const conversationOrigin = event.payload.conversationOriginId;
        let importedConversation = importedConversations.get(conversationOrigin) || null;
        if (!importedConversation) {
          const { data: existing } = await supabase.from("condor_conversations").select("id").eq("user_id", user.id).eq("origin_device", parsed.data.deviceKey).eq("origin_id", event.payload.conversationOriginId).maybeSingle();
          if (existing?.id) importedConversation = String(existing.id);
          else {
            const { data, error } = await supabase.from("condor_conversations").insert({ user_id: user.id, title_ciphertext: seal("Conversa sincronizada do PC"), origin_device: parsed.data.deviceKey, origin_id: event.payload.conversationOriginId }).select("id").single();
            if (error || !data) throw error || new Error("conversa importada nao criada");
            importedConversation = String(data.id);
          }
          importedConversations.set(conversationOrigin, importedConversation);
        }
        const content = redactSecrets(event.payload.content).text;
        const { error } = await supabase.from("condor_messages").upsert({
          user_id: user.id, conversation_id: importedConversation, role: event.payload.role,
          content_ciphertext: seal(content), origin_device: parsed.data.deviceKey, origin_id: event.payload.originId,
          created_at: event.payload.createdAt || new Date().toISOString(),
        }, { onConflict: "user_id,origin_device,origin_id", ignoreDuplicates: true });
        if (error) throw error;
        await appendSyncEvent(supabase, user.id, event.clientEventId, parsed.data.deviceKey, "message", { ...event.payload, content, conversationId: importedConversation });
      } else if (event.type === "fact") {
        const value = redactSecrets(event.payload.value).text;
        const { error } = await supabase.from("condor_facts").upsert({
          user_id: user.id, category: event.payload.category, fact_key: event.payload.key,
          value_ciphertext: seal(value), confidence: event.payload.confidence, origin: parsed.data.deviceKey,
          updated_at: event.payload.updatedAt || new Date().toISOString(),
        }, { onConflict: "user_id,category,fact_key" });
        if (error) throw error;
        await appendSyncEvent(supabase, user.id, event.clientEventId, parsed.data.deviceKey, "fact", { ...event.payload, value });
      } else {
        const title = redactSecrets(event.payload.title).text;
        const body = redactSecrets(event.payload.body).text;
        const { error } = await supabase.from("condor_notes").upsert({
          user_id: user.id, title_ciphertext: seal(title), body_ciphertext: seal(body),
          origin_device: parsed.data.deviceKey, origin_id: event.payload.originId,
          updated_at: event.payload.updatedAt || new Date().toISOString(),
        }, { onConflict: "user_id,origin_device,origin_id" });
        if (error) throw error;
        await appendSyncEvent(supabase, user.id, event.clientEventId, parsed.data.deviceKey, "note", { ...event.payload, title, body });
      }
      accepted += 1;
    }
    await supabase.from("condor_devices").update({ last_seen: new Date().toISOString() }).eq("user_id", user.id).eq("device_key", parsed.data.deviceKey);
    return NextResponse.json({ mindId: CONDOR_MIND_ID, accepted, skipped: parsed.data.events.length - accepted });
  } catch (error) { return authFailure(error) || NextResponse.json({ error: error instanceof Error ? error.message : "sincronizacao recusada" }, { status: 500 }); }
}
