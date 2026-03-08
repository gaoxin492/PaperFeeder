#!/usr/bin/env python3
"""Unit/integration-style tests for Semantic Scholar anti-repetition memory."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from models import Paper, PaperSource
from main import _extract_report_urls, _normalize_url_for_match, update_semantic_memory_from_report
from semantic_memory import (
    SemanticMemoryStore,
    memory_keys_for_paper,
    normalize_arxiv_id,
    normalize_semantic_id,
)
from sources.paper_sources import SemanticScholarSource


class MemoryKeyHelpersTests(unittest.TestCase):
    def test_normalization_helpers(self):
        self.assertEqual(normalize_semantic_id("123"), "CorpusId:123")
        self.assertEqual(normalize_semantic_id("CorpusId:123"), "CorpusId:123")
        self.assertEqual(normalize_arxiv_id("arXiv:2501.00001"), "2501.00001")
        self.assertEqual(normalize_arxiv_id("2501.00001V2"), "2501.00001v2")

    def test_memory_key_generation_prefers_arxiv_with_semantic_dual_write(self):
        paper = Paper(
            title="A",
            abstract="",
            url="https://www.semanticscholar.org/paper/abc",
            source=PaperSource.SEMANTIC_SCHOLAR,
            semantic_paper_id="12345",
            arxiv_id="arXiv:2501.00001",
        )
        keys = memory_keys_for_paper(paper)
        self.assertIn("arxiv:2501.00001", keys)
        self.assertIn("semantic:CorpusId:12345", keys)
        self.assertIn("CorpusId:12345", keys)

    def test_hf_without_arxiv_falls_back_to_hf_url(self):
        paper = Paper(
            title="HF",
            abstract="",
            url="https://huggingface.co/papers/abc?x=1",
            source=PaperSource.HUGGINGFACE,
        )
        keys = memory_keys_for_paper(paper)
        self.assertEqual(keys, {"hf:https://huggingface.co/papers/abc"})


class SemanticMemoryStoreTests(unittest.TestCase):
    def test_mark_seen_and_recent_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memory.json"
            store = SemanticMemoryStore(str(path), max_ids=10)
            store.load()
            store.mark_seen(["p1", "p2"])
            self.assertTrue(store.recently_seen("p1", ttl_days=30))
            self.assertEqual(store.filter_recently_seen(["p1", "pX"], ttl_days=30), {"p1"})

    def test_prune_expired(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memory.json"
            path.write_text(
                json.dumps(
                    {
                        "seen": {
                            "old": (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(),
                            "new": datetime.now(timezone.utc).isoformat(),
                        },
                        "updated_at": "",
                    }
                )
            )
            store = SemanticMemoryStore(str(path), max_ids=10)
            store.load()
            removed = store.prune_expired(ttl_days=30)
            self.assertEqual(removed, 1)
            self.assertIn("new", store.state.seen)
            self.assertNotIn("old", store.state.seen)

    def test_invalid_memory_resets_safely(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memory.json"
            path.write_text("{invalid-json")
            store = SemanticMemoryStore(str(path), max_ids=10)
            store.load()
            self.assertEqual(store.state.seen, {})


class SemanticScholarSuppressionTests(unittest.TestCase):
    def test_source_suppression_filters_seen_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_path = Path(tmpdir) / "memory.json"
            mem_store = SemanticMemoryStore(str(mem_path), max_ids=10)
            mem_store.load()
            mem_store.mark_seen(["s2-a"])

            source = SemanticScholarSource(memory_store=mem_store, seen_ttl_days=30)
            papers = [
                Paper(
                    title="A",
                    abstract="",
                    url="https://example.com/a",
                    source=PaperSource.SEMANTIC_SCHOLAR,
                    semantic_paper_id="s2-a",
                ),
                Paper(
                    title="B",
                    abstract="",
                    url="https://example.com/b",
                    source=PaperSource.SEMANTIC_SCHOLAR,
                    semantic_paper_id="s2-b",
                ),
            ]
            filtered = source._apply_seen_suppression(papers)
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0].semantic_paper_id, "s2-b")
            self.assertEqual(source.last_stats["suppressed"], 1)

    def test_repeated_recommendations_across_runs(self):
        """Integration-style: same recommendation set on run 2 is suppressed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_path = Path(tmpdir) / "memory.json"
            store = SemanticMemoryStore(str(mem_path), max_ids=100)
            store.load()

            first_run_selected = ["r1", "r2"]
            store.mark_seen(first_run_selected)
            store.save()

            store2 = SemanticMemoryStore(str(mem_path), max_ids=100)
            store2.load()
            source = SemanticScholarSource(memory_store=store2, seen_ttl_days=30)
            papers = [
                Paper("t1", "", "u1", PaperSource.SEMANTIC_SCHOLAR, semantic_paper_id="r1"),
                Paper("t2", "", "u2", PaperSource.SEMANTIC_SCHOLAR, semantic_paper_id="r2"),
                Paper("t3", "", "u3", PaperSource.SEMANTIC_SCHOLAR, semantic_paper_id="r3"),
            ]
            second = source._apply_seen_suppression(papers)
            self.assertEqual([p.semantic_paper_id for p in second], ["r3"])

    def test_cross_source_suppression_uses_arxiv_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_path = Path(tmpdir) / "memory.json"
            mem_store = SemanticMemoryStore(str(mem_path), max_ids=10)
            mem_store.load()
            mem_store.mark_seen(["arxiv:2501.00001"])

            source = SemanticScholarSource(memory_store=mem_store, seen_ttl_days=30)
            papers = [
                Paper(
                    title="A",
                    abstract="",
                    url="https://arxiv.org/abs/2501.00001",
                    source=PaperSource.SEMANTIC_SCHOLAR,
                    semantic_paper_id="s2-a",
                    arxiv_id="2501.00001",
                ),
                Paper(
                    title="B",
                    abstract="",
                    url="https://arxiv.org/abs/2501.00002",
                    source=PaperSource.SEMANTIC_SCHOLAR,
                    semantic_paper_id="s2-b",
                    arxiv_id="2501.00002",
                ),
            ]
            filtered = source._apply_seen_suppression(papers)
            self.assertEqual([p.semantic_paper_id for p in filtered], ["s2-b"])


