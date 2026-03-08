"""Filters for selecting relevant papers - upgraded for two-stage filtering."""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from models import Paper


class KeywordFilter:
    """Simple keyword filter matching title and abstract."""

    def __init__(self, keywords: Optional[List[str]] = None, exclude_keywords: Optional[List[str]] = None):
        self.keywords = [k.lower() for k in (keywords or [])]
        self.exclude_keywords = [k.lower() for k in (exclude_keywords or [])]

    def filter(self, papers: List[Paper]) -> List[Paper]:
        if not self.keywords and not self.exclude_keywords:
            return papers

        matched = []
        for p in papers:
            text = " ".join(filter(None, [getattr(p, "title", ""), getattr(p, "abstract", "")])).lower()
            
            # 排除关键词检查
            if self.exclude_keywords and any(ex in text for ex in self.exclude_keywords):
                continue
            
            # 关键词匹配
            if self.keywords:
                matched_kws = [kw for kw in self.keywords if kw in text]
                if matched_kws:
                    p.matched_keywords = matched_kws
                    matched.append(p)
            else:
                matched.append(p)
        
        return matched


class LLMFilter:
    """
    LLM-based paper filter supporting two-stage filtering:
    Stage 1 (Coarse): Title + Abstract only (fast, 粗筛)
    Stage 2 (Fine): Title + Abstract + Authors + Community Signals (精筛)
    """

    def __init__(
        self,
        api_key: str,
        research_interests: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        batch_size: int = 10,
    ):
        self.api_key = api_key
        self.research_interests = research_interests
        self.base_url = base_url
        self.model = model
        self.batch_size = batch_size
        self.debug_dir = Path(os.getenv("LLM_FILTER_DEBUG_DIR", "llm_filter_debug"))

    async def filter(
        self, 
        papers: List[Paper], 
        max_papers: int = 20, 
        include_community_signals: bool = False,
        **kwargs
    ) -> List[Paper]:
        """
        Score papers with the LLM and return top results.
        
        Args:
            papers: Papers to filter
            max_papers: Maximum number of papers to return
            include_community_signals: If True, uses Stage 2 (fine) filtering with research_notes
        """
        from llm_client import LLMClient

        if not papers:
            return []

        client = LLMClient(api_key=self.api_key, base_url=self.base_url, model=self.model)

        all_scored_papers: List[Paper] = []
        total_batches = (len(papers) + self.batch_size - 1) // self.batch_size

        stage_name = "Fine (with community signals)" if include_community_signals else "Coarse (title+abstract)"
        print(f"   📊 LLM Filter [{stage_name}]: Processing {len(papers)} papers in {total_batches} batches")

        for batch_idx, batch_start in enumerate(range(0, len(papers), self.batch_size)):
            batch_papers = papers[batch_start : batch_start + self.batch_size]
            print(f"   🔄 Batch {batch_idx + 1}/{total_batches} ({len(batch_papers)} papers)...")
            
            batch_results = await self._filter_batch(
                client, 
                batch_papers, 
                batch_start,
                include_community_signals=include_community_signals
            )
            all_scored_papers.extend(batch_results)
            
            if batch_idx < total_batches - 1:
                await asyncio.sleep(0.5)

        print(f"   ✅ Scored {len(all_scored_papers)} papers, sorting by relevance...")
        all_scored_papers.sort(key=lambda p: getattr(p, "relevance_score", 0), reverse=True)
        return all_scored_papers[:max_papers]

    async def _filter_batch(
        self, 
        client, 
        papers: List[Paper], 
        offset: int = 0,
        include_community_signals: bool = False
    ) -> List[Paper]:
        """
        Filter a batch of papers using the LLM.
        
        Args:
            include_community_signals: If True, includes research_notes in the prompt
        """
        # Build paper text for LLM
        papers_text = ""
        for i, paper in enumerate(papers):
            authors_str = ", ".join(
                [f"{a.name}" + (f" ({a.affiliation})" if getattr(a, "affiliation", None) else "") 
                 for a in getattr(paper, "authors", [])[:5]]
            )
            if len(getattr(paper, "authors", [])) > 5:
                authors_str += " et al."
            
            categories = ", ".join(getattr(paper, "categories", [])[:3]) if getattr(paper, "categories", None) else "N/A"
            
            paper_block = f"""
Paper {i+1}:
Title: {paper.title}
Authors: {authors_str}
Abstract: {paper.abstract[:600]}...
Categories: {categories}"""
            
            # 如果是Stage 2 (Fine filtering)，加上community signals
            if include_community_signals and hasattr(paper, 'research_notes') and paper.research_notes:
                paper_block += f"\n🔍 Community Signals: {paper.research_notes}"
            
            papers_text += paper_block + "\n---\n"

        # Build prompt based on stage
        if include_community_signals:
            prompt = self._build_fine_filter_prompt(papers_text, len(papers))
        else:
            prompt = self._build_coarse_filter_prompt(papers_text, len(papers))

        result_text: Optional[str] = None
        try:
            messages = [{"role": "user", "content": prompt}]
            result_text = await client.achat(messages, max_tokens=2000)

            result_text = (result_text or "").strip()
            # strip markdown code fences if present
            if result_text.startswith("```"):
                result_text = re.sub(r"^```(?:json)?\s*\n", "", result_text)
                result_text = re.sub(r"\n```$", "", result_text)

            json_match = re.search(r"\[.*\]", result_text, re.DOTALL)
            if not json_match:
                print(f"   ⚠️ LLM filter: Could not parse response (batch offset {offset})")
                self._log_parse_failure(
                    reason="no_json_array_match",
                    offset=offset,
                    include_community_signals=include_community_signals,
                    prompt=prompt,
                    response_text=result_text,
                )
                return self._fallback_scoring(papers)

            scores = json.loads(json_match.group())
            if not isinstance(scores, list):
                print(f"   ⚠️ LLM filter: Invalid response format (batch offset {offset})")
                self._log_parse_failure(
                    reason="json_not_list",
                    offset=offset,
                    include_community_signals=include_community_signals,
                    prompt=prompt,
                    response_text=result_text,
                )
                return self._fallback_scoring(papers)

            scored_papers: List[Paper] = []
            for item in scores:
                if not isinstance(item, dict) or "paper_num" not in item or "score" not in item:
                    continue
                paper_idx = int(item["paper_num"]) - 1
                if 0 <= paper_idx < len(papers):
                    paper = papers[paper_idx]
                    # normalize to 0-1
                    try:
                        score_val = float(item["score"]) / 10.0
                    except Exception:
                        score_val = 0.0
                    paper.relevance_score = score_val
                    paper.filter_reason = item.get("reason", "")
                    scored_papers.append(paper)

            return scored_papers

        except json.JSONDecodeError as e:
            print(f"   ⚠️ LLM filter JSON error (batch offset {offset}): {e}")
            self._log_parse_failure(
                reason=f"json_decode_error:{e}",
                offset=offset,
                include_community_signals=include_community_signals,
                prompt=prompt,
                response_text=result_text,
            )
            return self._fallback_scoring(papers)
        except Exception as e:
            print(f"   ⚠️ LLM filter error (batch offset {offset}): {type(e).__name__}: {e}")
            self._log_parse_failure(
                reason=f"runtime_error:{type(e).__name__}:{e}",
                offset=offset,
                include_community_signals=include_community_signals,
                prompt=prompt,
                response_text=result_text,
            )
            return self._fallback_scoring(papers)

    def _log_parse_failure(
        self,
        reason: str,
        offset: int,
        include_community_signals: bool,
        prompt: str,
        response_text: Optional[str],
    ) -> None:
        """Emit full debug context and save prompt/response for postmortem."""
        stage = "fine" if include_community_signals else "coarse"
        response_text = response_text or ""
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = self.debug_dir / f"{stage}_offset{offset}_{ts}.log"
        debug_payload = (
            f"reason={reason}\n"
            f"model={self.model}\n"
            f"base_url={self.base_url}\n"
            f"stage={stage}\n"
            f"batch_offset={offset}\n"
            f"prompt_chars={len(prompt)}\n"
            f"response_chars={len(response_text)}\n"
            "\n=== PROMPT BEGIN ===\n"
            f"{prompt}\n"
            "=== PROMPT END ===\n"
            "\n=== RESPONSE BEGIN ===\n"
            f"{response_text}\n"
            "=== RESPONSE END ===\n"
        )
        debug_path.write_text(debug_payload)
        print(
            "   🧪 LLM filter debug saved: "
            f"{debug_path} | reason={reason} | model={self.model}"
        )
        print("   🧪 Full raw response follows:")
        print("   ----- RESPONSE BEGIN -----")
        print(response_text)
        print("   ----- RESPONSE END -----")

    def _build_coarse_filter_prompt(self, papers_text: str, num_papers: int) -> str:
        """
        Stage 1 (Coarse): 只基于Title + Abstract进行粗筛。
        目标: 快速过滤，保留可能有价值的论文。
        """
        return f"""You are a research paper screening assistant doing COARSE filtering (Stage 1/2).

Your task: Quickly score papers based ONLY on title and abstract relevance.

My research interests:
{self.research_interests}

Papers to evaluate:
{papers_text}

Scoring criteria (0-10):
- **Relevance**: How well does the title/abstract match my research interests?
- **Novelty**: Does it propose something new or just incremental improvements?
- **Clarity**: Is the contribution clear from the abstract?

Return a JSON array with paper number, score, and brief reason:
[{{"paper_num": 1, "score": 8, "reason": "brief reason"}}, ...]

Requirements:
- Only return papers with score >= 6 (be generous at this stage)
- Sort by score from high to low
- You must evaluate ALL {num_papers} papers in this batch
- This is COARSE filtering - focus on potential, not perfection

Return only the JSON array, no other text."""

    def _build_fine_filter_prompt(self, papers_text: str, num_papers: int) -> str:
        """
        Stage 2 (Fine): 基于Title + Abstract + Authors + Community Signals精筛。
        目标: 选出真正值得深度阅读的Top 3论文。
        """
        return f"""You are a Senior Principal Researcher doing FINE filtering (Stage 2/2).

Your task: Select the TOP papers based on content + external signals.

My research interests:
{self.research_interests}

Papers to evaluate (with community signals):
{papers_text}

Scoring criteria (0-10):
1. **Relevance**: How well does the title/abstract match my research interests?
2. **Surprise (惊奇度)**: Does it challenge conventional wisdom? Is there an "aha" moment?
3. **Significance (重要性)**: Top-tier venue? Well-known authors? Novel methodology?
4. **External Signal (外部信号)**: 
   - BOOST: High GitHub stars, active discussions, reproducible code
   - PENALTY: Negative reviews, reproducibility issues, overhyped claims

Return a JSON array with paper number, score, and detailed reason:
[{{"paper_num": 1, "score": 9, "reason": "Paradigm-shifting approach to X. 1k GitHub stars. Hot discussion on Reddit about implications for Y."}}, ...]

Requirements:
- Only return papers with score >= 6 (be RUTHLESS - we want top 3-5 only)
- Sort by score from high to low
- Reason MUST explain: (1) why it's surprising/important AND (2) what community signals say
- Prioritize papers with both strong content AND positive external validation
- A paper needs at least one dimension ≥ 8 to be "Editor's Choice".

Return only the JSON array, no other text."""

    def _fallback_scoring(self, papers: List[Paper]) -> List[Paper]:
        """Fallback scoring using existing relevance scores (or zero)."""
        sorted_papers = sorted(papers, key=lambda p: getattr(p, "relevance_score", 0), reverse=True)
        return sorted_papers
