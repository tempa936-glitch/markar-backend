# """
# Ask Agent — "X feature kahan hai", "Y function kya karta hai"
# Neo4j se dhundho, actual file content padho, LLM se explain karo.
# """
# from typing import Dict
# from .base_agent import BaseAgent
# from app.agents.deep_context_mixin import DeepContextMixin


# class AskAgent(DeepContextMixin, BaseAgent):

#     SYSTEM_PROMPT = """
# You are Markar AI — a code intelligence engine with DIRECT database access.

# ══════════════════════════════════════════════════════════
# IDENTITY
# ══════════════════════════════════════════════════════════
# You are NOT a general AI assistant.
# You are a SPECIALIZED CODE DATABASE QUERY ENGINE.
# You have NO knowledge of code except what tools return.
# You CANNOT guess. You CANNOT assume. You CANNOT invent.

# ══════════════════════════════════════════════════════════
# IRON LAW — ZERO EXCEPTIONS
# ══════════════════════════════════════════════════════════
# LAW 1: Every single fact in your answer MUST come from a tool result.
#         If you did not get it from a tool — it does not exist.

# LAW 2: Every file path, function name, line number MUST be copy-pasted
#         from tool output. Never type them from memory.

# LAW 3: If tool returns empty — say EXACTLY:
#         "Not found in codebase via graph search."
#         Do NOT explain. Do NOT suggest alternatives. Just that sentence.

# LAW 4: NEVER write your answer before calling ALL required tools.
#         Writing answer early = VIOLATION.

# LAW 5: NEVER add information that was not in tool results.
#         "It probably also calls X" = VIOLATION.
#         "This function likely returns Y" = VIOLATION.

# LAW 6: When source code is in tool result — READ EVERY LINE.
#         Quote exact function signatures, parameters, return values.
#         Do not paraphrase — be exact.

# ══════════════════════════════════════════════════════════
# TOOL CALLING RULES
# ══════════════════════════════════════════════════════════
# RULE 1: Call tools in sequence. Never skip steps.
# RULE 2: ONE tool per response. Wait for result. Then next tool.
# RULE 3: Use EXACT format — no deviation:

# TOOL: tool_name
# ARG: value

# RULE 4: ARG must be a SINGLE keyword — never a phrase.
#         CORRECT:   ARG: signup
#         INCORRECT: ARG: signup function auth

# RULE 5: After each tool result — decide next tool based on RESULT.
#         Do not pre-plan all tools upfront.

# ══════════════════════════════════════════════════════════
# MANDATORY TOOL SEQUENCES
# ══════════════════════════════════════════════════════════

# FIND FUNCTION (where is X, how does X work):
#   1. search_nodes → find exact file and function name
#   2. get_source_code → read actual implementation
#   3. get_callees → what it calls internally
#   4. Answer using ONLY lines from source code

# DEPENDENCY (what calls X, who uses X, called by):
#   MANDATORY SEQUENCE — NO SHORTCUTS:
#   1. search_nodes → find function
#   2. get_source_code → read implementation  
#   3. get_callers → YOU MUST CALL THIS — NEVER SKIP
#   4. get_callees → YOU MUST CALL THIS — NEVER SKIP
#   5. ONLY THEN write answer
  
#   IF YOU SKIP get_callers → YOUR ANSWER IS WRONG
#   IF YOU SKIP get_callees → YOUR ANSWER IS WRONG

# LAW 7: IF search_nodes returns 0 results OR empty_notice is present:
#     YOU MUST RESPOND EXACTLY:
#     "Not found in codebase via graph search."
#     NOTHING ELSE. No explanations. No generic answers.
#     NEVER use general knowledge about software architecture.  

#   IF search_nodes returns 0 results:
#   → Try get_file_functions with partial file name
#   → NEVER answer from general knowledge
#   → Say "Not found in codebase" if all tools return empty

# BUG CHECK (is X working, any issues):
#   1. search_nodes → find function
#   2. get_source_code → read actual code
#   3. get_callees → check what it calls
#   4. get_callers → check how it is used
#   5. Verdict: YES working / NO not working — with LINE NUMBERS as evidence

# FLOW TRACE (how does X reach Y):
#   1. search_nodes → find entry point
#   2. get_source_code → read entry function
#   3. get_callees → what it calls
#   4. get_source_code → read each callee
#   5. Repeat until full chain traced
#   6. Answer: Line A calls B() at line X → B calls C() at line Y → ...

# ══════════════════════════════════════════════════════════
# ANSWER FORMAT — MANDATORY
# ══════════════════════════════════════════════════════════

# **Overview**
# [2-3 sentences. Only facts from tool results. No interpretation.]

# **Functions Found**
# For each function from tool results:
# - FunctionName — file path (line X)
#   Parameters: [exact params from source code]
#   Returns: [exact return from source code]
#   Calls: [only from get_callees result]
#   Called by: [only from get_callers result]

# **Code Flow**
# [Trace from source code only]
# Line X: variable = function_call()
# Line Y: calls ExternalFunction(param1, param2)
# Line Z: returns result_dict

# **Issues Found**
# [Only if visible in actual source code]
# [If no issues visible: "No issues detected in returned source code."]

# **Summary**
# Working: YES / NO
# Evidence: [specific line numbers from source code]

# ══════════════════════════════════════════════════════════
# VIOLATIONS THAT WILL BREAK ACCURACY
# ══════════════════════════════════════════════════════════
# X Writing answer before all tools called
# X Mentioning files not returned by tools
# X Guessing parameter names
# X Saying "probably", "likely", "typically", "usually"
# X Adding general knowledge about OAuth, JWT, HTTP, etc
# X Truncating — always give complete information
# X Using backticks in response
# """

#     # def run(self, user_message: str, model: str = None) -> Dict:
#     #     """User ka question answer karo."""

#     #     # Step 1 — Keywords nikalo
#     #     keywords = self._extract_keywords(user_message)

#     #     # Step 2 — Graph se search karo
#     #     graph_data = self._search_graph(keywords)

#     #     # Step 3 — Matched files ka actual content padho
#     #     try:
#     #         file_contents = self._read_matched_files(graph_data, user_message)
#     #         if file_contents:
#     #             graph_data["file_contents"] = file_contents
#     #     except Exception as e:
#     #         print(f"[AskAgent] File read failed (non-critical): {e}")

#     #     # Step 4 — Deep AST context inject karo
#     #     try:
#     #         if graph_data.get("nodes"):
#     #             # File match hua toh file summary, function match hua toh function context
#     #             top_file = graph_data.get("files", [None])[0]
#     #             top_funcs = graph_data.get("functions", [None])[:3]

#     #             if top_file:
#     #                 graph_data["deep_file_analysis"] = self._dq.file_deep_summary(top_file)
#     #             if top_funcs:
#     #                 combined = []
#     #                 for fn in top_funcs:
#     #                     ctx = self._dq.function_deep_context(fn, top_file)
#     #                     if ctx and "nahi mila" not in ctx:
#     #                         combined.append(ctx)
#     #                 if combined:
#     #                     graph_data["deep_function_analysis"] = "\n\n---\n\n".join(combined)
#     #     except Exception as e:
#     #         print(f"[AskAgent] Deep context failed (non-critical): {e}")

#     #     # Step 5 — Agar kuch nahi mila
#     #     if not graph_data["nodes"] and not graph_data.get("file_contents"):
#     #         return {
#     #             "answer": f"'{' '.join(keywords)}' se koi file ya function nahi mila. "
#     #                       f"Doosre keywords try karo.",
#     #             "files":     [],
#     #             "functions": [],
#     #         }

#     #     # Step 6 — LLM ko graph + file content bhejo
#     #     answer = self.ask_llm(
#     #         system_prompt=self.SYSTEM_PROMPT,
#     #         user_message=user_message,
#     #         graph_context=graph_data,
#     #         model=model,
#     #     )

#     #     return {
#     #         "answer":    answer,
#     #         "files":     graph_data.get("files", []),
#     #         "functions": graph_data.get("functions", []),
#     #         "agent":     "ask",
#     #     }

#     def run(self, user_message: str, model: str = None) -> Dict:
#         """Tool-based approach — LLM khud decide kare kya fetch karna hai."""

#         # Tools define karo
#         tools = [
#             {
#                 "name": "search_nodes",
#                 "description": "Search functions/files by keyword in name or file path",
#                 "parameters": {"query": "string"}
#             },
#             {
#                 "name": "get_source_code",
#                 "description": "Get actual source code of a specific function",
#                 "parameters": {"function_name": "string"}
#             },
#             {
#                 "name": "get_callers",
#                 "description": "Who calls this function — find all callers",
#                 "parameters": {"function_name": "string"}
#             },
#             {
#                 "name": "get_callees",
#                 "description": "What does this function call internally",
#                 "parameters": {"function_name": "string"}
#             },
#             {
#                 "name": "get_file_functions",
#                 "description": "Get all functions in a file with line numbers",
#                 "parameters": {"file_path": "string"}
#             }
#         ]

#         # Tool execution loop
#         messages       = [{"role": "user", "content": user_message}]
#         all_files      = set()
#         all_funcs      = set()
#         MAX_TOOL_CALLS = 8
#         tools_called   = set()   # track karo kaunse tools call hue
#         last_func_name = None    # last function name save karo force inject ke liye

#         for _ in range(MAX_TOOL_CALLS):
#             # LLM se next action lo
#             llm_response = self._ask_with_tools(
#                 system_prompt=self.SYSTEM_PROMPT,
#                 messages=messages,
#                 tools=tools,
#                 model=model,
#             )

#             # Agar tool call nahi — final answer se PEHLE check karo
#             if not llm_response.get("tool_call"):

#                 # get_callers force karo agar nahi hua
#                 if "get_callers" not in tools_called and last_func_name:
#                     messages.append({
#                         "role":    "user",
#                         "content": f"[SYSTEM]: You MUST call get_callers tool for '{last_func_name}' before answering. Called by field cannot be empty.",
#                     })
#                     continue

#                 # get_callees force karo agar nahi hua
#                 if "get_callees" not in tools_called and last_func_name:
#                     messages.append({
#                         "role":    "user",
#                         "content": f"[SYSTEM]: You MUST call get_callees tool for '{last_func_name}' before answering. Calls field cannot be empty.",
#                     })
#                     continue

#                 return {
#                     "answer":    llm_response.get("content", ""),
#                     "files":     list(all_files),
#                     "functions": list(all_funcs),
#                     "agent":     "ask",
#                 }

#             # Tool execute karo
#             tool_name = llm_response["tool_call"]["name"]
#             tool_args = llm_response["tool_call"]["arguments"]
#             tools_called.add(tool_name)

#             # last function name track karo
#             if tool_name in ("search_nodes", "get_source_code"):
#                 val = list(tool_args.values())[0] if tool_args else None
#                 if val:
#                     last_func_name = val

#             tool_result = self._execute_tool(tool_name, tool_args)

#             if tool_name == "search_nodes" and tool_result.get("count", 0) == 0:
#                 query = tool_args.get("query", "")
#                 # File name se try karo
#                 broad = self._execute_tool("get_file_functions", {"file_path": query})
#                 if broad.get("count", 0) > 0:
#                     tool_result = broad
#                 else:
#                     return {
#                         "answer":    "Not found in codebase via graph search. Please ask about a specific file or function name.",
#                         "files":     [],
#                         "functions": [],
#                         "agent":     "ask",
#                     }

#             # Track files/functions
#             if "file" in tool_result:
#                 all_files.add(tool_result["file"])
#             if "function" in tool_result:
#                 all_funcs.add(tool_result["function"])

#             # Messages mein add karo — history maintain karo
#             messages.append({"role": "assistant", "content": f"[Tool: {tool_name}] {str(tool_args)}"})
#             messages.append({"role": "user",      "content": f"[Tool Result]: {str(tool_result)[:4000]}"})

#         # Max calls hit — jo mila usse answer karo
#         final = self.ask_llm(
#             system_prompt=self.SYSTEM_PROMPT,
#             user_message=user_message,
#             graph_context={"tool_results": str(messages[-6:])},
#             model=model,
#             max_tokens=3000,
#         )
#         return {"answer": final, "files": list(all_files), "functions": list(all_funcs), "agent": "ask"}
#     # ask_agent.py mein _ask_with_tools method replace karo

#     def _ask_with_tools(self, system_prompt, messages, tools, model=None) -> dict:
#         """LLM ko tools ke saath call karo."""

#         tools_text = "\n".join([
#             f"- {t['name']}({list(t['parameters'].keys())[0]}): {t['description']}"
#             for t in tools
#         ])

#         full_system = system_prompt + f"""

# AVAILABLE TOOLS:
# {tools_text}

# CRITICAL: When giving FINAL ANSWER:
# - Write COMPLETE detailed response
# - Include ALL steps from source code
# - Include ALL line numbers
# - Do NOT summarize — write everything

# To call a tool respond ONLY with exactly this format:
# TOOL: tool_name
# ARG: value

# If you have enough information to answer, give your final answer"""

#         # Latest user message nikalo
#         last_user_msg = ""
#         for m in reversed(messages):
#             if m.get("role") == "user":
#                 last_user_msg = m.get("content", "")
#                 break

#         # Conversation history context banao
#         history_context = {}
#         if len(messages) > 1:
#             history_context["conversation"] = "\n".join(
#                 f"{m['role'].upper()}: {m['content'][:2000]}"
#                 for m in messages[:-1]
#             )

#         try:
#             content = self.ask_llm(
#                 system_prompt  = full_system,
#                 user_message   = last_user_msg,
#                 graph_context  = history_context,
#                 model          = model,
#                 include_history= False,
#                 temperature    = 0.1,
#                 max_tokens     = 2000,
#             )
#         except Exception as e:
#             print(f"[AskAgent] _ask_with_tools LLM call failed: {e}")
#             return {"content": f"LLM call failed: {e}"}

#         if not content:
#             return {"content": "No response from LLM"}

#         print(f"[AskAgent] LLM raw: {content[:150]}")

#         # Tool call parse karo
#         import re
#         stripped = content.strip()
#         match = re.search(
#             r'TOOL:\s*(\w+)\s*\nARG:\s*(.+?)(?:\nTOOL:|$)',
#             stripped, re.DOTALL
#         )
#         if match:
#             tool_name = match.group(1).strip()
#             arg_value = match.group(2).strip().split("\n")[0].strip()

#             tool_def = next((t for t in tools if t["name"] == tool_name), None)
#             if tool_def:
#                 arg_key = list(tool_def["parameters"].keys())[0]
#                 print(f"[AskAgent] Tool call: {tool_name}({arg_key}={arg_value})")
#                 return {
#                     "tool_call": {
#                         "name":      tool_name,
#                         "arguments": {arg_key: arg_value},
#                     }
#                 }
#             else:
#                 print(f"[AskAgent] Unknown tool: {tool_name}")

#         return {"content": content}
    

#     # ask_agent.py mein sirf _execute_tool method replace karo

#     def _execute_tool(self, tool_name: str, args: dict) -> dict:
#         """Tool execute karo — Neo4j se data lo, disk se source code."""
#         import os

#         if tool_name == "search_nodes":
#             query = args.get("query", "")
#             # Har word alag search — SQL ILIKE jaisa
#             stop = {"the","a","an","in","is","or","not","and","of","to","for"}
#             words = [w.lower().strip("?.,") for w in query.split()
#                     if len(w) > 2 and w.lower() not in stop]
#             if not words:
#                 words = [query.lower()]

#             all_rows = []
#             seen = set()
#             for word in words[:4]:
#                 rows = self.query("""
#                     MATCH (n:CodeNode {repo_id:$r})
#                     WHERE n.node_type IN ['function','file']
#                     AND (toLower(n.name)      CONTAINS toLower($w)
#                     OR  toLower(n.file_path) CONTAINS toLower($w))
#                     RETURN n.name AS name, n.file_path AS file,
#                         n.node_type AS type, n.line_no AS line
#                     ORDER BY
#                     CASE n.node_type WHEN 'file' THEN 0 ELSE 1 END
#                     LIMIT 8
#                 """, w=word)
#                 for r in rows:
#                     key = f"{r['file']}:{r['name']}"
#                     if key not in seen:
#                         all_rows.append(r)
#                         seen.add(key)

#             return {"results": all_rows, "count": len(all_rows)}

#         elif tool_name == "get_source_code":
#             fname = args.get("function_name", "")
#             # Neo4j se file path aur line number nikalo
#             rows = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE toLower(n.name) CONTAINS toLower($fn)
#                    OR n.name = $fn
#                 RETURN n.name AS name, n.file_path AS file,
#                        n.line_no AS line,
#                        n.deep_total_lines AS total_lines
#                 LIMIT 3
#             """, fn=fname)

#             if not rows:
#                 return {"error": f"Function '{fname}' not found in graph"}

#             # Disk se actual source code padho
#             repo_path = self._get_repo_path()
#             results = []

#             for row in rows:
#                 file_path  = row.get("file", "")
#                 line_start = row.get("line") or 1
#                 total_lines= row.get("total_lines") or 30

#                 source = self._read_function_source(
#                     repo_path, file_path, fname, line_start, total_lines
#                 )
#                 results.append({
#                     "function":   row["name"],
#                     "file":       file_path,
#                     "line_start": line_start,
#                     "source":     source,
#                 })
#                 print(f"[get_source_code] results count: {len(results)}")

#             for r in results:
#                 print(f"[get_source_code] func={r['function']} file={r['file']} source_len={len(r.get('source',''))}")
#                 print(f"[get_source_code] source preview: {r.get('source','')[:200]}")   

#             return {"functions": results, "count": len(results)}

#         elif tool_name == "get_callers":
#             fname = args.get("function_name", "")
#             print(f"[get_callers] searching for: '{fname}' in repo: {self.repo_id}")
#             rows = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r})
#                 WHERE toLower(n.name) CONTAINS toLower($fn)
#                 MATCH (caller:CodeNode {repo_id:$r})-[:DEPENDS_ON*1..2]->(n)
#                 WHERE caller.name <> n.name
#                 AND caller.node_type IN ['file','class','function']
#                 RETURN DISTINCT
#                     caller.name      AS name,
#                     caller.file_path AS file,
#                     caller.line_no   AS line,
#                     caller.node_type AS type
#                 ORDER BY caller.file_path, caller.line_no
#                 LIMIT 25
#             """, fn=fname)
#             return {"callers": rows, "count": len(rows)}

#         elif tool_name == "get_callees":
#             fname = args.get("function_name", "")
#             rows = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r})
#                 WHERE toLower(n.name) CONTAINS toLower($fn)
#                 MATCH (n)-[:DEPENDS_ON*1..2]->(callee:CodeNode {repo_id:$r})
#                 WHERE callee.name <> n.name
#                 AND callee.node_type IN ['file','class','function']
#                 RETURN DISTINCT
#                     callee.name      AS name,
#                     callee.file_path AS file,
#                     callee.line_no   AS line,
#                     callee.node_type AS type
#                 ORDER BY callee.file_path, callee.line_no
#                 LIMIT 25
#             """, fn=fname)
#             return {"callees": rows, "count": len(rows)}

#         elif tool_name == "get_file_functions":
#             fpath = args.get("file_path", "")
#             rows = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE toLower(n.file_path) CONTAINS toLower($fp)
#                 RETURN n.name AS name, n.line_no AS line,
#                        n.deep_risk_level AS risk,
#                        n.deep_complexity  AS complexity,
#                        n.deep_raises      AS raises
#                 ORDER BY n.line_no
#                 LIMIT 30
#             """, fp=fpath)

#             # File ka actual content bhi do (first 2000 chars)
#             repo_path = self._get_repo_path()
#             file_source = ""
#             if repo_path and rows:
#                 actual_path = rows[0].get("file_path") or fpath
#                 file_source = self._read_file_source(repo_path, actual_path)

#             return {
#                 "functions":   rows,
#                 "count":       len(rows),
#                 "file_source": file_source[:2000] if file_source else "",
#             }

#         return {"error": f"Unknown tool: {tool_name}"}

#     def _get_repo_path(self) -> str:
#         """Repo path nikalo — multiple sources se try karo."""
#         import os
#         # 1. Store se
#         repo_path = getattr(self.store, "repo_path", None)
#         if repo_path: return repo_path
#         # 2. _jobs se
#         try:
#             from app.services.repo_service import _jobs
#             for job in _jobs.values():
#                 if job.get("repo_path"):
#                     return job["repo_path"]
#         except Exception:
#             pass
#         # 3. Env
#         return os.getenv("MARKAR_REPO_PATH", "")

#     def _read_function_source(
#         self, repo_path: str, file_path: str,
#         func_name: str, line_start: int, total_lines: int
#     ) -> str:
#         """Disk se ek function ka source code padho."""
#         import os, ast

