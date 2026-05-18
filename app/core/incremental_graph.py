"""
Phase 4 — Incremental Graph Updater.
Poora repo re-index karne ki bajaye sirf changed files update karo.
Git diff se changed files detect karo, sirf unhe re-parse karo.
"""
import os
import json
import hashlib
import sqlite3
from typing import List, Dict, Set, Optional
from datetime import datetime
from pathlib import Path


DB_PATH = os.getenv("MARKAR_DB_PATH", "markar.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_incremental_db():
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS file_snapshots (
            repo_id    TEXT NOT NULL,
            file_path  TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            indexed_at TEXT NOT NULL,
            node_count INTEGER DEFAULT 0,
            PRIMARY KEY (repo_id, file_path)
        );

        CREATE TABLE IF NOT EXISTS graph_changelog (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id    TEXT NOT NULL,
            file_path  TEXT NOT NULL,
            change_type TEXT NOT NULL,
            nodes_added INTEGER DEFAULT 0,
            nodes_removed INTEGER DEFAULT 0,
            indexed_at TEXT NOT NULL
        );
        """)


def _hash_file(path: str) -> str:
    """File ka MD5 hash — change detection ke liye."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return ""


class IncrementalGraphUpdater:
    """
    Phase 4: Incremental graph updates.
    Sirf changed/new/deleted files ko re-index karo.
    Full re-index se 10x faster hota hai large repos mein.
    """

    def __init__(self, repo_id: str, store):
        self.repo_id = repo_id
        self.store   = store
        init_incremental_db()

    def detect_changes(self, repo_path: str) -> Dict[str, List[str]]:
        """
        Repo mein kya kya badla? Three categories:
        - new: pehli baar dekha
        - modified: hash change hua
        - deleted: file gayab ho gayi
        """
        # Current snapshots DB se
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT file_path, content_hash FROM file_snapshots
                WHERE repo_id=?
            """, (self.repo_id,)).fetchall()
        known = {r["file_path"]: r["content_hash"] for r in rows}

        # Current disk files
        current_files: Set[str] = set()
        repo_p = Path(repo_path)
        for ext in [".py", ".js", ".ts", ".java", ".go", ".rs"]:
            for f in repo_p.rglob(f"*{ext}"):
                rel = str(f.relative_to(repo_p))
                if not any(skip in rel for skip in [".git", "__pycache__", "node_modules", ".venv"]):
                    current_files.add(rel)

        new_files      = []
        modified_files = []
        deleted_files  = []

        for filepath in current_files:
            abs_path = str(repo_p / filepath)
            file_hash = _hash_file(abs_path)
            if filepath not in known:
                new_files.append(filepath)
            elif known[filepath] != file_hash:
                modified_files.append(filepath)

        for filepath in known:
            if filepath not in current_files:
                deleted_files.append(filepath)

        print(f"[IncrementalUpdater] new={len(new_files)} modified={len(modified_files)} deleted={len(deleted_files)}")
        return {
            "new":      new_files,
            "modified": modified_files,
            "deleted":  deleted_files,
        }

    def update_snapshots(self, repo_path: str, changed_files: List[str],
                         node_counts: Dict[str, int] = None):
        """Snapshots update karo — indexes ke baad call karo."""
        now = datetime.utcnow().isoformat()
        repo_p = Path(repo_path)
        with _get_conn() as conn:
            for filepath in changed_files:
                abs_path = str(repo_p / filepath)
                file_hash = _hash_file(abs_path)
                nc = (node_counts or {}).get(filepath, 0)
                conn.execute("""
                    INSERT OR REPLACE INTO file_snapshots
                        (repo_id, file_path, content_hash, indexed_at, node_count)
                    VALUES (?, ?, ?, ?, ?)
                """, (self.repo_id, filepath, file_hash, now, nc))

    def remove_deleted_snapshots(self, deleted_files: List[str]):
        """Deleted files ke snapshots remove karo."""
        with _get_conn() as conn:
            for filepath in deleted_files:
                conn.execute("""
                    DELETE FROM file_snapshots
                    WHERE repo_id=? AND file_path=?
                """, (self.repo_id, filepath))

    def log_changelog(self, filepath: str, change_type: str,
                      nodes_added: int = 0, nodes_removed: int = 0):
        """Graph changelog — audit trail."""
        now = datetime.utcnow().isoformat()
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO graph_changelog
                    (repo_id, file_path, change_type, nodes_added,
                     nodes_removed, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (self.repo_id, filepath, change_type,
                  nodes_added, nodes_removed, now))

    def get_changelog(self, limit: int = 20) -> List[Dict]:
        """Recent graph changes."""
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM graph_changelog
                WHERE repo_id=?
                ORDER BY indexed_at DESC LIMIT ?
            """, (self.repo_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def needs_full_reindex(self, repo_path: str) -> bool:
        """
        Kya full reindex chahiye?
        - Pehli baar index ho raha ho
        - 50% se zyada files change hui hon
        """
        with _get_conn() as conn:
            count = conn.execute("""
                SELECT COUNT(*) as cnt FROM file_snapshots WHERE repo_id=?
            """, (self.repo_id,)).fetchone()["cnt"]
        if count == 0:
            return True

        changes = self.detect_changes(repo_path)
        total_changed = len(changes["new"]) + len(changes["modified"]) + len(changes["deleted"])
        return total_changed > count * 0.5
