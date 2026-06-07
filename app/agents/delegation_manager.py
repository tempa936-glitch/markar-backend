"""
DelegationManager — Markar Multi-Agent Delegation System.
Potpie-inspired, adapted for Markar's SQLite + Neo4j stack.

Architecture:
  SupervisorAgent
    ├── routes intent (AutoRouter)
    ├── optionally decomposes task into sub-tasks
    └── delegates to specialized agents:
         ├── AskAgent      → code exploration
         ├── DebugAgent    → error analysis
         ├── BuildAgent    → code generation
         ├── QAAgent       → test generation
         └── ImpactAgent   → blast radius

Key features:
- Async delegation with result caching
- Streaming sub-agent responses to caller
- History compression before each run
- Self-reflection on final answer
- Structured AgentResponse output (Pydantic)
"""
import asyncio
import uuid as _uuid
from typing import Dict, Optional, List, AsyncGenerator, Callable, Any

from .base_agent import BaseAgent, AgentResponse, StreamChunk
from .auto_router import AutoRouterAgent, get_router
from .history_manager import (
    CompressedHistoryStore, HistorySummarizer,
    HistoryMessage, get_compressed_store, get_summarizer,
)


# ── Delegation result cache ───────────────────────────────────────────────────

class _DelegationCache:
    """
    Simple in-memory cache for sub-agent results.
    Key: (session_id, intent, message_hash)
    Prevents duplicate executions in a single supervisor run.
    """
    def __init__(self):
        self._store: Dict[str, str] = {}

    def key(self, session_id: str, intent: str, message: str) -> str:
        import hashlib
        raw = f"{session_id}:{intent}:{message[:200]}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def get(self, k: str) -> Optional[str]:
        return self._store.get(k)

    def set(self, k: str, value: str) -> None:
        self._store[k] = value
        # Simple eviction: keep max 50 entries
        if len(self._store) > 50:
            oldest = next(iter(self._store))
            del self._store[oldest]

    def clear(self):
        self._store.clear()


# ── Delegation Manager ────────────────────────────────────────────────────────

