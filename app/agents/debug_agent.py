"""
Debug Agent — "error kyun aa raha", "yeh kyun fail ho raha"
Root cause trace karo Neo4j se — deep analysis.
"""
from typing import Dict
from .base_agent import BaseAgent


class DebugAgent(BaseAgent):

    SYSTEM_PROMPT = """
Tu ek expert senior software engineer aur debugger hai.
Tumhare paas ek codebase ka knowledge graph hai jisme
files, functions, classes aur unke connections hain.

User ne ek file ya function debug karne ko kaha hai.
Neeche graph data hai — isse deeply analyze karo.

RESPONSE FORMAT — yeh sab sections ZAROOR do, detail mein:

## 1. File/Function Overview
- File path kya hai
- Kitne functions hain, kitni classes
- Risk level kyun hai (CRITICAL/HIGH/MEDIUM/LOW)
- Yeh file overall system mein kya role play karti hai

## 2. Dependency Analysis
- Yeh file/function kise depend karti hai (calls kya karta hai)
- Kaun is file/function pe depend karta hai (callers)
- Dependency chain kitni deep hai

## 3. Problems Found
- Har problem clearly explain karo
- Problem kyun hai — root cause
- Specific function ya line mention karo agar available ho
- Risk level ke hisaab se problems rank karo

## 4. Blast Radius
- Agar yeh file change ho ya tod jaaye — kya kya toot sakta hai
- Kitni files affected hongi
- Kaun se critical paths break honge

## 5. Fix Recommendations  
- Har problem ka specific fix batao
- Priority order mein likho (pehle kya fix karo)
- Code restructuring suggestions agar zaroorat ho
- Testing recommendations

## 6. Summary
- Ek paragraph mein overall assessment
- Severity: CRITICAL / HIGH / MEDIUM / LOW

RULES:
- Kabhi sirf ek line mein mat chhodna
- Agar graph mein data kam hai — file ke naam se purpose samjho aur relevant advice do
- Risk level CRITICAL/HIGH ho toh extra detail do
- Same file mein function define aur use hona NORMAL hai — circular dependency mat bolna
- circular_deps list empty ho toh "No circular dependencies" likho
- Hamesha actionable recommendations do
- Risk levels: CRITICAL > HIGH > MEDIUM > LOW — inhe exactly as-is use karo, rename mat karo
- Test files (test_*.py, *_test.py, conftest.py) ko CRITICAL mat bolna — yeh normal test code hai
- CRITICAL sirf tab hota hai jab production code file pe 30+ nodes depend karti hon
- Test files mein zyada functions hona GOOD sign hai — extensive test coverage
"""

    def run(self, user_message: str, target: str = None,
            model: str = None) -> Dict:
        if not target:
            target = self._find_target(user_message)

        if not target:
            return {
                "answer": "Kaunsi file ya function debug karni hai? "
                          "File path ya function naam mention karo.",
                "agent": "debug",
            }

        graph_data = self._collect_debug_data(target)

        answer = self.ask_llm(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_message,
            graph_context=graph_data,
            model=model,
        )

        return {
            "answer":     answer,
            "target":     target,
            "graph_data": graph_data,
            "agent":      "debug",
        }

    def _find_target(self, message: str) -> str:
        import re

        # Priority 1 — full file path with extension
        file_match = re.search(
            r'[\w/\\]+\.(py|js|ts|java|go|jsx|tsx)', message
        )
        if file_match:
            return file_match.group(0)

        # Priority 2 — agent/module name (build_agent, debug_agent etc)
        agent_match = re.search(
            r'\b(\w+_agent|\w+_store|\w+_router|\w+_service|\w+_manager)\b',
            message, re.IGNORECASE
        )
        if agent_match:
            return agent_match.group(1)

        # Priority 3 — meaningful words (stop words hata ke)
        stop = {"koi","bug","hay","hai","mein","kya","check","karo",
                "dekho","is","the","a","an","in","find","show","any",
                "there","file","function","code","error","issue","problem"}
        words = [w.lower() for w in message.split()
                 if w.lower() not in stop and len(w) > 3]

        if words:
            return words[0]

        return ""

    def _collect_debug_data(self, target: str) -> Dict:
        """Neo4j se deep debug data nikalo."""

        # ── 1. Target node dhundho ────────────────────────────────────
        # Pehle exact match try karo
        node = self.query_one("""
            MATCH (n:CodeNode {repo_id:$r})
            WHERE n.file_path ENDS WITH $t
               OR n.file_path ENDS WITH ($t + '.py')
               OR n.file_path ENDS WITH ($t + '.js')
               OR n.file_path ENDS WITH ('\\' + $t + '.py')
               OR n.file_path ENDS WITH ('/' + $t + '.py')
               OR n.name = $t
               OR toLower(n.name) = toLower($t)
            RETURN n.node_id   AS id,
                   n.name      AS name,
                   n.node_type AS type,
                   n.file_path AS file,
                   n.line_no   AS line
            ORDER BY
              CASE n.node_type
                WHEN 'file'     THEN 1
                WHEN 'class'    THEN 2
                WHEN 'function' THEN 3
                ELSE 4
              END
            LIMIT 1
        """, t=target)

        # Exact match nahi mila toh CONTAINS try karo
        if not node:
            node = self.query_one("""
                MATCH (n:CodeNode {repo_id:$r})
                WHERE n.name CONTAINS $t
                   OR n.file_path CONTAINS $t
                RETURN n.node_id   AS id,
                       n.name      AS name,
                       n.node_type AS type,
                       n.file_path AS file,
                       n.line_no   AS line
                ORDER BY
                  CASE n.node_type
                    WHEN 'file'     THEN 1
                    WHEN 'class'    THEN 2
                    WHEN 'function' THEN 3
                    ELSE 4
                  END
                LIMIT 1
            """, t=target)

        if not node:
            return {"error": f"'{target}' graph mein nahi mila"}

        node_id   = node["id"]
        file_path = node["file"]

        # ── 2. Is file ke SAARE functions ────────────────────────────
        all_functions = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
            WHERE f.file_path = $fp
            OPTIONAL MATCH ()-[:DEPENDS_ON]->(f)
            WITH f, count(*) AS dependents
            RETURN f.name    AS name,
                   f.line_no AS line,
                   dependents
            ORDER BY dependents DESC
            LIMIT 30
        """, fp=file_path)

        # ── 3. Is file ke SAARE classes ──────────────────────────────
        all_classes = self.query("""
            MATCH (c:CodeNode {repo_id:$r, node_type:'class'})
            WHERE c.file_path = $fp
            RETURN c.name AS name, c.line_no AS line
            LIMIT 10
        """, fp=file_path)

        # ── 4. External callers — dusri files jo ise use karti hain ──
        external_callers = self.query("""
            MATCH (caller:CodeNode {repo_id:$r})
                  -[:DEPENDS_ON]->(n:CodeNode {node_id:$nid})
            WHERE caller.file_path <> $fp
            RETURN caller.name      AS name,
                   caller.file_path AS file,
                   caller.node_type AS type,
                   caller.line_no   AS line
            LIMIT 15
        """, nid=node_id, fp=file_path)

        # ── 5. Is node ki dependencies (kise call karta hai) ─────────
        dependencies = self.query("""
            MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
                  -[:DEPENDS_ON]->(dep:CodeNode {repo_id:$r})
            WHERE dep.file_path <> $fp
            RETURN dep.name      AS name,
                   dep.file_path AS file,
                   dep.node_type AS type
            LIMIT 15
        """, nid=node_id, fp=file_path)

        # ── 6. Blast radius — kitni files affected hongi ─────────────
        blast = self.query_one("""
            MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
            OPTIONAL MATCH (affected:CodeNode {repo_id:$r})
                           -[:DEPENDS_ON*1..3]->(n)
            WHERE affected.file_path <> $fp
            RETURN count(DISTINCT affected.file_path) AS affected_files,
                   count(DISTINCT affected)           AS affected_nodes
        """, nid=node_id, fp=file_path)

        # ── 7. Most depended-upon functions in this file ──────────────
        hotspot_funcs = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
            WHERE f.file_path = $fp
            MATCH (caller:CodeNode {repo_id:$r})
                  -[:DEPENDS_ON]->(f)
            WHERE caller.file_path <> $fp
            WITH f, count(DISTINCT caller) AS external_callers
            WHERE external_callers > 0
            RETURN f.name    AS name,
                   f.line_no AS line,
                   external_callers
            ORDER BY external_callers DESC
            LIMIT 10
        """, fp=file_path)

        # ── 8. Circular dependencies ──────────────────────────────────
        circular = self.query("""
            MATCH path = (n:CodeNode {node_id:$nid, repo_id:$r})
                         -[:DEPENDS_ON*2..5]->(n)
            WITH [nd IN nodes(path) | nd.name] AS cycle
            WHERE size(cycle) > 1
            RETURN cycle
            LIMIT 5
        """, nid=node_id)

        # ── 9. File risk level ────────────────────────────────────────
        file_node = self.query_one("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
            WHERE f.file_path = $fp
            OPTIONAL MATCH ()-[:DEPENDS_ON]->(f)
            WITH f, count(*) AS total_deps
            RETURN f.name      AS name,
                   total_deps  AS total_dependents,
                   CASE
                     WHEN total_deps > 30 THEN 'CRITICAL'
                     WHEN total_deps > 10 THEN 'HIGH'
                     WHEN total_deps > 3  THEN 'MEDIUM'
                     ELSE 'LOW'
                   END AS risk_level
        """, fp=file_path)

        # ── 10. Similar risky files in same module ────────────────────
        module_path = "/".join(file_path.replace("\\", "/").split("/")[:-1])
        similar_risky = self.query("""
            MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
            WHERE f.file_path CONTAINS $module
              AND f.file_path <> $fp
            OPTIONAL MATCH ()-[:DEPENDS_ON]->(f)
            WITH f, count(*) AS deps
            WHERE deps > 5
            RETURN f.file_path AS file, deps
            ORDER BY deps DESC
            LIMIT 5
        """, module=module_path, fp=file_path)

        return {
            "target":             target,
            "node":               node,
            "file_path":          file_path,
            "file_risk":          file_node or {},
            "total_functions":    len(all_functions),
            "all_functions":      all_functions,
            "all_classes":        all_classes,
            "external_callers":   external_callers,
            "dependencies":       dependencies,
            "hotspot_functions":  hotspot_funcs,
            "blast_radius": {
                "affected_files": blast["affected_files"] if blast else 0,
                "affected_nodes": blast["affected_nodes"] if blast else 0,
            },
            "circular_deps":      [c["cycle"] for c in circular],
            "has_circular_deps":  len(circular) > 0,
            "similar_risky_files_in_module": similar_risky,
            "analysis_note": (
                "Same-file function calls are NORMAL patterns. "
                "Focus on external dependencies and high dependent counts."
            ),
        }