"""Parser module — AST-based Python + Tree-sitter multi-language parsing."""

from .code_parser import (
    CodeParser,
    RepositoryParser,
    Function,
    ClassInfo,
    ImportInfo,
    FileInfo,
)

from .universal_parser import (
    UniversalParser,
    ParsedFile,
    EXTENSION_MAP,
    LANG_QUERIES,
)

__all__ = [
    # Original (Python-only)
    "CodeParser",
    "RepositoryParser",
    "Function",
    "ClassInfo",
    "ImportInfo",
    "FileInfo",
    # New (multi-language)
    "UniversalParser",
    "ParsedFile",
    "EXTENSION_MAP",
    "LANG_QUERIES",
]
