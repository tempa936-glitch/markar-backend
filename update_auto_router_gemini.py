import os

file_path = r"d:\Makar.ai\Backend\MarkarServer\app\agents\auto_router.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_llm_route = """
            try:
                from app.core.llm_settings import get_user_llm_keys
                user_keys = get_user_llm_keys(user_id)
                if user_keys.get("use_own_keys"):
                    if fast_model.startswith("openai/"):
                        api_key = user_keys.get("openai_key")
                        url = "https://api.openai.com/v1/chat/completions"
                        provider = "openai"
                    elif fast_model.startswith("anthropic/"):
                        api_key = user_keys.get("anthropic_key")
                        url = "https://api.anthropic.com/v1/messages"
                        provider = "anthropic"
                    else:
                        api_key = user_keys.get("openrouter_key")
                        provider = "openrouter"
                if not api_key and provider != "openrouter":
                    api_key = user_keys.get("openrouter_key") or os.getenv("OPENROUTER_API_KEY", "")
                    url = "https://openrouter.ai/api/v1/chat/completions"
                    provider = "openrouter"
            except Exception:
"""

new_llm_route = """
            try:
                from app.core.llm_settings import get_user_llm_keys
                user_keys = get_user_llm_keys(user_id)
                if user_keys.get("use_own_keys"):
                    if fast_model.startswith("openai/"):
                        api_key = user_keys.get("openai_key")
                        url = "https://api.openai.com/v1/chat/completions"
                        provider = "openai"
                    elif fast_model.startswith("anthropic/"):
                        api_key = user_keys.get("anthropic_key")
                        url = "https://api.anthropic.com/v1/messages"
                        provider = "anthropic"
                    elif fast_model.startswith("google/") or fast_model.startswith("gemini"):
                        api_key = user_keys.get("gemini_key")
                        provider = "gemini"
                        gemini_model = fast_model.replace("google/", "")
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={api_key}"
                    else:
                        api_key = user_keys.get("openrouter_key")
                        provider = "openrouter"
                if not api_key and provider != "openrouter":
                    api_key = user_keys.get("openrouter_key") or os.getenv("OPENROUTER_API_KEY", "")
                    url = "https://openrouter.ai/api/v1/chat/completions"
                    provider = "openrouter"
            except Exception:
"""
content = content.replace(old_llm_route, new_llm_route)


old_http = """
            if provider == "anthropic":
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                json_body = {
                    "model": fast_model.replace("anthropic/", ""),
                    "system": self.ROUTER_SYSTEM,
                    "messages": [{"role": "user", "content": f"Message: {message}"}],
                    "max_tokens": 80,
                    "temperature": 0.0,
                }
            else:
                json_body = {
                    "model": fast_model.replace("openai/", "") if provider == "openai" else fast_model,
                    "messages": messages,
                    "max_tokens": 80,
                    "temperature": 0.0,
                }
"""

new_http = """
            if provider == "anthropic":
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                json_body = {
                    "model": fast_model.replace("anthropic/", ""),
                    "system": self.ROUTER_SYSTEM,
                    "messages": [{"role": "user", "content": f"Message: {message}"}],
                    "max_tokens": 80,
                    "temperature": 0.0,
                }
            elif provider == "gemini":
                headers = {
                    "Content-Type": "application/json"
                }
                json_body = {
                    "systemInstruction": { "parts": [{"text": self.ROUTER_SYSTEM}] },
                    "contents": [
                        {"role": "user", "parts": [{"text": f"Message: {message}"}]}
                    ],
                    "generationConfig": {
                        "temperature": 0.0,
                        "maxOutputTokens": 80
                    }
                }
            else:
                json_body = {
                    "model": fast_model.replace("openai/", "") if provider == "openai" else fast_model,
                    "messages": messages,
                    "max_tokens": 80,
                    "temperature": 0.0,
                }
"""
content = content.replace(old_http, new_http)


old_parse = """
            if provider == "anthropic":
                content = data.get("content", [{}])[0].get("text", "")
            else:
                content = data["choices"][0]["message"].get("content") or ""
"""

new_parse = """
            if provider == "anthropic":
                content = data.get("content", [{}])[0].get("text", "")
            elif provider == "gemini":
                content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            else:
                content = data["choices"][0]["message"].get("content") or ""
"""
content = content.replace(old_parse, new_parse)


with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated auto_router.py with Gemini logic")
