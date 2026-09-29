# SpecSignal 반응형 웹

2026-09-29 교수님 피드백에 따라 기본 제공 형태를 Windows 데스크톱 앱에서 **PC·태블릿·모바일 브라우저용 반응형 웹**으로 변경했습니다.

## 기본 실행

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.web.server
```

http://127.0.0.1:8000 에 접속합니다. Windows에서는 `start-web.cmd`로 서버를 실행할 수도 있습니다. 웹 실행에는 pywebview나 WebView2 설치가 필요하지 않습니다.

같은 네트워크의 휴대폰에서 확인하려면 `--host 0.0.0.0` 옵션으로 실행하고 `http://PC의LAN주소:8000`에 접속합니다. 네트워크와 방화벽에서 해당 포트 연결이 허용되어 있어야 합니다. 현재 Python 서버는 개발·시연용이며 공개 서비스 배포는 별도 작업입니다.

- 760px 이하: 접이식 메뉴, 세로 화면 배치, 터치 입력에 맞춘 버튼·폼.
- 420px 이하: 자격증 카드 한 열 배치. 캘린더는 7열을 유지합니다.
- 페이지 전체 스크롤과 화면 크기에 맞는 알림·상세·일정 팝업을 지원합니다.
- 데스크톱 전용 실행 코드·의존성·테스트를 제거하고 웹 실행으로 통일했습니다.

반응형 검증: `.\.venv\Scripts\python.exe tests/verify_responsive.py`

구조 변경 결정은 [architecture-decisions.md](docs/architecture-decisions.md)의 9절, 화면 변경은 [design-implementation.md](docs/design-implementation.md)의 반응형 웹 전환 항목에 기록했습니다.

## 현재 기능

현재 기본 화면은 연보라색 테마의 한국어 대시보드입니다. 홈, AI 맞춤 추천, 관심 목록, 자격증·공모전 탐색, 프로필 설정을 같은 사이드바로 연결했습니다.

자격증 둘러보기는 기존 공식 API 전체 목록·검색·자격구분/직무분야 필터·8개 단위 더 보기·상세정보·연도별 시험일정 기능으로 복원했습니다. 진입 시 항상 **전체 보기**이며 프로필로 제한하지 않습니다. **나에게 맞는 자격증**을 선택하면 전공·목표 직무·관심 분야와 종목명/직무분야의 키워드를 비교합니다. 모드 전환 시 검색/필터는 초기화됩니다. 이 맞춤 기능은 키워드 필터이며 AI 추천이나 응시자격 판정이 아닙니다. API가 제공하지 않는 민간자격까지 포함한다는 뜻은 아닙니다.

- 홈: 빈 개인 캘린더로 시작하며 포스트잇 추가·수정·삭제, 날짜별 일정 확인, 월 이동을 지원합니다.
- 추천·탐색·관심 목록: 상세정보, 관심 저장/해제, 날짜 선택·수정 및 알림 시점을 지정하는 일정 등록 팝업을 제공합니다. 관심 저장과 추천만으로 일정이 추가되지 않습니다. 동일 항목의 같은 종류 일정을 다시 저장하면 기존 일정을 수정합니다.
- 프로필: 기본 정보, 학사일정 연도·학기, 직접 입력 및 예시 검색 결과 확인, 최소·평균·최대 공부기간과 하루 공부시간, 알림 설정을 제공합니다.
- 추천: 더미 항목을 관심 분야·입력 키워드·준비기간으로 정렬/필터링하고 등록된 학교 일정과 비교합니다. 실제 LLM은 호출하지 않습니다.
- 알림: 선택한 알림 시점에 도달한 등록 일정, 7일 이내 관심 공모전 마감, 최근 추천을 공통 종 아이콘에서 확인합니다. 실제 발송은 하지 않습니다.
- 날짜·공부기간은 예시입니다. 자격증은 공식 기관 링크를 제공하며, 가상 공모전과 학사일정은 공식 출처가 미연동임을 표시합니다. 학교 자동 조회 스위치는 설정 저장만 수행합니다.

