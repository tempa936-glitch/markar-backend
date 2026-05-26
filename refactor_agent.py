import os

file_path = r"d:\Makar.ai\Backend\MarkarServer\app\agents\base_agent.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# We'll replace the body of `ask_llm_async`
old_ask_llm_async = """
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
        \"\"\"
        Async LLM call with:
        - Token-aware context trimming
        - Conversation history injection
        - Exponential backoff retry
        - Structured error handling
        \"\"\"
        import httpx

        try:
            from app.core.llm_settings import get_user_llm_keys
            user_keys = get_user_llm_keys(self.user_id)
            api_key = user_keys.get("openrouter_key") or os.getenv("OPENROUTER_API_KEY", "")
            
            # If model is not provided or it's just a default fallback like "openrouter/free"
            # we should use the user's preferred_model if available.
            if not model or model == "openrouter/free":
                model = user_keys.get("preferred_model")
                
            # If use_own_keys is true, always respect user's preferred_model unless the frontend
            # explicitly passed a different specific model (not the default free one).
            if user_keys.get("use_own_keys") and (not model or model == "openrouter/free"):
                model = user_keys.get("preferred_model")
                
        except Exception:
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
            full_user_content += f"=== CONVERSATION HISTORY ===\\n{history_text}\\n\\n"
        if context_text:
            full_user_content += f"=== CODEBASE KNOWLEDGE GRAPH ===\\n{context_text}\\n=================================\\n\\n"
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
                text = ResponseFormatter.clean(text)
                if not text:
                    return self._fallback_response(graph_context)
                print(f"[LLM] OK — model={selected_model} attempt={attempt+1}")
                try:
                    import time as _time
                    from app.core.llm_settings import track_usage
                    usage = data.get("usage", {})
                    track_usage(
                        user_id=self.user_id,
                        model=selected_model,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
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
                wait = 2 ** attempt
                print(f"[LLM] Attempt {attempt+1} failed: {e} — retrying in {wait}s")
                await asyncio.sleep(wait)

        print(f"[LLM] All {retries} retries failed: {last_error}")
        return self._fallback_response(graph_context)
"""

