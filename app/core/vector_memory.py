"""
Phase 4 — Vector Memory.
Semantic search over codebase — keyword matching se better.
Embeddings store karo, similar code dhundho.

Lightweight implementation:
- sentence-transformers se embeddings (requirements mein already hai)
- SQLite mein store (no extra infra)
- cosine similarity se search
"""
import os
import json
import sqlite3
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime


DB_PATH = os.getenv("MARKAR_DB_PATH", "markar.db")
EMBED_MODEL = os.getenv("MARKAR_EMBED_MODEL", "all-MiniLM-L6-v2")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_vector_db():
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS code_embeddings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id      TEXT NOT NULL,
            node_id      TEXT NOT NULL,
            node_type    TEXT NOT NULL,
            file_path    TEXT NOT NULL,
            content      TEXT NOT NULL,
            embedding    BLOB NOT NULL,
            created_at   TEXT NOT NULL,
            UNIQUE(repo_id, node_id)
        );

        CREATE INDEX IF NOT EXISTS idx_embeddings_repo
            ON code_embeddings(repo_id, node_type);
        """)


class VectorMemory:
    """
    Phase 4: Semantic code search.
    Natural language se code dhundho — "authentication logic" →
    relevant functions mil jayenge even if keyword "auth" nahi hai.
    """

    def __init__(self, repo_id: str):
        self.repo_id = repo_id
        self._model  = None
        init_vector_db()

    def _get_model(self):
        """Lazy load — pehli baar call pe load karo."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(EMBED_MODEL)
                print(f"[VectorMemory] Model loaded: {EMBED_MODEL}")
            except ImportError:
                print("[VectorMemory] sentence-transformers not installed — pip install sentence-transformers")
                return None
        return self._model

    def embed(self, text: str) -> Optional[np.ndarray]:
        """Text ko embedding vector mein convert karo."""
        model = self._get_model()
        if not model:
            return None
        try:
            vec = model.encode(text, convert_to_numpy=True)
            return vec.astype(np.float32)
        except Exception as e:
            print(f"[VectorMemory] Embed failed: {e}")
            return None

    def store_node(self, node_id: str, node_type: str,
                   file_path: str, content: str):
        """Code node ka embedding store karo."""
        vec = self.embed(content)
        if vec is None:
            return

        now = datetime.utcnow().isoformat()
        with _get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO code_embeddings
                    (repo_id, node_id, node_type, file_path,
                     content, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (self.repo_id, node_id, node_type, file_path,
                  content[:500], vec.tobytes(), now))

    def search(self, query: str, top_k: int = 5,
               node_type: str = None) -> List[Dict]:
        """
        Semantic search — query ke similar code nodes dhundho.
        Returns ranked results with similarity scores.
        """
        query_vec = self.embed(query)
        if query_vec is None:
            return []

        # DB se embeddings fetch karo
        with _get_conn() as conn:
            if node_type:
                rows = conn.execute("""
                    SELECT node_id, node_type, file_path, content, embedding
                    FROM code_embeddings
                    WHERE repo_id=? AND node_type=?
                """, (self.repo_id, node_type)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT node_id, node_type, file_path, content, embedding
                    FROM code_embeddings WHERE repo_id=?
                """, (self.repo_id,)).fetchall()

        if not rows:
            return []

        # Cosine similarity calculate karo
        results = []
        q_norm = np.linalg.norm(query_vec)

        for row in rows:
            try:
                stored_vec = np.frombuffer(row["embedding"], dtype=np.float32)
                sim = float(np.dot(query_vec, stored_vec) /
                            (q_norm * np.linalg.norm(stored_vec) + 1e-8))
                results.append({
                    "node_id":   row["node_id"],
                    "node_type": row["node_type"],
                    "file_path": row["file_path"],
                    "content":   row["content"],
                    "score":     round(sim, 3),
                })
            except Exception:
                continue

        # Sort by similarity
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def bulk_store(self, nodes: List[Dict]):
        """
        Multiple nodes ek saath store karo — indexing time pe.
        nodes: [{node_id, node_type, file_path, content}]
        """
        model = self._get_model()
        if not model:
            return 0

        stored = 0
        now = datetime.utcnow().isoformat()

        # Batch embedding (faster than one-by-one)
        texts = [n.get("content", "")[:500] for n in nodes]
        try:
            vecs = model.encode(texts, convert_to_numpy=True, batch_size=32)
        except Exception as e:
            print(f"[VectorMemory] Bulk embed failed: {e}")
            return 0

        with _get_conn() as conn:
            for node, vec in zip(nodes, vecs):
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO code_embeddings
                            (repo_id, node_id, node_type, file_path,
                             content, embedding, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        self.repo_id,
                        node.get("node_id", ""),
                        node.get("node_type", ""),
                        node.get("file_path", ""),
                        node.get("content", "")[:500],
                        vec.astype(np.float32).tobytes(),
                        now,
                    ))
                    stored += 1
                except Exception:
                    continue

        print(f"[VectorMemory] Stored {stored}/{len(nodes)} embeddings")
        return stored

    def get_stats(self) -> Dict:
        """Vector store stats."""
        with _get_conn() as conn:
            total = conn.execute("""
                SELECT COUNT(*) as cnt FROM code_embeddings WHERE repo_id=?
            """, (self.repo_id,)).fetchone()["cnt"]

            by_type = conn.execute("""
                SELECT node_type, COUNT(*) as cnt FROM code_embeddings
                WHERE repo_id=? GROUP BY node_type
            """, (self.repo_id,)).fetchall()

        return {
            "total_vectors": total,
            "by_type": [dict(r) for r in by_type],
            "model": EMBED_MODEL,
        }


# ── Global cache ──────────────────────────────────────────────────────────
_vector_cache: Dict[str, VectorMemory] = {}


def get_vector_memory(repo_id: str) -> VectorMemory:
    if repo_id not in _vector_cache:
        _vector_cache[repo_id] = VectorMemory(repo_id)
    return _vector_cache[repo_id]
