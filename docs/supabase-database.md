# SpecSignal Supabase 데이터베이스

작성 기준: 2026-10-13. 관련 결정: [architecture-decisions.md](architecture-decisions.md)

## 1. 구성 개요

```text
공공데이터 API ──(수집 CLI: src.certification.sync)──▶ Supabase PostgreSQL
  15003024 종목 목록                                   certifications
  15003003 종목 상세                                   certification_details
  15074408 시험일정                                    certification_exams
                                                        sync_runs / certification_sync_state
브라우저 ──▶ FastAPI (src.web.server) ──▶ Supabase PostgreSQL (조회)
          (공공데이터 API를 직접 호출하지 않음)
```

- 수집은 기존 `collect_items()`·`collect_info()`를 그대로 호출한다. 재시도(연결 오류 3회), 페이지 처리, 원문 저장(`data/raw/`) 정책은 변경하지 않았다.
- 웹의 기존 API(`/api/items`, `/api/details`, `/api/schedules`)는 응답 형식을 유지하면서 DB를 조회한다. 프론트엔드 코드는 수정하지 않았다.
- 스키마는 `supabase/migrations/`의 SQL 마이그레이션으로 관리한다.

## 2. ERD

```mermaid
erDiagram
    auth_users ||--|| profiles : "id"
    profiles ||--|| user_preferences : "user_id"
    universities ||--o{ profiles : "university_id"
    universities ||--o{ academic_events : "university_id"

    certifications ||--o{ certification_details : "certification_id"
    certifications ||--o{ certification_exams : "certification_id"
    certifications ||--o{ certification_sync_state : "certification_id"

    profiles ||--o{ bookmarks : "user_id"
    certifications ||--o{ bookmarks : "certification_id"
    competitions ||--o{ bookmarks : "competition_id"

    profiles ||--o{ calendar_events : "user_id"
    certification_exams ||--o{ calendar_events : "certification_exam_id"
    competitions ||--o{ calendar_events : "competition_id"
    academic_events ||--o{ calendar_events : "academic_event_id"

    auth_users ||--o{ competitions : "created_by / reviewed_by"
    profiles ||--o{ chat_sessions : "user_id"
    chat_sessions ||--o{ chat_messages : "session_id"
```

| 영역 | 테이블 | 핵심 키·제약 |
|---|---|---|
| 사용자 | `profiles` | PK = `auth.users.id` (가입 트리거로 자동 생성, 탈퇴 시 cascade) |
| | `user_preferences` | PK = `user_id`. 공부기간 기준(min/avg/max), 하루 공부시간, 학사일정 연동, 알림 토글 |
| 자격증 | `certifications` | `jm_cd` UNIQUE. 목록에서 사라진 종목은 삭제 대신 `is_active=false` |
| | `certification_details` | UNIQUE(`certification_id`, `info_gb`) |
| | `certification_exams` | 자연키 UNIQUE NULLS NOT DISTINCT (아래 3절) |
| | `certification_sync_state` | PK(`certification_id`, `resource`, `impl_year`). 리소스별 마지막 시도/성공/오류 |
| | `sync_runs` | 수집 작업 로그 (요청·성공·빈 결과·실패·신규·변경·유지·비활성 건수) |
| 학교 | `universities` | UNIQUE NULLS NOT DISTINCT(`name`, `campus`) |
| | `academic_events` | UNIQUE(학교, 학년도, 학기, 유형, 일정명, 시작일), `verification_status` |
| 공모전 | `competitions` | 상태 `draft → pending → approved / rejected`, 승인된 공고 URL 중복 방지 |
| 활동 | `bookmarks` | 자격증/공모전 중 정확히 하나, 사용자별 중복 방지 |
| | `calendar_events` | `start_date`가 D-day 기준. 원본(시험일정·공모전·학사일정) 연결, 같은 원본·유형은 1건 |
| 챗봇 | `chat_sessions`, `chat_messages` | 메시지 `role` = user/assistant/system, 추천 참조는 `metadata` |

설계 메모

