"""
Deep AST Analyzer — Markar Knowledge Graph Enhancement
=======================================================
Multi-language deep analysis:
  Python  → Python ast module  (exact, complete)
  JS/TS   → tree-sitter        (branches, loops, try/catch/throw, async)
  Go      → tree-sitter        (error return pattern, defer, goroutines)
  Java    → tree-sitter        (checked exceptions, try/catch/throws)
  Rust    → tree-sitter        (Result/?, match arms, panic)

Har language ka output → same DeepFunctionAnalysis dataclass
→ same Neo4j properties → agents ko language ka pata nahi chahiye

Kaise use karo:
    analyzer = DeepRepositoryAnalyzer("/path/to/repo")
    results  = analyzer.analyze_all()
    # results → { "file.py" → { "func_name" → DeepFunctionAnalysis } }
"""

import ast
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES  — same for ALL languages
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BranchInfo:
    """Ek if/elif/else/switch/match branch."""
    branch_type: str        # "if"|"elif"|"else"|"switch_case"|"match_arm"|"ternary"
    condition: str          # human-readable condition text
    line_no: int
    leads_to_return: bool = False
    leads_to_raise: bool   = False
    raises_type: Optional[str]       = None
    return_value_hint: Optional[str] = None


@dataclass
class LoopInfo:
    """For/while/loop construct."""
    loop_type: str          # "for"|"while"|"loop" (Rust)|"range" (Go)
    line_no: int
    iterates_over: Optional[str] = None
    has_break: bool    = False
    has_continue: bool = False
    nesting_level: int = 0


@dataclass
class ExceptionPath:
    """Possible exception/error path."""
    exc_type: str           # "ValueError"|"error"|"Result<_,E>"|"IOException"
    origin: str             # "raise"|"throw"|"return_error"|"propagated_from:<callee>"
    line_no: int
    condition: Optional[str] = None
    is_caught: bool          = False
    caught_at_line: Optional[int] = None


@dataclass
class DataFlowInfo:
    """Variable flow inside function."""
    inputs: List[str]      = field(default_factory=list)   # parameters
    local_vars: List[str]  = field(default_factory=list)   # created vars
    returns: List[str]     = field(default_factory=list)   # return value hints
    mutates_args: List[str]= field(default_factory=list)   # args modified


