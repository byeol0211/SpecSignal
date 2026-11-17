# SpecSignal

작성 기준: 2026-11-17.

대학생이 자격증·공모전을 탐색하고 학교 시험 일정과 함께 준비 일정을 관리하는 반응형 웹입니다. PLSAi 화면과 FastAPI 백엔드를 연결했습니다.

## 현재 기능

- 이메일 회원가입·로그인, 기존 프로필 복원, 최초 학교·학과 입력과 프로필 수정.
- 자격증 공식 API 목록·상세·시험일정 조회, 분야별 필터·검색, 1열/2열 보기.
- Supabase `contests` 기반 공모전 목록·분야 필터·검색·포스터·상세 조회.
- 자격증·공모전 관심 저장과 마이페이지 관심 목록.
- 공식 시험일·공모전 접수 마감일을 일정 추가의 기본 날짜로 제공하고 직접 수정 허용.
- 학교 중간고사·기말고사 조회, 출처 확인 후 계정별 등록·수정·삭제.
- 홈 추천 카드 6개(2열 × 3행), 기간 일정의 연결된 형광펜 표시, 마이페이지 전체 일정 목록.

학교 시험 일정과 기본 프로필은 Supabase에 저장합니다. 관심 목록·일반 개인 일정은 브라우저 저장 방식이며 현재 로그인·로그아웃·세션 복원 과정에서 초기화됩니다. 계정 간 영구 동기화는 아직 구현하지 않았습니다. AI 맞춤 추천·공모전 제출·실제 알림 발송도 미연결입니다.

## 로컬 실행

Python 가상환경을 만들고 `.env.example`을 `.env`로 복사해 값을 설정합니다. 실제 `.env`는 Git에 올리지 않습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.web.server
```

`start-web.cmd`로도 실행할 수 있습니다. 화면: `http://127.0.0.1:8000`, API 명세: `/api/openapi.json`.

주요 설정은 `DATA_GO_KR_API_KEY`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_DB_URL`, `ANTHROPIC_API_KEY`입니다. Claude 키는 학교 시험 일정 검색에 필요하며, 다른 기능과는 별도입니다.

## 저장소와 배포

현재 작업 저장소는 `SpecSignal`이며 실행 파일은 `PLSAi` 저장소에도 반영했습니다. PLSAi에서는 루트 `index.html`, `CSS/`, `js/`를 유지하고 `pages/`와 Markdown은 변경하지 않았습니다. Python 백엔드는 `src/`에 둡니다.

PLSAi에 Render 배포 설정을 추가했지만 실제 서비스 생성과 공개 URL 발급은 아직 완료하지 않았습니다. GitHub Pages만으로는 Python API가 실행되지 않습니다. 자세한 절차는 [배포 안내](docs/deployment.md)를 참고하세요.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# 실제 DB 검증: 테스트 데이터는 트랜잭션 종료 시 롤백
.\.venv\Scripts\python.exe -m tests.verify_academic_database
```

브라우저 검증에는 개발 환경의 Playwright와 Edge를 사용했습니다. 런타임 의존성에는 포함하지 않습니다. 개별 기능 검증과 실제 클라우드 배포 검증은 구분합니다.

## 문서

현행 문서는 이 README와 아래 두 문서로 관리합니다.

- [개발 문서](docs/development.md): 코드 구조, API·DB 연결, 화면 규칙, 검증·제한사항
- [배포 문서](docs/deployment.md): 저장소 구조, Render 설정, 배포 후 확인

과거 구현과 DB 설계 상세는 [이전 기록](docs/history/README.md)에 보존합니다.
