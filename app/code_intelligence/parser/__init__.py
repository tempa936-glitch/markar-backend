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

from .deep_ast_analyzer import (
    DeepRepositoryAnalyzer,
    DeepFunctionAnalysis,
    PythonDeepAnalyzer,
    PythonDeepFileAnalyzer,
    TSDeepFileAnalyzer,
)

__all__ = [
    "CodeParser",
    "RepositoryParser",
    "Function",
    "ClassInfo",
    "ImportInfo",
    "FileInfo",
    "UniversalParser",
    "ParsedFile",
    "EXTENSION_MAP",
    "LANG_QUERIES",
    "DeepRepositoryAnalyzer",
    "DeepFunctionAnalysis",
    "PythonDeepAnalyzer",
    "PythonDeepFileAnalyzer",
    "TSDeepFileAnalyzer",
]