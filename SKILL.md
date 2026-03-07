---
name: notebooklm
description: Use this skill to query and manage Google NotebookLM notebooks directly from Claude Code/OpenClaw. Supports auth, remote notebook discovery, notebook creation, source import, and source-grounded Q&A.
---

# NotebookLM Research Assistant Skill

Interact with Google NotebookLM to discover notebooks, create new notebooks, add sources, run Fast/Deep Research source discovery, and query them with source-grounded answers.

## When to Use This Skill

Trigger when user:
- Mentions NotebookLM explicitly
- Shares NotebookLM URL (`https://notebooklm.google.com/notebook/...`)
- Asks to query or manage their notebooks
- Wants to discover available notebooks under the logged-in Google account
- Wants to create a notebook or add a source into NotebookLM
- Wants NotebookLM to discover new sources via Fast Research or Deep Research

## Critical: Always Use `run.py` Wrapper

**NEVER call scripts directly. ALWAYS use `python scripts/run.py [script]`:**

```bash
# ✅ CORRECT
python scripts/run.py auth_manager.py status
python scripts/run.py notebook_manager.py list
python scripts/run.py notebook_manager.py sync-remote
python scripts/run.py notebook_manager.py create --name "My Notebook"
python scripts/run.py notebook_manager.py add-source --notebook-url "https://notebooklm.google.com/notebook/..." --source-url "https://example.com"
python scripts/run.py notebook_manager.py discover-sources --notebook-url "https://notebooklm.google.com/notebook/..." --query "agent tool learning survey"
python scripts/run.py notebook_manager.py discover-sources --notebook-url "https://notebooklm.google.com/notebook/..." --query "agent tool learning survey" --mode deep-research
python scripts/run.py ask_question.py --question "..."

# ❌ WRONG
python scripts/auth_manager.py status
```

The wrapper automatically:
1. Creates `.venv` if needed
2. Installs dependencies
3. Activates the environment
4. Executes the target script properly

## Proxy Requirement on Linux

NotebookLM often needs an explicit browser proxy on Linux. Prefer the Singapore exit when available.

Supported env vars:

```bash
export NOTEBOOKLM_PROXY_URL=http://127.0.0.1:7890
# optional
export NOTEBOOKLM_PROXY_BYPASS=localhost,127.0.0.1
```

If `NOTEBOOKLM_PROXY_URL` is unset, the skill falls back to standard `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY`.

## Core Workflow

### 1) Check Authentication
```bash
python scripts/run.py auth_manager.py status
python scripts/run.py auth_manager.py validate
```

If not authenticated, proceed to setup.

### 2) Authenticate
```bash
python scripts/run.py auth_manager.py setup
```

Important:
- Browser must be visible for manual Google login
- Authentication is valid only when the browser actually enters NotebookLM UI
- Redirects to Google login, account chooser, or password challenge do **not** count as success

### 3) Manage Notebook Library

**Manual library**
```bash
python scripts/run.py notebook_manager.py add \
  --url "https://notebooklm.google.com/notebook/..." \
  --name "Descriptive Name" \
  --description "What this notebook contains" \
  --topics "topic1,topic2"

python scripts/run.py notebook_manager.py list
python scripts/run.py notebook_manager.py search --query "keyword"
python scripts/run.py notebook_manager.py activate --id notebook-id
python scripts/run.py notebook_manager.py remove --id notebook-id
python scripts/run.py notebook_manager.py stats
```

**Remote discovery / sync**
```bash
python scripts/run.py notebook_manager.py list-remote
python scripts/run.py notebook_manager.py sync-remote
```

`sync-remote` writes fetched notebooks into `data/library.json` under a remote section, distinct from manually added entries.

### 4) Create NotebookLM Notebooks
```bash
python scripts/run.py notebook_manager.py create
python scripts/run.py notebook_manager.py create --name "My New Notebook"
python scripts/run.py notebook_manager.py create --name "My New Notebook" --show-browser
```

Returns the new notebook title and URL. If UI title editing is unavailable, the command still returns the created URL and reports the limitation.

### 5) Add Sources to a Notebook

**Web / YouTube / Google Docs / Slides links**
```bash
python scripts/run.py notebook_manager.py add-source \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --source-url "https://example.com"

python scripts/run.py notebook_manager.py add-source \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --source-url "https://www.youtube.com/watch?v=..."

python scripts/run.py notebook_manager.py add-source \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --source-url "https://docs.google.com/document/d/.../edit"
```

**Local file / local PDF**
```bash
python scripts/run.py notebook_manager.py add-source \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --file "/path/to/file.pdf"
```

**PDF URL**
```bash
python scripts/run.py notebook_manager.py add-source \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --source-url "https://arxiv.org/pdf/1706.03762.pdf"
```

PDF URLs are downloaded first, then uploaded through NotebookLM's file upload UI.