#         if not repo_path or not file_path:
#             return "source not available"

#         clean = file_path.replace("\\", os.sep).replace("/", os.sep)
#         abs_path = os.path.join(repo_path, clean)
#         if not os.path.exists(abs_path):
#             abs_path = file_path
#         if not os.path.exists(abs_path):
#             return f"file not found: {file_path}"

#         try:
#             with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
#                 source = f.read()

#             # ast se exact function dhundho
#             try:
#                 tree  = ast.parse(source)
#                 lines = source.splitlines()
#                 for node in ast.walk(tree):
#                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
#                         clean_name = func_name.split(".")[-1]
#                         if node.name == clean_name or clean_name.lower() in node.name.lower():
#                             s = node.lineno - 1
#                             e = getattr(node, "end_lineno", s + total_lines)
#                             func_src = "\n".join(lines[s:e])
#                             return f"lines {node.lineno}-{e}:\n{func_src}"
#             except Exception:
#                 pass

#             # Fallback — line range se
#             lines = source.splitlines()
#             start = max(0, line_start - 1)
#             end   = min(len(lines), start + (total_lines or 30))
#             return "\n".join(
#                 f"{i+1}: {l}" for i, l in enumerate(lines[start:end], start=start)
#             )

#         except Exception as e:
#             return f"read error: {e}"

#     def _read_file_source(self, repo_path: str, file_path: str) -> str:
#         """Poori file ka source padho."""
#         import os
#         if not repo_path or not file_path:
#             return ""
#         clean = file_path.replace("\\", os.sep).replace("/", os.sep)
#         abs_path = os.path.join(repo_path, clean)
#         if not os.path.exists(abs_path):
#             abs_path = file_path
#         try:
#             with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
#                 return f.read()
#         except Exception:
#             return ""
    
    
    
    
    
    
    
    
    
#     def _read_matched_files(self, graph_data: dict, user_message: str) -> dict:
#         """
#         Matched files ka actual content padho — Neo4j se file path milta hai,
#         disk se content. LLM ko actual code milega.
#         """
#         import os
#         contents = {}

#         # Repo path nikalo
#         repo_path = getattr(self, "repo_path", None)
#         if not repo_path:
#             # store se try karo
#             repo_path = getattr(self.store, "repo_path", None)
#         if not repo_path:
#             return contents

#         files_to_read = graph_data.get("files", [])[:1]  # max 3 files

#         for file_path in files_to_read:
#             try:
#                 # Windows aur Unix dono handle karo
#                 clean_path = file_path.replace("\\", os.sep).replace("/", os.sep)
#                 abs_path = os.path.join(repo_path, clean_path)

#                 if not os.path.exists(abs_path):
#                     # Direct try karo
#                     abs_path = file_path

#                 if os.path.exists(abs_path):
#                     with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
#                         content = f.read()
#                     # Max 3000 chars per file — LLM context limit
#                     contents[file_path] = content[:3000]
#                     if len(content) > 3000:
#                         contents[file_path] += "\n... (file truncated)"

#             except Exception as e:
#                 print(f"[AskAgent] Cannot read {file_path}: {e}")

#         return contents

#     def _extract_keywords(self, message: str) -> list:
#         stop = {
#             "kahan","hai","kya","kar","raha","mein","se","ka",
#             "ki","ko","karo","where","is","the","a","an","in",
#             "what","how","does","do","find","show","tell","me",
#             "batao","dikhao","give","list","all","get","search",
#             "kaunsa","konsa","kon","kis","kisiko","working","or",
#             "not","check","routes","route","file","me","ek",
#         }
#         words = [w.lower().strip("?.,!") for w in message.split()
#                  if w.lower().strip("?.,!") not in stop and len(w) > 2]
#         return words[:6]

#     def _search_graph(self, keywords: list) -> Dict:
#         all_funcs = []
#         all_files = []
#         seen_ids  = set()

#         for kw in keywords:
#             if len(kw) < 2:
#                 continue

#             funcs = self.query("""
#                 MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE toLower(f.name) CONTAINS toLower($kw)
#                    OR toLower(f.file_path) CONTAINS toLower($kw)
#                 RETURN f.node_id AS id, f.name AS name,
#                        f.file_path AS file, f.line_no AS line
#                 LIMIT 10
#             """, kw=kw)

#             for fn in funcs:
#                 if fn["id"] not in seen_ids:
#                     all_funcs.append(fn)
#                     seen_ids.add(fn["id"])

#             files = self.query("""
#                 MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
#                 WHERE toLower(f.file_path) CONTAINS toLower($kw)
#                    OR toLower(f.name)      CONTAINS toLower($kw)
#                 RETURN f.node_id AS id, f.name AS name,
#                        f.file_path AS file
#                 LIMIT 5
#             """, kw=kw)

#             for fl in files:
#                 if fl["id"] not in seen_ids:
#                     all_files.append(fl)
#                     seen_ids.add(fl["id"])

#         connections = []
#         if all_funcs:
#             first_id = all_funcs[0]["id"]
#             connections = self.query("""
#                 MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
#                 OPTIONAL MATCH (caller)-[:DEPENDS_ON]->(n)
#                 OPTIONAL MATCH (n)-[:DEPENDS_ON]->(callee)
#                 RETURN
#                     collect(DISTINCT caller.name)[..5] AS callers,
#                     collect(DISTINCT callee.name)[..5] AS callees
#             """, nid=first_id)

#         risk_keywords = {"critical","high","risk","risky","important","danger"}
#         risk_data = []
#         if any(kw in risk_keywords for kw in keywords):
#             risk_data = self.query("""
#                 MATCH (file:CodeNode {repo_id:$r, node_type:'file'})
#                 OPTIONAL MATCH (file)-[:DEPENDS_ON]->(fn:CodeNode {node_type:'function'})
#                 WITH file, count(DISTINCT fn) AS fc
#                 WHERE fc > 15
#                 RETURN file.file_path AS file, fc AS function_count,
#                        CASE
#                            WHEN fc > 30 THEN 'High'
#                            WHEN fc > 15 THEN 'Medium'
#                            ELSE 'Low'
#                        END AS risk
#                 ORDER BY fc DESC
#                 LIMIT 10
#             """)
#             for rf in risk_data:
#                 if rf["file"] not in seen_ids:
#                     all_files.append({
#                         "id":             rf["file"],
#                         "name":           rf["file"].split("\\")[-1].split("/")[-1],
#                         "file":           rf["file"],
#                         "risk":           rf["risk"],
#                         "function_count": rf["function_count"],
#                     })
#                     seen_ids.add(rf["file"])

#         nodes = all_funcs + all_files

#         return {
#             "keywords":    keywords,
#             "nodes":       nodes,
#             "files":       [f["file"] for f in all_files],
#             "functions":   [f["name"] for f in all_funcs],
#             "connections": connections[0] if connections else {},
#             "risk_files":  risk_data,
#         }
        

    
# """
# Ask Agent — "X feature kahan hai", "Y function kya karta hai"
# Neo4j se dhundho, actual file content padho, LLM se explain karo.

# v2: Potpie ke best patterns add kiye —
#   - Pre-fetch context (run se pehle hi data load)
#   - Coverage check (complete hone pe tools skip)
#   - Async run + run_stream support
#   - File structure context injection
#   - Dynamic system prompt (context ke basis pe)
# """
# from typing import Dict, AsyncGenerator, Optional
# from .base_agent import BaseAgent
# from app.agents.deep_context_mixin import DeepContextMixin


# # ── Markers ────────────────────────────────────────────────────────────────────
# FILE_STRUCTURE_MARKER = "[[repo_structure_context_v1]]"
# FILE_STRUCTURE_HEADER = "File Structure of the project:\n"
# PREFETCH_MARKER       = "[[prefetch_context_v1]]"


# class AskAgent(DeepContextMixin, BaseAgent):

#     # ═══════════════════════════════════════════════════════════════════════════
#     # SYSTEM PROMPT  (Iron Laws — Markar ka core, unchanged)
#     # ═══════════════════════════════════════════════════════════════════════════
#     SYSTEM_PROMPT_BASE = """
# You are Markar AI — a code intelligence engine with DIRECT database access.

# ══════════════════════════════════════════════════════════
# IDENTITY
# ══════════════════════════════════════════════════════════
# You are NOT a general AI assistant.
# You are a SPECIALIZED CODE DATABASE QUERY ENGINE.
# You have NO knowledge of code except what tools return.
# You CANNOT guess. You CANNOT assume. You CANNOT invent.

# ══════════════════════════════════════════════════════════
# IRON LAW — ZERO EXCEPTIONS
# ══════════════════════════════════════════════════════════
# LAW 1: Every single fact in your answer MUST come from a tool result.
#         If you did not get it from a tool — it does not exist.

# LAW 2: Every file path, function name, line number MUST be copy-pasted
#         from tool output. Never type them from memory.

# LAW 3: If tool returns empty — say EXACTLY:
#         "Not found in codebase via graph search."
#         Do NOT explain. Do NOT suggest alternatives. Just that sentence.

# LAW 4: NEVER write your answer before calling ALL required tools.
#         Writing answer early = VIOLATION.

# LAW 5: NEVER add information that was not in tool results.
#         "It probably also calls X" = VIOLATION.
#         "This function likely returns Y" = VIOLATION.

# LAW 6: When source code is in tool result — READ EVERY LINE.
#         Quote exact function signatures, parameters, return values.
#         Do not paraphrase — be exact.

# ══════════════════════════════════════════════════════════
# TOOL CALLING RULES
# ══════════════════════════════════════════════════════════
# RULE 1: Call tools in sequence. Never skip steps.
# RULE 2: ONE tool per response. Wait for result. Then next tool.
# RULE 3: Use EXACT format — no deviation:

# TOOL: tool_name
# ARG: value

# RULE 4: ARG must be a SINGLE keyword — never a phrase.
#         CORRECT:   ARG: signup
#         INCORRECT: ARG: signup function auth

# RULE 5: After each tool result — decide next tool based on RESULT.
#         Do not pre-plan all tools upfront.

# ══════════════════════════════════════════════════════════
# MANDATORY TOOL SEQUENCES
# ══════════════════════════════════════════════════════════

# FIND FUNCTION (where is X, how does X work):
#   1. search_nodes → find exact file and function name
#   2. get_source_code → read actual implementation
#   3. get_callees → what it calls internally
#   4. Answer using ONLY lines from source code

# DEPENDENCY (what calls X, who uses X, called by):
#   MANDATORY SEQUENCE — NO SHORTCUTS:
#   1. search_nodes → find function
#   2. get_source_code → read implementation
#   3. get_callers → YOU MUST CALL THIS — NEVER SKIP
#   4. get_callees → YOU MUST CALL THIS — NEVER SKIP
#   5. ONLY THEN write answer

#   IF YOU SKIP get_callers → YOUR ANSWER IS WRONG
#   IF YOU SKIP get_callees → YOUR ANSWER IS WRONG

# LAW 7: IF search_nodes returns 0 results OR empty_notice is present:
#     YOU MUST RESPOND EXACTLY:
#     "Not found in codebase via graph search."
#     NOTHING ELSE. No explanations. No generic answers.
#     NEVER use general knowledge about software architecture.

#   IF search_nodes returns 0 results:
#   → Try get_file_functions with partial file name
#   → NEVER answer from general knowledge
#   → Say "Not found in codebase" if all tools return empty

# BUG CHECK (is X working, any issues):
#   1. search_nodes → find function
#   2. get_source_code → read actual code
#   3. get_callees → check what it calls
#   4. get_callers → check how it is used
#   5. Verdict: YES working / NO not working — with LINE NUMBERS as evidence

# FLOW TRACE (how does X reach Y):
#   1. search_nodes → find entry point
#   2. get_source_code → read entry function
#   3. get_callees → what it calls
#   4. get_source_code → read each callee
#   5. Repeat until full chain traced
#   6. Answer: Line A calls B() at line X → B calls C() at line Y → ...

# ══════════════════════════════════════════════════════════
# ANSWER FORMAT — MANDATORY
# ══════════════════════════════════════════════════════════

# **Overview**
# [2-3 sentences. Only facts from tool results. No interpretation.]

# **Functions Found**
# For each function from tool results:
# - FunctionName — file path (line X)
#   Parameters: [exact params from source code]
#   Returns: [exact return from source code]
#   Calls: [only from get_callees result]
#   Called by: [from get_callers result]
#     - If get_callers returns empty list OR note says "entry-point" →
#       write exactly: "Entry-point — called externally (HTTP/CLI/scheduler)"
#     - NEVER write "Not found in codebase" for Called by field
#     - NEVER leave Called by blank

# **Code Flow**
# [Trace from source code only]
# Line X: variable = function_call()
# Line Y: calls ExternalFunction(param1, param2)
# Line Z: returns result_dict

# ...
# PREFETCH OVERRIDE — ABSOLUTE LAW:
# IF question contains "who calls" OR "called by" OR "caller" OR "kaun call":
# → PREFETCH DATA MEIN JO BHI CALLERS HAIN — IGNORE KARO
# → get_callers TOOL CALL KARNA MANDATORY HAI
# → Prefetch se caller answer DENA = SEVERE VIOLATION
# ...

# **Issues Found**
# [Only if visible in actual source code]
# [If no issues visible: "No issues detected in returned source code."]

# **Summary**
# Working: YES / NO
# Evidence: [specific line numbers from source code]

# ══════════════════════════════════════════════════════════
# VIOLATIONS THAT WILL BREAK ACCURACY
# ══════════════════════════════════════════════════════════
# X Writing answer before all tools called
# X Mentioning files not returned by tools
# X Guessing parameter names
# X Saying "probably", "likely", "typically", "usually"
# X Adding general knowledge about OAuth, JWT, HTTP, etc
# X Truncating — always give complete information
# X Using backticks in response
# """

#     # ── POTPIE-INSPIRED: Context-aware system prompt ────────────────────────────
#     SYSTEM_PROMPT_WITH_PREFETCH = SYSTEM_PROMPT_BASE + """

# ══════════════════════════════════════════════════════════
# PREFETCH CONTEXT PROTOCOL  (HIGHEST PRIORITY)
# ══════════════════════════════════════════════════════════
# Additional Context mein PREFETCHED DATA available hai.

# COVERAGE = COMPLETE:
#   → Answer DIRECTLY from prefetched data.
#   → Tool calls ONLY agar actual source code dikhana ho.
#   → get_callers / get_callees MAT bulao — data already hai.

# COVERAGE = PARTIAL:
#   → Jo data hai use karo.
#   → Sirf missing parts ke liye tools call karo.

# COVERAGE = NONE:
#   → Normal tool sequence follow karo (upar wale rules).
# """

#     # ═══════════════════════════════════════════════════════════════════════════
#     # POTPIE-INSPIRED: Pre-fetch context before LLM call
#     # ═══════════════════════════════════════════════════════════════════════════

#     def _prefetch_context(self, user_message: str) -> Dict:
#         """
#         Run se pehle hi relevant nodes + file structure fetch karo.
#         Agar milta hai → tools ki zaroorat kam hogi (coverage = COMPLETE / PARTIAL).
#         Agar nahi milta → coverage = NONE → normal tool loop.
#         """
#         prefetch = {
#             "coverage":       "NONE",
#             "nodes":          [],
#             "file_structure": "",
#             "source_snippets": {},
#         }

#         try:
#             # 1. Keywords se quick node search
#             keywords = self._extract_keywords(user_message)
#             graph_data = self._search_graph(keywords)
#             nodes = graph_data.get("nodes", [])

#             if not nodes:
#                 return prefetch

#             prefetch["nodes"] = nodes[:5]

#             # 2. Top function ka source code bhi pre-fetch karo
#             repo_path = self._get_repo_path()
#             top_funcs = graph_data.get("functions", [])[:2]

#             for fn_name in top_funcs:
#                 rows = self.query("""
#                     MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                     WHERE n.name = $fn
#                     RETURN n.file_path AS file, n.line_no AS line,
#                            n.deep_total_lines AS total_lines
#                     LIMIT 1
#                 """, fn=fn_name)
#                 if rows:
#                     r = rows[0]
#                     src = self._read_function_source(
#                         repo_path, r["file"], fn_name,
#                         r.get("line") or 1, r.get("total_lines") or 30
#                     )
#                     if src and "not found" not in src and "error" not in src:
#                         prefetch["source_snippets"][fn_name] = {
#                             "file":   r["file"],
#                             "source": src,
#                         }

#             # 3. File structure (repo overview)
#             try:
#                 prefetch["file_structure"] = self._get_file_structure()
#             except Exception:
#                 pass

#             # 4. Coverage decide karo
#             # COMPLETE sirf tab jab fetched snippets question se actually match kare
#             # Warna PARTIAL → tool loop chalta hai
#             if prefetch["source_snippets"]:
#                 # Check karo — kya fetched functions question ke keywords se match karte hain?
#                 question_lower = user_message.lower()
#                 snippets_relevant = any(
#                     fn_name.lower() in question_lower or
#                     any(kw in fn_name.lower() for kw in keywords)
#                     for fn_name in prefetch["source_snippets"].keys()
#                 )
#                 if snippets_relevant:
#                     prefetch["coverage"] = "COMPLETE"
#                 else:
#                     # Snippets hain lekin question se match nahi — tool loop zaroori hai
#                     prefetch["coverage"] = "PARTIAL"
#             elif prefetch["nodes"]:
#                 prefetch["coverage"] = "PARTIAL"

#         except Exception as e:
#             print(f"[AskAgent] prefetch failed (non-critical): {e}")

#         return prefetch

#     def _get_file_structure(self) -> str:
#         """Repo ka top-level file/folder structure string banao."""
#         import os
#         repo_path = self._get_repo_path()
#         if not repo_path or not os.path.exists(repo_path):
#             return ""

#         lines = []
#         for root, dirs, files in os.walk(repo_path):
#             # Hidden folders skip karo
#             dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
#             depth = root.replace(repo_path, "").count(os.sep)
#             if depth > 2:           # sirf 2 levels deep
#                 continue
#             indent = "  " * depth
#             folder = os.path.basename(root)
#             lines.append(f"{indent}{folder}/")
#             sub = "  " * (depth + 1)
#             for f in files[:10]:   # max 10 files per folder
#                 lines.append(f"{sub}{f}")
#         return "\n".join(lines[:80])   # max 80 lines

#     def _build_prefetch_context_string(self, prefetch: Dict) -> str:
#         """Prefetch data ko readable string mein convert karo."""
#         if prefetch["coverage"] == "NONE":
#             return ""

#         parts = [f"\n{PREFETCH_MARKER}"]
#         parts.append(f"COVERAGE: {prefetch['coverage']}")

#         if prefetch["nodes"]:
#             parts.append("\nNodes Found:")
#             for n in prefetch["nodes"]:
#                 parts.append(f"  - {n.get('name')} ({n.get('type','?')}) @ {n.get('file')} line {n.get('line','?')}")

#         if prefetch["source_snippets"]:
#             parts.append("\nSource Snippets:")
#             for fn_name, data in prefetch["source_snippets"].items():
#                 parts.append(f"\n  [{fn_name}] — {data['file']}")
#                 # First 800 chars of source
#                 parts.append("  " + data["source"][:800].replace("\n", "\n  "))

#         if prefetch["file_structure"]:
#             parts.append(f"\n{FILE_STRUCTURE_MARKER}")
#             parts.append(FILE_STRUCTURE_HEADER)
#             parts.append(prefetch["file_structure"])

#         return "\n".join(parts)

#     # ═══════════════════════════════════════════════════════════════════════════
#     # POTPIE-INSPIRED: Dynamic system prompt based on coverage
#     # ═══════════════════════════════════════════════════════════════════════════

#     def _get_system_prompt(self, coverage: str) -> str:
#         if coverage in ("COMPLETE", "PARTIAL"):
#             return self.SYSTEM_PROMPT_WITH_PREFETCH
#         return self.SYSTEM_PROMPT_BASE

#     # ═══════════════════════════════════════════════════════════════════════════
#     # MAIN RUN  (sync — original Markar style, now with pre-fetch)
#     # ═══════════════════════════════════════════════════════════════════════════

#     def run(self, user_message: str, model: str = None) -> Dict:
#         """Tool-based approach — prefetch pehle, phir LLM tool loop."""

#         # ── STEP 0: Pre-fetch (Potpie se liya) ─────────────────────────────────
#         prefetch        = self._prefetch_context(user_message)
#         prefetch_string = self._build_prefetch_context_string(prefetch)
#         system_prompt   = self._get_system_prompt(prefetch["coverage"])

#         print(f"[AskAgent] prefetch coverage={prefetch['coverage']} "
#               f"nodes={len(prefetch['nodes'])} "
#               f"snippets={len(prefetch['source_snippets'])}")

