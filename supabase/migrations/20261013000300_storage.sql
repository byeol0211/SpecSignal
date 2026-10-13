-- 공모전 포스터·공고 파일 Storage
-- 경로 규칙: {업로더 user_id}/{competition_id}/{파일명}
--   - 버킷은 비공개. 승인된 공모전의 포스터만 누구나 읽을 수 있다.
--   - 공고 원본(PDF)은 업로더와 관리자만 읽는다 (AI 분석 입력용).
--   - 승인된 공모전의 파일은 업로더도 변경할 수 없다.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('competition-posters', 'competition-posters', false, 5242880,
   array['image/png', 'image/jpeg', 'image/webp']),
  ('competition-files', 'competition-files', false, 20971520,
   array['application/pdf'])
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- 업로더 본인 폴더이고, 연결된 공모전이 본인 소유이며 아직 승인되지 않았는지 확인
create or replace function public.can_manage_competition_object(object_name text)
returns boolean
language sql
stable
set search_path = ''
as $$
  select (storage.foldername(object_name))[1] = (select auth.uid())::text
     and exists (
       select 1 from public.competitions c
       where c.id::text = (storage.foldername(object_name))[2]
         and c.created_by = (select auth.uid())
         and c.status <> 'approved'
     );
$$;

create or replace function public.is_approved_competition_object(object_name text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.competitions c
    where c.id::text = (storage.foldername(object_name))[2]
      and c.status = 'approved'
  );
$$;

revoke execute on function public.is_approved_competition_object(text) from public;
grant execute on function public.is_approved_competition_object(text) to anon, authenticated;

create policy "competition_posters_public_read_approved" on storage.objects
  for select to anon, authenticated
  using (bucket_id = 'competition-posters'
         and public.is_approved_competition_object(name));

create policy "competition_objects_owner_read" on storage.objects
  for select to authenticated
  using (bucket_id in ('competition-posters', 'competition-files')
         and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "competition_objects_owner_insert" on storage.objects
  for insert to authenticated
  with check (bucket_id in ('competition-posters', 'competition-files')
              and public.can_manage_competition_object(name));

create policy "competition_objects_owner_update" on storage.objects
  for update to authenticated
  using (bucket_id in ('competition-posters', 'competition-files')
         and public.can_manage_competition_object(name))
  with check (bucket_id in ('competition-posters', 'competition-files')
              and public.can_manage_competition_object(name));

create policy "competition_objects_owner_delete" on storage.objects
  for delete to authenticated
  using (bucket_id in ('competition-posters', 'competition-files')
         and public.can_manage_competition_object(name));

create policy "competition_objects_admin_all" on storage.objects
  for all to authenticated
  using (bucket_id in ('competition-posters', 'competition-files') and (select public.is_admin()))
  with check (bucket_id in ('competition-posters', 'competition-files') and (select public.is_admin()));
