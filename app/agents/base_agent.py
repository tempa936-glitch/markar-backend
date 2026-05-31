# """
# BaseAgent — Production-Grade Upgrade.
# - Async/await support with streaming
# - Pydantic-validated inputs/outputs
# - Structured LLM calls with retry logic
# - Tool Registry integration
# - Conversation history context
# - Self-reflection loop
# - Multi-step reasoning (Chain-of-Thought)
# - Token-aware context management
# """
# import os
# import asyncio
# import concurrent.futures          # ← yeh add karo
# from typing import Dict, List, Optional, AsyncGenerator, Any
# from pydantic import BaseModel
# from app.core.response_formatter import ResponseFormatter

# # ── Pydantic schemas ────────────────────────────────────────────────────────

# class AgentResponse(BaseModel):
#     answer: str
#     agent: str
#     files: List[str] = []
#     functions: List[str] = []
#     reflected: bool = False
#     intent: Optional[str] = None
#     metadata: Dict[str, Any] = {}


# class StreamChunk(BaseModel):
#     content: str
#     done: bool = False
#     agent: Optional[str] = None
#     metadata: Dict[str, Any] = {}


# # ── Base Agent ──────────────────────────────────────────────────────────────

# class BaseAgent:
#     """
#     Production-grade base for all Markar agents.
#     Features: async LLM, streaming, retry, token-awareness, reflection.
#     """

#     MAX_CONTEXT_TOKENS = 6000   # approximate token ceiling for graph context
#     MAX_HISTORY_TURNS  = 8      # last N conversation turns to include

#     def __init__(self, store, repo_id: str,
#                  session_id: str = None,
#                  conv_store=None,
#                  tool_registry=None,
#                  user_id: str = "dev-user"):
#         self.store         = store
#         self.repo_id       = repo_id
#         self.session_id    = session_id
#         self.conv_store    = conv_store
#         self.tool_registry = tool_registry
#         self.user_id       = user_id

#     # ── Neo4j query helpers ─────────────────────────────────────────────────

#     def query(self, cypher: str, **params) -> List[Dict]:
#         try:
#             driver = self.store._connect()
#             with driver.session() as s:
#                 result = s.run(cypher, r=self.repo_id, **params)
#                 return [dict(row) for row in result]
#         except Exception as e:
#             print(f"[{self.__class__.__name__}] Query failed: {e}")
#             return []

#     def query_one(self, cypher: str, **params) -> Optional[Dict]:
#         rows = self.query(cypher, **params)
#         return rows[0] if rows else None

#     # ── Tool Registry ────────────────────────────────────────────────────────

#     def use_tool(self, tool_name: str, **kwargs) -> Dict:
#         if not self.tool_registry:
#             return {"success": False, "error": "Tool registry nahi hai"}
#         return self.tool_registry.call(tool_name, **kwargs)

#     # ── LLM — Sync (backward compat) ────────────────────────────────────────

#     def ask_llm(self, system_prompt, user_message, graph_context,
#             model=None, include_history=True, temperature=0.2, max_tokens=2048) -> str:
#         """Synchronous LLM call — works in both sync and async contexts."""
#         import asyncio

#         coro = self.ask_llm_async(
#             system_prompt, user_message, graph_context,
#             model, include_history, temperature, max_tokens
#         )

#         try:
#             with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
#                 future = executor.submit(asyncio.run, coro)
#                 return future.result(timeout=120)
#         except Exception as e:
#             print(f"[{self.__class__.__name__}] ask_llm failed: {e}")
#             return self._fallback_response(graph_context)

#     async def ask_llm_async(
#         self,
#         system_prompt: str,
#         user_message: str,
#         graph_context: Dict,
#         model: str = None,
#         include_history: bool = True,
#         temperature: float = 0.2,
#         max_tokens: int = 2048,
#         retries: int = 3,
#     ) -> str:
#         """
#         Async LLM call with:
#         - Token-aware context trimming
#         - Conversation history injection
#         - Exponential backoff retry
#         - Structured error handling
#         - Dynamic Provider Routing
#         """
#         import httpx

#         try:
#             from app.core.llm_settings import get_user_llm_keys
#             user_keys = get_user_llm_keys(self.user_id)
#             selected_model = model or os.getenv("MARKAR_LLM_MODEL", "mistralai/mistral-7b-instruct:free")
#             if selected_model == "openrouter/free":
#                 selected_model = "meta-llama/llama-3.3-70b-instruct:free"

#             gemini_key = user_keys.get("gemini_key") or os.getenv("GEMINI_API_KEY", "")
#             print(f"[DEBUG] model={selected_model} gemini_key={'SET' if gemini_key else 'EMPTY'} provider will be={'gemini' if gemini_key and (selected_model.startswith('google/') or selected_model.startswith('gemini')) else 'other'}")
#             if gemini_key and (selected_model.startswith("google/") or selected_model.startswith("gemini")):
#                 api_key = gemini_key
#                 provider = "gemini"
#                 gemini_model = selected_model.replace("google/", "")
#                 url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={api_key}"    
#             else:
#                 if user_keys.get("use_own_keys"):
#                     if selected_model.startswith("openai/"):
#                         api_key = user_keys.get("openai_key")
#                         url = "https://api.openai.com/v1/chat/completions"
#                         provider = "openai"
#                     elif selected_model.startswith("anthropic/"):
#                         api_key = user_keys.get("anthropic_key")
#                         url = "https://api.anthropic.com/v1/messages"
#                         provider = "anthropic"
#                     else:
#                         api_key = user_keys.get("openrouter_key")
#                         url = "https://openrouter.ai/api/v1/chat/completions"
#                         provider = "openrouter"
#                 else:
#                     api_key = os.getenv("OPENROUTER_API_KEY", "")
#                     url = "https://openrouter.ai/api/v1/chat/completions"
#                     provider = "openrouter"        
                            

