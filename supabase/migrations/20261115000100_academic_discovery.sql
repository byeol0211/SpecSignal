-- Shared university-wide undergraduate calendars. User selections stay private.
create table if not exists public.academic_calendar_lookups (
  id uuid primary key default gen_random_uuid(),
  school_key text not null check (char_length(school_key) between 1 and 100),
  school_name text not null,
  campus text not null default '',
  academic_year smallint not null check (academic_year between 2000 and 2100),
  status text not null default 'pending' check (status in ('pending','ready','failed','needs_review')),
  requested_by uuid not null references auth.users(id) on delete cascade,
  candidates jsonb not null default '[]',
  message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(school_key, campus, academic_year)
);
alter table public.academic_calendar_lookups enable row level security;
-- Writes and candidate reads go through the authenticated backend, never the Data API.
revoke all on public.academic_calendar_lookups from anon, authenticated;
create index if not exists academic_lookup_owner_idx on public.academic_calendar_lookups(requested_by);
