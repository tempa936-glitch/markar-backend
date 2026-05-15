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
"""

    def run(self, user_message: str, model: str = None) -> Dict:
        """User ka question answer karo."""

        # Step 1 — Keywords nikalo message se
        keywords = self._extract_keywords(user_message)

        # Step 2 — Neo4j mein search karo
        graph_data = self._search_graph(keywords)

        if not graph_data["nodes"]:
            return {
                "answer": f"'{keywords}' se koi file ya function nahi mila. "
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
    
    def _extract_keywords(self, message: str) -> str:
        """Simple keyword extraction — common words hata do."""
        stop = {"kahan","hai","kya","kar","raha","mein","se","ka",
                "ki","ko","karo","where","is","the","a","an","in",
                "what","how","does","do","find","show","tell","me"}
        words = [w.lower() for w in message.split() if w.lower() not in stop]
        return " ".join(words[:5])  # top 5 meaningful words
    

    def _search_graph(self, keywords: str) -> Dict:
        """Neo4j mein keyword se nodes dhundho."""

        # Functions search
        funcs = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
            WHERE toLower(f.name) CONTAINS toLower($kw)
            RETURN f.node_id AS id, f.name AS name,
                   f.file_path AS file, f.line_no AS line
            LIMIT 10
        """, kw=keywords)

        # Files search
        files = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
            WHERE toLower(f.name) CONTAINS toLower($kw)
               OR toLower(f.file_path) CONTAINS toLower($kw)
            RETURN f.node_id AS id, f.name AS name,
                   f.file_path AS file
            LIMIT 10
        """, kw=keywords)


        # Pehle function mila to uske connections bhi nikalo
        connections = []
        if funcs:
            first_id = funcs[0]["id"]
            connections = self.query("""
                MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
                OPTIONAL MATCH (caller)-[:DEPENDS_ON]->(n)
                OPTIONAL MATCH (n)-[:DEPENDS_ON]->(callee)
                RETURN 
                    collect(DISTINCT caller.name)[..5] AS callers,
                    collect(DISTINCT callee.name)[..5] AS callees
            """, nid=first_id)


        return {
            "keywords":    keywords,
            "nodes":       funcs + files,
            "files":       [f["file"] for f in files],
            "functions":   [f["name"] for f in funcs],
            "connections": connections[0] if connections else {},
        }        