- **상세정보 분리**: 상세 API는 종목마다 2~3개 섹션(`infogb`: 취득방법·응시자격 등)을 반환하므로 `certifications`의 한 컬럼 대신 별도 테이블로 저장했다.
- **추천/알림 테이블 없음**: 추천은 챗봇에서 실시간 처리하고, 사용자가 선택한 항목만 `bookmarks`/`calendar_events`에 저장한다. 이후 `notifications`(calendar_event_id, channel, scheduled_at, sent_at, read_at)를 추가하면 `calendar_events.reminder_*`를 발송 예약의 입력으로 쓸 수 있다.
- **상태값**: ENUM 대신 `text + CHECK`를 사용하여 상태 추가 시 제약만 변경하면 된다.
- **updated_at**: 내용이 실제로 바뀐 경우에만 갱신된다. 수집 확인 시각은 `list_synced_at`/`last_synced_at`에 별도 저장한다.

## 3. 공공데이터 API 매핑

### 종목 목록 (15003024) → `certifications`

| API | 컬럼 | API | 컬럼 |
|---|---|---|---|
| jmcd | jm_cd | jmfldnm | name |
| qualgbcd / qualgbnm | qualgb_cd / qualgb_nm | seriescd / seriesnm | series_cd / series_nm |
| obligfldcd / obligfldnm | oblig_fld_cd / oblig_fld_nm | mdobligfldcd / mdobligfldnm | mdoblig_fld_cd / mdoblig_fld_nm |

페이지 변수가 없는 API로, 한 번의 응답에 전체 종목(2026-10 기준 613개: T 513, S 100)이 포함된다.

### 상세정보 (15003003) → `certification_details`

`infogb` → `info_gb`, `contents`(HTML 엔티티 해제 후) → `contents`. 종목 내 `infogb`는 중복되지 않음을 실응답으로 확인했다.

### 시험일정 (15074408) → `certification_exams`

API 한 행은 필기(`doc*`)와 실기(`prac*`) 날짜를 함께 가진다. 이를 `exam_phase`(written/practical) 단계별 행으로 나눈다. 날짜가 하나도 없는 단계(국가전문자격의 실기 등)는 행을 만들지 않는다.

| API | 컬럼 |
|---|---|
| implYy / implSeq | impl_year / impl_seq |
| qualgbCd / qualgbNm / description | qualgb_cd / qualgb_nm / description |
| {doc,prac}RegStartDt / RegEndDt | reg_start_date / reg_end_date |
| {doc,prac}ExamStartDt / ExamEndDt | exam_start_date / exam_end_date |
| {doc,prac}PassDt | pass_date |

**중복 방지 키 결정 근거**: `data/raw`의 실응답에서 같은 `implYy·implSeq·qualgbCd·description`에 필기 접수기간만 다른 두 행이 반복적으로 확인됐다(예: 2026년 기사 3회 `07-20~07-23`과 `08-01~08-02`). 따라서 식별 키를
`(certification_id, impl_year, impl_seq, qualgb_cd, description, exam_phase, reg_start_date, reg_end_date)`로 정했다. 실기 행은 두 API 행에서 동일하므로 하나로 합쳐진다. 같은 키에 다른 날짜가 오면 검증 오류로 저장하지 않는다.

웹의 기존 `/api/schedules`는 단계별 행을 원래 API 행 형태로 다시 결합해 반환한다.

### 검증 규칙

- 날짜는 `YYYYMMDD`만 허용하고, 존재하지 않는 날짜는 오류로 처리한다. 빈 값은 NULL로 저장한다.
- 시작일이 종료일보다 늦은 경우 공식 값을 고치지 않고 저장하되 경고 로그를 남긴다.
- API가 제공하지 않는 값은 생성하지 않는다.

## 4. 수집 정책

| 상황 | 처리 |
|---|---|
| 성공 | UPSERT. 응답에서 사라진 일정은 `is_active=false`, 상세 섹션은 삭제 |
| 빈 결과 | `empty` 상태 기록. 기존 데이터는 지우지 않음 |
| HTTP/업무 오류, 검증 실패 | 저장하지 않음. 기존 데이터 유지, `certification_sync_state`에 오류 기록 |
| 일시 연결 장애 | 호출 내 3회 재시도(기존 로직) 후, 실패한 종목은 작업 끝에 5초 뒤 한 번 더 시도 |
| 목록 응답이 기존 대비 절반 미만 | 부분 응답으로 보고 종목 비활성화를 건너뜀 |

