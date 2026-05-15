"""
QA Agent — test cases generate karo knowledge graph se.
Graph mein existing patterns dekho, usse match karo.
"""
from typing import Dict
from .base_agent import BaseAgent


class QAAgent(BaseAgent):

    SYSTEM_PROMPT = """
Tu ek expert QA engineer hai. Codebase ka knowledge graph 
dekh ke test cases suggest karta hai.

Response mein yeh do:
1. Unit tests — har function ke liye
2. Integration tests — dependencies ke saath
3. Edge cases — graph mein risky paths
4. Test file kahan banao — file path batao

Pytest format mein suggest karo.
"""

    def run(self, user_message: str, target: str = None,
            model: str = None) -> Dict:

        if not target:
            target = self._find_target(user_message)

        graph_data = self._collect_qa_data(target) if target else {}

        answer = self.ask_llm(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_message,
            graph_context=graph_data,
            model=model,
        )

        return {
            "answer":    answer,
            "target":    target,
            "agent":     "qa",
        }

    def _find_target(self, message: str) -> str:
        import re
        m = re.search(r'[\w/]+\.(py|js|ts)', message)
        if m:
            return m.group(0)
        m = re.search(r'\b([a-z_][a-z0-9_]{2,})\b', message)
        return m.group(1) if m else ""

    def _collect_qa_data(self, target: str) -> Dict:

        # Target ke saare functions
        functions = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
            WHERE f.file_path CONTAINS $t OR f.name CONTAINS $t
            RETURN f.name AS name, f.file_path AS file,
                   f.line_no AS line
            LIMIT 20
        """, t=target)

        # Existing test files — pattern samjho
        existing_tests = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
            WHERE f.file_path CONTAINS 'test'
               OR f.file_path CONTAINS 'spec'
            RETURN f.file_path AS file
            LIMIT 10
        """)

        # Dependencies — integration test ke liye
        deps = self.query("""
            MATCH (n:CodeNode {repo_id:$r})
                  -[:DEPENDS_ON]->(dep:CodeNode {repo_id:$r})
            WHERE n.file_path CONTAINS $t OR n.name CONTAINS $t
            RETURN DISTINCT dep.name AS name,
                   dep.node_type AS type, dep.file_path AS file
            LIMIT 15
        """, t=target)

        return {
            "target":         target,
            "functions":      functions,
            "dependencies":   deps,
            "existing_tests": [e["file"] for e in existing_tests],
            "test_pattern":   "pytest" if any(
                "pytest" in e["file"] or "test_" in e["file"]
                for e in existing_tests
            ) else "unittest",
        }