"""Supabase Auth 액세스 토큰 검증.

- 비대칭 서명키(ES256/RS256): 프로젝트의 공개 JWKS로 검증 (권장, 비밀값 불필요)
- 레거시 HS256: SUPABASE_JWT_SECRET이 설정된 경우에만 허용
검증된 claims는 user_transaction()에 전달되어 DB의 RLS 정책이 적용된다.
"""

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException

from src.config import get_settings


ASYMMETRIC_ALGORITHMS = {"ES256", "RS256", "EdDSA"}


@dataclass(frozen=True)
class AuthUser:
    id: str
    claims: dict


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=600)


def verify_access_token(token: str) -> dict:
    settings = get_settings()
    if not settings.supabase_url:
        raise ValueError("SUPABASE_URL이 설정되지 않았습니다.")
    try:
        algorithm = jwt.get_unverified_header(token).get("alg")
    except jwt.InvalidTokenError:
        raise ValueError("토큰 형식이 올바르지 않습니다.") from None
    if algorithm in ASYMMETRIC_ALGORITHMS:
        try:
            key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token).key
        except jwt.PyJWKClientError:
            raise ValueError("토큰 서명키를 확인할 수 없습니다.") from None
    elif algorithm == "HS256" and settings.supabase_jwt_secret:
        key = settings.supabase_jwt_secret
    else:
        raise ValueError("지원하지 않는 토큰 서명 방식입니다.")
    try:
        claims = jwt.decode(
            token, key, algorithms=[algorithm], audience="authenticated",
            issuer=f"{settings.supabase_url}/auth/v1",
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"토큰 검증 실패: {type(exc).__name__}") from None
    if claims.get("role") != "authenticated":
        raise ValueError("로그인 사용자 토큰이 아닙니다.")
    return claims


def current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    """FastAPI 의존성. Authorization: Bearer <Supabase access token>."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "로그인이 필요합니다.", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = verify_access_token(token.strip())
    except ValueError as exc:
        raise HTTPException(401, str(exc), headers={"WWW-Authenticate": "Bearer"}) from None
    return AuthUser(id=claims["sub"], claims=claims)