new_ask_llm_async = """
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
        \"\"\"
        Async LLM call with:
        - Token-aware context trimming
        - Conversation history injection
        - Exponential backoff retry
        - Structured error handling
        - Dynamic Provider Routing
        \"\"\"
        import httpx

        try:
            from app.core.llm_settings import get_user_llm_keys
            user_keys = get_user_llm_keys(self.user_id)
            selected_model = model or os.getenv("MARKAR_LLM_MODEL", "mistralai/mistral-7b-instruct:free")
            if selected_model == "openrouter/free":
                selected_model = "meta-llama/llama-3.3-70b-instruct:free"

            if user_keys.get("use_own_keys"):
                if selected_model.startswith("openai/"):
                    api_key = user_keys.get("openai_key")
                    url = "https://api.openai.com/v1/chat/completions"
                    provider = "openai"
                elif selected_model.startswith("anthropic/"):
                    api_key = user_keys.get("anthropic_key")
                    url = "https://api.anthropic.com/v1/messages"
                    provider = "anthropic"
                else:
                    api_key = user_keys.get("openrouter_key")
                    url = "https://openrouter.ai/api/v1/chat/completions"
                    provider = "openrouter"
            else:
                api_key = os.getenv("OPENROUTER_API_KEY", "")
                url = "https://openrouter.ai/api/v1/chat/completions"
                provider = "openrouter"
                
            if not api_key and provider != "openrouter":
                api_key = user_keys.get("openrouter_key") or os.getenv("OPENROUTER_API_KEY", "")
                url = "https://openrouter.ai/api/v1/chat/completions"
                provider = "openrouter"

        except Exception:
            api_key = os.getenv("OPENROUTER_API_KEY", "")
            url = "https://openrouter.ai/api/v1/chat/completions"
            provider = "openrouter"
            selected_model = model or "meta-llama/llama-3.3-70b-instruct:free"

        if not api_key:
            return self._fallback_response(graph_context)

        context_text  = self._format_context_trimmed(graph_context)
        history_text  = ""
        if include_history and self.conv_store and self.session_id:
            history_text = self.conv_store.get_context_text(
                self.session_id, last_n=self.MAX_HISTORY_TURNS
            )

        full_user_content = ""
        if history_text:
            full_user_content += f"=== CONVERSATION HISTORY ===\\n{history_text}\\n\\n"
        if context_text:
            full_user_content += f"=== CODEBASE KNOWLEDGE GRAPH ===\\n{context_text}\\n=================================\\n\\n"
        full_user_content += f"User: {user_message}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": full_user_content},
        ]

        if provider == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            json_body = {
                "model": selected_model.replace("anthropic/", ""),
                "system": system_prompt,
                "messages": [{"role": "user", "content": full_user_content}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        else:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
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

        last_error = None
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await client.post(url, headers=headers, json=json_body)

                data = response.json()
                if response.status_code != 200:
                    raise ValueError(f"LLM API error {response.status_code}: {data}")

                if provider == "anthropic":
                    text = data.get("content", [{}])[0].get("text", "")
                else:
                    text = data["choices"][0]["message"]["content"]
                    
                text = ResponseFormatter.clean(text)
                if not text:
                    return self._fallback_response(graph_context)
                    
                print(f"[LLM] OK — model={selected_model} attempt={attempt+1}")
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
                wait = 2 ** attempt
                print(f"[LLM] Attempt {attempt+1} failed: {e} — retrying in {wait}s")
                import asyncio
                await asyncio.sleep(wait)

        print(f"[LLM] All {retries} retries failed: {last_error}")
        return self._fallback_response(graph_context)
"""

old_ask_llm_stream = """
    async def ask_llm_stream(
        self,
        system_prompt: str,
        user_message: str,
        graph_context: Dict,
        model: str = None,
        include_history: bool = True,
    ) -> AsyncGenerator[StreamChunk, None]:
        \"\"\"
        Server-Sent Events streaming LLM call.
        Yields StreamChunk objects as tokens arrive.
        \"\"\"
        import httpx
        import json

        try:
            from app.core.llm_settings import get_user_llm_keys
            user_keys = get_user_llm_keys(self.user_id)
            api_key = user_keys.get("openrouter_key") or os.getenv("OPENROUTER_API_KEY", "")
            
            if not model or model == "openrouter/free":
                model = user_keys.get("preferred_model")
                
            if user_keys.get("use_own_keys") and (not model or model == "openrouter/free"):
                model = user_keys.get("preferred_model")
                
        except Exception:
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
            full_user_content += f"=== CONVERSATION HISTORY ===\\n{history_text}\\n\\n"
        if context_text:
            full_user_content += f"=== CODEBASE KNOWLEDGE GRAPH ===\\n{context_text}\\n=================================\\n\\n"
        full_user_content += f"User: {user_message}"

        selected_model = model or os.getenv("MARKAR_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        if selected_model == "openrouter/free":
            selected_model = "meta-llama/llama-3.3-70b-instruct:free"

        print(f"[LLM Stream] Using model={selected_model} for user={self.user_id}")

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
                            delta = ResponseFormatter.clean(delta)
                            if delta:
                                yield StreamChunk(content=delta, done=False)
                        except Exception:
                            continue

        except Exception as e:
            print(f"[LLM Stream] Failed: {e}")
            yield StreamChunk(content=f"[Streaming error: {e}]", done=True)
"""

