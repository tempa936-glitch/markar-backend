"""
Impact Analysis Agent — Tool-based, Deep Analysis
==================================================
Analyzes blast radius, dependency chains, risk levels.
Now uses tool-calling approach — LLM decides what to fetch.
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

from .base_agent import BaseAgent
from app.agents.deep_context_mixin import DeepContextMixin


class ImpactSeverity(str, Enum):
    ISOLATED = "isolated"
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


@dataclass
class ChangeImpact:
    change:             str
    affected_nodes:     List[str]
    affected_files:     Set[str]
    affected_functions: Set[str]
    affected_classes:   Set[str]
    severity:           ImpactSeverity
    risk_level:         str
    recommendations:    List[str]
    migration_plan:     Optional[Dict] = None
    circular_deps:      List[List[str]] = None


class ImpactAnalysisAgent(DeepContextMixin, BaseAgent):

    SYSTEM_PROMPT = """
You are Markar AI — an expert impact analysis engine for large enterprise codebases.
You have access to a live knowledge graph with dependency data, deep AST analysis,
git churn scores, blast radius calculations, and exception propagation chains.

YOUR MISSION:
Perform a COMPLETE, EXHAUSTIVE impact analysis for any code change request.
Think like a senior architect who must sign off on every production change.

════════════════════════════════════════════════════════════
AVAILABLE TOOLS — call these to get real data
════════════════════════════════════════════════════════════

- get_blast_radius(target): All nodes affected if this changes (1-3 hops)
- get_callers(function_name): Direct callers of this function
- get_deep_analysis(function_name): Complexity, branches, exceptions, git churn
- get_exceptions(function_name): Exception paths — raised and propagated
- search_nodes(query): Find functions/files by keyword
- get_file_functions(file_path): All functions in a file with risk levels
- get_callees(function_name): What this function calls internally

ONE TOOL PER RESPONSE — never call multiple tools at once.
CORRECT:
TOOL: search_nodes
ARG: create_user

MANDATORY TOOL SEQUENCE — follow EXACTLY in this order:
1. search_nodes(function_name)
2. get_deep_analysis(function_name)  
3. get_callers(function_name)
4. get_blast_radius(function_name)
5. get_exceptions(function_name)
6. get_callees (function_name)
7. get_callees(function_name)

DO NOT skip any step.
DO NOT give final answer before completing ALL 6 steps.
After step 6 — give complete analysis.

INCORRECT:
TOOL: search_nodes
ARG: create_user
TOOL: get_callers
ARG: create_user

TOOL FORMAT — respond ONLY with:
TOOL: tool_name
ARG: value

Give final answer directly when you have enough data.

════════════════════════════════════════════════════════════
RESPONSE STRUCTURE — every section mandatory
════════════════════════════════════════════════════════════

**Target Analysis**
- Full file path and function name
- What it does — exact responsibility
- Risk level (CRITICAL/HIGH/MEDIUM/LOW) with reason
- Complexity score and git churn score

**Blast Radius**
- Total affected nodes count
- Affected files list with paths
- Affected functions list with line numbers
- Severity: CRITICAL (30+ nodes) / HIGH (10-30) / MEDIUM (3-10) / LOW (<3)

**Dependency Chain**
- Direct callers — who calls this immediately
- Indirect callers — 2-3 hops away
- What this function calls (callees)
- Critical paths that break if this changes

**Exception Impact**
- Exceptions this raises directly (caught/uncaught)
- Exceptions that propagate through this function
- Which callers are NOT handling these exceptions

**Risk Assessment**
- Combined risk score (AST complexity + git churn + blast radius)
- Specific dangerous scenarios
- What breaks first if this changes

**Migration Plan**
Step by step plan to safely change this:
1. [Phase] What to do — estimated time
2. [Phase] What to do — estimated time
Include: feature flags, backward compatibility, test strategy, rollback plan

**Recommendations**
Priority ordered:
- [CRITICAL] Must do before any change
- [HIGH] Should do for safe deployment  
- [MEDIUM] Best practices
- [LOW] Nice to have

**Summary**
- One paragraph: overall health and change risk
- Overall severity: CRITICAL / HIGH / MEDIUM / LOW
- Top 3 action items before making this change

