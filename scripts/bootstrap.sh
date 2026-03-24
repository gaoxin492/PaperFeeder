#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

echo "==> Bootstrapping PaperFeeder in $ROOT_DIR"
echo "==> Using Python: $PYTHON_BIN"

if [ ! -d "$VENV_DIR" ]; then
  echo "==> Creating virtual environment: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  echo "==> Reusing existing virtual environment: $VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

echo "==> Upgrading pip"
python -m pip install --upgrade pip

echo "==> Installing dependencies"
pip install -r requirements.txt

if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    echo "==> Creating .env from .env.example"
    cp .env.example .env
  else
    echo "==> Creating empty .env (no .env.example found)"
    : > .env
  fi
else
  echo "==> Keeping existing .env"
fi

echo ""
echo "Bootstrap complete."
echo "Next steps:"
echo "  1) Edit .env and add your API keys"
echo "  2) Edit config.yaml and user/ files (blogs, research_interests, keywords, categories)"
echo "  3) Run: source $VENV_DIR/bin/activate && python main.py --dry-run"