### 실행

```powershell
# 초기 전체 적재 (목록 1회 + 상세 613회 + 일정 613회 × 연도 수)
.\.venv\Scripts\python.exe -m src.certification.sync all --force

# 정기 실행: 갱신 주기(기본 24시간)가 지난 항목만 수집
.\.venv\Scripts\python.exe -m src.certification.sync all

# 부분 실행
.\.venv\Scripts\python.exe -m src.certification.sync details --jmcd 1320 --force
.\.venv\Scripts\python.exe -m src.certification.sync schedules --year 2025 --limit 20
```

종료 코드: 0 성공/빈 결과/건너뜀, 2 일부 실패, 1 전체 실패 또는 DB 연결 실패.
정기 실행은 클라우드 배포 시 cron(예: 매일 04:00 KST `sync all`)으로 설정한다. 로컬에서는 Windows 작업 스케줄러로 같은 명령을 등록할 수 있다.

호출량: 초기 적재 시 약 1,840회(연도 2개 기준). 공공데이터포털 계정의 서비스별 일일 트래픽 한도를 확인하고, 한도가 낮으면 `--limit`으로 나누어 적재한다.

## 5. 보안

### RLS 요약

| 테이블 | anon | authenticated (본인) | 관리자 | 백엔드 |
|---|---|---|---|---|
| certifications / details / exams | 읽기 | 읽기 | 읽기 | 쓰기 |
| sync_runs / certification_sync_state | - | - | 읽기 | 쓰기 |
| universities / academic_events | 읽기(검증된 일정) | 읽기 | 전체 | 전체 |
| profiles / user_preferences | - | 본인 조회·수정 | - | 전체 |
| bookmarks / calendar_events / chat_sessions | - | 본인 CRUD | - | 전체 |
| chat_messages | - | 본인 조회·삭제, `user` 메시지만 추가 | - | AI 응답 저장 |
| competitions | 승인 항목 | 승인 항목 + 본인 등록 항목, 승인 전 수정 | 승인/반려 포함 전체 | 전체 |

- 테이블 권한(GRANT)도 역할별로 최소화하여 RLS와 이중으로 막는다. 이후 추가하는 테이블은 기본 권한이 없으므로 마이그레이션에서 명시적으로 GRANT해야 한다.
- 공모전 상태 변경은 트리거(`guard_competition_changes`)로도 막는다. 일반 사용자는 `draft`/`pending`만 설정할 수 있고 검토 필드는 강제로 초기화된다.
- **관리자 지정**: SQL Editor에서 아래를 실행한다. `app_metadata`는 사용자가 직접 바꿀 수 없다. 변경 후 해당 사용자는 다시 로그인해야 토큰에 반영된다.

```sql
update auth.users set raw_app_meta_data = raw_app_meta_data || '{"role": "admin"}'
where email = 'admin@example.com';
```

### Storage

| 버킷 | 용도 | 제한 | 읽기 | 쓰기 |
|---|---|---|---|---|
| competition-posters | 포스터 이미지 | 5MB, png/jpeg/webp | 승인 공모전은 누구나, 그 외 업로더·관리자 | 업로더(승인 전), 관리자 |
| competition-files | 공고 PDF | 20MB, pdf | 업로더·관리자 | 업로더(승인 전), 관리자 |

경로 규칙: `{user_id}/{competition_id}/{파일명}`. 버킷은 비공개이며 정책으로만 접근을 허용한다.

### 백엔드 접근 방식

- 공식 데이터 수집·조회: `SUPABASE_DB_URL`(postgres 역할)로 직접 연결. 이 연결은 RLS를 우회하므로 서버 코드에서만 사용한다.
- 사용자 개인 데이터: `Authorization: Bearer <access token>`을 JWKS(비대칭 키) 또는 레거시 secret으로 검증한 뒤, 트랜잭션 안에서 `SET LOCAL ROLE authenticated`와 `request.jwt.claims`를 설정한다. 그러면 DB의 RLS가 그대로 적용된다(`/api/v1/me` 참고).

## 6. 환경변수

