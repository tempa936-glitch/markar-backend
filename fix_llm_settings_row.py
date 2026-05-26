import os

file_path = r"d:\Makar.ai\Backend\MarkarServer\app\core\llm_settings.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# I will just write a clean version of the two functions and replace the old ones.

import re

# find get_user_llm_settings definition and replace up to get_user_llm_keys
func1_pattern = r"def get_user_llm_settings\(user_id: str\) -> Dict:.*?(?=def get_user_llm_keys\(user_id: str\) -> Dict:)"
func1_new = """def get_user_llm_settings(user_id: str) -> Dict:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_llm_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        
    if not row:
        return {
            "user_id": user_id,
            "openai_key": None, "anthropic_key": None, "openrouter_key": None, "gemini_key": None,
            "preferred_model": "meta-llama/llama-3.3-70b-instruct:free",
            "router_model": "mistralai/mistral-7b-instruct:free",
            "use_own_keys": False,
        }
        
    row_dict = dict(row)
    return {
        "user_id": row["user_id"],
        "openai_key": _mask_key(row["openai_key"]),
        "anthropic_key": _mask_key(row["anthropic_key"]),
        "openrouter_key": _mask_key(row["openrouter_key"]),
        "gemini_key": _mask_key(row_dict.get("gemini_key")),
        "preferred_model": row["preferred_model"],
        "router_model": row["router_model"],
        "use_own_keys": bool(row["use_own_keys"]),
    }


"""
content = re.sub(func1_pattern, func1_new, content, flags=re.DOTALL)

# find get_user_llm_keys definition and replace up to save_user_llm_settings
func2_pattern = r"def get_user_llm_keys\(user_id: str\) -> Dict:.*?(?=def save_user_llm_settings\()"
func2_new = """def get_user_llm_keys(user_id: str) -> Dict:
    \"\"\"Actual unmasked keys — sirf LLM calls ke liye.\"\"\"
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_llm_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        
    if not row:
        return {
            "openai_key": os.getenv("OPENAI_API_KEY", ""),
            "anthropic_key": os.getenv("ANTHROPIC_API_KEY", ""),
            "openrouter_key": os.getenv("OPENROUTER_API_KEY", ""),
            "gemini_key": os.getenv("GEMINI_API_KEY", ""),
            "preferred_model": os.getenv("MARKAR_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
            "router_model": os.getenv("MARKAR_ROUTER_MODEL", "mistralai/mistral-7b-instruct:free"),
            "use_own_keys": False,
        }
        
    row_dict = dict(row)
    use_own = bool(row["use_own_keys"])
    return {
        "openai_key": row["openai_key"] if use_own else os.getenv("OPENAI_API_KEY", ""),
        "anthropic_key": row["anthropic_key"] if use_own else os.getenv("ANTHROPIC_API_KEY", ""),
        "openrouter_key": row["openrouter_key"] if use_own else os.getenv("OPENROUTER_API_KEY", ""),
        "gemini_key": row_dict.get("gemini_key") if use_own else os.getenv("GEMINI_API_KEY", ""),
        "preferred_model": row["preferred_model"],
        "router_model": row["router_model"],
        "use_own_keys": use_own,
    }


"""
content = re.sub(func2_pattern, func2_new, content, flags=re.DOTALL)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated llm_settings.py safely.")
