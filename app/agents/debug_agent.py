"""
Debug Agent — "error kyun aa raha", "yeh kyun fail ho raha"
Root cause trace karo Neo4j se.
"""

from typing import Dict
from .base_agent import BaseAgent

class DebugAgent(BaseAgent):

    SYSTEM_PROMPT = """
Tu ek expert debugger hai jo codebase ka knowledge graph 
dekh ke root cause dhundta hai.

Response format:
1. Problem kahan hai — file + line
2. Root cause kya hai — dependency chain
3. Kya fix karo — specific steps
4. Kaun aur affected hai — blast radius

Sirf graph data se answer do. Code mat likho.
"""


    def run(self, user_message: str, target: str = None,
            model: str = None) -> Dict:
        """
        Debug query run karo.
        target: file path ya function name (optional)
        """

        # Step 1 — Target dhundho
        if not target:
            target = self._find_target(user_message)

        if not target:
            return {
                "answer": "Kaunsi file ya function debug karni hai? "
                          "Naam mention karo.",
                "agent": "debug",
            }
        # Step 2 — Root cause data Neo4j se
        graph_data = self._collect_debug_data(target)

        # Step 3 — LLM se explain karwao
        answer = self.ask_llm(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_message,
            graph_context=graph_data,
            model=model,
        )


        return {
            "answer":       answer,
            "target":       target,
            "graph_data":   graph_data,
            "agent":        "debug",
        }
    

    def _find_target(self, message: str) -> str:
        """Message se function ya file name nikalo."""
        # py/js/ts file mention
        import re
        file_match = re.search(r'[\w/]+\.(py|js|ts|java|go)', message)
        if file_match:
            return file_match.group(0)

        # function name — camelCase ya snake_case
        func_match = re.search(r'\b([a-z_][a-z0-9_]{2,}|[a-zA-Z][a-zA-Z0-9]{2,})\b', message)
        if func_match:
            return func_match.group(1)
        return ""
    def _collect_debug_data(self, target: str) -> Dict:
        """Neo4j se debug ke liye zaroori data nikalo."""

        # Node dhundho
        node = self.query_one("""
            MATCH (n:CodeNode {repo_id:$r})
            WHERE n.name CONTAINS $t OR n.file_path CONTAINS $t
            RETURN n.node_id AS id, n.name AS name,
                   n.node_type AS type, n.file_path AS file,
                   n.line_no AS line
            LIMIT 1
        """, t=target)

        if not node:
            return {"error": f"'{target}' graph mein nahi mila"}
        
        node_id = node["id"]

        # Direct callers — kaun is function ko call karta hai
        callers = self.query("""
            MATCH (caller:CodeNode {repo_id:$r})
                  -[:DEPENDS_ON]->(n:CodeNode {node_id:$nid})
            RETURN caller.name AS name, caller.file_path AS file,
                   caller.line_no AS line, caller.node_type AS type
            LIMIT 10
        """, nid=node_id)


        # Direct callees — yeh function kise call karta hai
        callees = self.query("""
            MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
                  -[:DEPENDS_ON]->(dep:CodeNode {repo_id:$r})
            RETURN dep.name AS name, dep.file_path AS file,
                   dep.node_type AS type
            LIMIT 10
        """, nid=node_id)


        # Circular dependency check
        circular = self.query("""
            MATCH path = (n:CodeNode {node_id:$nid, repo_id:$r})
                         -[:DEPENDS_ON*2..5]->(n)
            RETURN [nd IN nodes(path) | nd.name] AS cycle
            LIMIT 3
        """, nid=node_id)


        # Blast radius — kitne nodes affected
        blast = self.query_one("""
            MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
            MATCH (affected)-[:DEPENDS_ON*1..3]->(n)
            RETURN count(DISTINCT affected) AS count
        """, nid=node_id)

        return {
            "target_node":    node,
            "called_by":      callers,
            "calls":          callees,
            "circular_deps":  [c["cycle"] for c in circular],
            "blast_radius":   blast["count"] if blast else 0,
        }


