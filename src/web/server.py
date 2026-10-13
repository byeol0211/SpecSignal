"""SpecSignal 웹 서버 (FastAPI). 프로젝트 루트에서 python -m src.web.server 실행.

자격증 데이터는 공공데이터 API를 직접 호출하지 않고, 수집 작업(src.certification.sync)이
Supabase에 저장한 데이터를 조회한다. 기존 /api/items·/api/details·/api/schedules 응답 형식은 유지한다.
"""

import argparse
import logging
import threading
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager

import psycopg
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pathlib import Path

from src.certification.collect_info import validate_query
from src.certification.normalize import ITEM_FIELDS, rows_to_legacy_schedules
from src.config import get_settings
from src.db import certifications as repo
from src.db.connection import DatabaseNotConfigured, close_pool, service_transaction, user_transaction
from src.web.auth import AuthUser, current_user


logger = logging.getLogger("specsignal.web")
WEB_DIR = Path(__file__).resolve().parent
# 정해진 파일만 제공하여 .env 및 원문 데이터 접근을 막는다.
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/certifications.js": ("certifications.js", "text/javascript; charset=utf-8"),
    "/catalog-live": ("catalog-legacy.html", "text/html; charset=utf-8"),
    "/catalog-legacy.js": ("catalog-legacy.js", "text/javascript; charset=utf-8"),
    "/catalog-legacy.css": ("catalog-legacy.css", "text/css; charset=utf-8"),
}
for asset in (WEB_DIR / "assets").glob("*.svg"):
    STATIC_FILES[f"/assets/{asset.name}"] = (f"assets/{asset.name}", "image/svg+xml")

DB_UNAVAILABLE = "자격증 데이터베이스에 연결하지 못했습니다. 잠시 후 다시 시도해주세요."
NOT_COLLECTED = "아직 수집되지 않은 정보입니다. 데이터 수집 후 다시 조회해주세요."


# ---------------------------------------------------------------------------
# 기존 화면용 조회 (응답 형식 유지)
# ---------------------------------------------------------------------------

def load_items() -> dict:
    try:
        with service_transaction() as conn:
            rows = repo.list_certifications(conn)
            fetched_at = repo.last_list_sync(conn)
    except (DatabaseNotConfigured, psycopg.Error):
        logger.exception("자격증 목록 조회 실패")
        return {"ok": False, "http_status": None, "error": DB_UNAVAILABLE}
    if not rows:
        return {"ok": False, "http_status": None,
                "error": "아직 수집된 자격증 데이터가 없습니다. python -m src.certification.sync all --force 로 초기 수집을 실행하세요."}
    items = [{field: row[column] or "" for field, column in ITEM_FIELDS.items()} for row in rows]
    items.sort(key=lambda item: (item["jmfldnm"], item["jmcd"]))
    return {"ok": True, "source": "supabase", "items": items, "fetched_at": fetched_at.isoformat()}


def load_info(jmcd: str, *, year: str | None = None, category: str | None = None) -> dict:
    """연도가 있으면 시험일정, 없으면 상세정보. 입력 오류는 ValueError."""
    validate_query(jmcd, year, category)
    if year is not None and category is None:
        raise ValueError("일정 조회에는 자격구분이 필요합니다.")
    try:
        with service_transaction() as conn:
            cert = repo.get_certification(conn, jmcd)
            if cert is None:
                return {"ok": False, "not_found": True, "jmcd": jmcd, "error": "등록되지 않은 종목코드입니다."}
            if year is None:
                state = repo.get_sync_state(conn, cert["id"], "details")
                items = [{"infogb": r["info_gb"], "contents": r["contents"] or "", "jmfldnm": cert["name"],
                          "obligfldnm": cert["oblig_fld_nm"] or "", "mdobligfldnm": cert["mdoblig_fld_nm"] or ""}
                         for r in repo.get_details(conn, cert["id"])]
            else:
                state = repo.get_sync_state(conn, cert["id"], "schedule", int(year))
                items = rows_to_legacy_schedules(
                    repo.get_exams(conn, cert["id"], year=int(year), qualgb_cd=category))
    except (DatabaseNotConfigured, psycopg.Error):
        logger.exception("자격증 정보 조회 실패")
        return {"ok": False, "http_status": None, "jmcd": jmcd, "error": DB_UNAVAILABLE}
    if not items and (state is None or state["last_success_at"] is None):
        return {"ok": False, "http_status": None, "jmcd": jmcd, "collected": False, "error": NOT_COLLECTED}
    return {
        "ok": True, "source": "supabase", "jmcd": jmcd, "year": year, "items": items,
        "empty": not items,
        "fetched_at": state["last_success_at"].isoformat() if state and state["last_success_at"] else None,
        # 마지막 수집 시도가 실패했다면 이전에 저장된 데이터라는 표시
        "stale": bool(state and state["last_status"] == "error"),
    }


def legacy_response(result: dict) -> JSONResponse:
    status = 200 if result["ok"] else 404 if result.get("not_found") else 503
    return JSONResponse(result, status_code=status)


# ---------------------------------------------------------------------------
# 앱
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    close_pool()


