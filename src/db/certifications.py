"""국가자격 데이터 저장소. 쓰기 함수는 service 권한 연결에서만 호출한다."""

from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from src.certification.normalize import EXAM_KEY_FIELDS, EXAM_VALUE_FIELDS, ITEM_FIELDS


CERT_COLUMNS = tuple(ITEM_FIELDS.values())
# 목록 응답이 기존 활성 종목 수의 절반 미만이면 부분 응답으로 보고 비활성화를 건너뛴다.
DEACTIVATION_MIN_RATIO = 0.5


def _counts() -> dict[str, int]:
    return {"inserted": 0, "updated": 0, "unchanged": 0, "deactivated": 0}


# ---------------------------------------------------------------------------
# 쓰기 (수집)
# ---------------------------------------------------------------------------

def upsert_certifications(conn: psycopg.Connection, rows: list[dict], synced_at: datetime) -> dict:
    counts = _counts()
    existing = {r["jm_cd"]: r for r in conn.execute(
        f"select is_active, {', '.join(CERT_COLUMNS)} from public.certifications").fetchall()}
    for row in rows:
        old = existing.get(row["jm_cd"])
        if old is None:
            counts["inserted"] += 1
        elif not old["is_active"] or any(old[c] != row[c] for c in CERT_COLUMNS):
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    columns = ", ".join(CERT_COLUMNS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in CERT_COLUMNS if c != "jm_cd")
    with conn.cursor() as cur:
        cur.executemany(
            f"""insert into public.certifications ({columns}, is_active, list_synced_at)
                values ({', '.join(f'%({c})s' for c in CERT_COLUMNS)}, true, %(synced_at)s)
                on conflict (jm_cd) do update
                set {updates}, is_active = true, list_synced_at = excluded.list_synced_at""",
            [{**row, "synced_at": synced_at} for row in rows],
        )

    active_before = sum(1 for r in existing.values() if r["is_active"])
    if rows and len(rows) >= active_before * DEACTIVATION_MIN_RATIO:
        counts["deactivated"] = conn.execute(
            "update public.certifications set is_active = false "
            "where is_active and jm_cd <> all(%s)",
            ([r["jm_cd"] for r in rows],),
        ).rowcount
    else:
        counts["deactivation_skipped"] = True
    return counts


def replace_details(conn: psycopg.Connection, certification_id: int, rows: list[dict],
                    synced_at: datetime) -> dict:
    """수집 성공 시 호출. 응답에 없는 섹션은 공식 데이터에서 빠진 것이므로 삭제한다."""
    counts = _counts()
    existing = {r["info_gb"]: r["contents"] for r in conn.execute(
        "select info_gb, contents from public.certification_details where certification_id = %s",
        (certification_id,)).fetchall()}
    for row in rows:
        if row["info_gb"] not in existing:
            counts["inserted"] += 1
        elif existing[row["info_gb"]] != row["contents"]:
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
    with conn.cursor() as cur:
        cur.executemany(
            """insert into public.certification_details (certification_id, info_gb, contents, last_synced_at)
               values (%(certification_id)s, %(info_gb)s, %(contents)s, %(synced_at)s)
               on conflict (certification_id, info_gb) do update
               set contents = excluded.contents, last_synced_at = excluded.last_synced_at""",
            [{**row, "certification_id": certification_id, "synced_at": synced_at} for row in rows],
        )
    counts["deactivated"] = conn.execute(
        "delete from public.certification_details where certification_id = %s and info_gb <> all(%s)",
        (certification_id, [r["info_gb"] for r in rows]),
    ).rowcount
    conn.execute("update public.certifications set details_synced_at = %s where id = %s",
                 (synced_at, certification_id))
    return counts