### 6) Discover Sources with Research
```bash
python scripts/run.py notebook_manager.py discover-sources \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --query "latest notebooklm research papers"

python scripts/run.py notebook_manager.py discover-sources \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --query "agent tool learning survey" \
  --mode fast-research

python scripts/run.py notebook_manager.py discover-sources \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --query "agent tool learning survey" \
  --mode deep-research

# If you only want the results page and do not want auto-import:
python scripts/run.py notebook_manager.py discover-sources \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --query "agent tool learning survey" \
  --mode deep-research \
  --no-import
```

Behavior:
- Reuses the Sources view / Add source flow
- Types the query through real UI input events
- Returns visible candidate results and progress states
- Auto-clicks `Import` by default when NotebookLM exposes it
- Verifies import by re-opening the notebook and checking persisted source count
- For `--mode deep-research`, also returns `deep_research_details` when NotebookLM exposes the detailed sources panel

Deep Research return fields:
- `deep_research_details.report_title` — NotebookLM report title
- `deep_research_details.report_subtitle` — report subtitle (for example `based on 51 sources`)
- `deep_research_details.cited_count` — count from the `Cited in Report` tab
- `deep_research_details.not_cited_count` — count from the `Not cited` tab
- `deep_research_details.cited_sources` — structured list of cited entries, each with `title` and optional `snippet`
- `deep_research_details.not_cited_sources` — structured list of non-cited entries, each with `title` and optional `snippet`

Import verification fields:
- `source_count_before` — persisted source count before research/import
- `source_count_after` — persisted source count after import confirmation
- `import_result.source_count_before` / `import_result.source_count_after` — post-import persistence check details
- `auto_import_requested` — whether the command attempted Import automatically

### 7) Ask Questions
```bash
# Stateless mode (existing behavior)
python scripts/run.py ask_question.py --question "Your question here"
python scripts/run.py ask_question.py --question "..." --notebook-id notebook-id
python scripts/run.py ask_question.py --question "..." --notebook-url "https://..."
python scripts/run.py ask_question.py --question "..." --show-browser

# Persistent session mode
python scripts/run.py session_manager.py create --notebook-url "https://notebooklm.google.com/notebook/..."
python scripts/run.py session_manager.py ask --session-id session-xxxxxxxxxxxx --question "first question"
python scripts/run.py session_manager.py ask --session-id session-xxxxxxxxxxxx --question "follow-up question"

# Optional shortcut: reuse a persistent session via ask_question.py
python scripts/run.py ask_question.py --session-id session-xxxxxxxxxxxx --question "follow-up question"
```

### 8) Persistent Session Lifecycle
```bash
python scripts/run.py session_manager.py list
python scripts/run.py session_manager.py info --session-id session-xxxxxxxxxxxx
python scripts/run.py session_manager.py reset --session-id session-xxxxxxxxxxxx
python scripts/run.py session_manager.py close --session-id session-xxxxxxxxxxxx
python scripts/run.py session_manager.py gc
```

Behavior:
- `session_manager.py` starts a background process on demand and keeps one live browser context alive
- Each `session_id` maps to one reusable NotebookLM tab/page
- Same-session asks are serialized through the daemon so only one question runs at a time
- Idle sessions are auto-expired after the configured timeout (default `1800` seconds)
- Stateless `ask_question.py` remains the default and is unchanged unless `--session-id` is passed

## Navigation / Error Model

The automation reports these states clearly instead of silently failing:
- Redirected to Google login page
- Redirected to Google account chooser
- Sent to Google password challenge page
- Notebook deep link fell back to NotebookLM home page
- Source import/upload failed
- Source import/upload timed out without confirmation
- Sources view / research controls missing
- Fast Research / Deep Research selector missing
- Research query input missing or submission did not start
- Deep Research timed out mid-run
- Research finished without visible results
- Import button missing, click failed, or imported sources did not persist

The navigation layer waits for URL settling before classifying pages so SPA redirects do not cause false positives.

## Data Storage

All state stays in the skill directory:
- `data/library.json` — manual notebooks + remote-synced notebooks
- `data/auth_info.json` — auth metadata
- `data/browser_state/` — browser cookies and session state
- `data/sessions.json` — serializable persistent-session metadata (`session_id`, `notebook_url`, timestamps, counts, status)
- `data/session_runtime/` — daemon runtime files such as the local socket / pid file

## Best Practices

1. Always use `run.py`
2. Validate auth before deeper workflows
3. Use `sync-remote` before asking users for notebook URLs they may not remember
4. Prefer `--show-browser` when debugging UI changes
5. Keep manual library metadata human-meaningful; keep remote sync separate

## Limitations

- NotebookLM UI can change selectors without notice
- Google Docs / Slides links currently go through NotebookLM's URL import path; if the account/UI refuses them, the command reports a clear error instead of silently succeeding
- Free Google accounts still have NotebookLM-side rate limits
