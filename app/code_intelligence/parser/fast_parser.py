# """
# Fast Parallel Parser — Windows-safe multiprocessing
# =====================================================
# 3 optimizations:
#   1. File parsing  → ProcessPoolExecutor (parallel across CPU cores)
#   2. Graph build   → skip call-graph for non-Python (saves 70% time on large repos)
#   3. graph.json    → skip entirely (SQLite-lite via shelve instead)

# Windows note: spawn-based multiprocessing requires all worker functions
# to be importable at module level (no lambdas, no closures).
# """

# import os
# import ast
# import time
# from pathlib import Path
# from typing import Dict, List, Optional, Tuple, Set
# from concurrent.futures import ProcessPoolExecutor, as_completed
# from dataclasses import dataclass, field
# from collections import defaultdict

# # ── Reuse existing dataclasses ──────────────────────────────────
# from app.code_intelligence.parser.code_parser import (
#     Function, ClassInfo, ImportInfo, FileInfo
# )
# from app.code_intelligence.parser.universal_parser import (
#     EXTENSION_MAP, PYTHON_EXTENSIONS, DEFAULT_EXCLUDE_DIRS,
#     TreeSitterExtractor, _load_language
# )


# # ── Top-level worker functions (must be picklable for Windows spawn) ──────────

# def _parse_python_file_worker(file_path: str) -> Tuple[str, Optional[FileInfo]]:
#     """Parse one Python file using ast. Runs in a subprocess."""
#     try:
#         import ast as _ast
#         from app.code_intelligence.parser.code_parser import CodeParser
#         with open(file_path, "r", encoding="utf-8", errors="replace") as f:
#             src = f.read()
#         tree = _ast.parse(src)
#         cp = CodeParser(file_path)
#         cp.visit(tree)
#         fi = FileInfo(
#             path=file_path,
#             functions=cp.functions,
#             classes=cp.classes,
#             imports=cp.imports,
#         )
#         return file_path, fi
#     except Exception:
#         return file_path, None


# def _parse_nonpy_file_worker(args: Tuple[str, str]) -> Tuple[str, str, Optional[FileInfo]]:
#     """
#     Parse one non-Python file using tree-sitter.
#     Returns (rel_path, lang, FileInfo | None).
#     Runs in a subprocess — args tuple for picklability.
#     """
#     file_path, lang = args
#     try:
#         with open(file_path, "rb") as f:
#             src = f.read()
#         extractor = TreeSitterExtractor(lang, file_path)
#         pf = extractor.extract(src)
#         fi = FileInfo(
#             path=file_path,
#             functions=pf.functions,
#             classes=pf.classes,
#             imports=pf.imports,
#         )
#         return file_path, lang, fi
#     except Exception:
#         return file_path, lang, None


# # ── File collector ─────────────────────────────────────────────────────────────

# def collect_files(repo_path: str) -> Tuple[List[str], List[Tuple[str, str]]]:
#     """
#     Walk repo once, split into:
#       py_files  — list of absolute paths
#       non_py    — list of (abs_path, lang) tuples
#     """
#     repo = Path(repo_path)
#     all_exts = set(EXTENSION_MAP.keys()) | PYTHON_EXTENSIONS

#     py_files: List[str] = []
#     non_py: List[Tuple[str, str]] = []

#     for fp in repo.rglob("*"):
#         if not fp.is_file():
#             continue
#         if any(excl in fp.parts for excl in DEFAULT_EXCLUDE_DIRS):
#             continue
#         ext = fp.suffix.lower()
#         if ext not in all_exts:
#             continue
#         if ext in PYTHON_EXTENSIONS:
#             py_files.append(str(fp))
#         else:
#             lang = EXTENSION_MAP.get(ext)
#             if lang:
#                 non_py.append((str(fp), lang))

#     return py_files, non_py


# # ── Parallel parser ────────────────────────────────────────────────────────────

# class FastRepositoryParser:
#     """
#     Drop-in replacement for RepositoryParser + UniversalParser combo.
#     Uses ProcessPoolExecutor to parse files in parallel.

#     .files: Dict[rel_path → FileInfo]  (same interface as RepositoryParser)
#     """