#             # if user_keys.get("use_own_keys"):
#             #     if selected_model.startswith("openai/"):
#             #         api_key = user_keys.get("openai_key")
#             #         url = "https://api.openai.com/v1/chat/completions"
#             #         provider = "openai"
#             #     elif selected_model.startswith("anthropic/"):
#             #         api_key = user_keys.get("anthropic_key")
#             #         url = "https://api.anthropic.com/v1/messages"
#             #         provider = "anthropic"
#             #     elif selected_model.startswith("google/") or selected_model.startswith("gemini"):
#             #         api_key = user_keys.get("gemini_key")
#             #         provider = "gemini"
#             #         gemini_model = selected_model.replace("google/", "")
#             #         url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={api_key}"
#             #     else:
#             #         api_key = user_keys.get("openrouter_key")
#             #         url = "https://openrouter.ai/api/v1/chat/completions"
#             #         provider = "openrouter"
#             # else:
#             #     api_key = os.getenv("OPENROUTER_API_KEY", "")
#             #     url = "https://openrouter.ai/api/v1/chat/completions"
#             #     provider = "openrouter"
                
#             if not api_key and provider != "openrouter":
#                 api_key = user_keys.get("openrouter_key") or os.getenv("OPENROUTER_API_KEY", "")
#                 url = "https://openrouter.ai/api/v1/chat/completions"
#                 provider = "openrouter"

#         except Exception:
#             api_key = os.getenv("OPENROUTER_API_KEY", "")
#             url = "https://openrouter.ai/api/v1/chat/completions"
#             provider = "openrouter"
#             selected_model = model or "meta-llama/llama-3.3-70b-instruct:free"

#         if not api_key:
#             return self._fallback_response(graph_context)

#         context_text  = self._format_context_trimmed(graph_context)
#         history_text  = ""
#         if include_history and self.conv_store and self.session_id:
#             history_text = self.conv_store.get_context_text(
#                 self.session_id, last_n=self.MAX_HISTORY_TURNS
#             )

#         full_user_content = ""
#         if history_text:
#             full_user_content += f"=== CONVERSATION HISTORY ===\n{history_text}\n\n"
#         if context_text:
#             full_user_content += f"=== CODEBASE KNOWLEDGE GRAPH ===\n{context_text}\n=================================\n\n"
#         full_user_content += f"User: {user_message}"

#         messages = [
#             {"role": "system", "content": system_prompt},
#             {"role": "user",   "content": full_user_content},
#         ]

#         if provider == "anthropic":
#             headers = {
#                 "x-api-key": api_key,
#                 "anthropic-version": "2023-06-01",
#                 "content-type": "application/json"
#             }
#             json_body = {
#                 "model": selected_model.replace("anthropic/", ""),
#                 "system": system_prompt,
#                 "messages": [{"role": "user", "content": full_user_content}],
#                 "max_tokens": max_tokens,
#                 "temperature": temperature,
#             }
#         elif provider == "gemini":
#             headers = {
#                 "Content-Type": "application/json"
#             }
#             json_body = {
#                 "systemInstruction": { "parts": [{"text": system_prompt}] },
#                 "contents": [
#                     {"role": "user", "parts": [{"text": full_user_content}]}
#                 ],
#                 "generationConfig": {
#                     "temperature": temperature,
#                     "maxOutputTokens": max_tokens
#                 }
#             }
#         else:
#             headers = {
#                 "Authorization": f"Bearer {api_key}",
#                 "Content-Type":  "application/json",
#             }
#             if provider == "openrouter":
#                 headers["HTTP-Referer"] = "https://markarai.netlify.app"
#                 headers["X-Title"] = "Markar.ai"
#             json_body = {
#                 "model": selected_model.replace("openai/", "") if provider == "openai" else selected_model,
#                 "messages": messages,
#                 "max_tokens": max_tokens,
#                 "temperature": temperature,
#             }

#         last_error = None
#         for attempt in range(retries):
#             try:
#                 async with httpx.AsyncClient(timeout=90.0) as client:
#                     response = await client.post(url, headers=headers, json=json_body)

#                 data = response.json()
#                 if response.status_code != 200:
#                     raise ValueError(f"LLM API error {response.status_code}: {data}")

#                 if provider == "anthropic":
#                     text = data.get("content", [{}])[0].get("text", "")
#                 elif provider == "gemini":
#                     text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
#                 else:
#                     text = data["choices"][0]["message"]["content"]
                    
#                 text = ResponseFormatter.clean(text)
#                 if not text:
#                     return self._fallback_response(graph_context)
                    
#                 print(f"[LLM] OK — model={selected_model} attempt={attempt+1}")
#                 try:
#                     from app.core.llm_settings import track_usage
#                     usage = data.get("usage", {})
#                     track_usage(
#                         user_id=self.user_id,
#                         model=selected_model,
#                         prompt_tokens=usage.get("prompt_tokens", usage.get("input_tokens", 0)),
#                         completion_tokens=usage.get("completion_tokens", usage.get("output_tokens", 0)),
#                         session_id=self.session_id,
#                         repo_id=self.repo_id,
#                         agent=self.__class__.__name__,
#                         success=True,
#                     )
#                 except Exception:
#                     pass

#                 return text

#             except Exception as e:
#                 last_error = e
#                 wait = 2 ** attempt
#                 print(f"[LLM] Attempt {attempt+1} failed: {e} — retrying in {wait}s")
#                 import asyncio
#                 await asyncio.sleep(wait)

