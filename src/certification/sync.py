"""국가자격 공공데이터 수집 → Supabase 저장.

기존 수집 함수(collect_items, collect_info)를 그대로 사용하므로 재시도·페이지 처리·원문 저장
정책이 웹 조회 때와 동일하다. 실패한 종목은 기존 DB 데이터를 유지하고 실패 기록만 남긴다.

  python -m src.certification.sync all              # 목록 → 상세 → 일정 (갱신 주기가 지난 것만)
  python -m src.certification.sync all --force      # 주기와 무관하게 전체 수집 (초기 적재)
  python -m src.certification.sync details --jmcd 1320 --force
  python -m src.certification.sync schedules --year 2025 --limit 20
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg

from src.certification.collect_info import collect_info
from src.certification.collect_items import collect_items
from src.certification.normalize import detail_to_row, item_to_row, schedules_to_rows
from src.config import get_settings
from src.db import certifications as repo
from src.db.connection import DatabaseNotConfigured, connect


logger = logging.getLogger("specsignal.sync")
DEFERRED_RETRY_DELAY_SECONDS = 5
ERROR_SUMMARY_LIMIT = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _short(text: str | None, limit: int = 500) -> str:
    return " ".join((text or "").split())[:limit]


def _run_status(stats: dict) -> str:
    if stats["error"] and not (stats["success"] or stats["empty"]):
        return "error"
    if stats["error"]:
        return "partial"
    if stats["empty"] and not stats["success"]:
        return "empty"
    return "success"


def _add(stats: dict, counts: dict) -> None:
    for key in ("inserted", "updated", "unchanged", "deactivated"):
        stats[key] += counts.get(key, 0)


def _new_stats(requested: int) -> dict:
    return {"requested": requested, "success": 0, "empty": 0, "error": 0,
            "inserted": 0, "updated": 0, "unchanged": 0, "deactivated": 0}


def _log_summary(job: str, status: str, stats: dict, started: float) -> None:
    logger.info(
        "[%s] %s · 요청 %d · 성공 %d · 빈 결과 %d · 실패 %d · 신규 %d · 변경 %d · 유지 %d · 비활성/삭제 %d · %.1f초",
        job, status, stats["requested"], stats["success"], stats["empty"], stats["error"],
        stats["inserted"], stats["updated"], stats["unchanged"], stats["deactivated"],
        time.monotonic() - started)


# ---------------------------------------------------------------------------
# 종목 목록
# ---------------------------------------------------------------------------

def sync_list(conn: psycopg.Connection, *, force: bool = False) -> str:
    settings = get_settings()
    last = repo.last_list_sync(conn)
    if not force and last and _now() - last < timedelta(hours=settings.list_refresh_hours):
        logger.info("[certification_list] 건너뜀 · 마지막 수집 %s (주기 %d시간)",
                    last.isoformat(), settings.list_refresh_hours)
        return "skipped"

    started = time.monotonic()
    stats = _new_stats(1)
    run_id = repo.start_run(conn, "certification_list", {"force": force})
    result = collect_items()
    error = None
    if not result["ok"]:
        error = f"HTTP {result.get('http_status')}: {_short(result['error'])}"
    else:
        try:
            rows = [item_to_row(item) for item in result["items"]]
        except ValueError as exc:
            error = f"응답 검증 실패: {exc}"
    if error:
        stats["error"] = 1
        logger.error("[certification_list] 수집 실패 (기존 데이터 유지): %s", error)
    else:
        with conn.transaction():
            counts = repo.upsert_certifications(conn, rows, datetime.fromisoformat(result["fetched_at"]))
        if counts.get("deactivation_skipped"):
            logger.warning("[certification_list] 응답 종목 수(%d)가 기존 대비 너무 적어 비활성화를 건너뜀", len(rows))
        stats["success"] = 1
        _add(stats, counts)
    status = _run_status(stats)
    repo.finish_run(conn, run_id, status, stats, error)
    _log_summary("certification_list", status, stats, started)
    return status


# ---------------------------------------------------------------------------
# 종목별 상세정보 / 시험일정
# ---------------------------------------------------------------------------

def _sync_targets(conn: psycopg.Connection, job: str, resource: str, year: int, targets: list[dict],
                  fetch, store, params: dict) -> str:
    """종목 목록을 순회하며 fetch → store. 일시 장애로 실패한 종목은 마지막에 한 번 더 시도한다."""
    settings = get_settings()
    started = time.monotonic()
    stats = _new_stats(len(targets))
    errors: list[str] = []
    run_id = repo.start_run(conn, job, params)
    try:
        pending = list(targets)
        for round_no in (1, 2):
            deferred = []
            for index, target in enumerate(pending, 1):
                if index > 1 or round_no > 1:
                    time.sleep(settings.request_interval_seconds)
                label = f"[{job}] ({index}/{len(pending)}) {target['jm_cd']} {target['name']}"
                attempted = _now()
                try:
                    result = fetch(target)
                except ValueError as exc:  # 입력 검증 오류 (재시도 무의미)
                    result = {"ok": False, "error": str(exc), "retryable": False}
                if not result["ok"]:
                    message = _short(result.get("error"))
                    if result.get("retryable") and round_no == 1:
                        deferred.append(target)
                        logger.warning("%s · 일시 장애, 마지막에 재시도: %s", label, message)
                        continue
                    stats["error"] += 1
                    errors.append(f"{target['jm_cd']}: {message}")
                    with conn.transaction():
                        repo.record_sync_state(conn, target["id"], resource, year, "error", attempted,
                                               error=message)
                    logger.error("%s · 실패 (기존 데이터 유지): %s", label, message)
                    continue
                try:
                    with conn.transaction():
                        status, counts, note = store(target, result, attempted)
                        repo.record_sync_state(conn, target["id"], resource, year, status, attempted,
                                               record_count=counts.get("records", 0))
                except ValueError as exc:  # 응답 검증 실패 → 저장하지 않음
                    stats["error"] += 1
                    errors.append(f"{target['jm_cd']}: 검증 실패 {exc}")
                    with conn.transaction():
                        repo.record_sync_state(conn, target["id"], resource, year, "error", attempted,
                                               error=f"응답 검증 실패: {_short(str(exc))}")
                    logger.error("%s · 응답 검증 실패 (저장 안 함): %s", label, exc)
                    continue
                stats[status] += 1
                _add(stats, counts)
                logger.info("%s · %s", label, note)
            if not deferred:
                break
            logger.info("[%s] 일시 장애 %d건을 %d초 후 재시도합니다.", job, len(deferred),
                        DEFERRED_RETRY_DELAY_SECONDS)
            time.sleep(DEFERRED_RETRY_DELAY_SECONDS)
            pending = deferred
    finally:
        status = _run_status(stats) if stats["requested"] else "success"
        summary = "\n".join(errors[:ERROR_SUMMARY_LIMIT]) or None
        if len(errors) > ERROR_SUMMARY_LIMIT:
            summary += f"\n... 외 {len(errors) - ERROR_SUMMARY_LIMIT}건"
        if conn.closed:
            logger.error("[%s] DB 연결이 끊겨 작업 결과를 기록하지 못했습니다.", job)
        else:
            repo.finish_run(conn, run_id, status, stats, summary)
        _log_summary(job, status, stats, started)
    return status


def _describe(counts: dict, kind: str) -> str:
    return (f"{kind} {counts['records']}건 (신규 {counts['inserted']}, 변경 {counts['updated']}, "
            f"유지 {counts['unchanged']}, 비활성/삭제 {counts['deactivated']})")


def sync_details(conn: psycopg.Connection, *, jm_cds: list[str] | None = None,
                 limit: int | None = None, force: bool = False) -> str:
    hours = None if force else get_settings().details_refresh_hours
    targets = repo.certifications_to_sync(conn, "details", 0, hours, jm_cds, limit)

    def store(target, result, attempted):
        rows = [detail_to_row(record) for record in result["items"]]
        if not rows:
            # 빈 응답으로 기존 섹션을 지우지 않는다.
            return "empty", {"records": 0}, "API 빈 결과 (기존 데이터 유지)"
        counts = repo.replace_details(conn, target["id"], rows, attempted)
        counts["records"] = len(rows)
        return "success", counts, _describe(counts, "상세 섹션")

    return _sync_targets(conn, "certification_details", "details", 0, targets,
                         lambda t: collect_info(t["jm_cd"]), store,
                         {"jm_cds": jm_cds, "limit": limit, "force": force})


def sync_schedules(conn: psycopg.Connection, *, years: list[str] | None = None,
                   jm_cds: list[str] | None = None, limit: int | None = None,
                   force: bool = False) -> list[str]:
    settings = get_settings()
    hours = None if force else settings.schedule_refresh_hours
    statuses = []
    for year in years or settings.schedule_years():
        targets = repo.certifications_to_sync(conn, "schedule", int(year), hours, jm_cds, limit)

        def fetch(target, year=year):
            if not target["qualgb_cd"]:
                raise ValueError("자격구분 코드가 없어 일정을 조회할 수 없습니다.")
            return collect_info(target["jm_cd"], year=year, category=target["qualgb_cd"])

        def store(target, result, attempted, year=year):
            rows, warnings = schedules_to_rows(result["items"])
            for warning in warnings:
                logger.warning("[certification_schedules] %s %s", target["jm_cd"], warning)
            if not rows:
                return "empty", {"records": 0}, f"{year}년 API 빈 결과 (기존 데이터 유지)"
            counts = repo.replace_exams(conn, target["id"], int(year), target["qualgb_cd"], rows, attempted)
            counts["records"] = len(rows)
            return "success", counts, f"{year}년 " + _describe(counts, "일정(단계별)")

        statuses.append(_sync_targets(
            conn, "certification_schedules", "schedule", int(year), targets, fetch, store,
            {"year": year, "jm_cds": jm_cds, "limit": limit, "force": force}))
    return statuses


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="국가자격 공공데이터 → Supabase 동기화")
    parser.add_argument("job", choices=["list", "details", "schedules", "all"])
    parser.add_argument("--force", action="store_true", help="갱신 주기와 무관하게 수집")
    parser.add_argument("--jmcd", action="append", help="특정 종목코드만 (여러 번 지정 가능)")
    parser.add_argument("--year", action="append", help="일정 수집 연도 (기본: CERT_SCHEDULE_YEAR_OFFSETS)")
    parser.add_argument("--limit", type=int, help="작업별 최대 종목 수 (테스트·트래픽 조절용)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        with connect() as conn:
            conn.autocommit = True  # 작업 로그를 즉시 남기고, 저장 단위는 명시적 트랜잭션으로 묶는다
            statuses = []
            if args.job in ("list", "all"):
                statuses.append(sync_list(conn, force=args.force))
            if args.job in ("details", "all"):
                statuses.append(sync_details(conn, jm_cds=args.jmcd, limit=args.limit, force=args.force))
            if args.job in ("schedules", "all"):
                statuses += sync_schedules(conn, years=args.year, jm_cds=args.jmcd,
                                           limit=args.limit, force=args.force)
    except (DatabaseNotConfigured, psycopg.OperationalError) as exc:
        logger.error("DB 연결 실패: %s", exc)
        return 1
    if "error" in statuses:
        return 1
    return 2 if "partial" in statuses else 0


if __name__ == "__main__":
    sys.exit(main())
