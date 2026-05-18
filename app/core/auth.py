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
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum


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

        # Signature verify
        expected_sig = _sign(encoded, secret)
        if not hmac.compare_digest(sig, expected_sig):
            return None

        payload = json.loads(base64.urlsafe_b64decode(encoded).decode())

        # Expiry check
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


def check_permission(token_payload: TokenPayload,
                     required_permission: str,
                     repo_id: str) -> bool:
    """RBAC: User ke paas required permission hai?"""
    # Repo match karo
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
        # Dev mode — auth skip
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
