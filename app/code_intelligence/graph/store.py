"""Graph storage and query layer - JSON-based persistence."""

import json
from typing import Dict, List, Optional, Set
from pathlib import Path
from datetime import datetime

from .builder import DependencyNode
from .analyzer import GraphAnalyzer


class GraphStore:
    """Store and query dependency graphs."""
    
    def __init__(self, storage_path: str = ".code_graph"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self.graph_file = self.storage_path / "graph.json"
        self.metadata_file = self.storage_path / "metadata.json"
        self.nodes: Dict[str, DependencyNode] = {}
        self.analyzer: Optional[GraphAnalyzer] = None
    
    def save(self, nodes: Dict[str, DependencyNode]):
        """Save graph to storage."""
        self.nodes = nodes
        self.analyzer = GraphAnalyzer(nodes)
        
        # Serialize nodes to JSON
        graph_data = {}
        for node_id, node in nodes.items():
            graph_data[node_id] = {
                'id': node.id,
                'type': node.type,
                'name': node.name,
                'file_path': node.file_path,
                'line_no': node.line_no,
                'parents': list(node.parents),
                'children': list(node.children)
            }
        
        # Save graph
        with open(self.graph_file, 'w') as f:
            json.dump(graph_data, f, indent=2)
        
        # Save metadata
        metadata = {
            'timestamp': datetime.now().isoformat(),
            'total_nodes': len(nodes),
            'node_types': self._count_types(),
            'version': '1.0'
        }
        
        with open(self.metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"Graph saved to {self.graph_file}")
        print(f"Total nodes: {len(nodes)}")
    
    def load(self) -> Dict[str, DependencyNode]:
        """Load graph from storage."""
        if not self.graph_file.exists():
            return {}
        
        with open(self.graph_file, 'r') as f:
            graph_data = json.load(f)
        
        # Deserialize nodes
        nodes = {}
        for node_id, data in graph_data.items():
            node = DependencyNode(
                id=data['id'],
                type=data['type'],
                name=data['name'],
                file_path=data['file_path'],
                line_no=data['line_no'],
                parents=set(data.get('parents', [])),
                children=set(data.get('children', []))
            )
            nodes[node_id] = node
        
        self.nodes = nodes
        self.analyzer = GraphAnalyzer(nodes)
        return nodes
    
    def _count_types(self) -> Dict[str, int]:
        """Count nodes by type."""
        counts = {}
        for node in self.nodes.values():
            counts[node.type] = counts.get(node.type, 0) + 1
        return counts
    
    def query_impact(self, node_id: str) -> Dict:
        """Query blast radius."""
        if not self.analyzer:
            return {}
        return self.analyzer.get_impact(node_id)
    
    def query_dependencies(self, node_id: str) -> Dict:
        """Query all dependencies."""
        if not self.analyzer:
            return {}
        return self.analyzer.get_dependencies(node_id)
    
    def query_path(self, source_id: str, target_id: str) -> Optional[List[str]]:
        """Query call path."""
        if not self.analyzer:
            return None
        return self.analyzer.trace_path(source_id, target_id)
    
    def query_circular_deps(self) -> List[List[str]]:
        """Find circular dependencies."""
        if not self.analyzer:
            return []
        return self.analyzer.find_circular_dependencies()
    
    def search_nodes(self, query: str, node_type: Optional[str] = None) -> List[Dict]:
        """Search for nodes by name."""
        results = []
        query_lower = query.lower()
        
        for node_id, node in self.nodes.items():
            if query_lower in node.name.lower():
                if node_type is None or node.type == node_type:
                    results.append({
                        'id': node_id,
                        'name': node.name,
                        'type': node.type,
                        'file_path': node.file_path,
                        'line_no': node.line_no
                    })
        
        return results
    
    def get_file_structure(self, file_path: str) -> Dict:
        """Get all entities in a file."""
        file_id = f"file:{file_path}"
        
        if file_id not in self.nodes:
            return {}
        
        file_node = self.nodes[file_id]
        
        structure = {
            'file': file_path,
            'classes': [],
            'functions': []
        }
        
        for child_id in file_node.children:
            node = self.nodes[child_id]
            
            if node.type == 'class':
                class_info = {
                    'name': node.name,
                    'line_no': node.line_no,
                    'methods': []
                }
                
                # Get methods
                for method_id in node.children:
                    method = self.nodes[method_id]
                    class_info['methods'].append({
                        'name': method.name.split('.')[-1],
                        'line_no': method.line_no
                    })
                
                structure['classes'].append(class_info)
            
            elif node.type == 'function':
                structure['functions'].append({
                    'name': node.name,
                    'line_no': node.line_no
                })
        
        return structure
    
    def get_stats(self) -> Dict:
        """Get overall graph statistics."""
        if not self.nodes:
            return {}
        
        file_nodes = [n for n in self.nodes.values() if n.type == 'file']
        class_nodes = [n for n in self.nodes.values() if n.type == 'class']
        func_nodes = [n for n in self.nodes.values() if n.type == 'function']
        
        avg_deps = sum(len(n.children) for n in self.nodes.values()) / len(self.nodes) if self.nodes else 0
        
        return {
            'total_nodes': len(self.nodes),
            'files': len(file_nodes),
            'classes': len(class_nodes),
            'functions': len(func_nodes),
            'avg_dependencies': round(avg_deps, 2),
            'circular_deps': len(self.query_circular_deps())
        }
    
    def export_for_visualization(self, max_depth: int = 3) -> Dict:
        """Export graph in format suitable for visualization."""
        nodes_list = []
        links_list = []
        visited = set()
        
        for node_id, node in self.nodes.items():
            if node.type == 'file':  # Start with file nodes
                self._export_tree(node_id, nodes_list, links_list, visited, 0, max_depth)
        
        return {
            'nodes': nodes_list,
            'links': links_list
        }
    
    def _export_tree(self, node_id: str, nodes_list: List, links_list: List, 
                     visited: Set, depth: int, max_depth: int):
        """Recursively export node and children."""
        if depth >= max_depth or node_id in visited:
            return
        
        visited.add(node_id)
        node = self.nodes[node_id]
        
        nodes_list.append({
            'id': node_id,
            'name': node.name,
            'type': node.type,
            'depth': depth
        })
        
        for child_id in list(node.children)[:5]:  # Limit children for clarity
            if child_id not in visited:
                links_list.append({
                    'source': node_id,
                    'target': child_id,
                    'type': 'calls'
                })
                self._export_tree(child_id, nodes_list, links_list, visited, depth + 1, max_depth)
