"""
Phase 3 — Observability & Audit Logs.
- Har agent call ka structured log
- Performance metrics (latency, token count)
- Error tracking
- Audit trail (kaun ne kya kiya)
"""
import os
import time
import json
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict


DB_PATH = os.getenv("MARKAR_DB_PATH", "markar.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_observability_db():
    """Observability tables banao."""
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type   TEXT NOT NULL,
            user_id      TEXT,
            repo_id      TEXT,
            session_id   TEXT,
            agent        TEXT,
            intent       TEXT,
            action       TEXT,
            status       TEXT,
            latency_ms   REAL,
            token_count  INTEGER,
            error        TEXT,
            metadata     TEXT,
            created_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS metrics (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name  TEXT NOT NULL,
            metric_value REAL NOT NULL,
            tags         TEXT,
            created_at   TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_session
            ON audit_logs(session_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_audit_user
            ON audit_logs(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_metrics_name
            ON metrics(metric_name, created_at);
        """)


@dataclass
class AuditEvent:
    event_type:  str
    user_id:     str  = "unknown"
    repo_id:     str  = ""
    session_id:  str  = ""
    agent:       str  = ""
    intent:      str  = ""
    action:      str  = ""
    status:      str  = "success"
    latency_ms:  float = 0.0
    token_count: int  = 0
    error:       str  = ""
    metadata:    Dict = field(default_factory=dict)


class ObservabilityLogger:
    """
    Phase 3: Structured audit logging + metrics.
    Har agent call, LLM request, aur error track hota hai.
    """

    def __init__(self):
        init_observability_db()

    def log(self, event: AuditEvent):
        """Audit event log karo."""
        now = datetime.utcnow().isoformat()
        try:
            with _get_conn() as conn:
                conn.execute("""
                    INSERT INTO audit_logs
                        (event_type, user_id, repo_id, session_id, agent,
                         intent, action, status, latency_ms, token_count,
                         error, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_type, event.user_id, event.repo_id,
                    event.session_id, event.agent, event.intent,
                    event.action, event.status, event.latency_ms,
                    event.token_count, event.error,
                    json.dumps(event.metadata), now,
                ))
        except Exception as e:
            print(f"[Observability] Log failed: {e}")

    def record_metric(self, name: str, value: float, tags: Dict = None):
        """Metric record karo — latency, error rates, etc."""
        now = datetime.utcnow().isoformat()
        try:
            with _get_conn() as conn:
                conn.execute("""
                    INSERT INTO metrics (metric_name, metric_value, tags, created_at)
                    VALUES (?, ?, ?, ?)
                """, (name, value, json.dumps(tags or {}), now))
        except Exception as e:
            print(f"[Observability] Metric failed: {e}")

    @contextmanager
    def measure(self, event_type: str, **kwargs):
        """
        Context manager — automatically latency measure karo.

        Usage:
            with obs.measure("llm_call", agent="ask", intent="ask") as evt:
                response = call_llm()
                evt.token_count = count_tokens(response)
        """
        start = time.time()
        event = AuditEvent(event_type=event_type, **kwargs)
        try:
            yield event
            event.status = "success"
        except Exception as e:
            event.status = "error"
            event.error  = str(e)[:500]
            raise
        finally:
            event.latency_ms = (time.time() - start) * 1000
            self.log(event)
            self.record_metric(
                f"{event_type}.latency_ms",
                event.latency_ms,
                {"agent": event.agent, "status": event.status}
            )

    def get_session_audit(self, session_id: str) -> List[Dict]:
        """Session ke saare audit events do."""
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM audit_logs
                WHERE session_id = ?
                ORDER BY created_at ASC
            """, (session_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_repo_stats(self, repo_id: str, hours: int = 24) -> Dict:
        """Repo ke liye last N hours ki stats."""
        since = datetime.utcnow().replace(
            hour=datetime.utcnow().hour - min(hours, 23)
        ).isoformat()
        with _get_conn() as conn:
            total = conn.execute("""
                SELECT COUNT(*) as cnt FROM audit_logs
                WHERE repo_id=? AND created_at > ?
            """, (repo_id, since)).fetchone()["cnt"]

            errors = conn.execute("""
                SELECT COUNT(*) as cnt FROM audit_logs
                WHERE repo_id=? AND status='error' AND created_at > ?
            """, (repo_id, since)).fetchone()["cnt"]

            avg_latency = conn.execute("""
                SELECT AVG(latency_ms) as avg FROM audit_logs
                WHERE repo_id=? AND created_at > ?
            """, (repo_id, since)).fetchone()["avg"]

            by_agent = conn.execute("""
                SELECT agent, COUNT(*) as cnt FROM audit_logs
                WHERE repo_id=? AND created_at > ?
                GROUP BY agent ORDER BY cnt DESC
            """, (repo_id, since)).fetchall()

        return {
            "total_requests": total,
            "errors": errors,
            "error_rate": round(errors / total * 100, 1) if total else 0,
            "avg_latency_ms": round(avg_latency or 0, 1),
            "by_agent": [dict(r) for r in by_agent],
        }

    def get_recent_errors(self, repo_id: str, limit: int = 10) -> List[Dict]:
        """Recent errors do — debugging ke liye."""
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT event_type, agent, intent, error, created_at
                FROM audit_logs
                WHERE repo_id=? AND status='error'
                ORDER BY created_at DESC LIMIT ?
            """, (repo_id, limit)).fetchall()
        return [dict(r) for r in rows]


# ── Global instance ───────────────────────────────────────────────────────
_obs = ObservabilityLogger()


def get_obs() -> ObservabilityLogger:
    return _obs
