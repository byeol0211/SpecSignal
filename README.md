> Integration update (2026-11-10): PLSAi frontend now runs on the existing FastAPI server. Certification list, details and yearly exam schedules use backend APIs. Profile, bookmarks and personal schedules still use localStorage; AI and competition submission remain unconnected. Run `python -m src.web.server` and open http://127.0.0.1:8000. Earlier removal/pending statements below describe the previous stage.

# SpecSignal

> 2026-11-15: 학교·학과 입력 → Claude 공식 자료 조회 → 출처 확인 후 개인 일정 등록 흐름을 추가했습니다. 같은 학교·캠퍼스·학년도는 DB 결과를 재사용합니다. 설정·제한은 [학사일정 연결](docs/academic-calendar.md)을 참고하세요.

> 현재 자격증 화면은 **공식 API 직접 조회 방식**입니다. Supabase 초기 수집 없이 목록·상세·시험일정을 조회합니다. 실행에 `DATA_GO_KR_API_KEY`가 필요하며, 자세한 구조는 [공식 API 연결](docs/official-api.md)을 참고하세요. 아래 DB 기반 연결 설명은 이전 단계 기록입니다.

> 2026-11-10: **작품 조건 변경으로 인해 PLSAi 기반으로 프론트엔드를 재구축합니다.** 서비스의 기능과 목표는 유지합니다. PLSAi 소스는 `artifacts/PLSAi-reference/`에 참조용으로 확보했으며 아직 서비스에 적용하지 않았습니다. 이전 문서 내용은 [변경 전 기록](docs/history/README.md)에 보존합니다.

A service for university students to explore certifications and activities and plan preparation around academic schedules.

## Current status (2026-11-10)

The previous frontend has been removed due to changed project requirements. The replacement will be based on [PLSAi](https://github.com/byeol0211/PLSAi), preserving the same product goals and feature requirements. Source is available locally for reference; application integration is pending.

- Preserved: FastAPI APIs, authentication, certification collection and normalization, Supabase integration and migrations.
- Removed: HTML, CSS, JavaScript, SVG assets, UI verification scripts and screenshots.
- Previous UI routes (`/`, `/catalog-live`) now return 404.
- Calendar, bookmarks, profiles and recommendation demos previously implemented in the browser must be rebuilt in the replacement frontend.

## Run the backend

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.web.server
```

`start-web.cmd` also starts the backend. Default address: `http://127.0.0.1:8000`. API schema: `/api/openapi.json`. See `.env.example` and the database document for configuration.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Documents

- [Project overview](docs/project-overview.md): product goals and feature reference; previous UI implementation status is historical.
- [Architecture decisions](docs/architecture-decisions.md): data strategy, architecture history and frontend replacement decision.
- [Design implementation](docs/design-implementation.md): historical record of the removed UI.
- [Supabase database](docs/supabase-database.md): database schema, collection, authentication and operations.
