"""
Markar Intelligence — Orchestrator v2
Two changes from v1:
  1. GraphAnalyzer now gets repo_path
  2. get_rich_analysis() method added
"""

from typing import Dict, List, Optional
from enum import Enum

from .parser import RepositoryParser
from .graph import DependencyGraphBuilder,  GraphAnalyzer, GraphStore, Neo4jStore
from app.agents.impact_agent import ImpactAnalysisAgent


class QueryType(str, Enum):
    IMPACT_ANALYSIS     = "impact_analysis"
    DEPENDENCY_ANALYSIS = "dependency_analysis"
    ROOT_CAUSE          = "root_cause"
    REFACTORING         = "refactoring"
    API_MIGRATION       = "api_migration"
    MULTI_CHANGE        = "multi_change"


class CodeIntelligenceOrchestrator:

    def __init__(self, repo_path: str, graph_storage_path: str = None, repo_id: str = None):
        self.repo_path   = repo_path
        # Bug fix: graph storage hamesha repo ke andar hogi, relative path nahi
        import os
        storage = graph_storage_path or os.path.join(repo_path, ".code_graph")
        if os.getenv("NEO4J_URI") and repo_id:
            self.store = Neo4jStore(repo_id=repo_id, storage_path=storage)
            print(f"  [Orchestrator] Neo4j store (repo: {repo_id})")
        else:
            self.store = GraphStore(storage)
            print(f"  [Orchestrator] Local GraphStore")

        self.agent       = ImpactAnalysisAgent(self.store)
        self.initialized = False
        self._analyzer: Optional[GraphAnalyzer] = None        

    def initialize(self) -> Dict:
        print(f"Initializing Markar Intelligence for: {self.repo_path}")

        # ── Step 1: Python files via existing ast parser (fast, deep) ──────
        parser = RepositoryParser(self.repo_path)
        parser.parse()
        print(f"  Parsed {len(parser.files)} Python files (ast)")

        # ── Step 2: All other languages via UniversalParser (tree-sitter) ──
        try:
            from .parser.universal_parser import UniversalParser
            uni = UniversalParser()
            # Parse every non-python file in repo
            non_py_files = uni.parse_repository(
                self.repo_path,
                languages=[l for l in uni.get_supported_languages() if l != "python"],
            )
            # Merge into parser.files so DependencyGraphBuilder sees everything
            for rel_path, parsed_file in non_py_files.items():
                if rel_path not in parser.files:
                    parser.files[rel_path] = parsed_file.to_file_info()
            print(f"  Parsed {len(non_py_files)} non-Python files (tree-sitter)")
        except Exception as e:
            print(f"  [UniversalParser] skipped: {e}")

        print(f"  Total files in graph: {len(parser.files)}")

        builder = DependencyGraphBuilder(parser)
        nodes   = builder.build()
        print(f"  Built graph with {len(nodes)} nodes")

        self.store.save(nodes)
        print("  Graph stored")

        # ← CHANGE 1: pass repo_path so analyzer can read file sizes
        self._analyzer = GraphAnalyzer(nodes, repo_path=self.repo_path)
        self.initialized = True

        return {
            "status": "initialized",
            "files":  len(parser.files),
            "nodes":  len(nodes),
            "stats":  self.store.get_stats(),
        }

    # ← CHANGE 2: new method — this is what /status now calls
    def get_rich_analysis(self) -> Dict:
        """File sizes, danger imports, state issues, hotspots, issues_summary."""
        if not self.initialized or not self._analyzer:
            return {"error": "Not initialized"}
        return self._analyzer.rich_analysis()

    def query(self, query_type: QueryType, **kwargs) -> Dict:
        if not self.initialized:
            return {"error": "System not initialized. Call initialize() first."}
        try:
            if query_type == QueryType.IMPACT_ANALYSIS:
                return self._handle_impact_analysis(kwargs)
            elif query_type == QueryType.DEPENDENCY_ANALYSIS:
                return self._handle_dependency_analysis(kwargs)
            elif query_type == QueryType.ROOT_CAUSE:
                return self._handle_root_cause(kwargs)
            elif query_type == QueryType.REFACTORING:
                return self._handle_refactoring(kwargs)
            elif query_type == QueryType.API_MIGRATION:
                return self._handle_api_migration(kwargs)
            elif query_type == QueryType.MULTI_CHANGE:
                return self._handle_multi_change(kwargs)
            else:
                return {"error": f"Unknown query type: {query_type}"}
        except Exception as e:
            return {"error": str(e), "query_type": query_type.value}

    def _handle_impact_analysis(self, kwargs):
        target = kwargs.get("target")
        if not target:
            return {"error": "Missing target"}
        target_id = self._normalize_target(target)
        if target_id not in self.store.nodes:
            return {"error": f"Target not found: {target}"}
        impact = self.agent.analyze_function_change(target_id)
        return {
            "query_type": "impact_analysis", "target": target_id,
            "severity": impact.severity.value, "risk_level": impact.risk_level,
            "affected_count": len(impact.affected_nodes),
            "affected_files": list(impact.affected_files),
            "affected_functions": list(impact.affected_functions),
            "affected_classes": list(impact.affected_classes),
            "recommendations": impact.recommendations,
            "migration_plan": impact.migration_plan,
        }

    def _handle_dependency_analysis(self, kwargs):
        target = kwargs.get("target")
        if not target:
            return {"error": "Missing target"}
        target_id = self._normalize_target(target)
        if target_id not in self.store.nodes:
            return {"error": f"Target not found: {target}"}
        deps = self.store.query_dependencies(target_id)
        return {"query_type": "dependency_analysis", "target": target_id,
                "direct_dependencies": deps.get("direct_deps", []),
                "all_dependencies": deps.get("all_deps", []),
                "dependency_count": deps.get("dependency_count", 0)}

    def _handle_root_cause(self, kwargs):
        failing_node = kwargs.get("failing_node")
        if not failing_node:
            return {"error": "Missing failing_node"}
        node_id = self._normalize_target(failing_node)
        if node_id not in self.store.nodes:
            return {"error": f"Node not found: {failing_node}"}
        return self.agent.find_root_cause(node_id)

    def _handle_refactoring(self, kwargs):
        target = kwargs.get("target")
        if not target:
            return {"error": "Missing target"}
        target_id = self._normalize_target(target)
        if target_id not in self.store.nodes:
            return {"error": f"Target not found: {target}"}
        return self.agent.suggest_refactoring(target_id)

    def _handle_api_migration(self, kwargs):
        target      = kwargs.get("target")
        description = kwargs.get("description", "API change")
        if not target:
            return {"error": "Missing target"}
        target_id = self._normalize_target(target)
        if target_id not in self.store.nodes:
            return {"error": f"Target not found: {target}"}
        return self.agent.plan_api_change(target_id, description)

    def _handle_multi_change(self, kwargs):
        changes = kwargs.get("changes", [])
        if not changes:
            return {"error": "Missing changes"}
        normalized = [self._normalize_target(c) for c in changes]
        missing    = [c for c in normalized if c not in self.store.nodes]
        if missing:
            return {"error": f"Targets not found: {missing}"}
        return self.agent.analyze_multiple_changes(normalized)

    def search(self, query, node_type=None):
        return self.store.search_nodes(query, node_type)

    def get_file_structure(self, file_path):
        return self.store.get_file_structure(file_path)

    def get_stats(self):
        return self.store.get_stats()

    def export_visualization(self):
        return self.store.export_for_visualization()

    def _normalize_target(self, target: str) -> str:
        if target.startswith(("file:", "class:", "func:")):
            return target
        results = self.store.search_nodes(target)
        if results:
            return results[0]["id"]
        file_id = f"file:{target}"
        if file_id in self.store.nodes:
            return file_id
        for node in self.store.nodes.values():
            if node.name == target or node.name.endswith(f".{target}"):
                return node.id
        return target


