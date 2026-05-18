"""
Tool Registry — Microsoft pattern.
Har tool register hota hai — naam, description, capabilities.
Agents registry se tools discover karte hain.
Tool calling with error recovery built-in.
"""
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field
import traceback


@dataclass
class ToolDefinition:
    name:        str
    description: str
    category:    str          # "graph", "code", "git", "test"
    fn:          Callable
    required_params: List[str] = field(default_factory=list)
    optional_params: List[str] = field(default_factory=list)


class ToolRegistry:
    """
    Single source of truth for all agent tools.
    Microsoft standard: agents tools ko directly call nahi karte —
    registry ke through call karte hain taaki error recovery ho sake.
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._call_log: List[Dict] = []   # Phase 3: audit log

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool
        print(f"[ToolRegistry] Registered: {tool.name} ({tool.category})")

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_by_category(self, category: str) -> List[ToolDefinition]:
        return [t for t in self._tools.values() if t.category == category]

    def list_all(self) -> List[Dict]:
        return [
            {"name": t.name, "description": t.description,
             "category": t.category, "params": t.required_params}
            for t in self._tools.values()
        ]

    def call(self, tool_name: str, **kwargs) -> Dict:
        """
        Tool call with error recovery.
        Fail hone pe structured error return karo — exception nahi uthao.
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return {
                "success": False,
                "error":   f"Tool '{tool_name}' registry mein nahi hai",
                "data":    None,
            }

        # Required params check
        missing = [p for p in tool.required_params if p not in kwargs]
        if missing:
            return {
                "success": False,
                "error":   f"Missing params: {missing}",
                "data":    None,
                "clarify": f"Yeh information chahiye: {', '.join(missing)}",
            }

        try:
            result = tool.fn(**kwargs)
            log_entry = {"tool": tool_name, "success": True, "params": list(kwargs.keys())}
            self._call_log.append(log_entry)
            return {"success": True, "data": result, "error": None}
        except Exception as e:
            print(f"[ToolRegistry] {tool_name} failed: {e}")
            log_entry = {"tool": tool_name, "success": False, "error": str(e)}
            self._call_log.append(log_entry)
            return {
                "success":    False,
                "error":      str(e),
                "traceback":  traceback.format_exc()[-500:],
                "data":       None,
                "retry_hint": "Retry karo ya target change karo",
            }

    def get_call_log(self, last_n: int = 20) -> List[Dict]:
        """Phase 3: Audit log — last N tool calls."""
        return self._call_log[-last_n:]


# ── Global registry instance ──────────────────────────────────────────────
_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _registry


def register_tool(tool: ToolDefinition):
    _registry.register(tool)
