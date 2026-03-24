"""Cloudflare D1-backed semantic state storage helpers."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict

from .feedback import _d1_execute, _d1_query, _sql_quote, _sort_seed_ids


STATE_KEY_MEMORY = "semantic_memory"
STATE_KEY_SEEDS = "semantic_seeds"
DEFAULT_MEMORY_STATE = {"seen": {}, "updated_at": ""}
DEFAULT_SEEDS_STATE = {"positive_paper_ids": [], "negative_paper_ids": []}


def resolve_semantic_state_backend(value: str | None = None) -> str:
    backend = (value or os.getenv("SEMANTIC_STATE_BACKEND", "file")).strip().lower()
    return "d1" if backend == "d1" else "file"


def resolve_d1_credentials(
    *,
    account_id: str | None = None,
    api_token: str | None = None,
    database_id: str | None = None,
) -> tuple[str, str, str]:
    acc = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    tok = api_token or os.getenv("CLOUDFLARE_API_TOKEN", "")
    dbid = database_id or os.getenv("D1_DATABASE_ID", "")
    if not acc or not tok or not dbid:
        raise ValueError("Missing D1 credentials (account_id/api_token/database_id)")
    return acc, tok, dbid


def _normalize_memory_state(data: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return dict(DEFAULT_MEMORY_STATE)
    seen = data.get("seen", {})
    if not isinstance(seen, dict):
        seen = {}
    normalized_seen = {str(key): str(value) for key, value in seen.items() if str(key).strip()}
    updated_at = str(data.get("updated_at", "") or "")
    return {"seen": normalized_seen, "updated_at": updated_at}


def _normalize_seeds_state(data: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return dict(DEFAULT_SEEDS_STATE)
    positive = _sort_seed_ids(data.get("positive_paper_ids", []) or [])
    negative = _sort_seed_ids(data.get("negative_paper_ids", []) or [])
    return {
        "positive_paper_ids": positive,
        "negative_paper_ids": negative,
    }


def _normalize_state_payload(state_key: str, data: Dict[str, Any] | None) -> Dict[str, Any]:
    if state_key == STATE_KEY_MEMORY:
        return _normalize_memory_state(data)
    if state_key == STATE_KEY_SEEDS:
        return _normalize_seeds_state(data)
    raise ValueError(f"Unsupported semantic state key: {state_key}")


def ensure_semantic_state_tables(
    *,
    account_id: str | None = None,
    api_token: str | None = None,
    database_id: str | None = None,
) -> Dict[str, str]:
    acc, tok, dbid = resolve_d1_credentials(
        account_id=account_id,
        api_token=api_token,
        database_id=database_id,
    )
    create_sql = """
    CREATE TABLE IF NOT EXISTS semantic_state (
      state_key TEXT PRIMARY KEY,
      value_json TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_semantic_state_updated_at ON semantic_state(updated_at);
    """
    _d1_execute(acc, tok, dbid, create_sql)
    return {"database_id": dbid}


def load_semantic_state_from_d1(
    state_key: str,
    *,
    account_id: str | None = None,
    api_token: str | None = None,
    database_id: str | None = None,
) -> Dict[str, Any]:
    acc, tok, dbid = resolve_d1_credentials(
        account_id=account_id,
        api_token=api_token,
        database_id=database_id,
    )
    ensure_semantic_state_tables(account_id=acc, api_token=tok, database_id=dbid)
    rows = _d1_query(
        acc,
        tok,
        dbid,
        f"SELECT value_json FROM semantic_state WHERE state_key={_sql_quote(state_key)} LIMIT 1",
    )
    if not rows:
        return _normalize_state_payload(state_key, None)
    raw_value = rows[0].get("value_json")
    try:
        parsed = json.loads(str(raw_value))
    except Exception:
        parsed = None
    return _normalize_state_payload(state_key, parsed)


def save_semantic_state_to_d1(
    state_key: str,
    data: Dict[str, Any],
    *,
    account_id: str | None = None,
    api_token: str | None = None,
    database_id: str | None = None,
) -> Dict[str, Any]:
    acc, tok, dbid = resolve_d1_credentials(
        account_id=account_id,
        api_token=api_token,
        database_id=database_id,
    )
    ensure_semantic_state_tables(account_id=acc, api_token=tok, database_id=dbid)
    normalized = _normalize_state_payload(state_key, data)
    payload = json.dumps(normalized, separators=(",", ":"), ensure_ascii=False)
    sql = (
        "INSERT INTO semantic_state (state_key, value_json, updated_at) VALUES ("
        f"{_sql_quote(state_key)}, {_sql_quote(payload)}, datetime('now')"
        ") ON CONFLICT(state_key) DO UPDATE SET "
        "value_json=excluded.value_json, updated_at=excluded.updated_at"
    )
    _d1_execute(acc, tok, dbid, sql)
    return {
        "state_key": state_key,
        "database_id": dbid,
        "payload": normalized,
    }


def _write_json_file(path: str, payload: Dict[str, Any]) -> str:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(file_path)


def _read_json_file(path: str, default: Dict[str, Any]) -> Dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return dict(default)
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data


def export_semantic_state(
    *,
    memory_path: str = "state/semantic/memory.json",
    seeds_path: str = "state/semantic/seeds.json",
    include_memory: bool = True,
    include_seeds: bool = True,
    account_id: str | None = None,
    api_token: str | None = None,
    database_id: str | None = None,
) -> Dict[str, Any]:
    acc, tok, dbid = resolve_d1_credentials(
        account_id=account_id,
        api_token=api_token,
        database_id=database_id,
    )
    out: Dict[str, Any] = {"database_id": dbid}
    if include_memory:
        memory_state = load_semantic_state_from_d1(
            STATE_KEY_MEMORY,
            account_id=acc,
            api_token=tok,
            database_id=dbid,
        )
        out["memory_path"] = _write_json_file(memory_path, memory_state)
        out["memory_state"] = memory_state
    if include_seeds:
        seeds_state = load_semantic_state_from_d1(
            STATE_KEY_SEEDS,
            account_id=acc,
            api_token=tok,
            database_id=dbid,
        )
        out["seeds_path"] = _write_json_file(seeds_path, seeds_state)
        out["seeds_state"] = seeds_state
    return out


def import_semantic_state(
    *,
    memory_path: str = "state/semantic/memory.json",
    seeds_path: str = "state/semantic/seeds.json",
    include_memory: bool = True,
    include_seeds: bool = True,
    account_id: str | None = None,
    api_token: str | None = None,
    database_id: str | None = None,
) -> Dict[str, Any]:
    acc, tok, dbid = resolve_d1_credentials(
        account_id=account_id,
        api_token=api_token,
        database_id=database_id,
    )
    out: Dict[str, Any] = {"database_id": dbid}
    if include_memory:
        memory_state = _normalize_memory_state(_read_json_file(memory_path, DEFAULT_MEMORY_STATE))
        out["memory"] = save_semantic_state_to_d1(
            STATE_KEY_MEMORY,
            memory_state,
            account_id=acc,
            api_token=tok,
            database_id=dbid,
        )
    if include_seeds:
        seeds_state = _normalize_seeds_state(_read_json_file(seeds_path, DEFAULT_SEEDS_STATE))
        out["seeds"] = save_semantic_state_to_d1(
            STATE_KEY_SEEDS,
            seeds_state,
            account_id=acc,
            api_token=tok,
            database_id=dbid,
        )
    return out


def reset_semantic_memory_d1(
    *,
    account_id: str | None = None,
    api_token: str | None = None,
    database_id: str | None = None,
) -> Dict[str, Any]:
    return save_semantic_state_to_d1(
        STATE_KEY_MEMORY,
        dict(DEFAULT_MEMORY_STATE),
        account_id=account_id,
        api_token=api_token,
        database_id=database_id,
    )


def reset_semantic_seeds_d1(
    *,
    account_id: str | None = None,
    api_token: str | None = None,
    database_id: str | None = None,
) -> Dict[str, Any]:
    return save_semantic_state_to_d1(
        STATE_KEY_SEEDS,
        dict(DEFAULT_SEEDS_STATE),
        account_id=account_id,
        api_token=api_token,
        database_id=database_id,
    )


def open_file_in_editor(path: str, editor: str | None = None) -> Dict[str, Any]:
    selected_editor = (editor or os.getenv("EDITOR", "")).strip()
    if not selected_editor:
        return {"opened": False, "path": path, "editor": None}
    command = [selected_editor, path]
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Editor not found: {selected_editor}") from exc
    return {"opened": True, "path": path, "editor": selected_editor}