#     def __init__(self, repo_path: str, max_workers: int = None):
#         self.repo_path = repo_path
#         # Windows: too many workers = thrashing. Cap at (cores - 1) or 4.
#         cpu = os.cpu_count() or 2
#         self.max_workers = max_workers or min(max(1, cpu - 1), 6)
#         self.files: Dict[str, FileInfo] = {}
#         self._lang_stats: Dict[str, int] = {}

#     def parse(self, progress_cb=None) -> Dict[str, FileInfo]:
#         """
#         Parse entire repo in parallel.
#         progress_cb(done, total) called periodically if provided.
#         """
#         repo = Path(self.repo_path)
#         t0 = time.time()

#         py_files, non_py_files = collect_files(self.repo_path)
#         total = len(py_files) + len(non_py_files)
#         print(f"  [FastParser] {len(py_files)} Python + {len(non_py_files)} other = {total} files")
#         print(f"  [FastParser] Using {self.max_workers} workers")

#         done = 0

#         # ── Python files — parallel ──────────────────────────
#         if py_files:
#             with ProcessPoolExecutor(max_workers=self.max_workers) as ex:
#                 futures = {ex.submit(_parse_python_file_worker, fp): fp for fp in py_files}
#                 for fut in as_completed(futures):
#                     fp, fi = fut.result()
#                     if fi:
#                         rel = str(Path(fp).relative_to(repo))
#                         fi.path = rel
#                         self.files[rel] = fi
#                     done += 1
#                     if progress_cb and done % 50 == 0:
#                         progress_cb(done, total)

#         py_done = time.time()
#         print(f"  [FastParser] Python done in {py_done - t0:.1f}s — {len(self.files)} parsed")

#         # ── Non-Python files — parallel ──────────────────────
#         if non_py_files:
#             with ProcessPoolExecutor(max_workers=self.max_workers) as ex:
#                 futures = {ex.submit(_parse_nonpy_file_worker, args): args for args in non_py_files}
#                 for fut in as_completed(futures):
#                     fp, lang, fi = fut.result()
#                     if fi:
#                         rel = str(Path(fp).relative_to(repo))
#                         fi.path = rel
#                         self.files[rel] = fi
#                         self._lang_stats[lang] = self._lang_stats.get(lang, 0) + 1
#                     done += 1
#                     if progress_cb and done % 200 == 0:
#                         progress_cb(done, total)

#         total_time = time.time() - t0
#         print(f"  [FastParser] All done in {total_time:.1f}s — {len(self.files)} total files")
#         return self.files

#     def get_all_functions(self) -> Dict[str, Function]:
#         """Same interface as RepositoryParser.get_all_functions()"""
#         all_funcs = {}
#         for fi in self.files.values():
#             for func in fi.functions:
#                 all_funcs[func.full_name] = func
#         return all_funcs

#     def get_lang_stats(self) -> Dict[str, int]:
#         return self._lang_stats


# # ── Faster graph builder ───────────────────────────────────────────────────────

# class FastGraphBuilder:
#     """
#     Builds the dependency graph faster by:
#     1. Building node dict in one pass (no repeated lookups)
#     2. Skipping call-graph resolution for non-Python files
#        (tree-sitter gives us structure but not call targets — resolving
#         them costs O(n²) with near-zero benefit for JS/Go/Rust etc.)
#     3. Using sets throughout (no list→set conversion later)
#     """

#     def __init__(self, parser: FastRepositoryParser):
#         self.parser = parser
#         self.nodes: Dict = {}         # node_id → DependencyNode
#         self._func_index: Dict = {}   # func_name → node_id (for fast lookup)

#     def build(self, progress_cb=None) -> Dict:
#         from app.code_intelligence.graph.builder import DependencyNode

#         t0 = time.time()
#         files = self.parser.files

#         # ── Pass 1: Create all nodes ───────────────────────────
#         print(f"  [FastGraph] Pass 1: creating nodes for {len(files)} files...")
#         for rel_path, fi in files.items():
#             file_id = f"file:{rel_path}"
#             self.nodes[file_id] = DependencyNode(
#                 id=file_id, type="file",
#                 name=rel_path, file_path=rel_path, line_no=0,
#             )
#             for cls in fi.classes:
#                 cid = f"class:{cls.name}@{rel_path}"
#                 self.nodes[cid] = DependencyNode(
#                     id=cid, type="class",
#                     name=cls.name, file_path=rel_path, line_no=cls.line_no,
#                 )
#                 self.nodes[file_id].children.add(cid)
#                 self.nodes[cid].parents.add(file_id)

