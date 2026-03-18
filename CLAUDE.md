# Cost Control Rules

- Never load files larger than 100 lines into context unless explicitly needed.
- For simple tasks like reading files or checking status, suggest switching to a cheaper model with /model before starting.
- On long sessions, remind the user to run /compact every 30 minutes.
- Reserve Opus for complex architecture, hard debugging, and quality-critical tasks.

---

# Repository Purpose

This is a **Claude Code Skill** that integrates Google NotebookLM with Claude Code. It enables Claude to query NotebookLM notebooks directly via browser automation, retrieving source-grounded, citation-backed answers from Gemini exclusively from the user's uploaded documents. This drastically reduces hallucinations compared to feeding raw docs to Claude.

---

# Architecture Overview

```
notebooklm-skill/
├── SKILL.md                  # Claude instructions (triggers, commands, workflows)
├── AUTHENTICATION.md         # Auth architecture explanation
├── CHANGELOG.md              # Version history
├── requirements.txt          # Python dependencies (patchright, python-dotenv)
├── scripts/
│   ├── run.py                # Universal wrapper — ALWAYS use this to run scripts
│   ├── config.py             # Centralized config: paths, selectors, timeouts
│   ├── setup_environment.py  # First-run venv + Chrome installation
│   ├── ask_question.py       # Query a NotebookLM notebook
│   ├── auth_manager.py       # Google authentication management
│   ├── browser_session.py    # Browser session abstraction
│   ├── browser_utils.py      # BrowserFactory + StealthUtils
│   ├── notebook_manager.py   # Notebook library CRUD
│   ├── mcp_server.py         # MCP server (JSON-RPC via stdio)
│   ├── monitor.py            # Real-time activity monitoring
│   └── cleanup_manager.py    # Data cleanup utility
├── references/
│   ├── api_reference.md      # Detailed script API docs
│   ├── troubleshooting.md    # Common issues and fixes
│   └── usage_patterns.md     # Best practices and examples
└── .venv/                    # Auto-created isolated Python environment
```

**Data directory** (outside repo, not committed):
```
~/.claude/skills/notebooklm/data/
├── library.json              # Notebook metadata
├── auth_info.json            # Authentication status
├── browser_state/
│   ├── state.json            # Cookies for manual injection (critical!)
│   └── browser_profile/     # Chrome persistent profile
├── activity.log              # Real-time event log
└── metrics.json              # Performance metrics
```

---

# Key Implementation Details

## Always Use `run.py`

Never call scripts directly. The `run.py` wrapper auto-creates `.venv`, installs dependencies, and activates the environment:

```bash
# CORRECT
python scripts/run.py ask_question.py --question "..."

# WRONG — fails without venv
python scripts/ask_question.py --question "..."
```

## Authentication: Hybrid Approach

Due to a Playwright bug ([#36139](https://github.com/microsoft/playwright/issues/36139)), session cookies are NOT persisted when using `launch_persistent_context()` with `user_data_dir` in Python. The workaround:

1. **Setup phase**: Save all cookies to `state.json` after manual login
2. **Runtime phase**: Launch with `user_data_dir` (fingerprint), then manually inject cookies from `state.json`

This is documented in detail in `AUTHENTICATION.md`.

## MCP Server (`mcp_server.py`)

The skill also runs as an MCP server registered in `.mcp.json`. Tools exposed:
- `query_notebook` — Ask a question, get source-grounded answer
- `list_notebooks` — List library
- `add_notebook` — Add with url, name, description, topics
- `get_notebook` — Look up by ID or name
- `trigger_action` — Run `summarize`, `key-points`, `questions`, or `custom`

The MCP server uses JSON-RPC 2.0 over stdio.

## CSS Selectors (may need updating if NotebookLM UI changes)

```python
# config.py
QUERY_INPUT_SELECTORS = ["textarea.query-box-input", ...]
RESPONSE_SELECTORS = [".to-user-container .message-text-content", ...]
```

If queries fail, check whether NotebookLM changed their DOM structure.

## Timeouts

- `QUERY_TIMEOUT_SECONDS = 120` — Long queries need time; do not reduce
- `PAGE_LOAD_TIMEOUT = 30000` ms
- Stability detection: requires 3 consecutive stable polls before accepting answer

---

# Common Tasks

## Running queries
```bash
python scripts/run.py ask_question.py --question "What is X?" --notebook-id ID
python scripts/run.py ask_question.py --question "..." --notebook-url "https://notebooklm.google.com/..."
```

## Managing notebooks
```bash
python scripts/run.py notebook_manager.py list
python scripts/run.py notebook_manager.py add --url URL --name NAME --description DESC --topics t1,t2
python scripts/run.py notebook_manager.py search --query keyword
python scripts/run.py notebook_manager.py activate --id ID
python scripts/run.py notebook_manager.py remove --id ID
```

## Authentication
```bash
python scripts/run.py auth_manager.py status   # Check
python scripts/run.py auth_manager.py setup    # Initial (browser opens)
python scripts/run.py auth_manager.py reauth   # Re-authenticate
python scripts/run.py auth_manager.py clear    # Reset
```

## Monitoring
```bash
python scripts/run.py monitor.py status   # One-shot summary
python scripts/run.py monitor.py watch    # Live dashboard
python scripts/run.py monitor.py clear    # Reset logs
```

## Testing MCP server
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python scripts/run.py mcp_server.py
```

---

# Dependencies

- **patchright==1.55.2** — Playwright-based browser automation with stealth patches
- **python-dotenv==1.0.0** — Environment configuration from `.env`
- **Google Chrome** (not Chromium) — Required for reliable Google auth; installed automatically

---

# Debugging Tips

| Problem | Investigation |
|---------|--------------|
| `ModuleNotFoundError` | Ensure using `run.py` wrapper |
| Auth fails at runtime | Check `state.json` exists in `browser_state/`; re-run `auth_manager.py setup` |
| Incomplete answers | Check for `div.thinking-message` timeout; may need selector update |
| `NotebookNotFound` | Run `notebook_manager.py list` to verify IDs |
| CSS selector mismatch | NotebookLM UI may have changed; inspect DOM and update `config.py` |

Browser visibility for debugging: add `--show-browser` flag to `ask_question.py`.

---

# Security Notes

- `data/` directory is in `.gitignore` — never commit it (contains auth cookies)
- API keys / credentials never leave the local machine
- Recommend a dedicated Google account for automation
