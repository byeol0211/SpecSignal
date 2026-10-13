"""Supabase PostgreSQL 연결.

- service_transaction: 백엔드 권한(postgres 역할). RLS를 우회하므로 공식 데이터 수집·서버 내부 조회에만 사용한다.
- user_transaction: 검증된 사용자 JWT claims를 트랜잭션에 설정하고 authenticated 역할로 전환하여
  Supabase RLS 정책(auth.uid())이 그대로 적용되게 한다. 사용자 개인 데이터는 반드시 이 경로로 접근한다.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from src.config import get_settings


_pool: ConnectionPool | None = None
_pool_lock = Lock()


class DatabaseNotConfigured(RuntimeError):
    pass


def _conninfo() -> str:
    url = get_settings().database_url
    if not url:
        raise DatabaseNotConfigured(".env에 SUPABASE_DB_URL을 설정하세요.")
    return url


# Supabase 트랜잭션 풀러(6543)는 prepared statement를 지원하지 않으므로 비활성화한다.
_CONNECT_KWARGS = {"row_factory": dict_row, "prepare_threshold": None, "connect_timeout": 10}


def connect() -> psycopg.Connection:
    """CLI 수집 작업용 단일 연결."""
    return psycopg.connect(_conninfo(), **_CONNECT_KWARGS)


def get_pool() -> ConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(_conninfo(), kwargs=_CONNECT_KWARGS, min_size=1,
                                   max_size=5, timeout=10, open=True)
        return _pool


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def service_transaction() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as conn, conn.transaction():
        yield conn


@contextmanager
def user_transaction(claims: dict) -> Iterator[psycopg.Connection]:
    """트랜잭션 범위(SET LOCAL)로만 역할과 claims를 바꾸므로 풀 연결에 남지 않는다."""
    with get_pool().connection() as conn, conn.transaction():
        conn.execute(
            "select set_config('request.jwt.claims', %s, true), "
            "set_config('request.jwt.claim.sub', %s, true)",
            (json.dumps(claims), str(claims["sub"])),
        )
        conn.execute("set local role authenticated")
        yield conn