def replace_exams(conn: psycopg.Connection, certification_id: int, year: int, qualgb_cd: str,
                  rows: list[dict], synced_at: datetime) -> dict:
    """한 종목·연도·자격구분의 전체 일정을 정상 수집했을 때만 호출한다.

    응답에서 사라진 행은 삭제하지 않고 is_active=false로 둔다 (캘린더 연결 보존).
    """
    counts = _counts()
    fields = EXAM_KEY_FIELDS + EXAM_VALUE_FIELDS
    existing = {
        tuple(r[f] for f in EXAM_KEY_FIELDS): r
        for r in conn.execute(
            f"select id, is_active, {', '.join(fields)} from public.certification_exams "
            "where certification_id = %s and impl_year = %s and qualgb_cd = %s",
            (certification_id, year, qualgb_cd)).fetchall()
    }
    seen = set()
    for row in rows:
        key = tuple(row[f] for f in EXAM_KEY_FIELDS)
        seen.add(key)
        old = existing.get(key)
        if old is None:
            counts["inserted"] += 1
        elif not old["is_active"] or any(old[f] != row[f] for f in EXAM_VALUE_FIELDS):
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
    with conn.cursor() as cur:
        cur.executemany(
            f"""insert into public.certification_exams
                  (certification_id, {', '.join(fields)}, is_active, last_synced_at)
                values (%(certification_id)s, {', '.join(f'%({f})s' for f in fields)}, true, %(synced_at)s)
                on conflict on constraint certification_exams_natural_key do update
                set {', '.join(f'{f} = excluded.{f}' for f in EXAM_VALUE_FIELDS)},
                    is_active = true, last_synced_at = excluded.last_synced_at""",
            [{**row, "certification_id": certification_id, "synced_at": synced_at} for row in rows],
        )
    stale_ids = [r["id"] for key, r in existing.items() if key not in seen and r["is_active"]]
    if stale_ids:
        counts["deactivated"] = conn.execute(
            "update public.certification_exams set is_active = false where id = any(%s)",
            (stale_ids,)).rowcount
    return counts


def record_sync_state(conn: psycopg.Connection, certification_id: int, resource: str, year: int,
                      status: str, attempted_at: datetime, *, error: str | None = None,
                      record_count: int | None = None) -> None:
    """실패 시 last_success_at과 기존 데이터는 그대로 두고 시도 결과만 남긴다."""
    conn.execute(
        """insert into public.certification_sync_state
             (certification_id, resource, impl_year, last_attempt_at, last_success_at,
              last_status, last_error, record_count)
           values (%(id)s, %(resource)s, %(year)s, %(at)s,
                   case when %(status)s <> 'error' then %(at)s end, %(status)s, %(error)s, %(count)s)
           on conflict (certification_id, resource, impl_year) do update
           set last_attempt_at = excluded.last_attempt_at,
               last_success_at = coalesce(excluded.last_success_at, certification_sync_state.last_success_at),
               last_status = excluded.last_status,
               last_error = excluded.last_error,
               record_count = coalesce(excluded.record_count, certification_sync_state.record_count)""",
        {"id": certification_id, "resource": resource, "year": year, "at": attempted_at,
         "status": status, "error": error, "count": record_count},
    )


def start_run(conn: psycopg.Connection, job: str, params: dict) -> int:
    return conn.execute("insert into public.sync_runs (job, params) values (%s, %s) returning id",
                        (job, Jsonb(params))).fetchone()["id"]


def finish_run(conn: psycopg.Connection, run_id: int, status: str, stats: dict,
               error_summary: str | None = None) -> None:
    conn.execute(
        """update public.sync_runs set status = %(status)s, finished_at = now(),
             requested_count = %(requested)s, success_count = %(success)s, empty_count = %(empty)s,
             error_count = %(error)s, inserted_count = %(inserted)s, updated_count = %(updated)s,
             unchanged_count = %(unchanged)s, deactivated_count = %(deactivated)s,
             error_summary = %(summary)s
           where id = %(id)s""",
        {**{k: stats.get(k, 0) for k in ("requested", "success", "empty", "error", "inserted",
                                         "updated", "unchanged", "deactivated")},
         "status": status, "summary": error_summary, "id": run_id},
    )


