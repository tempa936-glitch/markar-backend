"""
Neo4j Store — GraphStore ka replacement
Graph Neo4j Aura mein save hoga, RAM mein nahi.
Status API Neo4j se query karega — koi crash nahi.
"""

import os
import json
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

from .builder import DependencyNode
from .analyzer import GraphAnalyzer

BATCH_SIZE = 500  # kitne nodes ek baar Neo4j mein jaayenge


def _get_driver():
    try:
        from neo4j import GraphDatabase
    except ImportError:
        raise RuntimeError("pip install neo4j chalao pehle")

    uri  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER",     "neo4j")
    pwd  = os.getenv("NEO4J_PASSWORD", "neo4j")
    return GraphDatabase.driver(uri, auth=(user, pwd))


class Neo4jStore:
    """
    GraphStore jaisi same interface.
    Orchestrator mein sirf import badalna hai.
    """

    def __init__(self, repo_id: str, storage_path: str = ".code_graph"):
        self.repo_id       = repo_id
        self.storage_path  = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self.metadata_file = self.storage_path / "metadata.json"
        self.nodes: Dict[str, DependencyNode] = {}  # analyzer ke liye
        self.analyzer: Optional[GraphAnalyzer] = None
        self._driver = None

    def _connect(self):
        if self._driver is None:
            self._driver = _get_driver()
        return self._driver

    # ── Indexes — ek baar chahiye ────────────────────────────────────────────
    def _create_indexes(self):
        driver = self._connect()
        with driver.session() as s:
            s.run("CREATE INDEX IF NOT EXISTS FOR (n:CodeNode) ON (n.node_id)")
            s.run("CREATE INDEX IF NOT EXISTS FOR (n:CodeNode) ON (n.repo_id)")
            s.run("CREATE INDEX IF NOT EXISTS FOR (n:CodeNode) ON (n.node_type)")
            s.run("CREATE INDEX IF NOT EXISTS FOR (n:CodeNode) ON (n.file_path)")

    # ── Save — graph build ke baad call hoga ─────────────────────────────────
    def save(self, nodes: Dict[str, DependencyNode]):
        self.nodes    = nodes
        self.analyzer = GraphAnalyzer(nodes)
        driver = self._connect()
        self._create_indexes()

        print(f"  [Neo4j] Saving {len(nodes)} nodes...")

        # Purana data delete karo
        with driver.session() as s:
            s.run("MATCH (n:CodeNode {repo_id:$r}) DETACH DELETE n", r=self.repo_id)

        # Nodes batch mein save karo
        node_list = [
            {"node_id": nid, "node_type": n.type,
             "name": n.name, "file_path": n.file_path, "line_no": n.line_no}
            for nid, n in nodes.items()
        ]
        for i in range(0, len(node_list), BATCH_SIZE):
            batch = node_list[i:i+BATCH_SIZE]
            with driver.session() as s:
                s.run("""
                    UNWIND $batch AS row
                    MERGE (n:CodeNode {node_id:row.node_id, repo_id:$r})
                    SET n.node_type=row.node_type, n.name=row.name,
                        n.file_path=row.file_path, n.line_no=row.line_no
                """, batch=batch, r=self.repo_id)
            print(f"  [Neo4j] Nodes {i+len(batch)}/{len(node_list)}")

        # Relationships save karo
        rels = [{"from": nid, "to": cid}
                for nid, n in nodes.items()
                for cid in n.children if cid in nodes]
        for i in range(0, len(rels), BATCH_SIZE):
            batch = rels[i:i+BATCH_SIZE]
            with driver.session() as s:
                s.run("""
                    UNWIND $batch AS row
                    MATCH (a:CodeNode {node_id:row.from, repo_id:$r})
                    MATCH (b:CodeNode {node_id:row.to,   repo_id:$r})
                    MERGE (a)-[:DEPENDS_ON]->(b)
                """, batch=batch, r=self.repo_id)
            print(f"  [Neo4j] Relations {i+len(batch)}/{len(rels)}")

        # Metadata local save karo
        with open(self.metadata_file, "w") as f:
            json.dump({
                "repo_id":     self.repo_id,
                "timestamp":   datetime.now().isoformat(),
                "total_nodes": len(nodes),
                "version":     "neo4j-1.0"
            }, f, indent=2)

        print(f"  [Neo4j] ✅ Done — {len(nodes)} nodes, {len(rels)} relations")

    # ── Stats — COUNT queries, instant ───────────────────────────────────────
    def get_stats(self) -> Dict:
        try:
            driver = self._connect()
            with driver.session() as s:
                rows = s.run("""
                    MATCH (n:CodeNode {repo_id:$r})
                    RETURN n.node_type AS t, count(*) AS c
                """, r=self.repo_id)
                counts = {row["t"]: row["c"] for row in rows}

                avg_row = s.run("""
                    MATCH (n:CodeNode {repo_id:$r})
                    OPTIONAL MATCH (n)-[:DEPENDS_ON]->(m)
                    WITH n, count(m) AS d
                    RETURN avg(d) AS avg
                """, r=self.repo_id).single()
                avg = float(avg_row["avg"] or 0)

            return {
                "total_nodes":      sum(counts.values()),
                "files":            counts.get("file", 0),
                "classes":          counts.get("class", 0),
                "functions":        counts.get("function", 0),
                "avg_dependencies": round(avg, 2),
                "circular_deps":    0,
            }
        except Exception as e:
            return {"error": str(e)}

    # ── Repo overview — dashboard ke liye ────────────────────────────────────
    def get_repo_overview(self) -> Dict:
        """
        Status API ke liye complete overview — Neo4j queries se.
        Koi RAM loop nahi — 100k nodes pe bhi instant.
        """
        try:
            driver = self._connect()
            with driver.session() as s:

                # Top 10 most called functions
                top = s.run("""
                    MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
                    OPTIONAL MATCH ()-[:DEPENDS_ON]->(f)
                    WITH f, count(*) AS dep
                    ORDER BY dep DESC LIMIT 10
                    RETURN f.name AS name, f.file_path AS file,
                           f.line_no AS line, dep AS dependents
                """, r=self.repo_id)
                top_10 = [dict(row) for row in top]

                # Dead code
                dead = s.run("""
                    MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
                    WHERE NOT ()-[:DEPENDS_ON]->(f)
                    AND   NOT (f)-[:DEPENDS_ON]->()
                    RETURN count(f) AS cnt
                """, r=self.repo_id).single()["cnt"]

                # Entry points
                entry = s.run("""
                    MATCH (f:CodeNode {repo_id:$r, node_type:'function'})
                    WHERE NOT ()-[:DEPENDS_ON]->(f)
                    RETURN count(f) AS cnt
                """, r=self.repo_id).single()["cnt"]

                # Per-file breakdown (paginated — pehle 50)
                files_q = s.run("""
                    MATCH (file:CodeNode {repo_id:$r, node_type:'file'})
                    OPTIONAL MATCH (file)-[:DEPENDS_ON]->(fn:CodeNode {node_type:'function'})
                    OPTIONAL MATCH (file)-[:DEPENDS_ON]->(cls:CodeNode {node_type:'class'})
                    OPTIONAL MATCH ()-[:DEPENDS_ON]->(file)
                    WITH file,
                         count(DISTINCT fn)  AS func_count,
                         count(DISTINCT cls) AS cls_count,
                         count(DISTINCT fn)  AS max_dep
                    ORDER BY func_count DESC LIMIT 150
                    RETURN file.file_path AS file,
                           func_count, cls_count, max_dep
                """, r=self.repo_id)

                files = []
                for row in files_q:
                    fc   = row["func_count"]
                    md   = row["max_dep"]
                    risk = _file_risk(fc, md)
                    files.append({
                        "file":           row["file"],
                        "function_count": fc,
                        "class_count":    row["cls_count"],
                        "max_dependents": md,
                        "risk":           risk,
                    })

                stats = self.get_stats()

            return {
                "total_files":        stats.get("files", 0),
                "total_functions":    stats.get("functions", 0),
                "total_classes":      stats.get("classes", 0),
                "dead_code_count":    dead,
                "entry_points_count": entry,
                "top_10_most_called": top_10,
                "files":              files,
                "issues_summary": {
                    "critical": sum(1 for f in files if f["risk"] == "CRITICAL"),
                    "high":     sum(1 for f in files if f["risk"] == "HIGH"),
                    "total_issues": sum(1 for f in files if f["risk"] in ("CRITICAL","HIGH")),
                }
            }
        except Exception as e:
            return {"error": str(e)}

    # ── Paginated files — dashboard file browser ──────────────────────────────
    def get_files_page(self, page: int = 1, page_size: int = 20,
                       risk_filter: str = None) -> Dict:
        try:
            driver = self._connect()
            offset = (page - 1) * page_size
            with driver.session() as s:
                total = s.run("""
                    MATCH (f:CodeNode {repo_id:$r, node_type:'file'})
                    RETURN count(f) AS cnt
                """, r=self.repo_id).single()["cnt"]

                rows = s.run("""
                    MATCH (file:CodeNode {repo_id:$r, node_type:'file'})
                    OPTIONAL MATCH (file)-[:DEPENDS_ON]->(fn:CodeNode {node_type:'function'})
                    OPTIONAL MATCH (file)-[:DEPENDS_ON]->(cls:CodeNode {node_type:'class'})
                    WITH file,
                         count(DISTINCT fn)  AS func_count,
                         count(DISTINCT cls) AS cls_count,
                         count(DISTINCT fn)  AS max_dep
                    ORDER BY func_count DESC
                    SKIP $skip LIMIT $limit
                    RETURN file.file_path AS file, func_count, cls_count, max_dep
                """, r=self.repo_id, skip=offset, limit=page_size)

                files = []
                for row in rows:
                    risk = _file_risk(row["func_count"], row["max_dep"])
                    if risk_filter and risk != risk_filter.upper():
                        continue
                    files.append({
                        "file":           row["file"],
                        "function_count": row["func_count"],
                        "class_count":    row["cls_count"],
                        "max_dependents": row["max_dep"],
                        "risk":           risk,
                    })

            return {
                "page":        page,
                "page_size":   page_size,
                "total_files": total,
                "total_pages": (total + page_size - 1) // page_size,
                "files":       files,
            }
        except Exception as e:
            return {"error": str(e), "files": []}

    # ── Single file detail ────────────────────────────────────────────────────
    def get_file_detail(self, file_path: str) -> Optional[Dict]:
        try:
            driver = self._connect()
            with driver.session() as s:
                funcs = s.run("""
                    MATCH (fn:CodeNode {repo_id:$r, node_type:'function',
                                        file_path:$fp})
                    OPTIONAL MATCH (caller)-[:DEPENDS_ON]->(fn)
                    OPTIONAL MATCH (fn)-[:DEPENDS_ON]->(callee:CodeNode {node_type:'function'})
                    WITH fn,
                         count(DISTINCT caller) AS dep,
                         collect(DISTINCT {name:caller.name, file:caller.file_path})[..10] AS called_by,
                         collect(DISTINCT {name:callee.name, file:callee.file_path})[..10] AS calls
                    RETURN fn.name AS name, fn.line_no AS line,
                           dep, called_by, calls
                    ORDER BY dep DESC
                """, r=self.repo_id, fp=file_path)

                functions = []
                for row in funcs:
                    dep = row["dep"]
                    functions.append({
                        "name":       row["name"],
                        "line":       row["line"],
                        "dependents": dep,
                        "risk":       _func_risk(dep),
                        "called_by":  [x for x in row["called_by"] if x.get("name")],
                        "calls":      [x for x in row["calls"]     if x.get("name")],
                        "is_dead_code": dep == 0,
                    })

                classes = s.run("""
                    MATCH (cls:CodeNode {repo_id:$r, node_type:'class', file_path:$fp})
                    OPTIONAL MATCH (cls)-[:DEPENDS_ON]->(m:CodeNode {node_type:'function'})
                    WITH cls, collect({name:m.name, line:m.line_no}) AS methods
                    RETURN cls.name AS name, cls.line_no AS line, methods
                """, r=self.repo_id, fp=file_path)

                return {
                    "file":      file_path,
                    "functions": functions,
                    "classes":   [dict(r) for r in classes],
                }
        except Exception as e:
            return {"error": str(e)}

    # ── Existing interface (orchestrator compatibility) ────────────────────────
    def search_nodes(self, query: str, node_type: Optional[str] = None) -> List[Dict]:
        try:
            driver = self._connect()
            with driver.session() as s:
                cypher = """
                    MATCH (n:CodeNode {repo_id:$r})
                    WHERE toLower(n.name) CONTAINS toLower($q)
                """ + ("AND n.node_type=$t " if node_type else "") + """
                    RETURN n.node_id AS id, n.name AS name,
                           n.node_type AS type, n.file_path AS file_path,
                           n.line_no AS line_no
                    LIMIT 50
                """
                params = {"r": self.repo_id, "q": query}
                if node_type:
                    params["t"] = node_type
                return [dict(r) for r in s.run(cypher, **params)]
        except Exception:
            return []

    def get_file_structure(self, file_path: str) -> Dict:
        detail = self.get_file_detail(file_path) or {}
        return {
            "file":      file_path,
            "classes":   detail.get("classes", []),
            "functions": [{"name": f["name"], "line_no": f["line"]}
                          for f in detail.get("functions", [])],
        }

    def query_impact(self, node_id: str) -> Dict:
        if self.analyzer:
            return self.analyzer.get_impact(node_id)
        return {"node_id": node_id, "impacted_nodes": []}

    def query_dependencies(self, node_id: str) -> Dict:
        if self.analyzer:
            return self.analyzer.get_dependencies(node_id)
        return {"node_id": node_id, "dependencies": []}

    def query_circular_deps(self) -> List:
        if self.analyzer:
            return self.analyzer.find_circular_dependencies()
        return []

    def export_for_visualization(self, max_depth: int = 3) -> Dict:
        try:
            driver = self._connect()
            with driver.session() as s:
                rows = s.run("""
                    MATCH (n:CodeNode {repo_id:$r})
                    WHERE n.node_type IN ['file','function']
                    WITH n LIMIT 200
                    OPTIONAL MATCH (n)-[:DEPENDS_ON]->(m:CodeNode {repo_id:$r})
                    RETURN n.node_id AS id, n.name AS name, n.node_type AS type,
                           collect({id:m.node_id}) AS children
                """, r=self.repo_id)
                nodes_out, links_out, seen = [], [], set()
                for row in rows:
                    if row["id"] not in seen:
                        nodes_out.append({"id": row["id"], "name": row["name"], "type": row["type"]})
                        seen.add(row["id"])
                    for c in row["children"]:
                        if c.get("id"):
                            links_out.append({"source": row["id"], "target": c["id"], "type": "calls"})
            return {"nodes": nodes_out, "links": links_out}
        except Exception as e:
            return {"nodes": [], "links": [], "error": str(e)}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _func_risk(d: int) -> str:
    if d == 0:  return "ISOLATED"
    if d <= 3:  return "LOW"
    if d <= 10: return "MEDIUM"
    if d <= 30: return "HIGH"
    return "CRITICAL"

def _file_risk(fc: int, md: int) -> str:
    if md > 30:    return "CRITICAL"
    if md > 10:    return "HIGH"
    if fc > 30:    return "HIGH"
    if fc > 15:    return "MEDIUM"
    if fc > 5:     return "LOW"
    return "ISOLATED"