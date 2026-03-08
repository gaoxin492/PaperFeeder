#!/usr/bin/env python3
"""Ingest one-click feedback token into local queue (for testing/integration)."""

from __future__ import annotations

import argparse
import sys

from semantic_feedback import ingest_feedback_token


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest signed one-click feedback token.")
    parser.add_argument("--token", required=True, help="Signed token from feedback link")
    parser.add_argument(
        "--queue-file",
        default="semantic_feedback_queue.json",
        help="Path to local feedback queue JSON",
    )
    parser.add_argument(
        "--signing-secret",
        default="",
        help="Signing secret override (default reads FEEDBACK_LINK_SIGNING_SECRET)",
    )
    parser.add_argument(
        "--source",
        default="email_link",
        help="Source label for queue event",
    )
    args = parser.parse_args()

    try:
        event = ingest_feedback_token(
            token=args.token,
            signing_secret=args.signing_secret or None,
            queue_path=args.queue_file,
            source=args.source,
        )
    except Exception as e:
        print(f"❌ Ingest failed: {e}")
        return 1

    print("✅ Feedback token ingested")
    print(f"   event_id: {event['event_id']}")
    print(f"   run_id: {event['run_id']}")
    print(f"   item_id: {event['item_id']}")
    print(f"   label: {event['label']}")
    print(f"   queue_file: {args.queue_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