@dataclass
class DeepFunctionAnalysis:
    """
    Complete deep analysis of ONE function.
    Language-agnostic — Python, JS, Go, Java, Rust sab ka same output.
    Neo4j function node pe yeh properties SET hongi (deep_ prefix).
    """
    function_name: str
    file_path: str
    language: str           # "python"|"javascript"|"go"|"java"|"rust"|"typescript"
    line_start: int
    line_end: int

    # Control flow
    branches: List[BranchInfo]       = field(default_factory=list)
    loops: List[LoopInfo]            = field(default_factory=list)
    exception_paths: List[ExceptionPath] = field(default_factory=list)
    has_try_except: bool = False

    # Data flow
    data_flow: DataFlowInfo = field(default_factory=DataFlowInfo)

    # Complexity
    cyclomatic_complexity: int = 1
    max_nesting_depth: int     = 0
    lines_of_logic: int        = 0
    total_lines: int           = 0

    # Async patterns
    is_async: bool   = False
    has_await: bool  = False

    # Return analysis
    always_returns: bool           = False
    can_return_none: bool          = False
    return_type_hint: Optional[str]= None

    # Risk
    risk_level: str        = "LOW"   # LOW|MEDIUM|HIGH|CRITICAL
    risk_reasons: List[str]= field(default_factory=list)

    # ── Neo4j serialization ───────────────────────────────────────────────────

    def to_neo4j_properties(self) -> Dict:
        """Flat dict — Neo4j node pe SET hoga (existing node pe, DELETE nahi)."""
        return {
            "deep_language":        self.language,
            "deep_complexity":      self.cyclomatic_complexity,
            "deep_max_depth":       self.max_nesting_depth,
            "deep_logic_lines":     self.lines_of_logic,
            "deep_total_lines":     self.total_lines,
            "deep_is_async":        self.is_async,
            "deep_has_await":       self.has_await,
            "deep_has_try_except":  self.has_try_except,
            "deep_always_returns":  self.always_returns,
            "deep_can_return_none": self.can_return_none,
            "deep_return_type":     self.return_type_hint or "",
            "deep_risk_level":      self.risk_level,
            "deep_risk_reasons":    "|".join(self.risk_reasons),
            "deep_branch_count":    len(self.branches),
            "deep_loop_count":      len(self.loops),
            "deep_exception_count": len(self.exception_paths),
            "deep_raises":          "|".join(
                                        set(e.exc_type for e in self.exception_paths
                                            if e.origin in ("raise","throw","return_error"))),
            "deep_can_propagate":   "|".join(
                                        set(e.exc_type for e in self.exception_paths
                                            if e.origin.startswith("propagated"))),
            "deep_branch_paths":    self._serialize_branches(),
            "deep_data_inputs":     "|".join(self.data_flow.inputs[:10]),
            "deep_data_returns":    "|".join(self.data_flow.returns[:5]),
            "deep_source_code":     self._get_source_snippet(),
        }

    def _serialize_branches(self) -> str:
        parts = []
        for b in self.branches[:10]:
            part = f"{b.branch_type}:{b.condition[:40]}@{b.line_no}"
            if b.leads_to_raise and b.raises_type:
                part += f"->raise({b.raises_type})"
            elif b.leads_to_return:
                part += "->return"
            parts.append(part)
        return ";".join(parts)
    
    def _get_source_snippet(self) -> str:
        try:
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                 lines = f.readlines()
            snippet = lines[self.line_start - 1 : self.line_end]
            return "".join(snippet[:50])
        except Exception:
            return ""
                 
    def human_summary(self) -> str:
        """Agent ke LLM prompt mein directly inject karo."""
        lines = [
            f"Function `{self.function_name}` [{self.language}] "
            f"(lines {self.line_start}-{self.line_end}):",
            f"  Risk: {self.risk_level}" +
            (f" — {', '.join(self.risk_reasons)}" if self.risk_reasons else ""),
            f"  Complexity: {self.cyclomatic_complexity} | "
            f"Nesting: {self.max_nesting_depth} | "
            f"Logic lines: {self.lines_of_logic}/{self.total_lines}",
        ]
        if self.is_async:
            lines.append(f"  Async {'(uses await)' if self.has_await else ''}")
        if self.branches:
            lines.append(f"  Branches ({len(self.branches)}):")
            for b in self.branches[:6]:
                arrow = (f" -> raises {b.raises_type or 'Exception'}"
                         if b.leads_to_raise else
                         " -> returns" if b.leads_to_return else "")
                lines.append(f"    [{b.branch_type}@{b.line_no}] `{b.condition[:55]}`{arrow}")
        raised = [e for e in self.exception_paths
                  if e.origin in ("raise","throw","return_error")]
        propagated = [e for e in self.exception_paths
                      if e.origin.startswith("propagated")]
        if raised:
            uncaught = [e for e in raised if not e.is_caught]
            types = ", ".join(set(e.exc_type for e in raised))
            lines.append(f"  Raises/throws: {types}"
                         + (f" ({len(uncaught)} uncaught)" if uncaught else " (all caught)"))
        if propagated:
            callees = ", ".join(set(e.origin.split(":",1)[1] for e in propagated))
            lines.append(f"  Can propagate from: {callees}")
        if self.loops:
            lines.append("  Loops: " +
                         ", ".join(f"{l.loop_type}@{l.line_no}"
                                   + (" +break" if l.has_break else "")
                                   for l in self.loops[:4]))
        if self.data_flow.returns:
            lines.append(f"  Returns: {', '.join(self.data_flow.returns[:4])}")
        if self.return_type_hint:
            lines.append(f"  Return type: {self.return_type_hint}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# PYTHON DEEP ANALYZER  — Python ast module (most accurate)
# ═══════════════════════════════════════════════════════════════════════════════

class PythonDeepAnalyzer:
    """Python ast module se exact deep analysis."""

    RISKY_PATTERNS = [
        "validate","assert_","check","verify","parse","deserialize",
        "decode","load","get_or_404","get_or_raise","raise_for_status","unwrap",
    ]

    def __init__(self, source_lines: List[str], file_path: str):
        self.source_lines = source_lines
        self.file_path    = file_path
        self._max_nesting = 0
        self._active_handlers: List[str] = []

    def analyze(self, func_node) -> DeepFunctionAnalysis:
        result = DeepFunctionAnalysis(
            function_name=func_node.name,
            file_path=self.file_path,
            language="python",
            line_start=func_node.lineno,
            line_end=getattr(func_node, "end_lineno", func_node.lineno),
            is_async=isinstance(func_node, ast.AsyncFunctionDef),
        )
        if func_node.returns:
            try:
                result.return_type_hint = ast.unparse(func_node.returns)
            except Exception:
                pass

        result.data_flow.inputs = [
            a.arg for a in func_node.args.args
            if a.arg not in ("self","cls")
        ]
        result.total_lines    = result.line_end - result.line_start + 1
        result.lines_of_logic = self._logic_lines(result.line_start, result.line_end)

        self._max_nesting     = 0
        self._active_handlers = []
        self._walk(func_node.body, result, 0)

        result.cyclomatic_complexity = 1 + len(result.branches) + len(result.loops)
        result.max_nesting_depth     = self._max_nesting
        self._analyze_returns(func_node, result)
        result.has_await = any(isinstance(n, ast.Await) for n in ast.walk(func_node))
        _score_risk(result)
        return result

    def _walk(self, stmts: list, r: DeepFunctionAnalysis, nesting: int):
        self._max_nesting = max(self._max_nesting, nesting)
        for stmt in stmts:

            if isinstance(stmt, ast.If):
                self._if(stmt, r, nesting)

            elif isinstance(stmt, ast.For):
                lp = LoopInfo("for", stmt.lineno,
                              self._unparse(stmt.iter)[:60],
                              self._has(stmt.body, ast.Break),
                              self._has(stmt.body, ast.Continue),
                              nesting)
                r.loops.append(lp)
                self._walk(stmt.body, r, nesting+1)
                if stmt.orelse: self._walk(stmt.orelse, r, nesting+1)

            elif isinstance(stmt, ast.While):
                lp = LoopInfo("while", stmt.lineno,
                              self._unparse(stmt.test)[:60],
                              self._has(stmt.body, ast.Break),
                              self._has(stmt.body, ast.Continue),
                              nesting)
                r.loops.append(lp)
                self._walk(stmt.body, r, nesting+1)

            elif isinstance(stmt, ast.Try):
                r.has_try_except = True
                caught = []
                for h in stmt.handlers:
                    if h.type:
                        ename = self._unparse(h.type)
                        caught.append(ename)
                        for ep in r.exception_paths:
                            if ep.exc_type == ename and not ep.is_caught:
                                ep.is_caught = True
                                ep.caught_at_line = h.lineno
                prev = self._active_handlers
                self._active_handlers = caught
                self._walk(stmt.body, r, nesting+1)
                self._active_handlers = prev
                for h in stmt.handlers:
                    self._walk(h.body, r, nesting+1)
                if hasattr(stmt,"finalbody") and stmt.finalbody:
                    self._walk(stmt.finalbody, r, nesting+1)

            elif isinstance(stmt, ast.Raise):
                et = "Exception"
                if stmt.exc:
                    et = (self._unparse(stmt.exc.func)
                          if isinstance(stmt.exc, ast.Call)
                          else self._unparse(stmt.exc))
                r.exception_paths.append(ExceptionPath(
                    exc_type=et, origin="raise",
                    line_no=stmt.lineno,
                    is_caught=bool(self._active_handlers),
                    caught_at_line=stmt.lineno if self._active_handlers else None,
                ))

            elif isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    v = self._unparse(t)
                    if v and len(v)<40 and v not in r.data_flow.local_vars:
                        r.data_flow.local_vars.append(v)

            elif isinstance(stmt, ast.AnnAssign) and stmt.target:
                v = self._unparse(stmt.target)
                if v and len(v)<40 and v not in r.data_flow.local_vars:
                    r.data_flow.local_vars.append(v)

            elif isinstance(stmt, ast.With):
                self._walk(stmt.body, r, nesting+1)

            elif hasattr(ast,"Match") and isinstance(stmt, ast.Match):
                for case in stmt.cases:
                    b = BranchInfo("match_case",
                                   f"match {self._unparse(stmt.subject)[:40]}",
                                   getattr(case.pattern,"lineno",stmt.lineno))
                    self._branch_outcome(case.body, b)
                    r.branches.append(b)
                    self._walk(case.body, r, nesting+1)

            # Risky call propagation
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call):
                    self._propagation(node, r)

    def _if(self, stmt: ast.If, r: DeepFunctionAnalysis, nesting: int):
        cond = self._unparse(stmt.test)[:80]
        b = BranchInfo("if", cond, stmt.lineno)
        self._branch_outcome(stmt.body, b)
        r.branches.append(b)
        self._walk(stmt.body, r, nesting+1)
        if stmt.orelse:
            if len(stmt.orelse)==1 and isinstance(stmt.orelse[0], ast.If):
                ei = stmt.orelse[0]
                eb = BranchInfo("elif", self._unparse(ei.test)[:80], ei.lineno)
                self._branch_outcome(ei.body, eb)
                r.branches.append(eb)
                self._walk(stmt.orelse, r, nesting+1)
            else:
                ln = stmt.orelse[0].lineno if stmt.orelse else stmt.lineno
                eb = BranchInfo("else","otherwise", ln)
                self._branch_outcome(stmt.orelse, eb)
                r.branches.append(eb)
                self._walk(stmt.orelse, r, nesting+1)

    def _branch_outcome(self, stmts: list, b: BranchInfo):
        for s in stmts:
            if isinstance(s, ast.Return):
                b.leads_to_return = True
                if s.value: b.return_value_hint = self._unparse(s.value)[:40]
            elif isinstance(s, ast.Raise):
                b.leads_to_raise = True
                if s.exc:
                    b.raises_type = (self._unparse(s.exc.func)
                                     if isinstance(s.exc,ast.Call)
                                     else self._unparse(s.exc))

    def _propagation(self, call: ast.Call, r: DeepFunctionAnalysis):
        callee = self._unparse(call.func).lower()
        for pat in self.RISKY_PATTERNS:
            if pat in callee:
                orig = f"propagated_from:{self._unparse(call.func)}"
                if orig not in {e.origin for e in r.exception_paths}:
                    r.exception_paths.append(ExceptionPath(
                        exc_type="Exception", origin=orig,
                        line_no=call.lineno,
                        is_caught=bool(self._active_handlers),
                    ))
                break

    def _analyze_returns(self, fn, r: DeepFunctionAnalysis):
        rets = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
        r.always_returns = bool(rets)
        for ret in rets:
            if ret.value is None:
                r.can_return_none = True
                if "None" not in r.data_flow.returns:
                    r.data_flow.returns.append("None")
            else:
                h = self._unparse(ret.value)[:40]
                if h not in r.data_flow.returns:
                    r.data_flow.returns.append(h)

    def _unparse(self, node) -> str:
        try:    return ast.unparse(node)
        except: return type(node).__name__

    def _has(self, stmts, ntype) -> bool:
        return any(isinstance(n,ntype) for s in stmts for n in ast.walk(s))

    def _logic_lines(self, start, end) -> int:
        count = 0
        for i in range(start-1, min(end, len(self.source_lines))):
            s = self.source_lines[i].strip()
            if s and not s.startswith("#"): count += 1
        return count


