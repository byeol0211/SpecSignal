"""환경변수 설정. 프로젝트 루트의 .env를 읽는다 (.env는 Git에 올리지 않는다)."""

import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    try:
        return int(value) if value else default
    except ValueError:
        raise ValueError(f"{name}는 정수여야 합니다.") from None


def _float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    try:
        return float(value) if value else default
    except ValueError:
        raise ValueError(f"{name}는 숫자여야 합니다.") from None


@dataclass(frozen=True)
class Settings:
    # 프론트엔드에 노출해도 되는 값
    supabase_url: str
    supabase_publishable_key: str
    # 백엔드 전용 (절대 프론트엔드/Git에 노출 금지)
    database_url: str
    supabase_jwt_secret: str
    # 수집 주기(시간). 정기 실행 시 이 시간보다 오래된 데이터만 다시 수집한다.
    list_refresh_hours: int
    details_refresh_hours: int
    schedule_refresh_hours: int
    # 시험일정 수집 연도: 올해 기준 상대값 (기본 올해·내년)
    schedule_year_offsets: tuple[int, ...]
    # 공공데이터 API 호출 간 대기(초). 제공기관 부하와 트래픽 한도를 고려한다.
    request_interval_seconds: float

    def schedule_years(self, today: date | None = None) -> list[str]:
        base = (today or date.today()).year
        return [str(base + offset) for offset in self.schedule_year_offsets]


@lru_cache
def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env", encoding="utf-8-sig")
    offsets = os.getenv("CERT_SCHEDULE_YEAR_OFFSETS", "0,1")
    try:
        year_offsets = tuple(int(part) for part in offsets.split(",") if part.strip())
    except ValueError:
        raise ValueError("CERT_SCHEDULE_YEAR_OFFSETS는 0,1 형식이어야 합니다.") from None
    return Settings(
        supabase_url=os.getenv("SUPABASE_URL", "").strip().rstrip("/"),
        supabase_publishable_key=os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip(),
        database_url=os.getenv("SUPABASE_DB_URL", "").strip(),
        supabase_jwt_secret=os.getenv("SUPABASE_JWT_SECRET", "").strip(),
        list_refresh_hours=_int("CERT_LIST_REFRESH_HOURS", 24),
        details_refresh_hours=_int("CERT_DETAILS_REFRESH_HOURS", 24),
        schedule_refresh_hours=_int("CERT_SCHEDULE_REFRESH_HOURS", 24),
        schedule_year_offsets=year_offsets,
        request_interval_seconds=_float("PUBLIC_API_REQUEST_INTERVAL_SECONDS", 0.3),
    )
