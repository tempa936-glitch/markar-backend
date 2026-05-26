"""
LLM Settings — Per-user API keys aur usage tracking.
"""
import os
import sqlite3
from typing import Optional, Dict, List
from datetime import datetime

DB_PATH = os.getenv("MARKAR_DB_PATH", "markar.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_llm_settings_db():
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_llm_settings (
            user_id          TEXT PRIMARY KEY,
            openai_key       TEXT,
            anthropic_key    TEXT,
            openrouter_key   TEXT,
            gemini_key       TEXT,
            preferred_model  TEXT DEFAULT 'meta-llama/llama-3.3-70b-instruct:free',
            router_model     TEXT DEFAULT 'mistralai/mistral-7b-instruct:free',
            use_own_keys     INTEGER DEFAULT 0,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );

        """)
        try:
            conn.execute("ALTER TABLE user_llm_settings ADD COLUMN gemini_key TEXT;")
        except Exception:
            pass
        
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS llm_usage (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           TEXT NOT NULL,
            session_id        TEXT,
            repo_id           TEXT,
            model             TEXT NOT NULL,
            prompt_tokens     INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens      INTEGER DEFAULT 0,
            agent             TEXT,
            intent            TEXT,
            latency_ms        INTEGER DEFAULT 0,
            success           INTEGER DEFAULT 1,
            error_msg         TEXT,
            created_at        TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_llm_usage_user
            ON llm_usage(user_id, created_at);
        """)


def _mask_key(key: str) -> Optional[str]:
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return f"{'*' * (len(key) - 4)}{key[-4:]}"


def get_user_llm_settings(user_id: str) -> Dict:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_llm_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        
    if not row:
        return {
            "user_id": user_id,
            "openai_key": None, "anthropic_key": None, "openrouter_key": None, "gemini_key": None,
            "preferred_model": "meta-llama/llama-3.3-70b-instruct:free",
            "router_model": "mistralai/mistral-7b-instruct:free",
            "use_own_keys": False,
        }
        
    row_dict = dict(row)
    return {
        "user_id": row["user_id"],
        "openai_key": _mask_key(row["openai_key"]),
        "anthropic_key": _mask_key(row["anthropic_key"]),
        "openrouter_key": _mask_key(row["openrouter_key"]),
        "gemini_key": _mask_key(row_dict.get("gemini_key")),
        "preferred_model": row["preferred_model"],
        "router_model": row["router_model"],
        "use_own_keys": bool(row["use_own_keys"]),
    }


def get_user_llm_keys(user_id: str) -> Dict:
    """Actual unmasked keys — sirf LLM calls ke liye."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_llm_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        
    if not row:
        return {
            "openai_key": os.getenv("OPENAI_API_KEY", ""),
            "anthropic_key": os.getenv("ANTHROPIC_API_KEY", ""),
            "openrouter_key": os.getenv("OPENROUTER_API_KEY", ""),
            "gemini_key": os.getenv("GEMINI_API_KEY", ""),
            "preferred_model": os.getenv("MARKAR_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
            "router_model": os.getenv("MARKAR_ROUTER_MODEL", "mistralai/mistral-7b-instruct:free"),
            "use_own_keys": False,
        }
        
    row_dict = dict(row)
    use_own = bool(row["use_own_keys"])
    return {
        "openai_key": row["openai_key"] if use_own else os.getenv("OPENAI_API_KEY", ""),
        "anthropic_key": row["anthropic_key"] if use_own else os.getenv("ANTHROPIC_API_KEY", ""),
        "openrouter_key": row["openrouter_key"] if use_own else os.getenv("OPENROUTER_API_KEY", ""),
        "gemini_key": row_dict.get("gemini_key") if use_own else os.getenv("GEMINI_API_KEY", ""),
        "preferred_model": row["preferred_model"],
        "router_model": row["router_model"],
        "use_own_keys": use_own,
    }


def save_user_llm_settings(user_id: str, openai_key=None, anthropic_key=None,
                            openrouter_key=None, gemini_key=None, preferred_model=None,
                            router_model=None, use_own_keys=None) -> Dict:
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        existing = conn.execute(
            "SELECT user_id FROM user_llm_settings WHERE user_id=?", (user_id,)
        ).fetchone()
        if existing:
            updates, params = [], []
            for col, val in [
                ("openai_key", openai_key), ("anthropic_key", anthropic_key),
                ("openrouter_key", openrouter_key), ("gemini_key", gemini_key), ("preferred_model", preferred_model),
                ("router_model", router_model),
            ]:
                if val is not None:
                    updates.append(f"{col} = ?")
                    params.append(val or None)
            if use_own_keys is not None:
                updates.append("use_own_keys = ?")
                params.append(1 if use_own_keys else 0)
            if updates:
                updates.append("updated_at = ?")
                params.extend([now, user_id])
                conn.execute(
                    f"UPDATE user_llm_settings SET {', '.join(updates)} WHERE user_id=?",
                    tuple(params)
                )
        else:
            conn.execute("""
                INSERT INTO user_llm_settings
                    (user_id, openai_key, anthropic_key, openrouter_key, gemini_key,
                     preferred_model, router_model, use_own_keys, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                user_id,
                openai_key or None, anthropic_key or None, openrouter_key or None, gemini_key or None,
                preferred_model or "meta-llama/llama-3.3-70b-instruct:free",
                router_model or "mistralai/mistral-7b-instruct:free",
                1 if use_own_keys else 0, now, now,
            ))
    return get_user_llm_settings(user_id)