app = FastAPI(title="SpecSignal API", version="1.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'self'; base-uri 'none'; frame-ancestors 'none'"
    return response


@app.exception_handler(DatabaseNotConfigured)
@app.exception_handler(psycopg.Error)
async def database_error(_: Request, exc: Exception) -> JSONResponse:
    logger.error("DB 오류: %s", type(exc).__name__)
    return JSONResponse({"detail": DB_UNAVAILABLE}, status_code=503)


@app.get("/api/items")
def api_items() -> JSONResponse:
    return legacy_response(load_items())


@app.get("/api/details")
def api_details(jmcd: str = "") -> JSONResponse:
    try:
        return legacy_response(load_info(jmcd))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "http_status": None}, status_code=400)


@app.get("/api/schedules")
def api_schedules(jmcd: str = "", year: str = "", category: str = "") -> JSONResponse:
    try:
        return legacy_response(load_info(jmcd, year=year, category=category))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "http_status": None}, status_code=400)


# --- v1: Supabase 데이터 조회 API ------------------------------------------

@app.get("/api/v1/config")
def public_config() -> dict:
    """프론트엔드 Supabase Auth 초기화용 공개 값. 비밀키는 절대 포함하지 않는다."""
    settings = get_settings()
    return {"supabase_url": settings.supabase_url,
            "supabase_publishable_key": settings.supabase_publishable_key}


@app.get("/api/v1/certifications")
def certifications(q: str | None = Query(None, max_length=50),
                   qualgb_cd: str | None = Query(None, pattern="^[A-Z]$"),
                   field: str | None = Query(None, max_length=50),
                   limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict:
    with service_transaction() as conn:
        rows = repo.list_certifications(conn, q=q, qualgb_cd=qualgb_cd, field=field,
                                        limit=limit, offset=offset)
        synced_at = repo.last_list_sync(conn)
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset,
            "list_synced_at": synced_at}


def _certification_or_404(conn, jm_cd: str) -> dict:
    try:
        validate_query(jm_cd)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    cert = repo.get_certification(conn, jm_cd)
    if cert is None:
        raise HTTPException(404, "등록되지 않은 종목코드입니다.")
    return cert


@app.get("/api/v1/certifications/{jm_cd}")
def certification_detail(jm_cd: str) -> dict:
    with service_transaction() as conn:
        cert = _certification_or_404(conn, jm_cd)
        details = repo.get_details(conn, cert["id"])
        state = repo.get_sync_state(conn, cert["id"], "details")
    return {"certification": cert, "details": details, "details_sync": state}


@app.get("/api/v1/certifications/{jm_cd}/exams")
def certification_exams(jm_cd: str, year: int | None = Query(None, ge=1900, le=2100),
                        phase: str | None = Query(None, pattern="^(written|practical)$")) -> dict:
    with service_transaction() as conn:
        cert = _certification_or_404(conn, jm_cd)
        exams = repo.get_exams(conn, cert["id"], year=year, phase=phase)
        state = repo.get_sync_state(conn, cert["id"], "schedule", year) if year else None
    return {"jm_cd": jm_cd, "year": year, "items": exams, "schedule_sync": state}


@app.get("/api/v1/me")
def me(user: AuthUser = Depends(current_user)) -> dict:
    """본인 프로필·설정. RLS가 적용된 연결이므로 다른 사용자의 행은 조회되지 않는다."""
    with user_transaction(user.claims) as conn:
        profile = conn.execute("select * from public.profiles where id = %s", (user.id,)).fetchone()
        preferences = conn.execute("select * from public.user_preferences where user_id = %s",
                                   (user.id,)).fetchone()
    if profile is None:
        raise HTTPException(404, "프로필이 없습니다.")
    return {"profile": profile, "preferences": preferences}


@app.get("/api/v1/admin/sync-runs")
def sync_runs(user: AuthUser = Depends(current_user)) -> dict:
    """작업별 최근 수집 결과. RLS의 관리자 정책(sync_runs_admin_read)으로 권한을 확인한다."""
    with user_transaction(user.claims) as conn:
        is_admin = conn.execute("select public.is_admin() as ok").fetchone()["ok"]
        if not is_admin:
            raise HTTPException(403, "관리자만 조회할 수 있습니다.")
        return {"runs": repo.latest_runs(conn)}


# --- 정적 파일 (반드시 마지막에 등록) ---------------------------------------

@app.get("/{path:path}", include_in_schema=False)
def static_file(path: str) -> Response:
    entry = STATIC_FILES.get("/" + path)
    if entry is None:
        return Response(b"Not found", status_code=404, media_type="text/plain; charset=utf-8")
    filename, content_type = entry
    return Response((WEB_DIR / filename).read_bytes(), media_type=content_type)


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

@contextmanager
def background_server(host: str = "127.0.0.1", port: int = 0) -> Iterator[str]:
    """테스트·화면 검증용: 별도 스레드에서 서버를 띄우고 기본 URL을 반환한다."""
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("테스트 서버를 시작하지 못했습니다.")
        time.sleep(0.02)
    bound_port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://{host}:{bound_port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description="SpecSignal 반응형 웹 개발 서버")
    parser.add_argument("--host", default="127.0.0.1", help="기본: 로컬 접속. 같은 네트워크 기기 테스트: 0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(f"SpecSignal: http://{args.host}:{args.port} (종료: Ctrl+C)", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
