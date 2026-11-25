-- X Downloader cross-device sync schema.
-- Run this once in your Supabase project's SQL Editor (Dashboard -> SQL Editor -> New query -> Run).

create table if not exists public.downloads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  source text not null default 'desktop',      -- 'desktop' | 'mobile'
  device_name text,
  claimed_by text,                              -- which desktop instance picked up a mobile-submitted link
  url text not null,
  filename text not null default '',
  kind text not null default 'http',            -- 'http' | 'stream' | 'ytdlp'
  status text not null default 'Pending',       -- Pending | Select Quality | Queued | Connecting | Downloading | Paused | Completed | Error | Cancelled
  progress real not null default 0,
  total_size bigint not null default -1,
  downloaded_bytes bigint not null default 0,
  speed_bps real not null default 0,
  error text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists downloads_user_id_idx on public.downloads(user_id);
create index if not exists downloads_status_idx on public.downloads(status);

alter table public.downloads enable row level security;

drop policy if exists "Users manage their own downloads" on public.downloads;
create policy "Users manage their own downloads"
  on public.downloads
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists downloads_set_updated_at on public.downloads;
create trigger downloads_set_updated_at
  before update on public.downloads
  for each row execute function public.set_updated_at();

-- Live updates for both apps
alter publication supabase_realtime add table public.downloads;
