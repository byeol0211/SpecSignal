-- SpecSignal 핵심 스키마
-- 상태값은 이후 확장이 쉽도록 ENUM 대신 text + CHECK 제약으로 관리한다.
-- 모든 시각은 timestamptz(UTC 저장), 날짜만 의미가 있는 값은 date를 사용한다.

-- ---------------------------------------------------------------------------
-- 공통 함수
-- ---------------------------------------------------------------------------

-- updated_at은 "내용이 실제로 바뀐 시각". 수집 확인 시각(*_synced_at)만 바뀐 경우는 유지한다.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  ignored constant text[] := array['updated_at', 'list_synced_at', 'details_synced_at', 'last_synced_at'];
begin
  if (to_jsonb(new) - ignored) is distinct from (to_jsonb(old) - ignored) then
    new.updated_at = now();
  else
    new.updated_at = old.updated_at;
  end if;
  return new;
end;
$$;

-- 관리자 판별. app_metadata는 사용자가 직접 수정할 수 없고 service_role/대시보드에서만 변경된다.
-- 관리자 지정: auth.users.raw_app_meta_data에 {"role": "admin"} 설정 (docs/supabase-database.md 참고)
create or replace function public.is_admin()
returns boolean
language sql
stable
set search_path = ''
as $$
  select coalesce((auth.jwt() -> 'app_metadata' ->> 'role') = 'admin', false);
$$;

-- ---------------------------------------------------------------------------
-- 학교 / 학사일정
-- ---------------------------------------------------------------------------

create table public.universities (
  id            bigint generated always as identity primary key,
  name          text not null check (char_length(name) between 1 and 100),
  campus        text check (char_length(campus) <= 50),
  homepage_url  text check (homepage_url ~ '^https?://'),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique nulls not distinct (name, campus)
);

create table public.academic_events (
  id                   bigint generated always as identity primary key,
  university_id        bigint not null references public.universities (id) on delete cascade,
  academic_year        smallint not null check (academic_year between 2000 and 2100),
  semester             text not null check (semester in ('1', '2', 'summer', 'winter', 'all')),
  event_type           text not null check (event_type in (
                         'SEMESTER_START', 'MIDTERM', 'FINAL', 'SEMESTER_END',
                         'VACATION', 'REGISTRATION', 'OTHER')),
  title                text not null check (char_length(title) between 1 and 200),
  start_date           date not null,
  end_date             date check (end_date is null or end_date >= start_date),
  source_url           text check (source_url ~ '^https?://'),
  -- 공식 출처 확인 → LLM 추출 → 검증 → 사용자 확인 흐름 (architecture-decisions.md 5절)
  verification_status  text not null default 'unverified'
                         check (verification_status in ('unverified', 'verified', 'rejected')),
  verified_at          timestamptz,
  created_by           uuid references auth.users (id) on delete set null,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  unique (university_id, academic_year, semester, event_type, title, start_date)
);

create index academic_events_lookup_idx
  on public.academic_events (university_id, academic_year, semester);

-- ---------------------------------------------------------------------------
-- 사용자 정보
-- ---------------------------------------------------------------------------

