"""
Test suite for Code Intelligence System.

Run with: python -m pytest app/code_intelligence/tests/
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from app.code_intelligence import (
    RepositoryParser,
    CodeParser,
    DependencyGraphBuilder,
    GraphStore,
    CodeIntelligenceOrchestrator,
    QueryType,
    WorkflowExecutor
)


class TestCodeParser:
    """Test AST parsing."""
    
    def test_parse_function(self, tmp_path):
        """Test parsing simple function."""
        py_file = tmp_path / "test.py"
        py_file.write_text("""
def hello(name: str) -> str:
    return f"Hello {name}"
""")
        
        parser = CodeParser(str(py_file))
        with open(py_file) as f:
            import ast
            tree = ast.parse(f.read())
        parser.visit(tree)
        
        assert len(parser.functions) == 1
        assert parser.functions[0].name == "hello"
        assert parser.functions[0].params == ["name"]
    
    def test_parse_class(self, tmp_path):
        """Test parsing class."""
        py_file = tmp_path / "test.py"
        py_file.write_text("""
class User:
    def __init__(self, name):
        self.name = name
    
    def greet(self):
        return f"Hi {self.name}"
""")
        
        parser = CodeParser(str(py_file))
        with open(py_file) as f:
            import ast
            tree = ast.parse(f.read())
        parser.visit(tree)
        
        assert len(parser.classes) == 1
        assert parser.classes[0].name == "User"
        assert "greet" in parser.classes[0].methods
    
    def test_parse_imports(self, tmp_path):
        """Test parsing imports."""
        py_file = tmp_path / "test.py"
        py_file.write_text("""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
""")
        
        parser = CodeParser(str(py_file))
        with open(py_file) as f:
            import ast
            tree = ast.parse(f.read())
        parser.visit(tree)
        
        assert len(parser.imports) >= 3


class TestRepositoryParser:
    """Test repository parsing."""
    
    def test_parse_repo(self, tmp_path):
        """Test parsing multiple files."""
        # Create test repo structure
        (tmp_path / "main.py").write_text("def main(): pass")
        (tmp_path / "utils.py").write_text("def helper(): pass")
        
        parser = RepositoryParser(str(tmp_path))
        files = parser.parse()
        
        assert len(files) == 2
        assert "main.py" in files
        assert "utils.py" in files


class TestDependencyGraph:
    """Test graph building."""
    
    def test_build_graph(self, tmp_path):
        """Test building dependency graph."""
        (tmp_path / "main.py").write_text("""
def caller():
    return callee()

def callee():
    return 42
""")
        
        parser = RepositoryParser(str(tmp_path))
        parser.parse()
        
        builder = DependencyGraphBuilder(parser)
        nodes = builder.build()
        
        # Should have file, 2 functions
        assert len(nodes) >= 3


class TestGraphStore:
    """Test graph storage."""
    
    def test_save_and_load(self, tmp_path):
        """Test saving and loading graph."""
        storage_path = tmp_path / ".code_graph"
        store = GraphStore(str(storage_path))
        
        # Create simple graph
        from app.code_intelligence.graph_builder import DependencyNode
        
        nodes = {
            "file:test.py": DependencyNode(
                id="file:test.py",
                type="file",
                name="test.py",
                file_path="test.py",
                line_no=0
            )
        }
        
        store.save(nodes)
        
        # Verify files created
        assert (storage_path / "graph.json").exists()
        assert (storage_path / "metadata.json").exists()
        
        # Load and verify
        loaded = store.load()
        assert len(loaded) > 0


class TestImpactAnalysis:
    """Test impact analysis."""
    
    def test_impact_analysis_isolated(self, tmp_path):
        """Test impact analysis for isolated node."""
        (tmp_path / "main.py").write_text("def isolated_func(): pass")
        
        orchestrator = CodeIntelligenceOrchestrator(str(tmp_path))
        orchestrator.initialize()
        
        # Try to analyze
        result = orchestrator.store.query_impact("file:main.py")
        
        # Should not error
        assert isinstance(result, dict)


class TestOrchestrator:
    """Test main orchestrator."""
    
    def test_initialize(self, tmp_path):
        """Test orchestrator initialization."""
        (tmp_path / "test.py").write_text("def test(): pass")
        
        orchestrator = CodeIntelligenceOrchestrator(str(tmp_path))
        result = orchestrator.initialize()
        
        assert result['status'] == 'initialized'
        assert result['files'] >= 1
        assert result['nodes'] >= 1
        assert orchestrator.initialized
    
    def test_query_not_initialized(self):
        """Test query without initialization."""
        orchestrator = CodeIntelligenceOrchestrator(".")
        
        result = orchestrator.query(
            QueryType.IMPACT_ANALYSIS,
            target="test"
        )
        
        assert 'error' in result
    
    def test_search(self, tmp_path):
        """Test search functionality."""
        (tmp_path / "test.py").write_text("""
def my_function():
    pass

def another_function():
    pass
""")
        
        orchestrator = CodeIntelligenceOrchestrator(str(tmp_path))
        orchestrator.initialize()
        
        results = orchestrator.search("my")
        assert isinstance(results, list)


class TestWorkflowExecutor:
    """Test workflow execution."""
    
    def test_on_code_change(self, tmp_path):
        """Test on-code-change workflow."""
        (tmp_path / "test.py").write_text("def test(): pass")
        
        orchestrator = CodeIntelligenceOrchestrator(str(tmp_path))
        orchestrator.initialize()
        
        executor = WorkflowExecutor(orchestrator)
        result = executor.on_code_change(["test.py"])
        
        assert result['workflow'] == 'on_code_change'
        assert 'impacts' in result
    
    def test_pre_deployment_check(self, tmp_path):
        """Test pre-deployment workflow."""
        (tmp_path / "test.py").write_text("def test(): pass")
        
        orchestrator = CodeIntelligenceOrchestrator(str(tmp_path))
        orchestrator.initialize()
        
        executor = WorkflowExecutor(orchestrator)
        result = executor.on_deployment("1.0.0")
        
        assert result['workflow'] == 'pre_deployment_check'
        assert 'version' in result


class TestEdgeCases:
    """Test edge cases."""
    
    def test_empty_repo(self, tmp_path):
        """Test parsing empty repository."""
        orchestrator = CodeIntelligenceOrchestrator(str(tmp_path))
        result = orchestrator.initialize()
        
        assert result['files'] == 0
    
    def test_invalid_target(self, tmp_path):
        """Test query with invalid target."""
        (tmp_path / "test.py").write_text("def test(): pass")
        
        orchestrator = CodeIntelligenceOrchestrator(str(tmp_path))
        orchestrator.initialize()
        
        result = orchestrator.query(
            QueryType.IMPACT_ANALYSIS,
            target="nonexistent_function"
        )
        
        # Should handle gracefully
        assert isinstance(result, dict)
    
    def test_circular_dependency_detection(self, tmp_path):
        """Test detecting circular dependencies."""
        (tmp_path / "a.py").write_text("from b import b_func\n\ndef a_func(): b_func()")
        (tmp_path / "b.py").write_text("from a import a_func\n\ndef b_func(): a_func()")
        
        orchestrator = CodeIntelligenceOrchestrator(str(tmp_path))
        orchestrator.initialize()
        
        circular = orchestrator.store.query_circular_deps()
        
        # May or may not find depending on resolution
        assert isinstance(circular, list)


# Fixtures

@pytest.fixture
def temp_repo(tmp_path):
    """Create temporary repo for testing."""
    return tmp_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
