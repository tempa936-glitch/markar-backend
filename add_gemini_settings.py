import os
import re

# 1. Update app/core/llm_settings.py
file_path_settings = r"d:\Makar.ai\Backend\MarkarServer\app\core\llm_settings.py"
with open(file_path_settings, "r", encoding="utf-8") as f:
    content = f.read()

# Add gemini_key to init_llm_settings_db
db_init_old = """
        CREATE TABLE IF NOT EXISTS user_llm_settings (
            user_id          TEXT PRIMARY KEY,
            openai_key       TEXT,
            anthropic_key    TEXT,
            openrouter_key   TEXT,
            preferred_model  TEXT DEFAULT 'meta-llama/llama-3.3-70b-instruct:free',
            router_model     TEXT DEFAULT 'mistralai/mistral-7b-instruct:free',
            use_own_keys     INTEGER DEFAULT 0,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );
"""

db_init_new = """
        CREATE TABLE IF NOT EXISTS user_llm_settings (
            user_id          TEXT PRIMARY KEY,
            openai_key       TEXT,
            anthropic_key    TEXT,
            openrouter_key   TEXT,
            gemini_key       TEXT,
            preferred_model  TEXT DEFAULT 'meta-llama/llama-3.3-70b-instruct:free',
            router_model     TEXT DEFAULT 'mistralai/mistral-7b-instruct:free',
            use_own_keys     INTEGER DEFAULT 0,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );
        
        -- Try to add gemini_key if table already exists
        BEGIN TRY
            ALTER TABLE user_llm_settings ADD COLUMN gemini_key TEXT;
        END TRY
        BEGIN CATCH
            -- Ignore if column already exists
        END CATCH;
"""

# SQLite doesn't have TRY...CATCH. The easiest way is to catch it in python.
# We will do it with executescript. But executescript fails the whole transaction if one statement fails.
# Let's fix the db init in Python.
db_init_py_old = """
def init_llm_settings_db():
    with _get_conn() as conn:
        conn.executescript(\"\"\"
        CREATE TABLE IF NOT EXISTS user_llm_settings (
            user_id          TEXT PRIMARY KEY,
            openai_key       TEXT,
            anthropic_key    TEXT,
            openrouter_key   TEXT,
            preferred_model  TEXT DEFAULT 'meta-llama/llama-3.3-70b-instruct:free',
            router_model     TEXT DEFAULT 'mistralai/mistral-7b-instruct:free',
            use_own_keys     INTEGER DEFAULT 0,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS llm_usage (
"""

db_init_py_new = """
def init_llm_settings_db():
    with _get_conn() as conn:
        conn.executescript(\"\"\"
        CREATE TABLE IF NOT EXISTS user_llm_settings (
            user_id          TEXT PRIMARY KEY,
            openai_key       TEXT,
            anthropic_key    TEXT,
            openrouter_key   TEXT,
            gemini_key       TEXT,
            preferred_model  TEXT DEFAULT 'meta-llama/llama-3.3-70b-instruct:free',
            router_model     TEXT DEFAULT 'mistralai/mistral-7b-instruct:free',
            use_own_keys     INTEGER DEFAULT 0,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS llm_usage (
\"\"\")
        try:
            conn.execute("ALTER TABLE user_llm_settings ADD COLUMN gemini_key TEXT;")
        except Exception:
            pass
        
        conn.executescript(\"\"\"
"""
content = content.replace(db_init_py_old, db_init_py_new)

# Update get_user_llm_settings defaults
content = content.replace(
    '"openai_key": None, "anthropic_key": None, "openrouter_key": None,',
    '"openai_key": None, "anthropic_key": None, "openrouter_key": None, "gemini_key": None,'
)

# Update get_user_llm_settings return
content = content.replace(
    '"openrouter_key": _mask_key(row["openrouter_key"]),',
    '"openrouter_key": _mask_key(row["openrouter_key"]),\n        "gemini_key": _mask_key(row.get("gemini_key")),'
)

# Update get_user_llm_keys defaults
content = content.replace(
    '"openrouter_key": os.getenv("OPENROUTER_API_KEY", ""),',
    '"openrouter_key": os.getenv("OPENROUTER_API_KEY", ""),\n            "gemini_key": os.getenv("GEMINI_API_KEY", ""),'
)

# Update get_user_llm_keys return
content = content.replace(
    '"openrouter_key": row["openrouter_key"] if use_own else os.getenv("OPENROUTER_API_KEY", ""),',
    '"openrouter_key": row["openrouter_key"] if use_own else os.getenv("OPENROUTER_API_KEY", ""),\n        "gemini_key": row.get("gemini_key") if use_own else os.getenv("GEMINI_API_KEY", ""),'
)

# Update save_user_llm_settings definition
content = content.replace(
    'def save_user_llm_settings(user_id: str, openai_key=None, anthropic_key=None,\n                            openrouter_key=None, preferred_model=None,',
    'def save_user_llm_settings(user_id: str, openai_key=None, anthropic_key=None,\n                            openrouter_key=None, gemini_key=None, preferred_model=None,'
)

# Update save_user_llm_settings columns
content = content.replace(
    '("openrouter_key", openrouter_key), ("preferred_model", preferred_model),',
    '("openrouter_key", openrouter_key), ("gemini_key", gemini_key), ("preferred_model", preferred_model),'
)

# Update save_user_llm_settings INSERT query
content = content.replace(
    '(user_id, openai_key, anthropic_key, openrouter_key,',
    '(user_id, openai_key, anthropic_key, openrouter_key, gemini_key,'
)
content = content.replace(
    'VALUES (?,?,?,?,?,?,?,?,?)',
    'VALUES (?,?,?,?,?,?,?,?,?,?)'
)
content = content.replace(
    'openai_key or None, anthropic_key or None, openrouter_key or None,',
    'openai_key or None, anthropic_key or None, openrouter_key or None, gemini_key or None,'
)

# Add Gemini models to AVAILABLE_MODELS
models_old = """AVAILABLE_MODELS = ["""
models_new = """AVAILABLE_MODELS = [
    {"id": "google/gemini-1.5-flash",                "name": "Gemini 1.5 Flash",      "provider": "Google",    "free": False},
    {"id": "google/gemini-1.5-pro",                  "name": "Gemini 1.5 Pro",        "provider": "Google",    "free": False},
    {"id": "google/gemini-2.0-flash",                "name": "Gemini 2.0 Flash",      "provider": "Google",    "free": False},"""
content = content.replace(models_old, models_new)

# Clean up duplicate gemini 2.0 flash if it existed already
# We know it exists already on line 247:
# {"id": "google/gemini-2.0-flash",                "name": "Gemini 2.0 Flash",      "provider": "Google",    "free": False},
# Let's remove the old one.
content = content.replace('    {"id": "google/gemini-2.0-flash",                "name": "Gemini 2.0 Flash",      "provider": "Google",    "free": False},\n', '')

with open(file_path_settings, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated llm_settings.py")

# 2. Update app/routes/settings.py
file_path_routes = r"d:\Makar.ai\Backend\MarkarServer\app\routes\settings.py"
with open(file_path_routes, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    'openrouter_key:  Optional[str] = None',
    'openrouter_key:  Optional[str] = None\n    gemini_key:      Optional[str] = None'
)

content = content.replace(
    'openrouter_key=req.openrouter_key,',
    'openrouter_key=req.openrouter_key,\n        gemini_key=req.gemini_key,'
)

content = content.replace(
    'openrouter_key="",',
    'openrouter_key="",\n        gemini_key="",'
)

with open(file_path_routes, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated settings.py")
