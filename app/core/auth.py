"""
Phase 3 — Auth & RBAC.
JWT-based authentication + Role-based access control.
Middleware jo har request authenticate karta hai.
"""
import os
import time
import json
import hashlib
import hmac
import sqlite3
import uuid
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


DB_PATH = os.getenv("MARKAR_DB_PATH", "markar.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db():
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id         TEXT PRIMARY KEY,
            email           TEXT UNIQUE,
            full_name       TEXT,
            hashed_password TEXT,
            provider        TEXT,
            provider_id     TEXT,
            avatar_url      TEXT,
            oauth_token     TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_users_email
            ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_provider
            ON users(provider, provider_id);
        """)


class Role(str, Enum):
    ADMIN  = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


ROLE_PERMISSIONS = {
    Role.ADMIN:  ["read", "write", "build", "delete", "admin"],
    Role.EDITOR: ["read", "write", "build"],
    Role.VIEWER: ["read"],
}

# Intent → required permission mapping
INTENT_PERMISSIONS = {
    "ask":    "read",
    "debug":  "read",
    "impact": "read",
    "qa":     "write",
    "build":  "build",
}


@dataclass
class TokenPayload:
    user_id:  str
    repo_id:  str
    role:     Role
    exp:      float


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_token(user_id: str, repo_id: str, role: Role,
                 ttl_hours: int = 24) -> str:
    """
    Simple HMAC token — production mein PyJWT use karo.
    Format: base64(payload).signature
    """
    secret = os.getenv("MARKAR_SECRET", "markar-dev-secret-change-in-prod")
    payload = json.dumps({
        "user_id": user_id,
        "repo_id": repo_id,
        "role":    role.value,
        "exp":     time.time() + ttl_hours * 3600,
    })
    import base64
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = _sign(encoded, secret)
    return f"{encoded}.{sig}"


def verify_token(token: str) -> Optional[TokenPayload]:
    """Token verify karo — None return karo agar invalid."""
    try:
        import base64
        secret = os.getenv("MARKAR_SECRET", "markar-dev-secret-change-in-prod")
        encoded, sig = token.rsplit(".", 1)

        expected_sig = _sign(encoded, secret)
        if not hmac.compare_digest(sig, expected_sig):
            return None

        payload = json.loads(base64.urlsafe_b64decode(encoded).decode())

        if payload["exp"] < time.time():
            return None

        return TokenPayload(
            user_id=payload["user_id"],
            repo_id=payload["repo_id"],
            role=Role(payload["role"]),
            exp=payload["exp"],
        )
    except Exception as e:
        print(f"[Auth] Token verify failed: {e}")
        return None


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or uuid.uuid4().hex
    iterations = 100_000
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        algo, iterations, salt, digest = hashed_password.split("$")
        if algo != "pbkdf2_sha256":
            return False
        new_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(digest, new_digest)
    except Exception:
        return False


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _row_to_user(row: sqlite3.Row) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    if not email:
        return None
    email = _normalize_email(email)
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    return _row_to_user(row)


def get_user_by_provider(provider: str, provider_id: str) -> Optional[Dict[str, Any]]:
    if not provider or not provider_id:
        return None
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE provider = ? AND provider_id = ?",
            (provider, provider_id),
        ).fetchone()
    return _row_to_user(row)


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    if not user_id:
        return None
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return _row_to_user(row)


def create_user(
    email: Optional[str] = None,
    password: Optional[str] = None,
    full_name: Optional[str] = None,
    provider: Optional[str] = None,
    provider_id: Optional[str] = None,
    avatar_url: Optional[str] = None,
    oauth_token: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    user_id = str(uuid.uuid4())[:12]
    email_norm = _normalize_email(email) if email else None
    hashed_password = _hash_password(password) if password else None
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO users (user_id, email, full_name, hashed_password, provider, provider_id, avatar_url, oauth_token, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                email_norm,
                full_name or "",
                hashed_password,
                provider,
                provider_id,
                avatar_url,
                oauth_token,
                now,
                now,
            ),
        )
    return get_user_by_id(user_id)


def update_user_oauth(user_id: str,
                      provider: Optional[str] = None,
                      provider_id: Optional[str] = None,
                      avatar_url: Optional[str] = None,
                      oauth_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not user_id:
        return None
    updates = []
    params = []
    if provider:
        updates.append("provider = ?")
        params.append(provider)
    if provider_id:
        updates.append("provider_id = ?")
        params.append(provider_id)
    if avatar_url is not None:
        updates.append("avatar_url = ?")
        params.append(avatar_url)
    if oauth_token is not None:
        updates.append("oauth_token = ?")
        params.append(oauth_token)
    if not updates:
        return get_user_by_id(user_id)
    params.append(datetime.utcnow().isoformat())
    params.append(user_id)
    with _get_conn() as conn:
        conn.execute(
            f"UPDATE users SET {', '.join(updates)}, updated_at = ? WHERE user_id = ?",
            tuple(params),
        )
    return get_user_by_id(user_id)


def create_or_get_social_user(
    provider: str,
    provider_id: str,
    email: Optional[str],
    full_name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    oauth_token: Optional[str] = None,
) -> Dict[str, Any]:
    user = get_user_by_provider(provider, provider_id)
    if user:
        update_user_oauth(
            user["user_id"],
            provider=provider,
            provider_id=provider_id,
            avatar_url=avatar_url,
            oauth_token=oauth_token,
        )
        return user

    user = get_user_by_email(email) if email else None
    if user:
        update_user_oauth(
            user["user_id"],
            provider=provider,
            provider_id=provider_id,
            avatar_url=avatar_url,
            oauth_token=oauth_token,
        )
        return get_user_by_id(user["user_id"])

    return create_user(
        email=email,
        full_name=full_name,
        provider=provider,
        provider_id=provider_id,
        avatar_url=avatar_url,
        oauth_token=oauth_token,
    )


def check_permission(token_payload: TokenPayload,
                     required_permission: str,
                     repo_id: str) -> bool:
    """RBAC: User ke paas required permission hai?"""
    if token_payload.repo_id != repo_id and token_payload.repo_id != "*":
        return False

    allowed = ROLE_PERMISSIONS.get(token_payload.role, [])
    return required_permission in allowed


def get_intent_permission(intent: str) -> str:
    """Intent ke liye required permission do."""
    return INTENT_PERMISSIONS.get(intent, "read")


# ── FastAPI Dependency ────────────────────────────────────────────────────
async def get_current_user(authorization: str = None) -> Optional[TokenPayload]:
    """
    FastAPI dependency — Header se token nikalo aur verify karo.
    Auth disabled hone pe dev mode mein admin return karo.
    """
    auth_enabled = os.getenv("MARKAR_AUTH_ENABLED", "false").lower() == "true"
    if not auth_enabled:
        return TokenPayload(
            user_id="dev-user",
            repo_id="*",
            role=Role.ADMIN,
            exp=time.time() + 86400,
        )

    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization[7:]
    return verify_token(token)
