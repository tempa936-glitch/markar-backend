"""
Ask Agent — "X feature kahan hai", "Y function kya karta hai"
Neo4j se dhundho, actual file content padho, LLM se explain karo.
"""
from typing import Dict
from .base_agent import BaseAgent
from app.agents.deep_context_mixin import DeepContextMixin


class AskAgent(DeepContextMixin, BaseAgent):

    SYSTEM_PROMPT = """
You are Markar AI — an expert code intelligence assistant with DIRECT access to the codebase via tools.

══════════════════════════════════════════════════════════
ABSOLUTE RULES — NEVER BREAK THESE
══════════════════════════════════════════════════════════
1. ALWAYS call a tool FIRST — NEVER write answer before tool call
2. NEVER mention any file, function, route, or line number you did NOT get from a tool result
3. NEVER hallucinate — if tool returns empty, say "not found in codebase"
4. NEVER say "Would you like me to" — just do it
5. NEVER add closing remarks like "Key improvements made" or "This version maintains"
6. NEVER invent routes, functions, or files — only use what tools return
7. If tool returns 0 results — say exactly: "Not found in codebase via graph search"

══════════════════════════════════════════════════════════
QUESTION TYPE → MANDATORY TOOL SEQUENCE
══════════════════════════════════════════════════════════

FUNCTION DHUNDHNA (find/where is X):
  Step 1: search_nodes(X)
  Step 2: get_source_code(function_name) for top result
  Step 3: Answer with ONLY what tools returned

ARCHITECTURE SAMAJHNA (how does X work, explain X system):
  Step 1: search_nodes(X)
  Step 2: get_file_functions(file found in step 1)
  Step 3: get_source_code for main function
  Step 4: Answer with ONLY what tools returned

DEPENDENCY CHECK (what depends on X, what files use X, who calls X):
  Step 1: search_nodes(X)
  Step 2: get_callers(X) — MANDATORY for dependency questions
  Step 3: Answer listing ONLY files/functions returned by get_callers
  FORBIDDEN: listing files not returned by get_callers tool

BUG CHECK (is X working, any issues in X, verify X):
  Step 1: search_nodes(X)
  Step 2: get_source_code(main function)
  Step 3: get_callers(function) to check usage
  Step 4: Analyze ONLY the actual code returned — give YES/NO verdict

FLOW SAMAJHNA (how does X reach Y, trace execution of X):
  Step 1: search_nodes(entry point)
  Step 2: get_source_code(entry function)
  Step 3: get_callees(function) — trace what it calls
  Step 4: get_source_code for each callee in chain
  Step 5: Answer with exact line-by-line flow from tool results

══════════════════════════════════════════════════════════
ANSWER STRUCTURE
══════════════════════════════════════════════════════════

**Overview**
2-3 sentences — only facts from tool results

**Functions & Routes Found**
ONLY list what tools returned — exact file path, line number, parameters, return value

**Code Flow**
Line X → calls Y() → which does Z → returns W
ONLY from actual source code tool returned

**Dependencies & Connections**
ONLY from get_callers / get_callees results

**Issues Found**
Based on actual code only — no guessing

**Summary**
YES/NO — is it working, with evidence from code

If ALL tool calls return empty results, respond with ONLY:
"Not enough codebase data found to answer this question."
Do NOT guess or use general knowledge.

══════════════════════════════════════════════════════════
STRICT FORMATTING
══════════════════════════════════════════════════════════
- **Bold** for headings, file paths, function names
- Bullet points for lists
- functionName (line X) format — no backticks
- No truncation — complete information
- Always in English
"""

    # def run(self, user_message: str, model: str = None) -> Dict:
    #     """User ka question answer karo."""

    #     # Step 1 — Keywords nikalo
    #     keywords = self._extract_keywords(user_message)

    #     # Step 2 — Graph se search karo
    #     graph_data = self._search_graph(keywords)

    #     # Step 3 — Matched files ka actual content padho
    #     try:
    #         file_contents = self._read_matched_files(graph_data, user_message)
    #         if file_contents:
    #             graph_data["file_contents"] = file_contents
    #     except Exception as e:
    #         print(f"[AskAgent] File read failed (non-critical): {e}")

    #     # Step 4 — Deep AST context inject karo
    #     try:
    #         if graph_data.get("nodes"):
    #             # File match hua toh file summary, function match hua toh function context
    #             top_file = graph_data.get("files", [None])[0]
    #             top_funcs = graph_data.get("functions", [None])[:3]

    #             if top_file:
    #                 graph_data["deep_file_analysis"] = self._dq.file_deep_summary(top_file)
    #             if top_funcs:
    #                 combined = []
    #                 for fn in top_funcs:
    #                     ctx = self._dq.function_deep_context(fn, top_file)
    #                     if ctx and "nahi mila" not in ctx:
    #                         combined.append(ctx)
    #                 if combined:
    #                     graph_data["deep_function_analysis"] = "\n\n---\n\n".join(combined)
    #     except Exception as e:
    #         print(f"[AskAgent] Deep context failed (non-critical): {e}")

    #     # Step 5 — Agar kuch nahi mila
    #     if not graph_data["nodes"] and not graph_data.get("file_contents"):
    #         return {
    #             "answer": f"'{' '.join(keywords)}' se koi file ya function nahi mila. "
    #                       f"Doosre keywords try karo.",
    #             "files":     [],
    #             "functions": [],
    #         }

    #     # Step 6 — LLM ko graph + file content bhejo
    #     answer = self.ask_llm(
    #         system_prompt=self.SYSTEM_PROMPT,
    #         user_message=user_message,
    #         graph_context=graph_data,
    #         model=model,
    #     )

    #     return {
    #         "answer":    answer,
    #         "files":     graph_data.get("files", []),
    #         "functions": graph_data.get("functions", []),
    #         "agent":     "ask",
    #     }

    def run(self, user_message: str, model: str = None) -> Dict:
        """Tool-based approach — LLM khud decide kare kya fetch karna hai."""

        # Tools define karo
        tools = [
            {
                "name": "search_nodes",
                "description": "Search functions/files by keyword in name or file path",
                "parameters": {"query": "string"}
            },
            {
                "name": "get_source_code",
                "description": "Get actual source code of a specific function",
                "parameters": {"function_name": "string"}
            },
            {
                "name": "get_callers",
                "description": "Who calls this function — find all callers",
                "parameters": {"function_name": "string"}
            },
           {
                "name": "get_callees",
                "description": "What does this function call internally",
                "parameters": {"function_name": "string"}
            },
            {
                "name": "get_file_functions",
                "description": "Get all functions in a file with line numbers",
                "parameters": {"file_path": "string"}
            }
        ]
    

        # Tool execution loop
        messages = [{"role": "user", "content": user_message}]
        all_files = set()
        all_funcs = set()
        MAX_TOOL_CALLS = 5

        for _ in range(MAX_TOOL_CALLS):
            # LLM se next action lo
            llm_response = self._ask_with_tools(
                system_prompt=self.SYSTEM_PROMPT,
                messages=messages,
                tools=tools,
                model=model,
                
            )

            # Agar tool call nahi — final answer aa gaya
            if not llm_response.get("tool_call"):
                return {
                    "answer":    llm_response.get("content", ""),
                    "files":     list(all_files),
                    "functions": list(all_funcs),
                    "agent":     "ask",
                }

            # Tool execute karo
            tool_name = llm_response["tool_call"]["name"]
            tool_args = llm_response["tool_call"]["arguments"]
            tool_result = self._execute_tool(tool_name, tool_args)

            # Track files/functions
            if "file" in tool_result:
                all_files.add(tool_result["file"])
            if "function" in tool_result:
                all_funcs.add(tool_result["function"])

            # Messages mein add karo — history maintain karo
            messages.append({"role": "assistant", "content": f"[Tool: {tool_name}] {str(tool_args)}"})
            messages.append({"role": "user", "content": f"[Tool Result]: {str(tool_result)[:2000]}"})

        # Max calls hit — jo mila usse answer karo
        final = self.ask_llm(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_message,
            graph_context={"tool_results": str(messages[-6:])},
            model=model,
        )
        return {"answer": final, "files": list(all_files), "functions": list(all_funcs), "agent": "ask"}
    
    # ask_agent.py mein _ask_with_tools method replace karo

    def _ask_with_tools(self, system_prompt, messages, tools, model=None) -> dict:
        """LLM ko tools ke saath call karo."""

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

        # Latest user message nikalo
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        # Conversation history context banao
        history_context = {}
        if len(messages) > 1:
            history_context["conversation"] = "\n".join(
                f"{m['role'].upper()}: {m['content'][:2000]}"
                for m in messages[:-1]
            )

        try:
            content = self.ask_llm(
                system_prompt  = full_system,
                user_message   = last_user_msg,
                graph_context  = history_context,
                model          = model,
                include_history= False,
                temperature    = 0.1,
                max_tokens     = 500,
            )
        except Exception as e:
            print(f"[AskAgent] _ask_with_tools LLM call failed: {e}")
            return {"content": f"LLM call failed: {e}"}

        if not content:
            return {"content": "No response from LLM"}

        print(f"[AskAgent] LLM raw: {content[:150]}")

        # Tool call parse karo
        import re
        stripped = content.strip()
        match = re.search(
            r'TOOL:\s*(\w+)\s*\nARG:\s*(.+?)(?:\nTOOL:|$)',
            stripped, re.DOTALL
        )
        if match:
            tool_name = match.group(1).strip()
            arg_value = match.group(2).strip().split("\n")[0].strip()

            tool_def = next((t for t in tools if t["name"] == tool_name), None)
            if tool_def:
                arg_key = list(tool_def["parameters"].keys())[0]
                print(f"[AskAgent] Tool call: {tool_name}({arg_key}={arg_value})")
                return {
                    "tool_call": {
                        "name":      tool_name,
                        "arguments": {arg_key: arg_value},
                    }
                }
            else:
                print(f"[AskAgent] Unknown tool: {tool_name}")

        return {"content": content}
    

    # ask_agent.py mein sirf _execute_tool method replace karo

    def _execute_tool(self, tool_name: str, args: dict) -> dict:
        """Tool execute karo — Neo4j se data lo, disk se source code."""
        import os

        if tool_name == "search_nodes":
            query = args.get("query", "")
            # Har word alag search — SQL ILIKE jaisa
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
                    AND (toLower(n.name)      CONTAINS toLower($w)
                    OR  toLower(n.file_path) CONTAINS toLower($w))
                    RETURN n.name AS name, n.file_path AS file,
                        n.node_type AS type, n.line_no AS line
                    ORDER BY
                    CASE n.node_type WHEN 'file' THEN 0 ELSE 1 END
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
            # Neo4j se file path aur line number nikalo
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE toLower(n.name) CONTAINS toLower($fn)
                   OR n.name = $fn
                RETURN n.name AS name, n.file_path AS file,
                       n.line_no AS line,
                       n.deep_total_lines AS total_lines
                LIMIT 3
            """, fn=fname)

            if not rows:
                return {"error": f"Function '{fname}' not found in graph"}

            # Disk se actual source code padho
            repo_path = self._get_repo_path()
            results = []

            for row in rows:
                file_path  = row.get("file", "")
                line_start = row.get("line") or 1
                total_lines= row.get("total_lines") or 30

                source = self._read_function_source(
                    repo_path, file_path, fname, line_start, total_lines
                )
                results.append({
                    "function":   row["name"],
                    "file":       file_path,
                    "line_start": line_start,
                    "source":     source,
                })

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
                       caller.name AS name,
                       caller.line_no AS line
                ORDER BY caller.file_path
                LIMIT 20
            """, fn=fname)
            return {"callers": rows, "count": len(rows)}

        elif tool_name == "get_callees":
            fname = args.get("function_name", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE toLower(n.name) CONTAINS toLower($fn)
                MATCH (n)-[:DEPENDS_ON]->(callee:CodeNode {repo_id:$r})
                RETURN callee.name AS name, callee.file_path AS file,
                       callee.line_no AS line
                LIMIT 15
            """, fn=fname)
            return {"callees": rows, "count": len(rows)}

        elif tool_name == "get_file_functions":
            fpath = args.get("file_path", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE toLower(n.file_path) CONTAINS toLower($fp)
                RETURN n.name AS name, n.line_no AS line,
                       n.deep_risk_level AS risk,
                       n.deep_complexity  AS complexity,
                       n.deep_raises      AS raises
                ORDER BY n.line_no
                LIMIT 30
            """, fp=fpath)

            # File ka actual content bhi do (first 2000 chars)
            repo_path = self._get_repo_path()
            file_source = ""
            if repo_path and rows:
                actual_path = rows[0].get("file_path") or fpath
                file_source = self._read_file_source(repo_path, actual_path)

            return {
                "functions":   rows,
                "count":       len(rows),
                "file_source": file_source[:2000] if file_source else "",
            }

        return {"error": f"Unknown tool: {tool_name}"}

    def _get_repo_path(self) -> str:
        """Repo path nikalo — multiple sources se try karo."""
        import os
        # 1. Store se
        repo_path = getattr(self.store, "repo_path", None)
        if repo_path: return repo_path
        # 2. _jobs se
        try:
            from app.services.repo_service import _jobs
            for job in _jobs.values():
                if job.get("repo_path"):
                    return job["repo_path"]
        except Exception:
            pass
        # 3. Env
        return os.getenv("MARKAR_REPO_PATH", "")

    def _read_function_source(
        self, repo_path: str, file_path: str,
        func_name: str, line_start: int, total_lines: int
    ) -> str:
        """Disk se ek function ka source code padho."""
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

            # ast se exact function dhundho
            try:
                tree  = ast.parse(source)
                lines = source.splitlines()
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if func_name.lower() in node.name.lower():
                            s = node.lineno - 1
                            e = getattr(node, "end_lineno", s + total_lines)
                            func_src = "\n".join(lines[s:e])
                            return f"lines {node.lineno}-{e}:\n{func_src}"
            except Exception:
                pass

            # Fallback — line range se
            lines = source.splitlines()
            start = max(0, line_start - 1)
            end   = min(len(lines), start + (total_lines or 30))
            return "\n".join(
                f"{i+1}: {l}" for i, l in enumerate(lines[start:end], start=start)
            )

        except Exception as e:
            return f"read error: {e}"

    def _read_file_source(self, repo_path: str, file_path: str) -> str:
        """Poori file ka source padho."""
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
    
    
    
    
    
    
    
    
    
    def _read_matched_files(self, graph_data: dict, user_message: str) -> dict:
        """
        Matched files ka actual content padho — Neo4j se file path milta hai,
        disk se content. LLM ko actual code milega.
        """
        import os
        contents = {}

        # Repo path nikalo
        repo_path = getattr(self, "repo_path", None)
        if not repo_path:
            # store se try karo
            repo_path = getattr(self.store, "repo_path", None)
        if not repo_path:
            return contents

        files_to_read = graph_data.get("files", [])[:1]  # max 3 files

        for file_path in files_to_read:
            try:
                # Windows aur Unix dono handle karo
                clean_path = file_path.replace("\\", os.sep).replace("/", os.sep)
                abs_path = os.path.join(repo_path, clean_path)

                if not os.path.exists(abs_path):
                    # Direct try karo
                    abs_path = file_path

                if os.path.exists(abs_path):
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    # Max 3000 chars per file — LLM context limit
                    contents[file_path] = content[:3000]
                    if len(content) > 3000:
                        contents[file_path] += "\n... (file truncated)"

            except Exception as e:
                print(f"[AskAgent] Cannot read {file_path}: {e}")

        return contents

    def _extract_keywords(self, message: str) -> list:
        stop = {
            "kahan","hai","kya","kar","raha","mein","se","ka",
            "ki","ko","karo","where","is","the","a","an","in",
            "what","how","does","do","find","show","tell","me",
            "batao","dikhao","give","list","all","get","search",
            "kaunsa","konsa","kon","kis","kisiko","working","or",
            "not","check","routes","route","file","me","ek",
        }
        words = [w.lower().strip("?.,!") for w in message.split()
                 if w.lower().strip("?.,!") not in stop and len(w) > 2]
        return words[:6]

    def _search_graph(self, keywords: list) -> Dict:
        all_funcs = []
        all_files = []
        seen_ids  = set()

        for kw in keywords:
            if len(kw) < 2:
                continue

            funcs = self.query("""
                MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
                WHERE toLower(f.name) CONTAINS toLower($kw)
                   OR toLower(f.file_path) CONTAINS toLower($kw)
                RETURN f.node_id AS id, f.name AS name,
                       f.file_path AS file, f.line_no AS line
                LIMIT 10
            """, kw=kw)

            for fn in funcs:
                if fn["id"] not in seen_ids:
                    all_funcs.append(fn)
                    seen_ids.add(fn["id"])

            files = self.query("""
                MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
                WHERE toLower(f.file_path) CONTAINS toLower($kw)
                   OR toLower(f.name)      CONTAINS toLower($kw)
                RETURN f.node_id AS id, f.name AS name,
                       f.file_path AS file
                LIMIT 5
            """, kw=kw)

            for fl in files:
                if fl["id"] not in seen_ids:
                    all_files.append(fl)
                    seen_ids.add(fl["id"])

        connections = []
        if all_funcs:
            first_id = all_funcs[0]["id"]
            connections = self.query("""
                MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
                OPTIONAL MATCH (caller)-[:DEPENDS_ON]->(n)
                OPTIONAL MATCH (n)-[:DEPENDS_ON]->(callee)
                RETURN
                    collect(DISTINCT caller.name)[..5] AS callers,
                    collect(DISTINCT callee.name)[..5] AS callees
            """, nid=first_id)

        risk_keywords = {"critical","high","risk","risky","important","danger"}
        risk_data = []
        if any(kw in risk_keywords for kw in keywords):
            risk_data = self.query("""
                MATCH (file:CodeNode {repo_id:$r, node_type:'file'})
                OPTIONAL MATCH (file)-[:DEPENDS_ON]->(fn:CodeNode {node_type:'function'})
                WITH file, count(DISTINCT fn) AS fc
                WHERE fc > 15
                RETURN file.file_path AS file, fc AS function_count,
                       CASE
                           WHEN fc > 30 THEN 'High'
                           WHEN fc > 15 THEN 'Medium'
                           ELSE 'Low'
                       END AS risk
                ORDER BY fc DESC
                LIMIT 10
            """)
            for rf in risk_data:
                if rf["file"] not in seen_ids:
                    all_files.append({
                        "id":             rf["file"],
                        "name":           rf["file"].split("\\")[-1].split("/")[-1],
                        "file":           rf["file"],
                        "risk":           rf["risk"],
                        "function_count": rf["function_count"],
                    })
                    seen_ids.add(rf["file"])

        nodes = all_funcs + all_files

        return {
            "keywords":    keywords,
            "nodes":       nodes,
            "files":       [f["file"] for f in all_files],
            "functions":   [f["name"] for f in all_funcs],
            "connections": connections[0] if connections else {},
            "risk_files":  risk_data,
        }
        

    