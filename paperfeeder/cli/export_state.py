#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs):
        return False

from paperfeeder.semantic import export_semantic_state


def load_cli_env() -> bool:
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        return bool(load_dotenv(dotenv_path=env_path))
    return False


def main() -> int:
    load_cli_env()
    parser = argparse.ArgumentParser(description="Export semantic state from D1 into local JSON files.")
    parser.add_argument("--memory-file", default="state/semantic/memory.json", help="Local semantic memory output path")
    parser.add_argument("--seeds-file", default="state/semantic/seeds.json", help="Local semantic seeds output path")
    parser.add_argument("--only", choices=("both", "memory", "seeds"), default="both", help="Subset of state to export")
    parser.add_argument("--cloudflare-account-id", default="", help="Cloudflare account ID")
    parser.add_argument("--cloudflare-api-token", default="", help="Cloudflare API token")
    parser.add_argument("--d1-database-id", default="", help="D1 database ID")
    args = parser.parse_args()

    try:
        result = export_semantic_state(
            memory_path=args.memory_file,
            seeds_path=args.seeds_file,
            include_memory=args.only in {"both", "memory"},
            include_seeds=args.only in {"both", "seeds"},
            account_id=args.cloudflare_account_id or None,
            api_token=args.cloudflare_api_token or None,
            database_id=args.d1_database_id or None,
        )
    except Exception as exc:
        print(f"Export failed: {exc}")
        return 1

    print("State export completed")
    print(f"   d1_database_id: {result['database_id']}")
    if "memory_path" in result:
        print(f"   memory: {result['memory_path']}")
    if "seeds_path" in result:
        print(f"   seeds: {result['seeds_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())