# ═══════════════════════════════════════════════════════════════════════════════
# TREE-SITTER BASE  — JS, Go, Java, Rust ke liye common walker
# ═══════════════════════════════════════════════════════════════════════════════

class TreeSitterDeepAnalyzer:
    """
    Base class for non-Python languages via tree-sitter.
    Subclass karo aur language-specific node names provide karo.
    """

    # Subclasses override these
    LANG_NAME        = "unknown"
    BRANCH_NODES     = []        # node types that represent branches
    LOOP_NODES       = []        # node types that are loops
    TRY_NODES        = []        # try-like nodes
    THROW_NODES      = []        # throw/raise/return error nodes
    RETURN_NODES     = ["return_statement"]
    FUNC_NODES       = []        # function declaration types
    ASYNC_KEYWORDS   = []        # "async" keyword identifiers
    CONDITION_FIELD  = "condition"   # field name for if condition
    CONSEQUENCE_FIELD= "consequence" # field name for if body

    def __init__(self, source: bytes, file_path: str):
        self.source    = source
        self.file_path = file_path
        self._max_nesting = 0

    def analyze_function(self, func_node, lang) -> Optional[DeepFunctionAnalysis]:
        """Tree-sitter function node ka deep analysis."""
        name = self._func_name(func_node)
        if not name:
            return None

        line_start = func_node.start_point[0] + 1
        line_end   = func_node.end_point[0]   + 1

        result = DeepFunctionAnalysis(
            function_name=name,
            file_path=self.file_path,
            language=self.LANG_NAME,
            line_start=line_start,
            line_end=line_end,
            is_async=self._is_async(func_node),
            total_lines=line_end - line_start + 1,
        )

        result.lines_of_logic = self._logic_lines(func_node)
        result.data_flow.inputs = self._params(func_node)
        result.return_type_hint = self._return_type(func_node)

        self._max_nesting = 0
        self._walk_node(func_node, result, 0)
        result.max_nesting_depth = self._max_nesting

        result.cyclomatic_complexity = 1 + len(result.branches) + len(result.loops)
        _score_risk(result)
        return result

    def _walk_node(self, node, r: DeepFunctionAnalysis, nesting: int):
        self._max_nesting = max(self._max_nesting, nesting)
        ntype = node.type

        if ntype in self.BRANCH_NODES:
            self._handle_branch(node, r, nesting)

        elif ntype in self.LOOP_NODES:
            ltype = "for" if "for" in ntype else "while" if "while" in ntype else "loop"
            lp = LoopInfo(ltype, node.start_point[0]+1,
                          nesting_level=nesting,
                          has_break=self._subtree_has(node,"break_statement"),
                          has_continue=self._subtree_has(node,"continue_statement"))
            r.loops.append(lp)
            for c in node.children:
                self._walk_node(c, r, nesting+1)

        elif ntype in self.TRY_NODES:
            r.has_try_except = True
            for c in node.children:
                self._walk_node(c, r, nesting+1)

        elif ntype in self.THROW_NODES:
            et = self._throw_type(node)
            r.exception_paths.append(ExceptionPath(
                exc_type=et, origin="throw",
                line_no=node.start_point[0]+1,
            ))

        else:
            # Check for return
            if ntype in self.RETURN_NODES:
                r.always_returns = True
                hint = self._node_text(node)[:40]
                if hint and hint not in r.data_flow.returns:
                    r.data_flow.returns.append(hint)

            # Check await
            if "await" in ntype.lower():
                r.has_await = True

            for c in node.children:
                self._walk_node(c, r, nesting)

    def _handle_branch(self, node, r: DeepFunctionAnalysis, nesting: int):
        """if/switch branch handle karo."""
        cond_node = node.child_by_field_name(self.CONDITION_FIELD)
        cond = self._node_text(cond_node)[:80] if cond_node else "condition"
        b = BranchInfo("if", cond, node.start_point[0]+1)

        # Check if body leads to throw/return
        conseq = node.child_by_field_name(self.CONSEQUENCE_FIELD)
        if conseq:
            b.leads_to_return = self._subtree_has(conseq, *self.RETURN_NODES)
            b.leads_to_raise  = self._subtree_has(conseq, *self.THROW_NODES)
            self._walk_node(conseq, r, nesting+1)

        r.branches.append(b)

        # else / alternate
        alt = node.child_by_field_name("alternative") or node.child_by_field_name("else")
        if alt:
            eb = BranchInfo("else","otherwise", alt.start_point[0]+1)
            eb.leads_to_return = self._subtree_has(alt, *self.RETURN_NODES)
            eb.leads_to_raise  = self._subtree_has(alt, *self.THROW_NODES)
            r.branches.append(eb)
            self._walk_node(alt, r, nesting+1)

    def _node_text(self, node) -> str:
        if node is None: return ""
        try:   return self.source[node.start_byte:node.end_byte].decode("utf-8","replace").strip()
        except: return ""

    def _subtree_has(self, node, *types) -> bool:
        if node.type in types: return True
        return any(self._subtree_has(c,*types) for c in node.children)

    def _logic_lines(self, node) -> int:
        start = node.start_point[0]
        end   = node.end_point[0]
        src   = self.source.decode("utf-8","replace").splitlines()
        count = 0
        for i in range(start, min(end+1, len(src))):
            s = src[i].strip()
            if s and not s.startswith("//") and not s.startswith("*") and s not in ("{","}"): count+=1
        return count

    def _is_async(self, node) -> bool:
        t = self._node_text(node)
        return "async" in t[:20]

    def _func_name(self, node) -> Optional[str]:
        for fname in ("name","identifier"):
            c = node.child_by_field_name(fname)
            if c: return self._node_text(c)
        for c in node.children:
            if c.type in ("identifier","property_identifier"):
                return self._node_text(c)
        return None

    def _params(self, node) -> List[str]:
        for fname in ("parameters","params","parameter_list"):
            p = node.child_by_field_name(fname)
            if p:
                return [self._node_text(c) for c in p.children
                        if c.type in ("identifier","required_parameter",
                                      "optional_parameter","parameter","formal_parameter")][:8]
        return []

    def _return_type(self, node) -> Optional[str]:
        for fname in ("return_type","result","type"):
            c = node.child_by_field_name(fname)
            if c: return self._node_text(c)[:40]
        return None

    def _throw_type(self, node) -> str:
        for c in node.children:
            t = self._node_text(c)
            if t and t not in ("throw","raise","return"): return t[:40]
        return "Exception"


