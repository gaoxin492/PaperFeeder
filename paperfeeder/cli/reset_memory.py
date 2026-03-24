#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs):
        return False

from paperfeeder.semantic import reset_semantic_memory_d1, resolve_semantic_state_backend


def load_cli_env() -> bool:
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        return bool(load_dotenv(dotenv_path=env_path))
    return False


def reset_local_memory(path: str) -> str:
    memory_path = Path(path)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(json.dumps({"seen": {}, "updated_at": ""}, indent=2) + "\n", encoding="utf-8")
    return str(memory_path)


def main() -> int:
    load_cli_env()
    parser = argparse.ArgumentParser(description="Reset short-term semantic memory locally and optionally in D1.")
    parser.add_argument("--memory-file", default="state/semantic/memory.json", help="Path to semantic memory JSON file")
    parser.add_argument("--backend", default="", help="Semantic state backend override (file or d1)")
    parser.add_argument("--cloudflare-account-id", default="", help="Cloudflare account ID")
    parser.add_argument("--cloudflare-api-token", default="", help="Cloudflare API token")
    parser.add_argument("--d1-database-id", default="", help="D1 database ID")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive reset")
    args = parser.parse_args()

    if not args.yes:
        print("Reset aborted: pass --yes to confirm.")
        return 1

    try:
        local_path = reset_local_memory(args.memory_file)
        backend = resolve_semantic_state_backend(args.backend or None)
        remote_result = None
        if backend == "d1":
            remote_result = reset_semantic_memory_d1(
                account_id=args.cloudflare_account_id or None,
                api_token=args.cloudflare_api_token or None,
                database_id=args.d1_database_id or None,
            )
    except Exception as exc:
        print(f"Reset failed: {exc}")
        return 1

    print("Semantic memory reset completed")
    print(f"   memory_file: {local_path}")
    if remote_result:
        print(f"   d1_database_id: {remote_result['database_id']}")
        print("   d1_memory: cleared")
    else:
        print("   d1_memory: not requested")
    return 0


if __name__ == "__main__":
    sys.exit(main())