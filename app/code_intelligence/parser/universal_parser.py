"""
Universal Tree-Sitter Parser — 40+ Language Support
=====================================================
Supports: Python, JavaScript, TypeScript, TSX, Java, Go, Rust,
          C, C++, C#, Ruby, PHP, Kotlin, Swift, Scala, Bash, etc.

Plugs into existing RepositoryParser / DependencyGraphBuilder without
breaking anything. Python files still go through ast (faster + richer),
all other languages go through tree-sitter.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

# ─── Re-use existing dataclasses ──────────────────────────────────────────────
from .code_parser import Function, ClassInfo, ImportInfo, FileInfo


# ─── Language → file extension mapping ────────────────────────────────────────
EXTENSION_MAP: Dict[str, str] = {
    # Python  (handled by existing ast parser — skipped here)
    ".py":    "python",
    # JavaScript / TypeScript
    ".js":    "javascript",
    ".jsx":   "javascript",
    ".mjs":   "javascript",
    ".cjs":   "javascript",
    ".ts":    "typescript",
    ".tsx":   "tsx",
    # Java / JVM
    ".java":  "java",
    ".kt":    "kotlin",
    ".kts":   "kotlin",
    ".scala": "scala",
    ".groovy":"java",          # best-effort with java grammar
    # Go
    ".go":    "go",
    # Rust
    ".rs":    "rust",
    # C / C++
    ".c":     "c",
    ".h":     "c",
    ".cpp":   "cpp",
    ".cc":    "cpp",
    ".cxx":   "cpp",
    ".hpp":   "cpp",
    ".hxx":   "cpp",
    # C#
    ".cs":    "c_sharp",
    # Ruby
    ".rb":    "ruby",
    ".rake":  "ruby",
    # PHP
    ".php":   "php",
    # Swift
    ".swift": "swift",
    # Bash / Shell
    ".sh":    "bash",
    ".bash":  "bash",
    # Lua
    ".lua":   "lua",
    # Elixir
    ".ex":    "elixir",
    ".exs":   "elixir",
    # Haskell
    ".hs":    "haskell",
    # OCaml
    ".ml":    "ocaml",
    ".mli":   "ocaml",
    # HTML / CSS (structure only)
    ".html":  "html",
    ".htm":   "html",
    # Markdown (headings as 'functions')
    ".md":    "markdown",
    ".mdx":   "markdown",
    # TOML / YAML / JSON  (keys as imports)
    ".toml":  "toml",
}

# Extensions that use the existing ast-based Python parser
PYTHON_EXTENSIONS: Set[str] = {".py", ".pyi"}

# Directories to always skip
DEFAULT_EXCLUDE_DIRS: Set[str] = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".pytest_cache", ".mypy_cache", "dist", "build", ".next",
    "target", "bin", "obj",
}


# ─── Parsed result per file ────────────────────────────────────────────────────
@dataclass
class ParsedFile:
    """Richer version of FileInfo — compatible with FileInfo interface."""
    path: str
    language: str
    functions: List[Function] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)

    def to_file_info(self) -> FileInfo:
        """Convert to existing FileInfo for backward compatibility."""
        return FileInfo(
            path=self.path,
            functions=self.functions,
            classes=self.classes,
            imports=self.imports,
        )


# ─── Per-language query definitions ───────────────────────────────────────────
# Each entry: (node_type, name_field, optional_class_field)
# These are Tree-sitter node-type strings used to walk the AST.
LANG_QUERIES: Dict[str, Dict] = {
    "javascript": {
        "function_types": [
            "function_declaration",
            "function",
            "arrow_function",
            "method_definition",
        ],
        "class_types": ["class_declaration", "class"],
        # call_expression: require('...') CommonJS imports ke liye
        "import_types": ["import_statement", "import_clause", "call_expression"],
    },
    "typescript": {
        "function_types": [
            "function_declaration",
            "function",
            "arrow_function",
            "method_definition",
            "method_signature",
        ],
        "class_types": ["class_declaration", "class", "interface_declaration"],
        "import_types": ["import_statement", "call_expression"],
    },
    "tsx": {  # same as typescript
        "function_types": [
            "function_declaration",
            "function",
            "arrow_function",
            "method_definition",
        ],
        "class_types": ["class_declaration", "interface_declaration"],
        "import_types": ["import_statement", "call_expression"],
    },
    "java": {
        "function_types": ["method_declaration", "constructor_declaration"],
        "class_types": ["class_declaration", "interface_declaration", "enum_declaration"],
        "import_types": ["import_declaration"],
    },
    "kotlin": {
        "function_types": ["function_declaration", "secondary_constructor"],
        "class_types": ["class_declaration", "object_declaration", "interface_declaration"],
        "import_types": ["import_header"],
    },
    "go": {
        "function_types": ["function_declaration", "method_declaration"],
        "class_types": ["type_spec"],  # Go structs
        "import_types": ["import_declaration", "import_spec"],
    },
    "rust": {
        "function_types": ["function_item"],
        "class_types": ["struct_item", "impl_item", "trait_item", "enum_item"],
        "import_types": ["use_declaration"],
    },
    "c": {
        "function_types": ["function_definition"],
        "class_types": ["struct_specifier", "enum_specifier"],
        "import_types": ["preproc_include"],
    },
    "cpp": {
        "function_types": ["function_definition"],
        "class_types": ["class_specifier", "struct_specifier"],
        "import_types": ["preproc_include"],
    },
    "c_sharp": {
        "function_types": ["method_declaration", "constructor_declaration"],
        "class_types": ["class_declaration", "interface_declaration", "struct_declaration"],
        "import_types": ["using_directive"],
    },
    "ruby": {
        "function_types": ["method", "singleton_method"],
        "class_types": ["class", "module"],
        "import_types": ["call"],  # require / require_relative
    },
    "php": {
        "function_types": ["function_definition", "method_declaration"],
        "class_types": ["class_declaration", "interface_declaration", "trait_declaration"],
        "import_types": ["require_expression", "include_expression"],
    },
    "swift": {
        "function_types": ["function_declaration"],
        "class_types": ["class_declaration", "struct_declaration", "protocol_declaration"],
        "import_types": ["import_declaration"],
    },
    "scala": {
        "function_types": ["function_definition", "function_declaration"],
        "class_types": ["class_definition", "object_definition", "trait_definition"],
        "import_types": ["import_declaration"],
    },
    "bash": {
        "function_types": ["function_definition"],
        "class_types": [],
        "import_types": [],
    },
    "lua": {
        "function_types": ["function_definition", "local_function"],
        "class_types": [],
        "import_types": [],
    },
    "elixir": {
        "function_types": ["def", "defp"],
        "class_types": ["defmodule"],
        "import_types": ["alias", "import", "use"],
    },
    "haskell": {
        "function_types": ["function"],
        "class_types": ["data_declaration", "class_declaration"],
        "import_types": ["import"],
    },
    "ocaml": {
        "function_types": ["let_binding"],
        "class_types": ["type_definition", "module_definition"],
        "import_types": ["open_module"],
    },
    "html": {
        "function_types": [],
        "class_types": [],
        "import_types": ["script_element", "link_element"],
    },
    "markdown": {
        "function_types": ["atx_heading"],
        "class_types": [],
        "import_types": [],
    },
    "toml": {
        "function_types": [],
        "class_types": ["table"],
        "import_types": [],
    },
}


# ─── Helper: safe node text ────────────────────────────────────────────────────
def _text(node, src: bytes) -> str:
    try:
        return src[node.start_byte: node.end_byte].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _child_text(node, field_name: str, src: bytes) -> Optional[str]:
    """Get text of a named child field."""
    child = node.child_by_field_name(field_name)
    if child:
        return _text(child, src)
    # Fallback: first identifier child
    for c in node.children:
        if c.type == "identifier":
            return _text(c, src)
    return None


# ─── Tree-sitter language loader ───────────────────────────────────────────────
_LANG_CACHE: Dict[str, object] = {}  # cache loaded languages


def _load_language(lang_name: str):
    """Dynamically load a tree-sitter language grammar."""
    if lang_name in _LANG_CACHE:
        return _LANG_CACHE[lang_name]

    try:
        import tree_sitter
        # tree-sitter 0.22+ style: Language from package
        pkg_map = {
            "python":      "tree_sitter_python",
            "javascript":  "tree_sitter_javascript",
            "typescript":  "tree_sitter_typescript",
            "tsx":         "tree_sitter_typescript",  # same package, diff entry
            "java":        "tree_sitter_java",
            "kotlin":      "tree_sitter_kotlin",
            "go":          "tree_sitter_go",
            "rust":        "tree_sitter_rust",
            "c":           "tree_sitter_c",
            "cpp":         "tree_sitter_cpp",
            "c_sharp":     "tree_sitter_c_sharp",
            "ruby":        "tree_sitter_ruby",
            "php":         "tree_sitter_php",
            "swift":       "tree_sitter_swift",
            "scala":       "tree_sitter_scala",
            "bash":        "tree_sitter_bash",
            "lua":         "tree_sitter_lua",
            "elixir":      "tree_sitter_elixir",
            "haskell":     "tree_sitter_haskell",
            "ocaml":       "tree_sitter_ocaml",
            "html":        "tree_sitter_html",
            "markdown":    "tree_sitter_markdown",
            "toml":        "tree_sitter_toml",
        }

        pkg_name = pkg_map.get(lang_name)
        if not pkg_name:
            return None

        pkg = __import__(pkg_name)

        # TSX needs special attr
        if lang_name == "tsx":
            lang_func = getattr(pkg, "language_tsx", None) or getattr(pkg, "tsx", None)
        else:
            lang_func = (
                getattr(pkg, "language", None)
                or getattr(pkg, f"language_{lang_name}", None)
            )

        if lang_func is None:
            return None

        # tree-sitter 0.22+ uses Language(func())
        if callable(lang_func):
            raw = lang_func()
        else:
            raw = lang_func

        lang = tree_sitter.Language(raw)
        _LANG_CACHE[lang_name] = lang
        return lang

    except Exception:
        _LANG_CACHE[lang_name] = None  # don't retry
        return None


# ─── Core extractor ────────────────────────────────────────────────────────────
class TreeSitterExtractor:
    """
    Walks a tree-sitter parse tree and extracts functions / classes / imports.
    Uses the LANG_QUERIES config — no hardcoded grammars.
    """

    def __init__(self, lang_name: str, file_path: str):
        self.lang_name = lang_name
        self.file_path = file_path
        self.config = LANG_QUERIES.get(lang_name, {
            "function_types": [],
            "class_types": [],
            "import_types": [],
        })

    def extract(self, src: bytes) -> ParsedFile:
        result = ParsedFile(path=self.file_path, language=self.lang_name)

        lang = _load_language(self.lang_name)
        if lang is None:
            # Grammar not installed — return empty but don't crash
            return result

        try:
            import tree_sitter
            parser = tree_sitter.Parser(lang)
            tree = parser.parse(src)
        except Exception:
            return result

        self._walk(tree.root_node, src, result, current_class=None)
        return result

    def _walk(self, node, src: bytes, result: ParsedFile, current_class: Optional[str]):
        node_type = node.type

        # ── Class / Struct / Interface ─────────────────────────────────────
        if node_type in self.config.get("class_types", []):
            name = _child_text(node, "name", src) or "<anonymous>"
            cls = ClassInfo(
                name=name,
                file_path=self.file_path,
                line_no=node.start_point[0] + 1,
            )
            # Collect method names from children
            for child in node.children:
                if child.type in self.config.get("function_types", []):
                    method_name = _child_text(child, "name", src)
                    if method_name:
                        cls.methods.append(method_name)
            result.classes.append(cls)

            # Recurse inside class body
            for child in node.children:
                self._walk(child, src, result, current_class=name)
            return  # don't double-recurse

        # ── Function / Method ──────────────────────────────────────────────
        if node_type in self.config.get("function_types", []):
            name = _child_text(node, "name", src)

            # JS/TS arrow & anonymous functions: naam parent node se lo
            # Pattern 1: const foo = () => {}  → parent: variable_declarator
            # Pattern 2: exports.foo = () => {} → parent: assignment_expression
            # Pattern 3: { foo: () => {} }      → parent: pair (object property)
            if not name and node_type in ("arrow_function", "function"):
                parent = node.parent
                if parent is not None:
                    if parent.type == "variable_declarator":
                        name = _child_text(parent, "name", src)
                    elif parent.type == "assignment_expression":
                        # exports.foo — sirf property name lo
                        left = parent.child_by_field_name("left")
                        if left is not None:
                            left_text = _text(left, src)
                            # "exports.foo" → "foo", "module.exports" → skip
                            if "." in left_text and "module.exports" not in left_text:
                                name = left_text.split(".")[-1]
                            elif "." not in left_text:
                                name = left_text
                    elif parent.type == "pair":
                        key = parent.child_by_field_name("key")
                        if key is not None:
                            name = _text(key, src)

            name = name or "<lambda>"
            params = self._extract_params(node, src)
            func = Function(
                name=name,
                file_path=self.file_path,
                line_no=node.start_point[0] + 1,
                class_name=current_class,
                params=params,
            )
            result.functions.append(func)
            # Still recurse (nested functions / lambdas)
            for child in node.children:
                self._walk(child, src, result, current_class=current_class)
            return

        # ── Imports ────────────────────────────────────────────────────────
        if node_type in self.config.get("import_types", []):
            # call_expression filter: sirf require('...') lo, baaki ignore
            if node_type == "call_expression":
                func_child = node.child_by_field_name("function")
                if func_child is None or _text(func_child, src) != "require":
                    # require nahi hai — recurse karo (koi aur function call ho sakta hai)
                    for child in node.children:
                        self._walk(child, src, result, current_class=current_class)
                    return
                # require('path') — argument nikalo
                args = node.child_by_field_name("arguments")
                if args is not None:
                    for arg in args.children:
                        if arg.type in ("string", "template_string"):
                            module_text = _text(arg, src).strip("'\"` \t")
                            if module_text:
                                result.imports.append(ImportInfo(
                                    file_path=self.file_path,
                                    module=module_text[:200],
                                ))
                return  # require processed — recurse mat karo

            module_text = _text(node, src).strip()
            imp = ImportInfo(
                file_path=self.file_path,
                module=module_text[:200],  # truncate huge paths
            )
            result.imports.append(imp)
            # Don't recurse imports (avoids duplicate children)
            return

        # ── Default: recurse ───────────────────────────────────────────────
        for child in node.children:
            self._walk(child, src, result, current_class=current_class)

    def _extract_params(self, func_node, src: bytes) -> List[str]:
        """Extract parameter names from a function node."""
        params = []
        for child in func_node.children:
            if "parameters" in child.type or "params" in child.type:
                for param in child.children:
                    if param.type in ("identifier", "required_parameter",
                                      "optional_parameter", "parameter"):
                        # Get the identifier inside complex param nodes
                        ident = None
                        for sub in param.children:
                            if sub.type == "identifier":
                                ident = _text(sub, src)
                                break
                        params.append(ident or _text(param, src))
        return [p.strip() for p in params if p.strip() and len(p) < 64]


# ─── Public API ────────────────────────────────────────────────────────────────
class UniversalParser:
    """
    Drop-in replacement / companion to RepositoryParser.
    
    Usage:
        parser = UniversalParser()
        
        # Parse single file
        result = parser.parse_file("path/to/file.go")
        
        # Parse whole repo (all languages)
        all_files = parser.parse_repository("/path/to/repo")
        
        # Get compatible FileInfo (for DependencyGraphBuilder)
        file_info = result.to_file_info()
    """

    def __init__(self, exclude_dirs: Set[str] = None):
        self.exclude_dirs = exclude_dirs or DEFAULT_EXCLUDE_DIRS
        # Import existing Python parser for .py files
        from .code_parser import RepositoryParser as PythonRepoParser
        self._py_repo_parser_class = PythonRepoParser

    # ── Single file ────────────────────────────────────────────────────────
    def parse_file(self, file_path: str) -> ParsedFile:
        """Parse a single file. Python uses ast; others use tree-sitter."""
        ext = Path(file_path).suffix.lower()
        
        if ext in PYTHON_EXTENSIONS:
            return self._parse_python_file(file_path)
        
        lang = EXTENSION_MAP.get(ext)
        if lang is None:
            return ParsedFile(path=file_path, language="unknown")
        
        try:
            with open(file_path, "rb") as f:
                src = f.read()
        except (OSError, IOError):
            return ParsedFile(path=file_path, language=lang)
        
        extractor = TreeSitterExtractor(lang, file_path)
        return extractor.extract(src)

    def _parse_python_file(self, file_path: str) -> ParsedFile:
        """Use existing ast-based parser for Python."""
        from .code_parser import CodeParser
        import ast

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                src = f.read()
            tree = ast.parse(src)
            cp = CodeParser(file_path)
            cp.visit(tree)
            pf = ParsedFile(
                path=file_path,
                language="python",
                functions=cp.functions,
                classes=cp.classes,
                imports=cp.imports,
            )
            return pf
        except Exception:
            return ParsedFile(path=file_path, language="python")

    # ── Full repository ────────────────────────────────────────────────────
    def parse_repository(
        self,
        repo_path: str,
        languages: Optional[List[str]] = None,
    ) -> Dict[str, ParsedFile]:
        """
        Parse all supported files in a repository.
        
        Args:
            repo_path: Root directory of the repo
            languages: Optional whitelist e.g. ["python", "javascript"]
                       If None, all supported languages are parsed.
        
        Returns:
            Dict[relative_path → ParsedFile]
        """
        repo = Path(repo_path)
        results: Dict[str, ParsedFile] = {}
        
        all_extensions = set(EXTENSION_MAP.keys()) | PYTHON_EXTENSIONS

        for file_path in repo.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip excluded dirs
            if any(excl in file_path.parts for excl in self.exclude_dirs):
                continue

            ext = file_path.suffix.lower()
            if ext not in all_extensions:
                continue

            lang = EXTENSION_MAP.get(ext, "python")
            if languages and lang not in languages:
                continue

            rel_path = str(file_path.relative_to(repo))

            try:
                parsed = self.parse_file(str(file_path))
                parsed.path = rel_path  # store relative path
                results[rel_path] = parsed
            except Exception as e:
                print(f"[UniversalParser] skipping {rel_path}: {e}")

        return results

    # ── Utilities ──────────────────────────────────────────────────────────
    def get_supported_languages(self) -> List[str]:
        """Return list of all supported language names."""
        langs = set(EXTENSION_MAP.values())
        langs.add("python")
        return sorted(langs)

    def get_supported_extensions(self) -> List[str]:
        """Return all file extensions this parser handles."""
        return sorted(set(EXTENSION_MAP.keys()) | PYTHON_EXTENSIONS)

    def languages_available(self) -> Dict[str, bool]:
        """
        Check which language grammars are actually installed.
        Useful for debugging / healthcheck endpoints.
        """
        result = {"python": True}  # always available via ast
        for lang in set(EXTENSION_MAP.values()):
            if lang == "python":
                continue
            result[lang] = _load_language(lang) is not None
        return result