#         # ── STEP 1: COMPLETE coverage → direct answer, no tool loop ────────────
#         # Sirf simple factual questions pe direct answer — "where is X", "what is X"
#         # Dependency / flow / caller questions pe ALWAYS tool loop
#         simple_question = not any(
#             kw in user_message.lower()
#             for kw in ["who calls", "caller", "called by", "flow", "how does",
#                        "trace", "reach", "supervisor", "explain", "architecture",
#                        "connect", "kaise", "kaun", "dependency", "callers"]
#         )

#         if prefetch["coverage"] == "COMPLETE" and simple_question:
#             answer = self.ask_llm(
#                 system_prompt=system_prompt,
#                 user_message=user_message,
#                 graph_context={"prefetch_context": prefetch_string},
#                 model=model,
#                 max_tokens=3000,
#             )
#             return {
#                 "answer":    answer,
#                 "files":     [s["file"] for s in prefetch["source_snippets"].values()],
#                 "functions": list(prefetch["source_snippets"].keys()),
#                 "agent":     "ask",
#                 "coverage":  "COMPLETE",
#             }

#         # ── STEP 2: PARTIAL / NONE / complex question → tool loop ──────────────
#         tools = self._define_tools()

#         # Prefetch data ko initial context mein inject karo
#         initial_user_msg = user_message
#         if prefetch_string:
#             initial_user_msg = (
#                 f"{user_message}\n\n"
#                 f"[Additional Context from prefetch]:\n{prefetch_string}"
#             )

#         messages       = [{"role": "user", "content": initial_user_msg}]
#         all_files      = set()
#         all_funcs      = set()
#         MAX_TOOL_CALLS = 8
#         tools_called   = set()
#         last_func_name = None

#         for _ in range(MAX_TOOL_CALLS):
#             llm_response = self._ask_with_tools(
#                 system_prompt=system_prompt,
#                 messages=messages,
#                 tools=tools,
#                 model=model,
#             )

#             if not llm_response.get("tool_call"):
#                 # Force get_callers agar nahi hua (original Markar enforcement)
#                 if "get_callers" not in tools_called and last_func_name:
#                     messages.append({
#                         "role":    "user",
#                         "content": (
#                             f"[SYSTEM]: You MUST call get_callers tool for '{last_func_name}' before answering. "
#                             f"If get_callers returns empty or a note saying entry-point/external — "
#                             f"that IS a valid result. Write 'Called by: Entry-point — called externally (HTTP/CLI/scheduler)' "
#                             f"and proceed to answer."
#                         ),
#                     })
#                     continue

#                 if "get_callees" not in tools_called and last_func_name:
#                     messages.append({
#                         "role":    "user",
#                         "content": f"[SYSTEM]: You MUST call get_callees tool for '{last_func_name}' before answering. Calls field cannot be empty.",
#                     })
#                     continue

#                 return {
#                     "answer":    llm_response.get("content", ""),
#                     "files":     list(all_files),
#                     "functions": list(all_funcs),
#                     "agent":     "ask",
#                     "coverage":  prefetch["coverage"],
#                 }

#             tool_name = llm_response["tool_call"]["name"]
#             tool_args = llm_response["tool_call"]["arguments"]
#             tools_called.add(tool_name)

#             if tool_name in ("search_nodes", "get_source_code"):
#                 val = list(tool_args.values())[0] if tool_args else None
#                 if val:
#                     last_func_name = val

#             tool_result = self._execute_tool(tool_name, tool_args)

#             # search_nodes empty → get_file_functions try karo (original logic)
#             if tool_name == "search_nodes" and tool_result.get("count", 0) == 0:
#                 query = tool_args.get("query", "")
#                 broad = self._execute_tool("get_file_functions", {"file_path": query})
#                 if broad.get("count", 0) > 0:
#                     tool_result = broad
#                 else:
#                     return {
#                         "answer":    "Not found in codebase via graph search. Please ask about a specific file or function name.",
#                         "files":     [],
#                         "functions": [],
#                         "agent":     "ask",
#                         "coverage":  "NONE",
#                     }

#             if "file" in tool_result:
#                 all_files.add(tool_result["file"])
#             if "function" in tool_result:
#                 all_funcs.add(tool_result["function"])

#             messages.append({"role": "assistant", "content": f"[Tool: {tool_name}] {str(tool_args)}"})
#             messages.append({"role": "user",      "content": f"[Tool Result]: {str(tool_result)[:4000]}"})

#         # Max calls hit
#         final = self.ask_llm(
#             system_prompt=system_prompt,
#             user_message=user_message,
#             graph_context={"tool_results": str(messages[-6:])},
#             model=model,
#             max_tokens=3000,
#         )
#         return {
#             "answer":    final,
#             "files":     list(all_files),
#             "functions": list(all_funcs),
#             "agent":     "ask",
#             "coverage":  prefetch["coverage"],
#         }

#     # ═══════════════════════════════════════════════════════════════════════════
#     # POTPIE-INSPIRED: Async run + run_stream
#     # ═══════════════════════════════════════════════════════════════════════════

#     async def run_async(self, user_message: str, model: str = None) -> Dict:
#         """Async version — same logic, await-friendly."""
#         import asyncio
#         loop = asyncio.get_event_loop()
#         return await loop.run_in_executor(None, lambda: self.run(user_message, model))

#     async def run_stream(
#         self, user_message: str, model: str = None
#     ) -> AsyncGenerator[str, None]:
#         """
#         Streaming version — prefetch pehle karo, phir LLM streaming response do.
#         Agar base agent mein streaming support nahi — chunk-by-chunk simulate karo.
#         """
#         # Prefetch sync mein
#         prefetch        = self._prefetch_context(user_message)
#         prefetch_string = self._build_prefetch_context_string(prefetch)
#         system_prompt   = self._get_system_prompt(prefetch["coverage"])

#         # Try to use native streaming if available
#         if hasattr(self, "ask_llm_stream"):
#             graph_context = {"prefetch_context": prefetch_string} if prefetch_string else {}
#             async for chunk in self.ask_llm_stream(
#                 system_prompt=system_prompt,
#                 user_message=user_message,
#                 graph_context=graph_context,
#                 model=model,
#             ):
#                 yield chunk
#         else:
#             # Fallback: run sync, yield complete answer
#             result = self.run(user_message, model)
#             yield result.get("answer", "")

#     # ═══════════════════════════════════════════════════════════════════════════
#     # TOOLS DEFINITION (extracted to method for clarity)
#     # ═══════════════════════════════════════════════════════════════════════════

#     def _define_tools(self) -> list:
#         return [
#             {
#                 "name":        "search_nodes",
#                 "description": "Search functions/files by keyword in name or file path",
#                 "parameters":  {"query": "string"},
#             },
#             {
#                 "name":        "get_source_code",
#                 "description": "Get actual source code of a specific function",
#                 "parameters":  {"function_name": "string"},
#             },
#             {
#                 "name":        "get_callers",
#                 "description": "Who calls this function — find all callers",
#                 "parameters":  {"function_name": "string"},
#             },
#             {
#                 "name":        "get_callees",
#                 "description": "What does this function call internally",
#                 "parameters":  {"function_name": "string"},
#             },
#             {
#                 "name":        "get_file_functions",
#                 "description": "Get all functions in a file with line numbers",
#                 "parameters":  {"file_path": "string"},
#             },
#         ]

#     # ═══════════════════════════════════════════════════════════════════════════
#     # _ask_with_tools  (original Markar — unchanged)
#     # ═══════════════════════════════════════════════════════════════════════════

#     def _ask_with_tools(self, system_prompt, messages, tools, model=None) -> dict:
#         """LLM ko tools ke saath call karo."""

#         tools_text = "\n".join([
#             f"- {t['name']}({list(t['parameters'].keys())[0]}): {t['description']}"
#             for t in tools
#         ])

#         full_system = system_prompt + f"""

# AVAILABLE TOOLS:
# {tools_text}

# CRITICAL: When giving FINAL ANSWER:
# - Write COMPLETE detailed response
# - Include ALL steps from source code
# - Include ALL line numbers
# - Do NOT summarize — write everything

# To call a tool respond ONLY with exactly this format:
# TOOL: tool_name
# ARG: value

# If you have enough information to answer, give your final answer"""

#         last_user_msg = ""
#         for m in reversed(messages):
#             if m.get("role") == "user":
#                 last_user_msg = m.get("content", "")
#                 break

#         history_context = {}
#         if len(messages) > 1:
#             history_context["conversation"] = "\n".join(
#                 f"{m['role'].upper()}: {m['content'][:2000]}"
#                 for m in messages[:-1]
#             )

#         try:
#             content = self.ask_llm(
#                 system_prompt  = full_system,
#                 user_message   = last_user_msg,
#                 graph_context  = history_context,
#                 model          = model,
#                 include_history= False,
#                 temperature    = 0.1,
#                 max_tokens     = 1500,
#             )
#         except Exception as e:
#             print(f"[AskAgent] _ask_with_tools LLM call failed: {e}")
#             return {"content": f"LLM call failed: {e}"}

#         if not content:
#             return {"content": "No response from LLM"}

#         print(f"[AskAgent] LLM raw: {content[:150]}")

#         import re
#         stripped = content.strip()
#         match = re.search(
#             r'TOOL:\s*(\w+)\s*\nARG:\s*(.+?)(?:\nTOOL:|$)',
#             stripped, re.DOTALL,
#         )
#         if match:
#             tool_name = match.group(1).strip()
#             arg_value = match.group(2).strip().split("\n")[0].strip()

#             tool_def = next((t for t in tools if t["name"] == tool_name), None)
#             if tool_def:
#                 arg_key = list(tool_def["parameters"].keys())[0]
#                 print(f"[AskAgent] Tool call: {tool_name}({arg_key}={arg_value})")
#                 return {
#                     "tool_call": {
#                         "name":      tool_name,
#                         "arguments": {arg_key: arg_value},
#                     }
#                 }
#             else:
#                 print(f"[AskAgent] Unknown tool: {tool_name}")

#         return {"content": content}

#     # ═══════════════════════════════════════════════════════════════════════════
#     # _execute_tool  (original Markar — unchanged)
#     # ═══════════════════════════════════════════════════════════════════════════

#     def _execute_tool(self, tool_name: str, args: dict) -> dict:
#         """Tool execute karo — Neo4j se data lo, disk se source code."""
#         import os

#         if tool_name == "search_nodes":
#             query = args.get("query", "")
#             stop  = {"the","a","an","in","is","or","not","and","of","to","for"}
#             words = [w.lower().strip("?.,") for w in query.split()
#                      if len(w) > 2 and w.lower() not in stop]
#             if not words:
#                 words = [query.lower()]

#             all_rows = []
#             seen = set()
#             for word in words[:4]:
#                 rows = self.query("""
#                     MATCH (n:CodeNode {repo_id:$r})
#                     WHERE n.node_type IN ['function','file']
#                     AND (toLower(n.name)      CONTAINS toLower($w)
#                     OR  toLower(n.file_path) CONTAINS toLower($w))
#                     RETURN n.node_id AS node_id,
#                            n.name AS name, n.file_path AS file,
#                            n.node_type AS type, n.line_no AS line
#                     ORDER BY
#                     CASE n.node_type WHEN 'file' THEN 0 ELSE 1 END
#                     LIMIT 8
#                 """, w=word)
#                 for r in rows:
#                     key = f"{r['file']}:{r['name']}"
#                     if key not in seen:
#                         all_rows.append(r)
#                         seen.add(key)

#             return {"results": all_rows, "count": len(all_rows)}

#         elif tool_name == "get_source_code":
#             fname = args.get("function_name", "")
#             rows  = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE toLower(n.name) CONTAINS toLower($fn)
#                    OR n.name = $fn
#                 RETURN n.name AS name, n.file_path AS file,
#                        n.line_no AS line,
#                        n.deep_total_lines AS total_lines
#                 LIMIT 3
#             """, fn=fname)

#             if not rows:
#                 return {"error": f"Function '{fname}' not found in graph"}

#             repo_path = self._get_repo_path()
#             results   = []
#             for row in rows:
#                 file_path   = row.get("file", "")
#                 line_start  = row.get("line") or 1
#                 total_lines = row.get("total_lines") or 30
#                 source = self._read_function_source(
#                     repo_path, file_path, fname, line_start, total_lines
#                 )
#                 results.append({
#                     "function":   row["name"],
#                     "file":       file_path,
#                     "line_start": line_start,
#                     "source":     source,
#                 })
#                 print(f"[get_source_code] func={row['name']} file={file_path} source_len={len(source)}")

#             return {"functions": results, "count": len(results)}

#         elif tool_name == "get_callers":
#             fname = args.get("function_name", "")
#             print(f"[get_callers] searching for: '{fname}' in repo: {self.repo_id}")

#             # ── POTPIE STYLE: Step 1 — exact node_id dhundo (naam se nahi) ──────
#             # Exact match pehle, phir partial — "run" jaisa common naam
#             # wrong nodes match na kare
#             id_rows = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE n.name = $fn
#                    OR n.name ENDS WITH ('.' + $fn)
#                 RETURN n.node_id AS node_id, n.name AS name,
#                        n.file_path AS file
#                 LIMIT 5
#             """, fn=fname)

#             # Exact nahi mila → partial fallback
#             if not id_rows:
#                 id_rows = self.query("""
#                     MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                     WHERE toLower(n.name) CONTAINS toLower($fn)
#                     RETURN n.node_id AS node_id, n.name AS name,
#                            n.file_path AS file
#                     LIMIT 5
#                 """, fn=fname)

#             if not id_rows:
#                 return {"callers": [], "count": 0,
#                         "note": f"Function '{fname}' not found in graph"}

#             # ── POTPIE STYLE: Step 2 — node_id se neighbours traverse karo ──────
#             all_callers = []
#             seen_caller = set()

#             for id_row in id_rows:
#                 node_id   = id_row["node_id"]
#                 node_name = id_row["name"]
#                 node_file = id_row["file"]

#                 print(f"[get_callers] node_id={node_id} name={node_name}")

#                 rows = self.query("""
#                     MATCH (target:CodeNode {node_id:$nid, repo_id:$r})
#                     MATCH (caller:CodeNode {repo_id:$r})-[:DEPENDS_ON]->(target)
#                     WHERE caller.node_id <> target.node_id
#                     AND   caller.node_type IN ['function','file','class']
#                     RETURN DISTINCT
#                         caller.node_id   AS node_id,
#                         caller.name      AS name,
#                         caller.file_path AS file,
#                         caller.line_no   AS line,
#                         caller.node_type AS type
#                     ORDER BY caller.file_path, caller.line_no
#                     LIMIT 20
#                 """, nid=node_id)

#                 for r in rows:
#                     key = r["node_id"]
#                     if key not in seen_caller:
#                         all_callers.append({
#                             "name": r["name"],
#                             "file": r["file"],
#                             "line": r["line"],
#                             "type": r["type"],
#                             "calls_into": node_name,
#                             "calls_into_file": node_file,
#                         })
#                         seen_caller.add(key)

#             print(f"[get_callers] found {len(all_callers)} callers for '{fname}'")

#             # ── POTPIE STYLE: Fallback — direct callers nahi mile ────────────────
#             # Entry-point functions (run, main, handle_request) ko koi direct
#             # caller nahi hota — externally call hoti hain. Aise case mein
#             # class/file ownership dikhao (Potpie ka get_node_neighbours approach).
#             if not all_callers and id_rows:
#                 ownership = []
#                 for id_row in id_rows:
#                     node_id = id_row["node_id"]

#                     # Class ownership — kis class ka member hai
#                     class_rows = self.query("""
#                         MATCH (cls:CodeNode {repo_id:$r, node_type:'class'})
#                               -[:DEPENDS_ON]->(fn:CodeNode {node_id:$nid})
#                         RETURN cls.name      AS name,
#                                cls.file_path AS file,
#                                cls.line_no   AS line,
#                                'class'       AS type,
#                                'owns'        AS relationship
#                         LIMIT 5
#                     """, nid=node_id)
#                     ownership.extend(class_rows)

#                     # File ownership — kis file mein defined hai
#                     file_rows = self.query("""
#                         MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
#                               -[:DEPENDS_ON]->(fn:CodeNode {node_id:$nid})
#                         RETURN f.name      AS name,
#                                f.file_path AS file,
#                                f.line_no   AS line,
#                                'file'      AS type,
#                                'contains'  AS relationship
#                         LIMIT 3
#                     """, nid=node_id)
#                     ownership.extend(file_rows)

#                 if ownership:
#                     print(f"[get_callers] no direct callers, returning ownership for '{fname}'")
#                     return {
#                         "callers": ownership,
#                         "count":   len(ownership),
#                         "note":    f"'{fname}' has no direct callers — it is likely an entry-point (HTTP/CLI/scheduler). Showing class/file ownership instead.",
#                     }

#                 return {
#                     "callers": [],
#                     "count":   0,
#                     "note":    f"'{fname}' is an entry-point function called externally (HTTP handler / scheduler / CLI). No internal callers in codebase.",
#                 }

#             return {"callers": all_callers, "count": len(all_callers)}

#         elif tool_name == "get_callees":
#             fname = args.get("function_name", "")
#             print(f"[get_callees] searching for: '{fname}' in repo: {self.repo_id}")

#             # ── POTPIE STYLE: Step 1 — exact node_id dhundo ──────────────────────
#             id_rows = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE n.name = $fn
#                    OR n.name ENDS WITH ('.' + $fn)
#                 RETURN n.node_id AS node_id, n.name AS name,
#                        n.file_path AS file
#                 LIMIT 5
#             """, fn=fname)

#             if not id_rows:
#                 id_rows = self.query("""
#                     MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                     WHERE toLower(n.name) CONTAINS toLower($fn)
#                     RETURN n.node_id AS node_id, n.name AS name,
#                            n.file_path AS file
#                     LIMIT 5
#                 """, fn=fname)

#             if not id_rows:
#                 return {"callees": [], "count": 0,
#                         "note": f"Function '{fname}' not found in graph"}

#             # ── POTPIE STYLE: Step 2 — outgoing DEPENDS_ON edges traverse ────────
#             all_callees = []
#             seen_callee = set()

#             for id_row in id_rows:
#                 node_id   = id_row["node_id"]
#                 node_name = id_row["name"]

#                 print(f"[get_callees] node_id={node_id} name={node_name}")

#                 rows = self.query("""
#                     MATCH (source:CodeNode {node_id:$nid, repo_id:$r})
#                     MATCH (source)-[:DEPENDS_ON]->(callee:CodeNode {repo_id:$r})
#                     WHERE callee.node_id <> source.node_id
#                     AND   callee.node_type IN ['function','file','class']
#                     RETURN DISTINCT
#                         callee.node_id   AS node_id,
#                         callee.name      AS name,
#                         callee.file_path AS file,
#                         callee.line_no   AS line,
#                         callee.node_type AS type
#                     ORDER BY callee.file_path, callee.line_no
#                     LIMIT 20
#                 """, nid=node_id)

#                 for r in rows:
#                     key = r["node_id"]
#                     if key not in seen_callee:
#                         all_callees.append({
#                             "name": r["name"],
#                             "file": r["file"],
#                             "line": r["line"],
#                             "type": r["type"],
#                             "called_by": node_name,
#                         })
#                         seen_callee.add(key)

#             print(f"[get_callees] found {len(all_callees)} callees for '{fname}'")
#             return {"callees": all_callees, "count": len(all_callees)}

#         elif tool_name == "get_file_functions":
#             fpath = args.get("file_path", "")
#             rows  = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE toLower(n.file_path) CONTAINS toLower($fp)
#                 RETURN n.name AS name, n.line_no AS line,
#                        n.deep_risk_level AS risk,
#                        n.deep_complexity  AS complexity,
#                        n.deep_raises      AS raises
#                 ORDER BY n.line_no
#                 LIMIT 30
#             """, fp=fpath)

#             repo_path   = self._get_repo_path()
#             file_source = ""
#             if repo_path and rows:
#                 actual_path = rows[0].get("file_path") or fpath
#                 file_source = self._read_file_source(repo_path, actual_path)

#             return {
#                 "functions":   rows,
#                 "count":       len(rows),
#                 "file_source": file_source[:2000] if file_source else "",
#             }

#         return {"error": f"Unknown tool: {tool_name}"}

#     # ═══════════════════════════════════════════════════════════════════════════
#     # HELPER METHODS  (original Markar — unchanged)
#     # ═══════════════════════════════════════════════════════════════════════════

#     def _get_repo_path(self) -> str:
#         import os
#         repo_path = getattr(self.store, "repo_path", None)
#         if repo_path:
#             return repo_path
#         try:
#             from app.services.repo_service import _jobs
#             for job in _jobs.values():
#                 if job.get("repo_path"):
#                     return job["repo_path"]
#         except Exception:
#             pass
#         return os.getenv("MARKAR_REPO_PATH", "")

