"""
Settings Routes — User LLM settings, API keys, usage stats.

Endpoints:
GET    /api/settings/llm              — current settings (masked keys)
PUT    /api/settings/llm              — save/update settings
GET    /api/settings/models           — available models list
GET    /api/settings/usage            — usage stats (tokens, requests)
DELETE /api/settings/llm/keys         — apni keys hata do (Markar keys use karo)
"""
import os
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

DEV_USER = "dev-user"


def _get_user_id(authorization: Optional[str]) -> str:
    """Authorization header se user_id nikalo."""
    auth_enabled = os.getenv("MARKAR_AUTH_ENABLED", "false").lower() == "true"
    if not auth_enabled:
        return DEV_USER

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token required")

    from app.core.auth import verify_token
    payload = verify_token(authorization[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload.user_id


# ── Request schemas ───────────────────────────────────────────────────────

class LLMSettingsRequest(BaseModel):
    openai_key:      Optional[str] = None
    anthropic_key:   Optional[str] = None
    openrouter_key:  Optional[str] = None
    gemini_key:      Optional[str] = None
    preferred_model: Optional[str] = None
    router_model:    Optional[str] = None
    use_own_keys:    Optional[bool] = None


# ── Endpoints ─────────────────────────────────────────────────────────────

@settings_router.get("/llm")
async def get_llm_settings(
    authorization: Optional[str] = Header(None)
):
    """
    Current user ki LLM settings return karo.
    API keys masked hoti hain — sirf last 4 chars dikhti hain.
    """
    user_id = _get_user_id(authorization)

    from app.core.llm_settings import get_user_llm_settings, init_llm_settings_db
    init_llm_settings_db()
    settings = get_user_llm_settings(user_id)

    return {"status": "success", "data": settings}


@settings_router.put("/llm")
async def update_llm_settings(
    req: LLMSettingsRequest,
    authorization: Optional[str] = Header(None)
):
    """
    User ki LLM settings save karo.
    Apni API keys dal ke use_own_keys=true karo.
    """
    user_id = _get_user_id(authorization)

    from app.core.llm_settings import save_user_llm_settings, init_llm_settings_db
    init_llm_settings_db()

    updated = save_user_llm_settings(
        user_id=user_id,
        openai_key=req.openai_key,
        anthropic_key=req.anthropic_key,
        openrouter_key=req.openrouter_key,
        gemini_key=req.gemini_key,
        preferred_model=req.preferred_model,
        router_model=req.router_model,
        use_own_keys=req.use_own_keys,
    )

    return {
        "status": "success",
        "message": "Settings saved",
        "data": updated,
    }


@settings_router.delete("/llm/keys")
async def clear_own_keys(
    authorization: Optional[str] = Header(None)
):
    """
    Apni API keys hata do — Markar ki default keys use hongi.
    """
    user_id = _get_user_id(authorization)

    from app.core.llm_settings import save_user_llm_settings
    save_user_llm_settings(
        user_id=user_id,
        openai_key="",
        anthropic_key="",
        openrouter_key="",
        gemini_key="",
        use_own_keys=False,
    )

    return {"status": "success", "message": "Keys cleared — Markar default keys use honge"}


@settings_router.get("/models")
async def get_available_models():
    """
    Available LLM models ki list return karo.
    Free aur paid dono — provider ke saath.
    """
    from app.core.llm_settings import AVAILABLE_MODELS
    return {
        "status": "success",
        "data": {
            "free":  [m for m in AVAILABLE_MODELS if m["free"]],
            "paid":  [m for m in AVAILABLE_MODELS if not m["free"]],
            "all":   AVAILABLE_MODELS,
        }
    }


@settings_router.get("/usage")
async def get_usage_stats(
    days: int = 30,
    authorization: Optional[str] = Header(None)
):
    """
    User ka LLM usage stats return karo.
    Total requests, tokens, per-model breakdown, recent prompts.
    """
    user_id = _get_user_id(authorization)

    from app.core.llm_settings import get_user_usage_stats, init_llm_settings_db
    init_llm_settings_db()
    stats = get_user_usage_stats(user_id, days=days)

    return {"status": "success", "data": stats}


@settings_router.get("/usage/history")
async def get_usage_history(
    limit: int = 50,
    authorization: Optional[str] = Header(None)
):
    """
    Recent LLM calls ki detailed history.
    Har call: model, agent, tokens, latency, timestamp.
    """
    user_id = _get_user_id(authorization)

    from app.core.llm_settings import _get_conn, init_llm_settings_db
    init_llm_settings_db()

    try:
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT model, agent, intent, session_id, repo_id,
                       prompt_tokens, completion_tokens, total_tokens,
                       latency_ms, success, error_msg, created_at
                FROM llm_usage
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit)).fetchall()

        return {
            "status": "success",
            "data": {
                "history": [dict(r) for r in rows],
                "count": len(rows),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))