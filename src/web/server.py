"""SpecSignal web server: official API queries for the frontend; Supabase for account APIs."""

import argparse
import logging
import threading
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager

import psycopg
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from pathlib import Path

from src.certification.collect_info import validate_query
from src.web.public_api import load_items, load_info
from src.config import get_settings
from src.db import certifications as repo
from src.db.connection import DatabaseNotConfigured, close_pool, service_transaction, user_transaction
from src.web.auth import AuthUser, current_user
from src.academic.routes import router as academic_router


logger = logging.getLogger("specsignal.web")
DB_UNAVAILABLE = "자격증 데이터베이스에 연결하지 못했습니다. 잠시 후 다시 시도해주세요."
NOT_COLLECTED = "아직 수집되지 않은 정보입니다. 데이터 수집 후 다시 조회해주세요."


# ---------------------------------------------------------------------------
# 기존 화면용 조회 (응답 형식 유지)
# ---------------------------------------------------------------------------

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
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
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

app.include_router(academic_router)

WEB_DIR = Path(__file__).resolve().parent
STATIC_FILES = {
    "": "index.html",
    "CSS/style.css": "CSS/style.css",
    "js/app.js": "js/app.js",
    "js/backend.js": "js/backend.js",
    "js/academic.js": "js/academic.js",
}


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    filename = STATIC_FILES.get(path)
    if filename is None:
        raise HTTPException(404, "Not found")
    return FileResponse(WEB_DIR / filename)

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
