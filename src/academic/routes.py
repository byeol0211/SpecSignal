"""Authenticated onboarding, shared discovery jobs and private calendar imports."""

from datetime import date, datetime, timezone
from uuid import UUID

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from src.academic.discovery import DiscoveryError, discover, normalize_school
from src.config import get_settings
from src.db.connection import service_transaction, user_transaction
from src.web.auth import AuthUser, current_user

router = APIRouter()


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


@router.post("/api/auth/{action}")
def authenticate(action: str, body: Credentials):
    if action not in {"signup", "login"}:
        raise HTTPException(404)
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(503, "Supabase 계정 연결 설정이 필요합니다.")
    endpoint = "/signup" if action == "signup" else "/token?grant_type=password"
    try:
        response = requests.post(settings.supabase_url + "/auth/v1" + endpoint,
                                 headers={"apikey": settings.supabase_publishable_key},
                                 json=body.model_dump(), timeout=20)
    except requests.RequestException:
        raise HTTPException(503, "계정 서버에 연결하지 못했습니다.") from None
    if not response.ok:
        raise HTTPException(400, "계정 연결에 실패했습니다. 이메일·비밀번호·인증 메일 또는 가입 제한을 확인해 주세요.")
    result = response.json()
    return {"access_token": result.get("access_token"), "expires_in": result.get("expires_in"),
            "confirmation_required": not bool(result.get("access_token"))}


class SchoolRequest(BaseModel):
    school: str = Field(min_length=2, max_length=100)
    major: str = Field(min_length=1, max_length=100)
    campus: str = Field(default="", max_length=50)
    year: int = Field(ge=2000, le=2100)
    nickname: str = Field(default="", max_length=50)
    career: str = Field(default="", max_length=100)


def public_job(row, source="database"):
    return {"id": str(row["id"]), "school": row["school_name"], "campus": row["campus"],
            "year": row["academic_year"], "status": row["status"], "source": source,
            "events": row["candidates"] if row["status"] == "ready" else [], "message": row["message"]}


def run_discovery(job_id):
    # No DB connection is held while Claude searches. The persisted job is shared across workers/users.
    with service_transaction() as conn:
        job = conn.execute("select * from public.academic_calendar_lookups where id=%s", (job_id,)).fetchone()
    try:
        events = discover(job["school_name"], job["campus"], job["academic_year"])
        with service_transaction() as conn:
            conn.execute("update public.academic_calendar_lookups set status='ready', candidates=%s, message=null, updated_at=now() where id=%s and status='pending'",
                         (Jsonb(events), job_id))
    except Exception as exc:
        message = str(exc) if isinstance(exc, DiscoveryError) else "학사일정 처리 중 오류가 발생했습니다. 다시 시도해 주세요."
        with service_transaction() as conn:
            conn.execute("update public.academic_calendar_lookups set status='failed', message=%s, updated_at=now() where id=%s and status='pending'",
                         (message, job_id))


@router.post("/api/academic/lookup")
def lookup(body: SchoolRequest, tasks: BackgroundTasks, user: AuthUser = Depends(current_user)):
    school, campus = body.school.strip(), body.campus.strip()
    if len(school) < 2 or not body.major.strip():
        raise HTTPException(400, "학교와 학과를 입력해 주세요.")
    key = normalize_school(school)
    created = False
    with service_transaction() as conn:
        # Serialize same-school cache misses, including across server processes.
        conn.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (f"{key}:{campus}:{body.year}",))
        row = conn.execute("select * from public.academic_calendar_lookups where school_key=%s and campus=%s and academic_year=%s for update",
                           (key, campus, body.year)).fetchone()
        if row and row["status"] == "pending" and (datetime.now(timezone.utc) - row["updated_at"]).total_seconds() > 1200:
            conn.execute("update public.academic_calendar_lookups set status='failed',message='이전 검색이 중단되었습니다. 다시 조회해 주세요.' where id=%s", (row["id"],))
            row["status"] = "failed"
        if not row or row["status"] in {"failed", "needs_review"}:
            conn.execute("select pg_advisory_xact_lock(hashtextextended(%s,1))", (user.id,))
            recent = conn.execute("select count(*) as n from public.academic_calendar_lookups where requested_by=%s and updated_at>now()-interval '1 minute'", (user.id,)).fetchone()["n"]
            if recent:
                raise HTTPException(429, "새 검색은 1분 후 다시 요청해 주세요.")
            row = conn.execute("""insert into public.academic_calendar_lookups(school_key,school_name,campus,academic_year,requested_by)
                values(%s,%s,%s,%s,%s) on conflict(school_key,campus,academic_year) do update
                set status='pending',message=null,candidates='[]',requested_by=excluded.requested_by,updated_at=now() returning *""",
                (key, school, campus, body.year, user.id)).fetchone()
            created = True
    with user_transaction(user.claims) as conn:
        conn.execute("update public.profiles set school_name=%s,major=%s,display_name=%s,interest_jobs=%s where id=%s", (school,body.major.strip(),body.nickname,[body.career] if body.career else [],user.id))
        conn.execute("update public.user_preferences set academic_year=%s where user_id=%s", (body.year,user.id))
    if created:
        tasks.add_task(run_discovery, str(row["id"]))
    return public_job(row, "ai" if created else "database")


