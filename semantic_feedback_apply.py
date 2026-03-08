#!/usr/bin/env python3
"""Manual apply entry point for semantic feedback -> seed updates."""

from __future__ import annotations

import argparse
import sys

from semantic_feedback import (
    apply_feedback_d1_to_seeds,
    apply_feedback_queue_to_seeds,
    apply_feedback_to_seeds,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply reviewed semantic feedback into seed IDs.")
    parser.add_argument(
        "--feedback-file",
        default="semantic_feedback.json",
        help="Path to feedback JSON file",
    )
    parser.add_argument(
        "--manifest-file",
        required=True,
        help="Path to run feedback manifest JSON file",
    )
    parser.add_argument(
        "--seeds-file",
        default="semantic_scholar_seeds.json",
        help="Path to semantic seeds JSON file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and compute results without writing seeds file",
    )
    parser.add_argument(
        "--from-queue",
        action="store_true",
        help="Apply from queued one-click events instead of feedback JSON file",
    )
    parser.add_argument(
        "--queue-file",
        default="semantic_feedback_queue.json",
        help="Path to queue JSON file (used with --from-queue)",
    )
    parser.add_argument(
        "--from-d1",
        action="store_true",
        help="Apply from Cloudflare D1 pending events",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional run_id filter for D1 mode (default: apply all pending)",
    )
    parser.add_argument(
        "--manifests-dir",
        default="artifacts",
        help="Directory for run feedback manifests (D1 mode mapping fallback)",
    )
    parser.add_argument(
        "--cloudflare-account-id",
        default="",
        help="Cloudflare account ID (optional if env set)",
    )
    parser.add_argument(
        "--cloudflare-api-token",
        default="",
        help="Cloudflare API token (optional if env set)",
    )
    parser.add_argument(
        "--d1-database-id",
        default="",
        help="D1 database ID (optional if env set)",
    )

    args = parser.parse_args()

    try:
        if args.from_d1 and args.from_queue:
            raise ValueError("--from-d1 and --from-queue are mutually exclusive")
        if args.from_d1:
            result = apply_feedback_d1_to_seeds(
                seeds_path=args.seeds_file,
                dry_run=args.dry_run,
                run_id_filter=args.run_id,
                manifest_file=args.manifest_file,
                manifests_dir=args.manifests_dir,
                account_id=args.cloudflare_account_id or None,
                api_token=args.cloudflare_api_token or None,
                database_id=args.d1_database_id or None,
            )
        elif args.from_queue:
            result = apply_feedback_queue_to_seeds(
                manifest_path=args.manifest_file,
                queue_path=args.queue_file,
                seeds_path=args.seeds_file,
                dry_run=args.dry_run,
            )
        else:
            result = apply_feedback_to_seeds(
                feedback_path=args.feedback_file,
                manifest_path=args.manifest_file,
                seeds_path=args.seeds_file,
                dry_run=args.dry_run,
            )
    except Exception as e:
        print(f"❌ Apply failed: {e}")
        return 1

    print("✅ Feedback apply completed")
    if args.from_d1:
        print("   source: cloudflare d1")
        if args.run_id:
            print(f"   run_id_filter: {args.run_id}")
        print(f"   d1_pending_count: {result['d1_pending_count']}")
    elif args.from_queue:
        print(f"   queue: {result['queue_path']}")
    else:
        print(f"   feedback: {result['feedback_path']}")
    print(f"   manifest: {result['manifest_path']}")
    print(f"   seeds: {result['seeds_path']}")
    print(f"   dry_run: {result['dry_run']}")
    print(f"   applied: {result['applied_count']}")
    print(f"   invalid: {result['invalid_count']}")
    print(f"   skipped: {result['skipped_count']}")
    if "rejected_count" in result:
        print(f"   rejected: {result['rejected_count']}")
    print(f"   positive_total: {result['positive_total']}")
    print(f"   negative_total: {result['negative_total']}")
    if result["warnings"]:
        print("   warnings:")
        for w in result["warnings"]:
            print(f"   - {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