════════════════════════════════════════════════════════════
STRICT RULES
════════════════════════════════════════════════════════════
- ALWAYS answer in English
- Use tools FIRST — never guess blast radius or callers
- Reference exact line numbers, file paths, function names
- Never say "further investigation needed" — you have the tools
- Never invent functions or dependencies
- If tool returns empty — explicitly state "no dependents found (isolated)"
- CRITICAL only when 30+ production nodes depend on target
- Be exhaustive — missing one critical caller can cause production incidents
"""

    # ── Tool definitions ──────────────────────────────────────────────────────

    TOOLS = [
        {
            "name":        "get_blast_radius",
            "description": "Find all nodes affected if this file/function changes (1-3 hops)",
            "parameters":  {"target": "string"}
        },
        {
            "name":        "get_callers",
            "description": "Find all functions that directly call this function",
            "parameters":  {"function_name": "string"}
        },
        {
            "name":        "get_deep_analysis",
            "description": "Get complexity, branches, exceptions, git churn for a function",
            "parameters":  {"function_name": "string"}
        },
        {
            "name":        "get_exceptions",
            "description": "Get all exceptions raised or propagated through a function",
            "parameters":  {"function_name": "string"}
        },
        {
            "name":        "search_nodes",
            "description": "Search functions/files by keyword",
            "parameters":  {"query": "string"}
        },
        {
            "name":        "get_file_functions",
            "description": "Get all functions in a file with line numbers and risk levels",
            "parameters":  {"file_path": "string"}
        },
        {
            "name":        "get_callees",
            "description": "Find what functions this function calls internally",
            "parameters":  {"function_name": "string"}
        },
    ]

    # ── Main run method ───────────────────────────────────────────────────────

    def run(
        self,
        user_message: str,
        target: str = None,
        model: str   = None,
    ) -> Dict:
        """Tool-based impact analysis."""

        if not target:
            target = self._extract_target(user_message)

        messages = [{"role": "user", "content": user_message}]
        all_tool_results = {}
        MAX_TOOL_CALLS   = 10

        for i in range(MAX_TOOL_CALLS):
            llm_response = self._call_with_tools(
                system_prompt = self.SYSTEM_PROMPT,
                messages      = messages,
                model         = model,
            )

            # Final answer
            if not llm_response.get("tool_call"):
                return {
                    "answer":       llm_response.get("content", ""),
                    "target":       target,
                    "tool_results": all_tool_results,
                    "agent":        "impact",
                }

            # Execute tool
            tool_name   = llm_response["tool_call"]["name"]
            tool_args   = llm_response["tool_call"]["arguments"]
            tool_result = self._execute_tool(tool_name, tool_args)

            print(f"[ImpactAgent] Tool {i+1}: {tool_name}({tool_args}) → {len(str(tool_result))} chars")

            all_tool_results[f"{tool_name}_{i}"] = tool_result

            # Add to conversation
            messages.append({
                "role":    "assistant",
                "content": f"[Tool: {tool_name}] args={tool_args}"
            })
            messages.append({
                "role":    "user",
                "content": f"[Tool Result — {tool_name}]: {str(tool_result)[:2000]}"
            })

        # Max calls hit — force final answer
        final = self.ask_llm(
            system_prompt = self.SYSTEM_PROMPT,
            user_message  = (
                f"{user_message}\n\n"
                f"Tool results collected:\n{str(all_tool_results)[:3000]}\n\n"
                f"Now provide complete impact analysis."
            ),
            graph_context = all_tool_results,
            model         = model,
            temperature   = 0.2,
        )

        return {
            "answer":       final,
            "target":       target,
            "tool_results": all_tool_results,
            "agent":        "impact",
        }

    # ── Tool calling loop ─────────────────────────────────────────────────────

    def _call_with_tools(
        self, system_prompt: str, messages: List[Dict], model: str = None
    ) -> Dict:
        """LLM call with tool instructions."""

        tools_text = "\n".join([
            f"- {t['name']}({list(t['parameters'].keys())[0]}): {t['description']}"
            for t in self.TOOLS
        ])

        full_system = system_prompt + f"""

