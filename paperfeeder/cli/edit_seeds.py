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

from paperfeeder.semantic import export_semantic_state, open_file_in_editor, resolve_semantic_state_backend


def load_cli_env() -> bool:
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        return bool(load_dotenv(dotenv_path=env_path))
    return False


def main() -> int:
    load_cli_env()
    parser = argparse.ArgumentParser(description="Export long-term seeds locally and optionally open them in an editor.")
    parser.add_argument("--seeds-file", default="state/semantic/seeds.json", help="Local semantic seeds path")
    parser.add_argument("--backend", default="", help="Semantic state backend override (file or d1)")
    parser.add_argument("--editor", default="", help="Editor command override (defaults to $EDITOR)")
    parser.add_argument("--skip-export", action="store_true", help="Edit the local seeds file without first pulling from D1")
    parser.add_argument("--cloudflare-account-id", default="", help="Cloudflare account ID")
    parser.add_argument("--cloudflare-api-token", default="", help="Cloudflare API token")
    parser.add_argument("--d1-database-id", default="", help="D1 database ID")
    args = parser.parse_args()

    try:
        backend = resolve_semantic_state_backend(args.backend or None)
        if backend == "d1" and not args.skip_export:
            export_semantic_state(
                seeds_path=args.seeds_file,
                include_memory=False,
                include_seeds=True,
                account_id=args.cloudflare_account_id or None,
                api_token=args.cloudflare_api_token or None,
                database_id=args.d1_database_id or None,
            )
        result = open_file_in_editor(args.seeds_file, editor=args.editor or None)
    except Exception as exc:
        print(f"Edit seeds failed: {exc}")
        return 1

    print("Seeds ready for editing")
    print(f"   seeds_file: {args.seeds_file}")
    if result["opened"]:
        print(f"   editor: {result['editor']}")
    else:
        print("   editor: not launched (set $EDITOR or pass --editor)")
        print("   next: run `python -m paperfeeder.cli.import_state --only seeds` after editing")
    return 0


if __name__ == "__main__":
    sys.exit(main())