#         print(f"[LLM] All {retries} retries failed: {last_error}")
#         return self._fallback_response(graph_context)

#     # ── Streaming LLM ───────────────────────────────────────────────────────

#     async def ask_llm_stream(
#         self,
#         system_prompt: str,
#         user_message: str,
#         graph_context: Dict,
#         model: str = None,
#         include_history: bool = True,
#     ) -> AsyncGenerator[StreamChunk, None]:
#         """
#         Server-Sent Events streaming LLM call.
#         Yields StreamChunk objects as tokens arrive.
#         """
#         import httpx
#         import json

#         try:
#             from app.core.llm_settings import get_user_llm_keys
#             user_keys = get_user_llm_keys(self.user_id)
#             print(f"[DEBUG2] received model param={model}")
#             selected_model = model or os.getenv("MARKAR_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
#             print(f"[DEBUG2] selected_model={selected_model}")
#             if selected_model == "openrouter/free":
#                 selected_model = "meta-llama/llama-3.3-70b-instruct:free"

#             if user_keys.get("use_own_keys"):
#                 if selected_model.startswith("openai/"):
#                     api_key = user_keys.get("openai_key")
#                     url = "https://api.openai.com/v1/chat/completions"
#                     provider = "openai"
#                 elif selected_model.startswith("anthropic/"):
#                     api_key = user_keys.get("anthropic_key")
#                     url = "https://api.anthropic.com/v1/messages"
#                     provider = "anthropic"
#                 elif selected_model.startswith("google/") or selected_model.startswith("gemini"):
#                     api_key = user_keys.get("gemini_key")
#                     provider = "gemini"
#                     gemini_model = selected_model.replace("google/", "")
#                     url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={api_key}"
#                 else:
#                     api_key = user_keys.get("openrouter_key")
#                     url = "https://openrouter.ai/api/v1/chat/completions"
#                     provider = "openrouter"
#             else:
#                 api_key = os.getenv("OPENROUTER_API_KEY", "")
#                 url = "https://openrouter.ai/api/v1/chat/completions"
#                 provider = "openrouter"
                
#             if not api_key and provider != "openrouter":
#                 api_key = user_keys.get("openrouter_key") or os.getenv("OPENROUTER_API_KEY", "")
#                 url = "https://openrouter.ai/api/v1/chat/completions"
#                 provider = "openrouter"

#         except Exception:
#             api_key = os.getenv("OPENROUTER_API_KEY", "")
#             url = "https://openrouter.ai/api/v1/chat/completions"
#             provider = "openrouter"
#             selected_model = model or "meta-llama/llama-3.3-70b-instruct:free"

#         if not api_key:
#             yield StreamChunk(content=self._fallback_response(graph_context), done=True)
#             return

#         context_text = self._format_context_trimmed(graph_context)
#         history_text = ""
#         if include_history and self.conv_store and self.session_id:
#             history_text = self.conv_store.get_context_text(
#                 self.session_id, last_n=self.MAX_HISTORY_TURNS
#             )

#         full_user_content = ""
#         if history_text:
#             full_user_content += f"=== CONVERSATION HISTORY ===\n{history_text}\n\n"
#         if context_text:
#             full_user_content += f"=== CODEBASE KNOWLEDGE GRAPH ===\n{context_text}\n=================================\n\n"
#         full_user_content += f"User: {user_message}"

#         messages = [
#             {"role": "system", "content": system_prompt},
#             {"role": "user",   "content": full_user_content},
#         ]

#         if provider == "anthropic":
#             headers = {
#                 "x-api-key": api_key,
#                 "anthropic-version": "2023-06-01",
#                 "content-type": "application/json"
#             }
#             json_body = {
#                 "model": selected_model.replace("anthropic/", ""),
#                 "system": system_prompt,
#                 "messages": [{"role": "user", "content": full_user_content}],
#                 "max_tokens": 2048,
#                 "temperature": 0.2,
#                 "stream": True,
#             }
#         elif provider == "gemini":
#             headers = {
#                 "Content-Type": "application/json"
#             }
#             json_body = {
#                 "systemInstruction": { "parts": [{"text": system_prompt}] },
#                 "contents": [
#                     {"role": "user", "parts": [{"text": full_user_content}]}
#                 ],
#                 "generationConfig": {
#                     "temperature": 0.2,
#                     "maxOutputTokens": 2048
#                 }
#             }
#         else:
#             headers = {
#                 "Authorization": f"Bearer {api_key}",
#                 "Content-Type":  "application/json",
#             }
#             if provider == "openrouter":
#                 headers["HTTP-Referer"] = "https://markarai.netlify.app"
#                 headers["X-Title"] = "Markar.ai"
#             json_body = {
#                 "model": selected_model.replace("openai/", "") if provider == "openai" else selected_model,
#                 "messages": messages,
#                 "max_tokens": 2048,
#                 "temperature": 0.2,
#                 "stream": True,
#             }

#         print(f"[LLM Stream] Using model={selected_model} (provider={provider}) for user={self.user_id}")

#         try:
#             async with httpx.AsyncClient(timeout=120.0) as client:
#                 async with client.stream("POST", url, headers=headers, json=json_body) as stream_response:
#                     async for line in stream_response.aiter_lines():
#                         if not line:
#                             continue
                        
