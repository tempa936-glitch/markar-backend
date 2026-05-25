"""
Deep Graph Builder — Neo4j mein deep AST data store karna
==========================================================
Existing Neo4j store ke saath kaam karta hai.
Function nodes pe deep_* properties ADD karta hai — DELETE nahi.

Naaye Neo4j relationships:
  HAS_BRANCH    → function → BranchNode
  RAISES        → function → ExceptionNode  (direct raise/throw)
  CAN_PROPAGATE → function → ExceptionNode  (via callee)

Orchestrator mein integrate karna:
    from app.code_intelligence.graph.deep_graph_builder import DeepGraphBuilder
    deep = DeepGraphBuilder(self.store, self.repo_path)
    deep.run()
"""

from typing import Dict, Optional
from app.code_intelligence.parser.deep_ast_analyzer import (
    DeepFunctionAnalysis,
    DeepRepositoryAnalyzer,
)

BATCH = 2000


class DeepGraphBuilder:

    def __init__(self, neo4j_store, repo_path: str):
        self.store     = neo4j_store
        self.repo_id   = neo4j_store.repo_id
        self.repo_path = repo_path

    def run(self) -> Dict:
        """Full pipeline — analyze karo, Neo4j update karo, summary return karo."""
        print(f"[DeepGraph] Deep AST analysis starting — repo: {self.repo_id}")

        analyzer    = DeepRepositoryAnalyzer(self.repo_path)
        all_results = analyzer.analyze_all()

        if not all_results:
            print("[DeepGraph] No files analyzed")
            return {"status": "no_data"}

        enriched = self._enrich_function_nodes(all_results)
        self._create_indexes()
        self._create_branch_nodes(all_results)
        self._create_exception_relationships(all_results)

        summary = analyzer.summary(all_results)
        summary["enriched_functions"] = enriched
        print(f"[DeepGraph] Done — {enriched} functions enriched in Neo4j")
        return summary

    # ── Step 1: Existing function nodes pe deep_* properties SET karo ────────

    def _enrich_function_nodes(
        self,
        all_results: Dict[str, Dict[str, DeepFunctionAnalysis]],
    ) -> int:
        driver   = self.store._connect()
        enriched = 0
        updates  = []

        for file_path, funcs in all_results.items():
            for func_name, analysis in funcs.items():
                updates.append({
                    "file_path": file_path,
                    "func_name": func_name,
                    "props":     analysis.to_neo4j_properties(),
                })

        with driver.session() as s:
            for i in range(0, len(updates), BATCH):
                batch = updates[i : i + BATCH]
                s.run("""
                    UNWIND $batch AS row
                    MATCH (n:CodeNode {
                        repo_id:   $r,
                        node_type: 'function',
                        name:      row.func_name,
                        file_path: row.file_path
                    })
                    SET n += row.props
                """, batch=batch, r=self.repo_id)
                enriched += len(batch)
                print(f"[DeepGraph] Enriched {min(i+BATCH, len(updates))}/{len(updates)}")

        return enriched

    # ── Step 2: Indexes ───────────────────────────────────────────────────────

    def _create_indexes(self):
        driver = self.store._connect()
        with driver.session() as s:
            s.run("CREATE INDEX IF NOT EXISTS FOR (n:CodeNode)   ON (n.deep_risk_level)")
            s.run("CREATE INDEX IF NOT EXISTS FOR (n:CodeNode)   ON (n.deep_complexity)")
            s.run("CREATE INDEX IF NOT EXISTS FOR (n:BranchNode) ON (n.repo_id, n.func_name, n.line_no)")
            s.run("CREATE INDEX IF NOT EXISTS FOR (n:ExceptionNode) ON (n.repo_id, n.exc_type)")

    # ── Step 3: BranchNode create + HAS_BRANCH relationship ──────────────────

    def _create_branch_nodes(
        self,
        all_results: Dict[str, Dict[str, DeepFunctionAnalysis]],
    ):
        driver      = self.store._connect()
        branch_data = []

        for file_path, funcs in all_results.items():
            for func_name, analysis in funcs.items():
                for b in analysis.branches:
                    branch_data.append({
                        "func_name":    func_name,
                        "file_path":    file_path,
                        "branch_type":  b.branch_type,
                        "condition":    b.condition[:200],
                        "line_no":      b.line_no,
                        "leads_return": b.leads_to_return,
                        "leads_raise":  b.leads_to_raise,
                        "raises_type":  b.raises_type or "",
                    })

        if not branch_data:
            return

        with driver.session() as s:
            for i in range(0, len(branch_data), BATCH):
                batch = branch_data[i : i + BATCH]
                s.run("""
                    UNWIND $batch AS row
                    MATCH (fn:CodeNode {
                        repo_id:   $r,
                        node_type: 'function',
                        name:      row.func_name,
                        file_path: row.file_path
                    })
                    MERGE (b:BranchNode {
                        repo_id:   $r,
                        func_name: row.func_name,
                        file_path: row.file_path,
                        line_no:   row.line_no
                    })
                    SET b.branch_type  = row.branch_type,
                        b.condition    = row.condition,
                        b.leads_return = row.leads_return,
                        b.leads_raise  = row.leads_raise,
                        b.raises_type  = row.raises_type
                    MERGE (fn)-[:HAS_BRANCH]->(b)
                """, batch=batch, r=self.repo_id)

        print(f"[DeepGraph] {len(branch_data)} BranchNodes created")

    # ── Step 4: ExceptionNode + RAISES / CAN_PROPAGATE relationships ─────────

    def _create_exception_relationships(
        self,
        all_results: Dict[str, Dict[str, DeepFunctionAnalysis]],
    ):
        driver         = self.store._connect()
        raises_data    = []
        propagate_data = []

        for file_path, funcs in all_results.items():
            for func_name, analysis in funcs.items():
                for ep in analysis.exception_paths:
                    if ep.origin in ("raise", "throw", "return_error"):
                        raises_data.append({
                            "func_name": func_name,
                            "file_path": file_path,
                            "exc_type":  ep.exc_type,
                            "line_no":   ep.line_no,
                            "is_caught": ep.is_caught,
                        })
                    elif ep.origin.startswith("propagated_from:"):
                        callee = ep.origin.split(":", 1)[1]
                        propagate_data.append({
                            "func_name": func_name,
                            "file_path": file_path,
                            "exc_type":  ep.exc_type,
                            "callee":    callee,
                            "line_no":   ep.line_no,
                        })

        if raises_data:
            with driver.session() as s:
                for i in range(0, len(raises_data), BATCH):
                    batch = raises_data[i : i + BATCH]
                    s.run("""
                        UNWIND $batch AS row
                        MATCH (fn:CodeNode {
                            repo_id:   $r,
                            node_type: 'function',
                            name:      row.func_name,
                            file_path: row.file_path
                        })
                        MERGE (ex:ExceptionNode {repo_id: $r, exc_type: row.exc_type})
                        MERGE (fn)-[rel:RAISES]->(ex)
                        SET rel.line_no   = row.line_no,
                            rel.is_caught = row.is_caught
                    """, batch=batch, r=self.repo_id)
            print(f"[DeepGraph] {len(raises_data)} RAISES relationships")

        if propagate_data:
            with driver.session() as s:
                for i in range(0, len(propagate_data), BATCH):
                    batch = propagate_data[i : i + BATCH]
                    s.run("""
                        UNWIND $batch AS row
                        MATCH (fn:CodeNode {
                            repo_id:   $r,
                            node_type: 'function',
                            name:      row.func_name,
                            file_path: row.file_path
                        })
                        MERGE (ex:ExceptionNode {repo_id: $r, exc_type: row.exc_type})
                        MERGE (fn)-[rel:CAN_PROPAGATE]->(ex)
                        SET rel.callee  = row.callee,
                            rel.line_no = row.line_no
                    """, batch=batch, r=self.repo_id)
            print(f"[DeepGraph] {len(propagate_data)} CAN_PROPAGATE relationships")
