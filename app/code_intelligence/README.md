# Code Intelligence Layer - Architectural Brain

A powerful AST-based code analysis system that builds structural graphs, detects blast radius, and enables intelligent impact analysis. Think of it as a "codebase brain" that understands relationships and architecture.

## 🎯 What It Does

### Real-World Example

When you change a function, the system tells you:

```
✅ Which 14 places call this function
✅ What APIs will break
✅ Which tests will fail
✅ Which microservices are impacted
✅ Safe migration plan with phases
```

## 🏗️ Architecture

### Phase 1: Core System

```
Repository → AST Parser → Dependency Graph → Graph Store
```

- **AST Parser**: Extracts file → class → function structure
- **Dependency Graph**: Builds call relationships and imports
- **Output**: Structured index of your entire codebase

### Phase 2: Graph Layer

```
Store file/class/function relationships
Query capabilities:
- "What breaks if I change X?"
- "What does X depend on?"
- "Call path from A to B?"
- "Circular dependencies?"
```

### Phase 3: Agent Layer

```
Single powerful "Impact Analysis Agent" that:
- Analyzes code changes
- Detects blast radius
- Suggests refactoring
- Plans safe migrations
- Finds root causes
```

### Phase 4: Orchestration

```
LangGraph-based workflows:
- On code change
- Pre-deployment checks
- Code review guidance
```

## 📁 Module Structure

```
code_intelligence/
├── parser.py              # AST parsing
├── graph_builder.py       # Dependency graph
├── graph_store.py         # Storage & queries
├── orchestrator.py        # Main orchestrator
├── agents/
│   ├── __init__.py
│   └── impact_agent.py    # Impact analysis agent
├── routes.py              # FastAPI endpoints
└── __init__.py
```

## 🚀 Quick Start

### 1. Initialize System

```python
from app.code_intelligence import CodeIntelligenceOrchestrator

orchestrator = CodeIntelligenceOrchestrator(repo_path="/path/to/repo")
result = orchestrator.initialize()
```

**Output:**

```
🚀 Initializing Code Intelligence for /path/to/repo
📍 Step 1: Parsing repository...
   ✓ Parsed 42 files
📍 Step 2: Building dependency graph...
   ✓ Built graph with 1,234 nodes
📍 Step 3: Storing graph...
   ✓ Graph stored successfully

📊 System Statistics:
   Files: 42
   Classes: 128
   Functions: 856
   Circular Dependencies: 2
```

### 2. Query for Impact Analysis

```python
from app.code_intelligence import QueryType

# Analyze what breaks if we change a function
impact = orchestrator.query(
    QueryType.IMPACT_ANALYSIS,
    target="app/services/user.services.py"
)

# Returns:
{
  'severity': 'high',
  'risk_level': 'HIGH - Large blast radius',
  'affected_count': 18,
  'affected_files': ['routes/auth.py', 'routes/user.py', ...],
  'affected_functions': ['login', 'register', ...],
  'recommendations': [
    '🔴 Use feature flag for gradual rollout',
    '🔴 Add comprehensive integration tests',
    ...
  ]
}
```

### 3. Use via FastAPI

**Initialize:**

```bash
POST /api/code-intelligence/initialize
{
  "repo_path": "/path/to/repo"
}
```

**Analyze Impact:**

```bash
POST /api/code-intelligence/analyze/impact
{
  "target": "app/main.py"
}
```

**Get Dependencies:**

```bash
POST /api/code-intelligence/analyze/dependencies
{
  "target": "app/services/user.py"
}
```

**Find Root Cause:**

```bash
POST /api/code-intelligence/analyze/root-cause
{
  "failing_node": "func:login@app/services/user.py"
}
```

**Plan API Migration:**

```bash
POST /api/code-intelligence/plan/api-migration
{
  "target": "func:get_user@app/services/user.py",
  "description": "Change signature from get_user(id) to get_user(id, include_permissions=True)"
}
```

**Multi-Change Analysis:**

```bash
POST /api/code-intelligence/analyze/multi-change
{
  "changes": [
    "app/services/user.py",
    "app/routes/auth.py"
  ]
}
```

## 📊 Query Types

### 1. Impact Analysis

**What to change → What breaks**

```python
orchestrator.query(QueryType.IMPACT_ANALYSIS, target="function_name")
```

Returns: blast radius, affected nodes, severity, recommendations

### 2. Dependency Analysis

**What does this depend on?**

```python
orchestrator.query(QueryType.DEPENDENCY_ANALYSIS, target="function_name")
```

Returns: direct & transitive dependencies

### 3. Root Cause Analysis

**Why is this failing?**

```python
orchestrator.query(QueryType.ROOT_CAUSE, failing_node="function_name")
```

Returns: potential causes, debug steps

### 4. Refactoring Suggestions

**How to reduce coupling?**