웹 실행: `.\.venv\Scripts\python.exe -m src.web.server` 후 http://127.0.0.1:8000 접속.
입력은 해당 브라우저·포트의 localStorage에 저장됩니다. 데이터베이스 연동은 없습니다.

검증:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests/verify_dashboard.py
.\.venv\Scripts\python.exe tests/verify_ui.py
```

새 대시보드 검증은 저장과 일정의 분리, 선택 날짜 등록, 편집·삭제·새로고침 복원, 프로필과 학사일정, 추천 충돌 안내, 알림 이동, 사용자 입력 이스케이프, 1440/1100/820px 레이아웃과 로컬 아이콘을 확인합니다. 스크린샷은 `artifacts/ui/dashboard-*.png`에 생성합니다.

기존 단독 실 API 자격증 화면은 `/catalog-live`에도 보존했습니다. 아래 기존 API 설명과 `verify_ui.py`는 이 화면에 해당합니다. 대시보드에서는 자격증 둘러보기에 진입할 때 공식 목록을 조회합니다. `tests/verify_catalog_modes.py`는 대시보드의 전체/맞춤 보기, 프로필 독립성, 목록·상세·일정·오류 처리를 검증합니다.

디자인 참고: Figma `29:905` 홈 및 `2:2899` 챗봇의 디자인 컨텍스트와 스크린샷을 확인했습니다. 기존 프로젝트의 SVG 아이콘을 재사용하고 사용자 요청에 맞춰 공통 내비게이션과 인터랙션을 확장했습니다. 제공된 Figma Make 링크는 소스 목록까지 조회됐으나 본문 리소스가 반환되지 않아, 프로필은 요청된 기능 명세와 공통 스타일을 기준으로 구현했습니다.

## 디자인과 검증

원본: [목록 화면](https://www.figma.com/design/2VrkrOxMePoD4E3WtsFxvB?node-id=3-3070), [상세 창](https://www.figma.com/design/2VrkrOxMePoD4E3WtsFxvB?node-id=30-1619).
청보라색 사이드바, 남색 버튼, 흰색 카드와 짙은 그림자, 상세 창의 청보라색 배경을 반영했습니다.
겹쳐 있던 시안 레이어는 하나의 실제 입력 요소로 통합했습니다. 임시 이름·설명은 실제 데이터 또는 사용자 입력으로 대체했습니다.
Figma 원본 SVG는 `src/web/assets/`에 저장되어 외부 이미지 요청 없이 표시됩니다.
화면 크기 1440/1100/820px에서 자동 조회·검색·필터·상세·빈 결과·오류·이름 저장 및 아이콘 크기를 확인합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests/verify_ui.py
```

UI 테스트는 설치된 Edge 브라우저와 테스트 전용 데이터를 사용합니다.
검증 스크린샷은 `artifacts/ui/`에 생성됩니다.

프로젝트 루트 `.env`에 다음 변수를 설정하세요. 키는 서버에서만 읽습니다.

```dotenv
DATA_GO_KR_API_KEY=발급받은키
```

API 활용신청 및 승인이 필요한 경우 공공데이터포털에서 확인하세요.
응답 원문은 `data/raw/`에 저장됩니다. HTTP 상태와 오류 내용은 화면에서 확인할 수 있습니다.
HTTP 200이라도 종목을 찾지 못하면 성공으로 표시하지 않습니다.
이전 조회 결과가 있는 상태에서 갱신에 실패하면 이전 결과임을 표시합니다.

## 데이터 범위와 명세

