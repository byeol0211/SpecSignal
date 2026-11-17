# 실행 저장소와 배포

작성 기준: 2026-11-17.

## 현재 상태

[SpecSignal 저장소](https://github.com/byeol0211/SpecSignal)는 개발·테스트·문서·배포의 기준이며, [PLSAi 저장소](https://github.com/byeol0211/PLSAi)에도 기존 정적 파일 구조로 같은 기능을 반영합니다. 두 저장소 모두 Render 설정을 포함합니다. 서비스 이름은 각각 `specsignal`, `plsai`로 구분합니다. 실제 서비스 생성, 환경변수 등록과 공개 URL 검증은 아직 완료되지 않았습니다.

## 저장소 구조

```text
index.html
CSS/style.css
js/app.js
js/backend.js
js/academic.js
pages/                 기존 파일 유지
README.md 등           기존 Markdown 유지
src/                   FastAPI·인증·DB·공식 API·학사일정
requirements.txt
start-web.cmd
.env.example
render.yaml
.python-version
```

위 구조는 PLSAi 기준입니다. SpecSignal의 프론트엔드는 `src/web/`에 있으며 테스트·문서·마이그레이션도 포함합니다. PLSAi에 반영할 때만 위 루트 구조로 복사하고 서버의 정적 파일 루트를 조정합니다. PLSAi에는 실제 `.env`, 테스트, 개발 산출물과 새 문서를 올리지 않습니다. PLSAi 실행 패키지는 기존 Supabase 프로젝트 연결을 전제로 하며 새 DB 전체 구축용 마이그레이션은 포함하지 않았습니다.

## Render 구성

- Python 웹 서비스 하나에서 화면과 API를 같은 주소로 제공합니다.
- `render.yaml`: Free 플랜, Singapore 리전, `main` 브랜치, 의존성 설치 및 시작 명령.
- `.python-version`: Python 3.14 계열.
- 상태 확인: `GET /healthz` → `{"status":"ok"}`. 외부 API·DB 상태 전체를 보장하는 검사는 아닙니다.

```sh
pip install -r requirements.txt
uvicorn src.web.server:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-graceful-shutdown 600
```

대표 저장소 배포: https://render.com/deploy?repo=https://github.com/byeol0211/SpecSignal

PLSAi 배포: https://render.com/deploy?repo=https://github.com/byeol0211/PLSAi

전체 서비스 하나를 공개하려면 사용할 저장소 하나만 선택하면 됩니다. 두 저장소를 모두 배포할 필요는 없습니다.

Render에서 저장소 접근 권한을 연결하고 Blueprint를 생성한 뒤 아래 환경변수를 대시보드에 입력합니다. 실제 값은 Git이나 문서에 쓰지 않습니다.

| 변수 | 용도 |
|---|---|
| `SUPABASE_URL` | Supabase 프로젝트 |
| `SUPABASE_PUBLISHABLE_KEY` | Auth 공개 키 |
| `SUPABASE_DB_URL` | DB 연결 문자열. IPv4 환경에서는 pooler 사용 |
| `DATA_GO_KR_API_KEY` | 자격증 공식 API |
| `ANTHROPIC_API_KEY` | 학교 시험 일정 검색 |
| `ANTHROPIC_MODEL` | 기본 `claude-sonnet-4-6` |
| `SUPABASE_JWT_SECRET` | 레거시 HS256 프로젝트만 별도 추가 |

계정은 생성된 서비스 주소를 Supabase Auth의 Site URL·허용 리디렉션 URL에도 맞춰야 합니다. 인증 메일 사용 시 SMTP와 발송 한도도 확인합니다.

## 배포 후 확인

1. `/healthz`, `/`, CSS·JS 파일이 정상 응답하는지 확인합니다.
2. 회원가입·이메일 인증·로그인과 프로필 복원을 확인합니다.
3. 자격증 공식 API, 공모전 목록·이미지, 홈 추천 카드를 확인합니다.
4. 학교 시험 일정 등록 후 새로고침·재로그인 시 본인 일정이 복원되는지 확인합니다.
5. 기간 표시, 공식 날짜 기본값과 수동 수정도 확인합니다.

GitHub Pages는 정적 화면만 제공하므로 현재 Python API는 실행되지 않습니다. 전체 서비스 접속 주소는 실제 배포가 완료된 Render 서비스 주소를 사용해야 합니다.

학교 일정 검색 작업은 웹 프로세스 안에서 실행됩니다. 서버 종료·재배포·휴면 등으로 중단될 수 있으며, 독립 작업 큐나 자동 복구 워커는 아직 없습니다.
