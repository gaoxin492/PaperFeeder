#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   scripts/apply_semantic_feedback_queue.sh <manifest_file> [queue_file] [seeds_file] [--dry-run]

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <manifest_file> [queue_file] [seeds_file] [--dry-run]"
  exit 1
fi

MANIFEST_FILE="${1}"
QUEUE_FILE="${2:-semantic_feedback_queue.json}"
SEEDS_FILE="${3:-semantic_scholar_seeds.json}"
DRY_RUN="${4:-}"

if [[ ! -f "${MANIFEST_FILE}" ]]; then
  echo "❌ manifest file not found: ${MANIFEST_FILE}"
  exit 1
fi

if [[ ! -f "${QUEUE_FILE}" ]]; then
  echo "❌ queue file not found: ${QUEUE_FILE}"
  exit 1
fi

PYTHON_BIN="python3"
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

CMD=(
  "${PYTHON_BIN}" semantic_feedback_apply.py
  --from-queue
  --manifest-file "${MANIFEST_FILE}"
  --queue-file "${QUEUE_FILE}"
  --seeds-file "${SEEDS_FILE}"
)

if [[ "${DRY_RUN}" == "--dry-run" ]]; then
  CMD+=(--dry-run)
fi

echo "▶ Running: ${CMD[*]}"
"${CMD[@]}"
