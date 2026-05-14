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

        # ── Pre-build lookup indexes — O(N) once, O(1) per lookup ──────
        self._all_functions: Dict[str, Function] = {}
        # last_segment → list of Function — for fast suffix search
        self._func_by_last: Dict[str, List[Function]] = defaultdict(list)
        # full endswith index — "ClassName.method" → list of Function
        self._func_endswith: Dict[str, List[Function]] = defaultdict(list)

    def build(self) -> Dict[str, DependencyNode]:
        """Build the complete dependency graph."""
        # Build indexes ONCE before any lookup-heavy step
        self._all_functions = self.parser.get_all_functions()
        for fname, func in self._all_functions.items():
            last = fname.split(".")[-1]
            self._func_by_last[last].append(func)
            # endswith index: every suffix segment
            parts = fname.split(".")
            for i in range(len(parts)):
                suffix = ".".join(parts[i:])
                if suffix != fname:  # skip exact match (already in _all_functions)
                    self._func_endswith[suffix].append(func)

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
        # Use pre-built index — NO repeated get_all_functions() calls
        all_functions = self._all_functions

        for func in all_functions.values():
            caller_id = f"func:{func.full_name}@{func.file_path}"
            
            for called_name in func.calls:
                callee_id = self._find_function_id(called_name, func.file_path)
                
                if callee_id and callee_id in self.nodes:
                    self.nodes[caller_id].children.add(callee_id)
                    self.nodes[callee_id].parents.add(caller_id)
                    
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
                imported_files = self._resolve_imports(import_info.module)
                
                for imported_file in imported_files:
                    if imported_file in self.parser.files:
                        imported_id = f"file:{imported_file}"
                        self.nodes[file_id].children.add(imported_id)
                        self.nodes[imported_id].parents.add(file_id)
                        self.import_map[file_path].add(imported_file)
    
    # ── External prefixes to skip — no changes needed ─────────────────────
    _EXTERNAL_PREFIXES = (
        "os.", "sys.", "re.", "json.", "math.", "time.", "datetime.",
        "logging.", "typing.", "collections.", "itertools.", "functools.",
        "pytest.", "mock.", "unittest.", "asyncio.", "pathlib.",
        "sqlalchemy.", "pydantic.", "fastapi.", "celery.", "redis.",
        "print", "len", "str", "int", "float", "list", "dict", "set",
        "tuple", "bool", "type", "isinstance", "hasattr", "getattr",
        "super", "range", "enumerate", "zip", "map", "filter",
    )

    def _find_function_id(self, func_name: str, current_file: str) -> Optional[str]:
        """
        Find function ID using pre-built indexes — O(1) average, no dict rebuild.
        """
        all_functions = self._all_functions

        # self.something.method → strip self prefix
        if func_name.startswith("self."):
            func_name = func_name[5:]

        # Skip known external/stdlib calls
        if any(func_name.startswith(p) for p in self._EXTERNAL_PREFIXES):
            return None

        # 1. Direct lookup — O(1)
        if func_name in all_functions:
            func = all_functions[func_name]
            return f"func:{func.full_name}@{func.file_path}"

        # 2. Same-file priority using last-segment index — O(k) where k is collisions
        last_part = func_name.split(".")[-1]
        candidates = self._func_by_last.get(last_part, [])

        same_file_match = None
        global_match = None
        for func in candidates:
            if func.file_path == current_file:
                same_file_match = f"func:{func.full_name}@{func.file_path}"
                break
            if global_match is None:
                global_match = f"func:{func.full_name}@{func.file_path}"

        if same_file_match:
            return same_file_match
        if global_match:
            return global_match

        # 3. Endswith match using pre-built index — O(1) instead of O(N) loop
        ew_candidates = self._func_endswith.get(func_name, [])
        if ew_candidates:
            return f"func:{ew_candidates[0].full_name}@{ew_candidates[0].file_path}"

        return None
    
    def _resolve_imports(self, module_name: str) -> Set[str]:
        """Resolve module name to file paths."""
        result = set()
        
        file_path = module_name.replace('.', '/')
        
        candidates = [
            f"{file_path}.py",
            f"{file_path}/__init__.py",
            f"{file_path}/index.py",
        ]
        
        for candidate in candidates:
            if candidate in self.parser.files:
                result.add(candidate)
        
        return result
