"""
Debug Agent — "error kyun aa raha", "yeh kyun fail ho raha"
Root cause trace karo Neo4j se — deep analysis.
"""
from typing import Dict
from .base_agent import BaseAgent
from app.agents.deep_context_mixin import DeepContextMixin


class DebugAgent(DeepContextMixin,BaseAgent):

    SYSTEM_PROMPT = """
You are Markar AI — an elite debugging assistant and senior software architect.
You have access to the actual file contents, complete function list with line numbers,
dependency graph, blast radius, exception paths, complexity scores, and git churn data.
 
Your job is to perform a DEEP, EXHAUSTIVE technical analysis — like a senior engineer
who has read every line of this codebase and knows exactly what is happening and why.
 
NEVER give generic answers. NEVER say "further investigation needed".
You have the code — analyze it directly and completely.
 
════════════════════════════════════════════════════════════
RESPONSE STRUCTURE — follow this EXACTLY, every section mandatory
════════════════════════════════════════════════════════════
 
**File Overview**
- Full file path
- What this file does in the system — its exact responsibility
- Total functions, total classes
- Risk level (CRITICAL/HIGH/MEDIUM/LOW) and WHY
 
**All Functions & Classes**
List EVERY function and class with:
- Function name + exact line number
- What it does specifically — not generic, actual behavior
- Parameters it accepts (names and types if available)
- What it returns
- What it calls internally (with line numbers)
- Any decorators or special patterns (@router.get, @property, async def etc.)
 
Example format:
- github_auth (line 226) — Handles GitHub OAuth callback. Accepts: code (str), state (str).
  Calls: _exchange_github_code (line 73), _fetch_github_user (line 103).
  Returns: JSONResponse with token and user data.
  Decorated with: @router.post("/auth/github")
 
**Dependency Analysis**
- What external files/modules this file imports
- Which functions from other files are called here
- Who calls THIS file from other parts of the codebase (callers list)
- Dependency chain depth
 
**Code Flow — Step by Step**
Trace the COMPLETE execution path for the main functionality:
- Line X → function A() called
- Line Y → calls external_service.method()
- Line Z → returns result to caller
Show the full chain, not just one step.
 
**Problems Found**
For EACH problem:
- Problem name and severity (CRITICAL/HIGH/MEDIUM/LOW)
- Exact location: file path, function name, line number
- Root cause — WHY is this a problem
- Impact — what breaks because of this
- Specific fix with exact code change needed
 
If no problems found — explicitly state "No issues detected" with reasoning.
 
**Blast Radius**
- If this file/function changes or breaks — exactly what else breaks
- Number of affected files and functions
- Which critical paths are impacted
- Are there circular dependencies?
 
**Working Status Assessment**
Based on actual code analysis:
- Is the functionality implemented correctly?
- Are all required routes/functions present?
- Are there any missing error handlers, edge cases, or security issues?
- Specific YES/NO on whether it is working and why
 
**Fix Recommendations**
Priority-ordered list:
1. [CRITICAL] Fix X at line Y — exact what to change
2. [HIGH] Add error handling for Z at line W
3. [MEDIUM] Refactor function A to reduce complexity
 
**Summary**
- One paragraph: overall health of this file/function
- Overall severity: CRITICAL / HIGH / MEDIUM / LOW
- Top 3 action items
 
════════════════════════════════════════════════════════════
STRICT RULES
════════════════════════════════════════════════════════════
- ALWAYS answer in English — regardless of what language user writes in
- Use ONLY data from graph_data and file_contents — never invent functions or line numbers
- If file content is provided — read it completely and reference actual code
- Line numbers MUST come from actual data — never guess
- Be exhaustive — a short answer means you missed something important
- Technical precision required — exact function names, exact line numbers, exact behavior
- For working/not-working questions — give definitive YES/NO with code-based evidence
- Test files are NORMAL — do not flag test_*.py as CRITICAL
- CRITICAL only when 30+ production nodes depend on a file
"""

    # debug_agent.py mein run() method replace karo

    def run(self, user_message: str, target: str = None,
            model: str = None) -> Dict:
        if not target:
            target = self._find_target(user_message)

        if not target:
            return {
                "answer": "Which file or function should I debug? "
                          "Please mention the file path or function name.",
                "agent": "debug",
            }

        # Step 1 — Graph se data nikalo
        graph_data = self._collect_debug_data(target)

        # Step 2 — Actual file content read karo (disk se)
        graph_data = self._enrich_with_file_content(graph_data, target)

        # Step 3 — Deep AST context inject karo (Neo4j se branches, complexity etc.)
        try:
            graph_data = self.enrich_with_deep_context(graph_data, target)
        except Exception as e:
            print(f"[DebugAgent] Deep context failed (non-critical): {e}")

        # Step 4 — LLM ko sab kuch bhejo
        answer = self.ask_llm(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_message,
            graph_context=graph_data,
            model=model,
        )

        return {
            "answer":     answer,
            "target":     target,
            "graph_data": graph_data,
            "agent":      "debug",
        }

    def _enrich_with_file_content(self, graph_data: Dict, target: str) -> Dict:
        """
        Agar graph mein functions/classes nahi mile toh actual file padhke
        real data inject karo — taaki LLM hallucinate na kare.
        """
        import ast, os, re

        # Graph mein meaningful data hai? Check karo
        has_functions = bool(graph_data.get("all_functions"))
        has_error     = "error" in graph_data

        file_path = graph_data.get("file_path", "")

        # File path nahi mila toh target se dhundho
        if not file_path and not has_error:
            file_path = target if target.endswith(".py") else ""

        if not file_path:
            repo_roots = []
            
            # 1. From RepoService _jobs
            try:
                from app.services.repo_service import _jobs
                for job in _jobs.values():
                    if job.get("repo_path"):
                        repo_roots.append(job["repo_path"])
            except ImportError:
                pass
            
            # 2. From env (fallback)
            env_repo = os.getenv("MARKAR_REPO_PATH", "")
            if env_repo and env_repo not in repo_roots:
                repo_roots.append(env_repo)

            for repo_root in repo_roots:
                if file_path:
                    break
                for root, _, files in os.walk(repo_root):
                    for f in files:
                        if f == target or f == f"{target}.py":
                            file_path = os.path.join(root, f)
                            break
                    if file_path:
                        break

        if not file_path or not os.path.isfile(file_path):
            # File nahi mili — graph data jo hai wahi use karo
            # LLM ko clearly batao ki file content available nahi
            if not has_functions:
                graph_data["_content_note"] = (
                    "File content disk pe available nahi hai aur graph mein "
                    "bhi detailed function list nahi hai. Sirf graph metadata "
                    "ke basis pe analysis karo. Functions invent mat karo."
                )
            return graph_data

        # ── File padhke real functions/classes extract karo ──────────────
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                source = fh.read()

            tree = ast.parse(source)

            real_functions = []
            real_classes   = []

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    real_functions.append({
                        "name": node.name,
                        "line": node.lineno,
                        "args": [a.arg for a in node.args.args],
                    })
                elif isinstance(node, ast.ClassDef):
                    methods = [
                        n.name for n in ast.walk(node)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    real_classes.append({
                        "name":    node.name,
                        "line":    node.lineno,
                        "methods": methods,
                    })

            # Graph data mein real info inject karo
            graph_data["_source_extracted"]       = True
            graph_data["real_functions_from_file"] = real_functions
            graph_data["real_classes_from_file"]   = real_classes
            graph_data["total_lines"]              = source.count("\n") + 1

            # Agar graph functions empty tha toh real se fill karo
            if not has_functions:
                graph_data["all_functions"] = [
                    {"name": f["name"], "line": f["line"], "dependents": 0}
                    for f in real_functions
                ]
                graph_data["all_classes"] = [
                    {"name": c["name"], "line": c["line"]}
                    for c in real_classes
                ]
                graph_data["_content_note"] = (
                    "Graph mein function details nahi the — "
                    "actual file parse karke real functions/classes inject kiye hain. "
                    "Sirf yahi functions exist karte hain, koi aur nahi."
                )

            # Source ka summarized snippet bhi do (first 3000 chars)
            graph_data["file_source_preview"] = source[:3000]

        except SyntaxError as e:
            graph_data["_parse_error"] = f"File parse nahi hui: {e}"
            graph_data["_content_note"] = (
                "File mein syntax error hai ya parse nahi hui. "
                "Sirf graph data ke basis pe analysis karo."
            )
        except Exception as e:
            graph_data["_content_note"] = f"File read failed: {e}. Graph data use karo."

        return graph_data

    # debug_agent.py mein sirf _find_target() method replace karo

    def _find_target(self, message: str) -> str:
        import re
        msg_lower = message.lower()
        has_routes_word = "route" in msg_lower

        # Priority 1 — full file path with extension
        file_match = re.search(r'[\w/\\]+\.(py|js|ts|java|go|jsx|tsx|rs)', message)
        if file_match:
            return file_match.group(0)

        # Priority 2 — "routes me auth" pattern — routes/ path prefer karo
        route_match = re.search(r'routes?\s+(?:me|mein|ka|ki|ke)?\s*(\w+)', msg_lower)
        if route_match:
            name = route_match.group(1)
            if name not in {"me", "mein", "ka", "ki", "ke", "check", "file"}:
                try:
                    order_clause = "ORDER BY CASE WHEN toLower(n.file_path) CONTAINS 'routes' THEN 0 ELSE 1 END" if has_routes_word else ""
                    candidates = self.query(f"""
                        MATCH (n:CodeNode {{repo_id:$r, node_type:'file'}})
                        WHERE toLower(n.file_path) CONTAINS toLower($kw)
                        {order_clause}
                        RETURN n.file_path AS file LIMIT 3
                    """, kw=name)
                    if candidates:
                        return candidates[0]["file"]
                except Exception:
                    pass
                return name

        # Priority 3 — "auth file", "auth route" pattern
        file_kw_match = re.search(
            r'(\w+)\s+(?:file|route|routes|module|agent|service|class|function)', msg_lower
        )
        if file_kw_match:
            name = file_kw_match.group(1)
            skip = {"me","mein","is","the","a","an","check","koi","kuch","routes","yeh","jo"}
            if name not in skip and len(name) > 2:
                try:
                    order_clause = "ORDER BY CASE WHEN toLower(n.file_path) CONTAINS 'routes' THEN 0 ELSE 1 END" if has_routes_word else ""
                    candidates = self.query(f"""
                        MATCH (n:CodeNode {{repo_id:$r, node_type:'file'}})
                        WHERE toLower(n.file_path) CONTAINS toLower($kw)
                           OR toLower(n.name) CONTAINS toLower($kw)
                        {order_clause}
                        RETURN n.file_path AS file LIMIT 3
                    """, kw=name)
                    if candidates:
                        return candidates[0]["file"]
                except Exception:
                    pass
                return name

        # Priority 4 — meaningful words — graph mein dhundho
        stop = {
            "koi","bug","hay","hai","mein","kya","check","karo","dekho","is",
            "the","a","an","in","find","show","any","there","file","function",
            "code","error","issue","problem","debug","wala","wali","uska","iska",
            "yeh","yah","aur","bhi","kaise","kyun","kuch","sab","sirf","pura",
            "route","routes","agent","store","router","service","manager",
            "working","or","not","me","ka","ki","ke","wo","vo","se","pe","par",
        }
        stop.discard("auth")
        stop.discard("login")
        stop.discard("github")

        words = [w.lower().strip("?.,!") for w in message.split()
                 if w.lower().strip("?.,!") not in stop and len(w) > 2]

        for word in words[:5]:
            try:
                order_clause = "ORDER BY CASE WHEN toLower(n.file_path) CONTAINS 'routes' THEN 0 ELSE 1 END" if has_routes_word else ""
                candidates = self.query(f"""
                    MATCH (n:CodeNode {{repo_id:$r, node_type:'file'}})
                    WHERE toLower(n.file_path) CONTAINS toLower($kw)
                       OR toLower(n.name) CONTAINS toLower($kw)
                    {order_clause}
                    RETURN n.file_path AS file LIMIT 1
                """, kw=word)
                if candidates:
                    return candidates[0]["file"]
            except Exception:
                pass

        # Priority 5 — function match
        for word in words[:5]:
            try:
                candidates = self.query("""
                    MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                    WHERE toLower(n.name) CONTAINS toLower($kw)
                    RETURN n.name AS name LIMIT 1
                """, kw=word)
                if candidates:
                    return candidates[0]["name"]
            except Exception:
                pass

        return ""

    def _collect_debug_data(self, target: str) -> Dict:
        """Neo4j se deep debug data nikalo."""

        # ── 1. Target node dhundho ────────────────────────────────────
        # Pehle exact match try karo
        _t = target
        node = self.query_one("""
            MATCH (n:CodeNode {repo_id:$r})
            WHERE n.file_path ENDS WITH $t
               OR n.file_path ENDS WITH $t_py
               OR n.file_path ENDS WITH $t_js
               OR n.file_path ENDS WITH $t_slash_py
               OR n.file_path ENDS WITH $t_slash
               OR n.file_path ENDS WITH $t_back_py
               OR n.name = $t
               OR toLower(n.name) = toLower($t)
            RETURN n.node_id   AS id,
                   n.name      AS name,
                   n.node_type AS type,
                   n.file_path AS file,
                   n.line_no   AS line
            ORDER BY
              CASE n.node_type
                WHEN 'file'     THEN 1
                WHEN 'class'    THEN 2
                WHEN 'function' THEN 3
                ELSE 4
              END
            LIMIT 1
        """,
            t          = _t,
            t_py       = _t + ".py",
            t_js       = _t + ".js",
            t_slash_py = "/" + _t + ".py",
            t_slash    = "/" + _t,
            t_back_py  = "\\" + _t + ".py",
        )

        # Exact match nahi mila toh CONTAINS try karo
        if not node:
            node = self.query_one("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE n.name CONTAINS $t
                   OR n.file_path CONTAINS $t
                RETURN n.node_id   AS id,
                       n.name      AS name,
                       n.node_type AS type,
                       n.file_path AS file,
                       n.line_no   AS line
                ORDER BY
                  CASE n.node_type
                    WHEN 'file'     THEN 1
                    WHEN 'class'    THEN 2
                    WHEN 'function' THEN 3
                    ELSE 4
                  END
                LIMIT 1
            """, t=target)

        if not node:
            return {"error": f"'{target}' graph mein nahi mila"}

        node_id   = node["id"]
        file_path = node["file"]

        # ── 2. Is file ke SAARE functions ────────────────────────────
        all_functions = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
            WHERE f.file_path = $fp
            OPTIONAL MATCH ()-[:DEPENDS_ON]->(f)
            WITH f, count(*) AS dependents
            RETURN f.name    AS name,
                   f.line_no AS line,
                   dependents
            ORDER BY dependents DESC
            LIMIT 30
        """, fp=file_path)

        # ── 3. Is file ke SAARE classes ──────────────────────────────
        all_classes = self.query("""
            MATCH (c:CodeNode {repo_id:$r, node_type:'class'})
            WHERE c.file_path = $fp
            RETURN c.name AS name, c.line_no AS line
            LIMIT 10
        """, fp=file_path)

        # ── 4. External callers — dusri files jo ise use karti hain ──
        external_callers = self.query("""
            MATCH (caller:CodeNode {repo_id:$r})
                  -[:DEPENDS_ON]->(n:CodeNode {node_id:$nid})
            WHERE caller.file_path <> $fp
            RETURN caller.name      AS name,
                   caller.file_path AS file,
                   caller.node_type AS type,
                   caller.line_no   AS line
            LIMIT 15
        """, nid=node_id, fp=file_path)

        # ── 5. Is node ki dependencies (kise call karta hai) ─────────
        dependencies = self.query("""
            MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
                  -[:DEPENDS_ON]->(dep:CodeNode {repo_id:$r})
            WHERE dep.file_path <> $fp
            RETURN dep.name      AS name,
                   dep.file_path AS file,
                   dep.node_type AS type
            LIMIT 15
        """, nid=node_id, fp=file_path)

        # ── 6. Blast radius — kitni files affected hongi ─────────────
        blast = self.query_one("""
            MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
            OPTIONAL MATCH (affected:CodeNode {repo_id:$r})
                           -[:DEPENDS_ON*1..3]->(n)
            WHERE affected.file_path <> $fp
            RETURN count(DISTINCT affected.file_path) AS affected_files,
                   count(DISTINCT affected)           AS affected_nodes
        """, nid=node_id, fp=file_path)

        # ── 7. Most depended-upon functions in this file ──────────────
        hotspot_funcs = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
            WHERE f.file_path = $fp
            MATCH (caller:CodeNode {repo_id:$r})
                  -[:DEPENDS_ON]->(f)
            WHERE caller.file_path <> $fp
            WITH f, count(DISTINCT caller) AS external_callers
            WHERE external_callers > 0
            RETURN f.name    AS name,
                   f.line_no AS line,
                   external_callers
            ORDER BY external_callers DESC
            LIMIT 10
        """, fp=file_path)

        # ── 8. Circular dependencies ──────────────────────────────────
        circular = self.query("""
            MATCH path = (n:CodeNode {node_id:$nid, repo_id:$r})
                         -[:DEPENDS_ON*2..5]->(n)
            WITH [nd IN nodes(path) | nd.name] AS cycle
            WHERE size(cycle) > 1
            RETURN cycle
            LIMIT 5
        """, nid=node_id)

        # ── 9. File risk level ────────────────────────────────────────
        file_node = self.query_one("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
            WHERE f.file_path = $fp
            OPTIONAL MATCH ()-[:DEPENDS_ON]->(f)
            WITH f, count(*) AS total_deps
            RETURN f.name      AS name,
                   total_deps  AS total_dependents,
                   CASE
                     WHEN total_deps > 30 THEN 'CRITICAL'
                     WHEN total_deps > 10 THEN 'HIGH'
                     WHEN total_deps > 3  THEN 'MEDIUM'
                     ELSE 'LOW'
                   END AS risk_level
        """, fp=file_path)

        # ── 10. Similar risky files in same module ────────────────────
        module_path = "/".join(file_path.replace("\\", "/").split("/")[:-1])
        similar_risky = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
            WHERE f.file_path CONTAINS $module
              AND f.file_path <> $fp
            OPTIONAL MATCH ()-[:DEPENDS_ON]->(f)
            WITH f, count(*) AS deps
            WHERE deps > 5
            RETURN f.file_path AS file, deps
            ORDER BY deps DESC
            LIMIT 5
        """, module=module_path, fp=file_path)

        return {
            "target":             target,
            "node":               node,
            "file_path":          file_path,
            "file_risk":          file_node or {},
            "total_functions":    len(all_functions),
            "all_functions":      all_functions,
            "all_classes":        all_classes,
            "external_callers":   external_callers,
            "dependencies":       dependencies,
            "hotspot_functions":  hotspot_funcs,
            "blast_radius": {
                "affected_files": blast["affected_files"] if blast else 0,
                "affected_nodes": blast["affected_nodes"] if blast else 0,
            },
            "circular_deps":      [c["cycle"] for c in circular],
            "has_circular_deps":  len(circular) > 0,
            "similar_risky_files_in_module": similar_risky,
            "analysis_note": (
                "Same-file function calls are NORMAL patterns. "
                "Focus on external dependencies and high dependent counts."
            ),
        }