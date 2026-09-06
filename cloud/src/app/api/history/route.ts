import { NextResponse } from "next/server";
import { authFailure, requireCloudUser } from "@/lib/auth";
import { listConversations, listMessages } from "@/lib/cloud-data";
import { CONDOR_MIND_ID } from "@/lib/identity";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const { user, supabase } = await requireCloudUser(request);
    const conversationId = new URL(request.url).searchParams.get("conversationId") || undefined;
    const conversations = await listConversations(supabase, user.id);
    const selected = conversationId || conversations[0]?.id;
    const messages = selected ? await listMessages(supabase, user.id, selected, 120) : [];
    return NextResponse.json({ mindId: CONDOR_MIND_ID, conversations, conversationId: selected || null, messages }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return authFailure(error) || NextResponse.json({ error: "historico indisponivel" }, { status: 500 });
  }
}
