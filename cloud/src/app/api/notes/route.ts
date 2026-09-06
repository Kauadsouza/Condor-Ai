import { NextResponse } from "next/server";
import { z } from "zod";
import { authFailure, requireCloudUser } from "@/lib/auth";
import { appendSyncEvent, createNote, listNotes } from "@/lib/cloud-data";
import { redactSecrets } from "@/lib/redaction";
import { CONDOR_MIND_ID } from "@/lib/identity";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const noteSchema = z.object({ title: z.string().trim().min(1).max(160), body: z.string().trim().min(1).max(16000), clientEventId: z.string().min(8).max(160).optional(), deviceKey: z.string().min(4).max(160).default("cloud-web") });

export async function GET(request: Request) {
  try {
    const { user, supabase } = await requireCloudUser(request);
    return NextResponse.json({ mindId: CONDOR_MIND_ID, notes: await listNotes(supabase, user.id) }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) { return authFailure(error) || NextResponse.json({ error: "notas indisponiveis" }, { status: 500 }); }
}

export async function POST(request: Request) {
  try {
    const { user, supabase } = await requireCloudUser(request);
    const parsed = noteSchema.safeParse(await request.json());
    if (!parsed.success) return NextResponse.json({ error: "nota invalida" }, { status: 400 });
    const title = redactSecrets(parsed.data.title).text;
    const body = redactSecrets(parsed.data.body).text;
    const note = await createNote(supabase, user.id, title, body);
    const eventId = parsed.data.clientEventId || `note-${note.id}`;
    await appendSyncEvent(supabase, user.id, eventId, parsed.data.deviceKey, "note", note);
    return NextResponse.json({ mindId: CONDOR_MIND_ID, note }, { status: 201 });
  } catch (error) { return authFailure(error) || NextResponse.json({ error: "nao foi possivel criar a nota" }, { status: 500 }); }
}

export async function DELETE(request: Request) {
  try {
    const { user, supabase } = await requireCloudUser(request);
    const id = new URL(request.url).searchParams.get("id");
    if (!id) return NextResponse.json({ error: "id ausente" }, { status: 400 });
    const { error } = await supabase.from("condor_notes").update({ archived_at: new Date().toISOString() }).eq("id", id).eq("user_id", user.id);
    if (error) throw error;
    return NextResponse.json({ mindId: CONDOR_MIND_ID, ok: true });
  } catch (error) { return authFailure(error) || NextResponse.json({ error: "nao foi possivel arquivar" }, { status: 500 }); }
}
