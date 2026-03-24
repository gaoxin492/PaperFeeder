#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - import-time fallback for lightweight environments
    def load_dotenv(*_args, **_kwargs):
        return False

from paperfeeder.semantic import reset_feedback_d1_state, reset_semantic_memory_d1, reset_semantic_seeds_d1


def load_cli_env() -> bool:
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        return bool(load_dotenv(dotenv_path=env_path))
    return False


def reset_semantic_memory_file(path: str) -> str:
    memory_path = Path(path)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(json.dumps({"seen": {}, "updated_at": ""}, indent=2) + "\n", encoding="utf-8")
    return str(memory_path)


def reset_feedback_queue_file(path: str) -> str:
    queue_path = Path(path)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps({"version": "v1", "events": []}, indent=2) + "\n", encoding="utf-8")
    return str(queue_path)


def reset_semantic_seeds_file(path: str) -> str:
    seeds_path = Path(path)
    seeds_path.parent.mkdir(parents=True, exist_ok=True)
    seeds_path.write_text(
        json.dumps({"positive_paper_ids": [], "negative_paper_ids": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    return str(seeds_path)


def main() -> int:
    load_cli_env()
    parser = argparse.ArgumentParser(description="Reset local semantic memory and optional D1 feedback state.")
    parser.add_argument("--memory-file", default="state/semantic/memory.json", help="Path to semantic memory JSON file")
    parser.add_argument("--seeds-file", default="state/semantic/seeds.json", help="Path to semantic seeds JSON file")
    parser.add_argument("--queue-file", default="semantic_feedback_queue.json", help="Path to local feedback queue JSON file")
    parser.add_argument("--skip-queue", action="store_true", help="Do not reset the local feedback queue file")
    parser.add_argument("--with-seeds", action="store_true", help="Also clear long-term semantic seeds")
    parser.add_argument("--with-d1", action="store_true", help="Also clear Cloudflare D1 feedback tables")
    parser.add_argument("--cloudflare-account-id", default="", help="Cloudflare account ID")
    parser.add_argument("--cloudflare-api-token", default="", help="Cloudflare API token")
    parser.add_argument("--d1-database-id", default="", help="D1 database ID")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive reset")
    args = parser.parse_args()

    if not args.yes:
        print("Reset aborted: pass --yes to confirm.")
        return 1

    try:
        memory_path = reset_semantic_memory_file(args.memory_file)
        queue_path = None if args.skip_queue else reset_feedback_queue_file(args.queue_file)
        seeds_path = reset_semantic_seeds_file(args.seeds_file) if args.with_seeds else None
        d1_result = None
        d1_state_result = None
        if args.with_d1:
            d1_result = reset_feedback_d1_state(
                account_id=args.cloudflare_account_id or None,
                api_token=args.cloudflare_api_token or None,
                database_id=args.d1_database_id or None,
            )
            d1_state_result = reset_semantic_memory_d1(
                account_id=args.cloudflare_account_id or None,
                api_token=args.cloudflare_api_token or None,
                database_id=args.d1_database_id or None,
            )
            if args.with_seeds:
                reset_semantic_seeds_d1(
                    account_id=args.cloudflare_account_id or None,
                    api_token=args.cloudflare_api_token or None,
                    database_id=args.d1_database_id or None,
                )
    except Exception as exc:
        print(f"Reset failed: {exc}")
        return 1

    print("Runtime state reset completed")
    print(f"   memory: {memory_path}")
    if seeds_path:
        print(f"   seeds: {seeds_path}")
    else:
        print("   seeds: skipped")
    if queue_path:
        print(f"   queue: {queue_path}")
    else:
        print("   queue: skipped")
    if d1_result:
        print("   d1: cleared")
        print(f"   d1_database_id: {d1_result['database_id']}")
        print(f"   d1_events_deleted: {d1_result['events_deleted']}")
        print(f"   d1_runs_deleted: {d1_result['runs_deleted']}")
        if d1_state_result:
            print("   d1_memory: cleared")
            if args.with_seeds:
                print("   d1_seeds: cleared")
    else:
        print("   d1: not requested")
    return 0


if __name__ == "__main__":
    sys.exit(main())