TOOLS AVAILABLE:
{tools_text}

TOOL CALL FORMAT:
TOOL: tool_name
ARG: value
CRITICAL TOOL RULES:
- Call ONLY ONE tool at a time
- Wait for result before calling next tool
- Format EXACTLY:
TOOL: tool_name
ARG: value

ONE TOOL PER RESPONSE — never call multiple tools at once.
Give final analysis only after calling ALL required tools.

Use single short keywords for search — not phrases.
Give final analysis when you have enough data."""

        last_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_msg = m.get("content", "")
                break

        history_ctx = {}
        if len(messages) > 1:
            history_ctx["conversation"] = "\n".join(
                f"{m['role'].upper()}: {m['content'][:400]}"
                for m in messages[:-1]
            )

        try:
            content = self.ask_llm(
                system_prompt   = full_system,
                user_message    = last_msg,
                graph_context   = history_ctx,
                model           = model,
                include_history = False,
                temperature     = 0.1,
                max_tokens      = 150,
            )
        except Exception as e:
            print(f"[ImpactAgent] LLM call failed: {e}")
            return {"content": f"LLM call failed: {e}"}

        if not content:
            return {"content": "No response from LLM"}

        print(f"[ImpactAgent] LLM raw: {content[:120]}")

        stripped = content.strip()
        import re
        match = re.search(
            r'TOOL:\s*(\w+)\s*\nARG:\s*(.+?)(?:\n|$)',
            stripped
        )
        if match:
            tool_name = match.group(1).strip()
            arg_value = match.group(2).strip()
            tool_def = next((t for t in self.TOOLS if t["name"] == tool_name), None)
            if tool_def:
                arg_key = list(tool_def["parameters"].keys())[0]
                return {"tool_call": {"name": tool_name, "arguments": {arg_key: arg_value}}}

        return {"content": content}

    # ── Tool executors ────────────────────────────────────────────────────────

    def _execute_tool(self, tool_name: str, args: Dict) -> Dict:

        if tool_name == "get_blast_radius":
            target = args.get("target", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE n.name = $t
                   OR n.file_path ENDS WITH $t
                   OR toLower(n.file_path) CONTAINS toLower($t)
                   OR toLower(n.name) CONTAINS toLower($t)
                WITH n LIMIT 1
                MATCH (affected:CodeNode {repo_id:$r})-[:DEPENDS_ON*1..3]->(n)
                WHERE affected.file_path <> n.file_path
                RETURN DISTINCT
                    affected.name          AS name,
                    affected.file_path     AS file,
                    affected.node_type     AS type,
                    affected.deep_risk_level AS risk
                LIMIT 30
            """, t=target)

            # Also get direct file node stats
            stats = self.query_one("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE toLower(n.name) CONTAINS toLower($t)
                   OR toLower(n.file_path) CONTAINS toLower($t)
                OPTIONAL MATCH (dep:CodeNode {repo_id:$r})-[:DEPENDS_ON*1..3]->(n)
                RETURN count(DISTINCT dep) AS total_affected,
                       count(DISTINCT dep.file_path) AS affected_files
                LIMIT 1
            """, t=target)

            severity = "ISOLATED"
            total    = stats["total_affected"] if stats else len(rows)
            if total >= 30:   severity = "CRITICAL"
            elif total >= 10: severity = "HIGH"
            elif total >= 3:  severity = "MEDIUM"
            elif total >= 1:  severity = "LOW"

            return {
                "target":          target,
                "total_affected":  total,
                "severity":        severity,
                "affected_nodes":  rows,
            }

        elif tool_name == "get_callers":
            fname = args.get("function_name", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE toLower(n.name) CONTAINS toLower($fn)
                MATCH (caller:CodeNode {repo_id:$r})-[:DEPENDS_ON]->(n)
                RETURN DISTINCT caller.file_path AS file,
                       caller.name AS name,
                       caller.line_no AS line
                ORDER BY caller.file_path
                LIMIT 20
            """, fn=fname)
            return {"callers": rows, "count": len(rows)}

        elif tool_name == "get_deep_analysis":
            fname = args.get("function_name", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE toLower(n.name) CONTAINS toLower($fn)
                RETURN n.name                  AS name,
                       n.file_path             AS file,
                       n.line_no               AS line,
                       n.deep_risk_level       AS ast_risk,
                       n.deep_complexity       AS complexity,
                       n.deep_max_depth        AS nesting,
                       n.deep_logic_lines      AS logic_lines,
                       n.deep_branch_count     AS branches,
                       n.deep_raises           AS raises,
                       n.deep_risk_reasons     AS risk_reasons,
                       n.deep_branch_paths     AS branch_paths,
                       n.deep_is_async         AS is_async,
                       n.deep_return_type      AS return_type
                LIMIT 3
            """, fn=fname)
            return {"function": fname, "analysis": rows}

        elif tool_name == "get_exceptions":
            fname = args.get("function_name", "")
            direct = self.query("""
                MATCH (fn:CodeNode {repo_id:$r})
                WHERE toLower(fn.name) CONTAINS toLower($fn)
                MATCH (fn)-[rel:RAISES]->(ex:ExceptionNode {repo_id:$r})
                RETURN fn.name AS func, ex.exc_type AS exc_type,
                       rel.is_caught AS is_caught, rel.line_no AS line
            """, fn=fname)
            propagated = self.query("""
                MATCH (fn:CodeNode {repo_id:$r})
                WHERE toLower(fn.name) CONTAINS toLower($fn)
                MATCH (fn)-[rel:CAN_PROPAGATE]->(ex:ExceptionNode {repo_id:$r})
                RETURN fn.name AS func, ex.exc_type AS exc_type,
                       rel.callee AS from_callee, rel.line_no AS line
            """, fn=fname)
            return {
                "function":   fname,
                "direct":     direct,
                "propagated": propagated,
                "uncaught":   [e for e in direct if not e.get("is_caught")],
            }

        elif tool_name == "search_nodes":
            query = args.get("query", "")
            words = [w for w in query.split() if len(w) > 2][:3]
            if not words:
                words = [query]
            all_rows = []
            seen = set()
            for word in words:
                rows = self.query("""
                    MATCH (n:CodeNode {repo_id:$r})
                    WHERE (n.node_type IN ['function','file'])
                    AND (toLower(n.name) CONTAINS toLower($q)
                    OR toLower(n.file_path) CONTAINS toLower($q))
                    RETURN n.name AS name, n.file_path AS file,
                           n.node_type AS type, n.line_no AS line,
                           n.deep_risk_level AS risk
                    LIMIT 8
                """, q=word)
                for r in rows:
                    key = r.get("name","") + r.get("file","")
                    if key not in seen:
                        seen.add(key)
                        all_rows.append(r)
            return {"results": all_rows, "count": len(all_rows)}

        elif tool_name == "get_file_functions":
            fpath = args.get("file_path", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
                WHERE toLower(n.file_path) CONTAINS toLower($fp)
                OPTIONAL MATCH ()-[:DEPENDS_ON]->(n)
                WITH n, count(*) AS callers
                RETURN n.name             AS name,
                       n.line_no          AS line,
                       n.file_path        AS file_path,
                       n.deep_risk_level  AS risk,
                       n.deep_complexity  AS complexity,
                       n.deep_raises      AS raises,
                       callers
                ORDER BY n.line_no
                LIMIT 30
            """, fp=fpath)
            return {"file": fpath, "functions": rows, "count": len(rows)}

        elif tool_name == "get_callees":
            fname = args.get("function_name", "")
            rows = self.query("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE toLower(n.name) CONTAINS toLower($fn)
                MATCH (n)-[:DEPENDS_ON]->(callee:CodeNode {repo_id:$r})
                RETURN callee.name          AS name,
                       callee.file_path      AS file,
                       callee.line_no        AS line,
                       callee.deep_risk_level AS risk
                LIMIT 15
            """, fn=fname)
            return {"function": fname, "callees": rows, "count": len(rows)}

        return {"error": f"Unknown tool: {tool_name}"}

    # ── Target extraction ─────────────────────────────────────────────────────

    def _extract_target(self, message: str) -> str:
        import re
        file_match = re.search(
            r'[\w/\\]+\.(py|js|ts|java|go|jsx|tsx|rs)', message
        )
        if file_match:
            return file_match.group(0)

        stop = {
            "impact", "analyze", "analysis", "change", "karo", "dekho",
            "check", "kya", "hoga", "if", "what", "happens", "when",
            "the", "a", "an", "in", "of", "to", "is", "are", "will",
        }
        words = [w.strip("?.,!") for w in message.split()
                 if w.strip("?.,!").lower() not in stop and len(w) > 2]

        if words:
            for word in words[:4]:
                rows = self.query("""
                    MATCH (n:CodeNode {repo_id:$r})
                    WHERE toLower(n.name) CONTAINS toLower($kw)
                       OR toLower(n.file_path) CONTAINS toLower($kw)
                    RETURN n.name AS name LIMIT 1
                """, kw=word)
                if rows:
                    return rows[0]["name"]

        return words[0] if words else ""

    # ── Legacy methods — kept for backward compatibility ──────────────────────

    def analyze_function_change(self, function_id: str) -> ChangeImpact:
        result = self.run(
            user_message=f"Analyze impact of changing {function_id}",
            target=function_id,
        )
        rows = self.query("""
            MATCH (n:CodeNode {repo_id:$r})
            WHERE n.name=$t OR n.file_path ENDS WITH $t
            OPTIONAL MATCH (aff:CodeNode {repo_id:$r})-[:DEPENDS_ON*1..3]->(n)
            RETURN collect(DISTINCT aff.node_id)[..50] AS nodes,
                   collect(DISTINCT aff.file_path)[..20] AS files,
                   count(DISTINCT aff) AS total
            LIMIT 1
        """, t=function_id)

        row      = rows[0] if rows else {}
        total    = row.get("total", 0)
        files    = set(f for f in (row.get("files") or []) if f)
        nodes    = row.get("nodes") or []

        if total >= 30:   sev = ImpactSeverity.CRITICAL
        elif total >= 10: sev = ImpactSeverity.HIGH
        elif total >= 3:  sev = ImpactSeverity.MEDIUM
        elif total >= 1:  sev = ImpactSeverity.LOW
        else:             sev = ImpactSeverity.ISOLATED

        return ChangeImpact(
            change             = function_id,
            affected_nodes     = nodes,
            affected_files     = files,
            affected_functions = set(),
            affected_classes   = set(),
            severity           = sev,
            risk_level         = sev.value.upper(),
            recommendations    = [],
            migration_plan     = {},
            circular_deps      = [],
        )

    def analyze_file_change(self, file_path: str) -> ChangeImpact:
        return self.analyze_function_change(f"file:{file_path}")

    def analyze_multiple_changes(self, changes: List[str]) -> Dict:
        impacts = {c: self.analyze_function_change(c) for c in changes}
        all_aff = set()
        max_sev = ImpactSeverity.ISOLATED
        scores  = {ImpactSeverity.ISOLATED:0,ImpactSeverity.LOW:1,
                   ImpactSeverity.MEDIUM:2,ImpactSeverity.HIGH:3,ImpactSeverity.CRITICAL:4}
        for imp in impacts.values():
            all_aff.update(imp.affected_nodes)
            if scores[imp.severity] > scores[max_sev]:
                max_sev = imp.severity
        return {
            "changes":                changes,
            "individual_impacts":     impacts,
            "combined_affected_nodes":list(all_aff),
            "overall_severity":       max_sev.value,
        }

    def suggest_refactoring(self, function_id: str) -> Dict:
        result = self.run(f"Suggest refactoring for {function_id}", target=function_id)
        return {"function": function_id, "answer": result.get("answer", "")}

    def find_root_cause(self, failing_node: str) -> Dict:
        result = self.run(f"Find root cause for {failing_node}", target=failing_node)
        return {"failing_node": failing_node, "answer": result.get("answer", "")}

    def plan_api_change(self, function_id: str, description: str) -> Dict:
        result = self.run(
            f"Plan API change for {function_id}: {description}",
            target=function_id
        )
        return {"function": function_id, "answer": result.get("answer", "")}