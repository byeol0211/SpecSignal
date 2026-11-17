> Integration update (2026-11-10): PLSAi frontend now runs on the existing FastAPI server. Certification list, details and yearly exam schedules use backend APIs. Profile, bookmarks and personal schedules still use localStorage; AI and competition submission remain unconnected. Run `python -m src.web.server` and open http://127.0.0.1:8000. Earlier removal/pending statements below describe the previous stage.

# SpecSignal 프로젝트 개요

> 현재 PLSAi 화면을 적용했으며, 자격증 목록·상세·시험일정은 [공식 API 직접 조회](official-api.md)로 제공합니다. Supabase 초기 수집이 필요하지 않습니다. 프로필·개인 일정·관심 목록은 아직 브라우저 저장 방식입니다. 아래 적용 전 상태는 과거 기록입니다.

작성 기준: 2026-11-10.

## 작품 조건 변경에 따른 전환

**작품 조건 변경으로 인해 기존 프론트엔드를 제거하고 [PLSAi](https://github.com/byeol0211/PLSAi) 기반으로 프론트엔드를 재구축하기로 했습니다.** 서비스의 기능과 목표는 동일하게 유지합니다.

SpecSignal은 대학생이 자격증과 대외활동을 탐색하고, 자신의 학사일정과 준비 가능 시간을 고려하여 계획을 세우도록 돕는 서비스입니다.

## 유지하는 기능 목표

- 자격증·공모전 탐색, 상세정보와 시험·접수 일정 확인
- 프로필과 관심 분야에 따른 추천 및 대화형 안내
- 관심 항목 저장과 개인 캘린더 일정 관리
- 학사일정과 준비 일정 비교
- 일정 알림과 준비 계획 지원

## 현재 상태

기존 프론트엔드는 제거했습니다. PLSAi 소스는 `artifacts/PLSAi-reference/`에 참조용으로 받아두었으며, 서비스에 적용하거나 기존 백엔드에 연결하지는 않았습니다. PLSAi의 예시 데이터·localStorage·추천 데모는 실제 DB·AI 연동과 구분합니다.

FastAPI API·인증, 자격증 데이터 수집·정규화, Supabase 연결·마이그레이션은 유지합니다. 화면에서 제공하던 기능은 새 프론트엔드에 다시 구현하고 연결해야 합니다.

## 이전 기록

이전 기능별 구현 상태와 기획 설명은 [전환 전 프로젝트 기록](history/project-overview-before-plsai.md)에 보존합니다. 해당 기록의 구현 완료·검증 결과는 과거 기준입니다.