```python
orchestrator.query(QueryType.REFACTORING, target="function_name")
```

Returns: extraction, DI, interface patterns, feature flags

### 5. API Migration Planning

**Safe API changes with phases**

```python
orchestrator.query(
    QueryType.API_MIGRATION,
    target="function_name",
    description="Change description"
)
```

Returns: 3-phase migration plan with checkpoints

### 6. Multi-Change Analysis

**How do multiple changes interact?**

```python
orchestrator.query(
    QueryType.MULTI_CHANGE,
    changes=["file1.py", "file2.py"]
)
```

Returns: cross-impacts, conflicts, warnings

## 🔍 Search & Browse

### Search Nodes

```bash
GET /api/code-intelligence/search?query=login&node_type=function
```

### Get File Structure

```bash
GET /api/code-intelligence/file-structure?file_path=app/main.py
```

### Get System Stats

```bash
GET /api/code-intelligence/stats
```

## 🔄 Workflows

### On Code Change

```python
from app.code_intelligence import WorkflowExecutor

executor = WorkflowExecutor(orchestrator)
result = executor.on_code_change(["app/services/user.py", "app/routes/auth.py"])
```

### Pre-Deployment Check

```python
result = executor.on_deployment(version="1.2.0")
# Checks for circular deps, gives deployment recommendations
```

### Code Review Guidance

```python
result = executor.on_code_review(
    pr_description="Add login feature",
    changed_files=["app/services/user.py"]
)
```

## 📈 Output Examples

### Impact Analysis - HIGH Risk

```
Target: app/services/user.py

Severity: HIGH
Risk Level: HIGH - Large blast radius

Affected: 18 nodes across 6 files
- 12 functions
- 4 classes
- 6 files

Recommendations:
  🔴 Use feature flag for gradual rollout
  🔴 Add comprehensive integration tests
  🔴 Plan staged deployment across services
  🔴 Have rollback plan ready
  📋 Break change into smaller PRs
  🔧 Consider refactoring to reduce coupling

Migration Plan:
  Step 1: Create feature branch (5 min)
  Step 2: Implement change (varies)
  Step 3: Update unit tests (30 min)
  ...
  Total: 7 hours
```

### Refactoring Suggestions

```
Function: app/services/user.py::get_user

Current Impact: high
Current Dependencies: 8

Suggestions:
  1. Extract Module
     - Move logic to separate module
     - Reduces blast radius by isolating changes
     - Difficulty: MEDIUM

  2. Dependency Injection
     - Inject dependencies instead of importing
     - Decouples modules and eases testing
     - Difficulty: MEDIUM

  3. Create Interface/Protocol
     - Abstract interface for dependent code
     - Multiple implementations with less coupling
     - Difficulty: MEDIUM
```

### API Migration Plan

```
Change: Update get_user() API signature

Phase 1: Add new API (backward compatible)
  - Implement new function/method alongside old one
  - Keep old API working
  - Add deprecation warning
  - Duration: Sprint 1

Phase 2: Migrate 14 callers to new API
  - Update callers in priority order
  - Run tests after each migration
  - Deploy in stages
  - Monitor error rates
  - Duration: Sprint 2-3

Phase 3: Remove old API
  - Verify all callers migrated
  - Remove old function
  - Clean up deprecation warnings
  - Update documentation
  - Duration: Sprint 4
```

## 🎯 Key Features

✅ **Full Codebase Analysis** - Parses entire repository in seconds
✅ **Structural Indexing** - Files, classes, functions, imports
✅ **Call Graph** - Who calls whom, complete relationships
✅ **Blast Radius Detection** - "If I change X, Y breaks"
✅ **Smart Severity Levels** - Isolated, Low, Medium, High, Critical
✅ **Migration Planning** - Phase-by-phase safe migration strategies
✅ **Root Cause Analysis** - Debug failing nodes
✅ **Refactoring Suggestions** - Reduce coupling intelligently
✅ **Circular Dependency Detection** - Prevent initialization issues
✅ **Multi-Change Analysis** - Interactions between related changes
✅ **Workflow Integration** - On-code-change, pre-deploy, code-review

## 🔌 Integration Points

### FastAPI

All features exposed via REST endpoints under `/api/code-intelligence/`

### Python API

Direct use of `CodeIntelligenceOrchestrator` class

### Workflows

Use `WorkflowExecutor` for structured analysis workflows

## 💾 Storage

Default: JSON files in `.code_graph/` directory

- `graph.json` - Complete graph structure
- `metadata.json` - Statistics and timestamps

**Future**: Upgrade to Neo4j for advanced queries

## 🚫 What It DOESN'T Do

❌ Execute code
❌ Modify files (analysis only)
❌ Track runtime state
❌ Analyze external dependencies deeply

---

**Status**: Production Ready  
**Version**: 1.0  
**Language**: Python 3.14+
