"""
Markar Intelligence — Deep Graph Analyzer
NOW extracts: file sizes, import danger, state issues,
duplicate systems, circular deps, hotspots.
"""

from __future__ import annotations
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Set, Optional
from .builder import DependencyNode

LARGE_FILE_LINES    = 500
CRITICAL_FILE_LINES = 1000
HIGH_IMPORT_COUNT   = 3


class GraphAnalyzer:

    def __init__(self, nodes: Dict[str, DependencyNode], repo_path: str = "",driver=None, repo_id: str = ""):
        self.nodes     = nodes
        self.repo_path = repo_path   # ← NEW: needed to read file sizes
        self._driver   = driver    # Neo4j driver — queries ke liye
        self._repo_id  = repo_id 

    # ── MAIN: rich_analysis ─────────────────────────────────────────────
    def rich_analysis(self) -> dict:
        file_lines    = self._collect_file_lines()
        import_counts = self._collect_import_counts()
        large_files    = self._find_large_files(file_lines)
        danger_imports = self._find_danger_imports(import_counts)
        state_issues   = self._find_state_issues()
        circular_deps  = self.find_circular_dependencies()
        hotspots       = self._find_hotspots()
        issues         = self._build_issues_summary(
                             large_files, danger_imports, state_issues, circular_deps)
        return {
            "file_sizes":     large_files,
            "danger_imports": danger_imports,
            "state_issues":   state_issues,
            "circular_deps":  circular_deps,
            "hotspots":       hotspots,
            "issues_summary": issues,
        }

    # ── File sizes ───────────────────────────────────────────────────────
    def _collect_file_lines(self) -> dict:
        result = {}
        for node in self.nodes.values():
            if node.type != "file":
                continue
            lines = self._lines_on_disk(node.file_path)
            if lines is not None:
                result[node.file_path] = lines
        return result

    def _lines_on_disk(self, rel_path: str) -> Optional[int]:
        if not self.repo_path:
            return None
        full = Path(self.repo_path) / rel_path
        try:
            with open(full, encoding="utf-8", errors="ignore") as f:
                return sum(1 for _ in f)
        except OSError:
            return None

    def _find_large_files(self, file_lines: dict) -> list:
        result = []
        for path, lines in sorted(file_lines.items(), key=lambda x: -x[1]):
            if lines >= LARGE_FILE_LINES:
                sev = "critical" if lines >= CRITICAL_FILE_LINES else "warning"
                result.append({
                    "file": path, "lines": lines, "severity": sev,
                    "reason": (
                        f"{lines} lines — too large, any change = high risk. Split it."
                        if sev == "critical"
                        else f"{lines} lines — getting large, monitor closely."
                    ),
                })
        return result

    # ── Import danger ────────────────────────────────────────────────────
    def _collect_import_counts(self) -> dict:
        return {node.file_path: len(node.parents)
                for node in self.nodes.values() if node.type == "file"}

    def _find_danger_imports(self, import_counts: dict) -> list:
        result = []
        for path, count in sorted(import_counts.items(), key=lambda x: -x[1]):
            if count >= HIGH_IMPORT_COUNT:
                sev = "critical" if count >= 6 else "high"
                result.append({
                    "file": path, "import_count": count, "severity": sev,
                    "reason": f"Imported in {count} places — if it breaks, everything importing it breaks.",
                })
        return result

    # ── State / auth duplicate detection ────────────────────────────────
    _STATE_PATTERNS = [
        (r"auth",    "auth"),   (r"store",   "state"),
        (r"slice",   "state"),  (r"context", "state"),
        (r"redux",   "state"),  (r"session", "auth"),
        (r"token",   "auth"),   (r"login",   "auth"),
    ]

    def _find_state_issues(self) -> list:
        buckets = defaultdict(list)
        for node in self.nodes.values():
            if node.type != "file":
                continue
            name_lower = node.file_path.lower()
            for pattern, bucket in self._STATE_PATTERNS:
                if re.search(pattern, name_lower):
                    buckets[bucket].append(node.file_path)
                    break
        issues = []
        for concern, files in buckets.items():
            if len(files) >= 2:
                issues.append({
                    "concern": concern, "files": files, "count": len(files),
                    "severity": "high",
                    "reason": (
                        f"{len(files)} files implement '{concern}': "
                        + ", ".join(Path(f).name for f in files)
                        + ". Consolidate to avoid hidden bugs."
                    ),
                })
        return issues

    # ── Circular deps ────────────────────────────────────────────────────
    def find_circular_dependencies(self) -> List[List[str]]:
        if self._driver and self._repo_id:
            try:
                with self._driver.session() as s:
                    rows = s.run("""
                        MATCH path = (a:CodeNode {repo_id:$r})
                              -[:DEPENDS_ON*2..6]->(a)
                        WITH [n IN nodes(path) | n.node_id] AS cycle
                        RETURN DISTINCT cycle
                        LIMIT 20
                    """, r=self._repo_id)
                    return [row["cycle"] for row in rows]
            except Exception as e:
                print(f"[Analyzer] Neo4j circular deps failed: {e}, falling back")

        # Fallback — RAM se
        cycles, visited = [], set()
        for node_id in self.nodes:
            if node_id not in visited:
                c = self._find_cycle(node_id, visited, [])
                if c:
                    cycles.append(c)
        return cycles

    def _find_cycle(self, node_id, visited, path):
        if node_id in path:
            return path[path.index(node_id):] + [node_id]
        if node_id in visited:
            return None
        visited.add(node_id)
        node = self.nodes.get(node_id)
        if not node:
            return None
        for child in node.children:
            if child in self.nodes:
                c = self._find_cycle(child, visited, path + [node_id])
                if c:
                    return c
        return None

    # ── Hotspots ─────────────────────────────────────────────────────────
    def _find_hotspots(self, top: int = 10) -> list:
        scored = [
            {"id": n.id, "name": n.name, "type": n.type, "file": n.file_path,
             "dependents": len(n.parents),
             "severity": self._calculate_impact_level(len(n.parents))}
            for n in self.nodes.values() if len(n.parents) > 0
        ]
        return sorted(scored, key=lambda x: -x["dependents"])[:top]

    # ── Issues summary ────────────────────────────────────────────────────
    def _build_issues_summary(self, large_files, danger_imports,
                               state_issues, circular_deps) -> list:
        issues = []
        for f in large_files:
            issues.append({"priority": 1 if f["severity"] == "critical" else 2,
                "type": "large_file", "severity": f["severity"],
                "title": f"Large file: {Path(f['file']).name}",
                "detail": f["reason"], "file": f["file"]})
        for ci in danger_imports:
            issues.append({"priority": 1 if ci["severity"] == "critical" else 2,
                "type": "dangerous_import", "severity": ci["severity"],
                "title": f"High blast radius: {Path(ci['file']).name}",
                "detail": ci["reason"], "file": ci["file"]})
        for si in state_issues:
            issues.append({"priority": 2, "type": "duplicate_system",
                "severity": "high",
                "title": f"Duplicate {si['concern']} ({si['count']} files)",
                "detail": si["reason"], "file": si["files"][0]})
        for cycle in circular_deps[:5]:
            issues.append({"priority": 1, "type": "circular_dependency",
                "severity": "critical", "title": "Circular dependency",
                "detail": " -> ".join(cycle),
                "file": self.nodes[cycle[0]].file_path if cycle[0] in self.nodes else ""})
        return sorted(issues, key=lambda x: x["priority"])

    # ── Standard methods (unchanged) ─────────────────────────────────────
    def get_impact(self, node_id: str) -> Dict:
        # Neo4j available hai to wahan se query karo
        if self._driver and self._repo_id:
            try:
                with self._driver.session() as s:
                    # Direct dependents — kaun is node pe depend karta hai
                    direct = s.run("""
                        MATCH (caller:CodeNode {repo_id:$r})
                        -[:DEPENDS_ON]->(n:CodeNode {node_id:$nid, repo_id:$r})
                        RETURN caller.node_id AS id, caller.name AS name,
                               caller.node_type AS type, caller.file_path AS file
                    """, r=self._repo_id, nid=node_id)
                    direct_list = [dict(row) for row in direct]

                    # All affected — 3 levels tak traverse (blast radius)
                    all_aff = s.run("""
                        MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
                        MATCH path = (caller:CodeNode {repo_id:$r})
                             -[:DEPENDS_ON*1..3]->(n)
                        UNWIND nodes(path) AS nd
                        WITH DISTINCT nd
                        WHERE nd.node_id <> $nid
                        RETURN nd.node_id AS id, nd.name AS name,
                               nd.node_type AS type, nd.file_path AS file
                        LIMIT 100
                    """, r=self._repo_id, nid=node_id)
                    all_list = [dict(row) for row in all_aff]

                    count = len(all_list)
                    return {
                        "node":              node_id,
                        "direct_dependents": direct_list,
                        "all_affected":      all_list,
                        "impact_count":      count,
                        "impact_level":      self._calculate_impact_level(count),
                    }
            except Exception as e:
                print(f"[Analyzer] Neo4j get_impact failed: {e}, falling back to RAM")

        # Fallback — RAM se (Neo4j nahi hai to)
        if node_id not in self.nodes:
            return {}
        node = self.nodes[node_id]
        affected = self._get_all_dependents(node_id, set())
        return {"node": node_id, "direct_dependents": list(node.parents),
                "all_affected": list(affected), "impact_count": len(affected),
                "impact_level": self._calculate_impact_level(len(affected))}

    def get_dependencies(self, node_id: str) -> Dict:
        if self._driver and self._repo_id:
            try:
                with self._driver.session() as s:
                    # Direct dependencies — yeh node kise call/use karta hai
                    direct = s.run("""
                        MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
                              -[:DEPENDS_ON]->(dep:CodeNode {repo_id:$r})
                        RETURN dep.node_id AS id, dep.name AS name,
                               dep.node_type AS type, dep.file_path AS file
                    """, r=self._repo_id, nid=node_id)
                    direct_list = [dict(row) for row in direct]

                    # All dependencies — 3 levels tak
                    all_deps = s.run("""
                        MATCH (n:CodeNode {node_id:$nid, repo_id:$r})
                        MATCH path = (n)-[:DEPENDS_ON*1..3]->
                                     (dep:CodeNode {repo_id:$r})
                        UNWIND nodes(path) AS nd
                        WITH DISTINCT nd
                        WHERE nd.node_id <> $nid
                        RETURN nd.node_id AS id, nd.name AS name,
                               nd.node_type AS type, nd.file_path AS file
                        LIMIT 100
                    """, r=self._repo_id, nid=node_id)
                    all_list = [dict(row) for row in all_deps]

                    return {
                        "node":             node_id,
                        "direct_deps":      direct_list,
                        "all_deps":         all_list,
                        "dependency_count": len(all_list),
                    }
            except Exception as e:
                print(f"[Analyzer] Neo4j get_dependencies failed: {e}, falling back to RAM")

        if node_id not in self.nodes:
            return {}
        node = self.nodes[node_id]
        deps = self._get_all_dependencies(node_id, set())
        return {"node": node_id, "direct_deps": list(node.children),
                "all_deps": list(deps), "dependency_count": len(deps)}

    def trace_path(self, source_id: str, target_id: str):
        if source_id not in self.nodes or target_id not in self.nodes:
            return None
        queue, visited = deque([(source_id, [source_id])]), {source_id}
        while queue:
            current, path = queue.popleft()
            if current == target_id:
                return path
            for child in self.nodes[current].children:
                if child not in visited:
                    visited.add(child)
                    queue.append((child, path + [child]))
        return None

    def _get_all_dependents(self, node_id, visited):
        if node_id in visited:
            return set()
        visited.add(node_id)
        result = set(self.nodes[node_id].parents)
        for p in self.nodes[node_id].parents:
            result.update(self._get_all_dependents(p, visited))
        return result

    def _get_all_dependencies(self, node_id, visited):
        if node_id in visited:
            return set()
        visited.add(node_id)
        result = set(self.nodes[node_id].children)
        for c in self.nodes[node_id].children:
            result.update(self._get_all_dependencies(c, visited))
        return result

    def _calculate_impact_level(self, count: int) -> str:
        if count == 0:  return "ISOLATED"
        if count <= 3:  return "LOW"
        if count <= 10: return "MEDIUM"
        if count <= 30: return"HIGH"
        return "CRITICAL"