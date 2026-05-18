"""
Agent Registry — Upgraded with LLM-first routing.
AutoRouter ke saath integrate — keyword scoring sirf fallback hai.
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class AgentDefinition:
    name:            str
    description:     str
    capabilities:    List[str]
    triggers:        List[str]
    requires_target: bool = False
    clarify_if_missing: List[str] = field(default_factory=list)


class AgentRegistry:
    """
    Agent definitions register karo.
    Routing AutoRouter (LLM-first) ke through hoti hai —
    registry ab sirf metadata store hai.
    """

    def __init__(self):
        self._agents: Dict[str, AgentDefinition] = {}

    def register(self, agent: AgentDefinition):
        self._agents[agent.name] = agent

    def get(self, name: str) -> Optional[AgentDefinition]:
        return self._agents.get(name)

    def list_all(self) -> List[Dict]:
        return [
            {
                "name":         a.name,
                "description":  a.description,
                "capabilities": a.capabilities,
            }
            for a in self._agents.values()
        ]

    def needs_clarification(
        self, agent_name: str, message: str, target: Optional[str]
    ) -> Optional[str]:
        agent = self._agents.get(agent_name)
        if not agent:
            return None
        if agent.requires_target and not target:
            missing = agent.clarify_if_missing
            if missing:
                return f"Kaunsi {missing[0]} analyze karni hai? File path ya function naam batao."
        return None


# ── Global instance ────────────────────────────────────────────────────────────

_agent_registry = AgentRegistry()


def get_agent_registry() -> AgentRegistry:
    return _agent_registry


def setup_default_agents():
    """Default agents register karo."""
    agents = [
        AgentDefinition(
            name="ask",
            description="Codebase ke baare mein sawaal jawab karta hai — functions, files, architecture",
            capabilities=["search", "explain", "list", "find", "architecture"],
            triggers=["kahan", "kya", "batao", "find", "show", "where",
                      "what", "explain", "how", "list", "dikhao", "samjhao"],
            requires_target=False,
        ),
        AgentDefinition(
            name="debug",
            description="Errors, bugs aur root cause analyze karta hai",
            capabilities=["root_cause", "trace", "blast_radius", "fix"],
            triggers=["error", "bug", "fail", "crash", "kyun nahi", "issue",
                      "debug", "problem", "broken", "exception", "fix", "wrong",
                      "nahi chal", "traceback", "stack trace"],
            requires_target=True,
            clarify_if_missing=["file ya function"],
        ),
        AgentDefinition(
            name="build",
            description="Features implement karta hai — plan se code tak",
            capabilities=["plan", "code_gen", "review", "pr"],
            triggers=["build", "implement", "add", "create", "feature", "banao",
                      "generate", "develop", "make", "write code", "new", "naya"],
            requires_target=False,
        ),
        AgentDefinition(
            name="qa",
            description="Tests generate karta hai knowledge graph se",
            capabilities=["unit_test", "integration_test", "coverage", "pytest"],
            triggers=["test", "qa", "coverage", "spec", "pytest",
                      "unit", "integration", "testing", "test cases"],
            requires_target=False,
        ),
        AgentDefinition(
            name="impact",
            description="Change ka blast radius calculate karta hai",
            capabilities=["blast_radius", "dependency", "risk", "migration"],
            triggers=["impact", "blast radius", "affect", "agar badloon",
                      "dependency", "migrate", "refactor", "effect",
                      "change karne se", "tod dega", "kya tootega"],
            requires_target=True,
            clarify_if_missing=["file ya function"],
        ),
    ]
    for agent in agents:
        _agent_registry.register(agent)
