"""
Integration guide for Code Intelligence System in FastAPI.
"""

# Step 1: Update app/main.py to include Code Intelligence routes

"""
from fastapi import FastAPI
from app.code_intelligence.routes import router as code_intelligence_router

app = FastAPI(title="MarkarServer API")

# Include Code Intelligence routes

app.include_router(code_intelligence_router)

# Your existing routes...

"""

# Step 2: Quick integration example

"""
from fastapi import FastAPI
from app.code_intelligence import CodeIntelligenceOrchestrator, QueryType

app = FastAPI()

@app.on_event("startup")
async def startup_event(): # Initialize Code Intelligence on startup
global orchestrator
orchestrator = CodeIntelligenceOrchestrator("./app")
orchestrator.initialize()

# Step 3: Use in your routes

@app.post("/analyze-pr")
async def analyze_pr(files: List[str]):
from app.code_intelligence import WorkflowExecutor

    executor = WorkflowExecutor(orchestrator)
    result = executor.on_code_change(files)
    return result

"""

# API Endpoints Available

"""
POST /api/code-intelligence/initialize
Initialize system with repository path

POST /api/code-intelligence/analyze/impact
Analyze what breaks if you change something

POST /api/code-intelligence/analyze/dependencies
Get all dependencies of a node

POST /api/code-intelligence/analyze/root-cause
Find root cause of a failure

POST /api/code-intelligence/analyze/multi-change
Analyze how multiple changes interact

POST /api/code-intelligence/suggest/refactoring
Get refactoring suggestions to reduce coupling

POST /api/code-intelligence/plan/api-migration
Plan safe API changes with phases

GET /api/code-intelligence/search
Search for code nodes

GET /api/code-intelligence/file-structure
Get structure (classes, functions) of a file

GET /api/code-intelligence/stats
Get system statistics

GET /api/code-intelligence/visualization
Get graph for visualization

POST /api/code-intelligence/workflow/on-code-change
Workflow: Analyze changed files

POST /api/code-intelligence/workflow/pre-deployment-check
Workflow: Pre-deployment verification

POST /api/code-intelligence/workflow/code-review
Workflow: Code review guidance
"""

# Example: Real-world usage in your agents

"""
from app.code_intelligence import CodeIntelligenceOrchestrator, QueryType

def my_agent_task():
orchestrator = CodeIntelligenceOrchestrator("./app")

    # Before working on a feature, analyze impact
    impact = orchestrator.query(
        QueryType.IMPACT_ANALYSIS,
        target="app/services/user.py"
    )

    if impact['severity'] == 'critical':
        return f"WARNING: This change affects {impact['affected_count']} nodes!"

    # Get refactoring suggestions
    refactor = orchestrator.query(
        QueryType.REFACTORING,
        target="app/services/user.py"
    )

    return refactor['refactoring_suggestions']

"""

# What You Can Do Now

features = """
✅ STATIC ANALYSIS

- Parse entire codebase to AST
- Extract file → class → function hierarchy
- Find all imports and dependencies

✅ IMPACT ANALYSIS

- "If I change X, what breaks?"
- Blast radius detection
- Severity levels (Isolated, Low, Medium, High, Critical)

✅ DEPENDENCY QUERIES

- What does function/file depend on?
- Full transitive dependency chain
- Call paths between functions

✅ ROOT CAUSE ANALYSIS

- Why is this node failing?
- Potential causes from dependencies
- Debug steps

✅ REFACTORING GUIDANCE

- Extract module patterns
- Dependency injection strategies
- Interface/protocol abstraction
- Feature flag implementation

✅ SAFE MIGRATIONS

- Phase-by-phase migration plans
- Checkpoints and validation steps
- Risk assessment

✅ MULTI-CHANGE ANALYSIS

- How do multiple changes interact?
- Conflicts and side effects
- Combined blast radius

✅ CIRCULAR DEPENDENCY DETECTION

- Find initialization cycles
- Prevent import issues

✅ CODE SEARCH

- Find all functions/classes by name
- Filter by type
- Get precise locations

✅ FILE STRUCTURE BROWSING

- Classes and methods in a file
- Line numbers
- Nested structure

✅ SYSTEM STATISTICS

- Total nodes, files, classes, functions
- Average coupling
- Health metrics

✅ WORKFLOWS

- On-code-change analysis
- Pre-deployment checks
- Code review guidance
  """

print(features)

# Next Steps for Enhancement

enhancements = """
🔮 FUTURE ENHANCEMENTS

1. Neo4j Integration
   - Replace JSON with Neo4j
   - Complex graph queries
   - Performance at scale

2. LLM Integration
   - Use Claude/GPT to interpret queries
   - Natural language impact analysis
   - Smarter refactoring suggestions

3. CI/CD Integration
   - GitHub/GitLab webhooks
   - Auto-analyze PRs
   - Block risky changes

4. Runtime Integration
   - Track actual call frequencies
   - Hot path detection
   - Performance-aware impact

5. Test Correlation
   - Link tests to functions
   - Test coverage impact
   - Auto-detect test gaps

6. Monitoring Integration
   - Link to error tracking
   - Failed deployment analysis
   - Real-time issue correlation

7. Visualization Dashboard
   - Interactive graph browser
   - Impact heat maps
   - Architecture diagrams

8. VS Code Extension
   - Inline impact warnings
   - On-hover dependency info
   - Refactoring suggestions
     """

print(enhancements)
