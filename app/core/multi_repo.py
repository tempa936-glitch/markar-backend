"""
Phase 3 — Multi-Repo Manager.
Ek user ke multiple repos manage karo.
Cross-repo queries support.
"""
import os
import json
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime


DB_PATH = os.getenv("MARKAR_DB_PATH", "markar.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_repo_db():
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS repos (
            repo_id      TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            owner_id     TEXT NOT NULL,
            description  TEXT,
            graph_path   TEXT,
            status       TEXT DEFAULT 'active',
            node_count   INTEGER DEFAULT 0,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS repo_members (
            repo_id   TEXT NOT NULL,
            user_id   TEXT NOT NULL,
            role      TEXT NOT NULL DEFAULT 'viewer',
            added_at  TEXT NOT NULL,
            PRIMARY KEY (repo_id, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_repo_owner
            ON repos(owner_id);
        CREATE INDEX IF NOT EXISTS idx_repo_members_user
            ON repo_members(user_id);
        """)


class MultiRepoManager:
    """
    Phase 3: Multi-repo support.
    Ek user ke multiple repos, members, cross-repo queries.
    """

    def __init__(self):
        init_repo_db()

    def register_repo(self, repo_id: str, name: str,
                      owner_id: str, description: str = "",
                      graph_path: str = "") -> Dict:
        """Naya repo register karo."""
        now = datetime.utcnow().isoformat()
        with _get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO repos
                    (repo_id, name, owner_id, description, graph_path,
                     status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
            """, (repo_id, name, owner_id, description, graph_path, now, now))
            # Owner ko admin banao automatically
            conn.execute("""
                INSERT OR IGNORE INTO repo_members
                    (repo_id, user_id, role, added_at)
                VALUES (?, ?, 'admin', ?)
            """, (repo_id, owner_id, now))
        return self.get_repo(repo_id)

    def get_repo(self, repo_id: str) -> Optional[Dict]:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM repos WHERE repo_id=?", (repo_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_user_repos(self, user_id: str) -> List[Dict]:
        """User ke saare repos — owner aur member dono."""
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT r.*, rm.role as user_role
                FROM repos r
                JOIN repo_members rm ON r.repo_id = rm.repo_id
                WHERE rm.user_id = ? AND r.status = 'active'
                ORDER BY r.updated_at DESC
            """, (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def add_member(self, repo_id: str, user_id: str, role: str = "viewer") -> Dict:
        """Repo mein member add karo."""
        now = datetime.utcnow().isoformat()
        with _get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO repo_members
                    (repo_id, user_id, role, added_at)
                VALUES (?, ?, ?, ?)
            """, (repo_id, user_id, role, now))
        return {"repo_id": repo_id, "user_id": user_id, "role": role}

    def get_user_role(self, repo_id: str, user_id: str) -> Optional[str]:
        """User ka role is repo mein kya hai?"""
        with _get_conn() as conn:
            row = conn.execute("""
                SELECT role FROM repo_members
                WHERE repo_id=? AND user_id=?
            """, (repo_id, user_id)).fetchone()
        return row["role"] if row else None

    def update_node_count(self, repo_id: str, count: int):
        """Graph index ke baad node count update karo."""
        now = datetime.utcnow().isoformat()
        with _get_conn() as conn:
            conn.execute("""
                UPDATE repos SET node_count=?, updated_at=?
                WHERE repo_id=?
            """, (count, now, repo_id))

    def get_members(self, repo_id: str) -> List[Dict]:
        """Repo ke saare members."""
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT user_id, role, added_at FROM repo_members
                WHERE repo_id=? ORDER BY added_at ASC
            """, (repo_id,)).fetchall()
        return [dict(r) for r in rows]

    def cross_repo_summary(self, user_id: str) -> Dict:
        """
        Phase 3: Cross-repo overview.
        User ke saare repos ki summary — total nodes, recent activity.
        """
        repos = self.list_user_repos(user_id)
        total_nodes = sum(r.get("node_count", 0) for r in repos)
        return {
            "repo_count":  len(repos),
            "total_nodes": total_nodes,
            "repos":       repos[:10],
        }


# ── Global instance ───────────────────────────────────────────────────────
_repo_manager = MultiRepoManager()


def get_repo_manager() -> MultiRepoManager:
    return _repo_manager
