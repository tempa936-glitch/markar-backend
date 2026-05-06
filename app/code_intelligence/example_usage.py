"""
Example usage of Code Intelligence System.

This demonstrates all major capabilities.
"""

from app.code_intelligence import (
    CodeIntelligenceOrchestrator,
    QueryType,
    WorkflowExecutor
)


def example_basic_initialization():
    """Example 1: Initialize system."""
    print("\n" + "="*60)
    print("EXAMPLE 1: Initialize System")
    print("="*60)
    
    orchestrator = CodeIntelligenceOrchestrator(".")
    result = orchestrator.initialize()
    
    print(f"\nInitialized! Found {result['nodes']} nodes")
    print(f"Statistics: {result['stats']}")


def example_impact_analysis():
    """Example 2: Analyze impact of change."""
    print("\n" + "="*60)
    print("EXAMPLE 2: Impact Analysis")
    print("="*60)
    
    orchestrator = CodeIntelligenceOrchestrator(".")
    if not orchestrator.initialized:
        orchestrator.initialize()
    
    # Analyze a file
    result = orchestrator.query(
        QueryType.IMPACT_ANALYSIS,
        target="app/main.py"
    )
    
    print(f"\nTarget: {result.get('target')}")
    print(f"Severity: {result.get('severity')}")
    print(f"Risk Level: {result.get('risk_level')}")
    print(f"Affected Nodes: {result.get('affected_count')}")
    print(f"Affected Files: {result.get('affected_files')}")
    
    print("\nRecommendations:")
    for rec in result.get('recommendations', []):
        print(f"  • {rec}")


def example_dependency_analysis():
    """Example 3: Analyze dependencies."""
    print("\n" + "="*60)
    print("EXAMPLE 3: Dependency Analysis")
    print("="*60)
    
    orchestrator = CodeIntelligenceOrchestrator(".")
    if not orchestrator.initialized:
        orchestrator.initialize()
    
    result = orchestrator.query(
        QueryType.DEPENDENCY_ANALYSIS,
        target="app/main.py"
    )
    
    print(f"\nTarget: {result.get('target')}")
    print(f"Total Dependencies: {result.get('dependency_count')}")
    print(f"\nDirect Dependencies:")
    for dep in result.get('direct_dependencies', [])[:5]:
        print(f"  • {dep}")


def example_refactoring_suggestions():
    """Example 4: Get refactoring suggestions."""
    print("\n" + "="*60)
    print("EXAMPLE 4: Refactoring Suggestions")
    print("="*60)
    
    orchestrator = CodeIntelligenceOrchestrator(".")
    if not orchestrator.initialized:
        orchestrator.initialize()
    
    result = orchestrator.query(
        QueryType.REFACTORING,
        target="app/main.py"
    )
    
    print(f"\nCurrent Impact Level: {result.get('current_impact')}")
    print(f"\nSuggestions:")
    for suggestion in result.get('refactoring_suggestions', []):
        print(f"\n  Name: {suggestion['name']}")
        print(f"  Description: {suggestion['description']}")
        print(f"  Benefit: {suggestion['benefit']}")
        print(f"  Difficulty: {suggestion['difficulty']}")


def example_api_migration_plan():
    """Example 5: Plan API migration."""
    print("\n" + "="*60)
    print("EXAMPLE 5: API Migration Planning")
    print("="*60)
    
    orchestrator = CodeIntelligenceOrchestrator(".")
    if not orchestrator.initialized:
        orchestrator.initialize()
    
    result = orchestrator.query(
        QueryType.API_MIGRATION,
        target="app/main.py",
        description="Add new parameter to API"
    )
    
    print(f"\nAPI Change: {result.get('api_change')}")
    print(f"Affected Nodes: {result.get('affected_count')}")
    
    print(f"\nMigration Phases:")
    for phase in result.get('phases', []):
        print(f"\n  Phase {phase['phase']}: {phase['name']}")
        print(f"  Duration: {phase['duration']}")
        for step in phase['steps'][:3]:
            print(f"    • {step}")


