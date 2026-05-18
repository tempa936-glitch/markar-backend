"""
AutoRouterAgent — LLM-powered intelligent routing.
Keyword matching ki jagah LLM se intent classify karta hai.
Fallback: keyword scoring (offline mode ke liye).
"""
import os
import json
import asyncio
from typing import Dict, Optional
from .base_agent import BaseAgent


# ── Intent schema ────────────────────────────────────────────────────────────

INTENT_DESCRIPTIONS = {
    "ask":    "Code exploration, explanation, finding functions/files, understanding architecture",
    "debug":  "Error analysis, bug finding, root cause, exception traceback, crash investigation",
    "build":  "Feature implementation, code generation, adding new functionality, writing new code",
    "qa":     "Test generation, unit tests, integration tests, test coverage, pytest",
    "impact": "Change impact analysis, blast radius, what breaks if X changes, dependency mapping",
}

KEYWORD_TRIGGERS = {
    "debug":  ["error", "bug", "fail", "crash", "kyun", "issue", "debug", "problem",
               "broken", "exception", "fix", "wrong", "nahi chal", "traceback", "stack"],
    "build":  ["build", "implement", "add", "create", "feature", "banao", "generate",
               "develop", "make", "write code", "new feature", "naya", "likho"],
    "qa":     ["test", "qa", "coverage", "spec", "pytest", "unit test", "integration test", "testing"],
    "impact": ["impact", "blast radius", "affect", "agar badloon", "dependency",
               "migrate", "refactor", "effect", "change karne se", "tod dega"],
    "ask":    ["kahan", "kya", "batao", "find", "show", "where", "what", "explain",
               "how", "list", "dikhao", "samjhao", "architecture", "flow"],
}


class AutoRouterAgent:
    """
    LLM-first intent router.
    1. LLM se classify karo (fast, 1 call, structured JSON output)
    2. Fallback: keyword scoring
    3. Confidence score return karo
    """

    ROUTER_SYSTEM = """You are an intent classifier for a codebase AI assistant.
Classify the user's message into exactly one of these intents:
- ask: Code questions, finding functions/files, explaining architecture
- debug: Errors, bugs, crashes, root cause analysis  
- build: Implementing features, generating code, writing new code
- qa: Test generation, unit/integration tests, coverage
- impact: Change impact, blast radius, dependency analysis

Respond ONLY with valid JSON, no markdown, no explanation:
{"intent": "<one of: ask|debug|build|qa|impact>", "confidence": <0.0-1.0>, "reason": "<1 sentence>"}"""

    def __init__(self):
        self._cache: Dict[str, str] = {}  # message hash → intent

    async def route(self, message: str, model: str = None) -> Dict:
        """
        Route message to correct agent intent.
        Returns: {"intent": str, "confidence": float, "method": "llm"|"keyword"}
        """
        # Check cache
        cache_key = message[:100].lower().strip()
        if cache_key in self._cache:
            return {**self._cache[cache_key], "method": "cache"}

        # Try LLM routing
        llm_result = await self._llm_route(message, model)
        if llm_result and llm_result.get("confidence", 0) >= 0.6:
            llm_result["method"] = "llm"
            self._cache[cache_key] = llm_result
            return llm_result

        # Fallback to keyword scoring
        kw_result = self._keyword_route(message)
        kw_result["method"] = "keyword"
        return kw_result

    async def _llm_route(self, message: str, model: str = None) -> Optional[Dict]:
        """Fast LLM classification call."""
        import httpx

        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            return None

        fast_model = model or os.getenv(
            "MARKAR_ROUTER_MODEL",
            "mistralai/mistral-7b-instruct:free"
        )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type":  "application/json",
                        "HTTP-Referer":  "https://markarai.netlify.app",
                        "X-Title":       "Markar.ai Router",
                    },
                    json={
                        "model":    fast_model,
                        "messages": [
                            {"role": "system", "content": self.ROUTER_SYSTEM},
                            {"role": "user",   "content": f"Message: {message}"},
                        ],
                        "max_tokens":  80,
                        "temperature": 0.0,
                    },
                )

            data = response.json()
            if response.status_code != 200:
                return None

            content = data["choices"][0]["message"].get("content") or ""
            raw = content.strip()
            if not raw:
                return None
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            parsed = json.loads(raw)
            intent = parsed.get("intent", "ask")
            if intent not in INTENT_DESCRIPTIONS:
                intent = "ask"

            print(f"[AutoRouter] LLM → intent={intent} confidence={parsed.get('confidence', 0):.2f}")
            return {
                "intent":     intent,
                "confidence": parsed.get("confidence", 0.8),
                "reason":     parsed.get("reason", ""),
            }

        except Exception as e:
            print(f"[AutoRouter] LLM routing failed: {e}")
            return None

    def _keyword_route(self, message: str) -> Dict:
        """Keyword-based fallback routing with score."""
        msg_lower = message.lower()
        scores: Dict[str, int] = {k: 0 for k in KEYWORD_TRIGGERS}

        for intent, keywords in KEYWORD_TRIGGERS.items():
            for kw in keywords:
                if kw in msg_lower:
                    scores[intent] += 1

        best   = max(scores, key=scores.get)
        score  = scores[best]
        intent = best if score > 0 else "ask"
        confidence = min(0.5 + score * 0.1, 0.9) if score > 0 else 0.4

        print(f"[AutoRouter] Keyword → intent={intent} score={score}")
        return {
            "intent":     intent,
            "confidence": confidence,
            "reason":     f"keyword match score={score}",
        }


# ── Global router instance ───────────────────────────────────────────────────
_router = AutoRouterAgent()

def get_router() -> AutoRouterAgent:
    return _router