#     def _read_function_source(
#         self, repo_path: str, file_path: str,
#         func_name: str, line_start: int, total_lines: int,
#     ) -> str:
#         import os, ast
#         if not repo_path or not file_path:
#             return "source not available"

#         clean    = file_path.replace("\\", os.sep).replace("/", os.sep)
#         abs_path = os.path.join(repo_path, clean)
#         if not os.path.exists(abs_path):
#             abs_path = file_path
#         if not os.path.exists(abs_path):
#             return f"file not found: {file_path}"

#         try:
#             with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
#                 source = f.read()

#             try:
#                 tree  = ast.parse(source)
#                 lines = source.splitlines()
#                 for node in ast.walk(tree):
#                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
#                         clean_name = func_name.split(".")[-1]
#                         if node.name == clean_name or clean_name.lower() in node.name.lower():
#                             s        = node.lineno - 1
#                             e        = getattr(node, "end_lineno", s + total_lines)
#                             func_src = "\n".join(lines[s:e])
#                             return f"lines {node.lineno}-{e}:\n{func_src}"
#             except Exception:
#                 pass

#             lines = source.splitlines()
#             start = max(0, line_start - 1)
#             end   = min(len(lines), start + (total_lines or 30))
#             return "\n".join(
#                 f"{i+1}: {l}" for i, l in enumerate(lines[start:end], start=start)
#             )
#         except Exception as e:
#             return f"read error: {e}"

#     def _read_file_source(self, repo_path: str, file_path: str) -> str:
#         import os
#         if not repo_path or not file_path:
#             return ""
#         clean    = file_path.replace("\\", os.sep).replace("/", os.sep)
#         abs_path = os.path.join(repo_path, clean)
#         if not os.path.exists(abs_path):
#             abs_path = file_path
#         try:
#             with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
#                 return f.read()
#         except Exception:
#             return ""

#     def _extract_keywords(self, message: str) -> list:
#         stop = {
#             "kahan","hai","kya","kar","raha","mein","se","ka",
#             "ki","ko","karo","where","is","the","a","an","in",
#             "what","how","does","do","find","show","tell","me",
#             "batao","dikhao","give","list","all","get","search",
#             "kaunsa","konsa","kon","kis","kisiko","working","or",
#             "not","check","routes","route","file","me","ek",
#         }
#         words = [w.lower().strip("?.,!") for w in message.split()
#                  if w.lower().strip("?.,!") not in stop and len(w) > 2]
#         return words[:6]

#     def _search_graph(self, keywords: list) -> Dict:
#         all_funcs = []
#         all_files = []
#         seen_ids  = set()

#         for kw in keywords:
#             if len(kw) < 2:
#                 continue

#             funcs = self.query("""
#                 MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE toLower(f.name) CONTAINS toLower($kw)
#                    OR toLower(f.file_path) CONTAINS toLower($kw)
#                 RETURN f.node_id AS id, f.name AS name,
#                        f.file_path AS file, f.line_no AS line
#                 LIMIT 10
#             """, kw=kw)
#             for fn in funcs:
#                 if fn["id"] not in seen_ids:
#                     all_funcs.append(fn)
#                     seen_ids.add(fn["id"])

#             files = self.query("""
#                 MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
#                 WHERE toLower(f.file_path) CONTAINS toLower($kw)
#                    OR toLower(f.name)      CONTAINS toLower($kw)
#                 RETURN f.node_id AS id, f.name AS name,
#                        f.file_path AS file
#                 LIMIT 5
#             """, kw=kw)
#             for fl in files:
#                 if fl["id"] not in seen_ids:
#                     all_files.append(fl)
#                     seen_ids.add(fl["id"])

#         connections = []
#         if all_funcs:
#             first_id    = all_funcs[0]["id"]
#             connections = self.query("""
#                 MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
#                 OPTIONAL MATCH (caller)-[:DEPENDS_ON]->(n)
#                 OPTIONAL MATCH (n)-[:DEPENDS_ON]->(callee)
#                 RETURN
#                     collect(DISTINCT caller.name)[..5] AS callers,
#                     collect(DISTINCT callee.name)[..5] AS callees
#             """, nid=first_id)

#         risk_keywords = {"critical","high","risk","risky","important","danger"}
#         risk_data     = []
#         if any(kw in risk_keywords for kw in keywords):
#             risk_data = self.query("""
#                 MATCH (file:CodeNode {repo_id:$r, node_type:'file'})
#                 OPTIONAL MATCH (file)-[:DEPENDS_ON]->(fn:CodeNode {node_type:'function'})
#                 WITH file, count(DISTINCT fn) AS fc
#                 WHERE fc > 15
#                 RETURN file.file_path AS file, fc AS function_count,
#                        CASE
#                            WHEN fc > 30 THEN 'High'
#                            WHEN fc > 15 THEN 'Medium'
#                            ELSE 'Low'
#                        END AS risk
#                 ORDER BY fc DESC
#                 LIMIT 10
#             """)
#             for rf in risk_data:
#                 if rf["file"] not in seen_ids:
#                     all_files.append({
#                         "id":             rf["file"],
#                         "name":           rf["file"].split("\\")[-1].split("/")[-1],
#                         "file":           rf["file"],
#                         "risk":           rf["risk"],
#                         "function_count": rf["function_count"],
#                     })
#                     seen_ids.add(rf["file"])

#         return {
#             "keywords":    keywords,
#             "nodes":       all_funcs + all_files,
#             "files":       [f["file"] for f in all_files],
#             "functions":   [f["name"] for f in all_funcs],
#             "connections": connections[0] if connections else {},
#             "risk_files":  risk_data,
#         }
# """
# Ask Agent — "X feature kahan hai", "Y function kya karta hai"
# Neo4j se dhundho, actual file content padho, LLM se explain karo.

# v3 (FIXED):
#   - Prefetch system HATAYA — LLM ko galat caller data inject karta tha
#   - _search_graph connections query se caller data inject hona band
#   - get_callers / get_callees mein *1..2 wali queries HATAI — node_id based exact queries
#   - Always tool loop — no COMPLETE/PARTIAL shortcut
#   - Ek hi SYSTEM_PROMPT — no dynamic switching
# """
# from typing import Dict, AsyncGenerator

# from langchain import messages
# from .base_agent import BaseAgent
# from app.agents.deep_context_mixin import DeepContextMixin


# class AskAgent(DeepContextMixin, BaseAgent):

#     # ═══════════════════════════════════════════════════════════════════════════
#     # SYSTEM PROMPT  (Iron Laws — unchanged from v2)
#     # ═══════════════════════════════════════════════════════════════════════════
#     SYSTEM_PROMPT = """
# You are Markar AI — a code intelligence engine with DIRECT database access.

# ══════════════════════════════════════════════════════════
# IDENTITY
# ══════════════════════════════════════════════════════════
# You are NOT a general AI assistant.
# You are a SPECIALIZED CODE DATABASE QUERY ENGINE.
# You have NO knowledge of code except what tools return.
# You CANNOT guess. You CANNOT assume. You CANNOT invent.

# ══════════════════════════════════════════════════════════
# IRON LAW — ZERO EXCEPTIONS
# ══════════════════════════════════════════════════════════
# LAW 1: Every single fact in your answer MUST come from a tool result.
#         If you did not get it from a tool — it does not exist.

# LAW 2: Every file path, function name, line number MUST be copy-pasted
#         from tool output. Never type them from memory.

# LAW 3: If tool returns empty — say EXACTLY:
#         "Not found in codebase via graph search."
#         Do NOT explain. Do NOT suggest alternatives. Just that sentence.

# LAW 4: NEVER write your answer before calling ALL required tools.
#         Writing answer early = VIOLATION.

# LAW 5: NEVER add information that was not in tool results.
#         "It probably also calls X" = VIOLATION.
#         "This function likely returns Y" = VIOLATION.

# LAW 6: When source code is in tool result — READ EVERY LINE.
#         Quote exact function signatures, parameters, return values.
#         Do not paraphrase — be exact.

# ══════════════════════════════════════════════════════════
# ⚠️  CRITICAL: YOU MUST CALL TOOLS FIRST ⚠️
# ══════════════════════════════════════════════════════════

# NEVER write a final answer without calling:
#   1. search_nodes
#   2. get_source_code  
#   3. get_callers
#   4. get_callees

# If you write an answer before calling all 4 tools → VIOLATION.

# TOOL FORMAT (EXACT — no changes):
# TOOL: search_nodes
# ARG: function_name

# Only after tool results → write final answer.        

# ══════════════════════════════════════════════════════════
# TOOL CALLING RULES
# ══════════════════════════════════════════════════════════
# RULE 1: Call tools in sequence. Never skip steps.
# RULE 2: ONE tool per response. Wait for result. Then next tool.
# RULE 3: Use EXACT format — no deviation:

# TOOL: tool_name
# ARG: value

# RULE 4: ARG must be a SINGLE keyword — never a phrase.
#         CORRECT:   ARG: signup
#         INCORRECT: ARG: signup function auth

# RULE 5: After each tool result — decide next tool based on RESULT.
#         Do not pre-plan all tools upfront.

# ══════════════════════════════════════════════════════════
# MANDATORY TOOL SEQUENCES
# ══════════════════════════════════════════════════════════

# FIND FUNCTION (where is X, how does X work):
#   1. search_nodes → find exact file and function name
#   2. get_source_code → read actual implementation
#   3. get_callees → what it calls internally
#   4. Answer using ONLY lines from source code

# DEPENDENCY (what calls X, who uses X, called by):
#   MANDATORY SEQUENCE — NO SHORTCUTS:
#   1. search_nodes → find function
#   2. get_source_code → read implementation
#   3. get_callers → YOU MUST CALL THIS — NEVER SKIP
#   4. get_callees → YOU MUST CALL THIS — NEVER SKIP
#   5. ONLY THEN write answer

#   IF YOU SKIP get_callers → YOUR ANSWER IS WRONG
#   IF YOU SKIP get_callees → YOUR ANSWER IS WRONG

# LAW 7: IF search_nodes returns 0 results OR empty_notice is present:
#     YOU MUST RESPOND EXACTLY:
#     "Not found in codebase via graph search."
#     NOTHING ELSE. No explanations. No generic answers.
#     NEVER use general knowledge about software architecture.

#   IF search_nodes returns 0 results:
#   → Try get_file_functions with partial file name
#   → NEVER answer from general knowledge
#   → Say "Not found in codebase" if all tools return empty

# ABSOLUTE RULE:
# EVERY question about this codebase requires tool calls FIRST.
# Even if you think you know the answer — call search_nodes FIRST.
# NO EXCEPTIONS.

# CRITICAL: When giving FINAL ANSWER:
# - Write COMPLETE detailed response
# - Include ALL source code lines — do NOT skip any
# - Include EVERY parameter with exact type
# - Include EVERY return value exactly as in source
# - Include ALL callers with file path and line number
# - Include ALL callees with file path and line number
# - Include ALL issues found in source code with line numbers
# - Minimum 300 words — short answers = VIOLATION
# - Do NOT summarize — write everything  

# BUG CHECK (is X working, any issues):
#   1. search_nodes → find function
#   2. get_source_code → read actual code
#   3. get_callees → check what it calls
#   4. get_callers → check how it is used
#   5. Verdict: YES working / NO not working — with LINE NUMBERS as evidence

# FLOW TRACE (how does X reach Y):
#   1. search_nodes → find entry point
#   2. get_source_code → read entry function
#   3. get_callees → what it calls
#   4. get_source_code → read each callee
#   5. Repeat until full chain traced
#   6. Answer: Line A calls B() at line X → B calls C() at line Y → ...

# ══════════════════════════════════════════════════════════
# ANSWER FORMAT — MANDATORY
# ══════════════════════════════════════════════════════════

# **Overview**
# [2-3 sentences. Only facts from tool results. No interpretation.]

# **Functions Found**
# For each function from tool results:
# - FunctionName — file path (line X)
#   Parameters: [exact params from source code]
#   Returns: [exact return from source code]
#   Calls: [only from get_callees result]
#   Called by: [from get_callers result]
#     - If get_callers returns empty list OR note says "entry-point" →
#       write exactly: "Entry-point — called externally (HTTP/CLI/scheduler)"
#     - NEVER write "Not found in codebase" for Called by field
#     - NEVER leave Called by blank

# **Code Flow**
# [Trace from source code only]
# Line X: variable = function_call()
# Line Y: calls ExternalFunction(param1, param2)
# Line Z: returns result_dict

# **Issues Found**
# [Only if visible in actual source code]
# [If no issues visible: "No issues detected in returned source code."]

# **Summary**
# Working: YES / NO
# Evidence: [specific line numbers from source code]

# ══════════════════════════════════════════════════════════
# VIOLATIONS THAT WILL BREAK ACCURACY
# ══════════════════════════════════════════════════════════
# X Writing answer before all tools called
# X Mentioning files not returned by tools
# X Guessing parameter names
# X Saying "probably", "likely", "typically", "usually"
# X Adding general knowledge about OAuth, JWT, HTTP, etc
# X Truncating — always give complete information
# X Using backticks in response
# """


#     # ═══════════════════════════════════════════════════════════════════════════
#     # USER MESSAGE SANITIZATION
#     # ═══════════════════════════════════════════════════════════════════════════
 
#     def _sanitize_user_message(self, raw: str) -> str:
#         """
#         User message clean karo — 3 problems handle karta hai:
 
#         PROBLEM 1 — User ne tool call syntax paste kar diya:
#             "explain repo_service\nTOOL: search_nodes\nARG: repo_service"
#             → "explain repo_service"
 
#         PROBLEM 2 — User ne sirf tool call likha, koi actual question nahi:
#             "TOOL: search_nodes\nARG: repo_service"
#             → "explain repo_service file working"
 
#         PROBLEM 3 — Tool result / system text mix ho gaya user message mein:
#             "[Tool Result]: {...}\nab explain karo"
#             → "ab explain karo"
#         """
#         import re
 
#         text = raw.strip()
 
#         # ── STEP 1: Tool call block detect karo ────────────────────────────────
#         # Pattern: TOOL: <name>\nARG: <value>  (kahin bhi in message mein)
#         tool_pattern = re.compile(
#             r'TOOL:\s*\w+\s*\n\s*ARG:\s*(.+?)(?:\n|$)',
#             re.IGNORECASE
#         )
 
#         # Saare tool call blocks se ARG values nikalo (agar user ne intent
#         # express kiya tha to woh ARG value hi real subject hai)
#         arg_values = tool_pattern.findall(text)
 
#         # Tool call blocks hatao — sirf human-written part bachao
#         cleaned = tool_pattern.sub("", text).strip()
 
#         # ── STEP 2: [Tool Result] / [SYSTEM] junk hatao ────────────────────────
#         junk_pattern = re.compile(
#             r'\[Tool(?:\s+Result)?[:\]].{0,2000}?(?=\n[A-Z\[]|\Z)',
#             re.DOTALL | re.IGNORECASE
#         )
#         cleaned = junk_pattern.sub("", cleaned).strip()
 
#         system_pattern = re.compile(r'\[SYSTEM\].*?(?=\n[A-Z\[]|\Z)', re.DOTALL | re.IGNORECASE)
#         cleaned = system_pattern.sub("", cleaned).strip()
 
#         # ── STEP 3: Agar human text bilkul nahi bacha → ARG se reconstruct ─────
#         # Example: user ne sirf "TOOL: search_nodes\nARG: repo_service" likha
#         # Toh cleaned = "" → ARG value se question banao
#         if not cleaned and arg_values:
#             subject = arg_values[0].strip().split()[0]   # pehla word lo
#             cleaned = f"explain {subject} working"
#             print(f"[AskAgent] Sanitize: pure tool-call input → reconstructed: '{cleaned}'")
 
#         # ── STEP 4: Agar cleaned bahut chota hai → original se subject nikalo ──
#         if len(cleaned) < 5 and arg_values:
#             subject = arg_values[0].strip().split()[0]
#             cleaned = f"explain {subject} working"
#             print(f"[AskAgent] Sanitize: too short after clean → reconstructed: '{cleaned}'")
 
#         if cleaned != raw.strip():
#             print(f"[AskAgent] Sanitize: original='{raw[:80]}' → cleaned='{cleaned[:80]}'")
 
#         return cleaned or raw.strip()   # fallback: original message
    
#     # ═══════════════════════════════════════════════════════════════════════════
#     # PROMPT CLARIFIER — vague file question → specific instruction
#     # ═══════════════════════════════════════════════════════════════════════════
 
#     def _clarify_vague_prompt(self, user_message: str) -> str:
#         """
#         Vague file-level prompts detect karo aur LLM ke liye specific banao.
 
#         WHY: Jab user "explain repo_service file" likhta hai toh search_nodes
#         file match karta hai, LLM randomly koi ek function pick karta hai,
#         inconsistent answers aate hain. Specific function naam wali queries
#         touch nahi hoti — woh already precise hain.
 
#         Vague:    "explain repo_service file working correctly"
#         Fixed:    "Get all functions in repo_service using get_file_functions.
#                    Then for each: source code, callers, callees, explain."
 
#         Specific (untouched): "How does _resolve_provider decide which LLM?"
#         """
#         import re
 
#         msg = user_message.lower().strip()
 
#         # ── Specific function naam already hai → touch mat karo ────────────────
#         has_function_name = bool(re.search(
#             r'\b_[a-z][a-z0-9_]{2,}\b'        # _save_repo_to_db style
#             r'|\b[a-z]+_[a-z_]+\([^)]*\)',    # func_name() with parens
#             user_message
#         ))
#         if has_function_name:
#             print(f"[AskAgent] Clarify: specific function detected → no change")
#             return user_message
 
#         # ── Vague file-level question patterns ─────────────────────────────────
#         file_patterns = [
#             r'\b(explain|describe|show|tell|how does|working of)\b.{0,30}\bfile\b',
#             r'\bfile\b.{0,20}\b(working|kaam|explain|kya karta|work)',
#             r'\b(\w+_service|service|module|router|handler|agent|utils|manager)'
#             r'\b.{0,25}\b(kya|what|how|explain|working|kaam|samjhao|bta)',
#             r'\b(explain|samjhao|bta|describe)\b.{0,40}'
#             r'\b(\w+_service|service|module|router|handler|agent)',
#         ]
#         is_vague = any(re.search(p, msg) for p in file_patterns)
 
#         # ── File / module naam extract karo ────────────────────────────────────
#         file_match = re.search(
#             r'\b([a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)+)\b',
#             msg
#         )
 
#         if is_vague and file_match:
#             file_name = file_match.group(1)
#             clarified = (
#                 f"Get all functions in the {file_name} file using get_file_functions tool. "
#                 f"Then for the most important functions found: get each function's source code "
#                 f"using get_source_code, find who calls it using get_callers, find what it calls "
#                 f"using get_callees. Give a complete overview of how {file_name} works end to end, "
#                 f"covering the main flow and purpose of each function."
#             )
#             print(
#                 f"[AskAgent] Clarify: vague='{user_message[:60]}' "
#                 f"→ specific='{clarified[:80]}'"
#             )
#             return clarified
 
#         return user_message
 
#     # ═══════════════════════════════════════════════════════════════════════════
#     # MAIN RUN  — ALWAYS tool loop, no prefetch shortcuts
#     # ═══════════════════════════════════════════════════════════════════════════


#     def _validate_tool_calls_in_messages(self, messages, required_tools):
#         """Check if LLM has already called required tools"""
#         last_assistant = None
#         for m in reversed(messages):
#             if m.get("role") == "assistant" and "TOOL:" in m.get("content", ""):
#                 last_assistant = m["content"]
#                 break
        
#         if last_assistant:
#             for tool in required_tools:
#                 if tool not in last_assistant:
#                     return False, f"Missing {tool}"
#         return True, "ok"
    
#     def _force_tool_instruction(self, user_message: str) -> str:
#         """
#         Har us question pe jo codebase ke baare mein poochta hai,
#         forcefully tool instruction inject karo.
        
#         WITHOUT this, LLM kabhi "explain X file" pe hallucinate kar leta hai.
#         """
#         import re
        
#         msg_lower = user_message.lower()
        
#         # Detect karo: kya yeh codebase-specific question hai?
#         codebase_patterns = [
#             r'explain.*\.py',           # explain repo_service.py
#             r'purpose of.*file',        # purpose of file
#             r'what does.*\.py',         # what does file do
#             r'kaam kya.*file',          # Hindi mix
#             r'main purpose',            # direct
#             r'repo_service',            # specific filename
#             r'service.*file',           # service file
#             r'function.*kya',           # function kya karta hai
#         ]
        
#         is_code_question = any(re.search(p, msg_lower) for p in codebase_patterns)
        
