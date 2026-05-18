"""
Phase 4 — Custom Agent Framework.
Users apne custom agents define kar sakte hain — YAML/JSON config se.
No code likhne ki zaroorat — bas capabilities aur prompts do.
"""
import os
import json
import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass


DB_PATH = os.getenv("MARKAR_DB_PATH", "markar.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_custom_agents_db():
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS custom_agents (
            agent_id     TEXT PRIMARY KEY,
            repo_id      TEXT NOT NULL,
            name         TEXT NOT NULL,
            description  TEXT,
            system_prompt TEXT NOT NULL,
            triggers     TEXT NOT NULL,
            capabilities TEXT NOT NULL,
            created_by   TEXT,
            is_active    INTEGER DEFAULT 1,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_custom_agents_repo
            ON custom_agents(repo_id, is_active);
        """)


@dataclass
class CustomAgentConfig:
    agent_id:     str
    repo_id:      str
    name:         str
    description:  str
    system_prompt: str
    triggers:     List[str]
    capabilities: List[str]
    created_by:   str = "user"


class CustomAgentRunner:
    """
    Phase 4: Custom agent runtime.
    DB se agent config lo, BaseAgent ki tarah run karo.
    """

    def __init__(self, config: CustomAgentConfig, store, base_agent_cls):
        self.config   = config
        self._agent   = base_agent_cls(store=store, repo_id=config.repo_id)

    def run(self, message: str, model: str = None) -> Dict:
        """Custom agent ko run karo."""
        # Graph se relevant data nikalo
        graph_data = self._collect_graph_data(message)

        answer = self._agent.ask_llm(
            system_prompt=self.config.system_prompt,
            user_message=message,
            graph_context=graph_data,
            model=model,
            include_history=True,
        )

        return {
            "answer":     answer,
            "agent":      f"custom:{self.config.name}",
            "agent_id":   self.config.agent_id,
        }

    def _collect_graph_data(self, message: str) -> Dict:
        """Message keywords se relevant graph data."""
        words = [w for w in message.lower().split() if len(w) > 3][:5]
        results = {}
        for word in words:
            nodes = self._agent.query("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE n.name CONTAINS $kw OR n.file_path CONTAINS $kw
                RETURN n.name AS name, n.file_path AS file,
                       n.node_type AS type LIMIT 5
            """, kw=word)
            if nodes:
                results[f"nodes_{word}"] = [
                    f"{n.get('name','?')} ({n.get('type','?')}) — {n.get('file','?')}"
                    for n in nodes
                ]
        return results


class CustomAgentManager:
    """
    CRUD for custom agents.
    Users apne specialized agents create kar sakte hain.
    """

    def __init__(self):
        init_custom_agents_db()

    def create_agent(self, config: Dict) -> Dict:
        """Naya custom agent banao."""
        import uuid
        agent_id = str(uuid.uuid4())[:12]
        now = datetime.utcnow().isoformat()

        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO custom_agents
                    (agent_id, repo_id, name, description, system_prompt,
                     triggers, capabilities, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agent_id,
                config["repo_id"],
                config["name"],
                config.get("description", ""),
                config["system_prompt"],
                json.dumps(config.get("triggers", [])),
                json.dumps(config.get("capabilities", [])),
                config.get("created_by", "user"),
                now, now,
            ))

        return self.get_agent(agent_id)

    def get_agent(self, agent_id: str) -> Optional[Dict]:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM custom_agents WHERE agent_id=?", (agent_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["triggers"]     = json.loads(d["triggers"])
        d["capabilities"] = json.loads(d["capabilities"])
        return d

    def list_repo_agents(self, repo_id: str) -> List[Dict]:
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM custom_agents
                WHERE repo_id=? AND is_active=1
                ORDER BY created_at DESC
            """, (repo_id,)).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["triggers"]     = json.loads(d["triggers"])
            d["capabilities"] = json.loads(d["capabilities"])
            result.append(d)
        return result

    def update_agent(self, agent_id: str, updates: Dict) -> Optional[Dict]:
        now = datetime.utcnow().isoformat()
        allowed = ["name", "description", "system_prompt", "triggers",
                   "capabilities", "is_active"]
        set_parts = []
        values = []
        for key in allowed:
            if key in updates:
                set_parts.append(f"{key}=?")
                val = updates[key]
                if isinstance(val, list):
                    val = json.dumps(val)
                values.append(val)

        if not set_parts:
            return self.get_agent(agent_id)

        set_parts.append("updated_at=?")
        values.append(now)
        values.append(agent_id)

        with _get_conn() as conn:
            conn.execute(
                f"UPDATE custom_agents SET {','.join(set_parts)} WHERE agent_id=?",
                values
            )
        return self.get_agent(agent_id)

    def delete_agent(self, agent_id: str):
        """Soft delete."""
        with _get_conn() as conn:
            conn.execute(
                "UPDATE custom_agents SET is_active=0 WHERE agent_id=?",
                (agent_id,)
            )

    def discover_custom_agent(self, repo_id: str, message: str) -> Optional[Dict]:
        """
        Message se matching custom agent dhundho.
        Default agents se pehle check karo.
        """
        agents = self.list_repo_agents(repo_id)
        msg_lower = message.lower()
        best_agent = None
        best_score = 0

        for agent in agents:
            score = sum(1 for t in agent["triggers"] if t in msg_lower)
            if score > best_score:
                best_score = score
                best_agent = agent

        return best_agent if best_score > 0 else None


# ── Global instances ──────────────────────────────────────────────────────
_custom_agent_manager = CustomAgentManager()


def get_custom_agent_manager() -> CustomAgentManager:
    return _custom_agent_manager
