"""
Trace Manager — Agent Execution Transparency.
Har agent run ka step-by-step trace store karo.

Events:
  agent_step     — agent ne kya decide kiya
  tool_call      — kaunsa tool call hua, result kya aaya
  graph_query    — Neo4j pe kya query gayi, kitna time laga
  llm_call       — LLM ko kya bheja, kya aaya, tokens
  routing        — AutoRouter ne intent kya detect kiya

GET /api/chat/trace/:session_id  se frontend timeline dikhayega.
"""
import os
import time
import json
import sqlite3
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict

DB_PATH = os.getenv("MARKAR_DB_PATH", "markar.db")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_trace_db():
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS trace_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id    TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            agent       TEXT DEFAULT '',
            tool_name   TEXT DEFAULT '',
            input_data  TEXT DEFAULT '{}',
            output_data TEXT DEFAULT '{}',
            status      TEXT DEFAULT 'success',
            latency_ms  REAL DEFAULT 0,
            token_count INTEGER DEFAULT 0,
            error       TEXT DEFAULT '',
            seq         INTEGER DEFAULT 0,
            created_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_trace_session
            ON trace_events(session_id, seq);
        CREATE INDEX IF NOT EXISTS idx_trace_id
            ON trace_events(trace_id);
        """)


# ── Trace Event Types ─────────────────────────────────────────────────────────

EVENT_ROUTING     = "routing"
EVENT_AGENT_STEP  = "agent_step"
EVENT_TOOL_CALL   = "tool_call"
EVENT_GRAPH_QUERY = "graph_query"
EVENT_LLM_CALL    = "llm_call"
EVENT_COMPLETE    = "complete"


@dataclass
class TraceEvent:
    trace_id:   str
    session_id: str
    event_type: str
    agent:      str  = ""
    tool_name:  str  = ""
    input_data: Dict = field(default_factory=dict)
    output_data: Dict = field(default_factory=dict)
    status:     str  = "success"
    latency_ms: float = 0.0
    token_count: int = 0
    error:      str  = ""
    seq:        int  = 0


class TraceManager:
    """
    Session ke liye execution trace collect karo.
    Thread-safe — multiple agents ek saath log kar sakte hain.
    """

    def __init__(self):
        init_trace_db()
        self._seq: Dict[str, int] = {}  # session_id → current seq

    def _next_seq(self, session_id: str) -> int:
        self._seq[session_id] = self._seq.get(session_id, 0) + 1
        return self._seq[session_id]

    def log(self, event: TraceEvent) -> None:
        if not event.seq:
            event.seq = self._next_seq(event.session_id)
        now = datetime.utcnow().isoformat()
        try:
            with _conn() as conn:
                conn.execute("""
                    INSERT INTO trace_events
                        (trace_id, session_id, event_type, agent, tool_name,
                         input_data, output_data, status, latency_ms,
                         token_count, error, seq, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.trace_id, event.session_id, event.event_type,
                    event.agent, event.tool_name,
                    json.dumps(event.input_data, default=str),
                    json.dumps(event.output_data, default=str),
                    event.status, event.latency_ms, event.token_count,
                    event.error, event.seq, now,
                ))
        except Exception as e:
            print(f"[Trace] Log failed: {e}")

    @contextmanager
    def span(
        self,
        session_id: str,
        trace_id: str,
        event_type: str,
        agent: str = "",
        tool_name: str = "",
        input_data: Dict = None,
    ):
        """
        Context manager — auto latency measure + log.

        Usage:
            with tracer.span(session_id, trace_id, EVENT_LLM_CALL,
                             agent="ask", input_data={"prompt": "..."}) as span:
                result = call_llm(...)
                span["output"] = {"tokens": 150, "answer": result[:100]}
        """
        start = time.time()
        ctx: Dict[str, Any] = {"output": {}, "token_count": 0, "status": "success"}
        try:
            yield ctx
        except Exception as e:
            ctx["status"] = "error"
            ctx["error"]  = str(e)[:400]
            raise
        finally:
            elapsed = (time.time() - start) * 1000
            event = TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type=event_type,
                agent=agent,
                tool_name=tool_name,
                input_data=input_data or {},
                output_data=ctx.get("output", {}),
                status=ctx.get("status", "success"),
                latency_ms=round(elapsed, 2),
                token_count=ctx.get("token_count", 0),
                error=ctx.get("error", ""),
            )
            self.log(event)

    # ── Read API ──────────────────────────────────────────────────────────

    def get_trace(self, session_id: str) -> Dict:
        """
        Session ka poora trace return karo — frontend timeline ke liye.
        """
        with _conn() as conn:
            rows = conn.execute("""
                SELECT * FROM trace_events
                WHERE session_id = ?
                ORDER BY seq ASC
            """, (session_id,)).fetchall()

        events = []
        total_latency = 0.0
        total_tokens  = 0
        agents_used   = set()

        for row in rows:
            e = dict(row)
            try:
                e["input_data"]  = json.loads(e["input_data"]  or "{}")
                e["output_data"] = json.loads(e["output_data"] or "{}")
            except Exception:
                pass
            events.append(e)
            total_latency += e.get("latency_ms", 0) or 0
            total_tokens  += e.get("token_count", 0) or 0
            if e.get("agent"):
                agents_used.add(e["agent"])

        # Build timeline — group by event type
        timeline = _build_timeline(events)

        return {
            "session_id":    session_id,
            "total_events":  len(events),
            "total_latency_ms": round(total_latency, 1),
            "total_tokens":  total_tokens,
            "agents_used":   list(agents_used),
            "events":        events,
            "timeline":      timeline,
        }

    def get_recent_traces(self, limit: int = 20) -> List[Dict]:
        """Recent sessions ka summary."""
        with _conn() as conn:
            rows = conn.execute("""
                SELECT session_id,
                       COUNT(*) as event_count,
                       SUM(latency_ms) as total_ms,
                       SUM(token_count) as total_tokens,
                       MIN(created_at) as started_at,
                       MAX(created_at) as ended_at,
                       GROUP_CONCAT(DISTINCT agent) as agents
                FROM trace_events
                GROUP BY session_id
                ORDER BY started_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def _build_timeline(events: List[Dict]) -> List[Dict]:
    """Events ko readable timeline mein convert karo."""
    timeline = []
    for e in events:
        step = {
            "seq":        e["seq"],
            "type":       e["event_type"],
            "agent":      e["agent"],
            "status":     e["status"],
            "latency_ms": e["latency_ms"],
            "created_at": e["created_at"],
            "label":      _event_label(e),
            "detail":     _event_detail(e),
        }
        if e["status"] == "error":
            step["error"] = e["error"]
        timeline.append(step)
    return timeline


def _event_label(e: Dict) -> str:
    t = e["event_type"]
    inp = e.get("input_data", {})
    if t == EVENT_ROUTING:
        return f"Routing → {inp.get('intent', '?')} ({inp.get('confidence', '?')})"
    if t == EVENT_AGENT_STEP:
        return f"{e['agent'].title()} Agent started"
    if t == EVENT_TOOL_CALL:
        return f"Tool: {e['tool_name']}"
    if t == EVENT_GRAPH_QUERY:
        q = inp.get("query", "")[:50]
        return f"Graph Query: {q}"
    if t == EVENT_LLM_CALL:
        model = inp.get("model", "claude")
        tokens = e.get("token_count", 0)
        return f"LLM Call ({model}) — {tokens} tokens"
    if t == EVENT_COMPLETE:
        return "Response Complete"
    return t.replace("_", " ").title()


def _event_detail(e: Dict) -> Dict:
    out = e.get("output_data", {})
    inp = e.get("input_data", {})
    if e["event_type"] == EVENT_LLM_CALL:
        return {
            "model":    inp.get("model", ""),
            "tokens":   e.get("token_count", 0),
            "answer_preview": str(out.get("answer", ""))[:200],
        }
    if e["event_type"] == EVENT_TOOL_CALL:
        return {
            "tool":   e["tool_name"],
            "result": str(out.get("result", ""))[:200],
        }
    if e["event_type"] == EVENT_ROUTING:
        return {
            "intent":     inp.get("intent"),
            "confidence": inp.get("confidence"),
            "method":     inp.get("method"),
        }
    return {}


# ── Global instance ───────────────────────────────────────────────────────────

_tracer = TraceManager()


def get_tracer() -> TraceManager:
    return _tracer
