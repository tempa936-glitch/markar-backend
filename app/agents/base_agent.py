"""
BaseAgent — Production-Grade Upgrade.
- Async/await support with streaming
- Pydantic-validated inputs/outputs
- Structured LLM calls with retry logic
- Tool Registry integration
- Conversation history context
- Self-reflection loop
- Multi-step reasoning (Chain-of-Thought)
- Token-aware context management
"""
import os
import asyncio
import concurrent.futures          # ← yeh add karo
from typing import Dict, List, Optional, AsyncGenerator, Any
from pydantic import BaseModel


# ── Pydantic schemas ────────────────────────────────────────────────────────

class AgentResponse(BaseModel):
    answer: str
    agent: str
    files: List[str] = []
    functions: List[str] = []
    reflected: bool = False
    intent: Optional[str] = None
    metadata: Dict[str, Any] = {}


class StreamChunk(BaseModel):
    content: str
    done: bool = False
    agent: Optional[str] = None
    metadata: Dict[str, Any] = {}


# ── Base Agent ──────────────────────────────────────────────────────────────

class BaseAgent:
    """
    Production-grade base for all Markar agents.
    Features: async LLM, streaming, retry, token-awareness, reflection.
    """

    MAX_CONTEXT_TOKENS = 6000   # approximate token ceiling for graph context
    MAX_HISTORY_TURNS  = 8      # last N conversation turns to include

    def __init__(
        self,
        store=None,
        repo_id: str = "",
        session_id: str = None,
        conv_store=None,
        tool_registry=None,
    ):
        self.store         = store
        self.repo_id       = repo_id
        self.session_id    = session_id
        self.conv_store    = conv_store
        self.tool_registry = tool_registry

    # ── Neo4j query helpers ─────────────────────────────────────────────────

    def query(self, cypher: str, **params) -> List[Dict]:
        try:
            driver = self.store._connect()
            with driver.session() as s:
                result = s.run(cypher, r=self.repo_id, **params)
                return [dict(row) for row in result]
        except Exception as e:
            print(f"[{self.__class__.__name__}] Query failed: {e}")
            return []

    def query_one(self, cypher: str, **params) -> Optional[Dict]:
        rows = self.query(cypher, **params)
        return rows[0] if rows else None

    # ── Tool Registry ────────────────────────────────────────────────────────

    def use_tool(self, tool_name: str, **kwargs) -> Dict:
        if not self.tool_registry:
            return {"success": False, "error": "Tool registry nahi hai"}
        return self.tool_registry.call(tool_name, **kwargs)

    # ── LLM — Sync (backward compat) ────────────────────────────────────────

    def ask_llm(self, system_prompt, user_message, graph_context,
            model=None, include_history=True, temperature=0.2, max_tokens=2048) -> str:
        """Synchronous LLM call — works in both sync and async contexts."""
        import asyncio

        coro = self.ask_llm_async(
            system_prompt, user_message, graph_context,
            model, include_history, temperature, max_tokens
        )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result(timeout=120)
        except Exception as e:
            print(f"[{self.__class__.__name__}] ask_llm failed: {e}")
            return self._fallback_response(graph_context)

    async def ask_llm_async(
        self,
        system_prompt: str,
        user_message: str,
        graph_context: Dict,
        model: str = None,
        include_history: bool = True,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        retries: int = 3,
    ) -> str:
        """
        Async LLM call with:
        - Token-aware context trimming
        - Conversation history injection
        - Exponential backoff retry
        - Structured error handling
        """
        import httpx

        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            return self._fallback_response(graph_context)

        # Build context — trim if too large
        context_text  = self._format_context_trimmed(graph_context)
        history_text  = ""
        if include_history and self.conv_store and self.session_id:
            history_text = self.conv_store.get_context_text(
                self.session_id, last_n=self.MAX_HISTORY_TURNS
            )

        full_user_content = ""
        if history_text:
            full_user_content += f"=== CONVERSATION HISTORY ===\n{history_text}\n\n"
        if context_text:
            full_user_content += f"=== CODEBASE KNOWLEDGE GRAPH ===\n{context_text}\n=================================\n\n"
        full_user_content += f"User: {user_message}"

        selected_model = model or os.getenv("MARKAR_LLM_MODEL", "mistralai/mistral-7b-instruct:free")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": full_user_content},
        ]

        # Retry with exponential backoff
        last_error = None
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type":  "application/json",
                            "HTTP-Referer":  "https://markarai.netlify.app",
                            "X-Title":       "Markar.ai",
                        },
                        json={
                            "model":       selected_model,
                            "messages":    messages,
                            "max_tokens":  max_tokens,
                            "temperature": temperature,
                        },
                    )

                data = response.json()
                if response.status_code != 200:
                    raise ValueError(f"LLM API error {response.status_code}: {data}")

                text = data["choices"][0]["message"]["content"]
                if not text:
                    return self._fallback_response(graph_context)
                print(f"[LLM] OK — model={selected_model} attempt={attempt+1}")
                return text

            except Exception as e:
                last_error = e
                wait = 2 ** attempt
                print(f"[LLM] Attempt {attempt+1} failed: {e} — retrying in {wait}s")
                await asyncio.sleep(wait)

        print(f"[LLM] All {retries} retries failed: {last_error}")
        return self._fallback_response(graph_context)

    # ── Streaming LLM ───────────────────────────────────────────────────────

    async def ask_llm_stream(
        self,
        system_prompt: str,
        user_message: str,
        graph_context: Dict,
        model: str = None,
        include_history: bool = True,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Server-Sent Events streaming LLM call.
        Yields StreamChunk objects as tokens arrive.
        """
        import httpx
        import json

        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            yield StreamChunk(content=self._fallback_response(graph_context), done=True)
            return

        context_text = self._format_context_trimmed(graph_context)
        history_text = ""
        if include_history and self.conv_store and self.session_id:
            history_text = self.conv_store.get_context_text(
                self.session_id, last_n=self.MAX_HISTORY_TURNS
            )

        full_user_content = ""
        if history_text:
            full_user_content += f"=== CONVERSATION HISTORY ===\n{history_text}\n\n"
        if context_text:
            full_user_content += f"=== CODEBASE KNOWLEDGE GRAPH ===\n{context_text}\n=================================\n\n"
        full_user_content += f"User: {user_message}"

        _env_model = os.getenv("MARKAR_LLM_MODEL", "openrouter/free")
        selected_model = model or _env_model
        if selected_model == "openrouter/free":
            selected_model = "meta-llama/llama-3.3-70b-instruct:free"

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type":  "application/json",
                        "HTTP-Referer":  "https://markarai.netlify.app",
                        "X-Title":       "Markar.ai",
                    },
                    json={
                        "model":    selected_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user",   "content": full_user_content},
                        ],
                        "max_tokens":  2048,
                        "temperature": 0.2,
                        "stream":      True,
                    },
                ) as stream_response:
                    async for line in stream_response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        raw = line[6:]
                        if raw.strip() == "[DONE]":
                            yield StreamChunk(content="", done=True)
                            return
                        try:
                            data  = json.loads(raw)
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield StreamChunk(content=delta, done=False)
                        except Exception:
                            continue

        except Exception as e:
            print(f"[LLM Stream] Failed: {e}")
            yield StreamChunk(content=f"[Streaming error: {e}]", done=True)

    # ── Self-Reflection ─────────────────────────────────────────────────────

    def reflect_and_improve(
        self,
        response: str,
        user_message: str,
        graph_context: Dict,
        model: str = None,
    ) -> str:
        """
        Phase 2: Self-reflection — check if response adequately answers the question.
        If inadequate, ask LLM to improve it.
        """
        if len(response) < 100:
            return response

        reflection_prompt = f"""Tu ek strict code review critic hai.
User QUESTION: {user_message}
RESPONSE (first 1200 chars): {response[:1200]}

Check karo:
1. Sawaal ka seedha jawab hai? (Y/N)
2. File path ya function references hain jahan relevant ho? (Y/N)
3. Actionable ya clear explanation hai? (Y/N)

Agar ADEQUATE (saare Y): sirf "OK" likho — kuch aur mat likho.
Agar INADEQUATE: improved version do (seedha, no preamble)."""

        try:
            critique = self.ask_llm(
                system_prompt="Tu ek concise code analysis critic hai.",
                user_message=reflection_prompt,
                graph_context={},
                model=model,
                include_history=False,
                temperature=0.1,
                max_tokens=1024,
            )
            if critique.strip().upper().startswith("OK"):
                return response
            return critique
        except Exception:
            return response

    # ── Multi-step Reasoning (Chain-of-Thought) ─────────────────────────────

    def reason_step_by_step(
        self,
        user_message: str,
        graph_context: Dict,
        model: str = None,
    ) -> str:
        """
        Phase 2: Chain-of-Thought reasoning for complex queries.
        Forces structured thinking before answering.
        """
        cot_prompt = f"""Step-by-step soch ke jawab do:

<think>
Step 1: Sawaal samjho — user kya jaanna chahta hai?
Step 2: Graph data analyze karo — kya available hai?
Step 3: Relevant patterns dhundho — connections, dependencies
Step 4: Conclusion nikalo — clear aur actionable
</think>

<answer>
Final clear answer (file paths, function names include karo)
</answer>

User sawaal: {user_message}"""

        response = self.ask_llm(
            system_prompt="Tu ek expert code analyst hai jo step-by-step sochta hai.",
            user_message=cot_prompt,
            graph_context=graph_context,
            model=model,
            include_history=True,
        )

        # Extract <answer> block
        if "<answer>" in response and "</answer>" in response:
            start = response.find("<answer>") + len("<answer>")
            end   = response.find("</answer>")
            return response[start:end].strip()
        return response

    # ── Context helpers ─────────────────────────────────────────────────────

    def _format_context_trimmed(self, ctx: Dict, max_chars: int = 8000) -> str:
        """Format graph context with token-aware trimming."""
        lines = []
        for key, val in ctx.items():
            if isinstance(val, list):
                lines.append(f"{key}:")
                for item in val[:20]:
                    lines.append(f"  - {item}")
            elif isinstance(val, dict):
                lines.append(f"{key}: {str(val)[:200]}")
            else:
                lines.append(f"{key}: {val}")

        full = "\n".join(lines)
        if len(full) > max_chars:
            full = full[:max_chars] + "\n... [context trimmed]"
        return full

    def _format_context(self, ctx: Dict) -> str:
        return self._format_context_trimmed(ctx)

    def _fallback_response(self, ctx: Dict) -> str:
        summary = {k: (v[:3] if isinstance(v, list) else v)
                   for k, v in list(ctx.items())[:5]}
        return f"LLM unavailable. Graph data preview: {summary}"
