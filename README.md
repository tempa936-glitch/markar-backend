# MarkarServer (FastAPI)

Minimal FastAPI project skeleton for MarkarServer.

Quick start

1. Create and activate a virtual environment:

```
python -m venv .venv
.
.venv\Scripts\activate
```

2. Install dependencies:

```
pip install -r requirements.txt
```

3. Run the dev server:

```
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

4. Run tests:

```
pytest -q
```