class WorkflowExecutor:
    def __init__(self, orchestrator: CodeIntelligenceOrchestrator):
        self.orchestrator = orchestrator

    def on_code_change(self, changed_files):
        analysis = {"workflow": "on_code_change", "files_changed": changed_files, "impacts": []}
        for file in changed_files:
            impact = self.orchestrator.query(QueryType.IMPACT_ANALYSIS, target=file)
            analysis["impacts"].append(impact)
        max_sev = max(
            (i.get("severity", "low") for i in analysis["impacts"]),
            key=lambda x: ["isolated","low","medium","high","critical"].index(x),
            default="low",
        )
        analysis["consolidated_severity"] = max_sev
        return analysis

    def on_deployment(self, version):
        stats = self.orchestrator.get_stats()
        circular_deps = self.orchestrator.store.query_circular_deps()
        return {
            "workflow": "pre_deployment_check", "version": version,
            "system_healthy": len(circular_deps) == 0,
            "circular_deps": circular_deps or "None found",
            "total_nodes": stats.get("total_nodes"),
            "recommendations": (
                ["Run full test suite", "No circular deps", "Safe to deploy"]
                if not circular_deps
                else ["Fix circular dependencies before deployment"]
            ),
        }

    def on_code_review(self, pr_description, changed_files):
        analysis = {"workflow": "code_review", "pr_description": pr_description, "review_points": []}
        for file in changed_files:
            impact = self.orchestrator.query(QueryType.IMPACT_ANALYSIS, target=file)
            focus = []
            if impact.get("severity") in ["high", "critical"]:
                focus.append("High blast radius — review all affected files")
            if impact.get("affected_count", 0) > 10:
                focus.append("Request tests for affected functions")
            analysis["review_points"].append({
                "file": file, "severity": impact.get("severity"),
                "affected_count": impact.get("affected_count"),
                "review_focus": focus or ["Standard review sufficient"],
            })
        return analysis