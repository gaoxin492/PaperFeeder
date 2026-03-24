from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperfeeder.models import PaperSource
from paperfeeder.pipeline.debug_sample import (
    build_minimal_digest_html,
    load_debug_sample_papers,
    resolve_debug_sample_path,
)


class DebugSampleTests(unittest.TestCase):
    def test_load_from_temp_file(self) -> None:
        data = {
            "papers": [
                {
                    "title": "T",
                    "abstract": "A",
                    "url": "https://example.com/p/1",
                    "source": "arxiv",
                    "arxiv_id": "0000.00001",
                }
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            path = f.name
        try:
            papers = load_debug_sample_papers(path)
            self.assertEqual(len(papers), 1)
            self.assertEqual(papers[0].title, "T")
            self.assertEqual(papers[0].source, PaperSource.ARXIV)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_minimal_html_contains_link(self) -> None:
        from paperfeeder.models import Author, Paper

        p = Paper(
            title="Hello",
            abstract="World",
            url="https://arxiv.org/abs/1706.03762",
            source=PaperSource.ARXIV,
            arxiv_id="1706.03762",
            authors=[Author(name="A")],
        )
        html = build_minimal_digest_html([p])
        self.assertIn("https://arxiv.org/abs/1706.03762", html)
        self.assertIn("<!DOCTYPE html>", html)

    def test_resolve_example_exists_in_repo(self) -> None:
        root = Path(__file__).resolve().parents[1]
        ex = root / "tests" / "debug_sample.example.json"
        if not ex.is_file():
            self.skipTest("example file not in tree")
        p = resolve_debug_sample_path(str(ex))
        self.assertTrue(p.is_file())


if __name__ == "__main__":
    unittest.main()

