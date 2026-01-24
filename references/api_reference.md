# NotebookLM Skill API Reference

Complete API documentation for all NotebookLM skill modules.

## Important: Always Use run.py Wrapper

**All commands must use the `run.py` wrapper to ensure proper environment:**

```bash
# ✅ CORRECT:
python3 scripts/run.py [script_name].py [arguments]

# ❌ WRONG:
python scripts/[script_name].py [arguments]  # Will fail without venv!
```

## Core Scripts

### ask_question.py
Query NotebookLM with automated browser interaction and intelligent source filtering.

```bash
# Basic usage
python3 scripts/run.py ask_question.py --question "Your question"

# With specific notebook
python3 scripts/run.py ask_question.py --question "..." --notebook-id notebook-id

# With direct URL
python3 scripts/run.py ask_question.py --question "..." --notebook-url "https://..."

# Show browser (debugging)
python3 scripts/run.py ask_question.py --question "..." --show-browser

# Source filtering options
python3 scripts/run.py ask_question.py --question "..." --keyword-filter  # Use keywords instead of LLM
python3 scripts/run.py ask_question.py --question "..." --threshold 7     # Higher = fewer sources (1-10)
python3 scripts/run.py ask_question.py --question "..." --no-filter       # Disable source filtering
```

**Parameters:**
- `--question` (required): Question to ask
- `--notebook-id`: Use notebook from library
- `--notebook-url`: Use URL directly
- `--show-browser`: Make browser visible
- `--keyword-filter`: Use keyword matching instead of LLM scoring
- `--threshold N`: Minimum relevance score for LLM filter (1-10, default: 5)
- `--no-filter`: Disable source filtering entirely

**Source Filtering Flow:**
1. Loads cached source summaries from `data/library-source-summary/`
2. LLM (Gemini → Claude → keywords) scores each source 1-10
3. Deselects sources below threshold in browser
4. Queries only relevant sources

**Returns:** Answer text with follow-up prompt appended

### notebook_manager.py
Manage notebook library with CRUD operations and source summary management.

```bash
# Smart Add (discover content first)
python3 scripts/run.py ask_question.py --question "What is the content of this notebook? What topics are covered? Provide a complete overview briefly and concisely" --notebook-url "[URL]"
# Then add with discovered info
python3 scripts/run.py notebook_manager.py add \
  --url "https://notebooklm.google.com/notebook/..." \
  --name "Name" \
  --description "Description" \
  --topics "topic1,topic2"

# Direct add (when you know the content)
python3 scripts/run.py notebook_manager.py add \
  --url "https://notebooklm.google.com/notebook/..." \
  --name "Name" \
  --description "What it contains" \
  --topics "topic1,topic2"

# List notebooks
python3 scripts/run.py notebook_manager.py list

# Search notebooks
python3 scripts/run.py notebook_manager.py search --query "keyword"

# Activate notebook
python3 scripts/run.py notebook_manager.py activate --id notebook-id

# Remove notebook
python3 scripts/run.py notebook_manager.py remove --id notebook-id

# Show statistics
python3 scripts/run.py notebook_manager.py stats

# Source Summary Management
python3 scripts/run.py notebook_manager.py update-sources --id ID        # Update (incremental)
python3 scripts/run.py notebook_manager.py update-sources --id ID --force # Re-extract all
python3 scripts/run.py notebook_manager.py update-sources --all          # Update all notebooks
python3 scripts/run.py notebook_manager.py show-sources --id ID          # Display cached summaries
```

**Commands:**
- `add`: Add notebook (requires --url, --name, --topics) - auto-extracts source summaries
- `list`: Show all notebooks
- `search`: Find notebooks by keyword
- `activate`: Set default notebook
- `remove`: Delete from library
- `stats`: Display library statistics
- `update-sources`: Update source summaries (--force to re-extract all)
- `show-sources`: Display cached source summaries

### auth_manager.py
Handle Google authentication and browser state.

```bash
# Setup (browser visible for login)
python3 scripts/run.py auth_manager.py setup

# Check status
python3 scripts/run.py auth_manager.py status

# Re-authenticate
python3 scripts/run.py auth_manager.py reauth

# Clear authentication
python3 scripts/run.py auth_manager.py clear
```

**Commands:**
- `setup`: Initial authentication (browser MUST be visible)
- `status`: Check if authenticated
- `reauth`: Clear and re-setup
- `clear`: Remove all auth data

### cleanup_manager.py
Clean skill data with preservation options.

```bash
# Preview cleanup
python3 scripts/run.py cleanup_manager.py

# Execute cleanup
python3 scripts/run.py cleanup_manager.py --confirm

# Keep library
python3 scripts/run.py cleanup_manager.py --confirm --preserve-library

# Force without prompt
python3 scripts/run.py cleanup_manager.py --confirm --force
```

**Options:**
- `--confirm`: Actually perform cleanup
- `--preserve-library`: Keep notebook library
- `--force`: Skip confirmation prompt

### run.py
Script wrapper that handles environment setup.

```bash
# Usage
python3 scripts/run.py [script_name].py [arguments]

# Examples
python3 scripts/run.py auth_manager.py status
python3 scripts/run.py ask_question.py --question "..."
```

