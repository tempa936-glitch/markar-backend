"""
Ask Agent — "X feature kahan hai", "Y function kya karta hai"
Neo4j se dhundho, LLM se explain karo.
"""

from .base_agent import BaseAgent

class AskAgent(BaseAgent):

    SYSTEM_PROMPT = """
Tu ek expert code analyst hai. Tumhare paas ek codebase ka 
knowledge graph hai — files, functions, classes aur unke
connections. User ke sawaal ka jawab graph data se do.

Rules:
- File path aur line number zaroor batao
- Connections explain karo (kaun kise call karta hai)
- Simple aur clear jawab do
- Code mat likho — sirf explain karo
- Risk levels: CRITICAL > HIGH > MEDIUM > LOW — inhe exactly as-is use karo, rename mat karo
- Test files (test_*.py, *_test.py, conftest.py) ko CRITICAL mat bolna — yeh normal test code hai
- CRITICAL sirf tab hota hai jab production code file pe 30+ nodes depend karti hon
- Test files mein zyada functions hona GOOD sign hai — extensive test coverage
"""

    def run(self, user_message: str, model: str = None) -> Dict:
        """User ka question answer karo."""

        # Step 1 — Keywords nikalo message se
        keywords = self._extract_keywords(user_message)

        # Step 2 — Neo4j mein search karo
        graph_data = self._search_graph(keywords)

        if not graph_data["nodes"]:
            return {
                "answer": f"'{' '.join(keywords)}' se koi file ya function nahi mila. "
                          f"Doosre keywords try karo.",
                "files":     [],
                "functions": [],
            }
        
        # Step 3 — LLM ko graph data bhejo
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
    
    def _extract_keywords(self, message: str) -> list:
        """Multiple keywords nikalo — har word alag search hoga."""
        stop = {"kahan","hai","kya","kar","raha","mein","se","ka",
                "ki","ko","karo","where","is","the","a","an","in",
                "what","how","does","do","find","show","tell","me"
                "batao","dikhao","show","give","list","all","get","find","search","kaunsa","konsa","kon","kis","kisiko",
                }
        words = [w.lower() for w in message.split() if w.lower() not in stop]
        return words[:6]  # top 6 meaningful words


    def _search_graph(self, keywords: list) -> Dict:
        """Har keyword se alag search karo — sab results merge karo."""
        all_funcs = []
        all_files = []
        seen_ids  = set()

        for kw in keywords:
            if len(kw) < 2:
                continue

        # Functions search
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

        # Files search
        files = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
            WHERE toLower(f.file_path) CONTAINS toLower($kw)
               OR toLower(f.name)      CONTAINS toLower($kw)
            RETURN f.node_id AS id, f.name AS name,
                   f.file_path AS file
            LIMIT 10
        """, kw=kw)

        for fl in files:
            if fl["id"] not in seen_ids:
                all_files.append(fl)
                seen_ids.add(fl["id"])


        # Pehle function mila to uske connections bhi nikalo
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
            # Risk files ko all_files mein add karo
            for rf in risk_data:
                if rf["file"] not in seen_ids:
                    all_files.append({
                        "id":   rf["file"],
                        "name": rf["file"].split("\\")[-1].split("/")[-1],
                        "file": rf["file"],
                        "risk": rf["risk"],
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