def track_usage(user_id: str, model: str, prompt_tokens: int = 0,
                completion_tokens: int = 0, session_id: str = None,
                repo_id: str = None, agent: str = None, intent: str = None,
                latency_ms: int = 0, success: bool = True, error_msg: str = None):
    now = datetime.utcnow().isoformat()
    try:
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO llm_usage
                    (user_id, session_id, repo_id, model,
                     prompt_tokens, completion_tokens, total_tokens,
                     agent, intent, latency_ms, success, error_msg, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                user_id, session_id, repo_id, model,
                prompt_tokens, completion_tokens,
                prompt_tokens + completion_tokens,
                agent, intent, latency_ms,
                1 if success else 0, error_msg, now,
            ))
    except Exception as e:
        print(f"[LLMSettings] track_usage failed: {e}")


def get_user_usage_stats(user_id: str, days: int = 30) -> Dict:
    try:
        with _get_conn() as conn:
            totals = conn.execute("""
                SELECT COUNT(*) AS total_requests,
                       SUM(total_tokens) AS total_tokens,
                       SUM(prompt_tokens) AS prompt_tokens,
                       SUM(completion_tokens) AS completion_tokens,
                       AVG(latency_ms) AS avg_latency_ms,
                       SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS successful,
                       SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failed
                FROM llm_usage
                WHERE user_id=? AND created_at >= datetime('now',?)
            """, (user_id, f"-{days} days")).fetchone()

            by_model = conn.execute("""
                SELECT model, COUNT(*) AS requests,
                       SUM(total_tokens) AS tokens,
                       AVG(latency_ms) AS avg_latency
                FROM llm_usage
                WHERE user_id=? AND created_at >= datetime('now',?)
                GROUP BY model ORDER BY requests DESC
            """, (user_id, f"-{days} days")).fetchall()

            by_agent = conn.execute("""
                SELECT agent, COUNT(*) AS requests, SUM(total_tokens) AS tokens
                FROM llm_usage
                WHERE user_id=? AND created_at >= datetime('now',?)
                  AND agent IS NOT NULL
                GROUP BY agent ORDER BY requests DESC
            """, (user_id, f"-{days} days")).fetchall()

            recent = conn.execute("""
                SELECT model, agent, intent, total_tokens,
                       latency_ms, success, created_at
                FROM llm_usage WHERE user_id=?
                ORDER BY created_at DESC LIMIT 20
            """, (user_id,)).fetchall()

        return {
            "period_days": days,
            "total_requests": totals["total_requests"] or 0,
            "total_tokens": totals["total_tokens"] or 0,
            "prompt_tokens": totals["prompt_tokens"] or 0,
            "completion_tokens": totals["completion_tokens"] or 0,
            "avg_latency_ms": round(totals["avg_latency_ms"] or 0, 1),
            "successful": totals["successful"] or 0,
            "failed": totals["failed"] or 0,
            "by_model": [dict(r) for r in by_model],
            "by_agent": [dict(r) for r in by_agent],
            "recent_requests": [dict(r) for r in recent],
        }
    except Exception as e:
        return {"error": str(e)}


AVAILABLE_MODELS = [
    {"id": "google/gemini-1.5-flash",                "name": "Gemini 1.5 Flash",      "provider": "Google",    "free": False},
    {"id": "google/gemini-1.5-pro",                  "name": "Gemini 1.5 Pro",        "provider": "Google",    "free": False},
    {"id": "meta-llama/llama-3.3-70b-instruct:free", "name": "Llama 3.3 70B",        "provider": "Meta",      "free": True},
    {"id": "deepseek/deepseek-r1:free",              "name": "DeepSeek R1",           "provider": "DeepSeek",  "free": True},
    {"id": "mistralai/mistral-small-3.1-24b-instruct:free", "name": "Mistral Small", "provider": "Mistral",   "free": True},
    {"id": "google/gemini-2.0-flash-lite-preview-02-05:free","name": "Gemini 2.0 Flash Lite","provider":"Google","free": True},
    {"id": "qwen/qwen3-8b:free",                     "name": "Qwen3 8B",              "provider": "Alibaba",   "free": True},
    {"id": "openai/gpt-4o",                          "name": "GPT-4o",                "provider": "OpenAI",    "free": False},
    {"id": "openai/gpt-4o-mini",                     "name": "GPT-4o Mini",           "provider": "OpenAI",    "free": False},
    {"id": "anthropic/claude-3-5-haiku",             "name": "Claude 3.5 Haiku",      "provider": "Anthropic", "free": False},
    {"id": "anthropic/claude-3-5-sonnet",            "name": "Claude 3.5 Sonnet",     "provider": "Anthropic", "free": False},
    {"id": "deepseek/deepseek-chat-v3-0324",         "name": "DeepSeek V3",           "provider": "DeepSeek",  "free": False},
    {"id": "mistralai/mistral-large",                "name": "Mistral Large",         "provider": "Mistral",   "free": False},
]