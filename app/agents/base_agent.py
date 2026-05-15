"""
Base class — sabhi agents yahan se inherit karte hain.
Common kaam: Neo4j query, LLM call, response format.
"""
from typing import Dict, List, Optional
import os

class BaseAgent:

    def __init__(self, store, repo_id: str):
        self.store   = store      # Neo4j store
        self.repo_id = repo_id

    def query(self, cypher: str, **params) -> List[Dict]:
        """Neo4j Cypher query chalao, list of dicts wapis do."""
        try:
            driver = self.store._connect()
            with driver.session() as s:
                result = s.run(cypher, r=self.repo_id, **params)
                return [dict(row) for row in result]
        except Exception as e:
            print(f"[{self.__class__.__name__}] Query failed: {e}")
            return []

    def query_one(self, cypher: str, **params) -> Optional[Dict]:
        """Single row wapas do."""
        rows = self.query(cypher, **params)
        return rows[0] if rows else None


    # ── LLM call — graph data bhejo, code nahi ──────────────────────────
    def ask_llm(self, system_prompt: str, user_message: str,
                graph_context: Dict, model: str = None) -> str:

        """
        LLM ko call karo.
        graph_context mein Neo4j ka structured data hoga — poora code nahi.
        """

        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return self._fallback_response(graph_context)

        client = anthropic.Anthropic(api_key=api_key)

        # Context banao — sirf structured data, code nahi
        context_text = self._format_context(graph_context)

        full_prompt = f"""
{system_prompt}

=== CODEBASE KNOWLEDGE GRAPH DATA ===
{context_text}
=====================================

User ka sawaal: {user_message}
"""
        try:
            response = client.messages.create(
                model=model or os.getenv("MARKAR_LLM_MODEL", "claude-3-5-haiku-20241022"),
                max_tokens=1500,
                messages=[{"role": "user", "content": full_prompt}]
            )
            return response.content[0].text
        except Exception as e:
            print(f"[LLM] Failed: {e}")
            return self._fallback_response(graph_context)

    def _format_context(self, ctx: Dict) -> str:
        """Graph data ko readable text mein convert karo."""
        lines = []
        for key, val in ctx.items():
            if isinstance(val, list):
                lines.append(f"{key}:")
                for item in val[:20]:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {val}")
        return "\n".join(lines)

    def _fallback_response(self, ctx: Dict) -> str:
        """Agar LLM nahi hai to graph data seedha return karo."""
        return f"Graph data: {ctx}"                 