#                         if provider == "anthropic":
#                             if line.startswith("data: "):
#                                 raw = line[6:]
#                                 try:
#                                     data = json.loads(raw)
#                                     if data.get("type") == "content_block_delta":
#                                         delta = data["delta"].get("text", "")
#                                         delta = ResponseFormatter.clean(delta)
#                                         if delta:
#                                             yield StreamChunk(content=delta, done=False)
#                                 except Exception:
#                                     continue
#                         elif provider == "gemini":
#                             if line.startswith("data: "):
#                                 raw = line[6:]
#                                 if raw.strip() == "":
#                                     continue
#                                 try:
#                                     data = json.loads(raw)
#                                     candidates = data.get("candidates", [])
#                                     if candidates:
#                                         parts = candidates[0].get("content", {}).get("parts", [])
#                                         if parts:
#                                             delta = parts[0].get("text", "")
#                                             delta = ResponseFormatter.clean(delta)
#                                             if delta:
#                                                 yield StreamChunk(content=delta, done=False)
#                                 except Exception:
#                                     continue
#                         else:
#                             if not line.startswith("data: "):
#                                 continue
#                             raw = line[6:]
#                             if raw.strip() == "[DONE]":
#                                 yield StreamChunk(content="", done=True)
#                                 return
#                             try:
#                                 data  = json.loads(raw)
#                                 delta = data["choices"][0]["delta"].get("content", "")
#                                 delta = ResponseFormatter.clean(delta)
#                                 if delta:
#                                     yield StreamChunk(content=delta, done=False)
#                             except Exception:
#                                 continue

#         except Exception as e:
#             print(f"[LLM Stream] Failed: {e}")
#             yield StreamChunk(content=f"[Streaming error: {e}]", done=True)

#     # ── Self-Reflection ─────────────────────────────────────────────────────

#     def reflect_and_improve(
#         self,
#         response: str,
#         user_message: str,
#         graph_context: Dict,
#         model: str = None,
#     ) -> str:
#         """
#         Phase 2: Self-reflection — check if response adequately answers the question.
#         If inadequate, ask LLM to improve it.
#         """
#         if len(response) < 100:
#             return response

#         reflection_prompt = f"""You are improving an AI code analysis response.
# User QUESTION: {user_message}
# RESPONSE (first 1500 chars): {response[:1500]}

# IMPORTANT:
# - Never shorten the response
# - Preserve all technical details
# - Preserve file names
# - Preserve counts

# STRICT RULES:
# - NEVER shorten the response
# - NEVER summarize aggressively
# - NEVER remove files
# - NEVER remove counts
# - NEVER remove technical details
# - NEVER remove architecture insights
# - Keep the answer detailed and structured
# - Preserve markdown formatting
# TASK:
# Return a polished improved version of the SAME response.

# If the response is already strong,
# return it with minimal edits.
# """

#         try:
#             critique = self.ask_llm(
#                 system_prompt="Tu ek concise code analysis critic hai.",
#                 user_message=reflection_prompt,
#                 graph_context={},
#                 model=model,
#                 include_history=False,
#                 temperature=0.1,
#                 max_tokens=1024,
#             )
#             if critique.strip().upper().startswith("OK"):
#                 return response
#             # Agar improved response bahut chhota ho to original rakho
#             if len(critique) < len(response) * 0.7:
#                 return response
            
#             critique = critique.replace("INADEQUATE", "")
#             critique = critique.replace("Improved version:", "").strip()
#             if len(critique)  < len(response) * 0.7:
#                 return response
            
#             return critique
#         except Exception:
#             return response

#     # ── Multi-step Reasoning (Chain-of-Thought) ─────────────────────────────

#     def reason_step_by_step(
#         self,
#         user_message: str,
#         graph_context: Dict,
#         model: str = None,
#     ) -> str:
#         """
#         Phase 2: Chain-of-Thought reasoning for complex queries.
#         Forces structured thinking before answering.
#         """
#         cot_prompt = f"""Step-by-step soch ke jawab do:

# <think>
# Step 1: Sawaal samjho — user kya jaanna chahta hai?
# Step 2: Graph data analyze karo — kya available hai?
# Step 3: Relevant patterns dhundho — connections, dependencies
# Step 4: Conclusion nikalo — clear aur actionable
# </think>

# <answer>
# Final clear answer (file paths, function names include karo)
# </answer>

# User sawaal: {user_message}"""

#         response = self.ask_llm(
#             system_prompt="Tu ek expert code analyst hai jo step-by-step sochta hai.",
#             user_message=cot_prompt,
#             graph_context=graph_context,
#             model=model,
#             include_history=True,
#         )

#         # Extract <answer> block
#         if "<answer>" in response and "</answer>" in response:
#             start = response.find("<answer>") + len("<answer>")
#             end   = response.find("</answer>")
#             return response[start:end].strip()
#         return response

#     # ── Context helpers ─────────────────────────────────────────────────────

#     def _format_context_trimmed(self, ctx: Dict, max_chars: int = 16000) -> str:
#         """Format graph context with token-aware trimming."""
#         lines = []

#         priority_keys = ["deep_function_analysis", "deep_file_analysis", "deep_branches", "deep_exception_chain"]
#         for key in priority_keys:
#             if key in ctx:
#                 lines.append(f"{key}: {ctx[key]}")
#         for key, val in ctx.items():
#             if key in priority_keys:
#                 continue
#             if isinstance(val, list):
#                 lines.append(f"{key}:")
#                 for item in val[:20]:
#                     lines.append(f"  - {item}")
#             elif isinstance(val, dict):
#                 lines.append(f"{key}: {str(val)[:200]}")
#             else:
#                 lines.append(f"{key}: {val}")

#         full = "\n".join(lines)
#         if len(full) > max_chars:
#             full = full[:max_chars] + "\n... [context trimmed]"
#         return full

#     def _format_context(self, ctx: Dict) -> str:
#         return self._format_context_trimmed(ctx)