class DelegationManager:
    """
    Core multi-agent orchestrator.
    Manages the full lifecycle:
    1. Route intent (AutoRouter)
    2. Compress history if needed
    3. Delegate to sub-agent
    4. Optionally self-reflect
    5. Save result to history
    """

    def __init__(self, store=None, repo_id: str = "", user_id: str = "dev-user"):
        self.store          = store
        self.repo_id        = repo_id
        self.user_id        = user_id
        self.router         = get_router()
        self.history_store  = get_compressed_store()
        self.summarizer     = get_summarizer()
        self._result_cache  = _DelegationCache()

        # Lazy-imported to avoid circular deps
        self._agents: Dict[str, BaseAgent] = {}
        self._conv_store = None
        self._tool_registry = None

    def _get_conv_store(self):
        if self._conv_store is None:
            from app.core.conversation_store import ConversationStore
            self._conv_store = ConversationStore()
        return self._conv_store

    def _get_tool_registry(self):
        if self._tool_registry is None:
            from app.core.tool_registry import get_registry
            self._tool_registry = get_registry()
        return self._tool_registry

    def _get_agent(self, intent: str, session_id: str) -> BaseAgent:
        """Lazy-init agents with shared dependencies."""
        if intent not in self._agents:
            shared = dict(
                store=self.store,
                repo_id=self.repo_id,
                session_id=session_id,
                conv_store=self._get_conv_store(),
                tool_registry=self._get_tool_registry(),
                user_id      = self.user_id,
            )

            if intent == "ask":
                from app.agents.ask_agent import AskAgent
                self._agents["ask"] = AskAgent(**shared)
            elif intent == "debug":
                from app.agents.debug_agent import DebugAgent
                self._agents["debug"] = DebugAgent(**shared)
            elif intent == "build":
                from app.agents.build_agent import BuildAgent
                self._agents["build"] = BuildAgent(**shared)
            elif intent == "qa":
                from app.agents.qa_agent import QAAgent
                self._agents["qa"] = QAAgent(**shared)
            elif intent == "impact":
                from app.agents.impact_agent import ImpactAnalysisAgent
                self._agents["impact"] = ImpactAnalysisAgent(store=self.store,repo_id=self.repo_id,user_id=self.user_id)
            else:
                from app.agents.ask_agent import AskAgent
                self._agents[intent] = AskAgent(**shared)

        # Always update session_id (may change per request)
        agent = self._agents[intent]
        if hasattr(agent, "session_id"):
            agent.session_id = session_id
        return agent
    
    def _enforce_tool_calling_for_ask(self, message: str, intent: str) -> str:
        """
        Ask intent ke liye force tool instruction inject karo.
        Without this, LLM kabhi hallucinate kar leta hai "Explain" pe.
        """
        if intent != "ask":
            return message
        
        # Codebase-related question detect karo
        code_patterns = [
            "explain", "purpose", "what does", "kaam", "kya", "batao", "samjhao",
            ".py", ".js", ".ts", ".go", ".java", "file", "function", "code",
            "repo_service", "service", "agent", "router", "handler", "controller",
            "how does", "working", "check", "verify", "analyze"
        ]
        
        is_code_question = any(p in message.lower() for p in code_patterns)
        
        if not is_code_question:
            return message
        
        # Agar user ne already tool format likh diya hai to double injection mat karo
        if "TOOL:" in message.upper() and "ARG:" in message.upper():
            return message
        
        # Force instruction inject karo
        forced_message = f"""🔧 SYSTEM ENFORCEMENT - TOOL CALLING MANDATORY 🔧

    You are answering a CODEBASE question about a REAL codebase. You have ZERO knowledge of this codebase outside of tool results.

    ABSOLUTE RULES:
    1. You MUST call search_nodes FIRST
    2. Then get_source_code on the main function
    3. Then MUST call get_callers
    4. Then MUST call get_callees
    5. You are FORBIDDEN to write any final answer before completing steps 1-4
    6. If you write an answer without calling all tools, it will be REJECTED
    If you violate these rules, your answer will be REJECTED.

    Original question: {message}

   Remember: Start with TOOL: search_nodes
   NEVER write "Not found" without trying get_file_functions first."""
        
        print(f"[Delegation] Tool enforcement injected for ask intent")
        return forced_message

    # ── Main execute method ───────────────────────────────────────────────────

    async def execute(
        self,
        message:    str,
        session_id: str,
        intent:     Optional[str] = None,
        target:     Optional[str] = None,
        model:      Optional[str] = None,
        trace_id:   Optional[str] = None,
    ) -> Dict:
        """
        Full delegation pipeline — returns final AgentResponse dict.
        """
        import uuid as _uuid2
        from app.core.trace_manager import get_tracer, TraceEvent
        from app.core.trace_manager import EVENT_ROUTING, EVENT_AGENT_STEP, EVENT_COMPLETE
        tracer   = get_tracer()
        trace_id = trace_id or str(_uuid2.uuid4())[:12]

        conv = self._get_conv_store()
        conv.create_session(session_id, self.repo_id)

        # ── 0. Specialist domain check ────────────────────────────────────
        _specialist = None
        if intent is None:
            from app.core.specialist_agents import find_specialist
            _specialist = find_specialist(message)

        # ── 1. Route intent ───────────────────────────────────────────────
        if intent is None:
            route_result = await self.router.route(message, model)
            intent       = route_result["intent"]
            confidence   = route_result.get("confidence", 0.5)
            route_method = route_result.get("method", "unknown")
        else:
            confidence   = 1.0
            route_method = "explicit"

        # ═══════════════════════════════════════════════════════════════════
        # 🔧 NEW: Tool enforcement for ask intent (force tool calling)
        # ═══════════════════════════════════════════════════════════════════
        original_message = message  # save for logging if needed
        message = self._enforce_tool_calling_for_ask(message, intent)
        # ═══════════════════════════════════════════════════════════════════    

        # Trace: routing
        tracer.log(TraceEvent(
            trace_id=trace_id, session_id=session_id,
            event_type=EVENT_ROUTING, agent=intent,
            input_data={"intent": intent, "confidence": round(confidence,2),
                        "method": route_method, "specialist": _specialist["name"] if _specialist else None,
                        "message_preview": message[:100]},
        ))
        print(f"[Delegation] intent={intent} confidence={confidence:.2f} method={route_method} session={session_id[:8]}")

        # ── 2. Clarification needed? ──────────────────────────────────────
        clarification = self._needs_clarification(intent, message, target)
        if clarification:
            conv.add_message(session_id, "user", message, intent=intent)
            conv.add_message(session_id, "assistant", clarification, agent="orchestrator")
            return {
                "answer":     clarification,
                "intent":     intent,
                "agent":      "orchestrator",
                "needs_info": True,
            }

        # ── 3. Save user message ──────────────────────────────────────────
        conv.add_message(session_id, "user", message, intent=intent)

        # ── 4. Compress history if needed ─────────────────────────────────
        await self._maybe_compress_history(session_id)

        # ── 5. Check result cache (within same supervisor run) ────────────
        cache_key = self._result_cache.key(session_id, intent, message)
        cached    = self._result_cache.get(cache_key)
        if cached:
            print(f"[Delegation] Cache hit — {intent}")
            return {
                "answer":     cached,
                "intent":     intent,
                "agent":      intent,
                "from_cache": True,
            }

        # ── 6. Delegate — specialist OR built-in agent ───────────────────
        # Trace: agent step start
        tracer.log(__import__("app.core.trace_manager", fromlist=["TraceEvent"]).TraceEvent(
            trace_id=trace_id, session_id=session_id,
            event_type=EVENT_AGENT_STEP,
            agent=_specialist["name"] if _specialist else intent,
            input_data={"target": target or "", "has_specialist": _specialist is not None},
        ))

        if _specialist:
            _ask = self._get_agent("ask", session_id)
            import asyncio as _aio2
            _sp = _specialist
            result = await _aio2.get_event_loop().run_in_executor(
                None,
                lambda: {
                    "answer": _ask.ask_llm(
                        system_prompt=_sp["system_prompt"],
                        user_message=message,
                        graph_context={},
                        model=model,
                        include_history=True,
                    ),
                    "agent": _sp["name"],
                    "specialist_id": _sp["agent_id"],
                    "domain": _sp["domain"],
                }
            )
        else:
            agent  = self._get_agent(intent, session_id)
            result = await self._run_agent(agent, intent, message, target, model)

        # ── 7. Self-reflection on answer ──────────────────────────────────
        answer = result.get("answer", "")
        reflect_enabled = False
        if reflect_enabled and hasattr(agent, "reflect_and_improve"):
            try:
                improved = agent.reflect_and_improve(answer, message, {}, model)
                if improved and improved != answer:
                    result["answer"]   = improved
                    result["reflected"] = True
                    answer = improved
            except Exception as e:
                print(f"[Delegation] Reflection failed: {e}")

        # ── 8. Cache result + save to history ─────────────────────────────
        if answer:
            self._result_cache.set(cache_key, answer)

        conv.add_message(
            session_id, "assistant", answer,
            agent=result.get("agent", intent), intent=intent
        )

        result["intent"]            = intent
        result["session_id"]        = session_id
        result["router_method"]     = route_method
        result["router_confidence"] = round(confidence, 2)
        result["trace_id"]          = trace_id

        # Trace: complete
        tracer.log(__import__("app.core.trace_manager", fromlist=["TraceEvent"]).TraceEvent(
            trace_id=trace_id, session_id=session_id,
            event_type=EVENT_COMPLETE,
            agent=result.get("agent", intent),
            output_data={"answer_len": len(result.get("answer",""))},
        ))
        return result

    # ── Streaming execute ─────────────────────────────────────────────────────

    async def execute_stream(
        self,
        message:    str,
        session_id: str,
        intent:     Optional[str] = None,
        target:     Optional[str] = None,
        model:      Optional[str] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Streaming delegation — yields StreamChunk objects.
        Router runs first (fast), then agent streams response.
        """
        conv = self._get_conv_store()
        conv.create_session(session_id, self.repo_id)

        # Route
        if intent is None:
            route_result = await self.router.route(message, model)
            intent = route_result["intent"]

        conv.add_message(session_id, "user", message, intent=intent)
        await self._maybe_compress_history(session_id)

        # Emit routing metadata
        yield StreamChunk(
            content  = "",
            done     = False,
            agent    = intent,
            metadata = {"event": "routing", "intent": intent},
        )

        # Delegate to agent streaming
        agent = self._get_agent(intent, session_id)

        # Build graph context for the agent
        graph_ctx = await self._build_graph_context(agent, intent, message, target)

        full_response = []
        async for chunk in agent.ask_llm_stream(
            system_prompt  = self._get_system_prompt(intent),
            user_message   = message,
            graph_context  = graph_ctx,
            model          = model,
            include_history = True,
        ):
            full_response.append(chunk.content)
            yield chunk

        # Save complete response to history
        complete = "".join(full_response)
        if complete:
            conv.add_message(session_id, "assistant", complete, agent=intent, intent=intent)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _run_agent(
        self,
        agent:   BaseAgent,
        intent:  str,
        message: str,
        target:  Optional[str],
        model:   Optional[str],
    ) -> Dict:
        """Run the correct agent method based on intent."""
        try:
            if intent == "debug":
                return await asyncio.get_event_loop().run_in_executor(
                    None, lambda: agent.run(message, target, model)
                )
            elif intent == "impact":
                return await asyncio.get_event_loop().run_in_executor(
                    None, lambda: agent.run(message, target, model)
                )
                #     return {
                #         "answer": self._format_impact(impact),
                #         "agent":  "impact",
                #     }
                # else:
                #     return {
                #         "answer": "Kaunsi file ya function ka impact analyze karna hai? Target batao.",
                #         "agent":  "impact",
                #     }
            elif intent == "qa":
                return await asyncio.get_event_loop().run_in_executor(
                    None, lambda: agent.run(message, target, model)
                )
            elif intent == "build":
                import uuid
                sid = str(uuid.uuid4())[:12]
                return await asyncio.get_event_loop().run_in_executor(
                    None, lambda: agent.clarify(sid, message, model)
                )
            else:  # ask + default
                # Use multi-step reasoning for complex queries
                if self._needs_multistep(message):
                    return await asyncio.get_event_loop().run_in_executor(
                        None, lambda: {"answer": agent.reason_step_by_step(message, {}, model), "agent": "ask"}
                    )
                else:
                    return await asyncio.get_event_loop().run_in_executor(
                        None, lambda: agent.run(message, model)
                    )

        except Exception as e:
            print(f"[Delegation] Agent run failed intent={intent}: {e}")
            return {"answer": f"Agent error: {e}. Retry karo.", "agent": "error"}

    async def _build_graph_context(
        self,
        agent:   BaseAgent,
        intent:  str,
        message: str,
        target:  Optional[str],
    ) -> Dict:
        """Build graph context dict for streaming calls."""
        try:
            if hasattr(agent, "_extract_keywords") and hasattr(agent, "_search_graph"):
                keywords = agent._extract_keywords(message)
                return await asyncio.get_event_loop().run_in_executor(
                    None, lambda: agent._search_graph(keywords)
                )
        except Exception:
            pass
        return {}

    def _get_system_prompt(self, intent: str) -> str:
        base_prompts = {
            "ask":    "Tu ek expert AI code analyst hai. Graph data aur codebase ke baare mein user ke sawaalon ka jawab do. File paths aur unke connections explain karo.",
            "debug":  "Tu ek senior debugger aur AI assistant hai. Errors ka root cause dhundho, blast radius batao, aur clean, working fix suggest karo.",
            "build":  "Tu ek senior software engineer hai. Clean, optimized, aur production-ready code generate karo.",
            "qa":     "Tu ek expert QA engineer hai. Comprehensive unit tests aur integration tests (jaise pytest) likho aur unka logic explain karo.",
            "impact": "Tu ek software architect hai. Code change ka blast radius aur risk level deeply analyze karo.",
        }
        
        formatting_rules = """
        
CRITICAL FORMATTING RULES:
1. Apne jawab ek professional aur highly-readable format me do. Jawab detailed aur complete rakho — koi bhi information mat chordo.
2. Headings ko hamesha **Bold** (`**Heading Name**`) rakho. `#` ya `###` ka use mat karo.
3. File paths, function names aur important keywords ko bhi **Bold** (`**file.py**`) karo.
4. IMPORTANT: Kisi bhi halat me backticks (`) ka use mat karo kyonki frontend unhe render nahi karta. Code snippets ke liye normal line breaks use karo.
5. Lambe paragraphs avoid karo. Clear aur short bullet points (`-` ya `•`) ka use karo.
6. Jawab naturally flow hona chahiye — ek AI assistant ki tarah politely aur clearly explain karo.
"""
        return base_prompts.get(intent, base_prompts["ask"]) + formatting_rules

    async def _maybe_compress_history(self, session_id: str) -> None:
        """Compress history if token count is high."""
        try:
            existing = self.history_store.get(session_id)
            if existing and len(existing) > 10:
                compressed = await self.summarizer.summarize_if_needed(existing)
                if len(compressed) < len(existing):
                    self.history_store.set(session_id, compressed)
        except Exception as e:
            print(f"[Delegation] History compression failed: {e}")

    def _needs_clarification(
        self, intent: str, message: str, target: Optional[str]
    ) -> Optional[str]:
        needs_target = {"debug", "impact"}
        if intent in needs_target and not target:
            msg_lower = message.lower()
            # File/function hints check karo
            has_hint = any(
                ext in message for ext in [
                    ".py", ".js", ".ts", ".go", ".java", "/", "\\",
                    "function", "class", "def ", "route", "routes",
                    "file", "module", "agent", "service", "auth",
                    "login", "api", "endpoint", "controller", "model",
                ]
            )
            # Meaningful keywords jo graph mein search ho saken
            meaningful_words = [
                w for w in msg_lower.split()
                if len(w) > 3 and w not in {
                    "check", "karo", "dekho", "working", "debug",
                    "analyze", "verify", "inspect", "mein", "hai",
                    "kya", "or", "not", "the", "and", "that", "this",
                    "routes", "route", "file", "github", "auth",
                }
            ]
            # Agar message mein koi searchable content hai toh clarification mat maango
            # DebugAgent khud graph mein dhund lega
            has_searchable_content = len(meaningful_words) >= 1 or has_hint

            if not has_searchable_content:
                labels = {"debug": "file ya function", "impact": "file ya function"}
                return f"Kaunsi {labels[intent]} analyze karni hai? File path ya function naam batao."
        return None

    def _needs_multistep(self, message: str) -> bool:
        complex_words = {
            "explain", "analyze", "compare", "difference", "architecture",
            "design", "flow", "overall", "samjhao", "poora", "detailed",
            "deep dive", "step by step", "kaisa", "kyun", "kaise"
        }
        return any(w in message.lower() for w in complex_words)

    def _format_impact(self, impact) -> str:
        try:
            return (
                f"**Severity:** {impact.severity.value.upper()}\n"
                f"**Affected nodes:** {len(impact.affected_nodes)}\n"
                f"**Affected files:** {len(impact.affected_files)}\n"
                f"**Risk Level:** {impact.risk_level}\n\n"
                f"**Recommendations:**\n" +
                "\n".join(f"• {r}" for r in impact.recommendations)
            )
        except Exception:
            return f"Impact analysis result: {impact}"


import os