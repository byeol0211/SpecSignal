-- Shared public school calendars must survive deletion of their first requester.
alter table public.academic_calendar_lookups alter column requested_by drop not null;
alter table public.academic_calendar_lookups drop constraint if exists academic_calendar_lookups_requested_by_fkey;
alter table public.academic_calendar_lookups add constraint academic_calendar_lookups_requested_by_fkey
  foreign key(requested_by) references auth.users(id) on delete set null;
