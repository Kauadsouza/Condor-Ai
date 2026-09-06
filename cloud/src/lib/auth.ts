import { createClient, type SupabaseClient, type User } from "@supabase/supabase-js";
import { publicEnv } from "@/lib/env";
import { CONDOR_IDENTITY_VERSION, CONDOR_MIND_ID } from "@/lib/identity";

export type CloudAuth = { user: User; supabase: SupabaseClient; token: string };

export async function requireCloudUser(request: Request): Promise<CloudAuth> {
  const authorization = request.headers.get("authorization") || "";
  if (!authorization.startsWith("Bearer ")) throw new Response("nao autenticado", { status: 401 });
  const token = authorization.slice(7).trim();
  const env = publicEnv();
  const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
    global: { headers: { Authorization: `Bearer ${token}` } },
  });
  const { data, error } = await supabase.auth.getUser(token);
  if (error || !data.user) throw new Response("sessao invalida", { status: 401 });
  const { data: profile, error: profileError } = await supabase.from("condor_profiles").upsert({
    user_id: data.user.id,
    mind_id: CONDOR_MIND_ID,
    identity_version: CONDOR_IDENTITY_VERSION,
    display_name: "Kaua",
  }, { onConflict: "user_id" }).select("mind_id,identity_version").single();
  if (profileError || profile?.mind_id !== CONDOR_MIND_ID || profile?.identity_version !== CONDOR_IDENTITY_VERSION) {
    throw new Response("identidade canonica do Condor indisponivel", { status: 409 });
  }
  return { user: data.user, supabase, token };
}

export function authFailure(error: unknown): Response | null {
  return error instanceof Response ? error : null;
}
