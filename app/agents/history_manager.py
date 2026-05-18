"""
HistorySummarizer + CompressedHistoryStore
Potpie-inspired production-grade history management.

Features:
- Token-aware history compaction
- LLM-based mid-segment summarization
- In-memory store with TTL + max-size eviction
- Thread-safe operations
"""
import os
import time
import threading
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class HistoryMessage:
    role:      str          # "user" | "assistant" | "system" | "summary"
    content:   str
    timestamp: float        = field(default_factory=time.time)
    agent:     Optional[str] = None
    intent:    Optional[str] = None
    tokens:    int           = 0  # estimated token count

    def estimate_tokens(self) -> int:
        """Rough estimate: 1 token ≈ 4 chars."""
        self.tokens = len(self.content) // 4
        return self.tokens


# ── In-Memory Compressed History Store ──────────────────────────────────────

class CompressedHistoryStore:
    """
    In-memory store with TTL and max-size eviction.
    Thread-safe. Per-conversation storage.
    Redis ke liye later swap karo (same interface).
    """

    def __init__(
        self,
        ttl_seconds:       int = 86400,   # 24 hours
        max_conversations: int = 500,
    ):
        self._ttl           = max(1, ttl_seconds)
        self._max           = max(1, max_conversations)
        self._data: Dict[str, tuple[List[HistoryMessage], float]] = {}
        self._lock          = threading.Lock()

    def _key(self, session_id: str, user_id: Optional[str] = None) -> str:
        return f"{user_id}:{session_id}" if user_id else session_id

    def get(
        self,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[List[HistoryMessage]]:
        key = self._key(session_id, user_id)
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            messages, last_write = entry
            if time.time() - last_write > self._ttl:
                del self._data[key]
                return None
            return list(messages)  # return copy

    def set(
        self,
        session_id: str,
        messages:   List[HistoryMessage],
        user_id:    Optional[str] = None,
    ) -> None:
        key = self._key(session_id, user_id)
        with self._lock:
            # Evict oldest if at capacity
            if len(self._data) >= self._max and key not in self._data:
                oldest = min(self._data, key=lambda k: self._data[k][1])
                del self._data[oldest]
            self._data[key] = (list(messages), time.time())

    def delete(
        self,
        session_id: str,
        user_id:    Optional[str] = None,
    ) -> None:
        key = self._key(session_id, user_id)
        with self._lock:
            self._data.pop(key, None)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "conversations": len(self._data),
                "max":           self._max,
                "ttl_hours":     self._ttl / 3600,
            }


# ── History Summarizer ───────────────────────────────────────────────────────

SUMMARIZE_PROMPT = """Summarize this conversation history concisely. Preserve:
1. Key decisions and conclusions
2. Important code findings (file paths, function names)
3. Errors found and their root causes
4. Pending tasks or unresolved questions
5. Tool calls made and their key outcomes

Omit: repetitive content, verbose explanations, full code blocks.
Target: 3-5 bullet points maximum.

Conversation:
{history_text}"""


class HistorySummarizer:
    """
    LLM-based history summarizer.
    Called when token count exceeds threshold.
    Replaces middle segment of conversation with summary.
    """

    MAX_TOKENS_BEFORE_SUMMARY = 4000   # ~16k chars
    HEAD_TURNS_TO_KEEP        = 2      # first N turns always kept
    TAIL_TURNS_TO_KEEP        = 4      # last N turns always kept

    async def summarize_if_needed(
        self,
        messages:   List[HistoryMessage],
        model:      str = None,
    ) -> List[HistoryMessage]:
        """
        If total tokens > threshold, summarize middle segment.
        Returns compacted message list.
        """
        total_tokens = sum(m.estimate_tokens() for m in messages)

        if total_tokens <= self.MAX_TOKENS_BEFORE_SUMMARY:
            return messages

        # Need summarization
        n = len(messages)
        if n <= self.HEAD_TURNS_TO_KEEP + self.TAIL_TURNS_TO_KEEP:
            return messages  # too short to summarize

        head = messages[:self.HEAD_TURNS_TO_KEEP]
        tail = messages[-self.TAIL_TURNS_TO_KEEP:]
        mid  = messages[self.HEAD_TURNS_TO_KEEP:-self.TAIL_TURNS_TO_KEEP]

        summary_text = await self._call_llm_summarize(mid, model)

        summary_msg = HistoryMessage(
            role    = "summary",
            content = f"[CONVERSATION SUMMARY]\n{summary_text}",
            agent   = "summarizer",
        )
        summary_msg.estimate_tokens()

        compacted = head + [summary_msg] + tail
        new_tokens = sum(m.estimate_tokens() for m in compacted)
        print(f"[HistorySummarizer] {total_tokens} → {new_tokens} tokens after summary")
        return compacted

    async def _call_llm_summarize(
        self,
        messages: List[HistoryMessage],
        model:    str = None,
    ) -> str:
        """LLM call to produce the summary."""
        import httpx
        import json

        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            return self._simple_summary(messages)

        history_text = "\n".join(
            f"{m.role.upper()}: {m.content[:400]}"
            for m in messages
        )
        prompt = SUMMARIZE_PROMPT.format(history_text=history_text)
        fast_model = model or os.getenv("MARKAR_LLM_MODEL", "mistralai/mistral-7b-instruct:free")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type":  "application/json",
                        "HTTP-Referer":  "https://markarai.netlify.app",
                        "X-Title":       "Markar.ai Summarizer",
                    },
                    json={
                        "model":    fast_model,
                        "messages": [
                            {"role": "system", "content": "You are a concise conversation summarizer. Respond with bullet points only."},
                            {"role": "user",   "content": prompt},
                        ],
                        "max_tokens":  400,
                        "temperature": 0.1,
                    },
                )
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

        except Exception as e:
            print(f"[HistorySummarizer] LLM failed: {e}")
            return self._simple_summary(messages)

    def _simple_summary(self, messages: List[HistoryMessage]) -> str:
        """Fallback — extract first line of each message."""
        lines = []
        for m in messages[:8]:
            first = m.content.split("\n")[0][:120]
            lines.append(f"• {m.role}: {first}")
        return "\n".join(lines) + f"\n[{len(messages)} messages summarized]"


# ── Global instances ─────────────────────────────────────────────────────────

_compressed_store = CompressedHistoryStore()
_summarizer       = HistorySummarizer()


def get_compressed_store() -> CompressedHistoryStore:
    return _compressed_store


def get_summarizer() -> HistorySummarizer:
    return _summarizer
