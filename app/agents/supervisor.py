"""
Supervisor Agent — user ka message padhta hai,
sahi agent ko route karta hai, response combine karta hai.
"""
from typing import Dict, Optional
from .ask_agent    import AskAgent
from .debug_agent  import DebugAgent
from .qa_agent     import QAAgent
from .impact_agent import ImpactAnalysisAgent
from .build_agent  import BuildAgent


class SupervisorAgent:

    # Intent → Agent mapping
    DEBUG_KEYWORDS  = {"error","bug","fail","crash","kyun","issue",
                       "broken","exception","traceback","root cause",
                       "debug","problem","wrong","fix"}
    IMPACT_KEYWORDS = {"impact","change","badloon","blast","affect",
                       "radius","agar","dependency","migrate","refactor"}
    QA_KEYWORDS     = {"test","qa","coverage","spec","pytest","unit",
                       "integration","testing","likhoo"}
    BUILD_KEYWORDS = {"build","implement","add","create","feature",
                  "banao","likho","generate","develop","make"}

    def __init__(self, store, repo_id: str):
        self.store   = store
        self.repo_id = repo_id

        # Sub-agents initialize
        self.ask_agent    = AskAgent(store, repo_id)
        self.debug_agent  = DebugAgent(store, repo_id)
        self.qa_agent     = QAAgent(store, repo_id)
        self.impact_agent = ImpactAnalysisAgent(store)
        self.build_agent = BuildAgent(store, repo_id)

    def handle(self, message: str, model: str = None,
               target: str = None) -> Dict:
        """
        Main entry point.
        Message aaya → intent detect karo → agent call karo → response do.
        """
        intent = self._detect_intent(message)
        
        print(f"[Supervisor] Intent: {intent} | Message: {message[:60]}")

        try:
            if intent == "debug":
                result = self.debug_agent.run(message, target, model)

            elif intent == "impact":
                if target:
                    impact = self.impact_agent.analyze_function_change(target)
                    result = {
                        "answer":  self._format_impact(impact),
                        "data":    impact.__dict__,
                        "agent":   "impact",
                    }
                else:
                    result = {
                        "answer": "Kaunsi file ya function ka impact dekhna hai? "
                                  "Naam mention karo.",
                        "agent":  "impact",
                    }

            elif intent == "qa":
                result = self.qa_agent.run(message, target, model)

            elif intent == "build":
                # Build multi-step hai — seedha clarify se shuru karo
                import uuid
                session_id = str(uuid.uuid4())[:12]
                result = self.build_agent.clarify(session_id, message, model)    

            else:
                # Default — Ask agent
                result = self.ask_agent.run(message, model)


        except Exception as e:
            print(f"[Supervisor] Agent failed: {e}")
            result = {
                "answer": f"Agent mein error aaya: {str(e)}. "
                          f"Please retry.",
                "agent":  "error",
            }

        result["intent"] = intent
        return result

    def _detect_intent(self, message: str) -> str:
        """Message se intent detect karo — simple keyword matching."""
        msg_lower = message.lower()
        words     = set(msg_lower.split())

        if words & self.DEBUG_KEYWORDS:
            return "debug"
        if words & self.IMPACT_KEYWORDS:
            return "impact"
        if words & self.QA_KEYWORDS:
            return "qa"
        if words & self.BUILD_KEYWORDS:   # ← yahan add karo
            return "build"
        return "ask"

    def _format_impact(self, impact) -> str:
        """ImpactAnalysisAgent ka result readable string mein."""
        return (
            f"Severity: {impact.severity.value.upper()}\n"
            f"Affected nodes: {len(impact.affected_nodes)}\n"
            f"Affected files: {len(impact.affected_files)}\n"
            f"Risk: {impact.risk_level}\n\n"
            f"Recommendations:\n" +
            "\n".join(impact.recommendations)
        )