"""
Impact Analysis Agent - core reasoning engine.

Single powerful agent that:
- Analyzes code changes
- Detects blast radius
- Suggests safe migration paths
- Provides root cause analysis
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum


class ImpactSeverity(str, Enum):
    """Impact severity levels."""
    ISOLATED = "isolated"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ChangeImpact:
    """Result of impact analysis."""
    change: str
    affected_nodes: List[str]
    affected_files: Set[str]
    affected_functions: Set[str]
    affected_classes: Set[str]
    severity: ImpactSeverity
    risk_level: str
    recommendations: List[str]
    migration_plan: Optional[Dict] = None
    circular_deps: List[List[str]] = None


class ImpactAnalysisAgent:
    """Core agent for impact analysis."""
    
    def __init__(self, graph_store):
        """Initialize with graph store."""
        self.store = graph_store
        self.analysis_history: List[Dict] = []
    
    def analyze_function_change(self, function_id: str) -> ChangeImpact:
        """Analyze impact of changing a function."""
        
        # Get blast radius
        impact = self.store.query_impact(function_id)
        
        if not impact:
            return ChangeImpact(
                change=function_id,
                affected_nodes=[],
                affected_files=set(),
                affected_functions=set(),
                affected_classes=set(),
                severity=ImpactSeverity.ISOLATED,
                risk_level="NONE",
                recommendations=[]
            )
        
        affected_nodes = impact.get('all_affected', [])
        affected_files, affected_functions, affected_classes = self._categorize_nodes(affected_nodes)
        
        # Determine severity
        severity = ImpactSeverity(impact.get('impact_level', 'low').lower())
        risk_level = self._assess_risk(affected_nodes, affected_files)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            function_id, affected_nodes, severity, affected_files
        )
        
        # Create migration plan
        migration_plan = self._create_migration_plan(
            function_id, affected_nodes, recommendations
        )
        
        # Check for circular deps
        circular_deps = self.store.query_circular_deps()
        
        result = ChangeImpact(
            change=function_id,
            affected_nodes=affected_nodes,
            affected_files=affected_files,
            affected_functions=affected_functions,
            affected_classes=affected_classes,
            severity=severity,
            risk_level=risk_level,
            recommendations=recommendations,
            migration_plan=migration_plan,
            circular_deps=circular_deps
        )
        
        # Store in history
        self._record_analysis(function_id, result)
        
        return result
    
    def analyze_file_change(self, file_path: str) -> ChangeImpact:
        """Analyze impact of changing an entire file."""
        file_id = f"file:{file_path}"
        return self.analyze_function_change(file_id)
    
    def analyze_multiple_changes(self, changes: List[str]) -> Dict:
        """Analyze impact of multiple related changes."""
        impacts = {}
        all_affected = set()
        max_severity = ImpactSeverity.ISOLATED
        
        for change in changes:
            impact = self.analyze_function_change(change)
            impacts[change] = impact
            all_affected.update(impact.affected_nodes)
            
            # Update max severity
            if self._severity_score(impact.severity) > self._severity_score(max_severity):
                max_severity = impact.severity
        
        # Check for cross-impacts
        cross_impacts = self._analyze_cross_impacts(changes, impacts)
        
        return {
            'changes': changes,
            'individual_impacts': impacts,
            'combined_affected_nodes': list(all_affected),
            'overall_severity': max_severity.value,
            'cross_impacts': cross_impacts,
            'warning': self._generate_cross_impact_warnings(cross_impacts)
        }
    
    def suggest_refactoring(self, function_id: str) -> Dict:
        """Suggest refactoring options to reduce blast radius."""
        impact = self.analyze_function_change(function_id)
        
        # Analyze dependencies
        deps = self.store.query_dependencies(function_id)
        
        suggestions = []
        
        # Suggestion 1: Extract logic
        if len(impact.affected_nodes) > 10:
            suggestions.append({
                'name': 'Extract Module',
                'description': 'Move logic to separate module to reduce coupling',
                'benefit': 'Reduces blast radius by isolating changes',
                'difficulty': 'MEDIUM'
            })
        
        # Suggestion 2: Dependency Injection
        if len(deps.get('direct_deps', [])) > 5:
            suggestions.append({
                'name': 'Dependency Injection',
                'description': 'Inject dependencies instead of importing directly',
                'benefit': 'Decouples modules and makes testing easier',
                'difficulty': 'MEDIUM'
            })
        
        # Suggestion 3: Interface Abstraction
        if any(n.type == 'class' for n in [self.store.nodes.get(nid) for nid in impact.affected_nodes] if n):
            suggestions.append({
                'name': 'Create Interface/Protocol',
                'description': 'Define abstract interface for dependent code',
                'benefit': 'Allows multiple implementations with less coupling',
                'difficulty': 'MEDIUM'
            })
        
        # Suggestion 4: Feature Flag
        if impact.severity in [ImpactSeverity.HIGH, ImpactSeverity.CRITICAL]:
            suggestions.append({
                'name': 'Feature Flag',
                'description': 'Add feature flag to gradual rollout',
                'benefit': 'Allows safe rollback if issues arise',
                'difficulty': 'LOW'
            })
        
        return {
            'function': function_id,
            'current_impact': impact.severity.value,
            'refactoring_suggestions': suggestions,
            'current_dependencies': deps
        }
    
    def find_root_cause(self, failing_node: str) -> Dict:
        """Analyze what might cause a node to fail."""
        # Get all dependencies
        deps = self.store.query_dependencies(failing_node)
        
        # Get all that call this node
        impact = self.store.query_impact(failing_node)
        
        root_causes = {
            'direct_causes': [],
            'indirect_causes': [],
            'environmental_factors': []
        }
        
        # Analyze dependencies for potential issues
        for dep_id in deps.get('direct_deps', []):
            node = self.store.nodes.get(dep_id)
            if node:
                root_causes['direct_causes'].append({
                    'node': dep_id,
                    'type': node.type,
                    'reason': f'Failed dependency: {node.name}'
                })
        
        # Check for circular dependencies
        circular_deps = self.store.query_circular_deps()
        for cycle in circular_deps:
            if failing_node in cycle:
                root_causes['indirect_causes'].append({
                    'issue': 'Circular dependency detected',
                    'cycle': cycle,
                    'impact': 'Can cause initialization or import issues'
                })
        
        return {
            'failing_node': failing_node,
            'root_causes': root_causes,
            'next_steps': self._suggest_debug_steps(failing_node),
            'related_nodes': impact.get('all_affected', [])[:10]
        }
    
    def plan_api_change(self, function_id: str, change_description: str) -> Dict:
        """Plan safe API change with migration strategy."""
        impact = self.analyze_function_change(function_id)
        
        plan = {
            'api_change': change_description,
            'target_function': function_id,
            'affected_count': len(impact.affected_nodes),
            'phases': []
        }
        
        # Phase 1: Add new API
        plan['phases'].append({
            'phase': 1,
            'name': 'Add new API (backward compatible)',
            'steps': [
                'Implement new function/method alongside old one',
                'Keep old API working',
                'Add deprecation warning to old API',
                'Update tests to cover both'
            ],
            'duration': 'Sprint 1'
        })
        
        # Phase 2: Migrate callers
        callers = impact.get('all_affected', [])[:20]  # Limit to 20
        plan['phases'].append({
            'phase': 2,
            'name': f'Migrate {len(callers)} callers to new API',
            'steps': [
                f'Update callers in priority order',
                'Run tests after each migration',
                'Deploy in stages',
                'Monitor error rates'
            ],
            'callers': callers,
            'duration': 'Sprint 2-3'
        })
        
        # Phase 3: Remove old API
        plan['phases'].append({
            'phase': 3,
            'name': 'Remove old API',
            'steps': [
                'Verify all callers migrated',
                'Remove old function/method',
                'Clean up deprecation warnings',
                'Update documentation'
            ],
            'duration': 'Sprint 4'
        })
        
        plan['risks'] = [
            f'High impact: Affects {len(impact.affected_nodes)} nodes',
            'Risk of breaking external consumers'
        ] if impact.severity in [ImpactSeverity.CRITICAL, ImpactSeverity.HIGH] else []
        
        return plan
    
    # Helper methods
    
    def _categorize_nodes(self, node_ids: List[str]) -> tuple:
        """Categorize nodes by type."""
        files = set()
        functions = set()
        classes = set()
        
        for node_id in node_ids:
            node = self.store.nodes.get(node_id)
            if node:
                if node.type == 'file':
                    files.add(node.name)
                elif node.type == 'function':
                    functions.add(node.name)
                elif node.type == 'class':
                    classes.add(node.name)
        
        return files, functions, classes
    
    def _assess_risk(self, affected_nodes: List[str], affected_files: Set[str]) -> str:
        """Assess risk level."""
        if len(affected_files) > 10:
            return "CRITICAL - Changes span many files"
        elif len(affected_nodes) > 20:
            return "HIGH - Large blast radius"
        elif len(affected_nodes) > 5:
            return "MEDIUM - Multiple callsites"
        else:
            return "LOW - Limited impact"
    
    def _generate_recommendations(self, function_id: str, affected_nodes: List[str],
                                 severity: ImpactSeverity, affected_files: Set[str]) -> List[str]:
        """Generate smart recommendations."""
        recs = []
        
        if severity in [ImpactSeverity.CRITICAL, ImpactSeverity.HIGH]:
            recs.append("🔴 Use feature flag for gradual rollout")
            recs.append("🔴 Add comprehensive integration tests")
            recs.append("🔴 Plan staged deployment across services")
            recs.append("🔴 Have rollback plan ready")
        
        if len(affected_files) > 5:
            recs.append("📋 Break change into smaller PRs")
            recs.append("📋 Migrate callers incrementally")
        
        if len(affected_nodes) > 15:
            recs.append("🔧 Consider refactoring to reduce coupling")
            recs.append("🔧 Use interface/protocol abstraction")
        
        recs.append("✅ Run full test suite before merging")
        recs.append("✅ Update documentation and changelog")
        
        return recs
    
    def _create_migration_plan(self, function_id: str, affected_nodes: List[str],
                              recommendations: List[str]) -> Dict:
        """Create step-by-step migration plan."""
        return {
            'steps': [
                {'step': 1, 'action': 'Create feature branch', 'time': '5 min'},
                {'step': 2, 'action': 'Implement change', 'time': 'varies'},
                {'step': 3, 'action': 'Update unit tests', 'time': '30 min'},
                {'step': 4, 'action': 'Run test suite', 'time': '10 min'},
                {'step': 5, 'action': f'Update {len(affected_nodes)} affected nodes', 'time': '2 hours'},
                {'step': 6, 'action': 'Code review', 'time': '1 hour'},
                {'step': 7, 'action': 'Integration testing', 'time': '1 hour'},
                {'step': 8, 'action': 'Staged deployment', 'time': '2 hours'},
            ],
            'estimated_total': '7 hours' if len(affected_nodes) > 10 else '3 hours',
            'checkpoints': [
                'All tests passing',
                'Zero breaking changes',
                'Documentation updated',
                'Monitoring in place'
            ]
        }
    
    def _severity_score(self, severity: ImpactSeverity) -> int:
        """Convert severity to numeric score."""
        scores = {
            ImpactSeverity.ISOLATED: 0,
            ImpactSeverity.LOW: 1,
            ImpactSeverity.MEDIUM: 2,
            ImpactSeverity.HIGH: 3,
            ImpactSeverity.CRITICAL: 4
        }
        return scores.get(severity, 0)
    
    def _analyze_cross_impacts(self, changes: List[str], impacts: Dict) -> Dict:
        """Analyze how changes affect each other."""
        cross_impact = {}
        
        for i, change1 in enumerate(changes):
            for change2 in changes[i+1:]:
                impact1 = impacts[change1]
                impact2 = impacts[change2]
                
                # Check if they affect common nodes
                common_affected = set(impact1.affected_nodes) & set(impact2.affected_nodes)
                
                if common_affected:
                    cross_impact[f"{change1} <-> {change2}"] = {
                        'common_affected': list(common_affected),
                        'warning': 'These changes conflict - test interaction effects'
                    }
        
        return cross_impact
    
    def _generate_cross_impact_warnings(self, cross_impacts: Dict) -> List[str]:
        """Generate warnings about cross-impacts."""
        if not cross_impacts:
            return []
        
        return [
            f"⚠️ {len(cross_impacts)} potential conflicts between changes",
            "⚠️ Test interaction effects thoroughly",
            "⚠️ Deploy as single unit or verify compatibility"
        ]
    
    def _suggest_debug_steps(self, failing_node: str) -> List[str]:
        """Suggest debug steps for investigating failure."""
        return [
            f'1. Check logs for {failing_node}',
            '2. Verify all dependencies are available',
            '3. Test dependencies in isolation',
            '4. Check for circular dependencies',
            '5. Verify imports and module paths',
            '6. Add debug logging to failing node',
            '7. Test with simpler inputs'
        ]
    
    def _record_analysis(self, target: str, impact: ChangeImpact):
        """Record analysis in history."""
        self.analysis_history.append({
            'timestamp': __import__('datetime').datetime.now().isoformat(),
            'target': target,
            'severity': impact.severity.value,
            'affected_count': len(impact.affected_nodes)
        })