# ── JavaScript / TypeScript deep analyzer ────────────────────────────────────

class JSDeepAnalyzer(TreeSitterDeepAnalyzer):
    LANG_NAME         = "javascript"
    BRANCH_NODES      = ["if_statement","switch_case","ternary_expression","conditional_expression"]
    LOOP_NODES        = ["for_statement","for_in_statement","for_of_statement",
                         "while_statement","do_statement"]
    TRY_NODES         = ["try_statement"]
    THROW_NODES       = ["throw_statement"]
    RETURN_NODES      = ["return_statement"]
    FUNC_NODES        = ["function_declaration","function","arrow_function","method_definition"]
    CONDITION_FIELD   = "condition"
    CONSEQUENCE_FIELD = "consequence"

    def _throw_type(self, node) -> str:
        txt = self._node_text(node)
        # "throw new SomeError(...)" → "SomeError"
        m = re.search(r"new\s+(\w+Error|\w+Exception|\w+)", txt)
        if m: return m.group(1)
        return "Error"


class TSDeepAnalyzer(JSDeepAnalyzer):
    LANG_NAME = "typescript"


# ── Go deep analyzer ──────────────────────────────────────────────────────────

class GoDeepAnalyzer(TreeSitterDeepAnalyzer):
    """
    Go mein exceptions nahi hain — error return pattern detect karta hai:
      if err != nil { return nil, err }
    Goroutines aur defer bhi track karta hai.
    """
    LANG_NAME         = "go"
    BRANCH_NODES      = ["if_statement","type_switch_statement","expression_switch_statement"]
    LOOP_NODES        = ["for_statement"]          # Go has only for
    TRY_NODES         = []                          # no try in Go
    THROW_NODES       = []                          # no throw — error return
    RETURN_NODES      = ["return_statement"]
    FUNC_NODES        = ["function_declaration","method_declaration","func_literal"]
    CONDITION_FIELD   = "condition"
    CONSEQUENCE_FIELD = "consequence"

    def _walk_node(self, node, r: DeepFunctionAnalysis, nesting: int):
        """Override: detect Go error patterns."""
        ntype = node.type

        # Go error return pattern: if err != nil
        if ntype == "if_statement":
            cond = node.child_by_field_name("condition")
            cond_txt = self._node_text(cond) if cond else ""
            if "err" in cond_txt and "nil" in cond_txt:
                # This is Go's "exception" equivalent
                conseq = node.child_by_field_name("consequence")
                b = BranchInfo("if", cond_txt[:80], node.start_point[0]+1,
                               leads_to_return=bool(conseq and
                                                    self._subtree_has(conseq,"return_statement")))
                r.branches.append(b)
                r.exception_paths.append(ExceptionPath(
                    exc_type="error",
                    origin="return_error",
                    line_no=node.start_point[0]+1,
                    condition=cond_txt[:60],
                ))
                if conseq: self._walk_node(conseq, r, nesting+1)
                return

        # Goroutine — async indicator
        if ntype == "go_statement":
            r.is_async = True

        # defer — treat as complexity+1
        if ntype == "defer_statement":
            r.loops.append(LoopInfo("defer", node.start_point[0]+1,
                                    nesting_level=nesting))

        # Panic
        if ntype == "call_expression":
            fn = node.child_by_field_name("function")
            if fn and self._node_text(fn) == "panic":
                r.exception_paths.append(ExceptionPath(
                    exc_type="panic",
                    origin="throw",
                    line_no=node.start_point[0]+1,
                ))

        super()._walk_node(node, r, nesting)

    def _is_async(self, node) -> bool:
        # Check if function body has goroutines
        return self._subtree_has(node, "go_statement")


