"""Persistent memory for cross-source recommendation suppression."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Set
from urllib.parse import urlsplit, urlunsplit


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str) -> datetime | None:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def normalize_semantic_id(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if s.isdigit():
        return f"CorpusId:{s}"
    return s


def normalize_arxiv_id(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    # Normalize common arXiv forms to bare id (e.g., arXiv:2501.00001 -> 2501.00001)
    low = s.lower()
    if low.startswith("arxiv:"):
        s = s.split(":", 1)[1].strip()
    return s.lower()


def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower() if parts.scheme else "https"
        netloc = parts.netloc.lower()
        path = parts.path.rstrip("/")
        return urlunsplit((scheme, netloc, path, "", ""))
    except Exception:
        return url.strip().lower().rstrip("/")


def memory_keys_for_paper(paper: Any) -> Set[str]:
    """
    Generate source-aware memory keys for a paper.
    Backward compatibility:
    - semantic papers include legacy raw semantic id key.
    """
    out: Set[str] = set()
    semantic_id = normalize_semantic_id(getattr(paper, "semantic_paper_id", ""))
    arxiv_id = normalize_arxiv_id(getattr(paper, "arxiv_id", ""))
    source = str(getattr(getattr(paper, "source", None), "value", "")).strip().lower()
    url = normalize_url(getattr(paper, "url", ""))

    # Canonical key preference: use arXiv key when available.
    if arxiv_id:
        out.add(f"arxiv:{arxiv_id}")
    if semantic_id:
        out.add(f"semantic:{semantic_id}")
        out.add(semantic_id)  # legacy compatibility (dual-write/dual-read)
    if source == "huggingface" and not arxiv_id and url:
        out.add(f"hf:{url}")
    if source == "arxiv" and not arxiv_id and url:
        out.add(f"arxiv:{url}")
    return {k for k in out if k}


@dataclass
class SemanticMemoryState:
    seen: Dict[str, str] = field(default_factory=dict)  # paper_id -> ISO timestamp
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "seen": dict(sorted(self.seen.items(), key=lambda kv: kv[0])),
            "updated_at": self.updated_at,
        }


class SemanticMemoryStore:
    """Load/save and query seen-paper memory."""

    def __init__(self, path: str, max_ids: int = 5000):
        self.path = Path(path)
        self.max_ids = max_ids
        self.state = SemanticMemoryState()

    def load(self) -> None:
        if not self.path.exists():
            self.state = SemanticMemoryState(updated_at=_to_iso(_utcnow()))
            return

        try:
            data = json.loads(self.path.read_text())
            seen = data.get("seen", {})
            if not isinstance(seen, dict):
                raise ValueError("seen must be an object")
            normalized_seen: Dict[str, str] = {}
            for paper_id, ts in seen.items():
                if not paper_id:
                    continue
                parsed = _parse_iso(str(ts))
                if parsed is None:
                    continue
                normalized_seen[str(paper_id)] = _to_iso(parsed)
            updated_at = data.get("updated_at", "")
            self.state = SemanticMemoryState(
                seen=normalized_seen,
                updated_at=updated_at if isinstance(updated_at, str) else "",
            )
        except Exception as e:
            print(f"      ⚠️ Semantic memory invalid, resetting: {e}")
            self.state = SemanticMemoryState(updated_at=_to_iso(_utcnow()))

        self.prune_to_cap()

    def save(self) -> None:
        self.state.updated_at = _to_iso(_utcnow())
        self.prune_to_cap()
        self.path.write_text(json.dumps(self.state.to_dict(), indent=2) + "\n")

    def mark_seen(self, paper_ids: Iterable[str], at: datetime | None = None) -> None:
        ts = _to_iso(at or _utcnow())
        for pid in paper_ids:
            if pid:
                self.state.seen[str(pid)] = ts
        self.prune_to_cap()

    def recently_seen(self, paper_id: str, ttl_days: int, now: datetime | None = None) -> bool:
        if not paper_id:
            return False
        seen_at = self.state.seen.get(str(paper_id))
        if not seen_at:
            return False
        parsed = _parse_iso(seen_at)
        if parsed is None:
            return False
        cutoff = (now or _utcnow()) - timedelta(days=ttl_days)
        return parsed >= cutoff

    def filter_recently_seen(self, paper_ids: Iterable[str], ttl_days: int) -> Set[str]:
        now = _utcnow()
        return {pid for pid in paper_ids if self.recently_seen(pid, ttl_days, now=now)}

    def recently_seen_any(self, paper_ids: Iterable[str], ttl_days: int, now: datetime | None = None) -> bool:
        now_v = now or _utcnow()
        for pid in paper_ids:
            if self.recently_seen(str(pid), ttl_days, now=now_v):
                return True
        return False

    def prune_expired(self, ttl_days: int) -> int:
        cutoff = _utcnow() - timedelta(days=ttl_days)
        before = len(self.state.seen)
        self.state.seen = {
            pid: ts
            for pid, ts in self.state.seen.items()
            if (parsed := _parse_iso(ts)) is not None and parsed >= cutoff
        }
        return before - len(self.state.seen)

    def prune_to_cap(self) -> int:
        if len(self.state.seen) <= self.max_ids:
            return 0
        # Keep most recent entries.
        sorted_items = sorted(
            self.state.seen.items(),
            key=lambda kv: _parse_iso(kv[1]) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        kept = dict(sorted_items[: self.max_ids])
        removed = len(self.state.seen) - len(kept)
        self.state.seen = kept
        return removed
