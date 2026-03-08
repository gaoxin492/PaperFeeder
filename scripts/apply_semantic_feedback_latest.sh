#!/usr/bin/env bash
set -euo pipefail

# Zero-arg wrapper for semantic feedback apply.
# Defaults:
# - feedback file: semantic_feedback.json
# - seeds file:    semantic_scholar_seeds.json
# - manifest file: latest artifacts/run_feedback_manifest_*.json
#
# Usage:
#   scripts/apply_semantic_feedback_latest.sh
#   scripts/apply_semantic_feedback_latest.sh --dry-run

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

DRY_RUN_FLAG="${1:-}"
if [[ -n "${DRY_RUN_FLAG}" && "${DRY_RUN_FLAG}" != "--dry-run" ]]; then
  echo "Usage: $0 [--dry-run]"
  exit 1
fi

LATEST_MANIFEST="$(ls -1t artifacts/run_feedback_manifest_*.json 2>/dev/null | head -n 1 || true)"
if [[ -z "${LATEST_MANIFEST}" ]]; then
  echo "❌ no manifest found under artifacts/ (expected run_feedback_manifest_*.json)"
  exit 1
fi

FEEDBACK_FILE="semantic_feedback.json"
SEEDS_FILE="semantic_scholar_seeds.json"

if [[ ! -f "${FEEDBACK_FILE}" ]]; then
  echo "❌ feedback file not found: ${FEEDBACK_FILE}"
  exit 1
fi

echo "Using manifest: ${LATEST_MANIFEST}"
if [[ "${DRY_RUN_FLAG}" == "--dry-run" ]]; then
  exec ./scripts/apply_semantic_feedback.sh "${LATEST_MANIFEST}" "${FEEDBACK_FILE}" "${SEEDS_FILE}" --dry-run
fi

exec ./scripts/apply_semantic_feedback.sh "${LATEST_MANIFEST}" "${FEEDBACK_FILE}" "${SEEDS_FILE}"