#         if not is_code_question:
#             return user_message
        
#         # ── Agar user ne sirf "Explain file" likha hai ────────────
#         # Extract filename agar mile
#         file_match = re.search(r'([\w/]+\.py)', user_message)
#         if file_match:
#             file_name = file_match.group(1)
#             forced = f"""CRITICAL INSTRUCTION FROM SYSTEM:

#     You MUST answer this question by calling tools ONLY. Do NOT use your general knowledge.

#     Step 1: First call search_nodes with ARG: {file_name}
#     Step 2: Then call get_file_functions to list all functions in this file
#     Step 3: For each important function, call get_source_code
#     Step 4: Then call get_callers and get_callees

#     NEVER write a final answer before completing ALL these tool calls.

#     USER QUESTION: {user_message}

#     Remember: You have NO knowledge of this codebase outside of tool results."""
#             return forced
        
#         # ── Agar sirf "explain" hai bina filename ke ──────────────
#         if 'explain' in msg_lower and 'file' in msg_lower:
#             forced = f"""SYSTEM OVERRIDE: This is a codebase question. You MUST use tools.

#     First call: TOOL: search_nodes with ARG based on the filename in the question.
#     Then call get_source_code on the main function found.

#     USER QUESTION: {user_message}"""
#             return forced
        
#         return user_message

    
    
#     def run(self, user_message: str, model: str = None) -> Dict:
#         """Tool-based approach — ALWAYS tool loop, no prefetch shortcuts."""

#          # ── STEP 0: Sanitize — junk / tool syntax hatao ──────────────────────
#         user_message = self._sanitize_user_message(user_message)
#         # ── STEP 1: Clarify — vague file question → specific instruction ─────
#         user_message = self._clarify_vague_prompt(user_message)

#          # ═══════════════════════════════════════════════════════════
#         # NEW: FORCE TOOL INSTRUCTION — Har "explain" question pe
#         # ═══════════════════════════════════════════════════════════
#         user_message = self._force_tool_instruction(user_message)
#         # ═══════════════════════════════════════════════════════════

#         print(f"[AskAgent] Final user_message: '{user_message[:100]}'")

        

#         tools          = self._define_tools()
#         messages       = [{"role": "user", "content": user_message}]
#         all_files      = set()
#         all_funcs      = set()
#         MAX_TOOL_CALLS = 15
#         tools_called   = set()
#         executed_tools = set()
#         tool_retry_count = {}
#         last_func_name = None

#         for _ in range(MAX_TOOL_CALLS):
#             if tools_called.issuperset({"search_nodes", "get_source_code", "get_callers", "get_callees"}):
#                 print("[AskAgent] All tools already called — forcing final answer generation")
#                 final = self.ask_llm(
#                     system_prompt=self.SYSTEM_PROMPT,
#                     user_message="""Now write your FINAL ANSWER based on the tool results above. 
#                 STRICT RULES:
#                 - If get_callers returned empty → say "Entry-point — called externally"
#                 - NEVER say "recursive" unless tool results explicitly show recursion
#                 - Copy-paste exact parameters from get_source_code result
#                 - Include ALL callers found in get_callers
#                 - Minimum 500 words

#                 Do NOT invent information. Do NOT guess.""",
#                     graph_context={"tool_results": str(messages[-6:])},
#                     model=model,
#                     max_tokens=1500,
#                 )
#                 return {
#                     "answer": final,
#                     "files": list(all_files),
#                     "functions": list(all_funcs),
#                     "agent": "ask",
#                 }
#             llm_response = self._ask_with_tools(
#                 system_prompt=self.SYSTEM_PROMPT,
#                 messages=messages,
#                 tools=tools,
#                 model=model,
#             )
#             if llm_response.get("pending_tool_calls"):
#                 for pending in llm_response["pending_tool_calls"]:
#                     # Execute pending tool calls automatically
#                     tool_name = pending["name"]
#                     tool_args = pending["arguments"]
#                     tools_called.add(tool_name)
                    
#                     # Execute tool
#                     tool_result = self._execute_tool(tool_name, tool_args)
                    
#                     # Add to messages
#                     messages.append({"role": "assistant", "content": f"[Tool: {tool_name}] {str(tool_args)}"})
#                     messages.append({"role": "user", "content": f"[Tool Result]: {str(tool_result)[:4000]}"})
                
#                 # After processing pending, continue to next iteration
#                 continue

#             if not llm_response.get("tool_call"):
#                 content = llm_response.get("content", "").lower()
                

#                 hallucination_markers = [
#                     "userrepo", "productrepo",      # Generic repo names
#                     "typically", "usually",         # Guess words
#                     "in most applications",         # General knowledge
#                     "business logic",               # Vague generic phrase
#                     "crud operations",              # Generic
#                 ]

                
#                 # Force get_callers agar nahi hua
#                 if any(marker in content for marker in hallucination_markers):
#                     messages.append({
#                         "role": "user",
#                         "content": f"[SYSTEM]: ❌ You wrote an answer without calling get_callers for '{last_func_name}'. This is FORBIDDEN. Call get_callers NOW.",
#                     })
#                     continue

#                 # Force get_callees agar nahi hua
#                 if "get_callees" not in tools_called and last_func_name:
#                     messages.append({
#                         "role": "user",
#                         "content": f"[SYSTEM]: ❌ You wrote an answer without calling get_callees for '{last_func_name}'. Call get_callees NOW.",
#                     })
#                     continue
#                 if llm_response.get("content"):
#                     messages.append({
#                         "role": "user",
#                         "content": "[SYSTEM]: ❌ You are NOT allowed to write answers without calling tools first. Start with TOOL: search_nodes",
#                     })
#                     continue

#                 return {
#                     "answer":    llm_response.get("content", "No tool called and no answer generated."),
#                     "files":     list(all_files),
#                     "functions": list(all_funcs),
#                     "agent":     "ask",
#                 }

#             tool_name = llm_response["tool_call"]["name"]
#             tool_args = llm_response["tool_call"]["arguments"]
#             tools_called.add(tool_name)

#             arg_value = ""
#             if tool_name in ["get_source_code", "get_callers", "get_callees"]:
#                 arg_value = tool_args.get("function_name", "")
#             elif tool_name == "search_nodes":
#                 arg_value = tool_args.get("query", "")
#             elif tool_name == "get_file_functions":
#                 arg_value = tool_args.get("file_path", "")
            
#             tool_key = f"{tool_name}:{arg_value}"

#             retries = tool_retry_count.get(tool_name, 0)
#             if retries >= 2:
#                 print(f"[AskAgent] Tool '{tool_name}' failed {retries} times — forcing different approach")
#                 messages.append({
#                     "role": "user",
#                     "content": f"[SYSTEM]: Tool '{tool_name}' has failed {retries} times. Try a different function name or use search_nodes first."
#                 })
#                 continue

#             if tool_key in executed_tools:
#                 print(f"[AskAgent] Duplicate tool call: {tool_key} — skipping")
#                 messages.append({
#                     "role": "user",
#                     "content": f"[SYSTEM]: You already called {tool_name} with '{arg_value}'. Write your FINAL ANSWER."
#                 })
#                 continue

#             executed_tools.add(tool_key)

#             # if tool_name in executed_tools:
#             #     print(f"[AskAgent] Duplicate tool call detected: {tool_name} — skipping")
#             #     messages.append({
#             #         "role": "user", 
#             #         "content": f"[SYSTEM]: You already called {tool_name}. Now write your FINAL ANSWER."
#             #     })
#             #     continue

#             # # Mark as executed
#             # executed_tools.add(tool_name)

#             if tool_name in ("search_nodes", "get_source_code"):
#                 val = list(tool_args.values())[0] if tool_args else None
#                 if val:
#                     last_func_name = val

#             tool_result = self._execute_tool(tool_name, tool_args)

#             is_error = "error" in tool_result or (tool_result.get("count", 0) == 0 and tool_name in ["search_nodes", "get_callers", "get_callees"])

#             if is_error:
#                 tool_retry_count[tool_key] = retries + 1
#                 error_msg = tool_result.get("error", "No results found")
#                 messages.append({
#                     "role": "user",
#                     "content": f"[SYSTEM]: Tool '{tool_name}' failed: {error_msg}. Try a different search term."
#                 })
#                 continue

#             # Force answer after all required tools
#             if {"search_nodes", "get_source_code", "get_callers", "get_callees"}.issubset(tools_called):
#                 print(f"[AskAgent] All required tools called — forcing final answer")
#                 messages.append({
#                     "role": "user",
#                     "content": "[SYSTEM]: All required tools have been called. Now write your FINAL ANSWER. Do NOT call any more tools."
#                 })










#             # if tool_name in ("search_nodes", "get_source_code"):
#             #     val = list(tool_args.values())[0] if tool_args else None
#             #     if val:
#             #         last_func_name = val

#             # tool_result = self._execute_tool(tool_name, tool_args)

#             # is_error = "error" in tool_result or (tool_result.get("count", 0) == 0 and tool_name in ["search_nodes", "get_callers", "get_callees"])

#             # if is_error:
#             #     tool_retry_count[tool_name] = tool_retry_count.get(tool_name, 0) + 1
#             #     error_msg = tool_result.get("error", "No results found")
#             #     messages.append({
#             #         "role": "user",
#             #         "content": f"[SYSTEM]: Tool '{tool_name}' failed: {error_msg}. Try a different search term or use a different tool. Do NOT repeat the same tool call."
#             #     })
#             #     continue

#             # required_tools = {"search_nodes", "get_source_code", "get_callers", "get_callees"}

#             # if required_tools.issubset(tools_called):
#             #     print(f"[AskAgent] All required tools called — forcing final answer")
#             #     messages.append({
#             #         "role": "user", 
#             #         "content": "[SYSTEM]: All required tools have been called. Now write your FINAL ANSWER. Do NOT call any more tools."
#             #     })



#             # search_nodes empty → get_file_functions try karo
#             if tool_name == "search_nodes" and tool_result.get("count", 0) == 0:
#                 query = tool_args.get("query", "")
#                 broad = self._execute_tool("get_file_functions", {"file_path": query})
#                 if broad.get("count", 0) > 0:
#                     tool_result = broad
#                 else:
#                     return {
#                         "answer":    "Not found in codebase via graph search. Please ask about a specific file or function name.",
#                         "files":     [],
#                         "functions": [],
#                         "agent":     "ask",
#                     }

#             if "file" in tool_result:
#                 all_files.add(tool_result["file"])
#             if "function" in tool_result:
#                 all_funcs.add(tool_result["function"])

#             messages.append({"role": "assistant", "content": f"[Tool: {tool_name}] {str(tool_args)}"})
#             messages.append({"role": "user",      "content": f"[Tool Result]: {str(tool_result)[:4000]}"})

#         # Max tool calls hit — jo mila usse final answer
#         final = self.ask_llm(
#             system_prompt=self.SYSTEM_PROMPT,
#             user_message=user_message,
#             graph_context={"tool_results": str(messages[-6:])},
#             model=model,
#             max_tokens=500,
#         )

#         def clean_answer(answer: str) -> str:
#             import re
#             # Remove TOOL: ... and ARG: ... lines
#             cleaned = re.sub(r'TOOL:\s*\w+\s*\n?\s*ARG:\s*[^\n]*\n?', '', answer)
#             # Remove multiple newlines
#             cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
#             # Remove leading/trailing whitespace
#             cleaned = cleaned.strip()
#             return cleaned
#         return {
#             "answer":   clean_answer(llm_response.get("content", "")), 
#             "files":     list(all_files),
#             "functions": list(all_funcs),
#             "agent":     "ask",
#         }
    
    

#     # ═══════════════════════════════════════════════════════════════════════════
#     # ASYNC SUPPORT  (Potpie-inspired — loop mein run karo)
#     # ═══════════════════════════════════════════════════════════════════════════

#     async def run_async(self, user_message: str, model: str = None) -> Dict:
#         """Async version — executor mein sync run karo."""
#         import asyncio
#         loop = asyncio.get_event_loop()
#         return await loop.run_in_executor(None, lambda: self.run(user_message, model))

#     async def run_stream(
#         self, user_message: str, model: str = None
#     ) -> AsyncGenerator[str, None]:
#         """
#         Streaming version — native streaming agar available ho,
#         warna sync run karke chunk yield karo.
#         """
#         if hasattr(self, "ask_llm_stream"):
#             async for chunk in self.ask_llm_stream(
#                 system_prompt=self.SYSTEM_PROMPT,
#                 user_message=user_message,
#                 graph_context={},
#                 model=model,
#             ):
#                 yield chunk
#         else:
#             result = self.run(user_message, model)
#             yield result.get("answer", "")

#     # ═══════════════════════════════════════════════════════════════════════════
#     # TOOLS DEFINITION
#     # ═══════════════════════════════════════════════════════════════════════════

#     def _define_tools(self) -> list:
#         return [
#             {
#                 "name":        "search_nodes",
#                 "description": "Search functions/files by keyword in name or file path",
#                 "parameters":  {"query": "string"},
#             },
#             {
#                 "name":        "get_source_code",
#                 "description": "Get actual source code of a specific function",
#                 "parameters":  {"function_name": "string"},
#             },
#             {
#                 "name":        "get_callers",
#                 "description": "Who calls this function — find all callers",
#                 "parameters":  {"function_name": "string"},
#             },
#             {
#                 "name":        "get_callees",
#                 "description": "What does this function call internally",
#                 "parameters":  {"function_name": "string"},
#             },
#             {
#                 "name":        "get_file_functions",
#                 "description": "Get all functions in a file with line numbers",
#                 "parameters":  {"file_path": "string"},
#             },
#         ]

#     # ═══════════════════════════════════════════════════════════════════════════
#     # _ask_with_tools  (unchanged from v2)
#     # ═══════════════════════════════════════════════════════════════════════════

#     def _ask_with_tools(self, system_prompt, messages, tools, model=None) -> dict:
#         """LLM ko tools ke saath call karo."""
#         import re

#         tools_text = "\n".join([
#             f"- {t['name']}({list(t['parameters'].keys())[0]}): {t['description']}"
#             for t in tools
#         ])

#         full_system = system_prompt + f"""

# AVAILABLE TOOLS:
# {tools_text}

# CRITICAL: When giving FINAL ANSWER:
# - Write COMPLETE detailed response
# - Include ALL steps from source code
# - Include ALL line numbers
# - Do NOT summarize — write everything

# To call a tool respond ONLY with exactly this format:
# TOOL: tool_name
# ARG: value

# If you have enough information to answer, give your final answer"""

#         last_user_msg = ""
#         for m in reversed(messages):
#             if m.get("role") == "user":
#                 last_user_msg = m.get("content", "")
#                 break

#         history_context = {}
#         if len(messages) > 1:
#             history_context["conversation"] = "\n".join(
#                 f"{m['role'].upper()}: {m['content'][:2000]}"
#                 for m in messages[:-1]
#             )

#         try:
#             content = self.ask_llm(
#                 system_prompt  = full_system,
#                 user_message   = last_user_msg,
#                 graph_context  = history_context,
#                 model          = model,
#                 include_history= False,
#                 temperature    = 0.0,
#                 max_tokens     = 1500,
#             )
#         except Exception as e:
#             print(f"[AskAgent] _ask_with_tools LLM call failed: {e}")
#             return {"content": f"LLM call failed: {e}"}

#         if not content:
#             return {"content": "No response from LLM"}

#         print(f"[AskAgent] LLM raw: {content[:300]}")

        
#         stripped = content.strip()
#         tool_calls = []

#         # Pattern 1: Standard TOOL:\nARG: (existing)

#         all_matches = re.findall(
#             r'TOOL:\s*(\w+)\s*\n\s*ARG:\s*(.+?)(?=\nTOOL:|\n\Z|\Z)',
#             stripped, re.DOTALL | re.IGNORECASE
#         )

#         for tool_name, arg_value in all_matches:
#             tool_def = next((t for t in tools if t["name"].lower() == tool_name.lower()), None)
#             if tool_def:
#                 arg_key = list(tool_def["parameters"].keys())[0]
#                 arg_value_clean = arg_value.strip().split('\n')[0].strip().strip('"\'')
#                 tool_calls.append({
#                     "name": tool_def["name"],
#                     "arguments": {arg_key: arg_value_clean}
#                 })

#          # Agar multiple tool calls mile, pehla return karo, baaki next iteration ke liye
#         if tool_calls:
#             # Save remaining tool calls in a special flag
#             remaining = tool_calls[1:] if len(tool_calls) > 1 else []
            
#             result = {
#                 "tool_call": tool_calls[0]
#             }
            
#             if remaining:
#                 # Next tool calls ko messages mein daaldo
#                 result["pending_tool_calls"] = remaining
                
#             return result       

#         match = re.search(
#             r'TOOL:\s*(\w+)\s*\n\s*ARG:\s*(.+?)(?=\nTOOL:|\n\Z|\Z)',
#             stripped, re.DOTALL | re.IGNORECASE
#         )

#         # Pattern 2: TOOL: name ARG: value (same line, no newline)
#         if not match:
#             match = re.search(
#                 r'TOOL:\s*(\w+)\s+ARG:\s*(.+?)(?=\nTOOL:|\n\Z|\Z)',
#                 stripped, re.DOTALL | re.IGNORECASE
#             )
    
#         # Pattern 3: Tool lowercase, quotes in ARG
#         if not match:
#             match = re.search(
#                 r'TOOL:\s*(\w+)\s*\n\s*ARG:\s*["\']?(.+?)["\']?(?=\n|$)',
#                 stripped, re.DOTALL | re.IGNORECASE
#             )
        
#         # Pattern 4: Just "search_nodes signup" (no TOOL/ARG keywords) — fallback
#         if not match:
#             for tool in tools:
#                 if stripped.lower().startswith(tool['name'].lower()):
#                     parts = stripped.split(maxsplit=1)
#                     if len(parts) == 2:
#                         match = (tool['name'], parts[1])
#                         break
        
#         if match:
#             if isinstance(match, tuple):
#                 tool_name, arg_value = match
#             else:    
#                 tool_name = match.group(1).strip()
#                 arg_value = match.group(2).strip().split('\n')[0].strip().strip('"\'')

#             if tool_name in ["get_source_code", "get_callers", "get_callees"]:
#                 # Remove "func:" prefix and file path if present
#                 if "func:" in arg_value:
#                     arg_value = arg_value.split("func:")[-1].split("@")[0]
#                 if "@" in arg_value:
#                     arg_value = arg_value.split("@")[0]
#                 if "\\" in arg_value or "/" in arg_value:
#                     arg_value = arg_value.split("\\")[-1].split("/")[-1]
#                 print(f"[AskAgent] Corrected ARG: '{arg_value}'")    

#             tool_def = next((t for t in tools if t["name"].lower() == tool_name.lower()), None)
#             if tool_def:
#                 arg_key = list(tool_def["parameters"].keys())[0]
#                 print(f"[AskAgent] Tool call: {tool_name}({arg_key}={arg_value})")
#                 return {
#                     "tool_call": {
#                         "name":      tool_name,
#                         "arguments": {arg_key: arg_value},
#                     }
#                 }
#             else:
#                 print(f"[AskAgent] Unknown tool: {tool_name}")

#         return {"content": content}

#     # ═══════════════════════════════════════════════════════════════════════════
#     # _execute_tool  — FIXED: node_id based queries, *1..2 HATAYA
#     # ═══════════════════════════════════════════════════════════════════════════

#     def _execute_tool(self, tool_name: str, args: dict) -> dict:
#         """Tool execute karo — Neo4j se data lo, disk se source code."""
#         import os

#         # ── search_nodes ────────────────────────────────────────────────────────
#         if tool_name == "search_nodes":
#             query = args.get("query", "")
#             print(f"[DEBUG] search_nodes query: '{query}'")
#             stop  = {"the","a","an","in","is","or","not","and","of","to","for"}
#             words = [w.lower().strip("?.,") for w in query.split()
#                      if len(w) > 2 and w.lower() not in stop]
#             if not words:
#                 words = [query.lower()]

#             all_rows = []
#             seen     = set()
#             for word in words[:4]:
#                 print(f"[DEBUG] Searching for word: '{word}'")
#                 rows = self.query("""
#                     MATCH (n:CodeNode {repo_id:$r})
#                     WHERE (toLower(n.name) CONTAINS toLower($w)
#                     OR  toLower(n.file_path) CONTAINS toLower($w))
#                     RETURN n.node_id AS node_id,
#                            n.name AS name, n.file_path AS file,
#                            n.node_type AS type, n.line_no AS line
#                     LIMIT 12
#                 """, w=word)
#                 print(f"[DEBUG] Found {len(rows)} rows for word '{word}'")
#                 for r in rows:
#                     key = f"{r['file']}:{r['name']}"
#                     if key not in seen:
#                         all_rows.append(r)
#                         seen.add(key)