| 변수 | 노출 범위 | 설명 |
|---|---|---|
| `SUPABASE_URL` | 공개 가능 | `https://<project-ref>.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | 공개 가능 | publishable(또는 레거시 anon) 키. RLS가 적용된다 |
| `SUPABASE_DB_URL` | **백엔드 전용** | DB 비밀번호 포함. Session pooler(IPv4) 연결 문자열 권장 |
| `SUPABASE_JWT_SECRET` | **백엔드 전용** | 레거시 HS256 토큰을 쓸 때만 설정 |
| `DATA_GO_KR_API_KEY` | **백엔드 전용** | 공공데이터포털 인증키 |
| `CERT_*_REFRESH_HOURS` | 설정 | 목록·상세·일정 갱신 주기(시간), 기본 24 |
| `CERT_SCHEDULE_YEAR_OFFSETS` | 설정 | 일정 수집 연도(올해 기준), 기본 `0,1` |
| `PUBLIC_API_REQUEST_INTERVAL_SECONDS` | 설정 | API 호출 간격, 기본 0.3초 |

secret key(`sb_secret_...`/service_role)는 현재 사용하지 않는다. 프론트엔드에는 `/api/v1/config`로 URL과 publishable key만 제공한다.

## 7. API

| 경로 | 설명 |
|---|---|
| `GET /api/items` | (기존 형식) 활성 종목 전체, `fetched_at` = 마지막 목록 수집 시각 |
| `GET /api/details?jmcd=` | (기존 형식) 상세 섹션. 미수집이면 503, `stale`은 마지막 갱신 실패 표시 |
| `GET /api/schedules?jmcd=&year=&category=` | (기존 형식) 시험일정 |
| `GET /api/v1/certifications?q=&qualgb_cd=&field=&limit=&offset=` | 검색·필터·페이지 |
| `GET /api/v1/certifications/{jm_cd}` | 종목 + 상세 + 수집 상태 |
| `GET /api/v1/certifications/{jm_cd}/exams?year=&phase=` | 단계별 시험일정 (캘린더 연결용 `id` 포함) |
| `GET /api/v1/me` | 로그인 필요. 본인 프로필·설정 (RLS 적용) |
| `GET /api/v1/admin/sync-runs` | 관리자. 작업별 최근 수집 결과 |
| `GET /api/v1/config` | 프론트엔드용 공개 설정 |

## 8. 마이그레이션 적용

```powershell
# 로컬 검증 (Docker 필요)
npx supabase start
npx supabase db reset            # migrations 전체 재적용
$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# 클라우드 반영 (승인 후)
npx supabase login
npx supabase link --project-ref mkcgobaupkpechhflnzr
npx supabase db push --dry-run   # 적용될 마이그레이션 확인
npx supabase db push
```

## 9. 향후 연동 계획

1. **프론트엔드 인증·동기화**: Supabase Auth(supabase-js + publishable key)로 로그인하고, localStorage의 프로필·관심 목록·일정을 첫 로그인 시 DB로 옮긴다. 개인 데이터 CRUD API를 `user_transaction` 기반으로 추가한다.
2. **학사일정**: 학교명 입력 → `universities`/`academic_events` 캐시 확인 → 없으면 공식 출처 검색과 LLM 추출 → 검증 → 사용자 확인 후 저장. 사용자별 수정 내용은 `calendar_events`(academic_event_id 연결)에 저장한다.
3. **공모전**: 공고 URL/PDF 업로드(Storage) → AI 추출 결과를 `ai_extraction`에 보관 → 사용자가 확인·수정 후 `pending` 제출 → 관리자 승인. 승인 화면은 관리자 전용 API로 구현한다.
4. **챗봇 추천**: 대화 기록은 `chat_sessions/messages`에 저장하고, 추천 항목은 메시지 `metadata`에 `{jm_cd, exam_id}` 참조로 남긴다. 사용자가 선택하면 `bookmarks`/`calendar_events`로 저장한다.
5. **알림**: 발송이 필요해지면 `notifications` 테이블과 정기 작업을 추가한다.
6. **운영**: 정기 수집 cron 설정, `data/raw` 원문 보관 기간 정책(현재는 호출마다 파일이 누적된다), 수집 실패 알림.
