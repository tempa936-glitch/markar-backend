"""
User Admin Layer — Credits, Permissions, Repo Limits.
Admin dashboard se users ko control karne ke liye.

Tables:
  user_limits   — per-user repo count limit, storage MB limit, plan
  user_credits  — credit balance + unlimited flag
  credit_log    — har credit transaction ka record
"""
import sqlite3
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

DB_PATH = os.getenv("MARKAR_DB_PATH", "markar.db")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


# ── DB Init ───────────────────────────────────────────────────────────────

def init_user_admin_db():
    """Startup pe call karo — tables create karo agar nahi hain."""
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_limits (
            user_id         TEXT PRIMARY KEY,
            plan            TEXT    NOT NULL DEFAULT 'free',
            max_repos       INTEGER NOT NULL DEFAULT 3,
            max_repo_size_mb INTEGER NOT NULL DEFAULT 100,
            max_messages_day INTEGER NOT NULL DEFAULT 50,
            is_active       INTEGER NOT NULL DEFAULT 1,
            notes           TEXT    DEFAULT '',
            updated_by      TEXT    DEFAULT 'system',
            updated_at      TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_credits (
            user_id         TEXT PRIMARY KEY,
            credits         INTEGER NOT NULL DEFAULT 0,
            unlimited       INTEGER NOT NULL DEFAULT 0,
            total_used      INTEGER NOT NULL DEFAULT 0,
            updated_at      TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS credit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT    NOT NULL,
            delta       INTEGER NOT NULL,
            reason      TEXT    NOT NULL DEFAULT '',
            admin_id    TEXT    DEFAULT 'system',
            balance_after INTEGER NOT NULL,
            created_at  TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_credit_log_user
            ON credit_log(user_id);
        """)


# ── Defaults ──────────────────────────────────────────────────────────────

PLAN_DEFAULTS = {
    "free":       {"max_repos": 3,  "max_repo_size_mb": 100,  "max_messages_day": 50},
    "pro":        {"max_repos": 20, "max_repo_size_mb": 500,  "max_messages_day": 500},
    "enterprise": {"max_repos": 999,"max_repo_size_mb": 5000, "max_messages_day": 9999},
}


def _now() -> str:
    return datetime.utcnow().isoformat()


# ── User Limits ───────────────────────────────────────────────────────────

def get_user_limits(user_id: str) -> Dict[str, Any]:
    """User ke limits return karo. Agar record nahi hai toh free defaults do."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_limits WHERE user_id = ?", (user_id,)
        ).fetchone()

    if row:
        return dict(row)

    # Free plan defaults — row nahi hai toh
    return {
        "user_id":          user_id,
        "plan":             "free",
        "max_repos":        3,
        "max_repo_size_mb": 100,
        "max_messages_day": 50,
        "is_active":        1,
        "notes":            "",
        "updated_by":       "system",
        "updated_at":       _now(),
    }


def set_user_limits(
    user_id: str,
    plan: Optional[str] = None,
    max_repos: Optional[int] = None,
    max_repo_size_mb: Optional[int] = None,
    max_messages_day: Optional[int] = None,
    is_active: Optional[int] = None,
    notes: Optional[str] = None,
    updated_by: str = "admin",
) -> Dict[str, Any]:
    """
    User ke limits update/set karo.
    Plan change karne pe PLAN_DEFAULTS se values auto-fill ho jaati hain
    jab tak manually override nahi karo.
    """
    current = get_user_limits(user_id)

    # Plan change → defaults apply karo
    if plan and plan != current["plan"]:
        defaults = PLAN_DEFAULTS.get(plan, PLAN_DEFAULTS["free"])
        current.update(defaults)
        current["plan"] = plan

    if max_repos is not None:
        current["max_repos"] = max_repos
    if max_repo_size_mb is not None:
        current["max_repo_size_mb"] = max_repo_size_mb
    if max_messages_day is not None:
        current["max_messages_day"] = max_messages_day
    if is_active is not None:
        current["is_active"] = is_active
    if notes is not None:
        current["notes"] = notes

    current["updated_by"] = updated_by
    current["updated_at"] = _now()

    with _conn() as conn:
        conn.execute("""
            INSERT INTO user_limits
                (user_id, plan, max_repos, max_repo_size_mb,
                 max_messages_day, is_active, notes, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                plan             = excluded.plan,
                max_repos        = excluded.max_repos,
                max_repo_size_mb = excluded.max_repo_size_mb,
                max_messages_day = excluded.max_messages_day,
                is_active        = excluded.is_active,
                notes            = excluded.notes,
                updated_by       = excluded.updated_by,
                updated_at       = excluded.updated_at
        """, (
            user_id,
            current["plan"],
            current["max_repos"],
            current["max_repo_size_mb"],
            current["max_messages_day"],
            current["is_active"],
            current["notes"],
            current["updated_by"],
            current["updated_at"],
        ))

    return get_user_limits(user_id)


# ── User Credits ──────────────────────────────────────────────────────────

def get_user_credits(user_id: str) -> Dict[str, Any]:
    """User ka credit balance return karo."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_credits WHERE user_id = ?", (user_id,)
        ).fetchone()

    if row:
        return dict(row)

    return {
        "user_id":    user_id,
        "credits":    0,
        "unlimited":  0,
        "total_used": 0,
        "updated_at": _now(),
    }


def add_credits(
    user_id: str,
    amount: int,
    reason: str = "admin_grant",
    admin_id: str = "admin",
) -> Dict[str, Any]:
    """User ko credits add karo (positive amount = add, negative = deduct)."""
    if amount == 0:
        return get_user_credits(user_id)

    current = get_user_credits(user_id)
    new_balance = max(0, current["credits"] + amount)
    now = _now()

    with _conn() as conn:
        conn.execute("""
            INSERT INTO user_credits (user_id, credits, unlimited, total_used, updated_at)
            VALUES (?, ?, 0, 0, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                credits    = MAX(0, credits + ?),
                updated_at = excluded.updated_at
        """, (user_id, new_balance, now, amount))

        conn.execute("""
            INSERT INTO credit_log (user_id, delta, reason, admin_id, balance_after, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, amount, reason, admin_id, new_balance, now))

    return get_user_credits(user_id)


def set_unlimited(
    user_id: str,
    unlimited: bool,
    admin_id: str = "admin",
) -> Dict[str, Any]:
    """User ko unlimited access do ya hato."""
    now = _now()
    with _conn() as conn:
        conn.execute("""
            INSERT INTO user_credits (user_id, credits, unlimited, total_used, updated_at)
            VALUES (?, 0, ?, 0, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                unlimited  = excluded.unlimited,
                updated_at = excluded.updated_at
        """, (user_id, 1 if unlimited else 0, now))

        reason = "unlimited_granted" if unlimited else "unlimited_revoked"
        conn.execute("""
            INSERT INTO credit_log (user_id, delta, reason, admin_id, balance_after, created_at)
            VALUES (?, 0, ?, ?, ?, ?)
        """, (user_id, reason, admin_id,
              get_user_credits(user_id)["credits"], now))

    return get_user_credits(user_id)


def deduct_credit(user_id: str, reason: str = "chat_message") -> bool:
    """
    Ek credit use karo.
    Returns True agar allowed (unlimited OR credits > 0), False agar nahi.
    """
    current = get_user_credits(user_id)

    if current["unlimited"]:
        # Unlimited user — track usage but allow
        with _conn() as conn:
            conn.execute("""
                UPDATE user_credits
                SET total_used = total_used + 1, updated_at = ?
                WHERE user_id = ?
            """, (_now(), user_id))
        return True

    if current["credits"] <= 0:
        return False

    now = _now()
    new_balance = current["credits"] - 1
    with _conn() as conn:
        conn.execute("""
            UPDATE user_credits
            SET credits = credits - 1, total_used = total_used + 1, updated_at = ?
            WHERE user_id = ? AND credits > 0
        """, (now, user_id))

        conn.execute("""
            INSERT INTO credit_log (user_id, delta, reason, admin_id, balance_after, created_at)
            VALUES (?, -1, ?, 'system', ?, ?)
        """, (user_id, reason, new_balance, now))

    return True


def has_credits(user_id: str) -> bool:
    """Quick check — user ke paas credits hain ya unlimited hai?"""
    c = get_user_credits(user_id)
    return bool(c["unlimited"]) or c["credits"] > 0


def get_credit_log(user_id: str, limit: int = 20) -> List[Dict]:
    """User ke credit transactions ka history."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT * FROM credit_log
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


# ── All Users (admin listing) ─────────────────────────────────────────────

def list_all_users(limit: int = 100, offset: int = 0) -> List[Dict]:
    """
    Admin ke liye — saare users + unke limits + credits ek saath.
    """
    with _conn() as conn:
        rows = conn.execute("""
            SELECT
                u.user_id,
                u.email,
                u.full_name,
                u.provider,
                u.avatar_url,
                u.created_at,
                COALESCE(ul.plan,             'free') AS plan,
                COALESCE(ul.max_repos,        3)      AS max_repos,
                COALESCE(ul.max_repo_size_mb, 100)    AS max_repo_size_mb,
                COALESCE(ul.max_messages_day, 50)     AS max_messages_day,
                COALESCE(ul.is_active,        1)      AS is_active,
                COALESCE(uc.credits,          0)      AS credits,
                COALESCE(uc.unlimited,        0)      AS unlimited,
                COALESCE(uc.total_used,       0)      AS total_used,
                (
                    SELECT COUNT(*) FROM user_repos ur WHERE ur.user_id = u.user_id
                ) AS repo_count
            FROM users u
            LEFT JOIN user_limits  ul ON ul.user_id = u.user_id
            LEFT JOIN user_credits uc ON uc.user_id = u.user_id
            ORDER BY u.created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()

    return [dict(r) for r in rows]


def get_user_detail(user_id: str) -> Optional[Dict]:
    """Single user ki poori detail — limits + credits + repos."""
    with _conn() as conn:
        user_row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

    if not user_row:
        return None

    result = dict(user_row)
    result.pop("hashed_password", None)  # password expose mat karo
    result["limits"]  = get_user_limits(user_id)
    result["credits"] = get_user_credits(user_id)

    with _conn() as conn:
        repos = conn.execute("""
            SELECT repo_id, repo_name, status, git_url, created_at, last_used
            FROM user_repos WHERE user_id = ?
            ORDER BY last_used DESC
        """, (user_id,)).fetchall()
    result["repos"] = [dict(r) for r in repos]

    return result


def check_repo_limit(user_id: str) -> Dict[str, Any]:
    """
    User aur repo add kar sakta hai?
    Returns { allowed: bool, current: int, max: int }
    """
    limits = get_user_limits(user_id)
    with _conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM user_repos WHERE user_id = ?",
            (user_id,)
        ).fetchone()["cnt"]

    allowed = count < limits["max_repos"]
    return {
        "allowed":  allowed,
        "current":  count,
        "max":      limits["max_repos"],
        "plan":     limits["plan"],
    }