#     def _fallback_response(self, ctx: Dict) -> str:
#         summary = {k: (v[:3] if isinstance(v, list) else v)
#                    for k, v in list(ctx.items())[:5]}
#         return f"LLM unavailable. Graph data preview: {summary}"

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
import concurrent.futures
from typing import Dict, List, Optional, AsyncGenerator, Any
from pydantic import BaseModel
from app.core.response_formatter import ResponseFormatter

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


# ── Routing Helper ──────────────────────────────────────────────────────────

# Gemini model name aliases — frontend ke short names → Gemini API ke official names
GEMINI_MODEL_ALIASES = {
    "gemini-2.5-flash-lite":        "gemini-2.5-flash-lite",
    "gemini-2.5-flash":             "gemini-2.5-flash",
    "gemini-2.5-pro":               "gemini-2.5-pro",
    "gemini-2.0-flash":             "gemini-2.0-flash",
    "gemini-2.0-flash-lite":        "gemini-2.0-flash-lite",
    "gemini-1.5-flash":             "gemini-1.5-flash",
    "gemini-1.5-flash-8b":          "gemini-1.5-flash-8b",
    "gemini-1.5-pro":               "gemini-1.5-pro",
}


def _normalize_gemini_model(model: str) -> str:
    """
    Frontend bheje koi bhi Gemini model name →
    Gemini REST API ke liye sahi model ID return karo.
    """
    # google/ prefix hata do
    clean = model.replace("google/", "").strip()
    # alias map mein dekho
    return GEMINI_MODEL_ALIASES.get(clean, clean)