def certifications_to_sync(conn: psycopg.Connection, resource: str, year: int,
                           older_than_hours: int | None, jm_cds: list[str] | None = None,
                           limit: int | None = None) -> list[dict]:
    """갱신 대상: 활성 종목 중 성공 기록이 없거나 주기보다 오래된 것 (older_than_hours=None이면 전체)."""
    return conn.execute(
        """select c.id, c.jm_cd, c.name, c.qualgb_cd
           from public.certifications c
           left join public.certification_sync_state s
             on s.certification_id = c.id and s.resource = %(resource)s and s.impl_year = %(year)s
           where c.is_active
             and (%(jm_cds)s::text[] is null or c.jm_cd = any(%(jm_cds)s))
             and (%(hours)s::int is null or s.last_success_at is null
                  or s.last_success_at < now() - make_interval(hours => %(hours)s::int))
           order by s.last_success_at nulls first, c.jm_cd
           limit %(limit)s""",
        {"resource": resource, "year": year, "jm_cds": jm_cds, "hours": older_than_hours,
         "limit": limit},
    ).fetchall()


def last_list_sync(conn: psycopg.Connection) -> datetime | None:
    return conn.execute("select max(list_synced_at) as at from public.certifications").fetchone()["at"]


# ---------------------------------------------------------------------------
# 읽기 (웹 API)
# ---------------------------------------------------------------------------

def list_certifications(conn: psycopg.Connection, *, q: str | None = None,
                        qualgb_cd: str | None = None, field: str | None = None,
                        limit: int | None = None, offset: int = 0) -> list[dict]:
    pattern = None
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
    return conn.execute(
        f"""select {', '.join(CERT_COLUMNS)}, list_synced_at, details_synced_at, updated_at
            from public.certifications
            where is_active
              and (%(pattern)s::text is null or name ilike %(pattern)s or jm_cd ilike %(pattern)s
                   or oblig_fld_nm ilike %(pattern)s or mdoblig_fld_nm ilike %(pattern)s)
              and (%(qualgb)s::text is null or qualgb_cd = %(qualgb)s)
              and (%(field)s::text is null or oblig_fld_nm = %(field)s)
            order by name, jm_cd
            limit %(limit)s offset %(offset)s""",
        {"pattern": pattern, "qualgb": qualgb_cd, "field": field, "limit": limit, "offset": offset},
    ).fetchall()


def get_certification(conn: psycopg.Connection, jm_cd: str) -> dict | None:
    return conn.execute(
        f"select id, is_active, {', '.join(CERT_COLUMNS)}, list_synced_at, details_synced_at, updated_at "
        "from public.certifications where jm_cd = %s", (jm_cd,)).fetchone()


def get_details(conn: psycopg.Connection, certification_id: int) -> list[dict]:
    return conn.execute(
        "select info_gb, contents, last_synced_at from public.certification_details "
        "where certification_id = %s order by id", (certification_id,)).fetchall()


def get_exams(conn: psycopg.Connection, certification_id: int, *, year: int | None = None,
              qualgb_cd: str | None = None, phase: str | None = None) -> list[dict]:
    return conn.execute(
        f"""select id, {', '.join(EXAM_KEY_FIELDS + EXAM_VALUE_FIELDS)}, last_synced_at, updated_at
            from public.certification_exams
            where certification_id = %(id)s and is_active
              and (%(year)s::int is null or impl_year = %(year)s)
              and (%(qualgb)s::text is null or qualgb_cd = %(qualgb)s)
              and (%(phase)s::text is null or exam_phase = %(phase)s)
            order by impl_year desc, impl_seq desc, exam_phase desc, reg_start_date desc nulls last""",
        {"id": certification_id, "year": year, "qualgb": qualgb_cd, "phase": phase},
    ).fetchall()


def get_sync_state(conn: psycopg.Connection, certification_id: int, resource: str,
                   year: int = 0) -> dict | None:
    return conn.execute(
        "select last_attempt_at, last_success_at, last_status, last_error, record_count "
        "from public.certification_sync_state "
        "where certification_id = %s and resource = %s and impl_year = %s",
        (certification_id, resource, year)).fetchone()


def latest_runs(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        """select distinct on (job) id, job, status, params, requested_count, success_count,
                  empty_count, error_count, inserted_count, updated_count, unchanged_count,
                  deactivated_count, error_summary, started_at, finished_at
           from public.sync_runs order by job, started_at desc""").fetchall()
