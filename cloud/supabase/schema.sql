-- Condor AI Cloud: projeto Supabase exclusivo. Execute apenas no projeto novo.
-- Todo conteudo pessoal fica cifrado pela aplicacao antes de chegar ao banco.

create extension if not exists pgcrypto;

create table if not exists public.condor_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  mind_id text not null default 'condor-kaua-primary-v1' check (mind_id = 'condor-kaua-primary-v1'),
  identity_version text not null default 'condor-core-identity-v1',
  display_name text not null default 'Kaua',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.condor_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  title_ciphertext text not null,
  origin_device text,
  origin_id text,
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, origin_device, origin_id)
);

create table if not exists public.condor_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  conversation_id uuid not null references public.condor_conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content_ciphertext text not null,
  client_message_id text,
  origin_device text,
  origin_id text,
  created_at timestamptz not null default now(),
  unique (user_id, client_message_id),
  unique (user_id, origin_device, origin_id)
);
create index if not exists condor_messages_conversation_idx
  on public.condor_messages(user_id, conversation_id, created_at desc);

create table if not exists public.condor_facts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  category text not null,
  fact_key text not null,
  value_ciphertext text not null,
  confidence double precision not null default 0.8 check (confidence between 0 and 1),
  origin text not null default 'cloud',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, category, fact_key)
);
create index if not exists condor_facts_updated_idx
  on public.condor_facts(user_id, updated_at desc);

create table if not exists public.condor_notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  title_ciphertext text not null,
  body_ciphertext text not null,
  source_message_id uuid references public.condor_messages(id) on delete set null,
  origin_device text,
  origin_id text,
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, origin_device, origin_id)
);
create index if not exists condor_notes_updated_idx
  on public.condor_notes(user_id, updated_at desc);

create table if not exists public.condor_devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  device_key text not null,
  name text not null,
  kind text not null check (kind in ('phone', 'desktop', 'tablet', 'browser')),
  trust_state text not null default 'trusted' check (trust_state in ('pending', 'trusted', 'revoked')),
  capabilities text[] not null default array['chat', 'notes', 'sync']::text[],
  last_seen timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, device_key)
);

create table if not exists public.condor_sync_events (
  sequence bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  client_event_id text not null,
  device_key text not null,
  event_type text not null check (event_type in ('message', 'fact', 'note', 'conversation', 'device')),
  payload_ciphertext text not null,
  created_at timestamptz not null default now(),
  unique (user_id, client_event_id)
);
create index if not exists condor_sync_events_user_sequence_idx
  on public.condor_sync_events(user_id, sequence asc);

alter table public.condor_profiles enable row level security;
alter table public.condor_conversations enable row level security;
alter table public.condor_messages enable row level security;
alter table public.condor_facts enable row level security;
alter table public.condor_notes enable row level security;
alter table public.condor_devices enable row level security;
alter table public.condor_sync_events enable row level security;

do $$
declare table_name text;
begin
  foreach table_name in array array[
    'condor_profiles', 'condor_conversations', 'condor_messages', 'condor_facts',
    'condor_notes', 'condor_devices', 'condor_sync_events'
  ] loop
    execute format('drop policy if exists "owner manages %s" on public.%I', table_name, table_name);
    execute format(
      'create policy "owner manages %s" on public.%I for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id)',
      table_name, table_name
    );
    execute format('revoke all on public.%I from anon', table_name);
    execute format('grant select, insert, update, delete on public.%I to authenticated', table_name);
  end loop;
end $$;

grant usage, select on sequence public.condor_sync_events_sequence_seq to authenticated;

create or replace function public.condor_touch_updated_at()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists condor_profiles_touch on public.condor_profiles;
create trigger condor_profiles_touch before update on public.condor_profiles
for each row execute function public.condor_touch_updated_at();
drop trigger if exists condor_conversations_touch on public.condor_conversations;
create trigger condor_conversations_touch before update on public.condor_conversations
for each row execute function public.condor_touch_updated_at();
drop trigger if exists condor_facts_touch on public.condor_facts;
create trigger condor_facts_touch before update on public.condor_facts
for each row execute function public.condor_touch_updated_at();
drop trigger if exists condor_notes_touch on public.condor_notes;
create trigger condor_notes_touch before update on public.condor_notes
for each row execute function public.condor_touch_updated_at();
drop trigger if exists condor_devices_touch on public.condor_devices;
create trigger condor_devices_touch before update on public.condor_devices
for each row execute function public.condor_touch_updated_at();

-- Cadastro publico fica desligado no painel. Crie somente o usuario do dono.