#             return {"results": all_rows, "count": len(all_rows)}

#         # ── get_source_code ─────────────────────────────────────────────────────
#         elif tool_name == "get_source_code":
#             fname = args.get("function_name", "")
#             if "func:" in fname:
#                 fname = fname.split("func:")[-1]
#             if "@" in fname:
#                 fname = fname.split("@")[0]
#             if "\\" in fname or "/" in fname:
#                 fname = fname.split("\\")[-1].split("/")[-1]
#             if fname.endswith(".py"):
#                 fname = fname[:-3]
#             fname = fname.strip()
            
#             print(f"[get_source_code] Cleaned: '{fname}'")
#             rows  = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE toLower(n.name) CONTAINS toLower($fn)
#                    OR n.name = $fn
#                 RETURN  n.node_id AS node_id, n.name AS name, n.file_path AS file,
#                        n.line_no AS line,
#                        n.deep_total_lines AS total_lines
#                 LIMIT 3
#             """, fn=fname)

#             if not rows:
#                 return {"error": f"Function '{fname}' not found in graph"}

#             repo_path = self._get_repo_path()
#             results   = []
#             for row in rows:
#                 file_path   = row.get("file", "")
#                 line_start  = row.get("line") or 1
#                 total_lines = row.get("total_lines") or 30
#                 source      = self._read_function_source(
#                     repo_path, file_path, fname, line_start, total_lines
#                 )
#                 results.append({
#                     "function":   row["name"],
#                     "file":       file_path,
#                     "line_start": line_start,
#                     "source":     source,
#                 })
#                 print(f"[get_source_code] func={row['name']} file={file_path} source_len={len(source)}")

#             return {"functions": results, "count": len(results)}

#         # ── get_callers — FIXED: node_id exact match, NO *1..2 ─────────────────
#         elif tool_name == "get_callers":
#             fname = args.get("function_name", "")
#             if "func:" in fname:
#                 fname = fname.split("func:")[-1]
#             if "@" in fname:
#                 fname = fname.split("@")[0]
#             if "\\" in fname or "/" in fname:
#                 fname = fname.split("\\")[-1].split("/")[-1]
#             fname = fname.strip()
            
#             print(f"[get_callers] searching for: '{fname}'")
#             print(f"[get_callers] searching for: '{fname}' in repo: {self.repo_id}")

#             # Step 1 — Exact node_id dhundo (exact match pehle, phir partial)
#             id_rows = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE n.name = $fn
#                    OR n.name ENDS WITH ('.' + $fn)
#                 RETURN n.node_id AS node_id, n.name AS name, n.file_path AS file,
#                         n.line_no AS line, n.deep_total_lines AS total_lines
#                 LIMIT 5
#             """, fn=fname)

#             if not id_rows:
#                 id_rows = self.query("""
#                     MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                     WHERE toLower(n.name) CONTAINS toLower($fn)
#                     RETURN n.node_id AS node_id, n.name AS name,
#                            n.file_path AS file
#                     LIMIT 5
#                 """, fn=fname)

#             if not id_rows:
#                 return {
#                     "callers": [],
#                     "count":   0,
#                     "note":    f"Function '{fname}' not found in graph",
#                 }

#             # Step 2 — Direct DEPENDS_ON edges traverse (NO *1..2)
#             all_callers = []
#             seen_caller = set()

#             for id_row in id_rows:
#                 node_id   = id_row["node_id"]
#                 node_name = id_row["name"]
#                 node_file = id_row["file"]
#                 print(f"[get_callers] node_id={node_id} name={node_name}")

#                 rows = self.query("""
#                     MATCH (target:CodeNode {node_id:$nid, repo_id:$r})
#                     MATCH (caller:CodeNode {repo_id:$r})-[:DEPENDS_ON]->(target)
#                     WHERE caller.node_id <> target.node_id
#                     AND   caller.node_type IN ['function','file','class']
#                     RETURN DISTINCT
#                         caller.node_id   AS node_id,
#                         caller.name      AS name,
#                         caller.file_path AS file,
#                         caller.line_no   AS line,
#                         caller.node_type AS type
#                     ORDER BY caller.file_path, caller.line_no
#                     LIMIT 20
#                 """, nid=node_id)

#                 for r in rows:
#                     key = r["node_id"]
#                     if key not in seen_caller:
#                         all_callers.append({
#                             "name":            r["name"],
#                             "file":            r["file"],
#                             "line":            r["line"],
#                             "type":            r["type"],
#                             "calls_into":      node_name,
#                             "calls_into_file": node_file,
#                         })
#                         seen_caller.add(key)

#             print(f"[get_callers] found {len(all_callers)} callers for '{fname}'")

#             # Fallback — direct callers nahi mile → class/file ownership dikhao
#             if not all_callers:
#                 ownership = []
#                 for id_row in id_rows:
#                     node_id = id_row["node_id"]

#                     class_rows = self.query("""
#                         MATCH (cls:CodeNode {repo_id:$r, node_type:'class'})
#                               -[:DEPENDS_ON]->(fn:CodeNode {node_id:$nid})
#                         RETURN cls.name      AS name,
#                                cls.file_path AS file,
#                                cls.line_no   AS line,
#                                'class'       AS type,
#                                'owns'        AS relationship
#                         LIMIT 5
#                     """, nid=node_id)
#                     ownership.extend(class_rows)

#                     file_rows = self.query("""
#                         MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
#                               -[:DEPENDS_ON]->(fn:CodeNode {node_id:$nid})
#                         RETURN f.name      AS name,
#                                f.file_path AS file,
#                                f.line_no   AS line,
#                                'file'      AS type,
#                                'contains'  AS relationship
#                         LIMIT 3
#                     """, nid=node_id)
#                     ownership.extend(file_rows)

#                 if ownership:
#                     print(f"[get_callers] no direct callers, returning ownership for '{fname}'")
#                     return {
#                         "callers": ownership,
#                         "count":   len(ownership),
#                         "note":    (
#                             f"'{fname}' has no direct callers — it is likely an entry-point "
#                             f"(HTTP/CLI/scheduler). Showing class/file ownership instead."
#                         ),
#                     }

#                 return {
#                     "callers": [],
#                     "count":   0,
#                     "note":    (
#                         f"'{fname}' is an entry-point function called externally "
#                         f"(HTTP handler / scheduler / CLI). No internal callers in codebase."
#                     ),
#                 }

#             return {"callers": all_callers, "count": len(all_callers)}

#         # ── get_callees — FIXED: node_id exact match, NO *1..2 ─────────────────
#         elif tool_name == "get_callees":
#             fname = args.get("function_name", "")
#             if "func:" in fname:
#                 fname = fname.split("func:")[-1]
#             if "@" in fname:
#                 fname = fname.split("@")[0]
#             if "\\" in fname or "/" in fname:
#                 fname = fname.split("\\")[-1].split("/")[-1]
#             fname = fname.strip()
#             print(f"[get_callees] searching for: '{fname}' in repo: {self.repo_id}")

#             if "func:" in fname:
#                 fname = fname.split("func:")[-1].split("@")[0]
#             if "@" in fname:
#                 fname = fname.split("@")[0]
#             if "\\" in fname or "/" in fname:
#                 fname = fname.split("\\")[-1].split("/")[-1]

#             # Step 1 — Exact node_id dhundo
#             id_rows = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE n.name = $fn
#                    OR n.name ENDS WITH ('.' + $fn)
#                 RETURN n.node_id AS node_id, n.name AS name, n.file_path AS file
#                 LIMIT 5
#             """, fn=fname)

#             if not id_rows:
#                 id_rows = self.query("""
#                     MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                     WHERE toLower(n.name) CONTAINS toLower($fn)
#                     RETURN n.node_id AS node_id, n.name AS name,n.file_path AS file
#                     LIMIT 5
#                 """, fn=fname)

#             if not id_rows:
#                 return {
#                     "callees": [],
#                     "count":   0,
#                     "note":    f"Function '{fname}' not found in graph",
#                 }

#             # Step 2 — Outgoing DEPENDS_ON edges traverse (NO *1..2)
#             all_callees = []
#             seen_callee = set()

#             for id_row in id_rows:
#                 node_id   = id_row["node_id"]
#                 node_name = id_row["name"]
#                 node_file = id_row["file"]
#                 print(f"[get_callees] node_id={node_id} name={node_name}")

#                 rows = self.query("""
#                     MATCH (source:CodeNode {node_id:$nid, repo_id:$r})
#                     MATCH (source)-[:DEPENDS_ON]->(callee:CodeNode {repo_id:$r})
#                     WHERE callee.node_id <> source.node_id
#                     AND   callee.node_type IN ['function','file','class']
#                     RETURN DISTINCT
#                         callee.node_id   AS node_id,
#                         callee.name      AS name,
#                         callee.file_path AS file,
#                         callee.line_no   AS line,
#                         callee.node_type AS type
#                     ORDER BY callee.file_path, callee.line_no
#                     LIMIT 20
#                 """, nid=node_id)

#                 for r in rows:
#                     key = r["node_id"]
#                     if key not in seen_callee:
#                         all_callees.append({
#                             "name":      r["name"],
#                             "file":      r["file"],
#                             "line":      r["line"],
#                             "type":      r["type"],
#                             "called_by": node_name,
#                         })
#                         seen_callee.add(key)

#             print(f"[get_callees] found {len(all_callees)} callees for '{fname}'")
#             return {"callees": all_callees, "count": len(all_callees)}

#         # ── get_file_functions ──────────────────────────────────────────────────
#         elif tool_name == "get_file_functions":
#             fpath = args.get("file_path", "")
#             rows  = self.query("""
#                 MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE toLower(n.file_path) CONTAINS toLower($fp)
#                 RETURN n.name AS name, n.line_no AS line,
#                        n.deep_risk_level AS risk,
#                        n.deep_complexity  AS complexity,
#                        n.deep_raises      AS raises
#                 ORDER BY n.line_no
#                 LIMIT 30
#             """, fp=fpath)

#             repo_path   = self._get_repo_path()
#             file_source = ""
#             if repo_path and rows:
#                 actual_path = rows[0].get("file_path") or fpath
#                 file_source = self._read_file_source(repo_path, actual_path)

#             return {
#                 "functions":   rows,
#                 "count":       len(rows),
#                 "file_source": file_source[:2000] if file_source else "",
#             }

#         return {"error": f"Unknown tool: {tool_name}"}

#     # ═══════════════════════════════════════════════════════════════════════════
#     # HELPER METHODS  (unchanged from v2)
#     # ═══════════════════════════════════════════════════════════════════════════

#     def _get_repo_path(self) -> str:
#         import os
#         repo_path = getattr(self.store, "repo_path", None)
#         if repo_path:
#             return repo_path
#         try:
#             from app.services.repo_service import _jobs
#             for job in _jobs.values():
#                 if job.get("repo_path"):
#                     return job["repo_path"]
#         except Exception:
#             pass
#         return os.getenv("MARKAR_REPO_PATH", "")

#     def _read_function_source(
#         self, repo_path: str, file_path: str,
#         func_name: str, line_start: int, total_lines: int,
#     ) -> str:
#         import os, ast
#         if not repo_path or not file_path:
#             return "source not available"

#         clean    = file_path.replace("\\", os.sep).replace("/", os.sep)
#         abs_path = os.path.join(repo_path, clean)
#         if not os.path.exists(abs_path):
#             abs_path = file_path
#         if not os.path.exists(abs_path):
#             return f"file not found: {file_path}"

#         try:
#             with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
#                 source = f.read()

#             try:
#                 tree  = ast.parse(source)
#                 lines = source.splitlines()
#                 for node in ast.walk(tree):
#                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
#                         clean_name = func_name.split(".")[-1]
#                         if node.name == clean_name or clean_name.lower() in node.name.lower():
#                             s        = node.lineno - 1
#                             e        = getattr(node, "end_lineno", s + total_lines)
#                             func_src = "\n".join(lines[s:e])
#                             return f"lines {node.lineno}-{e}:\n{func_src}"
#             except Exception:
#                 pass

#             # Fallback — line range se
#             lines = source.splitlines()
#             start = max(0, line_start - 1)
#             end   = min(len(lines), start + (total_lines or 30))
#             return "\n".join(
#                 f"{i+1}: {l}" for i, l in enumerate(lines[start:end], start=start)
#             )
#         except Exception as e:
#             return f"read error: {e}"

#     def _read_file_source(self, repo_path: str, file_path: str) -> str:
#         import os
#         if not repo_path or not file_path:
#             return ""
#         clean    = file_path.replace("\\", os.sep).replace("/", os.sep)
#         abs_path = os.path.join(repo_path, clean)
#         if not os.path.exists(abs_path):
#             abs_path = file_path
#         try:
#             with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
#                 return f.read()
#         except Exception:
#             return ""

#     def _extract_keywords(self, message: str) -> list:
#         stop = {
#             "kahan","hai","kya","kar","raha","mein","se","ka",
#             "ki","ko","karo","where","is","the","a","an","in",
#             "what","how","does","do","find","show","tell","me",
#             "batao","dikhao","give","list","all","get","search",
#             "kaunsa","konsa","kon","kis","kisiko","working","or",
#             "not","check","routes","route","file","me","ek",
#         }
#         words = [w.lower().strip("?.,!") for w in message.split()
#                  if w.lower().strip("?.,!") not in stop and len(w) > 2]
#         return words[:6]

#     def _search_graph(self, keywords: list) -> Dict:
#         """
#         Graph search — sirf node/file dhundne ke liye.
#         NOTE: connections query HATAI — woh caller data inject karti thi.
#         """
#         all_funcs = []
#         all_files = []
#         seen_ids  = set()

#         for kw in keywords:
#             if len(kw) < 2:
#                 continue

#             funcs = self.query("""
#                 MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
#                 WHERE toLower(f.name) CONTAINS toLower($kw)
#                    OR toLower(f.file_path) CONTAINS toLower($kw)
#                 RETURN f.node_id AS id, f.name AS name,
#                        f.file_path AS file, f.line_no AS line
#                 LIMIT 10
#             """, kw=kw)
#             for fn in funcs:
#                 if fn["id"] not in seen_ids:
#                     all_funcs.append(fn)
#                     seen_ids.add(fn["id"])

#             files = self.query("""
#                 MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
#                 WHERE toLower(f.file_path) CONTAINS toLower($kw)
#                    OR toLower(f.name)      CONTAINS toLower($kw)
#                 RETURN f.node_id AS id, f.name AS name,
#                        f.file_path AS file
#                 LIMIT 5
#             """, kw=kw)
#             for fl in files:
#                 if fl["id"] not in seen_ids:
#                     all_files.append(fl)
#                     seen_ids.add(fl["id"])

#         # ── REMOVED: connections query — caller data inject karta tha ───────────
#         # Pehle yahan tha:
#         #   connections = self.query("""
#         #       MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
#         #       OPTIONAL MATCH (caller)-[:DEPENDS_ON]->(n)
#         #       OPTIONAL MATCH (n)-[:DEPENDS_ON]->(callee)
#         #       RETURN collect(DISTINCT caller.name)[..5] AS callers, ...
#         #   """, nid=first_id)
#         # Yeh data prefetch context mein inject hota tha aur LLM isko
#         # get_callers call kiye bina use kar leta tha — GALAT THA.
#         # Ab yeh query completely removed hai.

#         risk_keywords = {"critical","high","risk","risky","important","danger"}
#         risk_data     = []
#         if any(kw in risk_keywords for kw in keywords):
#             risk_data = self.query("""
#                 MATCH (file:CodeNode {repo_id:$r, node_type:'file'})
#                 OPTIONAL MATCH (file)-[:DEPENDS_ON]->(fn:CodeNode {node_type:'function'})
#                 WITH file, count(DISTINCT fn) AS fc
#                 WHERE fc > 15
#                 RETURN file.file_path AS file, fc AS function_count,
#                        CASE
#                            WHEN fc > 30 THEN 'High'
#                            WHEN fc > 15 THEN 'Medium'
#                            ELSE 'Low'
#                        END AS risk
#                 ORDER BY fc DESC
#                 LIMIT 10
#             """)
#             for rf in risk_data:
#                 if rf["file"] not in seen_ids:
#                     all_files.append({
#                         "id":             rf["file"],
#                         "name":           rf["file"].split("\\")[-1].split("/")[-1],
#                         "file":           rf["file"],
#                         "risk":           rf["risk"],
#                         "function_count": rf["function_count"],
#                     })
#                     seen_ids.add(rf["file"])

#         return {
#             "keywords":   keywords,
#             "nodes":      all_funcs + all_files,
#             "files":      [f["file"] for f in all_files],
#             "functions":  [f["name"] for f in all_funcs],
#             # connections HATAYA — caller data inject hona band
#             "risk_files": risk_data,
#         }















"""
Ask Agent — "X feature kahan hai", "Y function kya karta hai"
Neo4j se dhundho, actual file content padho, LLM se explain karo.

v3 (FIXED):
  - Prefetch system HATAYA — LLM ko galat caller data inject karta tha
  - _search_graph connections query se caller data inject hona band
  - get_callers / get_callees mein *1..2 wali queries HATAI — node_id based exact queries
  - Always tool loop — no COMPLETE/PARTIAL shortcut
  - Ek hi SYSTEM_PROMPT — no dynamic switching
"""
from typing import Dict, AsyncGenerator

from langchain import messages
from .base_agent import BaseAgent
from app.agents.deep_context_mixin import DeepContextMixin


