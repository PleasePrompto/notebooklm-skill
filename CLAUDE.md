# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running Scripts

All scripts must be run through the `run.py` wrapper — never call scripts directly:

```bash
# Authentication
python scripts/run.py auth_manager.py setup    # First-time Google login (browser opens)
python scripts/run.py auth_manager.py status   # Check auth state
python scripts/run.py auth_manager.py reauth   # Re-authenticate
python scripts/run.py auth_manager.py clear    # Clear auth data

# Notebook library
python scripts/run.py notebook_manager.py list
python scripts/run.py notebook_manager.py add --url URL --name NAME --description DESC --topics TOPICS
python scripts/run.py notebook_manager.py activate --id ID
python scripts/run.py notebook_manager.py remove --id ID

# Query
python scripts/run.py ask_question.py --question "..." --notebook-id ID
python scripts/run.py ask_question.py --question "..." --notebook-url URL
python scripts/run.py ask_question.py --question "..." --show-browser   # debug mode

# Cleanup
python scripts/run.py cleanup_manager.py              # preview
python scripts/run.py cleanup_manager.py --confirm    # execute
```

The `run.py` wrapper auto-creates `.venv` and installs dependencies (including Chrome via `patchright install chrome`) on first run.

## Architecture

```
scripts/
  run.py              — venv bootstrap + subprocess launcher
  config.py           — all paths, CSS selectors, and timeouts (single source of truth)
  auth_manager.py     — Google login, browser state persistence (7-day TTL)
  browser_utils.py    — BrowserFactory (persistent Chrome context), StealthUtils
  browser_session.py  — low-level session wrapper
  notebook_manager.py — NotebookLibrary class: JSON-backed notebook registry
  ask_question.py     — main query flow: auth check → browser → NotebookLM → answer
  cleanup_manager.py  — clears browser state / auth / library selectively
  setup_environment.py — first-run venv + Chrome install
```

**Auth model**: Hybrid — persistent browser profile (`data/browser_state/browser_profile/`) for fingerprint consistency + manual cookie injection from `data/browser_state/state.json` to work around a Playwright bug. State expires after 7 days.

**Session model**: Stateless. Each `ask_question.py` call opens a fresh browser, sends the question, waits for a stable (non-streaming) response, then closes. No cross-question context.

**Answer stability detection**: Waits for `div.thinking-message` to disappear, then requires 3 consecutive stable polls before returning — prevents truncated streaming responses.

## Key Configuration (`scripts/config.py`)

- `QUERY_TIMEOUT_SECONDS = 120` — increase if long queries time out
- `QUERY_INPUT_SELECTORS` / `RESPONSE_SELECTORS` — update here if NotebookLM's UI changes
- `LIBRARY_FILE` = `data/library.json` — notebook registry
- `STATE_FILE` = `data/browser_state/state.json` — auth cookies

## Data Directory

`data/` is gitignored and contains sensitive auth state. Never commit it.

## Dependencies

Only two: `patchright==1.55.2` (Playwright-based stealth automation) and `python-dotenv==1.0.0`. Pinned in `requirements.txt`. After pip install, Chrome must be installed separately: `patchright install chrome`.
