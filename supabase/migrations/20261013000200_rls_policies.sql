-- RLS 보안 정책
-- 원칙
--   1) 모든 public 테이블에 RLS 활성화 (정책이 없으면 anon/authenticated는 접근 불가)
--   2) 공식 자격증 데이터: 누구나 읽기만 가능, 쓰기는 백엔드(DB 직접 연결/service_role)만
--   3) 개인 데이터: 본인 행(user_id = auth.uid())만 조회·수정
--   4) 공모전: 승인된 항목만 공개, 승인/반려는 관리자 전용
-- auth.uid()는 행마다 재평가되지 않도록 (select auth.uid()) 형태로 사용한다.

-- ---------------------------------------------------------------------------
-- 테이블 권한 (RLS와 함께 이중 방어)
-- Supabase 기본 권한에 의존하지 않고 역할별로 필요한 권한만 명시한다.
-- ---------------------------------------------------------------------------

revoke all on all tables in schema public from anon, authenticated;

-- 공개 읽기 전용
grant select on public.certifications, public.certification_details, public.certification_exams,
                public.universities, public.academic_events, public.competitions
  to anon, authenticated;

-- 로그인 사용자의 개인 데이터
grant select, insert, update, delete on public.bookmarks, public.calendar_events,
                                         public.chat_sessions
  to authenticated;
grant select, insert, delete on public.chat_messages to authenticated;
grant select, update on public.profiles, public.user_preferences to authenticated;
grant insert, update, delete on public.competitions to authenticated;

-- 관리자(authenticated + app_metadata.role=admin)가 RLS 정책을 통해 사용하는 권한
grant insert, update, delete on public.universities, public.academic_events to authenticated;
grant select on public.sync_runs, public.certification_sync_state to authenticated;

-- 이후 생성되는 테이블은 기본적으로 anon/authenticated 권한이 없도록 설정
alter default privileges in schema public revoke all on tables from anon, authenticated;

-- ---------------------------------------------------------------------------
-- RLS 활성화
-- ---------------------------------------------------------------------------

alter table public.universities             enable row level security;
alter table public.academic_events          enable row level security;
alter table public.profiles                 enable row level security;
alter table public.user_preferences         enable row level security;
alter table public.certifications           enable row level security;
alter table public.certification_details    enable row level security;
alter table public.certification_exams      enable row level security;
alter table public.certification_sync_state enable row level security;
alter table public.sync_runs                enable row level security;
alter table public.competitions             enable row level security;
alter table public.bookmarks                enable row level security;
alter table public.calendar_events          enable row level security;
alter table public.chat_sessions            enable row level security;
alter table public.chat_messages            enable row level security;

-- ---------------------------------------------------------------------------
-- 공식 자격증 데이터: 읽기 전용 (쓰기 정책 없음 → 사용자 쓰기 불가)
-- ---------------------------------------------------------------------------

create policy "certifications_public_read" on public.certifications
  for select to anon, authenticated using (true);

create policy "certification_details_public_read" on public.certification_details
  for select to anon, authenticated using (true);

create policy "certification_exams_public_read" on public.certification_exams
  for select to anon, authenticated using (true);

-- 수집 상태/로그: 관리자만 조회
create policy "certification_sync_state_admin_read" on public.certification_sync_state
  for select to authenticated using ((select public.is_admin()));

create policy "sync_runs_admin_read" on public.sync_runs
  for select to authenticated using ((select public.is_admin()));

-- ---------------------------------------------------------------------------
-- 학교 / 학사일정: 검증된 일정은 공개, 관리 작업은 관리자
-- (사용자별 수정 일정은 calendar_events에 academic_event_id로 연결하여 저장)
-- ---------------------------------------------------------------------------

create policy "universities_public_read" on public.universities
  for select to anon, authenticated using (true);

create policy "universities_admin_write" on public.universities
  for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

create policy "academic_events_verified_read" on public.academic_events
  for select to anon, authenticated
  using (verification_status = 'verified' or (select public.is_admin()));

create policy "academic_events_admin_write" on public.academic_events
  for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

-- ---------------------------------------------------------------------------
-- 프로필 / 설정: 본인만 (행 생성은 가입 트리거, 삭제는 auth.users 삭제 시 cascade)
-- ---------------------------------------------------------------------------

