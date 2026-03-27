#!/bin/bash
# NotebookLM Environment Diagnostic

echo "🔍 === Python Environment ==="
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version)
    echo "✅ $PY_VER detected"
else
    echo "❌ Python 3 not found"
    exit 1
fi

if [ -d ".venv" ]; then
    echo "✅ Virtual environment (.venv) present"
else
    echo "⚠️ .venv missing. It will be auto-created on first run of scripts/run.py"
fi

echo -e "\n🔐 === Auth Status ==="
if [ -f "data/auth_info.json" ]; then
    echo "✅ Auth credentials found"
else
    echo "⚠️ No auth data found. Run 'NotebookLM: Auth Setup' task."
fi