**Automatic actions:**
1. Creates `.venv` if missing
2. Installs dependencies
3. Activates environment
4. Executes target script

## Python API Usage

### Using subprocess with run.py

```python
import subprocess
import json

# Always use run.py wrapper
result = subprocess.run([
    "python", "scripts/run.py", "ask_question.py",
    "--question", "Your question",
    "--notebook-id", "notebook-id"
], capture_output=True, text=True)

answer = result.stdout
```

### Direct imports (after venv exists)

```python
# Only works if venv is already created and activated
from notebook_manager import NotebookLibrary
from auth_manager import AuthManager

library = NotebookLibrary()
notebooks = library.list_notebooks()

auth = AuthManager()
is_auth = auth.is_authenticated()
```

## Data Storage

Location: `~/.claude/skills/notebooklm/data/`

```
data/
├── library.json              # Notebook metadata
├── auth_info.json            # Auth status
├── browser_state/            # Browser cookies
│   └── state.json
└── library-source-summary/   # Cached source summaries
    └── {notebook-id}.md      # Source titles and summaries per notebook
```

**Source Summary Format:**
```markdown
# Source Summary: Notebook Name

**Notebook ID:** `notebook-id`
**Generated:** 2026-01-24 12:00:00
**Total Sources:** 18

---

### Source Title 1.pdf

Summary of the source content extracted from NotebookLM's Source Guide...

---

### Source Title 2.md

Another source summary...
```

**Security:** Protected by `.gitignore`, never commit.

## Environment Variables

Optional `.env` file configuration:

```env
HEADLESS=false           # Browser visibility
SHOW_BROWSER=false       # Default display
STEALTH_ENABLED=true     # Human behavior
TYPING_WPM_MIN=160       # Typing speed
TYPING_WPM_MAX=240
DEFAULT_NOTEBOOK_ID=     # Default notebook
```

## Error Handling

Common patterns:

```python
# Using run.py prevents most errors
result = subprocess.run([
    "python", "scripts/run.py", "ask_question.py",
    "--question", "Question"
], capture_output=True, text=True)

if result.returncode != 0:
    error = result.stderr
    if "rate limit" in error.lower():
        # Wait or switch accounts
        pass
    elif "not authenticated" in error.lower():
        # Run auth setup
        subprocess.run(["python", "scripts/run.py", "auth_manager.py", "setup"])
```

## Rate Limits

Free Google accounts: 50 queries/day

Solutions:
1. Wait for reset (midnight PST)
2. Switch accounts with `reauth`
3. Use multiple Google accounts

## Advanced Patterns

### Parallel Queries

```python
import concurrent.futures
import subprocess

def query(question, notebook_id):
    result = subprocess.run([
        "python", "scripts/run.py", "ask_question.py",
        "--question", question,
        "--notebook-id", notebook_id
    ], capture_output=True, text=True)
    return result.stdout

# Run multiple queries simultaneously
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [
        executor.submit(query, q, nb)
        for q, nb in zip(questions, notebooks)
    ]
    results = [f.result() for f in futures]
```

### Batch Processing

```python
def batch_research(questions, notebook_id):
    results = []
    for question in questions:
        result = subprocess.run([
            "python", "scripts/run.py", "ask_question.py",
            "--question", question,
            "--notebook-id", notebook_id
        ], capture_output=True, text=True)
        results.append(result.stdout)
        time.sleep(2)  # Avoid rate limits
    return results
```

## Module Classes

### NotebookLibrary
- `add_notebook(url, name, topics)`
- `list_notebooks()`
- `search_notebooks(query)`
- `get_notebook(notebook_id)`
- `activate_notebook(notebook_id)`
- `remove_notebook(notebook_id)`
- `fetch_source_summary(notebook_id)` - Extract source summaries via browser
- `update_source_summary(notebook_id, force=False)` - Update cached summaries
- `get_source_summary(notebook_id)` - Load cached summaries

### AuthManager
- `is_authenticated()`
- `setup_auth(headless=False)`
- `get_auth_info()`
- `clear_auth()`
- `validate_auth()`

### SourceFilter
- `get_relevant_sources(question, use_llm=True, threshold=5)` - Score and filter sources
- `_get_relevant_sources_llm(question, threshold)` - LLM-based scoring
- `_get_relevant_sources_keywords(question)` - Keyword-based scoring
- `_call_gemini(prompt)` - Call Gemini CLI
- `_call_claude(prompt)` - Call Claude CLI (fallback)
- `get_all_source_titles()` - Get all source titles

### SourceExtractor
- `extract_all_sources(notebook_url, headless=True)` - Extract all source summaries
- `get_existing_sources(notebook_id)` - Load existing summaries
- Used internally by NotebookLibrary

### BrowserSession (internal)
- Handles browser automation
- Manages stealth behavior
- Not intended for direct use

## Best Practices

1. **Always use run.py** - Ensures environment
2. **Check auth first** - Before operations
3. **Handle rate limits** - Implement retries
4. **Include context** - Questions are independent
5. **Clean sessions** - Use cleanup_manager