create table public.profiles (
  id               uuid primary key references auth.users (id) on delete cascade,
  display_name     text check (char_length(display_name) <= 50),
  university_id    bigint references public.universities (id) on delete set null,
  -- universities에 아직 없는 학교도 입력할 수 있도록 원문 학교명을 함께 보관
  school_name      text check (char_length(school_name) <= 100),
  major            text check (char_length(major) <= 100),
  academic_status  text check (academic_status in (
                     'enrolled', 'on_leave', 'graduation_expected', 'graduated', 'other')),
  grade            smallint check (grade between 1 and 6),
  interest_jobs    text[] not null default '{}' check (cardinality(interest_jobs) <= 20),
  interest_fields  text[] not null default '{}' check (cardinality(interest_fields) <= 20),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index profiles_university_idx on public.profiles (university_id);

create table public.user_preferences (
  user_id                  uuid primary key references public.profiles (id) on delete cascade,
  -- 추천 시 사용할 공부기간 기준 (프로필 화면의 최소/평균/최대 선택)
  study_period_basis       text not null default 'avg' check (study_period_basis in ('min', 'avg', 'max')),
  daily_study_hours        numeric(3, 1) check (daily_study_hours between 0 and 24),
  academic_calendar_sync   boolean not null default false,
  academic_year            smallint check (academic_year between 2000 and 2100),
  semester                 text check (semester in ('1', '2', 'summer', 'winter')),
  -- 알림 설정 (실제 발송/내역은 향후 notifications 테이블에서 관리)
  notify_registration_start boolean not null default true,
  notify_registration_end   boolean not null default true,
  notify_exam_day           boolean not null default true,
  notify_competition        boolean not null default true,
  notify_ai_recommendation  boolean not null default true,
  default_reminder_days     smallint not null default 3 check (default_reminder_days between 0 and 365),
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

-- 회원가입 시 프로필과 기본 설정을 자동 생성
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, left(new.raw_user_meta_data ->> 'name', 50))
  on conflict (id) do nothing;
  insert into public.user_preferences (user_id)
  values (new.id)
  on conflict (user_id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- 국가자격 (공공데이터 원천: 15003024 목록, 15003003 상세, 15074408 시험일정)
-- 백엔드 동기화 작업만 쓰기 가능. API가 제공하지 않는 값은 NULL로 둔다.
-- ---------------------------------------------------------------------------

create table public.certifications (
  id                 bigint generated always as identity primary key,
  jm_cd              text not null unique check (jm_cd ~ '^[A-Za-z0-9]{4}$'),
  name               text not null,                 -- jmfldnm
  qualgb_cd          text,                          -- 자격구분 코드 (T 국가기술, S 국가전문 ...)
  qualgb_nm          text,
  series_cd          text,                          -- 계열 (기술사, 기사 ...)
  series_nm          text,
  oblig_fld_cd       text,                          -- 대직무분야
  oblig_fld_nm       text,
  mdoblig_fld_cd     text,                          -- 중직무분야
  mdoblig_fld_nm     text,
  source             text not null default 'data.go.kr/15003024',
  -- 최신 목록에서 사라진 종목은 삭제하지 않고 비활성화 (사용자 관심/일정 연결 보존)
  is_active          boolean not null default true,
  list_synced_at     timestamptz not null,
  details_synced_at  timestamptz,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

create index certifications_active_name_idx on public.certifications (is_active, name);
create index certifications_qualgb_idx on public.certifications (qualgb_cd);
create index certifications_field_idx on public.certifications (oblig_fld_nm);

-- 상세정보: 종목당 여러 섹션(infogb: 취득방법, 응시자격 등)이 반환되어 별도 테이블로 분리
create table public.certification_details (
  id                bigint generated always as identity primary key,
  certification_id  bigint not null references public.certifications (id) on delete cascade,
  info_gb           text not null,
  contents          text,
  source            text not null default 'data.go.kr/15003003',
  last_synced_at    timestamptz not null,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (certification_id, info_gb)
);

-- 시험일정: API 한 행(필기 doc* + 실기 prac*)을 단계별 행으로 분리 저장
-- 실응답에서 같은 연도·회차·설명이라도 접수기간만 다른 행이 존재하므로
-- 접수 시작·마감일까지 식별 키에 포함한다 (docs/supabase-database.md 참고).
create table public.certification_exams (
  id                bigint generated always as identity primary key,
  certification_id  bigint not null references public.certifications (id) on delete cascade,
  impl_year         smallint not null check (impl_year between 1900 and 2100),  -- implYy
  impl_seq          integer not null,                                           -- implSeq
  qualgb_cd         text not null,
  qualgb_nm         text,
  description       text,
  exam_phase        text not null check (exam_phase in ('written', 'practical')), -- doc* / prac*
  reg_start_date    date,
  reg_end_date      date,
  exam_start_date   date,
  exam_end_date     date,
  pass_date         date,
  source            text not null default 'data.go.kr/15074408',
  -- 해당 연도 전체 조회에 성공했는데 응답에 없으면 false (실패 시에는 변경하지 않음)
  is_active         boolean not null default true,
  last_synced_at    timestamptz not null,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  constraint certification_exams_natural_key unique nulls not distinct (
    certification_id, impl_year, impl_seq, qualgb_cd, description,
    exam_phase, reg_start_date, reg_end_date)
);

create index certification_exams_cert_year_idx
  on public.certification_exams (certification_id, impl_year) where is_active;
create index certification_exams_reg_end_idx
  on public.certification_exams (reg_end_date) where is_active;
create index certification_exams_exam_start_idx
  on public.certification_exams (exam_start_date) where is_active;

-- 리소스(종목 상세 / 종목·연도별 일정)별 마지막 수집 결과. 웹은 이를 보고
-- "수집 전", "빈 결과", "최근 갱신 실패(이전 데이터 표시)"를 구분한다.
create table public.certification_sync_state (
  certification_id  bigint not null references public.certifications (id) on delete cascade,
  resource          text not null check (resource in ('details', 'schedule')),
  impl_year         smallint not null default 0,   -- details는 0
  last_attempt_at   timestamptz not null,
  last_success_at   timestamptz,
  last_status       text not null check (last_status in ('success', 'empty', 'error')),
  last_error        text,
  record_count      integer,
  primary key (certification_id, resource, impl_year)
);

-- 수집 작업 단위 로그
create table public.sync_runs (
  id                 bigint generated always as identity primary key,
  job                text not null check (job in (
                       'certification_list', 'certification_details', 'certification_schedules')),
  status             text not null default 'running'
                       check (status in ('running', 'success', 'partial', 'empty', 'error')),
  params             jsonb not null default '{}',
  requested_count    integer not null default 0,
  success_count      integer not null default 0,
  empty_count        integer not null default 0,
  error_count        integer not null default 0,
  inserted_count     integer not null default 0,
  updated_count      integer not null default 0,
  unchanged_count    integer not null default 0,
  deactivated_count  integer not null default 0,
  error_summary      text,
  started_at         timestamptz not null default now(),
  finished_at        timestamptz
);

create index sync_runs_job_started_idx on public.sync_runs (job, started_at desc);

-- ---------------------------------------------------------------------------
-- 공모전 (사용자 등록 → 관리자 승인)
-- ---------------------------------------------------------------------------

create table public.competitions (
  id                   uuid primary key default gen_random_uuid(),
  title                text check (char_length(title) <= 200),
  organizer            text check (char_length(organizer) <= 100),
  field                text check (char_length(field) <= 50),
  eligibility          text,
  apply_start_date     date,
  apply_end_date       date,
  result_date          date,
  description          text,
  official_url         text check (official_url ~ '^https?://'),
  poster_image_url     text check (poster_image_url ~ '^https?://'),  -- 외부 이미지 URL
  poster_storage_path  text,                                          -- Storage competition-posters 경로
  -- AI 공고 분석: 공식 URL 또는 업로드한 PDF에서 추출한 원본 값. 사용자가 확인·수정 후 제출
  source_type          text check (source_type in ('url', 'pdf', 'manual')),
  source_url           text check (source_url ~ '^https?://'),
  source_file_path     text,                                          -- Storage competition-files 경로
  ai_extraction        jsonb,
  ai_extracted_at      timestamptz,
  status               text not null default 'draft'
                         check (status in ('draft', 'pending', 'approved', 'rejected')),
  rejection_reason     text,
  submitted_at         timestamptz,
  reviewed_by          uuid references auth.users (id) on delete set null,
  reviewed_at          timestamptz,
  created_by           uuid default auth.uid() references auth.users (id) on delete set null,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  check (apply_end_date is null or apply_start_date is null or apply_end_date >= apply_start_date),
  -- 임시저장 외 상태는 핵심 항목이 채워져 있어야 한다
  check (status = 'draft' or (title is not null and organizer is not null
                              and official_url is not null and apply_end_date is not null))
);

create index competitions_status_deadline_idx on public.competitions (status, apply_end_date);
create index competitions_created_by_idx on public.competitions (created_by);
-- 같은 공고 URL이 중복 승인되지 않도록 방지
create unique index competitions_approved_url_key
  on public.competitions (lower(official_url)) where status = 'approved';

-- 일반 사용자의 승인 상태·검토 정보 변경을 차단 (관리자/백엔드는 허용)
create or replace function public.guard_competition_changes()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  -- 백엔드 직접 연결(JWT 없음), service_role 키, 관리자는 제한하지 않는다
  if auth.jwt() is null or auth.jwt() ->> 'role' = 'service_role' or public.is_admin() then
    return new;
  end if;
  if new.status not in ('draft', 'pending') then
    raise exception '공모전 승인/반려는 관리자만 할 수 있습니다.' using errcode = '42501';
  end if;
  if tg_op = 'INSERT' then
    new.created_by := auth.uid();
  else
    new.created_by := old.created_by;
  end if;
  new.reviewed_by := null;
  new.reviewed_at := null;
  new.rejection_reason := case when tg_op = 'UPDATE' then old.rejection_reason end;
  new.submitted_at := case when new.status = 'pending' then now() end;
  return new;
end;
$$;

create trigger competitions_guard
  before insert or update on public.competitions
  for each row execute function public.guard_competition_changes();

-- ---------------------------------------------------------------------------
-- 사용자 활동
-- ---------------------------------------------------------------------------

create table public.bookmarks (
  id                bigint generated always as identity primary key,
  user_id           uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  certification_id  bigint references public.certifications (id) on delete cascade,
  competition_id    uuid references public.competitions (id) on delete cascade,
  memo              text check (char_length(memo) <= 500),
  created_at        timestamptz not null default now(),
  check (num_nonnulls(certification_id, competition_id) = 1),
  -- NULL은 서로 다른 값으로 취급되므로 각 대상별로 사용자당 1건만 허용된다
  unique (user_id, certification_id),
  unique (user_id, competition_id)
);

create index bookmarks_certification_idx on public.bookmarks (certification_id);
create index bookmarks_competition_idx on public.bookmarks (competition_id);

create table public.calendar_events (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  title                  text not null check (char_length(title) between 1 and 200),
  -- 웹 화면의 일정 유형과 동일 (app.js types)
  event_type             text not null check (event_type in (
                           'exam', 'deadline', 'school', 'contest', 'start', 'result', 'personal')),
  start_date             date not null,                    -- D-day 계산 기준
  end_date               date check (end_date is null or end_date >= start_date),
  memo                   text check (char_length(memo) <= 1000),
  reminder_enabled       boolean not null default true,
  reminder_days_before   smallint check (reminder_days_before between 0 and 365),
  -- 원본 연결. 날짜는 등록 시점 값을 복사하므로 사용자가 수정할 수 있다
  source_type            text not null default 'manual'
                           check (source_type in ('manual', 'certification_exam', 'competition', 'academic_event')),
  certification_id       bigint references public.certifications (id) on delete set null,
  certification_exam_id  bigint references public.certification_exams (id) on delete set null,
  competition_id         uuid references public.competitions (id) on delete set null,
  academic_event_id      bigint references public.academic_events (id) on delete set null,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  check (num_nonnulls(certification_exam_id, competition_id, academic_event_id) <= 1),
  -- 같은 원본의 같은 유형 일정은 다시 저장하면 기존 일정을 수정한다 (기존 웹 동작)
  unique (user_id, certification_exam_id, event_type),
  unique (user_id, competition_id, event_type),
  unique (user_id, academic_event_id, event_type)
);

create index calendar_events_user_date_idx on public.calendar_events (user_id, start_date);
create index calendar_events_cert_exam_idx on public.calendar_events (certification_exam_id);
create index calendar_events_competition_idx on public.calendar_events (competition_id);
create index calendar_events_certification_idx on public.calendar_events (certification_id);
create index calendar_events_academic_idx on public.calendar_events (academic_event_id);

-- ---------------------------------------------------------------------------
-- 챗봇 대화 기록 (추천 결과는 별도 테이블 없이 메시지 metadata에 참조로 남긴다)
-- ---------------------------------------------------------------------------

create table public.chat_sessions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  title       text check (char_length(title) <= 100),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index chat_sessions_user_idx on public.chat_sessions (user_id, updated_at desc);

create table public.chat_messages (
  id          bigint generated always as identity primary key,
  session_id  uuid not null references public.chat_sessions (id) on delete cascade,
  user_id     uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  role        text not null check (role in ('user', 'assistant', 'system')),
  content     text not null check (char_length(content) <= 20000),
  metadata    jsonb not null default '{}',
  created_at  timestamptz not null default now()
);

create index chat_messages_session_idx on public.chat_messages (session_id, created_at);
create index chat_messages_user_idx on public.chat_messages (user_id);

-- ---------------------------------------------------------------------------
-- updated_at 트리거
-- ---------------------------------------------------------------------------

do $$
declare
  t text;
begin
  foreach t in array array[
    'universities', 'academic_events', 'profiles', 'user_preferences',
    'certifications', 'certification_details', 'certification_exams',
    'competitions', 'calendar_events', 'chat_sessions'
  ] loop
    execute format(
      'create trigger %I before update on public.%I
         for each row execute function public.set_updated_at()',
      t || '_set_updated_at', t);
  end loop;
end;
$$;