# ── Java deep analyzer ───────────────────────────────────────────────────────

class JavaDeepAnalyzer(TreeSitterDeepAnalyzer):
    LANG_NAME         = "java"
    BRANCH_NODES      = ["if_statement","switch_expression","switch_statement","ternary_expression"]
    LOOP_NODES        = ["for_statement","enhanced_for_statement","while_statement","do_statement"]
    TRY_NODES         = ["try_statement","try_with_resources_statement"]
    THROW_NODES       = ["throw_statement"]
    RETURN_NODES      = ["return_statement"]
    FUNC_NODES        = ["method_declaration","constructor_declaration"]
    CONDITION_FIELD   = "condition"
    CONSEQUENCE_FIELD = "consequence"

    def _throw_type(self, node) -> str:
        txt = self._node_text(node)
        m = re.search(r"new\s+(\w+Exception|\w+Error|\w+)", txt)
        if m: return m.group(1)
        # throws declaration mein bhi check karo
        m2 = re.search(r"throw\s+(\w+)", txt)
        if m2: return m2.group(1)
        return "Exception"

    def _return_type(self, node) -> Optional[str]:
        # Java: return type is before method name
        c = node.child_by_field_name("type")
        if c: return self._node_text(c)[:40]
        return None


# ── Rust deep analyzer ───────────────────────────────────────────────────────

