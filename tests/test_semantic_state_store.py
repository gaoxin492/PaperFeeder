from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperfeeder.semantic.state_store import (
    DEFAULT_MEMORY_STATE,
    DEFAULT_SEEDS_STATE,
    STATE_KEY_MEMORY,
    STATE_KEY_SEEDS,
    export_semantic_state,
    import_semantic_state,
    load_semantic_state_from_d1,
    reset_semantic_memory_d1,
    resolve_semantic_state_backend,
)


class SemanticStateStoreTests(unittest.TestCase):
    def test_resolve_backend_defaults_to_file(self) -> None:
        self.assertEqual(resolve_semantic_state_backend(None), "file")
        self.assertEqual(resolve_semantic_state_backend("d1"), "d1")
        self.assertEqual(resolve_semantic_state_backend("FILE"), "file")

    def test_load_semantic_state_returns_defaults_when_missing(self) -> None:
        with patch("paperfeeder.semantic.state_store.ensure_semantic_state_tables") as ensure_tables, patch(
            "paperfeeder.semantic.state_store._d1_query",
            return_value=[],
        ) as d1_query:
            payload = load_semantic_state_from_d1(
                STATE_KEY_MEMORY,
                account_id="acc",
                api_token="tok",
                database_id="dbid",
            )

        ensure_tables.assert_called_once()
        d1_query.assert_called_once()
        self.assertEqual(payload, DEFAULT_MEMORY_STATE)

    def test_export_semantic_state_writes_normalized_local_files(self) -> None:
        responses = {
            STATE_KEY_MEMORY: [{"value_json": json.dumps({"seen": {"123": 456}, "updated_at": 789})}],
            STATE_KEY_SEEDS: [{"value_json": json.dumps({"positive_paper_ids": ["2", "CorpusId:1"], "negative_paper_ids": ["3"]})}],
        }

        def fake_query(_acc: str, _tok: str, _dbid: str, sql: str):
            if STATE_KEY_MEMORY in sql:
                return responses[STATE_KEY_MEMORY]
            if STATE_KEY_SEEDS in sql:
                return responses[STATE_KEY_SEEDS]
            return []

        with tempfile.TemporaryDirectory() as td, patch(
            "paperfeeder.semantic.state_store.ensure_semantic_state_tables"
        ), patch("paperfeeder.semantic.state_store._d1_query", side_effect=fake_query):
            memory_path = str(Path(td) / "memory.json")
            seeds_path = str(Path(td) / "seeds.json")
            result = export_semantic_state(
                memory_path=memory_path,
                seeds_path=seeds_path,
                account_id="acc",
                api_token="tok",
                database_id="dbid",
            )

            memory_payload = json.loads(Path(memory_path).read_text(encoding="utf-8"))
            seeds_payload = json.loads(Path(seeds_path).read_text(encoding="utf-8"))

        self.assertEqual(result["database_id"], "dbid")
        self.assertEqual(memory_payload, {"seen": {"123": "456"}, "updated_at": "789"})
        self.assertEqual(seeds_payload, {"positive_paper_ids": ["CorpusId:1", "CorpusId:2"], "negative_paper_ids": ["CorpusId:3"]})

    def test_import_semantic_state_normalizes_before_upload(self) -> None:
        captured = []

        def fake_save(state_key: str, data, **_kwargs):
            captured.append((state_key, data))
            return {"state_key": state_key, "payload": data, "database_id": "dbid"}

        with tempfile.TemporaryDirectory() as td, patch(
            "paperfeeder.semantic.state_store.save_semantic_state_to_d1",
            side_effect=fake_save,
        ):
            memory_path = Path(td) / "memory.json"
            seeds_path = Path(td) / "seeds.json"
            memory_path.write_text(json.dumps({"seen": {"abc": 1}, "updated_at": 2}) + "\n", encoding="utf-8")
            seeds_path.write_text(
                json.dumps({"positive_paper_ids": ["2"], "negative_paper_ids": ["CorpusId:9", "9"]}) + "\n",
                encoding="utf-8",
            )

            result = import_semantic_state(
                memory_path=str(memory_path),
                seeds_path=str(seeds_path),
                account_id="acc",
                api_token="tok",
                database_id="dbid",
            )

        self.assertEqual(result["database_id"], "dbid")
        self.assertEqual(
            captured,
            [
                (STATE_KEY_MEMORY, {"seen": {"abc": "1"}, "updated_at": "2"}),
                (STATE_KEY_SEEDS, {"positive_paper_ids": ["CorpusId:2"], "negative_paper_ids": ["CorpusId:9"]}),
            ],
        )

    def test_reset_semantic_memory_d1_writes_default_payload(self) -> None:
        with patch("paperfeeder.semantic.state_store.save_semantic_state_to_d1") as save_state:
            reset_semantic_memory_d1(account_id="acc", api_token="tok", database_id="dbid")

        save_state.assert_called_once_with(
            STATE_KEY_MEMORY,
            dict(DEFAULT_MEMORY_STATE),
            account_id="acc",
            api_token="tok",
            database_id="dbid",
        )

    def test_import_semantic_state_uses_defaults_for_missing_files(self) -> None:
        captured = []

        def fake_save(state_key: str, data, **_kwargs):
            captured.append((state_key, data))
            return {"state_key": state_key, "payload": data, "database_id": "dbid"}

        with tempfile.TemporaryDirectory() as td, patch(
            "paperfeeder.semantic.state_store.save_semantic_state_to_d1",
            side_effect=fake_save,
        ):
            import_semantic_state(
                memory_path=str(Path(td) / "missing-memory.json"),
                seeds_path=str(Path(td) / "missing-seeds.json"),
                account_id="acc",
                api_token="tok",
                database_id="dbid",
            )

        self.assertEqual(captured, [(STATE_KEY_MEMORY, DEFAULT_MEMORY_STATE), (STATE_KEY_SEEDS, DEFAULT_SEEDS_STATE)])


if __name__ == "__main__":
    unittest.main()