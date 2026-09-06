import { NextResponse } from "next/server";
import { z } from "zod";
import { authFailure, requireCloudUser } from "@/lib/auth";
import { CONDOR_MIND_ID } from "@/lib/identity";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const deviceSchema = z.object({ deviceKey: z.string().min(8).max(160), name: z.string().trim().min(1).max(120), kind: z.enum(["phone", "desktop", "tablet", "browser"]), capabilities: z.array(z.enum(["chat", "notes", "sync", "projects", "notifications"])).max(5).default(["chat", "notes", "sync"]) });

export async function GET(request: Request) {
  try {
    const { user, supabase } = await requireCloudUser(request);
    const { data, error } = await supabase.from("condor_devices").select("id,device_key,name,kind,trust_state,capabilities,last_seen,created_at").eq("user_id", user.id).order("updated_at", { ascending: false });
    if (error) throw error;
    return NextResponse.json({ mindId: CONDOR_MIND_ID, devices: data || [] });
  } catch (error) { return authFailure(error) || NextResponse.json({ error: "dispositivos indisponiveis" }, { status: 500 }); }
}

export async function POST(request: Request) {
  try {
    const { user, supabase } = await requireCloudUser(request);
    const parsed = deviceSchema.safeParse(await request.json());
    if (!parsed.success) return NextResponse.json({ error: "dispositivo invalido" }, { status: 400 });
    const { data, error } = await supabase.from("condor_devices").upsert({
      user_id: user.id, device_key: parsed.data.deviceKey, name: parsed.data.name, kind: parsed.data.kind,
      capabilities: parsed.data.capabilities, trust_state: "trusted", last_seen: new Date().toISOString(),
    }, { onConflict: "user_id,device_key" }).select("id,device_key,name,kind,trust_state,capabilities,last_seen,created_at").single();
    if (error) throw error;
    return NextResponse.json({ mindId: CONDOR_MIND_ID, device: data });
  } catch (error) { return authFailure(error) || NextResponse.json({ error: "registro recusado" }, { status: 500 }); }
}

export async function DELETE(request: Request) {
  try {
    const { user, supabase } = await requireCloudUser(request);
    const deviceKey = new URL(request.url).searchParams.get("deviceKey");
    if (!deviceKey) return NextResponse.json({ error: "dispositivo ausente" }, { status: 400 });
    const { error } = await supabase.from("condor_devices").update({ trust_state: "revoked" }).eq("user_id", user.id).eq("device_key", deviceKey);
    if (error) throw error;
    return NextResponse.json({ mindId: CONDOR_MIND_ID, ok: true });
  } catch (error) { return authFailure(error) || NextResponse.json({ error: "revogacao recusada" }, { status: 500 }); }
}
