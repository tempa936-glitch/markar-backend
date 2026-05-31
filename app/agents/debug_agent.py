"""
Debug Agent — "error kyun aa raha", "yeh kyun fail ho raha"
Root cause trace karo Neo4j se — deep analysis.
"""
"""
Debug Agent — "error kyun aa raha", "yeh kyun fail ho raha"
"""
from typing import Dict
from .base_agent import BaseAgent
from app.agents.deep_context_mixin import DeepContextMixin


class DebugAgent(DeepContextMixin, BaseAgent):

    SYSTEM_PROMPT = """
You are Markar AI — an elite debugging assistant with DIRECT access to the codebase via tools.

══════════════════════════════════════════════════════════
ABSOLUTE RULES — NEVER BREAK THESE
══════════════════════════════════════════════════════════
1. ALWAYS call tools FIRST — NEVER write answer before getting real code
2. NEVER mention any file, function, route, or line number not from tool results
3. NEVER hallucinate — if tool returns empty, say "not found in codebase"
4. NEVER give generic debugging advice — analyze ACTUAL code from tools
5. If ALL tool calls return empty — respond ONLY: "Not enough codebase data found"

══════════════════════════════════════════════════════════
QUESTION TYPE → MANDATORY TOOL SEQUENCE
══════════════════════════════════════════════════════════

BUG/ERROR IN FUNCTION:
  Step 1: search_nodes(function_name)
  Step 2: get_source_code(function_name)
  Step 3: get_callees(function_name) — what it calls
  Step 4: Analyze actual code — give YES/NO verdict with line references

FILE DEBUG (is X working):
  Step 1: search_nodes(file_keyword)
  Step 2: get_file_functions(file_path)
  Step 3: get_source_code for main/critical functions
  Step 4: get_callers for hotspot functions
  Step 5: Report issues found in actual code only

ERROR TRACE (why is X failing):
  Step 1: search_nodes(X)
  Step 2: get_source_code(X)
  Step 3: get_callees(X) — trace the call chain
  Step 4: get_source_code for each callee that could fail
  Step 5: Pinpoint exact line and reason

══════════════════════════════════════════════════════════
ANSWER STRUCTURE
══════════════════════════════════════════════════════════

**File Overview**
- Full file path (from tool result only)
- What this file does — exact responsibility
- Total functions found

**Functions Found**
ONLY what tools returned:
- functionName (line X) — what it does, params, returns
- What it calls internally (from get_callees result)
- Who calls it (from get_callers result)

**Code Flow**
Line X → calls Y() → which does Z → returns W
ONLY from actual source code returned by tools

**Problems Found**
For each problem:
- Severity: CRITICAL / HIGH / MEDIUM / LOW
- Exact location: file, function, line number (from tool result)
- Root cause — WHY is this a problem
- Fix — exact code change needed

If no problems: state "No issues detected" with evidence

**Blast Radius**
Which other functions/files break if this changes
ONLY from get_callers results

**Working Status**
YES / NO — with specific line-level evidence from tool results

**Fix Recommendations**
1. [CRITICAL] Fix X at line Y — exact change
2. [HIGH] Add error handling at line Z

══════════════════════════════════════════════════════════
STRICT RULES
══════════════════════════════════════════════════════════
- Always answer in English
- Line numbers MUST come from tool results — never guess
- No generic advice — every point must reference actual code
- Short answer = you missed something — be exhaustive
- Test files are normal — do not flag as CRITICAL
- CRITICAL only when 20+ functions depend on something
BUG/ERROR IN FUNCTION:
  Step 1: search_nodes(function_name)
  Step 2: get_source_code(function_name) — actual code padho
  Step 3: get_callees(function_name) — kya call karta hai
  Step 4: get_exception_paths(function_name) — exceptions check karo
  Step 5: get_complexity(function_name) — risk/complexity dekho
  Step 6: get_callers(function_name) — kaun use karta hai
  Step 7: get_blast_radius(function_name) — impact check karo
  Step 8: Answer with line-level evidence from ALL tool results

FILE DEBUG (is X working):
  Step 1: search_nodes(file_keyword)
  Step 2: get_file_functions(file_path)
  Step 3: get_source_code for EACH critical function (repeat)
  Step 4: get_exception_paths for EACH function
  Step 5: get_complexity for HIGH risk functions
  Step 6: get_callers for hotspot functions
  Step 7: get_blast_radius for most depended function
  Step 8: Report ALL issues found

TOOL USAGE POLICY:
- Always explore thoroughly. Call minimum 6 tools before final answer.
- Use search_nodes → get_source_code → get_callers → get_callees → get_file_functions etc.
- Never stop early. Depth is more important than speed.

ERROR TRACE (why is X failing):
  Step 1: search_nodes(X)
  Step 2: get_source_code(X)
  Step 3: get_callees(X)
  Step 4: get_source_code for EACH callee
  Step 5: get_exception_paths for each callee
  Step 6: get_api_route(X) — endpoint check karo
  Step 7: Pinpoint EXACT line and reason with fix
"""

    def run(self, user_message: str, target: str = None, model: str = None) -> Dict:
        tools = [
            {"name": "search_nodes", "description": "Search files/functions by keyword", "parameters": {"query": "string"}},
            {"name": "get_source_code", "description": "Get actual source code of a function", "parameters": {"function_name": "string"}},
            {"name": "get_file_functions", "description": "Get all functions in a file with line numbers", "parameters": {"file_path": "string"}},
            {"name": "get_callers", "description": "Who calls this function from other files", "parameters": {"function_name": "string"}},
            {"name": "get_callees", "description": "What does this function call internally", "parameters": {"function_name": "string"}},
            {"name": "get_exception_paths", "description": "Get all raises/exceptions in a function — uncaught errors", "parameters": {"function_name": "string"}},
            {"name": "get_complexity", "description": "Get cyclomatic complexity, nesting depth, risk level of a function", "parameters": {"function_name": "string"}},
            {"name": "get_blast_radius", "description": "If this function breaks, how many files/functions are affected", "parameters": {"function_name": "string"}},
            {"name": "get_api_route", "description": "Find which HTTP route/endpoint maps to this function", "parameters": {"query": "string"}},
        ]

        messages = [{"role": "user", "content": user_message}]
        all_files = set()
        all_funcs = set()
        MAX_TOOL_CALLS = 10

        for _ in range(MAX_TOOL_CALLS):
            llm_response = self._ask_with_tools(
                system_prompt=self.SYSTEM_PROMPT,
                messages=messages,
                tools=tools,
                model=model,
            )

            if not llm_response.get("tool_call"):
                return {
                    "answer": llm_response.get("content", ""),
                    "target": target or "",
                    "files":  list(all_files),
                    "agent":  "debug",
                }

            tool_name   = llm_response["tool_call"]["name"]
            tool_args   = llm_response["tool_call"]["arguments"]
            tool_result = self._execute_tool(tool_name, tool_args)

            if "file" in tool_result:
                all_files.add(tool_result["file"])
            if "function" in tool_result:
                all_funcs.add(tool_result["function"])

            messages.append({"role": "assistant", "content": f"[Tool: {tool_name}] {str(tool_args)}"})
            messages.append({"role": "user", "content": f"[Tool Result]: {str(tool_result)[:2000]}"})

        # Max calls hit
        final = self.ask_llm(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_message,
            graph_context={"tool_results": str(messages[-8:])},
            model=model,
        )
        return {"answer": final, "target": target or "", "files": list(all_files), "agent": "debug"}

    def _ask_with_tools(self, system_prompt, messages, tools, model=None) -> dict:
        tools_text = "\n".join([
            f"- {t['name']}({list(t['parameters'].keys())[0]}): {t['description']}"
            for t in tools
        ])
        full_system = system_prompt + f"""

AVAILABLE TOOLS:
{tools_text}

To call a tool respond ONLY with exactly this format:
TOOL: tool_name
ARG: value

If you have enough information to answer, give your final answer directly without TOOL: prefix."""

        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        history_context = {}
        if len(messages) > 1:
            history_context["conversation"] = "\n".join(
                f"{m['role'].upper()}: {m['content'][:500]}"
                for m in messages[:-1]
            )

        try:
            content = self.ask_llm(
                system_prompt=full_system,
                user_message=last_user_msg,
                graph_context=history_context,
                model=model,
                include_history=False,
                temperature=0.1,
                max_tokens=900,
            )
        except Exception as e:
            print(f"[DebugAgent] _ask_with_tools failed: {e}")
            return {"content": f"LLM call failed: {e}"}

        if not content:
            return {"content": "No response from LLM"}

        print(f"[DebugAgent] LLM raw: {content[:150]}")

        import re
        stripped = content.strip()
        match = re.search(r'TOOL:\s*(\w+)\s*\nARG:\s*(.+?)(?:\nTOOL:|$)', stripped, re.DOTALL)
        if match:
            tool_name = match.group(1).strip()
            arg_value = match.group(2).strip().split("\n")[0].strip()
            tool_def = next((t for t in tools if t["name"] == tool_name), None)
            if tool_def:
                arg_key = list(tool_def["parameters"].keys())[0]
                print(f"[DebugAgent] Tool call: {tool_name}({arg_key}={arg_value})")
                return {"tool_call": {"name": tool_name, "arguments": {arg_key: arg_value}}}
            print(f"[DebugAgent] Unknown tool: {tool_name}")

        return {"content": content}

    def _execute_tool(self, tool_name: str, args: dict) -> dict:
        import os

        if tool_name == "search_nodes":
            query = args.get("query", "")
            stop = {"the","a","an","in","is","or","not","and","of","to","for"}
            words = [w.lower().strip("?.,") for w in query.split()
                    if len(w) > 2 and w.lower() not in stop]
            if not words:
                words = [query.lower()]
            all_rows = []
            seen = set()
            for word in words[:4]:
                rows = self.query("""
                    MATCH (n:CodeNode {repo_id:$r})
                    WHERE n.node_type IN ['function','file']
                    AND (toLower(n.name) CONTAINS toLower($w)
                    OR  toLower(n.file_path) CONTAINS toLower($w))
                    RETURN n.name AS name, n.file_path AS file,
                        n.node_type AS type, n.line_no AS line
                    ORDER BY CASE n.node_type WHEN 'file' THEN 0 ELSE 1 END
                    LIMIT 8
                """, w=word)
                for r in rows:
                    key = f"{r['file']}:{r['name']}"
                    if key not in seen:
                        all_rows.append(r)
                        seen.add(key)
            return {"results": all_rows, "count": len(all_rows)}

        elif tool_name == "get_source_code":
            fname = args.get("function_name", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE toLower(n.name) CONTAINS toLower($fn) OR n.name = $fn
                RETURN n.name AS name, n.file_path AS file,
                    n.line_no AS line, n.deep_total_lines AS total_lines
                LIMIT 3
            """, fn=fname)
            if not rows:
                return {"error": f"Function '{fname}' not found"}
            repo_path = self._get_repo_path()
            results = []
            for row in rows:
                source = self._read_function_source(
                    repo_path, row.get("file",""), fname,
                    row.get("line") or 1, row.get("total_lines") or 30
                )
                results.append({"function": row["name"], "file": row["file"],
                            "line_start": row.get("line"), "source": source})
            return {"functions": results, "count": len(results)}

        elif tool_name == "get_callers":
            fname = args.get("function_name", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE toLower(n.name) CONTAINS toLower($fn)
                OR toLower(n.file_path) CONTAINS toLower($fn)
                MATCH (caller:CodeNode {repo_id:$r})-[:DEPENDS_ON]->(n)
                WHERE caller.file_path <> n.file_path
                RETURN DISTINCT caller.file_path AS file,
                    caller.name AS name, caller.line_no AS line
                ORDER BY caller.file_path LIMIT 20
            """, fn=fname)
            return {"callers": rows, "count": len(rows)}

        elif tool_name == "get_callees":
            fname = args.get("function_name", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE toLower(n.name) CONTAINS toLower($fn)
                MATCH (n)-[:DEPENDS_ON]->(callee:CodeNode {repo_id:$r})
                RETURN callee.name AS name, callee.file_path AS file,
                    callee.line_no AS line LIMIT 15
            """, fn=fname)
            return {"callees": rows, "count": len(rows)}

        elif tool_name == "get_file_functions":
            fpath = args.get("file_path", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE toLower(n.file_path) CONTAINS toLower($fp)
                RETURN n.name AS name, n.line_no AS line,
                    n.deep_risk_level AS risk, n.deep_complexity AS complexity,
                    n.deep_raises AS raises
                ORDER BY n.line_no LIMIT 30
            """, fp=fpath)
            repo_path = self._get_repo_path()
            file_source = ""
            if repo_path and rows:
                file_source = self._read_file_source(repo_path, rows[0].get("file") or fpath)
            return {"functions": rows, "count": len(rows),
                    "file_source": file_source[:2000] if file_source else ""}

        elif tool_name == "get_exception_paths":
            fname = args.get("function_name", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE toLower(n.name) CONTAINS toLower($fn)
                RETURN n.name AS name, n.file_path AS file,
                    n.deep_raises AS raises,
                    n.deep_has_try_except AS has_try,
                    n.deep_exception_count AS exc_count,
                    n.deep_risk_level AS risk,
                    n.deep_branch_paths AS branches
                LIMIT 3
            """, fn=fname)
            return {"exception_data": rows, "count": len(rows)}

        elif tool_name == "get_complexity":
            fname = args.get("function_name", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE toLower(n.name) CONTAINS toLower($fn)
                RETURN n.name AS name, n.file_path AS file,
                    n.deep_complexity AS complexity,
                    n.deep_max_depth AS nesting,
                    n.deep_logic_lines AS logic_lines,
                    n.deep_risk_level AS risk,
                    n.deep_risk_reasons AS risk_reasons,
                    n.deep_is_async AS is_async,
                    n.deep_always_returns AS always_returns
                LIMIT 3
            """, fn=fname)
            return {"complexity": rows, "count": len(rows)}

        elif tool_name == "get_blast_radius":
            fname = args.get("function_name", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE toLower(n.name) CONTAINS toLower($fn)
                OPTIONAL MATCH (affected:CodeNode {repo_id:$r})-[:DEPENDS_ON*1..3]->(n)
                RETURN n.name AS function, n.file_path AS file,
                    count(DISTINCT affected.file_path) AS affected_files,
                    count(DISTINCT affected) AS affected_nodes,
                    collect(DISTINCT affected.file_path)[..10] AS affected_file_list
                LIMIT 1
            """, fn=fname)
            return {"blast_radius": rows, "count": len(rows)}

        elif tool_name == "get_api_route":
            query = args.get("query", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE toLower(n.file_path) CONTAINS 'route'
                AND (toLower(n.name) CONTAINS toLower($q)
                OR toLower(n.file_path) CONTAINS toLower($q))
                RETURN n.name AS name, n.file_path AS file,
                    n.line_no AS line, n.deep_source_code AS source
                LIMIT 5
            """, q=query)
            return {"routes": rows, "count": len(rows)}

        return {"error": f"Unknown tool: {tool_name}"}

    def _get_repo_path(self) -> str:
        import os
        repo_path = getattr(self.store, "repo_path", None)
        if repo_path:
            return repo_path
        try:
            from app.services.repo_service import _jobs
            for job in _jobs.values():
                if job.get("repo_path"):
                    return job["repo_path"]
        except Exception:
            pass
        return os.getenv("MARKAR_REPO_PATH", "")

    def _read_function_source(self, repo_path, file_path, func_name, line_start, total_lines) -> str:
        import os, ast
        if not repo_path or not file_path:
            return "source not available"
        clean = file_path.replace("\\", os.sep).replace("/", os.sep)
        abs_path = os.path.join(repo_path, clean)
        if not os.path.exists(abs_path):
            abs_path = file_path
        if not os.path.exists(abs_path):
            return f"file not found: {file_path}"
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
            try:
                tree = ast.parse(source)
                lines = source.splitlines()
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if func_name.lower() in node.name.lower():
                            s = node.lineno - 1
                            e = getattr(node, "end_lineno", s + total_lines)
                            return f"lines {node.lineno}-{e}:\n" + "\n".join(lines[s:e])
            except Exception:
                pass
            lines = source.splitlines()
            start = max(0, line_start - 1)
            end = min(len(lines), start + (total_lines or 30))
            return "\n".join(f"{i+1}: {l}" for i, l in enumerate(lines[start:end], start=start))
        except Exception as e:
            return f"read error: {e}"

    def _read_file_source(self, repo_path, file_path) -> str:
        import os
        if not repo_path or not file_path:
            return ""
        clean = file_path.replace("\\", os.sep).replace("/", os.sep)
        abs_path = os.path.join(repo_path, clean)
        if not os.path.exists(abs_path):
            abs_path = file_path
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return ""

    # def _enrich_with_file_content(self, graph_data: Dict, target: str) -> Dict:
    #     """
    #     Agar graph mein functions/classes nahi mile toh actual file padhke
    #     real data inject karo — taaki LLM hallucinate na kare.
    #     """
    #     import ast, os, re

    #     # Graph mein meaningful data hai? Check karo
    #     has_functions = bool(graph_data.get("all_functions"))
    #     has_error     = "error" in graph_data

    #     file_path = graph_data.get("file_path", "")

    #     # File path nahi mila toh target se dhundho
    #     if not file_path and not has_error:
    #         file_path = target if target.endswith(".py") else ""

    #     if not file_path:
    #         repo_roots = []
            
    #         # 1. From RepoService _jobs
    #         try:
    #             from app.services.repo_service import _jobs
    #             for job in _jobs.values():
    #                 if job.get("repo_path"):
    #                     repo_roots.append(job["repo_path"])
    #         except ImportError:
    #             pass
            
    #         # 2. From env (fallback)
    #         env_repo = os.getenv("MARKAR_REPO_PATH", "")
    #         if env_repo and env_repo not in repo_roots:
    #             repo_roots.append(env_repo)

    #         for repo_root in repo_roots:
    #             if file_path:
    #                 break
    #             for root, _, files in os.walk(repo_root):
    #                 for f in files:
    #                     if f == target or f == f"{target}.py":
    #                         file_path = os.path.join(root, f)
    #                         break
    #                 if file_path:
    #                     break

    #     if not file_path or not os.path.isfile(file_path):
    #         # File nahi mili — graph data jo hai wahi use karo
    #         # LLM ko clearly batao ki file content available nahi
    #         if not has_functions:
    #             graph_data["_content_note"] = (
    #                 "File content disk pe available nahi hai aur graph mein "
    #                 "bhi detailed function list nahi hai. Sirf graph metadata "
    #                 "ke basis pe analysis karo. Functions invent mat karo."
    #             )
    #         return graph_data

    #     # ── File padhke real functions/classes extract karo ──────────────
    #     try:
    #         with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
    #             source = fh.read()

    #         tree = ast.parse(source)

    #         real_functions = []
    #         real_classes   = []

    #         for node in ast.walk(tree):
    #             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
    #                 real_functions.append({
    #                     "name": node.name,
    #                     "line": node.lineno,
    #                     "args": [a.arg for a in node.args.args],
    #                 })
    #             elif isinstance(node, ast.ClassDef):
    #                 methods = [
    #                     n.name for n in ast.walk(node)
    #                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    #                 ]
    #                 real_classes.append({
    #                     "name":    node.name,
    #                     "line":    node.lineno,
    #                     "methods": methods,
    #                 })

    #         # Graph data mein real info inject karo
    #         graph_data["_source_extracted"]       = True
    #         graph_data["real_functions_from_file"] = real_functions
    #         graph_data["real_classes_from_file"]   = real_classes
    #         graph_data["total_lines"]              = source.count("\n") + 1

    #         # Agar graph functions empty tha toh real se fill karo
    #         if not has_functions:
    #             graph_data["all_functions"] = [
    #                 {"name": f["name"], "line": f["line"], "dependents": 0}
    #                 for f in real_functions
    #             ]
    #             graph_data["all_classes"] = [
    #                 {"name": c["name"], "line": c["line"]}
    #                 for c in real_classes
    #             ]
    #             graph_data["_content_note"] = (
    #                 "Graph mein function details nahi the — "
    #                 "actual file parse karke real functions/classes inject kiye hain. "
    #                 "Sirf yahi functions exist karte hain, koi aur nahi."
    #             )

    #         # Source ka summarized snippet bhi do (first 3000 chars)
    #         graph_data["file_source_preview"] = source[:3000]

    #     except SyntaxError as e:
    #         graph_data["_parse_error"] = f"File parse nahi hui: {e}"
    #         graph_data["_content_note"] = (
    #             "File mein syntax error hai ya parse nahi hui. "
    #             "Sirf graph data ke basis pe analysis karo."
    #         )
    #     except Exception as e:
    #         graph_data["_content_note"] = f"File read failed: {e}. Graph data use karo."

    #     return graph_data

    # debug_agent.py mein sirf _find_target() method replace karo

    # def _find_target(self, message: str) -> str:
    #     import re
    #     msg_lower = message.lower()
    #     has_routes_word = "route" in msg_lower

    #     # Priority 1 — full file path with extension
    #     file_match = re.search(r'[\w/\\]+\.(py|js|ts|java|go|jsx|tsx|rs)', message)
    #     if file_match:
    #         return file_match.group(0)

    #     # Priority 2 — "routes me auth" pattern — routes/ path prefer karo
    #     route_match = re.search(r'routes?\s+(?:me|mein|ka|ki|ke)?\s*(\w+)', msg_lower)
    #     if route_match:
    #         name = route_match.group(1)
    #         if name not in {"me", "mein", "ka", "ki", "ke", "check", "file"}:
    #             try:
    #                 order_clause = "ORDER BY CASE WHEN toLower(n.file_path) CONTAINS 'routes' THEN 0 ELSE 1 END" if has_routes_word else ""
    #                 candidates = self.query(f"""
    #                     MATCH (n:CodeNode {{repo_id:$r, node_type:'file'}})
    #                     WHERE toLower(n.file_path) CONTAINS toLower($kw)
    #                     {order_clause}
    #                     RETURN n.file_path AS file LIMIT 3
    #                 """, kw=name)
    #                 if candidates:
    #                     return candidates[0]["file"]
    #             except Exception:
    #                 pass
    #             return name

    #     # Priority 3 — "auth file", "auth route" pattern
    #     file_kw_match = re.search(
    #         r'(\w+)\s+(?:file|route|routes|module|agent|service|class|function)', msg_lower
    #     )
    #     if file_kw_match:
    #         name = file_kw_match.group(1)
    #         skip = {"me","mein","is","the","a","an","check","koi","kuch","routes","yeh","jo"}
    #         if name not in skip and len(name) > 2:
    #             try:
    #                 order_clause = "ORDER BY CASE WHEN toLower(n.file_path) CONTAINS 'routes' THEN 0 ELSE 1 END" if has_routes_word else ""
    #                 candidates = self.query(f"""
    #                     MATCH (n:CodeNode {{repo_id:$r, node_type:'file'}})
    #                     WHERE toLower(n.file_path) CONTAINS toLower($kw)
    #                        OR toLower(n.name) CONTAINS toLower($kw)
    #                     {order_clause}
    #                     RETURN n.file_path AS file LIMIT 3
    #                 """, kw=name)
    #                 if candidates:
    #                     return candidates[0]["file"]
    #             except Exception:
    #                 pass
    #             return name

    #     # Priority 4 — meaningful words — graph mein dhundho
    #     stop = {
    #         "koi","bug","hay","hai","mein","kya","check","karo","dekho","is",
    #         "the","a","an","in","find","show","any","there","file","function",
    #         "code","error","issue","problem","debug","wala","wali","uska","iska",
    #         "yeh","yah","aur","bhi","kaise","kyun","kuch","sab","sirf","pura",
    #         "route","routes","agent","store","router","service","manager",
    #         "working","or","not","me","ka","ki","ke","wo","vo","se","pe","par",
    #     }
    #     stop.discard("auth")
    #     stop.discard("login")
    #     stop.discard("github")

    #     words = [w.lower().strip("?.,!") for w in message.split()
    #              if w.lower().strip("?.,!") not in stop and len(w) > 2]

    #     for word in words[:5]:
    #         try:
    #             order_clause = "ORDER BY CASE WHEN toLower(n.file_path) CONTAINS 'routes' THEN 0 ELSE 1 END" if has_routes_word else ""
    #             candidates = self.query(f"""
    #                 MATCH (n:CodeNode {{repo_id:$r, node_type:'file'}})
    #                 WHERE toLower(n.file_path) CONTAINS toLower($kw)
    #                    OR toLower(n.name) CONTAINS toLower($kw)
    #                 {order_clause}
    #                 RETURN n.file_path AS file LIMIT 1
    #             """, kw=word)
    #             if candidates:
    #                 return candidates[0]["file"]
    #         except Exception:
    #             pass

    #     # Priority 5 — function match
    #     for word in words[:5]:
    #         try:
    #             candidates = self.query("""
    #                 MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
    #                 WHERE toLower(n.name) CONTAINS toLower($kw)
    #                 RETURN n.name AS name LIMIT 1
    #             """, kw=word)
    #             if candidates:
    #                 return candidates[0]["name"]
    #         except Exception:
    #             pass

    #     return ""

    # def _collect_debug_data(self, target: str) -> Dict:
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