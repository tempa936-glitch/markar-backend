"""
Conversation Store — Microsoft pattern: External Memory layer.
Har session ki history SQLite mein persist hoti hai.
Agents is history ko context ke saath padhte hain.
"""
import sqlite3
import json
import os
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path


DB_PATH = os.getenv("MARKAR_DB_PATH", "markar.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Tables banao agar exist nahi karte."""
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            session_id   TEXT PRIMARY KEY,
            repo_id      TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   TEXT NOT NULL,
            role         TEXT NOT NULL,
            content      TEXT NOT NULL,
            agent        TEXT,
            intent       TEXT,
            created_at   TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES conversations(session_id)
        );

        CREATE TABLE IF NOT EXISTS semantic_cache (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   TEXT NOT NULL,
            query_hash   TEXT NOT NULL,
            query_text   TEXT NOT NULL,
            response     TEXT NOT NULL,
            agent        TEXT,
            created_at   TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_cache_hash
            ON semantic_cache(session_id, query_hash);
        """)


class ConversationStore:
    """
    Microsoft pattern — External Memory + In-context Memory.

    Har agent is class se history padhta aur likhta hai.
    History LLM ko context ke roop mein jaati hai — agents
    pichle messages yaad rakhte hain.
    """

    def __init__(self):
        init_db()

    def create_session(self, session_id: str, repo_id: str) -> Dict:
        now = datetime.utcnow().isoformat()
        with _get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO conversations
                    (session_id, repo_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """, (session_id, repo_id, now, now))
        return {"session_id": session_id, "repo_id": repo_id}

    def add_message(self, session_id: str, role: str, content: str,
                    agent: str = None, intent: str = None):
        now = datetime.utcnow().isoformat()
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO messages
                    (session_id, role, content, agent, intent, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, role, content, agent, intent, now))
            conn.execute("""
                UPDATE conversations SET updated_at=? WHERE session_id=?
            """, (now, session_id))

    def get_history(self, session_id: str,
                    last_n: int = 10) -> List[Dict]:
        """Last N messages wapas do — LLM context ke liye."""
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT role, content, agent, intent, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (session_id, last_n)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_context_text(self, session_id: str,
                         last_n: int = 6) -> str:
        """
        History ko LLM-friendly text mein convert karo.
        Agents is text ko apne prompt mein add karte hain.
        """
        history = self.get_history(session_id, last_n)
        if not history:
            return ""
        lines = ["=== CONVERSATION HISTORY ==="]
        for msg in history:
            role = msg["role"].upper()
            agent = f" [{msg['agent']}]" if msg.get("agent") else ""
            lines.append(f"{role}{agent}: {msg['content'][:300]}")
        lines.append("=== END HISTORY ===")
        return "\n".join(lines)

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        with _get_conn() as conn:
            row = conn.execute("""
                SELECT * FROM conversations WHERE session_id=?
            """, (session_id,)).fetchone()
        return dict(row) if row else None

    def list_sessions(self, repo_id: str) -> List[Dict]:
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT c.session_id, c.repo_id, c.created_at, c.updated_at,
                       COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON c.session_id = m.session_id
                WHERE c.repo_id = ?
                GROUP BY c.session_id
                ORDER BY c.updated_at DESC
            """, (repo_id,)).fetchall()
        return [dict(r) for r in rows]

    # ── Episodic / Semantic Cache ─────────────────────────────────────
    def cache_response(self, session_id: str, query: str,
                       response: str, agent: str = None):
        """Episodic cache — similar queries ka response store karo."""
        import hashlib
        q_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()
        now = datetime.utcnow().isoformat()
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO semantic_cache
                    (session_id, query_hash, query_text, response, agent, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, q_hash, query, response, agent, now))

    def get_cached(self, session_id: str, query: str) -> Optional[str]:
        """Cache check karo — hit hone pe response do."""
        import hashlib
        q_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()
        with _get_conn() as conn:
            row = conn.execute("""
                SELECT response FROM semantic_cache
                WHERE session_id=? AND query_hash=?
                ORDER BY created_at DESC LIMIT 1
            """, (session_id, q_hash)).fetchone()
        return row["response"] if row else None
