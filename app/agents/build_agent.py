"""
Build Agent — feature request lo, plan banao,
permission lo, code generate karo, PR push karo.

Flow:
1. clarify()   — sawaal poocho
2. spec()      — plan banao
3. confirm()   — permission lo
4. build()     — code generate karo
5. push_pr()   — GitHub PR banao
"""
import os
import json
from typing import Dict, List, Optional
from .base_agent import BaseAgent


class BuildAgent(BaseAgent):

    SPEC_PROMPT = """
Tu ek senior software engineer hai jo feature implement karta hai.
Tumhare paas codebase ka knowledge graph hai — kaunsi files hain,
functions kya karte hain, dependencies kya hain.

Ek JSON spec banao is format mein:
{
  "feature": "feature ka naam",
  "summary": "2 line mein kya karna hai",
  "files_to_modify": [
    {"path": "relative/path.py", "reason": "kyun change hoga", "changes": "kya change hoga"}
  ],
  "files_to_create": [
    {"path": "new/file.py", "purpose": "kya kaam karega"}
  ],
  "dependencies_to_add": ["package1", "package2"],
  "affected_functions": ["func1", "func2"],
  "risks": ["risk1", "risk2"],
  "estimated_time": "2 hours"
}

Sirf JSON do, kuch aur nahi.
"""

    CODE_PROMPT = """
Tu ek senior software engineer hai.
Tumhare paas:
1. Feature ki spec
2. Codebase ka knowledge graph — kaunsi files hain, functions kya karte hain
3. Existing code patterns

Diye gaye spec ke according code do.

Rules:
- Existing code style follow karo
- Sirf zaroorat ki files change karo
- Har file ke liye diff format mein do:
  FILE: path/to/file.py
  ACTION: modify/create
  CODE:
```python
  ... poora code ...
```
- Tests bhi do agar existing test files hain
"""

    CLARIFY_PROMPT = """
Tu ek product manager + engineer hai.
User ne ek feature request ki hai.
Knowledge graph dekh ke 2-3 clarifying questions poocho jo
implementation ke liye zaroorat hain.

Questions short rakho. JSON array mein do:
["question 1", "question 2", "question 3"]

Sirf JSON array do.
"""

    def __init__(self, store, repo_id: str = "", session_id: str = None,
             conv_store=None, tool_registry=None):
        super().__init__(store, repo_id, session_id, conv_store, tool_registry)
        # Build session state — multi-step conversation
        self._sessions: Dict[str, Dict] = {}

    # ─────────────────────────────────────────────────────────────────
    # Step 1 — Clarifying questions poocho
    # ─────────────────────────────────────────────────────────────────
    def clarify(self, session_id: str, feature_request: str,
                model: str = None) -> Dict:
        """
        Pehla step — feature samjho, sawaal poocho.
        """
        # Graph se relevant context nikalo
        context = self._get_relevant_context(feature_request)

        questions_raw = self.ask_llm(
            system_prompt=self.CLARIFY_PROMPT,
            user_message=feature_request,
            graph_context=context,
            model=model,
        )

        # JSON parse karo
        try:
            questions = json.loads(questions_raw.strip())
            if not isinstance(questions, list):
                questions = [questions_raw]
        except Exception:
            questions = [
                "Kaunsi existing functionality ke saath integrate karna hai?",
                "Koi specific library ya approach prefer karte ho?",
                "Tests bhi chahiye?",
            ]

        # Session mein save karo
        self._sessions[session_id] = {
            "stage":           "clarifying",
            "feature_request": feature_request,
            "context":         context,
            "questions":       questions,
            "answers":         {},
            "spec":            None,
            "generated_code":  None,
        }

        return {
            "stage":     "clarifying",
            "questions": questions,
            "message":   "Kuch cheezein samajhni hain implement karne se pehle:",
            "agent":     "build",
        }

    # ─────────────────────────────────────────────────────────────────
    # Step 2 — Answers lo, spec banao
    # ─────────────────────────────────────────────────────────────────
    def make_spec(self, session_id: str, answers: Dict[str, str],
                  model: str = None) -> Dict:
        """
        User ke answers leke spec banao.
        answers = { "question": "user ka jawab" }
        """
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session nahi mila. Naya build shuru karo."}

        session["answers"] = answers
        session["stage"]   = "planning"

        # Answers ko context mein add karo
        qa_text = "\n".join(
            f"Q: {q}\nA: {a}" for q, a in answers.items()
        )

        full_context = {
            **session["context"],
            "user_answers": qa_text,
            "feature":      session["feature_request"],
        }

        spec_raw = self.ask_llm(
            system_prompt=self.SPEC_PROMPT,
            user_message=session["feature_request"],
            graph_context=full_context,
            model=model,
        )

        # JSON spec parse karo
        try:
            # LLM kabhi kabhi ```json ``` wrap karta hai
            clean = spec_raw.strip()
            if "```" in clean:
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            spec = json.loads(clean)
        except Exception as e:
            print(f"[BuildAgent] Spec parse failed: {e}")
            spec = {
                "feature":          session["feature_request"],
                "summary":          spec_raw[:200],
                "files_to_modify":  [],
                "files_to_create":  [],
                "dependencies_to_add": [],
                "risks":            [],
                "estimated_time":   "unknown",
            }

        session["spec"] = spec

        # Human readable plan banao
        plan_text = self._format_plan(spec)

        return {
            "stage":   "confirm",
            "spec":    spec,
            "plan":    plan_text,
            "message": "Yeh plan hai. Approve karo toh code generate karunga:",
            "agent":   "build",
        }

    # ─────────────────────────────────────────────────────────────────
    # Step 3 — Permission leke code generate karo
    # ─────────────────────────────────────────────────────────────────
    def build(self, session_id: str, approved: bool,
              model: str = None) -> Dict:
        """
        User ne approve kiya → code generate karo.
        approved=False → cancel karo.
        """
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session nahi mila."}

        if not approved:
            del self._sessions[session_id]
            return {
                "stage":   "cancelled",
                "message": "Build cancel kar diya. Naya request bhejo.",
                "agent":   "build",
            }

        session["stage"] = "building"
        spec = session["spec"]

        # Har file ke liye code generate karo
        generated = []

        files_to_handle = (
            [{"action": "modify", **f} for f in spec.get("files_to_modify", [])] +
            [{"action": "create", **f} for f in spec.get("files_to_create", [])]
        )

        for file_info in files_to_handle:
            code = self._generate_file_code(
                file_info=file_info,
                spec=spec,
                context=session["context"],
                model=model,
            )
            generated.append({
                "path":   file_info["path"],
                "action": file_info["action"],
                "code":   code,
            })

        session["generated_code"] = generated

        return {
            "stage":     "review",
            "files":     generated,
            "message":   "Code ready hai. Review karo phir PR push karo:",
            "pr_ready":  True,
            "agent":     "build",
        }

    # ─────────────────────────────────────────────────────────────────
    # Step 4 — GitHub PR push karo
    # ─────────────────────────────────────────────────────────────────
    def push_pr(self, session_id: str,
                github_token: str,
                repo_full_name: str) -> Dict:
        """
        Generated code ko GitHub PR mein push karo.
        repo_full_name = "owner/repo-name"
        """
        session = self._sessions.get(session_id)
        if not session or not session.get("generated_code"):
            return {"error": "Pehle build karo."}

        try:
            import requests

            spec        = session["spec"]
            branch_name = f"markar/build-{session_id[:8]}"
            headers     = {
                "Authorization": f"token {github_token}",
                "Accept":        "application/vnd.github.v3+json",
            }
            base_url = f"https://api.github.com/repos/{repo_full_name}"

            # ── 1. Default branch ka SHA nikalo ──────────────────────
            repo_info   = requests.get(base_url, headers=headers).json()
            default_br  = repo_info.get("default_branch", "main")
            ref_info    = requests.get(
                f"{base_url}/git/ref/heads/{default_br}", headers=headers
            ).json()
            base_sha    = ref_info["object"]["sha"]

            # ── 2. Naya branch banao ─────────────────────────────────
            requests.post(f"{base_url}/git/refs", headers=headers, json={
                "ref": f"refs/heads/{branch_name}",
                "sha": base_sha,
            })

            # ── 3. Har file commit karo ───────────────────────────────
            for file_item in session["generated_code"]:
                import base64
                content_b64 = base64.b64encode(
                    file_item["code"].encode()
                ).decode()

                # File exist karti hai? SHA chahiye update ke liye
                existing = requests.get(
                    f"{base_url}/contents/{file_item['path']}",
                    headers=headers,
                    params={"ref": branch_name},
                )
                body = {
                    "message": f"markar: {file_item['action']} {file_item['path']}",
                    "content": content_b64,
                    "branch":  branch_name,
                }
                if existing.status_code == 200:
                    body["sha"] = existing.json()["sha"]

                requests.put(
                    f"{base_url}/contents/{file_item['path']}",
                    headers=headers,
                    json=body,
                )

            # ── 4. PR open karo ───────────────────────────────────────
            pr_body = self._format_pr_description(spec, session)
            pr_res  = requests.post(
                f"{base_url}/pulls", headers=headers, json={
                    "title": f"[Markar] {spec.get('feature', 'New Feature')}",
                    "body":  pr_body,
                    "head":  branch_name,
                    "base":  default_br,
                }
            ).json()

            # Session cleanup
            del self._sessions[session_id]

            return {
                "stage":    "done",
                "pr_url":   pr_res.get("html_url", ""),
                "pr_number": pr_res.get("number", ""),
                "branch":   branch_name,
                "message":  f"PR ready: {pr_res.get('html_url', '')}",
                "agent":    "build",
            }

        except Exception as e:
            return {
                "error":  f"PR push failed: {str(e)}",
                "stage":  "error",
                "agent":  "build",
            }

    # ─────────────────────────────────────────────────────────────────
    # Helper methods
    # ─────────────────────────────────────────────────────────────────
    def _get_relevant_context(self, feature_request: str) -> Dict:
        """Feature request se relevant graph data nikalo."""
        keywords = feature_request.lower().split()[:5]
        kw       = " ".join(keywords)

        # Related files
        files = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
            WHERE any(kw IN $kws WHERE toLower(f.file_path) CONTAINS kw)
            RETURN f.file_path AS path, f.name AS name
            LIMIT 15
        """, kws=keywords)

        # High impact files — jo bahut zyada connected hain
        hotspots = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
            OPTIONAL MATCH ()-[:DEPENDS_ON]->(f)
            WITH f, count(*) AS deps
            ORDER BY deps DESC LIMIT 10
            RETURN f.file_path AS path, deps AS dependents
        """)

        # Existing test files
        tests = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
            WHERE f.file_path CONTAINS 'test'
            RETURN f.file_path AS path LIMIT 5
        """)

        return {
            "feature_request":  feature_request,
            "related_files":    [f["path"] for f in files],
            "high_impact_files": [h["path"] for h in hotspots],
            "test_files":       [t["path"] for t in tests],
            "total_files":      self.query_one(
                "MATCH (f:CodeNode {repo_id:$r, node_type:'file'}) "
                "RETURN count(f) AS cnt"
            ) or {"cnt": 0},
        }

    def _generate_file_code(self, file_info: Dict, spec: Dict,
                             context: Dict, model: str = None) -> str:
        """Ek file ka code generate karo."""
        file_context = {
            **context,
            "current_file":    file_info.get("path"),
            "action":          file_info.get("action"),
            "file_purpose":    file_info.get("reason") or file_info.get("purpose"),
            "what_to_change":  file_info.get("changes", ""),
            "full_spec":       json.dumps(spec, indent=2),
        }

        return self.ask_llm(
            system_prompt=self.CODE_PROMPT,
            user_message=f"Generate code for: {file_info['path']}",
            graph_context=file_context,
            model=model,
        )

    def _format_plan(self, spec: Dict) -> str:
        """Spec ko human readable plan mein convert karo."""
        lines = [
            f"📋 Feature: {spec.get('feature', '')}",
            f"📝 Summary: {spec.get('summary', '')}",
            f"⏱  Estimated time: {spec.get('estimated_time', 'unknown')}",
            "",
        ]

        if spec.get("files_to_modify"):
            lines.append("📝 Files modify honge:")
            for f in spec["files_to_modify"]:
                lines.append(f"  • {f['path']} — {f.get('reason', '')}")

        if spec.get("files_to_create"):
            lines.append("🆕 Naye files banenge:")
            for f in spec["files_to_create"]:
                lines.append(f"  • {f['path']} — {f.get('purpose', '')}")

        if spec.get("dependencies_to_add"):
            lines.append("📦 Dependencies:")
            for d in spec["dependencies_to_add"]:
                lines.append(f"  • {d}")

        if spec.get("risks"):
            lines.append("⚠️  Risks:")
            for r in spec["risks"]:
                lines.append(f"  • {r}")

        return "\n".join(lines)

    def _format_pr_description(self, spec: Dict, session: Dict) -> str:
        """PR description banao."""
        files_changed = "\n".join(
            f"- `{f['path']}` ({f['action']})"
            for f in session.get("generated_code", [])
        )
        return f"""## 🤖 Generated by Markar.ai Build Agent

### Feature
{spec.get('feature', '')}

### Summary
{spec.get('summary', '')}

### Files Changed
{files_changed}

### Risks
{chr(10).join(f'- {r}' for r in spec.get('risks', []))}

---
*This PR was automatically generated by [Markar.ai](https://markarai.netlify.app)*
"""