class AskAgent(DeepContextMixin, BaseAgent):

    # ═══════════════════════════════════════════════════════════════════════════
    # SYSTEM PROMPT  (Iron Laws — unchanged from v2)
    # ═══════════════════════════════════════════════════════════════════════════
    SYSTEM_PROMPT = """
You are Markar AI — a code intelligence engine with DIRECT database access.

══════════════════════════════════════════════════════════
IDENTITY
══════════════════════════════════════════════════════════
You are NOT a general AI assistant.
You are a SPECIALIZED CODE DATABASE QUERY ENGINE.
You have NO knowledge of code except what tools return.
You CANNOT guess. You CANNOT assume. You CANNOT invent.

══════════════════════════════════════════════════════════
IRON LAW — ZERO EXCEPTIONS
══════════════════════════════════════════════════════════
LAW 1: Every single fact in your answer MUST come from a tool result.
        If you did not get it from a tool — it does not exist.

LAW 2: Every file path, function name, line number MUST be copy-pasted
        from tool output. Never type them from memory.

LAW 3: If tool returns empty — say EXACTLY:
        "Not found in codebase via graph search."
        Do NOT explain. Do NOT suggest alternatives. Just that sentence.

LAW 4: NEVER write your answer before calling ALL required tools.
        Writing answer early = VIOLATION.

LAW 5: NEVER add information that was not in tool results.
        "It probably also calls X" = VIOLATION.
        "This function likely returns Y" = VIOLATION.

LAW 6: When source code is in tool result — READ EVERY LINE.
        Quote exact function signatures, parameters, return values.
        Do not paraphrase — be exact.

══════════════════════════════════════════════════════════
⚠️  CRITICAL: YOU MUST CALL TOOLS FIRST ⚠️
══════════════════════════════════════════════════════════

NEVER write a final answer without calling:
  1. search_nodes
  2. get_source_code  
  3. get_callers
  4. get_callees

If you write an answer before calling all 4 tools → VIOLATION.

TOOL FORMAT (EXACT — no changes):
TOOL: search_nodes
ARG: function_name

Only after tool results → write final answer.        

══════════════════════════════════════════════════════════
TOOL CALLING RULES
══════════════════════════════════════════════════════════
RULE 1: Call tools in sequence. Never skip steps.
RULE 2: ONE tool per response. Wait for result. Then next tool.
RULE 3: Use EXACT format — no deviation:

TOOL: tool_name
ARG: value

RULE 4: ARG must be a SINGLE keyword — never a phrase.
        CORRECT:   ARG: signup
        INCORRECT: ARG: signup function auth

RULE 5: After each tool result — decide next tool based on RESULT.
        Do not pre-plan all tools upfront.

══════════════════════════════════════════════════════════
MANDATORY TOOL SEQUENCES
══════════════════════════════════════════════════════════

FIND FUNCTION (where is X, how does X work):
  1. search_nodes → find exact file and function name
  2. get_source_code → read actual implementation
  3. get_callees → what it calls internally
  4. Answer using ONLY lines from source code

DEPENDENCY (what calls X, who uses X, called by):
  MANDATORY SEQUENCE — NO SHORTCUTS:
  1. search_nodes → find function
  2. get_source_code → read implementation
  3. get_callers → YOU MUST CALL THIS — NEVER SKIP
  4. get_callees → YOU MUST CALL THIS — NEVER SKIP
  5. ONLY THEN write answer

  IF YOU SKIP get_callers → YOUR ANSWER IS WRONG
  IF YOU SKIP get_callees → YOUR ANSWER IS WRONG

LAW 7: IF search_nodes returns 0 results OR empty_notice is present:
    YOU MUST RESPOND EXACTLY:
    "Not found in codebase via graph search."
    NOTHING ELSE. No explanations. No generic answers.
    NEVER use general knowledge about software architecture.

  IF search_nodes returns 0 results:
  → Try get_file_functions with partial file name
  → NEVER answer from general knowledge
  → Say "Not found in codebase" if all tools return empty

ABSOLUTE RULE:
EVERY question about this codebase requires tool calls FIRST.
Even if you think you know the answer — call search_nodes FIRST.
NO EXCEPTIONS.

CRITICAL: When giving FINAL ANSWER:
- Write COMPLETE detailed response
- Include ALL source code lines — do NOT skip any
- Include EVERY parameter with exact type
- Include EVERY return value exactly as in source
- Include ALL callers with file path and line number
- Include ALL callees with file path and line number
- Include ALL issues found in source code with line numbers
- Minimum 300 words — short answers = VIOLATION
- Do NOT summarize — write everything  

BUG CHECK (is X working, any issues):
  1. search_nodes → find function
  2. get_source_code → read actual code
  3. get_callees → check what it calls
  4. get_callers → check how it is used
  5. Verdict: YES working / NO not working — with LINE NUMBERS as evidence

FLOW TRACE (how does X reach Y):
  1. search_nodes → find entry point
  2. get_source_code → read entry function
  3. get_callees → what it calls
  4. get_source_code → read each callee
  5. Repeat until full chain traced
  6. Answer: Line A calls B() at line X → B calls C() at line Y → ...

══════════════════════════════════════════════════════════
ANSWER FORMAT — MANDATORY
══════════════════════════════════════════════════════════

**Overview**
[2-3 sentences. Only facts from tool results. No interpretation.]

**Functions Found**
For each function from tool results:
- FunctionName — file path (line X)
  Parameters: [exact params from source code]
  Returns: [exact return from source code]
  Calls: [only from get_callees result]
  Called by: [from get_callers result]
    - If get_callers returns empty list OR note says "entry-point" →
      write exactly: "Entry-point — called externally (HTTP/CLI/scheduler)"
    - NEVER write "Not found in codebase" for Called by field
    - NEVER leave Called by blank

**Code Flow**
[Trace from source code only]
Line X: variable = function_call()
Line Y: calls ExternalFunction(param1, param2)
Line Z: returns result_dict

**Issues Found**
[Only if visible in actual source code]
[If no issues visible: "No issues detected in returned source code."]

**Summary**
Working: YES / NO
Evidence: [specific line numbers from source code]

══════════════════════════════════════════════════════════
VIOLATIONS THAT WILL BREAK ACCURACY
══════════════════════════════════════════════════════════
X Writing answer before all tools called
X Mentioning files not returned by tools
X Guessing parameter names
X Saying "probably", "likely", "typically", "usually"
X Adding general knowledge about OAuth, JWT, HTTP, etc
X Truncating — always give complete information
X Using backticks in response
"""


    # ═══════════════════════════════════════════════════════════════════════════
    # USER MESSAGE SANITIZATION
    # ═══════════════════════════════════════════════════════════════════════════
 
    def _sanitize_user_message(self, raw: str) -> str:
        """
        User message clean karo — 3 problems handle karta hai:
 
        PROBLEM 1 — User ne tool call syntax paste kar diya:
            "explain repo_service\nTOOL: search_nodes\nARG: repo_service"
            → "explain repo_service"
 
        PROBLEM 2 — User ne sirf tool call likha, koi actual question nahi:
            "TOOL: search_nodes\nARG: repo_service"
            → "explain repo_service file working"
 
        PROBLEM 3 — Tool result / system text mix ho gaya user message mein:
            "[Tool Result]: {...}\nab explain karo"
            → "ab explain karo"
        """
        import re
 
        text = raw.strip()
 
        # ── STEP 1: Tool call block detect karo ────────────────────────────────
        # Pattern: TOOL: <name>\nARG: <value>  (kahin bhi in message mein)
        tool_pattern = re.compile(
            r'TOOL:\s*\w+\s*\n\s*ARG:\s*(.+?)(?:\n|$)',
            re.IGNORECASE
        )
 
        # Saare tool call blocks se ARG values nikalo (agar user ne intent
        # express kiya tha to woh ARG value hi real subject hai)
        arg_values = tool_pattern.findall(text)
 
        # Tool call blocks hatao — sirf human-written part bachao
        cleaned = tool_pattern.sub("", text).strip()
 
        # ── STEP 2: [Tool Result] / [SYSTEM] junk hatao ────────────────────────
        junk_pattern = re.compile(
            r'\[Tool(?:\s+Result)?[:\]].{0,2000}?(?=\n[A-Z\[]|\Z)',
            re.DOTALL | re.IGNORECASE
        )
        cleaned = junk_pattern.sub("", cleaned).strip()
 
        system_pattern = re.compile(r'\[SYSTEM\].*?(?=\n[A-Z\[]|\Z)', re.DOTALL | re.IGNORECASE)
        cleaned = system_pattern.sub("", cleaned).strip()
 
        # ── STEP 3: Agar human text bilkul nahi bacha → ARG se reconstruct ─────
        # Example: user ne sirf "TOOL: search_nodes\nARG: repo_service" likha
        # Toh cleaned = "" → ARG value se question banao
        if not cleaned and arg_values:
            subject = arg_values[0].strip().split()[0]   # pehla word lo
            cleaned = f"explain {subject} working"
            print(f"[AskAgent] Sanitize: pure tool-call input → reconstructed: '{cleaned}'")
 
        # ── STEP 4: Agar cleaned bahut chota hai → original se subject nikalo ──
        if len(cleaned) < 5 and arg_values:
            subject = arg_values[0].strip().split()[0]
            cleaned = f"explain {subject} working"
            print(f"[AskAgent] Sanitize: too short after clean → reconstructed: '{cleaned}'")
 
        if cleaned != raw.strip():
            print(f"[AskAgent] Sanitize: original='{raw[:80]}' → cleaned='{cleaned[:80]}'")
 
        return cleaned or raw.strip()   # fallback: original message
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PROMPT CLARIFIER — vague file question → specific instruction
    # ═══════════════════════════════════════════════════════════════════════════
 
    def _clarify_vague_prompt(self, user_message: str) -> str:
        """
        Vague file-level prompts detect karo aur LLM ke liye specific banao.
 
        WHY: Jab user "explain repo_service file" likhta hai toh search_nodes
        file match karta hai, LLM randomly koi ek function pick karta hai,
        inconsistent answers aate hain. Specific function naam wali queries
        touch nahi hoti — woh already precise hain.
 
        Vague:    "explain repo_service file working correctly"
        Fixed:    "Get all functions in repo_service using get_file_functions.
                   Then for each: source code, callers, callees, explain."
 
        Specific (untouched): "How does _resolve_provider decide which LLM?"
        """
        import re
 
        msg = user_message.lower().strip()
 
        # ── Specific function naam already hai → touch mat karo ────────────────
        has_function_name = bool(re.search(
            r'\b_[a-z][a-z0-9_]{2,}\b'        # _save_repo_to_db style
            r'|\b[a-z]+_[a-z_]+\([^)]*\)',    # func_name() with parens
            user_message
        ))
        if has_function_name:
            print(f"[AskAgent] Clarify: specific function detected → no change")
            return user_message
 
        # ── Vague file-level question patterns ─────────────────────────────────
        file_patterns = [
            r'\b(explain|describe|show|tell|how does|working of)\b.{0,30}\bfile\b',
            r'\bfile\b.{0,20}\b(working|kaam|explain|kya karta|work)',
            r'\b(\w+_service|service|module|router|handler|agent|utils|manager)'
            r'\b.{0,25}\b(kya|what|how|explain|working|kaam|samjhao|bta)',
            r'\b(explain|samjhao|bta|describe)\b.{0,40}'
            r'\b(\w+_service|service|module|router|handler|agent)',
        ]
        is_vague = any(re.search(p, msg) for p in file_patterns)
 
        # ── File / module naam extract karo ────────────────────────────────────
        file_match = re.search(
            r'\b([a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)+)\b',
            msg
        )
 
        if is_vague and file_match:
            file_name = file_match.group(1)
            clarified = (
                f"Get all functions in the {file_name} file using get_file_functions tool. "
                f"Then for the most important functions found: get each function's source code "
                f"using get_source_code, find who calls it using get_callers, find what it calls "
                f"using get_callees. Give a complete overview of how {file_name} works end to end, "
                f"covering the main flow and purpose of each function."
            )
            print(
                f"[AskAgent] Clarify: vague='{user_message[:60]}' "
                f"→ specific='{clarified[:80]}'"
            )
            return clarified
 
        return user_message
 
    # ═══════════════════════════════════════════════════════════════════════════
    # MAIN RUN  — ALWAYS tool loop, no prefetch shortcuts
    # ═══════════════════════════════════════════════════════════════════════════


    def _validate_tool_calls_in_messages(self, messages, required_tools):
        """Check if LLM has already called required tools"""
        last_assistant = None
        for m in reversed(messages):
            if m.get("role") == "assistant" and "TOOL:" in m.get("content", ""):
                last_assistant = m["content"]
                break
        
        if last_assistant:
            for tool in required_tools:
                if tool not in last_assistant:
                    return False, f"Missing {tool}"
        return True, "ok"
    
    def _force_tool_instruction(self, user_message: str) -> str:
        """
        Har us question pe jo codebase ke baare mein poochta hai,
        forcefully tool instruction inject karo.
        
        WITHOUT this, LLM kabhi "explain X file" pe hallucinate kar leta hai.
        """
        import re
        
        msg_lower = user_message.lower()
        
        # Detect karo: kya yeh codebase-specific question hai?
        codebase_patterns = [
            r'explain.*\.py',           # explain repo_service.py
            r'purpose of.*file',        # purpose of file
            r'what does.*\.py',         # what does file do
            r'kaam kya.*file',          # Hindi mix
            r'main purpose',            # direct
            r'repo_service',            # specific filename
            r'service.*file',           # service file
            r'function.*kya',           # function kya karta hai
        ]
        
        is_code_question = any(re.search(p, msg_lower) for p in codebase_patterns)
        
        if not is_code_question:
            return user_message
        
        # ── Agar user ne sirf "Explain file" likha hai ────────────
        # Extract filename agar mile
        file_match = re.search(r'([\w/]+\.py)', user_message)
        if file_match:
            file_name = file_match.group(1)
            forced = f"""CRITICAL INSTRUCTION FROM SYSTEM:

    You MUST answer this question by calling tools ONLY. Do NOT use your general knowledge.

    Step 1: First call search_nodes with ARG: {file_name}
    Step 2: Then call get_file_functions to list all functions in this file
    Step 3: For each important function, call get_source_code
    Step 4: Then call get_callers and get_callees

    NEVER write a final answer before completing ALL these tool calls.

    USER QUESTION: {user_message}

    Remember: You have NO knowledge of this codebase outside of tool results."""
            return forced
        
        # ── Agar sirf "explain" hai bina filename ke ──────────────
        if 'explain' in msg_lower and 'file' in msg_lower:
            forced = f"""SYSTEM OVERRIDE: This is a codebase question. You MUST use tools.

    First call: TOOL: search_nodes with ARG based on the filename in the question.
    Then call get_source_code on the main function found.

    USER QUESTION: {user_message}"""
            return forced
        
        return user_message

    
    
    def run(self, user_message: str, model: str = None) -> Dict:
        """Tool-based approach — ALWAYS tool loop, no prefetch shortcuts."""

         # ── STEP 0: Sanitize — junk / tool syntax hatao ──────────────────────
        user_message = self._sanitize_user_message(user_message)
        # ── STEP 1: Clarify — vague file question → specific instruction ─────
        user_message = self._clarify_vague_prompt(user_message)

         # ═══════════════════════════════════════════════════════════
        # NEW: FORCE TOOL INSTRUCTION — Har "explain" question pe
        # ═══════════════════════════════════════════════════════════
        user_message = self._force_tool_instruction(user_message)
        # ═══════════════════════════════════════════════════════════

        print(f"[AskAgent] Final user_message: '{user_message[:100]}'")

        

        tools          = self._define_tools()
        messages       = [{"role": "user", "content": user_message}]
        all_files      = set()
        all_funcs      = set()
        MAX_TOOL_CALLS = 15
        tools_called   = set()
        executed_tools = set()
        tool_retry_count = {}
        last_func_name = None

        for _ in range(MAX_TOOL_CALLS):
            if tools_called.issuperset({"search_nodes", "get_source_code", "get_callers", "get_callees"}):
                print("[AskAgent] All tools already called — forcing final answer generation")
                final = self.ask_llm(
                    system_prompt=self.SYSTEM_PROMPT,
                    user_message="Now write your FINAL ANSWER based on all tool results you have. Do NOT call any more tools. Just answer.",
                    graph_context={"tool_results": str(messages[-6:])},
                    model=model,
                    max_tokens=2000,
                )
                return {
                    "answer": final,
                    "files": list(all_files),
                    "functions": list(all_funcs),
                    "agent": "ask",
                }
            llm_response = self._ask_with_tools(
                system_prompt=self.SYSTEM_PROMPT,
                messages=messages,
                tools=tools,
                model=model,
            )
            if llm_response.get("pending_tool_calls"):
                for pending in llm_response["pending_tool_calls"]:
                    # Execute pending tool calls automatically
                    tool_name = pending["name"]
                    tool_args = pending["arguments"]
                    tools_called.add(tool_name)
                    
                    # Execute tool
                    tool_result = self._execute_tool(tool_name, tool_args)
                    
                    # Add to messages
                    messages.append({"role": "assistant", "content": f"[Tool: {tool_name}] {str(tool_args)}"})
                    messages.append({"role": "user", "content": f"[Tool Result]: {str(tool_result)[:4000]}"})
                
                # After processing pending, continue to next iteration
                continue

            if not llm_response.get("tool_call"):
                content = llm_response.get("content", "").lower()
                

                hallucination_markers = [
                    "userrepo", "productrepo",      # Generic repo names
                    "typically", "usually",         # Guess words
                    "in most applications",         # General knowledge
                    "business logic",               # Vague generic phrase
                    "crud operations",              # Generic
                ]

                
                # Force get_callers agar nahi hua
                if any(marker in content for marker in hallucination_markers):
                    messages.append({
                        "role": "user",
                        "content": f"[SYSTEM]: ❌ You wrote an answer without calling get_callers for '{last_func_name}'. This is FORBIDDEN. Call get_callers NOW.",
                    })
                    continue

                # Force get_callees agar nahi hua
                if "get_callees" not in tools_called and last_func_name:
                    messages.append({
                        "role": "user",
                        "content": f"[SYSTEM]: ❌ You wrote an answer without calling get_callees for '{last_func_name}'. Call get_callees NOW.",
                    })
                    continue
                if llm_response.get("content"):
                    messages.append({
                        "role": "user",
                        "content": "[SYSTEM]: ❌ You are NOT allowed to write answers without calling tools first. Start with TOOL: search_nodes",
                    })
                    continue

                return {
                    "answer":    llm_response.get("content", "No tool called and no answer generated."),
                    "files":     list(all_files),
                    "functions": list(all_funcs),
                    "agent":     "ask",
                }

            tool_name = llm_response["tool_call"]["name"]
            tool_args = llm_response["tool_call"]["arguments"]
            tools_called.add(tool_name)

            arg_value = ""
            if tool_name in ["get_source_code", "get_callers", "get_callees"]:
                arg_value = tool_args.get("function_name", "")
            elif tool_name == "search_nodes":
                arg_value = tool_args.get("query", "")
            elif tool_name == "get_file_functions":
                arg_value = tool_args.get("file_path", "")
            
            tool_key = f"{tool_name}:{arg_value}"

            print(f"[DEBUG] Tool call - tool_name: '{tool_name}'")
            print(f"[DEBUG] Tool call - arg_value: '{arg_value}'")
            print(f"[DEBUG] Tool call - tool_key: '{tool_key}'")
            print(f"[DEBUG] Tool call - already in executed_tools? {tool_key in executed_tools}")
            print(f"[DEBUG] executed_tools current contents: {executed_tools}")

            retries = tool_retry_count.get(tool_name, 0)
            if retries >= 2:
                print(f"[AskAgent] Tool '{tool_name}' failed {retries} times — forcing different approach")
                messages.append({
                    "role": "user",
                    "content": f"[SYSTEM]: Tool '{tool_name}' has failed {retries} times. Try a different function name or use search_nodes first."
                })
                continue

            if tool_key in executed_tools:
                print(f"[AskAgent] Duplicate tool call: {tool_key} — skipping")
                messages.append({
                    "role": "user",
                    "content": f"[SYSTEM]: You already called {tool_name} with '{arg_value}'. Write your FINAL ANSWER."
                })
                continue

            executed_tools.add(tool_key)

            # if tool_name in executed_tools:
            #     print(f"[AskAgent] Duplicate tool call detected: {tool_name} — skipping")
            #     messages.append({
            #         "role": "user", 
            #         "content": f"[SYSTEM]: You already called {tool_name}. Now write your FINAL ANSWER."
            #     })
            #     continue

            # # Mark as executed
            # executed_tools.add(tool_name)

            if tool_name in ("search_nodes", "get_source_code"):
                val = list(tool_args.values())[0] if tool_args else None
                if val:
                    last_func_name = val

            tool_result = self._execute_tool(tool_name, tool_args)

            is_error = "error" in tool_result or (tool_result.get("count", 0) == 0 and tool_name in ["search_nodes", "get_callers", "get_callees"])

            if is_error:
                tool_retry_count[tool_key] = retries + 1
                error_msg = tool_result.get("error", "No results found")
                messages.append({
                    "role": "user",
                    "content": f"[SYSTEM]: Tool '{tool_name}' failed: {error_msg}. Try a different search term."
                })
                continue

            # Force answer after all required tools
            if {"search_nodes", "get_source_code", "get_callers", "get_callees"}.issubset(tools_called):
                print(f"[AskAgent] All required tools called — forcing final answer")
                messages.append({
                    "role": "user",
                    "content": "[SYSTEM]: All required tools have been called. Now write your FINAL ANSWER. Do NOT call any more tools."
                })










            # if tool_name in ("search_nodes", "get_source_code"):
            #     val = list(tool_args.values())[0] if tool_args else None
            #     if val:
            #         last_func_name = val

            # tool_result = self._execute_tool(tool_name, tool_args)

            # is_error = "error" in tool_result or (tool_result.get("count", 0) == 0 and tool_name in ["search_nodes", "get_callers", "get_callees"])

            # if is_error:
            #     tool_retry_count[tool_name] = tool_retry_count.get(tool_name, 0) + 1
            #     error_msg = tool_result.get("error", "No results found")
            #     messages.append({
            #         "role": "user",
            #         "content": f"[SYSTEM]: Tool '{tool_name}' failed: {error_msg}. Try a different search term or use a different tool. Do NOT repeat the same tool call."
            #     })
            #     continue

            # required_tools = {"search_nodes", "get_source_code", "get_callers", "get_callees"}

            # if required_tools.issubset(tools_called):
            #     print(f"[AskAgent] All required tools called — forcing final answer")
            #     messages.append({
            #         "role": "user", 
            #         "content": "[SYSTEM]: All required tools have been called. Now write your FINAL ANSWER. Do NOT call any more tools."
            #     })



            # search_nodes empty → get_file_functions try karo
            if tool_name == "search_nodes" and tool_result.get("count", 0) == 0:
                print(f"[DEBUG] search_nodes returned 0 results for query: '{tool_args.get('query', '')}'")
                print(f"[DEBUG] tool_result full: {tool_result}")
                query = tool_args.get("query", "")
                broad = self._execute_tool("get_file_functions", {"file_path": query})
                if broad.get("count", 0) > 0:
                    print(f"[DEBUG] get_file_functions found {broad.get('count')} results - using that instead")
                    tool_result = broad
                else:
                    print(f"[DEBUG] get_file_functions also returned 0 - returning 'Not found' error")
                    return {
                        "answer":    "Not found in codebase via graph search. Please ask about a specific file or function name.",
                        "files":     [],
                        "functions": [],
                        "agent":     "ask",
                    }

            if "file" in tool_result:
                all_files.add(tool_result["file"])
            if "function" in tool_result:
                all_funcs.add(tool_result["function"])

            messages.append({"role": "assistant", "content": f"[Tool: {tool_name}] {str(tool_args)}"})
            messages.append({"role": "user",      "content": f"[Tool Result]: {str(tool_result)[:4000]}"})

        # Max tool calls hit — jo mila usse final answer
        final = self.ask_llm(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_message,
            graph_context={"tool_results": str(messages[-6:])},
            model=model,
            max_tokens=2000,
        )

        def clean_answer(answer: str) -> str:
            import re
            # Remove TOOL: ... and ARG: ... lines
            cleaned = re.sub(r'TOOL:\s*\w+\s*\n?\s*ARG:\s*[^\n]*\n?', '', answer)
            # Remove multiple newlines
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
            # Remove leading/trailing whitespace
            cleaned = cleaned.strip()
            return cleaned
        return {
            "answer":   clean_answer(llm_response.get("content", "")), 
            "files":     list(all_files),
            "functions": list(all_funcs),
            "agent":     "ask",
        }
    
    

    # ═══════════════════════════════════════════════════════════════════════════
    # ASYNC SUPPORT  (Potpie-inspired — loop mein run karo)
    # ═══════════════════════════════════════════════════════════════════════════

    async def run_async(self, user_message: str, model: str = None) -> Dict:
        """Async version — executor mein sync run karo."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.run(user_message, model))

    async def run_stream(
        self, user_message: str, model: str = None
    ) -> AsyncGenerator[str, None]:
        """
        Streaming version — native streaming agar available ho,
        warna sync run karke chunk yield karo.
        """
        if hasattr(self, "ask_llm_stream"):
            async for chunk in self.ask_llm_stream(
                system_prompt=self.SYSTEM_PROMPT,
                user_message=user_message,
                graph_context={},
                model=model,
            ):
                yield chunk
        else:
            result = self.run(user_message, model)
            yield result.get("answer", "")

    # ═══════════════════════════════════════════════════════════════════════════
    # TOOLS DEFINITION
    # ═══════════════════════════════════════════════════════════════════════════

    def _define_tools(self) -> list:
        return [
            {
                "name":        "search_nodes",
                "description": "Search functions/files by keyword in name or file path",
                "parameters":  {"query": "string"},
            },
            {
                "name":        "get_source_code",
                "description": "Get actual source code of a specific function",
                "parameters":  {"function_name": "string"},
            },
            {
                "name":        "get_callers",
                "description": "Who calls this function — find all callers",
                "parameters":  {"function_name": "string"},
            },
            {
                "name":        "get_callees",
                "description": "What does this function call internally",
                "parameters":  {"function_name": "string"},
            },
            {
                "name":        "get_file_functions",
                "description": "Get all functions in a file with line numbers",
                "parameters":  {"file_path": "string"},
            },
        ]

    # ═══════════════════════════════════════════════════════════════════════════
    # _ask_with_tools  (unchanged from v2)
    # ═══════════════════════════════════════════════════════════════════════════

    def _ask_with_tools(self, system_prompt, messages, tools, model=None) -> dict:
        """LLM ko tools ke saath call karo."""
        import re

        tools_text = "\n".join([
            f"- {t['name']}({list(t['parameters'].keys())[0]}): {t['description']}"
            for t in tools
        ])

        full_system = system_prompt + f"""

