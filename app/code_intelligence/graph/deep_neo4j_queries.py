"""
Deep Neo4j Queries — Agent ke liye rich context queries
========================================================
Sab agents yeh class use karte hain deep AST data nikalne ke liye.
BaseAgent.query() ke upar bana hai — seedha Neo4j se.

Usage:
    dq  = DeepGraphQueries(self.store, self.repo_id)
    ctx = dq.function_deep_context("login", "app/routes/auth.py")
    # ctx → string — seedha LLM prompt mein inject karo
"""

from typing import Dict, List, Optional


class DeepGraphQueries:

    def __init__(self, store, repo_id: str):
        self.store   = store
        self.repo_id = repo_id

    def _run(self, cypher: str, **params) -> List[Dict]:
        try:
            driver = self.store._connect()
            with driver.session() as s:
                result = s.run(cypher, r=self.repo_id, **params)
                return [dict(row) for row in result]
        except Exception as e:
            print(f"[DeepQuery] failed: {e}")
            return []

    # ── 1. Ek function ka complete deep context ───────────────────────────────

    def function_deep_context(self, func_name: str, file_path: str = None) -> str:
        """
        Ek function ka poora deep context — string format mein.
        LLM prompt mein directly inject karo.
        """
        if file_path:
            rows = self._run("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function',
                                   name:$fn, file_path:$fp})
                RETURN n LIMIT 1
            """, fn=func_name, fp=file_path)
        else:
            rows = self._run("""
                MATCH (n:CodeNode {repo_id:$r, node_type:'function', name:$fn})
                RETURN n LIMIT 1
            """, fn=func_name)

        if not rows:
            return f"Function `{func_name}` graph mein nahi mila."

        node = dict(rows[0]["n"])
        lines = [f"=== Deep Analysis: `{func_name}` ==="]

        risk    = node.get("deep_risk_level", "UNKNOWN")
        reasons = node.get("deep_risk_reasons", "")
        lang    = node.get("deep_language", "?")
        lines.append(f"Language: {lang} | Risk: {risk}" +
                     (f" — {reasons}" if reasons else ""))

        c = node.get("deep_complexity","?")
        d = node.get("deep_max_depth","?")
        l = node.get("deep_logic_lines","?")
        t = node.get("deep_total_lines","?")
        lines.append(f"Complexity: {c} | Nesting depth: {d} | Logic lines: {l}/{t}")

        if node.get("deep_is_async"):
            lines.append(f"Async function {'(uses await)' if node.get('deep_has_await') else ''}")

        bp = node.get("deep_branch_paths","")
        if bp:
            lines.append("Branches:")
            for part in bp.split(";")[:8]:
                lines.append(f"  {part}")

        raises = node.get("deep_raises","")
        prop   = node.get("deep_can_propagate","")
        te     = node.get("deep_has_try_except", False)
        if raises: lines.append(f"Raises/throws: {raises}")
        if prop:   lines.append(f"Can propagate from callees: {prop}")
        if te:     lines.append("Has try/except/catch block")

        ret  = node.get("deep_data_returns","")
        rtyp = node.get("deep_return_type","")
        if ret:                       lines.append(f"Returns: {ret}")
        if rtyp:                      lines.append(f"Return type annotation: {rtyp}")
        if node.get("deep_can_return_none"): lines.append("WARNING: Can return None")

        inp = node.get("deep_data_inputs","")
        if inp: lines.append(f"Parameters: {inp}")

        loops = node.get("deep_loop_count", 0)
        if loops: lines.append(f"Loops: {loops}")
        # ← YAHAN ADD KARO:
        source = node.get("deep_source_code", "")
        if source:
            lines.append(f"\nSource Code:\n{source}")

        return "\n".join(lines)

    # ── 2. File ka saara functions deep summary ───────────────────────────────

    def file_deep_summary(self, file_path: str) -> str:
        rows = self._run("""
            MATCH (n:CodeNode {repo_id:$r, node_type:'function', file_path:$fp})
            RETURN n.name              AS name,
                   n.deep_risk_level  AS risk,
                   n.deep_complexity  AS complexity,
                   n.deep_raises      AS raises,
                   n.deep_branch_count AS branches,
                   n.deep_language    AS lang,
                   n.line_no          AS line
            ORDER BY
                CASE n.deep_risk_level
                    WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM'   THEN 2 ELSE 3 END,
                n.deep_complexity DESC
        """, fp=file_path)

        if not rows:
            return f"File `{file_path}` ka deep analysis nahi mila."

        lines = [f"=== Deep File Summary: `{file_path}` ==="]
        for r in rows:
            risk     = r.get("risk") or "?"
            comp     = r.get("complexity") or "?"
            name     = r.get("name","?")
            ln       = r.get("line","?")
            raises   = r.get("raises") or ""
            branches = r.get("branches") or 0
            lang     = r.get("lang") or "?"
            line = (f"  [{risk}] {name} (line {ln}) [{lang}] "
                    f"| complexity={comp} | branches={branches}")
            if raises: line += f" | raises: {raises}"
            lines.append(line)

        return "\n".join(lines)

    # ── 3. Repo hotspots ──────────────────────────────────────────────────────

    def repo_hotspots(self, top: int = 10) -> str:
        """HIGH + CRITICAL risk functions — dashboard ke liye."""
        rows = self._run("""
            MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
            WHERE n.deep_risk_level IN ['HIGH','CRITICAL']
            RETURN n.name             AS name,
                   n.file_path        AS file,
                   n.line_no          AS line,
                   n.deep_risk_level  AS risk,
                   n.deep_complexity  AS complexity,
                   n.deep_risk_reasons AS reasons,
                   n.deep_language    AS lang
            ORDER BY
                CASE n.deep_risk_level WHEN 'CRITICAL' THEN 0 ELSE 1 END,
                n.deep_complexity DESC
            LIMIT $top
        """, top=top)

        if not rows:
            return "Koi HIGH/CRITICAL risk function nahi — codebase healthy hai!"

        lines = [f"=== Top {top} Risk Hotspots (Across All Languages) ==="]
        for i, r in enumerate(rows, 1):
            lines.append(
                f"{i}. [{r.get('risk')}] {r.get('file')}:{r.get('name')} "
                f"(line {r.get('line')}) [{r.get('lang')}] "
                f"| complexity={r.get('complexity')} | {r.get('reasons','')}"
            )
        return "\n".join(lines)

    # ── 4. Exception chain ────────────────────────────────────────────────────

    def exception_chain(self, func_name: str) -> str:
        rows = self._run("""
            MATCH (fn:CodeNode {repo_id:$r, node_type:'function', name:$fn})
            OPTIONAL MATCH (fn)-[r1:RAISES]->(ex1:ExceptionNode {repo_id:$r})
            OPTIONAL MATCH (fn)-[r2:CAN_PROPAGATE]->(ex2:ExceptionNode {repo_id:$r})
            RETURN
                collect(DISTINCT {exc:ex1.exc_type, caught:r1.is_caught, line:r1.line_no})
                    AS direct,
                collect(DISTINCT {exc:ex2.exc_type, callee:r2.callee, line:r2.line_no})
                    AS propagated
        """, fn=func_name)

        if not rows:
            return f"`{func_name}` ka exception data nahi mila."

        row        = rows[0]
        lines      = [f"=== Exception Chain: `{func_name}` ==="]
        direct     = [d for d in (row.get("direct")     or []) if d.get("exc")]
        propagated = [p for p in (row.get("propagated") or []) if p.get("exc")]

        if direct:
            lines.append("Direct raises/throws:")
            for d in direct:
                caught = " (caught)" if d.get("caught") else " (UNCAUGHT ⚠)"
                lines.append(f"  {d['exc']}{caught} @ line {d.get('line','?')}")
        else:
            lines.append("No direct raises")

        if propagated:
            lines.append("Propagated via callees:")
            for p in propagated:
                lines.append(f"  {p['exc']} from `{p.get('callee','?')}` @ line {p.get('line','?')}")

        return "\n".join(lines)

    # ── 5. Impact + deep context combined ─────────────────────────────────────

    def impact_with_deep_context(self, func_name: str, file_path: str = None) -> str:
        """Impact Agent ke liye — blast radius + deep analysis + exception chain."""
        if file_path:
            dep_rows = self._run("""
                MATCH (fn:CodeNode {repo_id:$r, node_type:'function',
                                    name:$fn, file_path:$fp})
                      <-[:DEPENDS_ON]-(caller:CodeNode {repo_id:$r})
                RETURN caller.name          AS caller_name,
                       caller.file_path      AS caller_file,
                       caller.deep_risk_level AS caller_risk
                LIMIT 20
            """, fn=func_name, fp=file_path)
        else:
            dep_rows = self._run("""
                MATCH (fn:CodeNode {repo_id:$r, node_type:'function', name:$fn})
                      <-[:DEPENDS_ON]-(caller:CodeNode {repo_id:$r})
                RETURN caller.name          AS caller_name,
                       caller.file_path      AS caller_file,
                       caller.deep_risk_level AS caller_risk
                LIMIT 20
            """, fn=func_name)

        parts = [self.function_deep_context(func_name, file_path), ""]

        if dep_rows:
            parts.append(f"=== Callers ({len(dep_rows)}) ===")
            for r in dep_rows[:10]:
                risk = r.get("caller_risk") or "?"
                parts.append(f"  [{risk}] {r.get('caller_file')}:{r.get('caller_name')}")
        else:
            parts.append("=== No callers found ===")

        parts.append("")
        parts.append(self.exception_chain(func_name))
        return "\n".join(parts)

    # ── 6. Branch detail ──────────────────────────────────────────────────────

    def function_branches(self, func_name: str, file_path: str = None) -> str:
        """Ek function ke saare branches detail mein — Debug Agent ke liye."""
        if file_path:
            rows = self._run("""
                MATCH (fn:CodeNode {repo_id:$r, node_type:'function',
                                    name:$fn, file_path:$fp})
                      -[:HAS_BRANCH]->(b:BranchNode {repo_id:$r})
                RETURN b.branch_type  AS btype,
                       b.condition    AS cond,
                       b.line_no      AS line,
                       b.leads_return AS ret,
                       b.leads_raise  AS raise,
                       b.raises_type  AS rtype
                ORDER BY b.line_no
            """, fn=func_name, fp=file_path)
        else:
            rows = self._run("""
                MATCH (fn:CodeNode {repo_id:$r, node_type:'function', name:$fn})
                      -[:HAS_BRANCH]->(b:BranchNode {repo_id:$r})
                RETURN b.branch_type  AS btype,
                       b.condition    AS cond,
                       b.line_no      AS line,
                       b.leads_return AS ret,
                       b.leads_raise  AS raise,
                       b.raises_type  AS rtype
                ORDER BY b.line_no
            """, fn=func_name)

        if not rows:
            return f"`{func_name}` ke branches Neo4j mein nahi mile."

        lines = [f"=== Branches: `{func_name}` ({len(rows)} total) ==="]
        for r in rows:
            arrow = ""
            if r.get("raise"):  arrow = f" → raises {r.get('rtype') or 'Exception'}"
            elif r.get("ret"):  arrow = " → returns"
            lines.append(
                f"  [{r.get('btype')} @ line {r.get('line')}] "
                f"`{(r.get('cond') or '')[:60]}`{arrow}"
            )
        return "\n".join(lines)

    # ── 7. Complexity report ──────────────────────────────────────────────────

    def complexity_report(self) -> str:
        """Build + QA agent ke liye — poore repo ka complexity distribution."""
        rows = self._run("""
            MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
            WHERE n.deep_complexity IS NOT NULL
            RETURN
                count(n)                                                         AS total,
                avg(n.deep_complexity)                                           AS avg_c,
                max(n.deep_complexity)                                           AS max_c,
                sum(CASE WHEN n.deep_complexity >= 15 THEN 1 ELSE 0 END)        AS very_high,
                sum(CASE WHEN n.deep_complexity >= 8
                          AND n.deep_complexity < 15 THEN 1 ELSE 0 END)         AS high,
                sum(CASE WHEN n.deep_complexity >= 4
                          AND n.deep_complexity < 8  THEN 1 ELSE 0 END)         AS medium,
                sum(CASE WHEN n.deep_complexity < 4 THEN 1 ELSE 0 END)          AS low
        """)

        if not rows: return "Complexity data nahi mila — pehle repo index karo."
        r = rows[0]
        return (
            f"=== Complexity Report ===\n"
            f"Total functions: {r.get('total',0)}\n"
            f"Average complexity: {round(r.get('avg_c') or 0, 2)}\n"
            f"Max complexity:     {r.get('max_c',0)}\n"
            f"Distribution:\n"
            f"  Very high (>=15): {r.get('very_high',0)}\n"
            f"  High      (8-14): {r.get('high',0)}\n"
            f"  Medium    (4-7):  {r.get('medium',0)}\n"
            f"  Low       (<4):   {r.get('low',0)}"
        )

    # ── 8. Language breakdown ─────────────────────────────────────────────────

    def language_risk_breakdown(self) -> str:
        """Language-wise risk distribution — dashboard ke liye."""
        rows = self._run("""
            MATCH (n:CodeNode {repo_id:$r, node_type:'function'})
            WHERE n.deep_language IS NOT NULL
            RETURN n.deep_language  AS lang,
                   count(n)         AS total,
                   sum(CASE WHEN n.deep_risk_level IN ['HIGH','CRITICAL'] THEN 1 ELSE 0 END)
                                    AS high_risk,
                   avg(n.deep_complexity) AS avg_c
            ORDER BY total DESC
        """)

        if not rows: return "Language data nahi mila."
        lines = ["=== Language Risk Breakdown ==="]
        for r in rows:
            lines.append(
                f"  {r.get('lang','?'):<15} "
                f"functions={r.get('total',0):<6} "
                f"high_risk={r.get('high_risk',0):<5} "
                f"avg_complexity={round(r.get('avg_c') or 0, 1)}"
            )
        return "\n".join(lines)
