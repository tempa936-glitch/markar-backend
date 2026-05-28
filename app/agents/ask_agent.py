"""
Ask Agent — "X feature kahan hai", "Y function kya karta hai"
Neo4j se dhundho, actual file content padho, LLM se explain karo.
"""
from typing import Dict
from .base_agent import BaseAgent
from app.agents.deep_context_mixin import DeepContextMixin


class AskAgent(DeepContextMixin, BaseAgent):

    SYSTEM_PROMPT = """
You are Markar AI — an expert code intelligence assistant with deep knowledge of the entire codebase.
You have access to the actual file contents, function-level analysis, dependency graph, complexity scores, and exception paths.
 
YOUR JOB:
Answer the user's question with maximum technical depth and precision.
You are like a senior architect who has read every line of this codebase.
 
ANSWER STRUCTURE — always follow this:
 
**Overview**
- What this file/function/feature does in 2-3 sentences
 
**Functions & Routes Found**
- List every relevant function/route/class with:
  - Exact file path and line number
  - What it does specifically
  - What it calls internally (with line numbers if available)
  - What calls it (callers)
  - Parameters it accepts
  - What it returns
 
**Code Flow**
- Step by step how the code executes
- Example: Line 45 → calls `_exchange_code()` → which calls GitHub API → returns user token
- Trace the full execution path
 
**Dependencies & Connections**
- What other files/functions this depends on
- What would break if this changes
- Blast radius if relevant
 
**Risk & Quality**
- Complexity score if available
- Any uncaught exceptions
- Git churn — how often this changes
- Any issues or concerns
 
**Summary**
- Is it working correctly based on code analysis?
- Any missing pieces or potential bugs visible in the code?
 
LANGUAGE RULES:
- Always answer in English
- Use technical terminology — this is for engineers
- Be specific — line numbers, function names, exact variable names
- Never say "further investigation needed" — you have the code, analyze it directly
- Never give generic answers — every answer must reference actual code from the codebase
- If file content is provided, use it fully — read every function and explain it
 
FORMATTING RULES:
- Use **Bold** for all headings, file paths, function names
- Use bullet points for lists
- For code references write: functionName (line X) — not backticks
- Keep paragraphs short but content dense
- Do NOT truncate — give complete information
"""

    def run(self, user_message: str, model: str = None) -> Dict:
        """User ka question answer karo."""

        # Step 1 — Keywords nikalo
        keywords = self._extract_keywords(user_message)

        # Step 2 — Graph se search karo
        graph_data = self._search_graph(keywords)

        # Step 3 — Matched files ka actual content padho
        try:
            file_contents = self._read_matched_files(graph_data, user_message)
            if file_contents:
                graph_data["file_contents"] = file_contents
        except Exception as e:
            print(f"[AskAgent] File read failed (non-critical): {e}")

        # Step 4 — Deep AST context inject karo
        try:
            if graph_data.get("nodes"):
                # File match hua toh file summary, function match hua toh function context
                top_file = graph_data.get("files", [None])[0]
                top_func = graph_data.get("functions", [None])[0]

                if top_file:
                    graph_data["deep_file_analysis"] = self._dq.file_deep_summary(top_file)
                if top_func:
                    graph_data["deep_function_analysis"] = self._dq.function_deep_context(top_func)
        except Exception as e:
            print(f"[AskAgent] Deep context failed (non-critical): {e}")

        # Step 5 — Agar kuch nahi mila
        if not graph_data["nodes"] and not graph_data.get("file_contents"):
            return {
                "answer": f"'{' '.join(keywords)}' se koi file ya function nahi mila. "
                          f"Doosre keywords try karo.",
                "files":     [],
                "functions": [],
            }

        # Step 6 — LLM ko graph + file content bhejo
        answer = self.ask_llm(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_message,
            graph_context=graph_data,
            model=model,
        )

        return {
            "answer":    answer,
            "files":     graph_data.get("files", []),
            "functions": graph_data.get("functions", []),
            "agent":     "ask",
        }

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

        files_to_read = graph_data.get("files", [])[:3]  # max 3 files

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