class ReportMemoryUpdateTests(unittest.TestCase):
    def test_update_memory_marks_report_visible_cross_source_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_path = Path(tmpdir) / "memory.json"
            store = SemanticMemoryStore(str(mem_path), max_ids=100)
            store.load()
            cfg = SimpleNamespace(
                semantic_memory_enabled=True,
                semantic_seen_ttl_days=30,
                _semantic_memory_store=store,
            )
            final_papers = [
                Paper(
                    title="S2",
                    abstract="",
                    url="https://arxiv.org/abs/2501.00001",
                    source=PaperSource.SEMANTIC_SCHOLAR,
                    semantic_paper_id="123",
                    arxiv_id="2501.00001",
                ),
                Paper(
                    title="HF",
                    abstract="",
                    url="https://huggingface.co/papers/demo",
                    source=PaperSource.HUGGINGFACE,
                ),
            ]
            report_html = """
            <a href="https://arxiv.org/abs/2501.00001">paper</a>
            """
            update_semantic_memory_from_report(final_papers, report_html, cfg)
            self.assertTrue(store.recently_seen("arxiv:2501.00001", ttl_days=30))
            self.assertTrue(store.recently_seen("semantic:CorpusId:123", ttl_days=30))
            self.assertTrue(store.recently_seen("CorpusId:123", ttl_days=30))
            self.assertFalse(store.recently_seen("hf:https://huggingface.co/papers/demo", ttl_days=30))


class ReportMatchTests(unittest.TestCase):
    def test_extract_report_urls_and_normalize(self):
        html = """
        <div>
          <a href="https://arxiv.org/abs/1234.5678?utm_source=x">paper1</a>
          <a href='https://example.com/path/'>paper2</a>
        </div>
        """
        urls = _extract_report_urls(html)
        self.assertIn("https://arxiv.org/abs/1234.5678", urls)
        self.assertIn("https://example.com/path", urls)
        self.assertEqual(
            _normalize_url_for_match("HTTPS://EXAMPLE.com/path/?x=1#frag"),
            "https://example.com/path",
        )


if __name__ == "__main__":
    unittest.main()
