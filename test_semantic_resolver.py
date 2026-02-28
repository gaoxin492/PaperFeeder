from __future__ import annotations

import unittest
from unittest.mock import patch

from semantic_resolver import SemanticPaperResolver


class SemanticResolverTests(unittest.TestCase):
    def test_existing_id_passthrough(self) -> None:
        resolver = SemanticPaperResolver()
        out = resolver.resolve(
            title="Any",
            url="https://example.com/paper",
            existing_semantic_paper_id="12345",
            source="arxiv",
        )
        self.assertEqual(out.semantic_paper_id, "CorpusId:12345")
        self.assertEqual(out.resolution_status, "existing")
        self.assertEqual(out.resolution_method, "existing")

    def test_arxiv_lookup_success(self) -> None:
        resolver = SemanticPaperResolver(api_key="k")

        def fake_request(path: str, params: dict) -> dict:
            self.assertIn("/paper/ARXIV:", path)
            self.assertIn("fields", params)
            return {"paperId": "999"}

        with patch.object(resolver, "_request_json", side_effect=fake_request):
            out = resolver.resolve(
                title="Paper",
                url="https://arxiv.org/abs/2501.00001",
                arxiv_id="2501.00001",
                source="arxiv",
            )
        self.assertEqual(out.semantic_paper_id, "CorpusId:999")
        self.assertEqual(out.resolution_status, "resolved")
        self.assertEqual(out.resolution_method, "arxiv_id")

    def test_title_search_requires_strict_match_plus_secondary_check(self) -> None:
        resolver = SemanticPaperResolver(api_key="k")

        def fake_request(*, path: str, params: dict) -> dict:
            if "/paper/ARXIV:" in path:
                return {}
            return {
                "data": [
                    {
                        "paperId": "abc",
                        "title": "Different Title",
                        "year": 2024,
                        "authors": [{"name": "Alice"}],
                    }
                ]
            }

        with patch.object(resolver, "_request_json", side_effect=fake_request):
            out = resolver.resolve(
                title="Original Title",
                url="https://arxiv.org/abs/2501.00002",
                arxiv_id="2501.00002",
                source="arxiv",
                paper_year=2024,
                author_names=["Alice"],
            )
        self.assertFalse(out.semantic_paper_id)
        self.assertEqual(out.resolution_status, "unresolved")

    def test_no_key_budget_exhaustion_fails_open(self) -> None:
        resolver = SemanticPaperResolver(
            api_key="",
            max_lookups=20,
            no_key_max_lookups=1,
            time_budget_sec=300,
        )

        resolver._stats.lookups_attempted = 1
        out = resolver.resolve(
            title="t2",
            url="https://arxiv.org/abs/2501.00004",
            arxiv_id="2501.00004",
            source="arxiv",
        )
        self.assertEqual(out.resolution_status, "error")
        self.assertEqual(out.error, "budget_exhausted")


if __name__ == "__main__":
    unittest.main()
