"""Password hashing (Argon2 via pwdlib) and access tokens (JWT HS256 via PyJWT)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from mira_core.config import Settings
from mira_core.models import Role

ALGORITHM = "HS256"
CLOCK_SKEW = timedelta(seconds=10)  # tolerated difference for iat / exp checks
TOKEN_TYPE = "access"  # noqa: S105 — a JWT "type" claim value, not a password

_password_hash = PasswordHash.recommended()  # Argon2id
# Verified against when the user does not exist, so a failed login takes the same time
# whether or not the e-mail is known (no user enumeration by timing).
_DUMMY_HASH = _password_hash.hash("mira-dummy-password-for-timing")

# Refuse keys shorter than RFC 7518 allows instead of only warning.
_jwt = jwt.PyJWT(options={"enforce_minimum_key_length": True})


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, password_hash)


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    tenant_id: uuid.UUID | None
    role: Role


def create_access_token(claims: TokenClaims, settings: Settings) -> tuple[str, int]:
    """Return (token, lifetime in seconds)."""
    now = datetime.now(UTC)
    lifetime = timedelta(minutes=settings.jwt_access_minutes)
    payload = {
        "sub": str(claims.user_id),
        "tid": str(claims.tenant_id) if claims.tenant_id else None,
        "role": claims.role.value,
        "type": TOKEN_TYPE,
        "iat": now,
        "exp": now + lifetime,
        "jti": uuid.uuid4().hex,
    }
    token = _jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str, settings: Settings) -> TokenClaims:
    """Raise jwt.InvalidTokenError (or ValueError) for anything that is not a valid access token."""
    payload = _jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[ALGORITHM],
        options={"require": ["exp", "iat", "sub", "type"]},
        # PyJWT rejects a token whose "iat" is in the future. Server clocks get stepped by NTP
        # (and WSL/VM clocks jump), which turned freshly issued tokens into 401s in testing.
        leeway=CLOCK_SKEW,
    )
    if payload.get("type") != TOKEN_TYPE:
        raise jwt.InvalidTokenError("not an access token")
    tid = payload.get("tid")
    return TokenClaims(
        user_id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(tid) if tid else None,
        role=Role(payload["role"]),
    )