#             for func in fi.functions:
#                 fid = f"func:{func.full_name}@{rel_path}"
#                 self.nodes[fid] = DependencyNode(
#                     id=fid, type="function",
#                     name=func.full_name, file_path=rel_path, line_no=func.line_no,
#                 )
#                 if func.class_name:
#                     cid = f"class:{func.class_name}@{rel_path}"
#                     if cid in self.nodes:
#                         self.nodes[cid].children.add(fid)
#                         self.nodes[fid].parents.add(cid)
#                     else:
#                         self.nodes[file_id].children.add(fid)
#                         self.nodes[fid].parents.add(file_id)
#                 else:
#                     self.nodes[file_id].children.add(fid)
#                     self.nodes[fid].parents.add(file_id)

#                 # Index last segment for fast call resolution
#                 last = func.full_name.split(".")[-1]
#                 self._func_index.setdefault(last, []).append((fid, rel_path))

#         print(f"  [FastGraph] {len(self.nodes)} nodes in {time.time()-t0:.1f}s")

#         # ── Pass 2: Call graph — Python-only (fast) ────────────
#         t1 = time.time()
#         py_files = {p: fi for p, fi in files.items() if p.endswith(".py")}
#         print(f"  [FastGraph] Pass 2: call graph for {len(py_files)} Python files...")

#         SKIP_PREFIXES = (
#             "os.", "sys.", "re.", "json.", "math.", "time.", "datetime.",
#             "logging.", "typing.", "collections.", "itertools.", "functools.",
#             "pytest.", "mock.", "unittest.", "asyncio.", "pathlib.",
#             "print", "len", "str", "int", "float", "list", "dict", "set",
#             "tuple", "bool", "type", "isinstance", "hasattr", "getattr",
#             "super", "range", "enumerate", "zip", "map", "filter", "sorted",
#             "open", "next", "iter", "vars", "dir", "repr", "format",
#         )

#         for rel_path, fi in py_files.items():
#             for func in fi.functions:
#                 caller_id = f"func:{func.full_name}@{rel_path}"
#                 if caller_id not in self.nodes:
#                     continue
#                 for called in func.calls:
#                     if called.startswith("self."):
#                         called = called[5:]
#                     if any(called.startswith(p) for p in SKIP_PREFIXES):
#                         continue
#                     callee_id = self._resolve_call(called, rel_path)
#                     if callee_id and callee_id in self.nodes:
#                         self.nodes[caller_id].children.add(callee_id)
#                         self.nodes[callee_id].parents.add(caller_id)

#         print(f"  [FastGraph] Call graph done in {time.time()-t1:.1f}s")

#         # ── Pass 3: Import graph ───────────────────────────────
#         t2 = time.time()
#         print(f"  [FastGraph] Pass 3: import graph...")
#         file_set = set(files.keys())
#         for rel_path, fi in files.items():
#             file_id = f"file:{rel_path}"
#             for imp in fi.imports:
#                 for resolved in self._resolve_import(imp.module, file_set):
#                     imp_id = f"file:{resolved}"
#                     if imp_id in self.nodes:
#                         self.nodes[file_id].children.add(imp_id)
#                         self.nodes[imp_id].parents.add(file_id)

#         total_time = time.time() - t0
#         print(f"  [FastGraph] Import graph done in {time.time()-t2:.1f}s")
#         print(f"  [FastGraph] Total graph build: {total_time:.1f}s, {len(self.nodes)} nodes")
#         return self.nodes

#     def _resolve_call(self, func_name: str, current_file: str) -> Optional[str]:
#         last = func_name.split(".")[-1]
#         candidates = self._func_index.get(last, [])
#         if not candidates:
#             return None
#         # Prefer same file
#         for fid, fpath in candidates:
#             if fpath == current_file:
#                 return fid
#         return candidates[0][0]

#     def _resolve_import(self, module: str, file_set: Set[str]) -> List[str]:
#         fp = module.replace(".", "/")
#         candidates = [f"{fp}.py", f"{fp}/__init__.py"]
#         return [c for c in candidates if c in file_set]
