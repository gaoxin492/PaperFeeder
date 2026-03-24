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

from paperfeeder.semantic import import_semantic_state


def load_cli_env() -> bool:
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        return bool(load_dotenv(dotenv_path=env_path))
    return False


def main() -> int:
    load_cli_env()
    parser = argparse.ArgumentParser(description="Import local semantic state JSON files into D1.")
    parser.add_argument("--memory-file", default="state/semantic/memory.json", help="Local semantic memory input path")
    parser.add_argument("--seeds-file", default="state/semantic/seeds.json", help="Local semantic seeds input path")
    parser.add_argument("--only", choices=("both", "memory", "seeds"), default="both", help="Subset of state to import")
    parser.add_argument("--cloudflare-account-id", default="", help="Cloudflare account ID")
    parser.add_argument("--cloudflare-api-token", default="", help="Cloudflare API token")
    parser.add_argument("--d1-database-id", default="", help="D1 database ID")
    args = parser.parse_args()

    try:
        result = import_semantic_state(
            memory_path=args.memory_file,
            seeds_path=args.seeds_file,
            include_memory=args.only in {"both", "memory"},
            include_seeds=args.only in {"both", "seeds"},
            account_id=args.cloudflare_account_id or None,
            api_token=args.cloudflare_api_token or None,
            database_id=args.d1_database_id or None,
        )
    except Exception as exc:
        print(f"Import failed: {exc}")
        return 1

    print("State import completed")
    print(f"   d1_database_id: {result['database_id']}")
    if "memory" in result:
        print("   memory: uploaded")
    if "seeds" in result:
        print("   seeds: uploaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())