@router.get("/api/academic/lookup/{job_id}")
def get_lookup(job_id: UUID, user: AuthUser = Depends(current_user)):
    with service_transaction() as conn:
        row = conn.execute("select * from public.academic_calendar_lookups where id=%s", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "조회 기록을 찾지 못했습니다.")
    return public_job(row)


class Selection(BaseModel):
    lookup_id: UUID
    indices: list[int] = Field(min_length=1, max_length=100)


@router.post("/api/academic/confirm")
def confirm(body: Selection, user: AuthUser = Depends(current_user)):
    with service_transaction() as conn:
        job = conn.execute("select * from public.academic_calendar_lookups where id=%s and status='ready'", (body.lookup_id,)).fetchone()
        if not job:
            raise HTTPException(409, "완료된 조회 결과를 먼저 확인해 주세요.")
        indices = sorted(set(body.indices))
        if any(i < 0 or i >= len(job["candidates"]) for i in indices):
            raise HTTPException(400, "일정 선택이 올바르지 않습니다.")
        university = conn.execute("""insert into public.universities(name,campus) values(%s,%s)
            on conflict(name,campus) do update set name=excluded.name returning id""",
            (job["school_key"],job["campus"] or None)).fetchone()["id"]
        event_ids = []
        for i in indices:
            e = job["candidates"][i]
            row = conn.execute("""insert into public.academic_events(university_id,academic_year,semester,event_type,title,start_date,end_date,source_url,created_by)
                values(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict(university_id,academic_year,semester,event_type,title,start_date) do update
                set title=excluded.title returning id,title,start_date,end_date,source_url""",
                (university,job["academic_year"],e["semester"],e["event_type"],e["title"],e["start_date"],e["end_date"],e["source_url"],user.id)).fetchone()
            event_ids.append(row)
    # A user's confirmation imports a private snapshot; it does not certify shared AI facts.
    with user_transaction(user.claims) as conn:
        conn.execute("update public.profiles set university_id=%s,school_name=%s where id=%s", (university,job["school_name"],user.id))
        for e in event_ids:
            conn.execute("""insert into public.calendar_events(user_id,title,event_type,start_date,end_date,memo,source_type,academic_event_id)
                values(%s,%s,'school',%s,%s,%s,'academic_event',%s)
                on conflict(user_id,academic_event_id,event_type) do nothing""",
                (user.id,e["title"],e["start_date"],e["end_date"],e["source_url"],e["id"]))
        conn.execute("update public.user_preferences set academic_calendar_sync=true,academic_year=%s where user_id=%s", (job["academic_year"],user.id))
    return {"imported":len(event_ids),"events":calendar(user)["events"]}


@router.get("/api/academic/calendar")
def calendar(user: AuthUser = Depends(current_user)):
    with user_transaction(user.claims) as conn:
        rows = conn.execute("select id,title,start_date,end_date,memo,academic_event_id from public.calendar_events where user_id=%s and source_type='academic_event' order by start_date,id", (user.id,)).fetchall()
    return {"events":rows}


class PersonalAcademicEdit(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    date: date


@router.patch("/api/academic/calendar/{event_id}")
def edit_calendar(event_id: UUID, body: PersonalAcademicEdit, user: AuthUser = Depends(current_user)):
    with user_transaction(user.claims) as conn:
        row = conn.execute("""update public.calendar_events set title=%s,start_date=%s,
            end_date=case when end_date<%s then %s else end_date end
            where id=%s and user_id=%s and source_type='academic_event' returning id""",
            (body.title,body.date,body.date,body.date,event_id,user.id)).fetchone()
    if not row:
        raise HTTPException(404, "일정을 찾지 못했습니다.")
    return {"ok":True}


@router.delete("/api/academic/calendar/{event_id}")
def remove_calendar(event_id: UUID, user: AuthUser = Depends(current_user)):
    with user_transaction(user.claims) as conn:
        result = conn.execute("delete from public.calendar_events where id=%s and user_id=%s and source_type='academic_event'", (event_id,user.id))
    if not result.rowcount:
        raise HTTPException(404, "일정을 찾지 못했습니다.")
    return {"ok":True}