class RustDeepAnalyzer(TreeSitterDeepAnalyzer):
    """
    Rust: Result<T,E>, ? operator, match arms, panic!
    """
    LANG_NAME         = "rust"
    BRANCH_NODES      = ["if_expression","match_expression","if_let_expression"]
    LOOP_NODES        = ["loop_expression","for_expression","while_expression",
                         "while_let_expression"]
    TRY_NODES         = []               # no try — ? operator
    THROW_NODES       = ["macro_invocation"]  # panic!
    RETURN_NODES      = ["return_expression"]
    FUNC_NODES        = ["function_item"]
    CONDITION_FIELD   = "condition"
    CONSEQUENCE_FIELD = "consequence"

    def _walk_node(self, node, r: DeepFunctionAnalysis, nesting: int):
        ntype = node.type

        # ? operator — Result propagation
        if ntype == "try_expression":
            inner = self._node_text(node)[:40]
            r.exception_paths.append(ExceptionPath(
                exc_type="Err(?)",
                origin="propagated_from:?-operator",
                line_no=node.start_point[0]+1,
            ))

        # match arms — each arm is a branch
        if ntype == "match_arm":
            pat = node.child_by_field_name("pattern")
            pat_txt = self._node_text(pat)[:60] if pat else "pattern"
            b = BranchInfo("match_arm", pat_txt, node.start_point[0]+1)
            body = node.child_by_field_name("value")
            if body:
                b.leads_to_return = self._subtree_has(body,"return_expression")
            r.branches.append(b)

        # panic! macro
        if ntype == "macro_invocation":
            macro_name = node.child_by_field_name("macro")
            if macro_name and "panic" in self._node_text(macro_name):
                r.exception_paths.append(ExceptionPath(
                    exc_type="panic",
                    origin="throw",
                    line_no=node.start_point[0]+1,
                ))

        # async fn
        if ntype == "function_item":
            txt = self._node_text(node)[:30]
            if "async" in txt:
                r.is_async = True

        super()._walk_node(node, r, nesting)

    def _throw_type(self, node) -> str:
        txt = self._node_text(node)
        if "panic" in txt: return "panic"
        return "Err"


# ═══════════════════════════════════════════════════════════════════════════════
# RISK SCORER  — language-agnostic, same formula for all
# ═══════════════════════════════════════════════════════════════════════════════

