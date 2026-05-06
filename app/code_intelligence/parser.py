"""
AST-based Python code parser for building structural graphs.

Parses Python files and extracts:
- Classes and methods
- Functions
- Imports and dependencies
- Function calls and relationships
"""

import ast
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class Function:
    """Represents a function in the codebase."""
    name: str
    file_path: str
    line_no: int
    class_name: Optional[str] = None
    params: List[str] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)  # function names called
    decorators: List[str] = field(default_factory=list)
    
    @property
    def full_name(self) -> str:
        """Returns fully qualified name."""
        return f"{self.class_name}.{self.name}" if self.class_name else self.name


@dataclass
class ClassInfo:
    """Represents a class in the codebase."""
    name: str
    file_path: str
    line_no: int
    methods: List[str] = field(default_factory=list)
    base_classes: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    """Represents an import statement."""
    file_path: str
    module: str
    items: List[str] = field(default_factory=list)  # for 'from X import Y'
    alias: Optional[str] = None


@dataclass
class FileInfo:
    """Represents a Python file."""
    path: str
    functions: List[Function] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)


class CodeParser(ast.NodeVisitor):
    """AST visitor to extract code structure."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.functions: List[Function] = []
        self.classes: List[ClassInfo] = []
        self.imports: List[ImportInfo] = []
        self.current_class: Optional[str] = None
        self.current_scope: List[str] = []  # Stack for nested scopes
        
    def visit_Import(self, node: ast.Import):
        """Handle: import X, import X as Y"""
        for alias in node.names:
            import_info = ImportInfo(
                file_path=self.file_path,
                module=alias.name,
                alias=alias.asname
            )
            self.imports.append(import_info)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Handle: from X import Y, from X import Y as Z"""
        if node.module:
            items = [alias.name for alias in node.names]
            import_info = ImportInfo(
                file_path=self.file_path,
                module=node.module,
                items=items
            )
            self.imports.append(import_info)
        self.generic_visit(node)
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Handle class definitions."""
        base_classes = [self._get_name(base) for base in node.bases]
        decorators = [self._get_name(dec) for dec in node.decorator_list]
        
        class_info = ClassInfo(
            name=node.name,
            file_path=self.file_path,
            line_no=node.lineno,
            base_classes=base_classes,
            decorators=decorators
        )
        
        prev_class = self.current_class
        self.current_class = node.name
        
        # Visit methods
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                class_info.methods.append(item.name)
        
        self.classes.append(class_info)
        self.generic_visit(node)
        self.current_class = prev_class
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Handle function definitions."""
        params = [arg.arg for arg in node.args.args]
        calls = self._extract_function_calls(node)
        decorators = [self._get_name(dec) for dec in node.decorator_list]
        
        func_info = Function(
            name=node.name,
            file_path=self.file_path,
            line_no=node.lineno,
            class_name=self.current_class,
            params=params,
            calls=calls,
            decorators=decorators
        )
        
        self.functions.append(func_info)
        self.generic_visit(node)
    
    # Alias for async functions
    visit_AsyncFunctionDef = visit_FunctionDef
    
    def _extract_function_calls(self, node: ast.AST) -> List[str]:
        """Extract all function calls within a node."""
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._get_name(child.func)
                if call_name:
                    calls.append(call_name)
        return calls
    
    def _get_name(self, node: ast.AST) -> Optional[str]:
        """Extract name from various node types."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value = self._get_name(node.value)
            return f"{value}.{node.attr}" if value else node.attr
        elif isinstance(node, ast.Call):
            return self._get_name(node.func)
        return None


class RepositoryParser:
    """Parse entire repository and build structure."""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.files: Dict[str, FileInfo] = {}
    
    def parse(self, exclude_dirs: Set[str] = None) -> Dict[str, FileInfo]:
        """Parse all Python files in the repository."""
        if exclude_dirs is None:
            exclude_dirs = {'.venv', '__pycache__', '.git', 'node_modules', '.pytest_cache'}
        
        for py_file in self.repo_path.rglob('*.py'):
            # Skip excluded directories
            if any(excluded in py_file.parts for excluded in exclude_dirs):
                continue
            
            try:
                self._parse_file(str(py_file))
            except Exception as e:
                print(f"Error parsing {py_file}: {e}")
        
        return self.files
    
    def _parse_file(self, file_path: str):
        """Parse a single Python file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            parser = CodeParser(file_path)
            parser.visit(tree)
            
            # Get relative path
            rel_path = os.path.relpath(file_path, self.repo_path)
            
            file_info = FileInfo(
                path=rel_path,
                functions=parser.functions,
                classes=parser.classes,
                imports=parser.imports
            )
            
            self.files[rel_path] = file_info
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
    
    def get_all_functions(self) -> Dict[str, Function]:
        """Get all functions keyed by their full names."""
        result = {}
        for file_info in self.files.values():
            for func in file_info.functions:
                result[func.full_name] = func
        return result
    
    def get_all_classes(self) -> Dict[str, ClassInfo]:
        """Get all classes keyed by name."""
        result = {}
        for file_info in self.files.values():
            for cls in file_info.classes:
                result[cls.name] = cls
        return result