create policy "profiles_select_own" on public.profiles
  for select to authenticated using (id = (select auth.uid()));

create policy "profiles_update_own" on public.profiles
  for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

create policy "user_preferences_select_own" on public.user_preferences
  for select to authenticated using (user_id = (select auth.uid()));

create policy "user_preferences_update_own" on public.user_preferences
  for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- 공모전
-- ---------------------------------------------------------------------------

-- 승인된 공모전은 누구나, 본인이 등록한 공모전은 상태와 무관하게, 관리자는 전체 조회
create policy "competitions_read" on public.competitions
  for select to anon, authenticated
  using (
    status = 'approved'
    or created_by = (select auth.uid())
    or (select public.is_admin())
  );

-- 등록: 본인 명의로 임시저장/검토요청만 가능 (트리거가 검토 필드를 강제 초기화)
create policy "competitions_insert_own" on public.competitions
  for insert to authenticated
  with check (created_by = (select auth.uid()) and status in ('draft', 'pending'));

-- 수정: 승인 전(임시저장·검토중·반려) 본인 항목만, 결과 상태는 임시저장/검토요청만
create policy "competitions_update_own" on public.competitions
  for update to authenticated
  using (created_by = (select auth.uid()) and status <> 'approved')
  with check (created_by = (select auth.uid()) and status in ('draft', 'pending'));

-- 삭제: 본인의 임시저장/반려 항목만
create policy "competitions_delete_own" on public.competitions
  for delete to authenticated
  using (created_by = (select auth.uid()) and status in ('draft', 'rejected'));

-- 관리자: 승인/반려 포함 전체 관리
create policy "competitions_admin_all" on public.competitions
  for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));

-- ---------------------------------------------------------------------------
-- 관심 목록
-- ---------------------------------------------------------------------------

create policy "bookmarks_select_own" on public.bookmarks
  for select to authenticated using (user_id = (select auth.uid()));

-- 공모전은 본인이 볼 수 있는(승인 또는 본인 등록) 항목만 저장 가능
create policy "bookmarks_insert_own" on public.bookmarks
  for insert to authenticated
  with check (
    user_id = (select auth.uid())
    and (competition_id is null
         or exists (select 1 from public.competitions c where c.id = competition_id))
  );

create policy "bookmarks_update_own" on public.bookmarks
  for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "bookmarks_delete_own" on public.bookmarks
  for delete to authenticated using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- 개인 캘린더
-- ---------------------------------------------------------------------------

create policy "calendar_events_select_own" on public.calendar_events
  for select to authenticated using (user_id = (select auth.uid()));

create policy "calendar_events_insert_own" on public.calendar_events
  for insert to authenticated
  with check (
    user_id = (select auth.uid())
    and (competition_id is null
         or exists (select 1 from public.competitions c where c.id = competition_id))
  );

create policy "calendar_events_update_own" on public.calendar_events
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (
    user_id = (select auth.uid())
    and (competition_id is null
         or exists (select 1 from public.competitions c where c.id = competition_id))
  );

create policy "calendar_events_delete_own" on public.calendar_events
  for delete to authenticated using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- 챗봇 대화 기록
-- AI 응답(assistant/system)은 백엔드가 직접 저장하고, 사용자는 user 메시지만 추가한다.
-- ---------------------------------------------------------------------------

create policy "chat_sessions_select_own" on public.chat_sessions
  for select to authenticated using (user_id = (select auth.uid()));

create policy "chat_sessions_insert_own" on public.chat_sessions
  for insert to authenticated with check (user_id = (select auth.uid()));

create policy "chat_sessions_update_own" on public.chat_sessions
  for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "chat_sessions_delete_own" on public.chat_sessions
  for delete to authenticated using (user_id = (select auth.uid()));

create policy "chat_messages_select_own" on public.chat_messages
  for select to authenticated using (user_id = (select auth.uid()));

create policy "chat_messages_insert_own" on public.chat_messages
  for insert to authenticated
  with check (
    user_id = (select auth.uid())
    and role = 'user'
    and exists (select 1 from public.chat_sessions s
                where s.id = session_id and s.user_id = (select auth.uid()))
  );

create policy "chat_messages_delete_own" on public.chat_messages
  for delete to authenticated using (user_id = (select auth.uid()));
