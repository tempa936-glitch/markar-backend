import os

file_path = r"d:\Makar.ai\Backend\MarkarServer\app\agents\base_agent.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# --- update ask_llm_async ---

old_async_router = """
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
"""

new_async_router = """
            if user_keys.get("use_own_keys"):
                if selected_model.startswith("openai/"):
                    api_key = user_keys.get("openai_key")
                    url = "https://api.openai.com/v1/chat/completions"
                    provider = "openai"
                elif selected_model.startswith("anthropic/"):
                    api_key = user_keys.get("anthropic_key")
                    url = "https://api.anthropic.com/v1/messages"
                    provider = "anthropic"
                elif selected_model.startswith("google/") or selected_model.startswith("gemini"):
                    api_key = user_keys.get("gemini_key")
                    provider = "gemini"
                    gemini_model = selected_model.replace("google/", "")
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={api_key}"
                else:
                    api_key = user_keys.get("openrouter_key")
                    url = "https://openrouter.ai/api/v1/chat/completions"
                    provider = "openrouter"
"""

content = content.replace(old_async_router, new_async_router)

old_async_payload = """
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
"""

new_async_payload = """
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
        elif provider == "gemini":
            headers = {
                "Content-Type": "application/json"
            }
            json_body = {
                "systemInstruction": { "parts": [{"text": system_prompt}] },
                "contents": [
                    {"role": "user", "parts": [{"text": full_user_content}]}
                ],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens
                }
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
"""
content = content.replace(old_async_payload, new_async_payload)

old_async_parse = """
                if provider == "anthropic":
                    text = data.get("content", [{}])[0].get("text", "")
                else:
                    text = data["choices"][0]["message"]["content"]
"""

new_async_parse = """
                if provider == "anthropic":
                    text = data.get("content", [{}])[0].get("text", "")
                elif provider == "gemini":
                    text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                else:
                    text = data["choices"][0]["message"]["content"]
"""
content = content.replace(old_async_parse, new_async_parse)


# --- update ask_llm_stream ---

old_stream_router = """
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
"""

new_stream_router = """
            if user_keys.get("use_own_keys"):
                if selected_model.startswith("openai/"):
                    api_key = user_keys.get("openai_key")
                    url = "https://api.openai.com/v1/chat/completions"
                    provider = "openai"
                elif selected_model.startswith("anthropic/"):
                    api_key = user_keys.get("anthropic_key")
                    url = "https://api.anthropic.com/v1/messages"
                    provider = "anthropic"
                elif selected_model.startswith("google/") or selected_model.startswith("gemini"):
                    api_key = user_keys.get("gemini_key")
                    provider = "gemini"
                    gemini_model = selected_model.replace("google/", "")
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:streamGenerateContent?alt=sse&key={api_key}"
                else:
                    api_key = user_keys.get("openrouter_key")
                    url = "https://openrouter.ai/api/v1/chat/completions"
                    provider = "openrouter"
"""
content = content.replace(old_stream_router, new_stream_router)

old_stream_payload = """
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
"""

new_stream_payload = """
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
        elif provider == "gemini":
            headers = {
                "Content-Type": "application/json"
            }
            json_body = {
                "systemInstruction": { "parts": [{"text": system_prompt}] },
                "contents": [
                    {"role": "user", "parts": [{"text": full_user_content}]}
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 2048
                }
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
"""
content = content.replace(old_stream_payload, new_stream_payload)

old_stream_parse = """
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
"""

new_stream_parse = """
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
                        elif provider == "gemini":
                            if line.startswith("data: "):
                                raw = line[6:]
                                if raw.strip() == "":
                                    continue
                                try:
                                    data = json.loads(raw)
                                    candidates = data.get("candidates", [])
                                    if candidates:
                                        parts = candidates[0].get("content", {}).get("parts", [])
                                        if parts:
                                            delta = parts[0].get("text", "")
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
"""
content = content.replace(old_stream_parse, new_stream_parse)


with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated base_agent.py with Gemini logic")
