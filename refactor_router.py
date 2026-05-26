import os

file_path = r"d:\Makar.ai\Backend\MarkarServer\app\agents\auto_router.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_route = """
    async def route(self, message: str, model: str = None) -> Dict:
        \"\"\"
        Route message to correct agent intent.
        Returns: {"intent": str, "confidence": float, "method": "llm"|"keyword"}
        \"\"\"
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
        \"\"\"Fast LLM classification call.\"\"\"
        import httpx

        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            return None

        fast_model = model or os.getenv(
            "MARKAR_ROUTER_MODEL",
            "mistralai/mistral-7b-instruct:free"
        )
"""

new_route = """
    async def route(self, message: str, model: str = None, user_id: str = None) -> Dict:
        \"\"\"
        Route message to correct agent intent.
        Returns: {"intent": str, "confidence": float, "method": "llm"|"keyword"}
        \"\"\"
        # Check cache
        cache_key = message[:100].lower().strip()
        if cache_key in self._cache:
            return {**self._cache[cache_key], "method": "cache"}

        # Try LLM routing
        llm_result = await self._llm_route(message, model, user_id)
        if llm_result and llm_result.get("confidence", 0) >= 0.6:
            llm_result["method"] = "llm"
            self._cache[cache_key] = llm_result
            return llm_result

        # Fallback to keyword scoring
        kw_result = self._keyword_route(message)
        kw_result["method"] = "keyword"
        return kw_result

    async def _llm_route(self, message: str, model: str = None, user_id: str = None) -> Optional[Dict]:
        \"\"\"Fast LLM classification call.\"\"\"
        import httpx

        api_key = os.getenv("OPENROUTER_API_KEY", "")
        url = "https://openrouter.ai/api/v1/chat/completions"
        provider = "openrouter"
        fast_model = model or os.getenv("MARKAR_ROUTER_MODEL", "mistralai/mistral-7b-instruct:free")
        if fast_model == "openrouter/free":
            fast_model = "meta-llama/llama-3.3-70b-instruct:free"

        if user_id:
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
                pass

        if not api_key:
            return None
"""

old_http = """
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
"""

new_http = """
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            }
            if provider == "openrouter":
                headers["HTTP-Referer"] = "https://markarai.netlify.app"
                headers["X-Title"] = "Markar.ai Router"
                
            messages = [
                {"role": "system", "content": self.ROUTER_SYSTEM},
                {"role": "user",   "content": f"Message: {message}"},
            ]
            
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

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, headers=headers, json=json_body)

            data = response.json()
            if response.status_code != 200:
                print(f"[AutoRouter] HTTP Error {response.status_code}: {data}")
                return None

            if provider == "anthropic":
                content = data.get("content", [{}])[0].get("text", "")
            else:
                content = data["choices"][0]["message"].get("content") or ""
"""

if old_route in content:
    content = content.replace(old_route, new_route)
else:
    print("Could not find old_route")

if old_http in content:
    content = content.replace(old_http, new_http)
else:
    print("Could not find old_http")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Replaced auto_router content successfully.")
