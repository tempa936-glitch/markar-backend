"""
Recipe Engine — Multi-step Reusable Workflows.
User ek recipe run karta hai → multiple agent steps automatically execute hote hain.
Har step ka output agla step ka input ban jaata hai.

Built-in recipes:
  debug_and_fix   — Debug karo → Fix suggest karo → Test cases banao
  add_feature     — Clarify → Spec → Build → Tests
  write_tests     — Code analyze karo → Test cases banao → Coverage check
  code_review     — Files analyze → Issues list → Fixes suggest

Custom recipes bhi create ho sakte hain (SQLite mein save).
"""
import os
import json
import sqlite3
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

DB_PATH = os.getenv("MARKAR_DB_PATH", "markar.db")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_recipe_db():
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS recipes (
            recipe_id   TEXT PRIMARY KEY,
            repo_id     TEXT NOT NULL DEFAULT '*',
            name        TEXT NOT NULL,
            description TEXT DEFAULT '',
            steps       TEXT NOT NULL,
            is_builtin  INTEGER DEFAULT 0,
            created_by  TEXT DEFAULT 'system',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recipe_runs (
            run_id      TEXT PRIMARY KEY,
            recipe_id   TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            repo_id     TEXT NOT NULL,
            user_id     TEXT DEFAULT '',
            status      TEXT DEFAULT 'running',
            current_step INTEGER DEFAULT 0,
            total_steps  INTEGER DEFAULT 0,
            results     TEXT DEFAULT '[]',
            error       TEXT DEFAULT '',
            started_at  TEXT NOT NULL,
            finished_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_recipe_runs_session
            ON recipe_runs(session_id);
        """)


# ── Step & Recipe Dataclasses ─────────────────────────────────────────────────

@dataclass
class RecipeStep:
    """Ek step in a recipe."""
    step_id:    str
    name:       str
    agent:      str          # ask | debug | build | qa | impact | custom
    prompt:     str          # LLM ko kya bhejna hai ({{input}} se prev output inject hogi)
    target:     str = ""     # optional file/function target
    use_prev_output: bool = True   # kya previous step ka output inject karna hai
    required:   bool = True


@dataclass
class RecipeDef:
    """Ek complete recipe definition."""
    recipe_id:   str
    name:        str
    description: str
    steps:       List[RecipeStep]
    is_builtin:  bool = False
    repo_id:     str  = "*"
    created_by:  str  = "system"


# ── Built-in Recipes ──────────────────────────────────────────────────────────

BUILTIN_RECIPES: List[RecipeDef] = [
    RecipeDef(
        recipe_id="debug_and_fix",
        name="Debug & Fix",
        description="Bug dhundho, root cause analyze karo, fix + tests suggest karo",
        is_builtin=True,
        steps=[
            RecipeStep(
                step_id="s1_debug",
                name="Bug Analysis",
                agent="debug",
                prompt="Is target mein bugs aur issues dhundho. Root cause batao.",
                use_prev_output=False,
            ),
            RecipeStep(
                step_id="s2_fix",
                name="Fix Generation",
                agent="build",
                prompt="Pichle analysis ke basis pe fix suggest karo:\n{{prev_output}}\n\nClean, working code do.",
                use_prev_output=True,
            ),
            RecipeStep(
                step_id="s3_tests",
                name="Test Cases",
                agent="qa",
                prompt="Is fix ke liye test cases likho:\n{{prev_output}}",
                use_prev_output=True,
            ),
        ],
    ),
    RecipeDef(
        recipe_id="add_feature",
        name="Add Feature",
        description="Feature request lo → plan banao → code generate karo → tests likho",
        is_builtin=True,
        steps=[
            RecipeStep(
                step_id="s1_analyze",
                name="Codebase Analysis",
                agent="ask",
                prompt="Mujhe {{input}} feature add karni hai. Codebase mein kaunsi files relevant hain? Impact kya hoga?",
                use_prev_output=False,
            ),
            RecipeStep(
                step_id="s2_spec",
                name="Feature Spec",
                agent="build",
                prompt="Is analysis ke basis pe feature ka implementation plan banao:\n{{prev_output}}\n\nKaunsi files change hongi, kya add hoga.",
                use_prev_output=True,
            ),
            RecipeStep(
                step_id="s3_code",
                name="Code Generation",
                agent="build",
                prompt="Is spec ke according code generate karo:\n{{prev_output}}",
                use_prev_output=True,
            ),
            RecipeStep(
                step_id="s4_tests",
                name="Tests",
                agent="qa",
                prompt="Generated code ke liye comprehensive tests likho:\n{{prev_output}}",
                use_prev_output=True,
            ),
        ],
    ),
    RecipeDef(
        recipe_id="write_tests",
        name="Write Tests",
        description="Target file/function ke liye complete test suite banao",
        is_builtin=True,
        steps=[
            RecipeStep(
                step_id="s1_analyze",
                name="Code Analysis",
                agent="ask",
                prompt="Is target ka analysis karo — functions, edge cases, error paths kya hain?",
                use_prev_output=False,
            ),
            RecipeStep(
                step_id="s2_tests",
                name="Test Generation",
                agent="qa",
                prompt="Is analysis ke basis pe comprehensive tests likho:\n{{prev_output}}\n\nHar edge case cover karo.",
                use_prev_output=True,
            ),
        ],
    ),
    RecipeDef(
        recipe_id="code_review",
        name="Code Review",
        description="Code quality, security, performance issues analyze karo",
        is_builtin=True,
        steps=[
            RecipeStep(
                step_id="s1_quality",
                name="Quality Check",
                agent="ask",
                prompt="Is code mein quality issues, code smells, aur improvements dhundho.",
                use_prev_output=False,
            ),
            RecipeStep(
                step_id="s2_security",
                name="Security Analysis",
                agent="debug",
                prompt="Security vulnerabilities aur risks analyze karo:\n{{prev_output}}",
                use_prev_output=True,
            ),
            RecipeStep(
                step_id="s3_fixes",
                name="Fix Recommendations",
                agent="build",
                prompt="Oopar ke issues ke liye concrete fixes suggest karo:\n{{prev_output}}",
                use_prev_output=True,
            ),
        ],
    ),
]


# ── Recipe Manager ────────────────────────────────────────────────────────────

class RecipeEngine:
    """
    Recipe run karo — step by step, prev output next step mein inject.
    """

    def __init__(self):
        init_recipe_db()
        self._seed_builtins()

    def _seed_builtins(self):
        """Built-in recipes DB mein save karo (once)."""
        with _conn() as conn:
            for r in BUILTIN_RECIPES:
                existing = conn.execute(
                    "SELECT recipe_id FROM recipes WHERE recipe_id=?", (r.recipe_id,)
                ).fetchone()
                if not existing:
                    now = datetime.utcnow().isoformat()
                    conn.execute("""
                        INSERT INTO recipes
                            (recipe_id, repo_id, name, description, steps,
                             is_builtin, created_by, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        r.recipe_id, r.repo_id, r.name, r.description,
                        json.dumps([s.__dict__ for s in r.steps]),
                        1, "system", now, now,
                    ))

    def list_recipes(self, repo_id: str = "*") -> List[Dict]:
        """Available recipes list karo — builtin + repo-specific."""
        with _conn() as conn:
            rows = conn.execute("""
                SELECT recipe_id, name, description, is_builtin,
                       created_by, created_at,
                       json_array_length(steps) as step_count
                FROM recipes
                WHERE repo_id='*' OR repo_id=?
                ORDER BY is_builtin DESC, name ASC
            """, (repo_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_recipe(self, recipe_id: str) -> Optional[RecipeDef]:
        with _conn() as conn:
            row = conn.execute(
                "SELECT * FROM recipes WHERE recipe_id=?", (recipe_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        steps_raw = json.loads(d["steps"])
        steps = [RecipeStep(**s) for s in steps_raw]
        return RecipeDef(
            recipe_id=d["recipe_id"],
            name=d["name"],
            description=d["description"],
            steps=steps,
            is_builtin=bool(d["is_builtin"]),
            repo_id=d["repo_id"],
            created_by=d["created_by"],
        )

    def create_recipe(self, data: Dict) -> Dict:
        """Custom recipe create karo."""
        recipe_id = data.get("recipe_id") or str(uuid.uuid4())[:12]
        now = datetime.utcnow().isoformat()
        steps = data.get("steps", [])

        with _conn() as conn:
            conn.execute("""
                INSERT INTO recipes
                    (recipe_id, repo_id, name, description, steps,
                     is_builtin, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
            """, (
                recipe_id,
                data.get("repo_id", "*"),
                data["name"],
                data.get("description", ""),
                json.dumps(steps),
                data.get("created_by", "user"),
                now, now,
            ))
        return {"recipe_id": recipe_id, "name": data["name"], "steps": steps}

    async def run(
        self,
        recipe_id: str,
        session_id: str,
        repo_id: str,
        user_input: str,
        target: str = "",
        model: str = None,
        user_id: str = "",
        store=None,
    ) -> Dict:
        """
        Recipe execute karo — sare steps sequentially.
        Returns run summary with all step results.
        """
        recipe = self.get_recipe(recipe_id)
        if not recipe:
            return {"error": f"Recipe '{recipe_id}' nahi mili.", "status": "failed"}

        run_id = str(uuid.uuid4())[:12]
        now = datetime.utcnow().isoformat()

        # Run record create karo
        with _conn() as conn:
            conn.execute("""
                INSERT INTO recipe_runs
                    (run_id, recipe_id, session_id, repo_id, user_id,
                     status, current_step, total_steps, started_at)
                VALUES (?, ?, ?, ?, ?, 'running', 0, ?, ?)
            """, (run_id, recipe_id, session_id, repo_id, user_id,
                  len(recipe.steps), now))

        step_results = []
        prev_output  = ""
        final_status = "success"

        for idx, step in enumerate(recipe.steps):
            # Prompt mein {{input}} aur {{prev_output}} inject karo
            prompt = step.prompt
            prompt = prompt.replace("{{input}}", user_input)
            if step.use_prev_output and prev_output:
                prompt = prompt.replace("{{prev_output}}", prev_output[:2000])
            else:
                prompt = prompt.replace("{{prev_output}}", "")

            step_target = target or step.target

            # Progress update
            with _conn() as conn:
                conn.execute(
                    "UPDATE recipe_runs SET current_step=? WHERE run_id=?",
                    (idx + 1, run_id)
                )

            try:
                result = await self._run_step(
                    step=step,
                    prompt=prompt,
                    target=step_target,
                    repo_id=repo_id,
                    session_id=f"{session_id}_step{idx}",
                    model=model,
                    store=store,
                )
                answer = result.get("answer", "")
                step_results.append({
                    "step_id":   step.step_id,
                    "name":      step.name,
                    "agent":     step.agent,
                    "status":    "success",
                    "output":    answer,
                    "seq":       idx + 1,
                })
                prev_output = answer

            except Exception as e:
                err_msg = str(e)[:300]
                step_results.append({
                    "step_id": step.step_id,
                    "name":    step.name,
                    "agent":   step.agent,
                    "status":  "error",
                    "error":   err_msg,
                    "seq":     idx + 1,
                })
                if step.required:
                    final_status = "failed"
                    break

        # Run finalize karo
        finished = datetime.utcnow().isoformat()
        with _conn() as conn:
            conn.execute("""
                UPDATE recipe_runs
                SET status=?, results=?, finished_at=?
                WHERE run_id=?
            """, (final_status, json.dumps(step_results), finished, run_id))

        return {
            "run_id":       run_id,
            "recipe_id":    recipe_id,
            "recipe_name":  recipe.name,
            "status":       final_status,
            "total_steps":  len(recipe.steps),
            "steps":        step_results,
            "final_output": prev_output,
            "session_id":   session_id,
        }

    async def _run_step(
        self,
        step: RecipeStep,
        prompt: str,
        target: str,
        repo_id: str,
        session_id: str,
        model: str,
        store,
    ) -> Dict:
        """Single step run karo — DelegationManager use karke."""
        import asyncio
        from app.agents.delegation_manager import DelegationManager

        dm = DelegationManager(store=store, repo_id=repo_id)
        result = await dm.execute(
            message=prompt,
            session_id=session_id,
            intent=step.agent if step.agent in ("ask","debug","build","qa","impact") else None,
            target=target or None,
            model=model,
        )
        return result

    def get_run(self, run_id: str) -> Optional[Dict]:
        with _conn() as conn:
            row = conn.execute(
                "SELECT * FROM recipe_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["results"] = json.loads(d.get("results") or "[]")
        return d


# ── Global instance ───────────────────────────────────────────────────────────

_engine = RecipeEngine()


def get_recipe_engine() -> RecipeEngine:
    return _engine
