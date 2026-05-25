"""
DeepContextMixin — Existing agents mein deep AST context inject karna
=====================================================================
Kisi bhi agent mein yeh mixin add karo:

    class DebugAgent(DeepContextMixin, BaseAgent):
        ...

Phir yeh methods available ho jaate hain:
    self.enrich_with_deep_context(graph_data, target)
    self.get_deep_impact_context(target, file_path)
    self.get_repo_hotspots()
    self.get_complexity_report()
    self.get_function_branches(func_name, file_path)
    self.get_exception_chain(func_name)
    self.get_language_breakdown()
"""

from app.code_intelligence.graph.deep_neo4j_queries import DeepGraphQueries


class DeepContextMixin:
    """
    Mixin class — BaseAgent ke saath milao.
    store aur repo_id BaseAgent se milte hain automatically.
    Koi __init__ change nahi karna.
    """

    @property
    def _dq(self) -> DeepGraphQueries:
        """Lazy init — baar baar object mat banao."""
        if not hasattr(self, "_dq_instance"):
            self._dq_instance = DeepGraphQueries(self.store, self.repo_id)
        return self._dq_instance

    def enrich_with_deep_context(self, graph_data: dict, target: str) -> dict:
        """
        Existing graph_data dict mein deep AST data inject karo.
        target: function naam ya file path — auto detect hoga.
        
        Usage:
            graph_data = self._collect_graph_data(...)
            graph_data = self.enrich_with_deep_context(graph_data, target)
            answer     = self.ask_llm(SYSTEM_PROMPT, user_msg, graph_data)
        """
        try:
            is_file = (
                any(target.endswith(ext) for ext in
                    (".py",".js",".ts",".go",".java",".rs",".jsx",".tsx"))
                or ("/" in target and "." in target.split("/")[-1])
            )

            if is_file:
                graph_data["deep_file_analysis"] = self._dq.file_deep_summary(target)
            else:
                clean = target.replace("func:","").split("@")[0]
                graph_data["deep_function_analysis"] = self._dq.function_deep_context(clean)
                graph_data["deep_branches"]          = self._dq.function_branches(clean)
                graph_data["deep_exception_chain"]   = self._dq.exception_chain(clean)

        except Exception as e:
            graph_data["deep_context_error"] = str(e)

        return graph_data

    def get_deep_impact_context(self, target: str, file_path: str = None) -> str:
        """Impact Agent ke liye — blast radius + deep context + exception chain."""
        try:
            clean = target.replace("func:","").split("@")[0]
            return self._dq.impact_with_deep_context(clean, file_path)
        except Exception as e:
            return f"Deep impact unavailable: {e}"

    def get_repo_hotspots(self, top: int = 10) -> str:
        """Ask Agent + Dashboard — HIGH/CRITICAL risk functions."""
        try:    return self._dq.repo_hotspots(top)
        except Exception as e: return f"Hotspots unavailable: {e}"

    def get_complexity_report(self) -> str:
        """Build + QA Agent — complexity distribution."""
        try:    return self._dq.complexity_report()
        except Exception as e: return f"Complexity report unavailable: {e}"

    def get_function_branches(self, func_name: str, file_path: str = None) -> str:
        """Debug Agent — exact branch paths with line numbers."""
        try:    return self._dq.function_branches(func_name, file_path)
        except Exception as e: return f"Branch data unavailable: {e}"

    def get_exception_chain(self, func_name: str) -> str:
        """Debug Agent — exception/error propagation chain."""
        try:    return self._dq.exception_chain(func_name)
        except Exception as e: return f"Exception chain unavailable: {e}"

    def get_function_deep_context(self, func_name: str, file_path: str = None) -> str:
        """Direct deep context — any agent use kar sakta hai."""
        try:    return self._dq.function_deep_context(func_name, file_path)
        except Exception as e: return f"Deep context unavailable: {e}"

    def get_language_breakdown(self) -> str:
        """Dashboard — language-wise risk breakdown."""
        try:    return self._dq.language_risk_breakdown()
        except Exception as e: return f"Language breakdown unavailable: {e}"