[한국산업인력공단 국가자격 종목 목록 정보](https://www.data.go.kr/data/15003024/openapi.do)의 공개 명세를 2026-09-23 확인했습니다.

- 서비스 URL: `http://openapi.q-net.or.kr/api/service/rest/InquiryListNationalQualifcationSVC/getList`
- 인증 파라미터: `serviceKey`. 공개 요청변수 표에 별도 페이지 파라미터는 없습니다.
- 형식: XML. 출력 필드: `qualgbcd`, `qualgbnm`, `seriescd`, `seriesnm`, `jmcd`, `jmfldnm`, `obligfldcd`, `obligfldnm`, `mdobligfldcd`, `mdobligfldnm`.
- 종목코드는 이 API에서 소문자 `jmcd`로 제공됩니다. 선행 0을 보존하기 위해 문자열로 처리합니다.
- 실제 GET 호출에서 HTTP 200, `response/header/resultCode=00`, `response/body/items/item` 구조와 613개 종목을 확인했습니다. 종목 수는 조회 시점에 따라 달라질 수 있습니다.
- HTTP 상태와 업무 성공 코드 `00`을 모두 검증합니다. XML 구조가 달라지거나 종목명·종목코드가 누락되면 오류를 표시합니다.

각 카드의 **상세정보 · 시험일정 보기**를 누르면 선택한 종목의 두 API를 조회합니다.
상세정보에는 출제경향·출제기준·취득방법 등 API에서 반환한 항목을 표시합니다.
시험일정은 연도를 선택해 조회하며 필기/실기 접수·시험·발표 기간을 표시합니다.
API별 성공과 실패를 따로 표시하므로 한 API가 실패해도 다른 정보를 볼 수 있습니다.

### 추가 연결 API

- [종목별 자격정보](https://www.data.go.kr/data/15003003/openapi.do): `http://openapi.q-net.or.kr/api/service/rest/InquiryInformationTradeNTQSVC/getList`, GET, `ServiceKey`, `jmCd`.
- [시험일정](https://www.data.go.kr/data/15074408/openapi.do): `https://apis.data.go.kr/B490007/qualExamSchd/getQualExamSchdList`, GET, `serviceKey`, `jmCd`, `qualgbCd`, `implYy`, `dataFormat=xml`, `numOfRows=50`, `pageNo`.
- 실응답 기준 두 API 모두 `response/header/resultCode=00`, `response/body/items/item` 구조를 사용합니다. 일정은 `body/totalCount` 기준으로 전체 페이지를 수집합니다.
- 목록의 `jmcd`를 두 API 요청의 `jmCd`로 전달합니다. 일정 응답 자체에는 종목코드가 없으므로 요청한 코드와 연도를 결과에 함께 기록합니다.
- 같은 회차의 다른 접수기간을 임의로 합치지 않습니다. 빈 일정은 해당 조건의 반환 결과가 없다는 뜻이며 시험 미시행으로 단정하지 않습니다.
- 상세 응답은 일반 텍스트로 표시하며 HTML을 실행하지 않습니다. 두 API의 원문도 `data/raw/`에 별도로 저장합니다.
- 정보처리기사(1320), 2026년 기준 실호출에서 상세 3개 항목과 일정 6건을 확인했습니다.

### 정보 없음과 연결 장애 구분

- 성공 코드 `00`과 빈 `items`가 확인된 경우에만 관련 정보가 없다고 표시합니다. 응답 구조가 깨졌거나 업무 오류가 발생하면 정보 없음으로 처리하지 않습니다.
- `99 / Failed to validate a newly established connection.`은 제공기관의 연결 검증 실패 응답입니다. 같은 종목의 재조회 성공이 확인되어 일시적 장애로 처리합니다. 제공기관 내부의 정확한 원인은 해당 서버 로그 없이는 확정할 수 없습니다.
- 해당 오류, HTTP 502/503/504, 연결 실패·시간 초과는 1초와 2초 간격으로 최대 3회 시도합니다. 인증 오류나 그 밖의 업무 오류는 자동 재시도하지 않습니다.
- 재시도 후에도 실패하면 연결 장애 안내와 다시 조회 버튼을 표시합니다. 기술적 오류와 XML 원문은 접힌 오류 상세에서 확인할 수 있습니다. 각 시도의 응답은 원문 파일로 보존합니다.

CLI 수집만 실행하려면:

```powershell
.\.venv\Scripts\python.exe src/certification/collect_items.py
```