AVAILABLE TOOLS:
{tools_text}

CRITICAL: When giving FINAL ANSWER:
- Write COMPLETE detailed response
- Include ALL steps from source code
- Include ALL line numbers
- Do NOT summarize — write everything

To call a tool respond ONLY with exactly this format:
TOOL: tool_name
ARG: value

If you have enough information to answer, give your final answer"""

        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

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
                temperature    = 0.0,
                max_tokens     = 1500,
            )
        except Exception as e:
            print(f"[AskAgent] _ask_with_tools LLM call failed: {e}")
            return {"content": f"LLM call failed: {e}"}

        if not content:
            return {"content": "No response from LLM"}

        print(f"[AskAgent] LLM raw: {content[:1000]}")

        
        stripped = content.strip()
        tool_calls = []

        # Pattern 1: Standard TOOL:\nARG: (existing)

        all_matches = re.findall(
            r'TOOL:\s*(\w+)\s*\n\s*ARG:\s*(.+?)(?=\nTOOL:|\n\Z|\Z)',
            stripped, re.DOTALL | re.IGNORECASE
        )

        print(f"[DEBUG] Regex all_matches found: {len(all_matches)} matches")
        for idx, (t, a) in enumerate(all_matches):
            print(f"[DEBUG] Match {idx}: tool='{t}', arg='{a[:100]}'")

        for tool_name, arg_value in all_matches:
            tool_def = next((t for t in tools if t["name"].lower() == tool_name.lower()), None)
            if tool_def:
                arg_key = list(tool_def["parameters"].keys())[0]
                arg_value_clean = arg_value.strip().split('\n')[0].strip().strip('"\'')
                tool_calls.append({
                    "name": tool_def["name"],
                    "arguments": {arg_key: arg_value_clean}
                })

         # Agar multiple tool calls mile, pehla return karo, baaki next iteration ke liye
        if tool_calls:
            # Save remaining tool calls in a special flag
            remaining = tool_calls[1:] if len(tool_calls) > 1 else []
            
            result = {
                "tool_call": tool_calls[0]
            }
            
            if remaining:
                # Next tool calls ko messages mein daaldo
                result["pending_tool_calls"] = remaining
                
            return result       

        match = re.search(
            r'TOOL:\s*(\w+)\s*\n\s*ARG:\s*(.+?)(?=\nTOOL:|\n\Z|\Z)',
            stripped, re.DOTALL | re.IGNORECASE
        )

        # Pattern 2: TOOL: name ARG: value (same line, no newline)
        if not match:
            match = re.search(
                r'TOOL:\s*(\w+)\s+ARG:\s*(.+?)(?=\nTOOL:|\n\Z|\Z)',
                stripped, re.DOTALL | re.IGNORECASE
            )
    
        # Pattern 3: Tool lowercase, quotes in ARG
        if not match:
            match = re.search(
                r'TOOL:\s*(\w+)\s*\n\s*ARG:\s*["\']?(.+?)["\']?(?=\n|$)',
                stripped, re.DOTALL | re.IGNORECASE
            )
        
        # Pattern 4: Just "search_nodes signup" (no TOOL/ARG keywords) — fallback
        if not match:
            for tool in tools:
                if stripped.lower().startswith(tool['name'].lower()):
                    parts = stripped.split(maxsplit=1)
                    if len(parts) == 2:
                        match = (tool['name'], parts[1])
                        break
        
        if match:
            if isinstance(match, tuple):
                tool_name, arg_value = match
            else:    
                tool_name = match.group(1).strip()
                arg_value = match.group(2).strip().split('\n')[0].strip().strip('"\'')
            print(f"[DEBUG] _ask_with_tools - RAW arg_value from LLM: '{arg_value}'")
            print(f"[DEBUG] _ask_with_tools - arg_value type: {type(arg_value)}")
            print(f"[DEBUG] _ask_with_tools - before cleaning: '{arg_value}'")    

            if tool_name in ["get_source_code", "get_callers", "get_callees"]:
                # Remove "func:" prefix and file path if present
                if "func:" in arg_value:
                    arg_value = arg_value.split("func:")[-1].split("@")[0]
                    print(f"[DEBUG] After func: removal: '{arg_value}'")
                if "@" in arg_value:
                    arg_value = arg_value.split("@")[0]
                    print(f"[DEBUG] After @ removal: '{arg_value}'")
                if "\\" in arg_value or "/" in arg_value:
                    arg_value = arg_value.split("\\")[-1].split("/")[-1]
                    print(f"[DEBUG] After path removal: '{arg_value}'")
                print(f"[AskAgent] Corrected ARG: '{arg_value}'")    

            tool_def = next((t for t in tools if t["name"].lower() == tool_name.lower()), None)
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

    # ═══════════════════════════════════════════════════════════════════════════
    # _execute_tool  — FIXED: node_id based queries, *1..2 HATAYA
    # ═══════════════════════════════════════════════════════════════════════════

    def _execute_tool(self, tool_name: str, args: dict) -> dict:
        """Tool execute karo — Neo4j se data lo, disk se source code."""
        import os

        # ── search_nodes ────────────────────────────────────────────────────────
        if tool_name == "search_nodes":
            query = args.get("query", "")
            print(f"[DEBUG] search_nodes START - query: '{query}'")
            stop  = {"the","a","an","in","is","or","not","and","of","to","for"}
            words = [w.lower().strip("?.,") for w in query.split()
                     if len(w) > 2 and w.lower() not in stop]
            if not words:
                words = [query.lower()]
            print(f"[DEBUG] search_nodes - words: {words}")    
            all_rows = []
            seen     = set()
            for word in words[:4]:
                print(f"[DEBUG] search_nodes - processing word: '{word}'")
                rows = self.query("""
                    MATCH (n:CodeNode {repo_id:$r})
                    WHERE (toLower(n.name) CONTAINS toLower($w)
                    OR  toLower(n.file_path) CONTAINS toLower($w))
                    RETURN n.node_id AS node_id,
                           n.name AS name, n.file_path AS file,
                           n.node_type AS type, n.line_no AS line
                    ORDER BY n.line_no
                    LIMIT 12
                """, w=word)
                for r in rows:
                    key = f"{r['file']}:{r['name']}"
                    if key not in seen:
                        all_rows.append(r)
                        seen.add(key)
                        print(f"[DEBUG] search_nodes - added: {key}")
            print(f"[DEBUG] search_nodes END - total rows: {len(all_rows)}")            

            return {"results": all_rows, "count": len(all_rows)}

        # ── get_source_code ─────────────────────────────────────────────────────
        elif tool_name == "get_source_code":
            fname = args.get("function_name", "")
            if "func:" in fname:
                fname = fname.split("func:")[-1].split("@")[0]
            rows  = self.query("""
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

            repo_path = self._get_repo_path()
            results   = []
            for row in rows:
                file_path   = row.get("file", "")
                line_start  = row.get("line") or 1
                total_lines = row.get("total_lines") or 30
                source      = self._read_function_source(
                    repo_path, file_path, fname, line_start, total_lines
                )
                results.append({
                    "function":   row["name"],
                    "file":       file_path,
                    "line_start": line_start,
                    "source":     source,
                })
                print(f"[get_source_code] func={row['name']} file={file_path} source_len={len(source)}")

            return {"functions": results, "count": len(results)}

        # ── get_callers — FIXED: node_id exact match, NO *1..2 ─────────────────
        elif tool_name == "get_callers":
            fname = args.get("function_name", "")
            print(f"[DEBUG] get_callers - RAW args dict: {args}")
            print(f"[DEBUG] get_callers - fname before any cleaning: '{fname}'")
            print(f"[DEBUG] get_callers - fname length: {len(fname)}")
            print(f"[DEBUG] get_callers - fname contains '@': {'@' in fname}")
            print(f"[DEBUG] get_callers - fname contains '\\\\': {'\\\\' in fname}")
            
            # Ye cleaning already hai? Check karo:
            if "func:" in fname:
                fname = fname.split("func:")[-1]
                print(f"[DEBUG] get_callers - after func: removal: '{fname}'")
            if "@" in fname:
                fname = fname.split("@")[0]
                print(f"[DEBUG] get_callers - after @ removal: '{fname}'")
            if "\\" in fname or "/" in fname:
                fname = fname.split("\\")[-1].split("/")[-1]
                print(f"[DEBUG] get_callers - after path removal: '{fname}'")
            print(f"[get_callers] searching for: '{fname}' in repo: {self.repo_id}")

            # Step 1 — Exact node_id dhundo (exact match pehle, phir partial)
            id_rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE n.name = $fn
                   OR n.name ENDS WITH ('.' + $fn)
                RETURN n.node_id AS node_id, n.name AS name,
                       n.file_path AS file
                LIMIT 5
            """, fn=fname)

            if not id_rows:
                id_rows = self.query("""
                    MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                    WHERE toLower(n.name) CONTAINS toLower($fn)
                    RETURN n.node_id AS node_id, n.name AS name,
                           n.file_path AS file
                    LIMIT 5
                """, fn=fname)

            if not id_rows:
                return {
                    "callers": [],
                    "count":   0,
                    "note":    f"Function '{fname}' not found in graph",
                }

            # Step 2 — Direct DEPENDS_ON edges traverse (NO *1..2)
            all_callers = []
            seen_caller = set()

            for id_row in id_rows:
                node_id   = id_row["node_id"]
                node_name = id_row["name"]
                node_file = id_row["file"]
                print(f"[get_callers] node_id={node_id} name={node_name}")

                rows = self.query("""
                    MATCH (target:CodeNode {node_id:$nid, repo_id:$r})
                    MATCH (caller:CodeNode {repo_id:$r})-[:DEPENDS_ON]->(target)
                    WHERE caller.node_id <> target.node_id
                    AND   caller.node_type IN ['function','file','class']
                    RETURN DISTINCT
                        caller.node_id   AS node_id,
                        caller.name      AS name,
                        caller.file_path AS file,
                        caller.line_no   AS line,
                        caller.node_type AS type
                    ORDER BY caller.file_path, caller.line_no
                    LIMIT 20
                """, nid=node_id)

                for r in rows:
                    key = r["node_id"]
                    if key not in seen_caller:
                        all_callers.append({
                            "name":            r["name"],
                            "file":            r["file"],
                            "line":            r["line"],
                            "type":            r["type"],
                            "calls_into":      node_name,
                            "calls_into_file": node_file,
                        })
                        seen_caller.add(key)

            print(f"[get_callers] found {len(all_callers)} callers for '{fname}'")

            # Fallback — direct callers nahi mile → class/file ownership dikhao
            if not all_callers:
                ownership = []
                for id_row in id_rows:
                    node_id = id_row["node_id"]

                    class_rows = self.query("""
                        MATCH (cls:CodeNode {repo_id:$r, node_type:'class'})
                              -[:DEPENDS_ON]->(fn:CodeNode {node_id:$nid})
                        RETURN cls.name      AS name,
                               cls.file_path AS file,
                               cls.line_no   AS line,
                               'class'       AS type,
                               'owns'        AS relationship
                        LIMIT 5
                    """, nid=node_id)
                    ownership.extend(class_rows)

                    file_rows = self.query("""
                        MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
                              -[:DEPENDS_ON]->(fn:CodeNode {node_id:$nid})
                        RETURN f.name      AS name,
                               f.file_path AS file,
                               f.line_no   AS line,
                               'file'      AS type,
                               'contains'  AS relationship
                        LIMIT 3
                    """, nid=node_id)
                    ownership.extend(file_rows)

                if ownership:
                    print(f"[get_callers] no direct callers, returning ownership for '{fname}'")
                    return {
                        "callers": ownership,
                        "count":   len(ownership),
                        "note":    (
                            f"'{fname}' has no direct callers — it is likely an entry-point "
                            f"(HTTP/CLI/scheduler). Showing class/file ownership instead."
                        ),
                    }

                return {
                    "callers": [],
                    "count":   0,
                    "note":    (
                        f"'{fname}' is an entry-point function called externally "
                        f"(HTTP handler / scheduler / CLI). No internal callers in codebase."
                    ),
                }

            return {"callers": all_callers, "count": len(all_callers)}

        # ── get_callees — FIXED: node_id exact match, NO *1..2 ─────────────────
        elif tool_name == "get_callees":
            fname = args.get("function_name", "")
            print(f"[DEBUG] get_callees - RAW args dict: {args}")
            print(f"[DEBUG] get_callees - fname before cleaning: '{fname}'")
            
            # Same cleaning logic add karo agar already nahi hai
            if "func:" in fname:
                fname = fname.split("func:")[-1]
                print(f"[DEBUG] get_callees - after func: removal: '{fname}'")
            if "@" in fname:
                fname = fname.split("@")[0]
                print(f"[DEBUG] get_callees - after @ removal: '{fname}'")
            if "\\" in fname or "/" in fname:
                fname = fname.split("\\")[-1].split("/")[-1]
                print(f"[DEBUG] get_callees - after path removal: '{fname}'")
            print(f"[get_callees] searching for: '{fname}' in repo: {self.repo_id}")
            

            # Step 1 — Exact node_id dhundo
            id_rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE n.name = $fn
                   OR n.name ENDS WITH ('.' + $fn)
                RETURN n.node_id AS node_id, n.name AS name,
                       n.file_path AS file
                LIMIT 5
            """, fn=fname)

            if not id_rows:
                id_rows = self.query("""
                    MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                    WHERE toLower(n.name) CONTAINS toLower($fn)
                    RETURN n.node_id AS node_id, n.name AS name,
                           n.file_path AS file
                    LIMIT 5
                """, fn=fname)

            if not id_rows:
                return {
                    "callees": [],
                    "count":   0,
                    "note":    f"Function '{fname}' not found in graph",
                }

            # Step 2 — Outgoing DEPENDS_ON edges traverse (NO *1..2)
            all_callees = []
            seen_callee = set()

            for id_row in id_rows:
                node_id   = id_row["node_id"]
                node_name = id_row["name"]
                print(f"[get_callees] node_id={node_id} name={node_name}")

                rows = self.query("""
                    MATCH (source:CodeNode {node_id:$nid, repo_id:$r})
                    MATCH (source)-[:DEPENDS_ON]->(callee:CodeNode {repo_id:$r})
                    WHERE callee.node_id <> source.node_id
                    AND   callee.node_type IN ['function','file','class']
                    RETURN DISTINCT
                        callee.node_id   AS node_id,
                        callee.name      AS name,
                        callee.file_path AS file,
                        callee.line_no   AS line,
                        callee.node_type AS type
                    ORDER BY callee.file_path, callee.line_no
                    LIMIT 20
                """, nid=node_id)

                for r in rows:
                    key = r["node_id"]
                    if key not in seen_callee:
                        all_callees.append({
                            "name":      r["name"],
                            "file":      r["file"],
                            "line":      r["line"],
                            "type":      r["type"],
                            "called_by": node_name,
                        })
                        seen_callee.add(key)

            print(f"[get_callees] found {len(all_callees)} callees for '{fname}'")
            return {"callees": all_callees, "count": len(all_callees)}

        # ── get_file_functions ──────────────────────────────────────────────────
        elif tool_name == "get_file_functions":
            fpath = args.get("file_path", "")
            rows  = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE toLower(n.file_path) CONTAINS toLower($fp)
                RETURN n.name AS name, n.line_no AS line,
                       n.deep_risk_level AS risk,
                       n.deep_complexity  AS complexity,
                       n.deep_raises      AS raises
                ORDER BY n.line_no
                LIMIT 30
            """, fp=fpath)

            repo_path   = self._get_repo_path()
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

    # ═══════════════════════════════════════════════════════════════════════════
    # HELPER METHODS  (unchanged from v2)
    # ═══════════════════════════════════════════════════════════════════════════

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

    def _read_function_source(
        self, repo_path: str, file_path: str,
        func_name: str, line_start: int, total_lines: int,
    ) -> str:
        import os, ast
        if not repo_path or not file_path:
            return "source not available"

        clean    = file_path.replace("\\", os.sep).replace("/", os.sep)
        abs_path = os.path.join(repo_path, clean)
        if not os.path.exists(abs_path):
            abs_path = file_path
        if not os.path.exists(abs_path):
            return f"file not found: {file_path}"

        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()

            try:
                tree  = ast.parse(source)
                lines = source.splitlines()
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        clean_name = func_name.split(".")[-1]
                        if node.name == clean_name or clean_name.lower() in node.name.lower():
                            s        = node.lineno - 1
                            e        = getattr(node, "end_lineno", s + total_lines)
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
        import os
        if not repo_path or not file_path:
            return ""
        clean    = file_path.replace("\\", os.sep).replace("/", os.sep)
        abs_path = os.path.join(repo_path, clean)
        if not os.path.exists(abs_path):
            abs_path = file_path
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return ""

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
        """
        Graph search — sirf node/file dhundne ke liye.
        NOTE: connections query HATAI — woh caller data inject karti thi.
        """
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

        # ── REMOVED: connections query — caller data inject karta tha ───────────
        # Pehle yahan tha:
        #   connections = self.query("""
        #       MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
        #       OPTIONAL MATCH (caller)-[:DEPENDS_ON]->(n)
        #       OPTIONAL MATCH (n)-[:DEPENDS_ON]->(callee)
        #       RETURN collect(DISTINCT caller.name)[..5] AS callers, ...
        #   """, nid=first_id)
        # Yeh data prefetch context mein inject hota tha aur LLM isko
        # get_callers call kiye bina use kar leta tha — GALAT THA.
        # Ab yeh query completely removed hai.

        risk_keywords = {"critical","high","risk","risky","important","danger"}
        risk_data     = []
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

        return {
            "keywords":   keywords,
            "nodes":      all_funcs + all_files,
            "files":      [f["file"] for f in all_files],
            "functions":  [f["name"] for f in all_funcs],
            # connections HATAYA — caller data inject hona band
            "risk_files": risk_data,
        }