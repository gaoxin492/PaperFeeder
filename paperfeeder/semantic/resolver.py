"""Semantic Scholar ID resolver for feedback manifest export."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _normalize_title_for_match(value: str) -> str:
    out = []
    for ch in (value or "").lower():
        if ch.isalnum() or ch.isspace():
            out.append(ch)
    return " ".join("".join(out).split())


def _normalize_paper_id(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if s.isdigit():
        return f"CorpusId:{s}"
    return s


def _extract_arxiv_id(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    low = s.lower()
    if low.startswith("arxiv:"):
        return s.split(":", 1)[1].strip()
    return s


@dataclass
class ResolutionResult:
    semantic_paper_id: str = ""
    resolution_status: str = "unresolved"
    resolution_method: str = "none"
    error: str = ""


@dataclass
class ResolverStats:
    resolved: int = 0
    unresolved: int = 0
    errors: int = 0
    cache_hits: int = 0
    lookups_attempted: int = 0
    budget_skips: int = 0


@dataclass
class SemanticPaperResolver:
    api_key: str = ""
    timeout_sec: int = 8
    max_lookups: int = 25
    no_key_max_lookups: int = 10
    time_budget_sec: int = 20
    enable_cache: bool = True
    _start_monotonic: float = field(default_factory=time.monotonic)
    _cache: Dict[str, ResolutionResult] = field(default_factory=dict)
    _stats: ResolverStats = field(default_factory=ResolverStats)

    def stats(self) -> Dict[str, int]:
        return {
            "resolved": self._stats.resolved,
            "unresolved": self._stats.unresolved,
            "errors": self._stats.errors,
            "cache_hits": self._stats.cache_hits,
            "lookups_attempted": self._stats.lookups_attempted,
            "budget_skips": self._stats.budget_skips,
        }

    def _budget_exhausted(self) -> bool:
        if self.time_budget_sec > 0 and (time.monotonic() - self._start_monotonic) >= float(self.time_budget_sec):
            return True
        hard_cap = self.max_lookups if self.api_key else min(self.max_lookups, self.no_key_max_lookups)
        return hard_cap > 0 and self._stats.lookups_attempted >= hard_cap

    def resolve(
        self,
        *,
        title: str,
        url: str,
        arxiv_id: str = "",
        existing_semantic_paper_id: str = "",
        source: str = "",
        paper_year: Optional[int] = None,
        author_names: Optional[List[str]] = None,
    ) -> ResolutionResult:
        existing = _normalize_paper_id(existing_semantic_paper_id)
        if existing:
            self._stats.resolved += 1
            return ResolutionResult(
                semantic_paper_id=existing,
                resolution_status="existing",
                resolution_method="existing",
            )

        src = (source or "").strip().lower()
        if src not in {"arxiv", "huggingface"}:
            self._stats.unresolved += 1
            return ResolutionResult()

        lookup_key = self._build_cache_key(title=title, url=url, arxiv_id=arxiv_id)
        if self.enable_cache and lookup_key in self._cache:
            self._stats.cache_hits += 1
            cached = self._cache[lookup_key]
            if cached.resolution_status in {"existing", "resolved"}:
                self._stats.resolved += 1
            elif cached.resolution_status == "error":
                self._stats.errors += 1
            else:
                self._stats.unresolved += 1
            return cached

        if self._budget_exhausted():
            self._stats.budget_skips += 1
            self._stats.unresolved += 1
            res = ResolutionResult(resolution_status="error", resolution_method="none", error="budget_exhausted")
            if self.enable_cache:
                self._cache[lookup_key] = res
            return res

        result = self._resolve_uncached(
            title=title,
            arxiv_id=arxiv_id,
            paper_year=paper_year,
            author_names=author_names or [],
        )
        if self.enable_cache:
            self._cache[lookup_key] = result
        if result.resolution_status in {"existing", "resolved"}:
            self._stats.resolved += 1
        elif result.resolution_status == "error":
            self._stats.errors += 1
        else:
            self._stats.unresolved += 1
        return result

    def _build_cache_key(self, *, title: str, url: str, arxiv_id: str) -> str:
        aid = _extract_arxiv_id(arxiv_id)
        if aid:
            return f"arxiv:{aid.lower()}"
        return f"title:{_normalize_title_for_match(title)}|url:{(url or '').strip().lower()}"

    def _resolve_uncached(
        self,
        *,
        title: str,
        arxiv_id: str,
        paper_year: Optional[int],
        author_names: List[str],
    ) -> ResolutionResult:
        aid = _extract_arxiv_id(arxiv_id)
        if aid:
            mapped = self._lookup_by_arxiv_id(aid)
            if mapped:
                return mapped
        if title:
            by_title = self._lookup_by_title(title=title, paper_year=paper_year, author_names=author_names)
            if by_title:
                return by_title
        return ResolutionResult()

    def _request_json(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        self._stats.lookups_attempted += 1
        base_url = "https://api.semanticscholar.org/graph/v1"
        qs = urllib.parse.urlencode(params)
        url = f"{base_url}{path}?{qs}" if qs else f"{base_url}{path}"
        headers = {"User-Agent": "PaperFeeder/semantic-resolver"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=max(1, int(self.timeout_sec))) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else {}

    def _lookup_by_arxiv_id(self, arxiv_id: str) -> Optional[ResolutionResult]:
        try:
            payload = self._request_json(
                path=f"/paper/ARXIV:{urllib.parse.quote(arxiv_id, safe='')}",
                params={"fields": "paperId,title,year,authors,externalIds"},
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                return ResolutionResult(resolution_status="error", resolution_method="arxiv_id", error="rate_limited")
            return ResolutionResult(resolution_status="error", resolution_method="arxiv_id", error=f"http_{exc.code}")
        except Exception:
            return ResolutionResult(resolution_status="error", resolution_method="arxiv_id", error="lookup_failed")

        semantic_id = _normalize_paper_id(payload.get("paperId", ""))
        if semantic_id:
            return ResolutionResult(
                semantic_paper_id=semantic_id,
                resolution_status="resolved",
                resolution_method="arxiv_id",
            )
        return None

    def _lookup_by_title(
        self,
        *,
        title: str,
        paper_year: Optional[int],
        author_names: List[str],
    ) -> Optional[ResolutionResult]:
        try:
            payload = self._request_json(
                path="/paper/search/match",
                params={"query": title, "fields": "paperId,title,year,authors,externalIds"},
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                return ResolutionResult(resolution_status="error", resolution_method="title_search", error="rate_limited")
            return ResolutionResult(resolution_status="error", resolution_method="title_search", error=f"http_{exc.code}")
        except Exception:
            return ResolutionResult(resolution_status="error", resolution_method="title_search", error="lookup_failed")

        candidate = None
        if isinstance(payload.get("data"), list) and payload["data"]:
            candidate = payload["data"][0]
        elif isinstance(payload, dict) and payload.get("paperId"):
            candidate = payload
        if not isinstance(candidate, dict):
            return None
        if not self._accept_title_candidate(
            input_title=title,
            candidate=candidate,
            paper_year=paper_year,
            author_names=author_names,
        ):
            return None

        semantic_id = _normalize_paper_id(candidate.get("paperId", ""))
        if semantic_id:
            return ResolutionResult(
                semantic_paper_id=semantic_id,
                resolution_status="resolved",
                resolution_method="title_search",
            )
        return None

    def _accept_title_candidate(
        self,
        *,
        input_title: str,
        candidate: Dict[str, Any],
        paper_year: Optional[int],
        author_names: List[str],
    ) -> bool:
        norm_in = _normalize_title_for_match(input_title)
        norm_cand = _normalize_title_for_match(str(candidate.get("title", "")))
        if not norm_in or not norm_cand or norm_in != norm_cand:
            return False

        year_ok = False
        cand_year = candidate.get("year")
        if isinstance(cand_year, int) and isinstance(paper_year, int):
            year_ok = abs(cand_year - paper_year) <= 1

        overlap_ok = False
        if author_names:
            input_authors = {_normalize_title_for_match(a) for a in author_names if a}
            cand_authors = {
                _normalize_title_for_match(str(author.get("name", "")))
                for author in (candidate.get("authors") or [])
                if isinstance(author, dict)
            }
            input_authors.discard("")
            cand_authors.discard("")
            overlap_ok = bool(input_authors & cand_authors)

        return year_ok or overlap_ok