def example_multi_change_analysis():
    """Example 6: Analyze multiple related changes."""
    print("\n" + "="*60)
    print("EXAMPLE 6: Multi-Change Analysis")
    print("="*60)
    
    orchestrator = CodeIntelligenceOrchestrator(".")
    if not orchestrator.initialized:
        orchestrator.initialize()
    
    result = orchestrator.query(
        QueryType.MULTI_CHANGE,
        changes=["app/main.py", "app/core"]
    )
    
    if 'error' not in result:
        print(f"\nChanges: {result.get('changes')}")
        print(f"Overall Severity: {result.get('overall_severity')}")
        print(f"Combined Affected Nodes: {len(result.get('combined_affected_nodes', []))}")
        
        if result.get('warning'):
            print(f"\nWarnings:")
            for w in result.get('warning', []):
                print(f"  ⚠️ {w}")


def example_search_nodes():
    """Example 7: Search for nodes."""
    print("\n" + "="*60)
    print("EXAMPLE 7: Search Nodes")
    print("="*60)
    
    orchestrator = CodeIntelligenceOrchestrator(".")
    if not orchestrator.initialized:
        orchestrator.initialize()
    
    results = orchestrator.search("main", node_type="function")
    
    print(f"\nSearching for 'main' (functions only)")
    print(f"Found {len(results)} results:")
    for result in results[:5]:
        print(f"  • {result['name']} ({result['type']}) @ {result['file_path']}:{result['line_no']}")


def example_file_structure():
    """Example 8: Get file structure."""
    print("\n" + "="*60)
    print("EXAMPLE 8: File Structure")
    print("="*60)
    
    orchestrator = CodeIntelligenceOrchestrator(".")
    if not orchestrator.initialized:
        orchestrator.initialize()
    
    structure = orchestrator.get_file_structure("app/main.py")
    
    print(f"\nFile: {structure.get('file')}")
    print(f"Classes: {len(structure.get('classes', []))}")
    print(f"Functions: {len(structure.get('functions', []))}")


def example_get_stats():
    """Example 9: Get system statistics."""
    print("\n" + "="*60)
    print("EXAMPLE 9: System Statistics")
    print("="*60)
    
    orchestrator = CodeIntelligenceOrchestrator(".")
    if not orchestrator.initialized:
        orchestrator.initialize()
    
    stats = orchestrator.get_stats()
    
    print(f"\nTotal Nodes: {stats.get('total_nodes')}")
    print(f"Files: {stats.get('files')}")
    print(f"Classes: {stats.get('classes')}")
    print(f"Functions: {stats.get('functions')}")
    print(f"Avg Dependencies: {stats.get('avg_dependencies')}")
    print(f"Circular Dependencies: {stats.get('circular_deps')}")


def example_workflows():
    """Example 10: Use workflows."""
    print("\n" + "="*60)
    print("EXAMPLE 10: Workflows")
    print("="*60)
    
    orchestrator = CodeIntelligenceOrchestrator(".")
    if not orchestrator.initialized:
        orchestrator.initialize()
    
    executor = WorkflowExecutor(orchestrator)
    
    # Code change workflow
    print("\n--- On Code Change Workflow ---")
    result = executor.on_code_change(["app/main.py"])
    print(f"Severity: {result.get('consolidated_severity')}")
    
    # Pre-deployment workflow
    print("\n--- Pre-Deployment Check Workflow ---")
    result = executor.on_deployment("1.0.0")
    print(f"System Healthy: {result.get('system_healthy')}")
    print(f"Recommendations:")
    for rec in result.get('recommendations', []):
        print(f"  • {rec}")


def run_all_examples():
    """Run all examples."""
    examples = [
        example_basic_initialization,
        example_impact_analysis,
        example_dependency_analysis,
        example_refactoring_suggestions,
        example_api_migration_plan,
        example_multi_change_analysis,
        example_search_nodes,
        example_file_structure,
        example_get_stats,
        example_workflows,
    ]
    
    print("\n" + "="*60)
    print("Code Intelligence System - Examples")
    print("="*60)
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"\n❌ Error in {example.__name__}: {e}")
    
    print("\n" + "="*60)
    print("All examples completed!")
    print("="*60)


if __name__ == "__main__":
    run_all_examples()
