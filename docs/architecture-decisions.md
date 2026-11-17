> Integration update (2026-11-10): PLSAi frontend now runs on the existing FastAPI server. Certification list, details and yearly exam schedules use backend APIs. Profile, bookmarks and personal schedules still use localStorage; AI and competition submission remain unconnected. Run `python -m src.web.server` and open http://127.0.0.1:8000. Earlier removal/pending statements below describe the previous stage.

# SpecSignal 아키텍처 결정

## 자격증 조회 방식 변경 (2026-11-10)

현재 규모와 관리 난이도를 고려하여 자격증 정보는 Supabase 사전 수집 대신 서버를 통한 공식 API 직접 조회로 전환합니다. API 키는 서버에 유지하며 정상 응답에 5분 메모리 캐시를 적용합니다. 현재 화면 구성과 서비스 목표는 유지합니다. [연결 상세](official-api.md).

작성 기준: 2026-11-10.

## 작품 조건 변경에 따른 PLSAi 전환

작품 조건 변경으로 인해 기존 프론트엔드를 전면 제거하고 [PLSAi](https://github.com/byeol0211/PLSAi)를 기반으로 다시 구축합니다. 서비스의 기능과 목표는 동일하게 유지합니다.

## 유지하는 구조

- FastAPI 백엔드 API와 Supabase 인증 검증
- Supabase PostgreSQL 데이터·권한 정책·마이그레이션
- 공공데이터 API 기반 자격증 수집·정규화·저장 파이프라인
- 정형 데이터는 수집 파이프라인으로 처리하고, 비정형 학사일정은 출처·검증·사용자 확인을 거쳐 구조화한다는 방향

## 프론트엔드 상태

기존 HTML·CSS·JavaScript·SVG와 UI 검증 자료는 제거했습니다. 기존 화면 경로는 404를 반환하며 백엔드 API는 유지합니다.

PLSAi는 참조용으로 내려받은 상태입니다. 실제 적용과 API 연결은 후속 작업이며, 프로토타입의 예시·데모 기능을 실제 서비스 기능으로 연결해야 합니다.

## 이전 결정 이력

초기 데이터 수집 전략, 데스크톱에서 반응형 웹으로의 변경, 기존 UI 구성과 검증 내역은 [전환 전 아키텍처 기록](history/architecture-decisions-before-plsai.md)에 보존합니다. 과거 문서의 화면 구조와 실행·검증 설명은 현재 프론트엔드 상태를 의미하지 않습니다.
