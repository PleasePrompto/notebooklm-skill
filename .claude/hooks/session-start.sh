#!/bin/bash
set -euo pipefail

# Only run in remote/web environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo '{"async": true, "asyncTimeout": 300000}'

SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_DIR="$SKILL_DIR/.venv"
REQUIREMENTS="$SKILL_DIR/requirements.txt"

# Skip if venv already exists
if [ -d "$VENV_DIR" ]; then
  exit 0
fi

echo "Setting up NotebookLM skill virtual environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$REQUIREMENTS" -q
"$VENV_DIR/bin/python" -m patchright install chrome
echo "NotebookLM skill environment ready."
