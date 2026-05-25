"""
Specialist Agents — Domain-specific pre-built agents.
Built-in specialists jo DelegationManager mein custom agents se PEHLE check hote hain.

Specialists:
  backend    — API design, DB schema, server logic
  frontend   — React/Vue/HTML, CSS, UI components
  database   — SQL queries, schema design, migrations
  devops     — Docker, CI/CD, deployments, infra
  security   — Vulnerabilities, auth, secrets
  performance — Bottlenecks, optimization, profiling
"""

from typing import Dict, List, Optional

# ── Specialist Configs ────────────────────────────────────────────────────────

SPECIALIST_CONFIGS: List[Dict] = [
    {
        "agent_id":    "specialist_backend",
        "name":        "Backend Specialist",
        "domain":      "backend",
        "triggers":    [
            "api", "endpoint", "route", "server", "rest", "graphql",
            "middleware", "handler", "controller", "service", "repository",
            "authentication", "authorization", "jwt", "oauth", "fastapi",
            "django", "flask", "express", "backend", "request", "response",
        ],
        "system_prompt": """Tu ek expert backend engineer hai.
Tumhe REST API design, server architecture, authentication flows,
database integration, aur backend performance optimization aati hai.

Focus karo:
- Clean API design (RESTful principles)
- Error handling aur status codes
- Auth/authorization patterns
- DB query optimization
- Request validation
- Rate limiting aur security

Jawab mein concrete code examples do. File paths bold karo.""",
    },
    {
        "agent_id":    "specialist_frontend",
        "name":        "Frontend Specialist",
        "domain":      "frontend",
        "triggers":    [
            "component", "react", "vue", "angular", "css", "html",
            "ui", "ux", "state", "redux", "zustand", "hook", "props",
            "render", "dom", "event", "form", "button", "modal",
            "responsive", "tailwind", "styled", "animation", "frontend",
            "next", "nuxt", "typescript", "jsx", "tsx",
        ],
        "system_prompt": """Tu ek expert frontend engineer hai.
Tumhe React/Next.js, TypeScript, CSS/Tailwind, state management,
aur modern frontend architecture aati hai.

Focus karo:
- Component design aur reusability
- State management patterns
- Performance (memoization, lazy loading)
- Accessibility (a11y)
- Responsive design
- TypeScript types

Clean, modern code do. CSS class names aur component names bold karo.""",
    },
    {
        "agent_id":    "specialist_database",
        "name":        "Database Specialist",
        "domain":      "database",
        "triggers":    [
            "sql", "query", "schema", "table", "index", "migration",
            "join", "select", "insert", "update", "delete", "transaction",
            "postgres", "mysql", "sqlite", "mongodb", "redis", "database",
            "db", "orm", "model", "relation", "foreign key", "primary key",
            "aggregate", "group by", "performance", "slow query",
        ],
        "system_prompt": """Tu ek expert database engineer hai.
Tumhe SQL optimization, schema design, indexing strategies,
migrations, aur database performance aati hai.

Focus karo:
- Query optimization (EXPLAIN ANALYZE)
- Index strategies
- Schema normalization/denormalization tradeoffs
- Transaction management
- Migration best practices
- N+1 problem prevention

Actual SQL queries do, table names bold karo.""",
    },
    {
        "agent_id":    "specialist_devops",
        "name":        "DevOps Specialist",
        "domain":      "devops",
        "triggers":    [
            "docker", "kubernetes", "k8s", "deploy", "deployment", "ci",
            "cd", "pipeline", "github actions", "gitlab", "jenkins",
            "terraform", "ansible", "nginx", "load balancer", "ssl",
            "certificate", "environment", "env", "config", "secret",
            "monitoring", "logging", "alert", "devops", "infra",
            "container", "pod", "service", "ingress", "helm",
        ],
        "system_prompt": """Tu ek expert DevOps/Infrastructure engineer hai.
Tumhe Docker, Kubernetes, CI/CD pipelines, cloud infrastructure,
monitoring, aur deployment automation aati hai.

Focus karo:
- Container best practices
- CI/CD pipeline design
- Environment configuration
- Secret management
- Health checks aur monitoring
- Zero-downtime deployments

YAML/config files do. Service names aur commands bold karo.""",
    },
    {
        "agent_id":    "specialist_security",
        "name":        "Security Specialist",
        "domain":      "security",
        "triggers":    [
            "security", "vulnerability", "exploit", "injection", "xss",
            "csrf", "sql injection", "auth", "token", "secret", "password",
            "encrypt", "hash", "ssl", "tls", "https", "cors", "owasp",
            "penetration", "audit", "compliance", "permission", "access",
        ],
        "system_prompt": """Tu ek expert security engineer hai.
Tumhe OWASP Top 10, authentication/authorization security,
data encryption, secure coding practices, aur security auditing aati hai.

Focus karo:
- Input validation aur sanitization
- Auth token security
- Data encryption at rest/transit
- CORS aur CSP configuration
- Secret management
- Common vulnerability patterns

Specific code fixes do. Vulnerable lines clearly mark karo.""",
    },
    {
        "agent_id":    "specialist_performance",
        "name":        "Performance Specialist",
        "domain":      "performance",
        "triggers":    [
            "slow", "performance", "optimize", "bottleneck", "memory",
            "cpu", "cache", "caching", "lazy", "async", "concurrent",
            "parallel", "profiling", "benchmark", "latency", "throughput",
            "n+1", "query time", "response time", "timeout", "heavy",
        ],
        "system_prompt": """Tu ek expert performance engineer hai.
Tumhe profiling, caching strategies, async patterns, query optimization,
aur application performance tuning aati hai.

Focus karo:
- Specific bottleneck identification
- Caching strategies (Redis, in-memory)
- Async/await optimization
- Database query performance
- Memory leak detection
- Algorithm complexity

Before/after code examples do. Performance numbers estimate karo.""",
    },
]


def find_specialist(message: str) -> Optional[Dict]:
    """
    Message mein specialist triggers dhundho.
    Sabse zyada matching triggers wala specialist return karo.
    """
    msg_lower = message.lower()
    best: Optional[Dict] = None
    best_score = 0

    for spec in SPECIALIST_CONFIGS:
        score = sum(1 for t in spec["triggers"] if t in msg_lower)
        if score > best_score:
            best_score = score
            best = spec

    # Minimum 2 trigger words chahiye — false positives avoid karo
    return best if best_score >= 2 else None


def get_all_specialists() -> List[Dict]:
    """All specialists ka public info (no system_prompt)."""
    return [
        {
            "agent_id": s["agent_id"],
            "name":     s["name"],
            "domain":   s["domain"],
            "triggers": s["triggers"][:6],  # preview only
        }
        for s in SPECIALIST_CONFIGS
    ]


def get_specialist_by_id(agent_id: str) -> Optional[Dict]:
    return next((s for s in SPECIALIST_CONFIGS if s["agent_id"] == agent_id), None)
