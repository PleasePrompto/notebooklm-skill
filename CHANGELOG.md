# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-12-20

### BREAKING CHANGES

**UV Shebang Conversion**
- Converted from manual venv management to UV shebang scripts with PEP 723 inline metadata
- Command pattern changed: `python scripts/run.py script.py` → `./scripts/script.py` or `uv run scripts/script.py`
- Requires UV installation: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Migration Guide

**1. Install UV:**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**2. Update skill:**
```bash
cd ~/.claude/skills/notebooklm
git pull
```

**3. Clean old environment (optional):**
```bash
rm -rf .venv  # No longer needed
```

**4. Make scripts executable (Unix/Mac only):**
```bash
chmod +x scripts/*.py
```

**Updated Commands:**

| Old Command | New Command (Unix/Mac) | New Command (Windows) |
|-------------|------------------------|------------------------|
| `python scripts/run.py auth_manager.py status` | `./scripts/auth_manager.py status` | `uv run scripts\auth_manager.py status` |
| `python scripts/run.py notebook_manager.py list` | `./scripts/notebook_manager.py list` | `uv run scripts\notebook_manager.py list` |
| `python scripts/run.py ask_question.py --question "..."` | `./scripts/ask_question.py --question "..."` | `uv run scripts\ask_question.py --question "..."` |

**First run:** Dependencies install automatically (one-time, ~30 seconds)

**Troubleshooting:**

- **"uv: command not found"**: Install uv and restart terminal
- **"Permission denied"**: Run `chmod +x scripts/*.py` (Unix/Mac)
- **Windows users**: Always use `uv run scripts\script.py` syntax

**Rollback to v1.3.0:**
```bash
cd ~/.claude/skills/notebooklm
git checkout v1.3.0
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m patchright install chrome
```

### Added
- UV shebang with PEP 723 inline metadata in all entry point scripts
- Automatic dependency installation on first run
- Dependency caching for instant subsequent runs

### Removed
- `scripts/run.py` - Replaced by UV shebang
- `scripts/setup_environment.py` - Replaced by UV automatic setup
- `requirements.txt` - Dependencies now inline in scripts

### Changed
- All scripts now directly executable with UV shebang
- Updated documentation for UV usage pattern
- Simplified installation process (no manual venv setup)

## [1.3.0] - 2025-11-21

### Added
- **Modular Architecture** - Refactored codebase for better maintainability
  - New `config.py` - Centralized configuration (paths, selectors, timeouts)
  - New `browser_utils.py` - BrowserFactory and StealthUtils classes
  - Cleaner separation of concerns across all scripts

### Changed
- **Timeout increased to 120 seconds** - Long queries no longer timeout prematurely
  - `ask_question.py`: 30s → 120s
  - `browser_session.py`: 30s → 120s
  - Resolves Issue #4

### Fixed
- **Thinking Message Detection** - Fixed incomplete answers showing placeholder text
  - Now waits for `div.thinking-message` element to disappear before reading answer
  - Answers like "Reviewing the content..." or "Looking for answers..." no longer returned prematurely
  - Works reliably across all languages and NotebookLM UI changes

- **Correct CSS Selectors** - Updated to match current NotebookLM UI
  - Changed from `.response-content, .message-content` to `.to-user-container .message-text-content`
  - Consistent selectors across all scripts

- **Stability Detection** - Improved answer completeness check
  - Now requires 3 consecutive stable polls instead of 1 second wait
  - Prevents truncated responses during streaming

## [1.2.0] - 2025-10-28

### Added
- Initial public release
- NotebookLM integration via browser automation
- Session-based conversations with Gemini 2.5
- Notebook library management
- Knowledge base preparation tools
- Google authentication with persistent sessions