def _score_risk(r: DeepFunctionAnalysis):
    """DeepFunctionAnalysis mein risk_level aur risk_reasons fill karo."""
    reasons = []

    if r.cyclomatic_complexity >= 15:
        reasons.append(f"complexity={r.cyclomatic_complexity} (very high)")
    elif r.cyclomatic_complexity >= 8:
        reasons.append(f"complexity={r.cyclomatic_complexity} (high)")

    if r.max_nesting_depth >= 5:
        reasons.append(f"nesting={r.max_nesting_depth}")
    elif r.max_nesting_depth >= 4:
        reasons.append(f"nesting={r.max_nesting_depth} (moderate)")

    if r.lines_of_logic >= 100:
        reasons.append(f"logic_lines={r.lines_of_logic} (split this function)")
    elif r.lines_of_logic >= 60:
        reasons.append(f"logic_lines={r.lines_of_logic} (large)")

    uncaught = [e for e in r.exception_paths
                if not e.is_caught and e.origin in ("raise","throw","return_error")]
    if len(uncaught) >= 3:
        reasons.append(f"{len(uncaught)} uncaught raises/throws")
    elif len(uncaught) >= 1 and r.cyclomatic_complexity >= 5:
        reasons.append("uncaught raise in complex function")

    nested_loops = [l for l in r.loops if l.nesting_level >= 2]
    if nested_loops:
        reasons.append(f"nested loops (depth={max(l.nesting_level for l in nested_loops)})")

    if not r.always_returns and len(r.branches) > 3:
        reasons.append("multiple branches, no guaranteed return")

    if reasons:
        n = len(reasons)
        if n >= 3 or r.cyclomatic_complexity >= 15:
            r.risk_level = "CRITICAL"
        elif n >= 2 or r.cyclomatic_complexity >= 8:
            r.risk_level = "HIGH"
        else:
            r.risk_level = "MEDIUM"
    else:
        r.risk_level = "LOW"

    r.risk_reasons = reasons


# ═══════════════════════════════════════════════════════════════════════════════
# FILE-LEVEL ANALYZERS
# ═══════════════════════════════════════════════════════════════════════════════

