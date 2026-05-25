"""
orchestrator_patch.py
=====================
Yeh file directly import nahi hoti.
Yeh sirf batati hai ki existing orchestrator.py mein
EXACTLY kahan aur kya add karna hai.

Do jagah change karni hain orchestrator.py mein:
    1. Import section
    2. initialize() method ke end mein
"""

# ════════════════════════════════════════════════════════════════════
# CHANGE 1 — orchestrator.py ke top mein yeh import add karo
# ════════════════════════════════════════════════════════════════════
#
# from app.code_intelligence.graph.deep_graph_builder import DeepGraphBuilder
#
# ════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════
# CHANGE 2 — initialize() method mein
# Yeh existing code ke baad add karo:
#
#         self._analyzer = GraphAnalyzer(nodes, repo_path=self.repo_path)
#         self.initialized = True
#
# Uske BAAD yeh block add karo:
# ════════════════════════════════════════════════════════════════════
#
#         # ── Deep AST enrichment (Step 5) ──────────────────────────
#         t5 = time.time()
#         try:
#             deep_builder = DeepGraphBuilder(self.store, self.repo_path)
#             deep_summary = deep_builder.run()
#             print(f"  Deep AST done: {deep_summary} [{time.time()-t5:.1f}s]")
#         except Exception as e:
#             print(f"  [DeepAST] Skipped (non-critical): {e}")
#         # ── End deep AST ───────────────────────────────────────────
#
# ════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════
# CHANGE 3 — Agents mein mixin add karo
# Yeh sirf ek line ka change hai har agent file mein:
# ════════════════════════════════════════════════════════════════════

# debug_agent.py:
#   from app.agents.deep_context_mixin import DeepContextMixin
#   class DebugAgent(DeepContextMixin, BaseAgent):    ← sirf yeh line badlo
#       ...
#       def run(self, user_message, ...):
#           graph_data = self._collect_debug_data(...)      # existing
#           graph_data = self.enrich_with_deep_context(     # ADD
#               graph_data, target or user_message
#           )
#           ...

# impact_agent.py:
#   from app.agents.deep_context_mixin import DeepContextMixin
#   class ImpactAnalysisAgent(DeepContextMixin, BaseAgent):
#       ...
#       def run(self, user_message, target=None, ...):
#           graph_data["deep_impact"] = self.get_deep_impact_context(   # ADD
#               target or user_message
#           )

# ask_agent.py:
#   from app.agents.deep_context_mixin import DeepContextMixin
#   class AskAgent(DeepContextMixin, BaseAgent):
#       ...
#       def run(self, user_message, ...):
#           msg_lower = user_message.lower()
#           if any(w in msg_lower for w in             # ADD this block
#                  ("risky","complex","hotspot","dangerous","high risk")):
#               graph_data["hotspots"]   = self.get_repo_hotspots()
#               graph_data["complexity"] = self.get_complexity_report()
#               graph_data["languages"]  = self.get_language_breakdown()

# build_agent.py:
#   from app.agents.deep_context_mixin import DeepContextMixin
#   class BuildAgent(DeepContextMixin, BaseAgent):
#       ...
#       def run(self, user_message, ...):
#           graph_data["complexity"] = self.get_complexity_report()  # ADD
#           graph_data["hotspots"]   = self.get_repo_hotspots(top=5) # ADD

# qa_agent.py:
#   from app.agents.deep_context_mixin import DeepContextMixin
#   class QAAgent(DeepContextMixin, BaseAgent):
#       ...
#       def run(self, user_message, target=None, ...):
#           if target:                                                  # ADD
#               graph_data["deep_func"] = self.get_function_deep_context(target)
#               graph_data["branches"]  = self.get_function_branches(target)

# ════════════════════════════════════════════════════════════════════
# YAHI HAI — Sirf yeh changes karo. Koi aur file touch nahi karni.
# ════════════════════════════════════════════════════════════════════


def apply_deep_ast(orchestrator_instance) -> bool:
    """
    Agar orchestrator.py modify nahi karna toh yeh function call karo
    repo_service.py ya jahan orchestrator initialize hota hai:

        from app.code_intelligence.orchestrator_patch import apply_deep_ast
        orch = CodeIntelligenceOrchestrator(...)
        orch.initialize()
        apply_deep_ast(orch)    ← yeh ek line add karo
    """
    from app.code_intelligence.graph.deep_graph_builder import DeepGraphBuilder
    try:
        repo_path = getattr(orchestrator_instance, "repo_path", None)
        store     = getattr(orchestrator_instance, "store", None)
        if not repo_path or not store:
            print("[DeepAST] repo_path ya store nahi mila — skip")
            return False
        builder = DeepGraphBuilder(store, repo_path)
        summary = builder.run()
        print(f"[DeepAST] Complete: {summary}")
        return True
    except Exception as e:
        print(f"[DeepAST] Failed (non-critical): {e}")
        return False
