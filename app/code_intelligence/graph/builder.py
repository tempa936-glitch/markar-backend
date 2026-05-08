"""
Build dependency graphs from parsed code structure.

Creates:
- Call graphs (who calls whom)
- Dependency graphs (file dependencies)
- Import relationships
"""

from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
from collections import defaultdict

from app.code_intelligence.parser import RepositoryParser, Function, ClassInfo, FileInfo


@dataclass
class CallRelation:
    """Represents a call relationship."""
    caller: str  # full name of caller
    callee: str  # full name of callee
    caller_file: str
    callee_file: str
    line_no: int


@dataclass
class DependencyNode:
    """Graph node for dependency analysis."""
    id: str  # unique identifier
    type: str  # 'file', 'class', 'function'
    name: str
    file_path: str
    line_no: int
    
    # Relationships
    parents: Set[str] = field(default_factory=set)  # what depends on this
    children: Set[str] = field(default_factory=set)  # what this depends on


class DependencyGraphBuilder:
    """Build complete dependency graph from parsed repository."""
    
    def __init__(self, parser: RepositoryParser):
        self.parser = parser
        self.nodes: Dict[str, DependencyNode] = {}
        self.call_relations: List[CallRelation] = []
        self.import_map: Dict[str, Set[str]] = defaultdict(set)
    
    def build(self) -> Dict[str, DependencyNode]:
        """Build the complete dependency graph."""
        self._create_nodes()
        self._build_call_graph()
        self._build_import_graph()
        return self.nodes
    
    def _create_nodes(self):
        """Create nodes for all files, classes, and functions."""
        for file_path, file_info in self.parser.files.items():
            # File node
            file_id = f"file:{file_path}"
            self.nodes[file_id] = DependencyNode(
                id=file_id,
                type='file',
                name=file_path,
                file_path=file_path,
                line_no=0
            )
            
            # Class nodes
            for cls in file_info.classes:
                class_id = f"class:{cls.name}@{file_path}"
                self.nodes[class_id] = DependencyNode(
                    id=class_id,
                    type='class',
                    name=cls.name,
                    file_path=file_path,
                    line_no=cls.line_no
                )
                # Class belongs to file
                self.nodes[file_id].children.add(class_id)
                self.nodes[class_id].parents.add(file_id)
            
            # Function nodes
            for func in file_info.functions:
                func_id = f"func:{func.full_name}@{file_path}"
                self.nodes[func_id] = DependencyNode(
                    id=func_id,
                    type='function',
                    name=func.full_name,
                    file_path=file_path,
                    line_no=func.line_no
                )
                
                # Function belongs to file (or class)
                if func.class_name:
                    class_id = f"class:{func.class_name}@{file_path}"
                    if class_id in self.nodes:
                        self.nodes[class_id].children.add(func_id)
                        self.nodes[func_id].parents.add(class_id)
                else:
                    self.nodes[file_id].children.add(func_id)
                    self.nodes[func_id].parents.add(file_id)
    
    def _build_call_graph(self):
        """Build call relationships between functions."""
        all_functions = self.parser.get_all_functions()
        
        for func in all_functions.values():
            caller_id = f"func:{func.full_name}@{func.file_path}"
            
            for called_name in func.calls:
                # Try to find the called function
                callee_id = self._find_function_id(called_name, func.file_path)
                
                if callee_id and callee_id in self.nodes:
                    # Add relationship
                    self.nodes[caller_id].children.add(callee_id)
                    self.nodes[callee_id].parents.add(caller_id)
                    
                    # Record call relation
                    callee_file = self.nodes[callee_id].file_path
                    self.call_relations.append(CallRelation(
                        caller=func.full_name,
                        callee=called_name,
                        caller_file=func.file_path,
                        callee_file=callee_file,
                        line_no=func.line_no
                    ))
    
    def _build_import_graph(self):
        """Build import dependencies between files."""
        for file_path, file_info in self.parser.files.items():
            file_id = f"file:{file_path}"
            
            for import_info in file_info.imports:
                # Map module names to file paths
                imported_files = self._resolve_imports(import_info.module)
                
                for imported_file in imported_files:
                    if imported_file in self.parser.files:
                        imported_id = f"file:{imported_file}"
                        self.nodes[file_id].children.add(imported_id)
                        self.nodes[imported_id].parents.add(file_id)
                        self.import_map[file_path].add(imported_file)
    
    def _find_function_id(self, func_name: str, current_file: str) -> Optional[str]:
        """
        Find function ID — improved matching:
        1. Direct lookup
        2. Same-file priority (local calls)
        3. self.xyz.method → strip 'self.' prefix
        4. Last segment match (ClassName.method → method)
        5. Skip external libs (no dot OR known stdlib prefix)
        """
        all_functions = self.parser.get_all_functions()

        # self.something.method → strip self prefix
        if func_name.startswith("self."):
            func_name = func_name[5:]  # "self.db.execute" → "db.execute"

        # Skip obvious external calls — single known builtins or
        # calls starting with common stdlib/external prefixes
        _EXTERNAL_PREFIXES = (
            "os.", "sys.", "re.", "json.", "math.", "time.", "datetime.",
            "logging.", "typing.", "collections.", "itertools.", "functools.",
            "pytest.", "mock.", "unittest.", "asyncio.", "pathlib.",
            "sqlalchemy.", "pydantic.", "fastapi.", "celery.", "redis.",
            "print", "len", "str", "int", "float", "list", "dict", "set",
            "tuple", "bool", "type", "isinstance", "hasattr", "getattr",
            "super", "range", "enumerate", "zip", "map", "filter",
        )
        if any(func_name.startswith(p) for p in _EXTERNAL_PREFIXES):
            return None

        # 1. Direct lookup
        if func_name in all_functions:
            func = all_functions[func_name]
            return f"func:{func.full_name}@{func.file_path}"

        # 2. Same-file priority — local calls should prefer same file
        last_part = func_name.split(".")[-1]
        same_file_match = None
        for fname, func in all_functions.items():
            fname_last = fname.split(".")[-1]
            if fname_last == last_part and func.file_path == current_file:
                same_file_match = f"func:{func.full_name}@{func.file_path}"
                break

        if same_file_match:
            return same_file_match

        # 3. Global match — any file, last segment match
        for fname, func in all_functions.items():
            fname_last = fname.split(".")[-1]
            if fname_last == last_part:
                return f"func:{func.full_name}@{func.file_path}"

        # 4. Endswith match (ClassName.method_name)
        for fname, func in all_functions.items():
            if fname.endswith(func_name):
                return f"func:{func.full_name}@{func.file_path}"

        return None
    
    def _resolve_imports(self, module_name: str) -> Set[str]:
        """Resolve module name to file paths."""
        result = set()
        
        # Simple resolution: convert module.path to file/path.py
        file_path = module_name.replace('.', '/')
        
        # Check multiple possible paths
        candidates = [
            f"{file_path}.py",
            f"{file_path}/__init__.py",
            f"{file_path}/index.py",
        ]
        
        for candidate in candidates:
            if candidate in self.parser.files:
                result.add(candidate)
        
        return result