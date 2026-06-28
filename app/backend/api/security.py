# -*- coding: utf-8 -*-
"""Password hashing and compact JWT helpers.

The deployed environment should install passlib[bcrypt] from requirements.txt.
For local/offline development this module also provides a PBKDF2 fallback so
auth can be tested without downloading extra packages.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any


try:  # pragma: no cover - exercised only when optional dependency exists.
    import bcrypt as _bcrypt

    if not hasattr(_bcrypt, "__about__"):
        raise RuntimeError("passlib 1.7.x requires bcrypt<5")
    from passlib.context import CryptContext

    _PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
except Exception:  # pragma: no cover - local sandbox currently has no passlib.
    _PWD_CONTEXT = None


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PBKDF2_ITERATIONS = 260_000
JWT_ALG = "HS256"
DEFAULT_TOKEN_MINUTES = 60 * 24 * 14


def validate_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not EMAIL_RE.match(normalized):
        raise ValueError("邮箱格式不正确")
    return normalized


def validate_password(password: str) -> None:
    if len(password or "") < 6:
        raise ValueError("密码至少需要 6 位")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _hash_pbkdf2(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def hash_password(password: str) -> str:
    validate_password(password)
    if _PWD_CONTEXT is not None:
        try:
            return "passlib$" + _PWD_CONTEXT.hash(password)
        except Exception:
            # passlib 1.7.x is not compatible with bcrypt 5.x. Keep local
            # development usable while production pins bcrypt<5.
            return _hash_pbkdf2(password)
    return _hash_pbkdf2(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith("passlib$"):
        if _PWD_CONTEXT is None:
            return False
        try:
            return bool(_PWD_CONTEXT.verify(password, password_hash.removeprefix("passlib$")))
        except Exception:
            return False

    try:
        scheme, iterations, salt, stored_digest = password_hash.split("$", 3)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        _b64url_decode(salt),
        int(iterations),
    )
    return hmac.compare_digest(_b64url_encode(digest), stored_digest)


def _jwt_secret() -> bytes:
    secret = os.getenv("JWT_SECRET", "qingliuxue-local-dev-secret-change-me")
    return secret.encode("utf-8")


def create_access_token(subject: str, expires_minutes: int | None = None, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire_delta = timedelta(minutes=expires_minutes or int(os.getenv("JWT_EXPIRE_MINUTES", DEFAULT_TOKEN_MINUTES)))
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expire_delta).timestamp()),
    }
    if extra:
        payload.update(extra)

    header = {"typ": "JWT", "alg": JWT_ALG}
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
        ]
    )
    signature = hmac.new(_jwt_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("Token 格式不正确") from exc

    signing_input = f"{header_b64}.{payload_b64}"
    expected = _b64url_encode(hmac.new(_jwt_secret(), signing_input.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature_b64):
        raise ValueError("Token 签名无效")

    header = json.loads(_b64url_decode(header_b64))
    if header.get("alg") != JWT_ALG:
        raise ValueError("Token 算法不支持")

    payload = json.loads(_b64url_decode(payload_b64))
    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("Token 已过期")
    if not payload.get("sub"):
        raise ValueError("Token 缺少用户")
    return payload