class PythonDeepFileAnalyzer:
    """Ek Python file ke saare functions ka deep analysis."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def analyze(self) -> Dict[str, DeepFunctionAnalysis]:
        try:
            with open(self.file_path,"r",encoding="utf-8",errors="replace") as f:
                source = f.read()
            lines = source.splitlines()
            tree  = ast.parse(source)
        except Exception as e:
            print(f"[DeepPython] {self.file_path}: {e}")
            return {}

        results: Dict[str, DeepFunctionAnalysis] = {}
        analyzer = PythonDeepAnalyzer(lines, self.file_path)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                try:
                    analysis = analyzer.analyze(node)
                    key = node.name
                    if key in results:
                        key = f"{node.name}_{node.lineno}"
                    results[key] = analysis
                except Exception as e:
                    print(f"[DeepPython] func {node.name}: {e}")

        return results


class TSDeepFileAnalyzer:
    """JS/TS/Go/Java/Rust files ka deep analysis via tree-sitter."""

    LANG_ANALYZER_MAP = {
        "javascript": JSDeepAnalyzer,
        "typescript": TSDeepAnalyzer,
        "tsx":        TSDeepAnalyzer,
        "go":         GoDeepAnalyzer,
        "java":       JavaDeepAnalyzer,
        "rust":       RustDeepAnalyzer,
    }

    FUNC_NODE_MAP = {
        "javascript": ["function_declaration","function","arrow_function","method_definition"],
        "typescript": ["function_declaration","function","arrow_function","method_definition",
                       "method_signature"],
        "tsx":        ["function_declaration","function","arrow_function","method_definition"],
        "go":         ["function_declaration","method_declaration","func_literal"],
        "java":       ["method_declaration","constructor_declaration"],
        "rust":       ["function_item"],
    }

    def __init__(self, file_path: str, language: str):
        self.file_path = file_path
        self.language  = language

    def analyze(self) -> Dict[str, DeepFunctionAnalysis]:
        analyzer_cls = self.LANG_ANALYZER_MAP.get(self.language)
        func_nodes   = self.FUNC_NODE_MAP.get(self.language, [])
        if not analyzer_cls or not func_nodes:
            return {}

        try:
            with open(self.file_path,"rb") as f:
                source = f.read()
        except Exception:
            return {}

        lang = self._load_ts_lang()
        if lang is None:
            return {}

        try:
            import tree_sitter
            parser = tree_sitter.Parser(lang)
            tree   = parser.parse(source)
        except Exception as e:
            print(f"[DeepTS] parse {self.file_path}: {e}")
            return {}

        ts_analyzer = analyzer_cls(source, self.file_path)
        results: Dict[str, DeepFunctionAnalysis] = {}

        def walk(node):
            if node.type in func_nodes:
                try:
                    analysis = ts_analyzer.analyze_function(node, lang)
                    if analysis:
                        key = analysis.function_name
                        if key in results:
                            key = f"{key}_{node.start_point[0]+1}"
                        results[key] = analysis
                except Exception as e:
                    print(f"[DeepTS] func in {self.file_path}: {e}")
            for c in node.children:
                walk(c)

        walk(tree.root_node)
        return results

    def _load_ts_lang(self):
        """Existing universal_parser._load_language() se same logic."""
        pkg_map = {
            "javascript": "tree_sitter_javascript",
            "typescript": "tree_sitter_typescript",
            "tsx":        "tree_sitter_typescript",
            "go":         "tree_sitter_go",
            "java":       "tree_sitter_java",
            "rust":       "tree_sitter_rust",
        }
        pkg_name = pkg_map.get(self.language)
        if not pkg_name: return None
        try:
            import tree_sitter
            pkg = __import__(pkg_name)
            lang_func = getattr(pkg,"language",None)
            if lang_func is None: return None
            raw = lang_func() if callable(lang_func) else lang_func
            return tree_sitter.Language(raw)
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# REPOSITORY-LEVEL ANALYZER  — public API
# ═══════════════════════════════════════════════════════════════════════════════

PYTHON_EXTS = {".py",".pyi"}
JS_EXTS     = {".js",".mjs",".cjs",".jsx"}
TS_EXTS     = {".ts",".tsx"}
GO_EXTS     = {".go"}
JAVA_EXTS   = {".java",".kt"}
RUST_EXTS   = {".rs"}

SUPPORTED_EXTS = PYTHON_EXTS | JS_EXTS | TS_EXTS | GO_EXTS | JAVA_EXTS | RUST_EXTS

EXCLUDE_DIRS = {
    ".git",".venv","venv","__pycache__","node_modules",
    ".pytest_cache",".mypy_cache","dist","build",".next",
    "target","bin","obj","migrations",".idea",".vscode",
}


class DeepRepositoryAnalyzer:
    """
    Poore repository ka multi-language deep analysis.
    Orchestrator ke initialize() ke baad call hota hai.

    Usage:
        dr = DeepRepositoryAnalyzer("/path/to/repo")
        all_results = dr.analyze_all()
        summary     = dr.summary(all_results)
        high_risk   = dr.get_high_risk(all_results)
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def analyze_all(self) -> Dict[str, Dict[str, DeepFunctionAnalysis]]:
        """
        Returns: { "relative/file.ext" → { "func_name" → DeepFunctionAnalysis } }
        All supported languages, parallel.
        """
        files = self._collect_files()
        if not files:
            return {}

        results: Dict[str, Dict[str, DeepFunctionAnalysis]] = {}
        workers = min(16, os.cpu_count() or 4)

        def _analyze_one(args):
            abs_path, rel_path, lang = args
            try:
                if lang == "python":
                    analysis = PythonDeepFileAnalyzer(abs_path).analyze()
                else:
                    analysis = TSDeepFileAnalyzer(abs_path, lang).analyze()
                return rel_path, analysis
            except Exception as e:
                print(f"[DeepRepo] {rel_path}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for res in pool.map(_analyze_one, files):
                if res:
                    rel_path, analysis = res
                    if analysis:
                        results[rel_path] = analysis

        total = sum(len(v) for v in results.values())
        lang_counts = {}
        for _, _, lang in files:
            lang_counts[lang] = lang_counts.get(lang,0) + 1
        print(f"[DeepAST] {len(results)} files | {total} functions | langs: {lang_counts}")
        return results

    def _collect_files(self) -> List[Tuple[str,str,str]]:
        """Returns list of (abs_path, rel_path, language)."""
        result = []
        for p in self.repo_path.rglob("*"):
            if not p.is_file(): continue
            if any(excl in p.parts for excl in EXCLUDE_DIRS): continue
            ext  = p.suffix.lower()
            lang = self._ext_to_lang(ext)
            if lang is None: continue
            rel = os.path.relpath(str(p), str(self.repo_path))
            result.append((str(p), rel, lang))
        return result

    def _ext_to_lang(self, ext: str) -> Optional[str]:
        if ext in PYTHON_EXTS: return "python"
        if ext in JS_EXTS:     return "javascript"
        if ext in TS_EXTS:     return "typescript"
        if ext in GO_EXTS:     return "go"
        if ext in JAVA_EXTS:   return "java"
        if ext in RUST_EXTS:   return "rust"
        return None

    def get_high_risk(
        self, all_analysis: Dict[str, Dict[str, DeepFunctionAnalysis]]
    ) -> List[Tuple[str, str, DeepFunctionAnalysis]]:
        """HIGH + CRITICAL functions, severity order mein."""
        risky = [
            (fp, fn, a)
            for fp, funcs in all_analysis.items()
            for fn, a in funcs.items()
            if a.risk_level in ("HIGH","CRITICAL")
        ]
        risky.sort(key=lambda x: (
            0 if x[2].risk_level=="CRITICAL" else 1,
            -x[2].cyclomatic_complexity,
        ))
        return risky

    def summary(self, all_analysis: Dict[str, Dict[str, DeepFunctionAnalysis]]) -> Dict:
        """Dashboard + orchestrator ke liye summary."""
        total = sum(len(v) for v in all_analysis.values())
        risks = {"LOW":0,"MEDIUM":0,"HIGH":0,"CRITICAL":0}
        langs: Dict[str,int] = {}
        tc = 0; mc = 0; mc_func = None

        for fp, funcs in all_analysis.items():
            for fn, a in funcs.items():
                risks[a.risk_level] = risks.get(a.risk_level,0) + 1
                langs[a.language]   = langs.get(a.language,0) + 1
                tc += a.cyclomatic_complexity
                if a.cyclomatic_complexity > mc:
                    mc = a.cyclomatic_complexity
                    mc_func = f"{fp}:{fn}"

        return {
            "files_analyzed":     len(all_analysis),
            "functions_analyzed": total,
            "languages":          langs,
            "risk_distribution":  risks,
            "avg_complexity":     round(tc/total,2) if total else 0,
            "max_complexity":     mc,
            "most_complex":       mc_func,
            "high_risk_count":    risks.get("HIGH",0)+risks.get("CRITICAL",0),
        }