def _resolve_provider(selected_model: str, user_keys: dict) -> tuple:
    """
    Model name ke basis pe provider, api_key, aur url resolve karo.

    Priority order:
      1. Model name se provider detect karo
      2. User ki key hai → direct use karo (gemini/anthropic/openai)
      3. Key nahi → system OpenRouter fallback
      4. OpenRouter key bhi nahi → empty (caller handle karega)

    Returns: (provider, api_key, url)
    """
    system_openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    # ── Gemini ───────────────────────────────────────────────────────────────
    if selected_model.startswith("google/") or selected_model.lower().startswith("gemini"):
        gemini_key = user_keys.get("gemini_key") or os.getenv("GEMINI_API_KEY", "")
        if gemini_key:
            gemini_model = _normalize_gemini_model(selected_model)
            print(f"[Provider] Gemini model normalized: '{selected_model}' → '{gemini_model}'")
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{gemini_model}:generateContent?key={gemini_key}"
            )
            return "gemini", gemini_key, url
        # Gemini key nahi → OpenRouter pe try karo (wo bhi Gemini support karta hai)
        print(f"[Provider] Gemini key missing, falling back to OpenRouter for {selected_model}")
        return "openrouter", system_openrouter_key, "https://openrouter.ai/api/v1/chat/completions"

    # ── Anthropic ────────────────────────────────────────────────────────────
    if selected_model.startswith("anthropic/") or selected_model.startswith("claude"):
        anthropic_key = user_keys.get("anthropic_key") or os.getenv("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            return "anthropic", anthropic_key, "https://api.anthropic.com/v1/messages"
        print(f"[Provider] Anthropic key missing, falling back to OpenRouter for {selected_model}")
        return "openrouter", system_openrouter_key, "https://openrouter.ai/api/v1/chat/completions"

    # ── OpenAI ───────────────────────────────────────────────────────────────
    if selected_model.startswith("openai/") or selected_model.startswith("gpt"):
        openai_key = user_keys.get("openai_key") or os.getenv("OPENAI_API_KEY", "")
        if openai_key:
            return "openai", openai_key, "https://api.openai.com/v1/chat/completions"
        print(f"[Provider] OpenAI key missing, falling back to OpenRouter for {selected_model}")
        return "openrouter", system_openrouter_key, "https://openrouter.ai/api/v1/chat/completions"

    # ── OpenRouter / Meta / Mistral / everything else ────────────────────────
    openrouter_key = user_keys.get("openrouter_key") or system_openrouter_key
    if not openrouter_key:
        print(f"[Provider] WARNING: No API key found for model={selected_model}")
    return "openrouter", openrouter_key, "https://openrouter.ai/api/v1/chat/completions"


# ── Base Agent ──────────────────────────────────────────────────────────────

class BaseAgent:
    """
    Production-grade base for all Markar agents.
    Features: async LLM, streaming, retry, token-awareness, reflection.
    """

    MAX_CONTEXT_TOKENS = 6000   # approximate token ceiling for graph context
    MAX_HISTORY_TURNS  = 8      # last N conversation turns to include

    def __init__(self, store, repo_id: str,
                 session_id: str = None,
                 conv_store=None,
                 tool_registry=None,
                 user_id: str = "dev-user"):
        self.store         = store
        self.repo_id       = repo_id
        self.session_id    = session_id
        self.conv_store    = conv_store
        self.tool_registry = tool_registry
        self.user_id       = user_id

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
        - Model-first provider routing
        - Token-aware context trimming
        - Conversation history injection
        - Exponential backoff retry
        - Structured error handling
        """
        import httpx

        try:
            from app.core.llm_settings import get_user_llm_keys
            user_keys = get_user_llm_keys(self.user_id)
        except Exception:
            user_keys = {}

        selected_model = model or user_keys.get("preferred_model") or os.getenv("MARKAR_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        if selected_model in ("openrouter/free", None, ""):
            selected_model = "meta-llama/llama-3.3-70b-instruct:free"

        # ── Model-first provider routing ─────────────────────────────────────
        try:
            provider, api_key, url = _resolve_provider(selected_model, user_keys)
        except Exception as e:
            print(f"[LLM] Provider resolve failed: {e}")
            provider = "openrouter"
            api_key  = os.getenv("OPENROUTER_API_KEY", "")
            url      = "https://openrouter.ai/api/v1/chat/completions"

        # ── has_own_keys: user ne koi bhi key di hai? ─────────────────────────
        has_own_keys = bool(
            user_keys.get("gemini_key") or user_keys.get("anthropic_key") or
            user_keys.get("openai_key") or user_keys.get("openrouter_key")
        )

        print(f"[LLM] model={selected_model} provider={provider} has_own_keys={has_own_keys} key={'SET' if api_key else 'EMPTY'}")

        if not api_key:
            if has_own_keys:
                # User ne key di hai lekin is provider ke liye nahi — clear error
                err = (
                    f"❌ {provider.upper()} ke liye API key nahi mili. "
                    f"Settings mein '{provider}' key add karein ya doosra model choose karein."
                )
            else:
                # System key bhi nahi — system level problem
                err = "❌ Koi bhi API key configure nahi hai. Admin se contact karein."
            print(f"[LLM] No API key — returning error: {err}")
            return err

        # ── Build message payload ────────────────────────────────────────────
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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": full_user_content},
        ]

        # ── Provider-specific headers & body ─────────────────────────────────
        if provider == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            json_body = {
                "model": selected_model.replace("anthropic/", ""),
                "system": system_prompt,
                "messages": [{"role": "user", "content": full_user_content}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        elif provider == "gemini":
            headers = {"Content-Type": "application/json"}
            json_body = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [
                    {"role": "user", "parts": [{"text": full_user_content}]}
                ],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }
        else:  # openai / openrouter
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            if provider == "openrouter":
                headers["HTTP-Referer"] = "https://markarai.netlify.app"
                headers["X-Title"] = "Markar.ai"
            json_body = {
                "model": selected_model.replace("openai/", "") if provider == "openai" else selected_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

        # ── Retry loop ───────────────────────────────────────────────────────
        last_error    = None
        last_err_msg  = ""   # user-facing error message
        has_own_keys  = bool(
            user_keys.get("gemini_key") or user_keys.get("anthropic_key") or
            user_keys.get("openai_key") or user_keys.get("openrouter_key")
        )

        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await client.post(url, headers=headers, json=json_body)

                data = response.json()
                status = response.status_code

                # ── HTTP error classification ─────────────────────────────────
                if status != 200:
                    err_body = str(data)
                    if status == 401:
                        last_err_msg = (
                            f"❌ API key invalid hai ({provider.upper()}). "
                            "Settings mein sahi key daalo."
                        )
                        print(f"[LLM] 401 Invalid key — stopping retries")
                        break  # retry se kuch faida nahi

                    elif status == 402:
                        last_err_msg = (
                            f"⚠️ {provider.upper()} credits khatam ho gaye (402). "
                            "Account recharge karein ya doosra model choose karein."
                        )
                        print(f"[LLM] 402 Credits exhausted — stopping retries")
                        break  # recharge kiye bina retry bekar hai

                    elif status == 429:
                        last_err_msg = (
                            f"⚠️ {provider.upper()} rate limit ya quota exceed ho gayi. "
                            "Thodi der baad try karein."
                        )
                        print(f"[LLM] 429 Rate limit attempt={attempt+1} — will retry")

                    elif status == 400:
                        last_err_msg = (
                            f"❌ Request error ({provider.upper()} 400). "
                            f"Model name galat ho sakta hai: {selected_model}"
                        )
                        print(f"[LLM] 400 Bad request: {err_body[:300]}")
                        break  # bad request retry se theek nahi hoga

                    elif status == 503 or status == 502:
                        last_err_msg = (
                            f"⚠️ {provider.upper()} server abhi busy hai (503/502). "
                            "Retry ho raha hai..."
                        )
                        print(f"[LLM] {status} Server busy attempt={attempt+1}")

                    else:
                        last_err_msg = (
                            f"❌ {provider.upper()} API error {status}. "
                            f"Detail: {err_body[:200]}"
                        )
                        print(f"[LLM] HTTP {status}: {err_body[:300]}")

                    last_error = ValueError(last_err_msg)
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    continue

                # ── Response parsing ──────────────────────────────────────────
                try:
                    if provider == "anthropic":
                        text = data.get("content", [{}])[0].get("text", "")
                    elif provider == "gemini":
                        # Gemini ke alag-alag failure modes handle karo
                        candidates = data.get("candidates", [])
                        if not candidates:
                            finish = data.get("promptFeedback", {}).get("blockReason", "UNKNOWN")
                            last_err_msg = f"⚠️ Gemini ne response block kar diya: {finish}"
                            print(f"[LLM] Gemini blocked: {data}")
                            break
                        finish_reason = candidates[0].get("finishReason", "")
                        if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
                            last_err_msg = f"⚠️ Gemini ne content block kiya (reason: {finish_reason})"
                            print(f"[LLM] Gemini finish_reason={finish_reason}")
                            break
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text = parts[0].get("text", "") if parts else ""
                    else:
                        text = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as parse_err:
                    last_err_msg = f"❌ Response parse nahi hua ({provider}): {parse_err} | Raw: {str(data)[:300]}"
                    print(f"[LLM] Parse error: {parse_err} | data={str(data)[:300]}")
                    last_error = parse_err
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    continue

                text = ResponseFormatter.clean(text) if text else ""
                if not text:
                    last_err_msg = f"⚠️ {provider.upper()} ne empty response diya (attempt {attempt+1})"
                    print(f"[LLM] Empty response from {provider}, attempt={attempt+1}")
                    last_error = ValueError(last_err_msg)
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    continue

                # ── Success ───────────────────────────────────────────────────
                print(f"[LLM] OK — model={selected_model} provider={provider} attempt={attempt+1}")
                try:
                    from app.core.llm_settings import track_usage
                    usage = data.get("usage", {})
                    track_usage(
                        user_id=self.user_id,
                        model=selected_model,
                        prompt_tokens=usage.get("prompt_tokens", usage.get("input_tokens", 0)),
                        completion_tokens=usage.get("completion_tokens", usage.get("output_tokens", 0)),
                        session_id=self.session_id,
                        repo_id=self.repo_id,
                        agent=self.__class__.__name__,
                        success=True,
                    )
                except Exception:
                    pass

                return text

            except Exception as e:
                last_error = e
                last_err_msg = f"❌ Network/connection error ({provider}): {e}"
                wait = 2 ** attempt
                print(f"[LLM] Attempt {attempt+1} exception: {e} — retrying in {wait}s")
                await asyncio.sleep(wait)

        # ── All retries exhausted ─────────────────────────────────────────────
        print(f"[LLM] All {retries} retries failed. last_error={last_error}")

        if has_own_keys:
            # User ki apni key fail hui — system fallback BILKUL NAHI
            msg = last_err_msg or f"❌ {provider.upper()} se response nahi mila. Apni key aur model check karein."
            print(f"[LLM] has_own_keys=True — NOT using system fallback. Returning error to user.")
            return msg
        else:
            # System key fail hui
            msg = last_err_msg or "⚠️ LLM service abhi temporarily unavailable hai. Thodi der baad try karein."
            print(f"[LLM] has_own_keys=False — system key also failed.")
            return msg

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

        try:
            from app.core.llm_settings import get_user_llm_keys
            user_keys = get_user_llm_keys(self.user_id)
        except Exception:
            user_keys = {}

        selected_model = model or user_keys.get("preferred_model") or os.getenv("MARKAR_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        if selected_model in ("openrouter/free", None, ""):
            selected_model = "meta-llama/llama-3.3-70b-instruct:free"

        print(f"[LLM Stream] received model param={model}, resolved={selected_model}")

        # ── Model-first provider routing ─────────────────────────────────────
        try:
            provider, api_key, url = _resolve_provider(selected_model, user_keys)
        except Exception as e:
            print(f"[LLM Stream] Provider resolve failed: {e}")
            provider = "openrouter"
            api_key  = os.getenv("OPENROUTER_API_KEY", "")
            url      = "https://openrouter.ai/api/v1/chat/completions"

        # ── has_own_keys: user ne koi bhi key di hai? ─────────────────────────
        has_own_keys = bool(
            user_keys.get("gemini_key") or user_keys.get("anthropic_key") or
            user_keys.get("openai_key") or user_keys.get("openrouter_key")
        )

        print(f"[LLM Stream] model={selected_model} provider={provider} has_own_keys={has_own_keys} key={'SET' if api_key else 'EMPTY'}")

        if not api_key:
            if has_own_keys:
                err_msg = (
                    f"❌ {provider.upper()} ke liye API key nahi mili. "
                    f"Settings mein '{provider}' key add karein ya doosra model choose karein."
                )
            else:
                err_msg = "❌ Koi bhi API key configure nahi hai. Admin se contact karein."
            print(f"[LLM Stream] No API key — {err_msg}")
            yield StreamChunk(content=err_msg, done=True)
            return

        # ── Build message payload ────────────────────────────────────────────
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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": full_user_content},
        ]

        # ── Provider-specific headers & body ─────────────────────────────────
        if provider == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            json_body = {
                "model": selected_model.replace("anthropic/", ""),
                "system": system_prompt,
                "messages": [{"role": "user", "content": full_user_content}],
                "max_tokens": 2048,
                "temperature": 0.2,
                "stream": True,
            }
        elif provider == "gemini":
            # NOTE: Gemini streaming uses a different endpoint suffix
            url = url.replace(":generateContent", ":streamGenerateContent") + "&alt=sse"
            headers = {"Content-Type": "application/json"}
            json_body = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [
                    {"role": "user", "parts": [{"text": full_user_content}]}
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 2048,
                },
            }
        else:  # openai / openrouter
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            if provider == "openrouter":
                headers["HTTP-Referer"] = "https://markarai.netlify.app"
                headers["X-Title"] = "Markar.ai"
            json_body = {
                "model": selected_model.replace("openai/", "") if provider == "openai" else selected_model,
                "messages": messages,
                "max_tokens": 2048,
                "temperature": 0.2,
                "stream": True,
            }

        print(f"[LLM Stream] Starting stream — model={selected_model} provider={provider}")

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, headers=headers, json=json_body) as stream_response:

                    # ── HTTP error check before reading body ──────────────────
                    if stream_response.status_code != 200:
                        status = stream_response.status_code
                        body   = await stream_response.aread()
                        try:
                            err_data = json.loads(body)
                        except Exception:
                            err_data = {"raw": body.decode(errors="replace")[:300]}

                        if status == 401:
                            err_msg = (
                                f"❌ API key invalid hai ({provider.upper()}). "
                                "Settings mein sahi key daalo."
                            )
                        elif status == 402:
                            err_msg = (
                                f"⚠️ {provider.upper()} credits khatam ho gaye. "
                                "Account recharge karein ya doosra model choose karein."
                            )
                        elif status == 429:
                            err_msg = (
                                f"⚠️ {provider.upper()} rate limit ya quota khatam ho gayi. "
                                "Thodi der baad try karein ya doosra model choose karein."
                            )
                        elif status == 400:
                            err_msg = (
                                f"❌ {provider.upper()} ne request reject ki (400). "
                                f"Model name check karein: {selected_model}. "
                                f"Detail: {str(err_data)[:200]}"
                            )
                        elif status in (502, 503):
                            err_msg = (
                                f"⚠️ {provider.upper()} server abhi busy/down hai ({status}). "
                                "Thodi der baad try karein."
                            )
                        else:
                            err_msg = (
                                f"❌ {provider.upper()} API error {status}. "
                                f"Detail: {str(err_data)[:200]}"
                            )

                        print(f"[LLM Stream] HTTP {status}: {err_data}")
                        # User ke own keys fail hue → system fallback NAHI
                        if has_own_keys:
                            yield StreamChunk(content=err_msg, done=True)
                        else:
                            yield StreamChunk(content=err_msg, done=True)
                        return

                    # ── Line-by-line streaming parse ──────────────────────────
                    async for line in stream_response.aiter_lines():
                        if not line:
                            continue

                        if provider == "anthropic":
                            if not line.startswith("data: "):
                                continue
                            raw = line[6:]
                            try:
                                data = json.loads(raw)
                                event_type = data.get("type", "")
                                if event_type == "content_block_delta":
                                    delta = data.get("delta", {}).get("text", "")
                                    delta = ResponseFormatter.clean(delta)
                                    if delta:
                                        yield StreamChunk(content=delta, done=False)
                                elif event_type == "error":
                                    err = data.get("error", {})
                                    err_msg = f"❌ Anthropic error: {err.get('type','?')} — {err.get('message','?')}"
                                    print(f"[LLM Stream] Anthropic SSE error: {err}")
                                    yield StreamChunk(content=err_msg, done=True)
                                    return
                                elif event_type == "message_stop":
                                    yield StreamChunk(content="", done=True)
                                    return
                            except json.JSONDecodeError:
                                continue

                        elif provider == "gemini":
                            if not line.startswith("data: "):
                                continue
                            raw = line[6:].strip()
                            if not raw:
                                continue
                            try:
                                data = json.loads(raw)
                                # Error check
                                if "error" in data:
                                    err = data["error"]
                                    err_msg = f"❌ Gemini error {err.get('code','?')}: {err.get('message','?')}"
                                    print(f"[LLM Stream] Gemini error in stream: {err}")
                                    yield StreamChunk(content=err_msg, done=True)
                                    return
                                candidates = data.get("candidates", [])
                                if not candidates:
                                    continue
                                finish_reason = candidates[0].get("finishReason", "")
                                if finish_reason in ("SAFETY", "RECITATION"):
                                    yield StreamChunk(
                                        content=f"⚠️ Gemini ne content block kiya (reason: {finish_reason})",
                                        done=True
                                    )
                                    return
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts:
                                    delta = parts[0].get("text", "")
                                    delta = ResponseFormatter.clean(delta)
                                    if delta:
                                        yield StreamChunk(content=delta, done=False)
                            except json.JSONDecodeError:
                                continue

                        else:  # openai / openrouter
                            if not line.startswith("data: "):
                                continue
                            raw = line[6:]
                            if raw.strip() == "[DONE]":
                                yield StreamChunk(content="", done=True)
                                return
                            try:
                                data  = json.loads(raw)
                                # OpenRouter error in stream body
                                if "error" in data:
                                    err = data["error"]
                                    err_msg = f"❌ {provider.upper()} error: {err.get('message', str(err))[:200]}"
                                    print(f"[LLM Stream] {provider} error chunk: {err}")
                                    yield StreamChunk(content=err_msg, done=True)
                                    return
                                delta = data["choices"][0]["delta"].get("content", "")
                                delta = ResponseFormatter.clean(delta)
                                if delta:
                                    yield StreamChunk(content=delta, done=False)
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue

        except Exception as e:
            err_msg = f"❌ Connection/network error ({provider}): {e}"
            print(f"[LLM Stream] Exception: {e}")
            yield StreamChunk(content=err_msg, done=True)

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

        reflection_prompt = f"""You are improving an AI code analysis response.
User QUESTION: {user_message}
RESPONSE (first 1500 chars): {response[:1500]}

IMPORTANT:
- Never shorten the response
- Preserve all technical details
- Preserve file names
- Preserve counts

STRICT RULES:
- NEVER shorten the response
- NEVER summarize aggressively
- NEVER remove files
- NEVER remove counts
- NEVER remove technical details
- NEVER remove architecture insights
- Keep the answer detailed and structured
- Preserve markdown formatting
TASK:
Return a polished improved version of the SAME response.

If the response is already strong,
return it with minimal edits.
"""

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
            if len(critique) < len(response) * 0.7:
                return response

            critique = critique.replace("INADEQUATE", "")
            critique = critique.replace("Improved version:", "").strip()
            if len(critique) < len(response) * 0.7:
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

        if "<answer>" in response and "</answer>" in response:
            start = response.find("<answer>") + len("<answer>")
            end   = response.find("</answer>")
            return response[start:end].strip()
        return response

    # ── Context helpers ─────────────────────────────────────────────────────

    def _format_context_trimmed(self, ctx: Dict, max_chars: int = 16000) -> str:
        """Format graph context with token-aware trimming."""
        lines = []

        priority_keys = ["deep_function_analysis", "deep_file_analysis", "deep_branches", "deep_exception_chain"]
        for key in priority_keys:
            if key in ctx:
                lines.append(f"{key}: {ctx[key]}")
        for key, val in ctx.items():
            if key in priority_keys:
                continue
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