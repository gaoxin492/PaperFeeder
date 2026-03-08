#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   scripts/apply_semantic_feedback.sh <manifest_file> [feedback_file] [seeds_file] [--dry-run]
#
# Example:
#   scripts/apply_semantic_feedback.sh artifacts/run_feedback_manifest_2026-02-21T08-00-00Z.json
#   scripts/apply_semantic_feedback.sh artifacts/run_feedback_manifest_2026-02-21T08-00-00Z.json semantic_feedback.json semantic_scholar_seeds.json --dry-run

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <manifest_file> [feedback_file] [seeds_file] [--dry-run]"
  exit 1
fi

MANIFEST_FILE="${1}"
FEEDBACK_FILE="${2:-semantic_feedback.json}"
SEEDS_FILE="${3:-semantic_scholar_seeds.json}"
DRY_RUN="${4:-}"

if [[ ! -f "${MANIFEST_FILE}" ]]; then
  echo "❌ manifest file not found: ${MANIFEST_FILE}"
  exit 1
fi

if [[ ! -f "${FEEDBACK_FILE}" ]]; then
  echo "❌ feedback file not found: ${FEEDBACK_FILE}"
  exit 1
fi

PYTHON_BIN="python3"
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

CMD=(
  "${PYTHON_BIN}" semantic_feedback_apply.py
  --manifest-file "${MANIFEST_FILE}"
  --feedback-file "${FEEDBACK_FILE}"
  --seeds-file "${SEEDS_FILE}"
)

if [[ "${DRY_RUN}" == "--dry-run" ]]; then
  CMD+=(--dry-run)
fi

echo "▶ Running: ${CMD[*]}"
"${CMD[@]}"
