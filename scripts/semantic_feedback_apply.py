#!/usr/bin/env python3
"""CLI wrapper for applying reviewed semantic feedback."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from paperfeeder.cli.apply_feedback import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())