new_ask_llm_stream = """
    async def ask_llm_stream(
        self,
        system_prompt: str,
        user_message: str,
        graph_context: Dict,
        model: str = None,
        include_history: bool = True,
    ) -> AsyncGenerator[StreamChunk, None]:
        \"\"\"
        Server-Sent Events streaming LLM call.
        Yields StreamChunk objects as tokens arrive.
        \"\"\"
        import httpx
        import json

        try:
            from app.core.llm_settings import get_user_llm_keys
            user_keys = get_user_llm_keys(self.user_id)
            selected_model = model or os.getenv("MARKAR_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
            if selected_model == "openrouter/free":
                selected_model = "meta-llama/llama-3.3-70b-instruct:free"

            if user_keys.get("use_own_keys"):
                if selected_model.startswith("openai/"):
                    api_key = user_keys.get("openai_key")
                    url = "https://api.openai.com/v1/chat/completions"
                    provider = "openai"
                elif selected_model.startswith("anthropic/"):
                    api_key = user_keys.get("anthropic_key")
                    url = "https://api.anthropic.com/v1/messages"
                    provider = "anthropic"
                else:
                    api_key = user_keys.get("openrouter_key")
                    url = "https://openrouter.ai/api/v1/chat/completions"
                    provider = "openrouter"
            else:
                api_key = os.getenv("OPENROUTER_API_KEY", "")
                url = "https://openrouter.ai/api/v1/chat/completions"
                provider = "openrouter"
                
            if not api_key and provider != "openrouter":
                api_key = user_keys.get("openrouter_key") or os.getenv("OPENROUTER_API_KEY", "")
                url = "https://openrouter.ai/api/v1/chat/completions"
                provider = "openrouter"

        except Exception:
            api_key = os.getenv("OPENROUTER_API_KEY", "")
            url = "https://openrouter.ai/api/v1/chat/completions"
            provider = "openrouter"
            selected_model = model or "meta-llama/llama-3.3-70b-instruct:free"

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
            full_user_content += f"=== CONVERSATION HISTORY ===\\n{history_text}\\n\\n"
        if context_text:
            full_user_content += f"=== CODEBASE KNOWLEDGE GRAPH ===\\n{context_text}\\n=================================\\n\\n"
        full_user_content += f"User: {user_message}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": full_user_content},
        ]

        if provider == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            json_body = {
                "model": selected_model.replace("anthropic/", ""),
                "system": system_prompt,
                "messages": [{"role": "user", "content": full_user_content}],
                "max_tokens": 2048,
                "temperature": 0.2,
                "stream": True,
            }
        else:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
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

        print(f"[LLM Stream] Using model={selected_model} (provider={provider}) for user={self.user_id}")

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, headers=headers, json=json_body) as stream_response:
                    async for line in stream_response.aiter_lines():
                        if not line:
                            continue
                        
                        if provider == "anthropic":
                            if line.startswith("data: "):
                                raw = line[6:]
                                try:
                                    data = json.loads(raw)
                                    if data.get("type") == "content_block_delta":
                                        delta = data["delta"].get("text", "")
                                        delta = ResponseFormatter.clean(delta)
                                        if delta:
                                            yield StreamChunk(content=delta, done=False)
                                except Exception:
                                    continue
                        else:
                            if not line.startswith("data: "):
                                continue
                            raw = line[6:]
                            if raw.strip() == "[DONE]":
                                yield StreamChunk(content="", done=True)
                                return
                            try:
                                data  = json.loads(raw)
                                delta = data["choices"][0]["delta"].get("content", "")
                                delta = ResponseFormatter.clean(delta)
                                if delta:
                                    yield StreamChunk(content=delta, done=False)
                            except Exception:
                                continue

        except Exception as e:
            print(f"[LLM Stream] Failed: {e}")
            yield StreamChunk(content=f"[Streaming error: {e}]", done=True)
"""

if old_ask_llm_async in content:
    content = content.replace(old_ask_llm_async, new_ask_llm_async)
else:
    print("Could not find old_ask_llm_async")

if old_ask_llm_stream in content:
    content = content.replace(old_ask_llm_stream, new_ask_llm_stream)
else:
    print("Could not find old_ask_llm_stream")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Replaced content successfully.")
