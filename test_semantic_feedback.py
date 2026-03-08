from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from models import Paper, PaperSource
from semantic_feedback import (
    apply_feedback_d1_to_seeds,
    apply_feedback_queue_to_seeds,
    apply_feedback_to_seeds,
    build_feedback_run_view_url,
    create_feedback_token,
    export_run_feedback_manifest,
    get_run_id_from_manifest,
    ingest_feedback_token,
    inject_feedback_actions_into_report,
    inject_feedback_entry_link,
    publish_feedback_run_to_d1,
    verify_feedback_token,
)


class SemanticFeedbackTests(unittest.TestCase):
    def test_export_manifest_contains_report_visible_entries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            papers = [
                Paper(
                    title="Visible Paper",
                    abstract="a",
                    url="https://arxiv.org/abs/2501.00001",
                    source=PaperSource.SEMANTIC_SCHOLAR,
                    semantic_paper_id="123456",
                ),
                Paper(
                    title="Hidden Paper",
                    abstract="b",
                    url="https://arxiv.org/abs/2501.00002",
                    source=PaperSource.SEMANTIC_SCHOLAR,
                    semantic_paper_id="CorpusId:999999",
                ),
            ]
            html = '<a href="https://arxiv.org/abs/2501.00001">Visible Paper</a>'
            out = export_run_feedback_manifest(papers, html, output_dir=td, run_id="2026-02-21T08-00-00Z")

            self.assertIsNotNone(out)
            manifest_path, questionnaire_path = out
            data = json.loads(Path(manifest_path).read_text())
            questionnaire = json.loads(Path(questionnaire_path).read_text())
            self.assertEqual(data["run_id"], "2026-02-21T08-00-00Z")
            self.assertEqual(len(data["papers"]), 1)
            self.assertEqual(data["papers"][0]["item_id"], "p01")
            self.assertEqual(data["papers"][0]["semantic_paper_id"], "CorpusId:123456")
            self.assertEqual(questionnaire["run_id"], "2026-02-21T08-00-00Z")
            self.assertEqual(questionnaire["labels"][0]["item_id"], "p01")
            self.assertEqual(questionnaire["labels"][0]["label"], "undecided")

    def test_apply_feedback_latest_review_wins_and_moves_between_lists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            manifest = td_path / "manifest.json"
            feedback = td_path / "feedback.json"
            seeds = td_path / "seeds.json"

            manifest.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "run_id": "2026-02-21T08-00-00Z",
                        "generated_at": "2026-02-21T08:10:00Z",
                        "papers": [
                            {
                                "item_id": "p01",
                                "title": "A",
                                "url": "https://arxiv.org/abs/1",
                                "semantic_paper_id": "CorpusId:111",
                            },
                            {
                                "item_id": "p02",
                                "title": "B",
                                "url": "https://arxiv.org/abs/2",
                                "semantic_paper_id": "222",
                            },
                        ],
                    }
                )
                + "\n"
            )
            feedback.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "run_id": "2026-02-21T08-00-00Z",
                        "reviewer": "u",
                        "reviewed_at": "2026-02-21T09:00:00Z",
                        "labels": [
                            {"item_id": "p01", "label": "positive", "reviewed_at": "2026-02-21T09:01:00Z"},
                            {"item_id": "p01", "label": "negative", "reviewed_at": "2026-02-21T09:02:00Z"},
                            {"item_id": "p02", "label": "positive"},
                        ],
                    }
                )
                + "\n"
            )
            seeds.write_text(
                json.dumps(
                    {
                        "positive_paper_ids": ["CorpusId:111"],
                        "negative_paper_ids": [],
                    }
                )
                + "\n"
            )

            result = apply_feedback_to_seeds(
                feedback_path=str(feedback),
                manifest_path=str(manifest),
                seeds_path=str(seeds),
                dry_run=False,
            )
            self.assertEqual(result["applied_count"], 2)

            updated = json.loads(seeds.read_text())
            self.assertEqual(updated["positive_paper_ids"], ["CorpusId:222"])
            self.assertEqual(updated["negative_paper_ids"], ["CorpusId:111"])

    def test_apply_feedback_undecided_resets_seed_membership(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            manifest = td_path / "manifest.json"
            feedback = td_path / "feedback.json"
            seeds = td_path / "seeds.json"

            manifest.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "run_id": "run-reset",
                        "generated_at": "2026-02-21T08:10:00Z",
                        "papers": [
                            {
                                "item_id": "p01",
                                "title": "A",
                                "url": "https://arxiv.org/abs/1",
                                "semantic_paper_id": "CorpusId:111",
                            }
                        ],
                    }
                )
                + "\n"
            )
            feedback.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "run_id": "run-reset",
                        "reviewer": "u",
                        "reviewed_at": "2026-02-21T09:00:00Z",
                        "labels": [
                            {"item_id": "p01", "label": "undecided", "reviewed_at": "2026-02-21T09:01:00Z"}
                        ],
                    }
                )
                + "\n"
            )
            seeds.write_text(
                json.dumps(
                    {
                        "positive_paper_ids": ["CorpusId:111"],
                        "negative_paper_ids": [],
                    }
                )
                + "\n"
            )

            result = apply_feedback_to_seeds(
                feedback_path=str(feedback),
                manifest_path=str(manifest),
                seeds_path=str(seeds),
                dry_run=False,
            )
            self.assertEqual(result["applied_count"], 1)
            updated = json.loads(seeds.read_text())
            self.assertEqual(updated["positive_paper_ids"], [])
            self.assertEqual(updated["negative_paper_ids"], [])

    def test_apply_feedback_rejects_run_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            manifest = td_path / "manifest.json"
            feedback = td_path / "feedback.json"

            manifest.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "run_id": "run-a",
                        "generated_at": "2026-02-21T08:10:00Z",
                        "papers": [],
                    }
                )
                + "\n"
            )
            feedback.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "run_id": "run-b",
                        "reviewer": "u",
                        "reviewed_at": "2026-02-21T09:00:00Z",
                        "labels": [],
                    }
                )
                + "\n"
            )

            with self.assertRaises(ValueError):
                apply_feedback_to_seeds(
                    feedback_path=str(feedback),
                    manifest_path=str(manifest),
                    seeds_path=str(td_path / "seeds.json"),
                    dry_run=True,
                )

    def test_token_sign_and_verify(self) -> None:
        claims = {
            "v": 1,
            "run_id": "run-1",
            "item_id": "p01",
            "label": "positive",
            "reviewer": "xuhan",
            "exp": "2099-01-01T00:00:00Z",
        }
        token = create_feedback_token(claims, "secret123")
        verified = verify_feedback_token(token, "secret123")
        self.assertEqual(verified["run_id"], "run-1")
        self.assertEqual(verified["item_id"], "p01")
        self.assertEqual(verified["label"], "positive")

    def test_ingest_feedback_token_appends_queue_event(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            queue_path = str(Path(td) / "queue.json")
            claims = {
                "v": 1,
                "run_id": "run-1",
                "item_id": "p02",
                "semantic_paper_id": "CorpusId:123",
                "label": "negative",
                "reviewer": "xuhan",
                "exp": "2099-01-01T00:00:00Z",
            }
            token = create_feedback_token(claims, "secret123")
            event = ingest_feedback_token(
                token=token,
                signing_secret="secret123",
                queue_path=queue_path,
                source="email_link",
            )
            self.assertEqual(event["run_id"], "run-1")
            self.assertEqual(event["item_id"], "p02")
            self.assertEqual(event["label"], "negative")
            self.assertEqual(event["resolved_semantic_paper_id"], "CorpusId:123")
            queue_data = json.loads(Path(queue_path).read_text())
            self.assertEqual(len(queue_data["events"]), 1)
            self.assertEqual(queue_data["events"][0]["status"], "pending")

    def test_ingest_rejects_expired_token(self) -> None:
        claims = {
            "v": 1,
            "run_id": "run-1",
            "item_id": "p02",
            "label": "negative",
            "reviewer": "xuhan",
            "exp": "2000-01-01T00:00:00Z",
        }
        token = create_feedback_token(claims, "secret123")
        with self.assertRaises(ValueError):
            ingest_feedback_token(token=token, signing_secret="secret123", queue_path=":memory:")

    def test_apply_queue_latest_event_wins(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            manifest = td_path / "manifest.json"
            queue = td_path / "queue.json"
            seeds = td_path / "seeds.json"

            manifest.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "run_id": "run-1",
                        "generated_at": "2026-02-21T08:10:00Z",
                        "papers": [
                            {"item_id": "p01", "title": "A", "url": "u1", "semantic_paper_id": "CorpusId:100"},
                            {"item_id": "p02", "title": "B", "url": "u2", "semantic_paper_id": "CorpusId:200"},
                        ],
                    }
                )
                + "\n"
            )
            queue.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "events": [
                            {
                                "event_id": "evt_1",
                                "run_id": "run-1",
                                "item_id": "p01",
                                "label": "positive",
                                "reviewer": "x",
                                "created_at": "2026-02-21T10:00:00Z",
                                "source": "email_link",
                                "status": "pending",
                                "resolved_semantic_paper_id": None,
                                "applied_at": None,
                                "error": None,
                            },
                            {
                                "event_id": "evt_2",
                                "run_id": "run-1",
                                "item_id": "p01",
                                "label": "negative",
                                "reviewer": "x",
                                "created_at": "2026-02-21T10:01:00Z",
                                "source": "email_link",
                                "status": "pending",
                                "resolved_semantic_paper_id": None,
                                "applied_at": None,
                                "error": None,
                            },
                            {
                                "event_id": "evt_3",
                                "run_id": "run-1",
                                "item_id": "p02",
                                "label": "positive",
                                "reviewer": "x",
                                "created_at": "2026-02-21T10:02:00Z",
                                "source": "email_link",
                                "status": "pending",
                                "resolved_semantic_paper_id": None,
                                "applied_at": None,
                                "error": None,
                            },
                        ],
                    }
                )
                + "\n"
            )
            seeds.write_text(json.dumps({"positive_paper_ids": [], "negative_paper_ids": []}) + "\n")

            result = apply_feedback_queue_to_seeds(
                manifest_path=str(manifest),
                queue_path=str(queue),
                seeds_path=str(seeds),
                dry_run=False,
            )
            self.assertEqual(result["applied_count"], 2)
            self.assertGreaterEqual(result["rejected_count"], 1)
            updated_seeds = json.loads(seeds.read_text())
            self.assertIn("CorpusId:200", updated_seeds["positive_paper_ids"])
            self.assertIn("CorpusId:100", updated_seeds["negative_paper_ids"])

    def test_apply_queue_undecided_resets_seed_membership(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            manifest = td_path / "manifest.json"
            queue = td_path / "queue.json"
            seeds = td_path / "seeds.json"

            manifest.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "run_id": "run-1",
                        "generated_at": "2026-02-21T08:10:00Z",
                        "papers": [
                            {"item_id": "p01", "title": "A", "url": "u1", "semantic_paper_id": "CorpusId:100"}
                        ],
                    }
                )
                + "\n"
            )
            queue.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "events": [
                            {
                                "event_id": "evt_1",
                                "run_id": "run-1",
                                "item_id": "p01",
                                "label": "undecided",
                                "reviewer": "x",
                                "created_at": "2026-02-21T10:02:00Z",
                                "source": "web_viewer",
                                "status": "pending",
                                "resolved_semantic_paper_id": None,
                                "applied_at": None,
                                "error": None,
                            }
                        ],
                    }
                )
                + "\n"
            )
            seeds.write_text(
                json.dumps({"positive_paper_ids": ["CorpusId:100"], "negative_paper_ids": []}) + "\n"
            )

            result = apply_feedback_queue_to_seeds(
                manifest_path=str(manifest),
                queue_path=str(queue),
                seeds_path=str(seeds),
                dry_run=False,
            )
            self.assertEqual(result["applied_count"], 1)
            updated = json.loads(seeds.read_text())
            self.assertEqual(updated["positive_paper_ids"], [])
            self.assertEqual(updated["negative_paper_ids"], [])

    def test_manifest_with_action_links_injects_buttons(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            papers = [
                Paper(
                    title="Visible Paper",
                    abstract="a",
                    url="https://arxiv.org/abs/2501.00001",
                    source=PaperSource.SEMANTIC_SCHOLAR,
                    semantic_paper_id="123456",
                )
            ]
            html = '<html><head></head><body><h3><a href="https://arxiv.org/abs/2501.00001">Visible Paper</a></h3></body></html>'
            out = export_run_feedback_manifest(
                papers,
                html,
                output_dir=td,
                run_id="2026-02-21T08-00-00Z",
                feedback_endpoint_base_url="https://paperfeeder-feedback.example.workers.dev",
                feedback_link_signing_secret="secret123",
                reviewer="xuhan",
                token_ttl_days=7,
            )
            self.assertIsNotNone(out)
            manifest_path, _q = out
            updated = inject_feedback_actions_into_report(html, str(manifest_path))
            self.assertIn("pf-feedback-actions", updated)
            self.assertIn("Positive", updated)
            self.assertIn("Undecided", updated)

    def test_build_and_inject_feedback_entry_link(self) -> None:
        html = "<html><head></head><body><h1>Paper Digest</h1></body></html>"
        url = build_feedback_run_view_url("https://paperfeeder-feedback.example.workers.dev", "run-123")
        updated = inject_feedback_entry_link(html, url)
        self.assertIn("/run?run_id=run-123", updated)
        self.assertIn("Open Feedback Web Viewer", updated)
        self.assertNotIn("pf-feedback-actions", updated)

    def test_manifest_skips_action_links_without_semantic_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            papers = [
                Paper(
                    title="No SID Paper",
                    abstract="a",
                    url="https://example.com/paper-no-sid",
                    source=PaperSource.MANUAL,
                    semantic_paper_id="",
                )
            ]
            html = '<html><head></head><body><h3><a href="https://example.com/paper-no-sid">No SID Paper</a></h3></body></html>'
            out = export_run_feedback_manifest(
                papers,
                html,
                output_dir=td,
                run_id="2026-02-21T08-00-00Z",
                feedback_endpoint_base_url="https://paperfeeder-feedback.example.workers.dev",
                feedback_link_signing_secret="secret123",
                reviewer="xuhan",
                token_ttl_days=7,
            )
            self.assertIsNotNone(out)
            manifest_path, _ = out
            manifest = json.loads(Path(manifest_path).read_text())
            self.assertEqual(len(manifest["papers"]), 1)
            self.assertNotIn("action_links", manifest["papers"][0])
            updated = inject_feedback_actions_into_report(html, str(manifest_path))
            self.assertNotIn("pf-feedback-actions", updated)

    def test_manifest_cross_source_resolution_metadata_and_questionnaire_filter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            papers = [
                Paper(
                    title="Resolve Me",
                    abstract="a",
                    url="https://arxiv.org/abs/2501.10001",
                    source=PaperSource.ARXIV,
                    arxiv_id="2501.10001",
                    semantic_paper_id="",
                    published_date=datetime(2025, 1, 1),
                ),
                Paper(
                    title="Unresolved Paper",
                    abstract="b",
                    url="https://arxiv.org/abs/2501.10002",
                    source=PaperSource.HUGGINGFACE,
                    arxiv_id="2501.10002",
                    semantic_paper_id="",
                ),
            ]
            html = (
                '<html><head></head><body>'
                '<a href="https://arxiv.org/abs/2501.10001">Resolve Me</a>'
                '<a href="https://arxiv.org/abs/2501.10002">Unresolved Paper</a>'
                "</body></html>"
            )

            class FakeResolver:
                def __init__(self, **_kwargs):
                    self.calls = 0

                def resolve(self, **kwargs):
                    self.calls += 1
                    title = kwargs.get("title", "")
                    if title == "Resolve Me":
                        return type(
                            "Result",
                            (),
                            {
                                "semantic_paper_id": "CorpusId:123",
                                "resolution_status": "resolved",
                                "resolution_method": "arxiv_id",
                                "error": "",
                            },
                        )()
                    return type(
                        "Result",
                        (),
                        {
                            "semantic_paper_id": "",
                            "resolution_status": "unresolved",
                            "resolution_method": "title_search",
                            "error": "",
                        },
                    )()

                def stats(self):
                    return {
                        "resolved": 1,
                        "unresolved": 1,
                        "errors": 0,
                        "cache_hits": 0,
                        "lookups_attempted": 2,
                        "budget_skips": 0,
                    }

            with patch("semantic_feedback.SemanticPaperResolver", FakeResolver):
                out = export_run_feedback_manifest(
                    papers,
                    html,
                    output_dir=td,
                    run_id="run-meta",
                    feedback_endpoint_base_url="https://paperfeeder-feedback.example.workers.dev",
                    feedback_link_signing_secret="secret123",
                    reviewer="xuhan",
                    token_ttl_days=7,
                )

            self.assertIsNotNone(out)
            manifest_path, questionnaire_path = out
            manifest = json.loads(Path(manifest_path).read_text())
            questionnaire = json.loads(Path(questionnaire_path).read_text())
            self.assertEqual(len(manifest["papers"]), 2)
            first = manifest["papers"][0]
            second = manifest["papers"][1]
            self.assertEqual(first["resolution_status"], "resolved")
            self.assertEqual(first["resolution_method"], "arxiv_id")
            self.assertTrue(first["feedback_enabled"])
            self.assertIn("action_links", first)
            self.assertFalse(second["feedback_enabled"])
            self.assertNotIn("action_links", second)
            self.assertEqual(questionnaire["labels"], [{"item_id": "p01", "label": "undecided", "note": ""}])

    def test_manifest_only_resolves_report_visible_papers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            papers = [
                Paper(
                    title="Visible",
                    abstract="a",
                    url="https://arxiv.org/abs/2501.20001",
                    source=PaperSource.ARXIV,
                    arxiv_id="2501.20001",
                ),
                Paper(
                    title="Hidden",
                    abstract="b",
                    url="https://arxiv.org/abs/2501.20002",
                    source=PaperSource.ARXIV,
                    arxiv_id="2501.20002",
                ),
            ]
            html = '<a href="https://arxiv.org/abs/2501.20001">Visible</a>'

            class CountingResolver:
                calls = 0

                def __init__(self, **_kwargs):
                    pass

                def resolve(self, **_kwargs):
                    CountingResolver.calls += 1
                    return type(
                        "Result",
                        (),
                        {
                            "semantic_paper_id": "",
                            "resolution_status": "unresolved",
                            "resolution_method": "none",
                            "error": "",
                        },
                    )()

                def stats(self):
                    return {
                        "resolved": 0,
                        "unresolved": 1,
                        "errors": 0,
                        "cache_hits": 0,
                        "lookups_attempted": 1,
                        "budget_skips": 0,
                    }

            with patch("semantic_feedback.SemanticPaperResolver", CountingResolver):
                out = export_run_feedback_manifest(papers, html, output_dir=td, run_id="run-visible-only")

            self.assertIsNotNone(out)
            self.assertEqual(CountingResolver.calls, 1)

    def test_manifest_no_key_budget_exhausted_keeps_non_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            papers = [
                Paper(
                    title="P1",
                    abstract="a",
                    url="https://arxiv.org/abs/2501.30001",
                    source=PaperSource.ARXIV,
                    arxiv_id="2501.30001",
                ),
                Paper(
                    title="P2",
                    abstract="b",
                    url="https://arxiv.org/abs/2501.30002",
                    source=PaperSource.ARXIV,
                    arxiv_id="2501.30002",
                ),
            ]
            html = (
                '<a href="https://arxiv.org/abs/2501.30001">P1</a>'
                '<a href="https://arxiv.org/abs/2501.30002">P2</a>'
            )

            class BudgetResolver:
                def __init__(self, **_kwargs):
                    self.calls = 0

                def resolve(self, **_kwargs):
                    self.calls += 1
                    if self.calls == 1:
                        return type(
                            "Result",
                            (),
                            {
                                "semantic_paper_id": "",
                                "resolution_status": "unresolved",
                                "resolution_method": "title_search",
                                "error": "",
                            },
                        )()
                    return type(
                        "Result",
                        (),
                        {
                            "semantic_paper_id": "",
                            "resolution_status": "error",
                            "resolution_method": "none",
                            "error": "budget_exhausted",
                        },
                    )()

                def stats(self):
                    return {
                        "resolved": 0,
                        "unresolved": 1,
                        "errors": 1,
                        "cache_hits": 0,
                        "lookups_attempted": 1,
                        "budget_skips": 1,
                    }

            with patch("semantic_feedback.SemanticPaperResolver", BudgetResolver):
                out = export_run_feedback_manifest(
                    papers,
                    html,
                    output_dir=td,
                    run_id="run-budget",
                    semantic_scholar_api_key="",
                    resolver_max_lookups=20,
                    resolver_no_key_max_lookups=1,
                    resolver_time_budget_sec=300,
                )
            self.assertIsNotNone(out)
            manifest_path, _ = out
            manifest = json.loads(Path(manifest_path).read_text())
            self.assertEqual(len(manifest["papers"]), 2)
            self.assertFalse(manifest["papers"][1]["feedback_enabled"])
            self.assertEqual(manifest["papers"][1]["resolution_status"], "error")
            self.assertEqual(manifest["papers"][1]["resolution_error"], "budget_exhausted")

    @patch("semantic_feedback._d1_execute")
    def test_publish_feedback_run_to_d1(self, mock_d1_execute) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            manifest = td_path / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "run_id": "run-pub",
                        "generated_at": "2026-02-21T08:10:00Z",
                        "papers": [],
                    }
                )
                + "\n"
            )
            run_id = publish_feedback_run_to_d1(
                manifest_path=str(manifest),
                report_html="<html>r</html>",
                account_id="acc",
                api_token="tok",
                database_id="db",
            )
            self.assertEqual(run_id, "run-pub")
            self.assertGreaterEqual(mock_d1_execute.call_count, 2)
            self.assertEqual(get_run_id_from_manifest(str(manifest)), "run-pub")

    @patch("semantic_feedback._d1_execute")
    @patch("semantic_feedback._d1_query")
    def test_apply_d1_all_pending_default(self, mock_d1_query, _mock_d1_execute) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            seeds = td_path / "seeds.json"
            seeds.write_text(json.dumps({"positive_paper_ids": [], "negative_paper_ids": []}) + "\n")

            mock_d1_query.return_value = [
                {
                    "event_id": "evt_1",
                    "run_id": "run-a",
                    "item_id": "p01",
                    "label": "positive",
                    "reviewer": "x",
                    "created_at": "2026-02-21T10:00:00Z",
                    "source": "email_link",
                    "status": "pending",
                    "resolved_semantic_paper_id": "CorpusId:100",
                    "applied_at": None,
                    "error": None,
                },
                {
                    "event_id": "evt_2",
                    "run_id": "run-b",
                    "item_id": "p03",
                    "label": "negative",
                    "reviewer": "x",
                    "created_at": "2026-02-21T10:01:00Z",
                    "source": "email_link",
                    "status": "pending",
                    "resolved_semantic_paper_id": "CorpusId:200",
                    "applied_at": None,
                    "error": None,
                },
            ]

            result = apply_feedback_d1_to_seeds(
                seeds_path=str(seeds),
                dry_run=True,
                account_id="acc",
                api_token="tok",
                database_id="db",
                manifests_dir=str(td_path / "missing-artifacts"),
            )
            self.assertEqual(result["mode"], "d1")
            self.assertEqual(result["d1_pending_count"], 2)
            self.assertEqual(result["applied_count"], 2)

    @patch("semantic_feedback._d1_execute")
    @patch("semantic_feedback._d1_query")
    def test_apply_d1_undecided_resets_seed_membership(self, mock_d1_query, _mock_d1_execute) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            seeds = td_path / "seeds.json"
            seeds.write_text(json.dumps({"positive_paper_ids": ["CorpusId:100"], "negative_paper_ids": []}) + "\n")

            mock_d1_query.return_value = [
                {
                    "event_id": "evt_1",
                    "run_id": "run-a",
                    "item_id": "p01",
                    "label": "undecided",
                    "reviewer": "x",
                    "created_at": "2026-02-21T10:00:00Z",
                    "source": "web_viewer",
                    "status": "pending",
                    "resolved_semantic_paper_id": "CorpusId:100",
                    "applied_at": None,
                    "error": None,
                }
            ]

            result = apply_feedback_d1_to_seeds(
                seeds_path=str(seeds),
                dry_run=False,
                account_id="acc",
                api_token="tok",
                database_id="db",
                manifests_dir=str(td_path / "missing-artifacts"),
            )
            self.assertEqual(result["applied_count"], 1)
            updated = json.loads(seeds.read_text())
            self.assertEqual(updated["positive_paper_ids"], [])
            self.assertEqual(updated["negative_paper_ids"], [])

    @patch("semantic_feedback._d1_query")
    def test_apply_d1_failure_does_not_write_seeds(self, mock_d1_query) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            seeds = td_path / "seeds.json"
            initial = {"positive_paper_ids": ["CorpusId:1"], "negative_paper_ids": []}
            seeds.write_text(json.dumps(initial) + "\n")

            mock_d1_query.side_effect = RuntimeError("boom")

            with self.assertRaises(RuntimeError):
                apply_feedback_d1_to_seeds(
                    seeds_path=str(seeds),
                    dry_run=False,
                    account_id="acc",
                    api_token="tok",
                    database_id="db",
                )
            self.assertEqual(json.loads(seeds.read_text()), initial)

    @patch("semantic_feedback._d1_execute")
    @patch("semantic_feedback._d1_query")
    def test_apply_d1_dry_run_has_no_side_effects(self, mock_d1_query, mock_d1_execute) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            seeds = td_path / "seeds.json"
            initial = {"positive_paper_ids": [], "negative_paper_ids": []}
            seeds.write_text(json.dumps(initial) + "\n")
            mock_d1_query.return_value = [
                {
                    "event_id": "evt_1",
                    "run_id": "run-a",
                    "item_id": "p01",
                    "label": "positive",
                    "reviewer": "x",
                    "created_at": "2026-02-21T10:00:00Z",
                    "source": "email_link",
                    "status": "pending",
                    "resolved_semantic_paper_id": "CorpusId:100",
                    "applied_at": None,
                    "error": None,
                }
            ]

            result = apply_feedback_d1_to_seeds(
                seeds_path=str(seeds),
                dry_run=True,
                account_id="acc",
                api_token="tok",
                database_id="db",
                manifests_dir=str(td_path / "missing-artifacts"),
            )
            self.assertEqual(result["applied_count"], 1)
            self.assertEqual(json.loads(seeds.read_text()), initial)
            mock_d1_execute.assert_not_called()

    @patch("semantic_feedback._d1_execute")
    @patch("semantic_feedback._d1_query")
    def test_apply_d1_and_queue_modes_have_parity(self, mock_d1_query, _mock_d1_execute) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            manifest = td_path / "manifest.json"
            queue = td_path / "queue.json"
            queue_seeds = td_path / "queue_seeds.json"
            d1_seeds = td_path / "d1_seeds.json"

            manifest.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "run_id": "run-1",
                        "generated_at": "2026-02-21T08:10:00Z",
                        "papers": [
                            {"item_id": "p01", "title": "A", "url": "u1", "semantic_paper_id": "CorpusId:100"},
                            {"item_id": "p02", "title": "B", "url": "u2", "semantic_paper_id": "CorpusId:200"},
                        ],
                    }
                )
                + "\n"
            )
            events = [
                {
                    "event_id": "evt_1",
                    "run_id": "run-1",
                    "item_id": "p01",
                    "label": "positive",
                    "reviewer": "x",
                    "created_at": "2026-02-21T10:00:00Z",
                    "source": "email_link",
                    "status": "pending",
                    "resolved_semantic_paper_id": "CorpusId:100",
                    "applied_at": None,
                    "error": None,
                },
                {
                    "event_id": "evt_2",
                    "run_id": "run-1",
                    "item_id": "p01",
                    "label": "negative",
                    "reviewer": "x",
                    "created_at": "2026-02-21T10:01:00Z",
                    "source": "email_link",
                    "status": "pending",
                    "resolved_semantic_paper_id": "CorpusId:100",
                    "applied_at": None,
                    "error": None,
                },
                {
                    "event_id": "evt_3",
                    "run_id": "run-1",
                    "item_id": "p02",
                    "label": "positive",
                    "reviewer": "x",
                    "created_at": "2026-02-21T10:02:00Z",
                    "source": "email_link",
                    "status": "pending",
                    "resolved_semantic_paper_id": "CorpusId:200",
                    "applied_at": None,
                    "error": None,
                },
            ]
            queue.write_text(json.dumps({"version": "v1", "events": events}, indent=2) + "\n")

            initial = {"positive_paper_ids": [], "negative_paper_ids": []}
            queue_seeds.write_text(json.dumps(initial) + "\n")
            d1_seeds.write_text(json.dumps(initial) + "\n")

            queue_result = apply_feedback_queue_to_seeds(
                manifest_path=str(manifest),
                queue_path=str(queue),
                seeds_path=str(queue_seeds),
                dry_run=False,
            )

            mock_d1_query.return_value = events
            d1_result = apply_feedback_d1_to_seeds(
                seeds_path=str(d1_seeds),
                dry_run=False,
                manifest_file=str(manifest),
                manifests_dir=str(td_path),
                account_id="acc",
                api_token="tok",
                database_id="db",
            )

            self.assertEqual(json.loads(queue_seeds.read_text()), json.loads(d1_seeds.read_text()))
            self.assertEqual(queue_result["applied_count"], d1_result["applied_count"])
            self.assertEqual(queue_result["rejected_count"], d1_result["rejected_count"])


if __name__ == "__main__":
    unittest.main()
