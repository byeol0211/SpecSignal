> Integration update (2026-11-10): PLSAi frontend now runs on the existing FastAPI server. Certification list, details and yearly exam schedules use backend APIs. Profile, bookmarks and personal schedules still use localStorage; AI and competition submission remain unconnected. Run `python -m src.web.server` and open http://127.0.0.1:8000. Earlier removal/pending statements below describe the previous stage.

# 프론트엔드 구현 방향

> 2026-11-15: 계정 연결·학교/학과 입력·학사일정 출처 확인·선택 등록 화면을 추가했습니다. [학사일정 구현](academic-calendar.md)을 참고하세요. 공통 자료는 DB에서 재사용하고 등록 일정은 계정별로 분리합니다.

> 현재 자격증 목록·상세·시험일정은 [공식 API](official-api.md)에 연결했습니다. 카테고리·검색·1개/2개 보기와 기존 화면 구성은 유지합니다. 아래 미적용·DB 연결 예정 설명은 이전 단계 기록입니다.

작성 기준: 2026-11-10.

## 변경 사유와 기준

**작품 조건 변경에 따라 프론트엔드를 PLSAi 기반으로 재구축합니다.** 서비스 기능과 목표는 유지하며, 기존 Figma 기반 화면 구현은 현재 구현 기준에서 제외하고 이력으로 보존합니다.

기준 소스: [PLSAi 저장소](https://github.com/byeol0211/PLSAi).

PLSAi는 HTML·CSS·JavaScript로 구성된 모바일 중심 프로토타입입니다. 루트 `index.html`, `CSS/style.css`, `js/app.js`가 기본 화면을 구성하며, `pages/`에는 별도 프로토타입 파일들이 있습니다.

## 적용 상태와 후속 작업

- 소스는 `artifacts/PLSAi-reference/`에 참조용으로 확보했습니다.
- 기존 화면 코드·에셋·전용 UI 검증·스크린샷은 제거했습니다.
- PLSAi의 서비스 적용, FastAPI·Supabase 연결, 기능 재구현과 화면 검증은 아직 진행하지 않았습니다.
- 프로토타입의 예시 데이터, localStorage 저장, 추천·학사일정 데모는 실제 서비스 연동으로 대체해야 합니다.

## 이전 기록

기존 Figma 화면·SVG·반응형 구현과 UI 검증 내역은 [이전 디자인 구현 기록](history/design-implementation-before-plsai.md)에 보존합니다. 새 프론트엔드의 구현·검증 결과로 사용하지 않습니다.
