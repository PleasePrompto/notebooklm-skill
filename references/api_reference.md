# NotebookLM Skill API Reference

Complete API documentation for all NotebookLM skill modules.

## Prerequisites

**All commands require UV to be installed:**

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Command patterns:**
- **Unix/Mac**: `./scripts/script.py` (direct execution)
- **All platforms**: `uv run scripts/script.py` (explicit uv)
- **Windows**: `uv run scripts\script.py` (backslash paths)

**First run**: Dependencies install automatically (~30 seconds, one-time)

## Core Scripts

### ask_question.py
Query NotebookLM with automated browser interaction.

```bash
# Basic usage (Unix/Mac)
./scripts/ask_question.py --question "Your question"

# All platforms
uv run scripts/ask_question.py --question "Your question"

# With specific notebook
./scripts/ask_question.py --question "..." --notebook-id notebook-id

# With direct URL
./scripts/ask_question.py --question "..." --notebook-url "https://..."

# Show browser (debugging)
./scripts/ask_question.py --question "..." --show-browser
```

**Parameters:**
- `--question` (required): Question to ask
- `--notebook-id`: Use notebook from library
- `--notebook-url`: Use URL directly
- `--show-browser`: Make browser visible

**Returns:** Answer text with follow-up prompt appended

### notebook_manager.py
Manage notebook library with CRUD operations.

```bash
# Smart Add (discover content first)
./scripts/ask_question.py --question "What is the content of this notebook? What topics are covered? Provide a complete overview briefly and concisely" --notebook-url "[URL]"
# Then add with discovered info
./scripts/notebook_manager.py add \
  --url "https://notebooklm.google.com/notebook/..." \
  --name "Name" \
  --description "Description" \
  --topics "topic1,topic2"

# Direct add (when you know the content)
./scripts/notebook_manager.py add \
  --url "https://notebooklm.google.com/notebook/..." \
  --name "Name" \
  --description "What it contains" \
  --topics "topic1,topic2"

# List notebooks
./scripts/notebook_manager.py list

# Search notebooks
./scripts/notebook_manager.py search --query "keyword"

# Activate notebook
./scripts/notebook_manager.py activate --id notebook-id

# Remove notebook
./scripts/notebook_manager.py remove --id notebook-id

# Show statistics
./scripts/notebook_manager.py stats
```

**Commands:**
- `add`: Add notebook (requires --url, --name, --topics)
- `list`: Show all notebooks
- `search`: Find notebooks by keyword
- `activate`: Set default notebook
- `remove`: Delete from library
- `stats`: Display library statistics

### auth_manager.py
Handle Google authentication and browser state.

```bash
# Setup (browser visible for login)
./scripts/auth_manager.py setup

# Check status
./scripts/auth_manager.py status

# Re-authenticate
./scripts/auth_manager.py reauth

# Clear authentication
./scripts/auth_manager.py clear
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
./scripts/cleanup_manager.py

# Execute cleanup
./scripts/cleanup_manager.py --confirm

# Keep library
./scripts/cleanup_manager.py --confirm --preserve-library

# Force without prompt
./scripts/cleanup_manager.py --confirm --force
```

**Options:**
- `--confirm`: Actually perform cleanup
- `--preserve-library`: Keep notebook library
- `--force`: Skip confirmation prompt

### UV Automatic Dependency Management

All scripts use UV shebang with PEP 723 inline metadata for automatic dependency management.

**How it works:**
1. First run: UV installs dependencies (~30 seconds)
2. Subsequent runs: Instant execution (cached)
3. No manual venv setup needed
4. Dependencies declared inline in each script

**Making scripts executable (Unix/Mac only):**
```bash
chmod +x scripts/*.py
```

## Python API Usage

### Using subprocess with UV

```python
import subprocess
import json

# Direct execution (Unix/Mac)
result = subprocess.run([
    "./scripts/ask_question.py",
    "--question", "Your question",
    "--notebook-id", "notebook-id"
], capture_output=True, text=True)

# Or explicit uv (all platforms)
result = subprocess.run([
    "uv", "run", "scripts/ask_question.py",
    "--question", "Your question",
    "--notebook-id", "notebook-id"
], capture_output=True, text=True)

answer = result.stdout
```

### Direct imports with uv run

```python
# Using uv run for module imports
import subprocess

# Execute in UV environment
result = subprocess.run([
    "uv", "run", "python", "-c",
    """
from scripts.notebook_manager import NotebookLibrary
library = NotebookLibrary()
print(len(library.list_notebooks()))
"""
], capture_output=True, text=True, cwd="~/.claude/skills/notebooklm")

print(result.stdout)
```

## Data Storage

Location: `~/.claude/skills/notebooklm/data/`

```
data/
├── library.json       # Notebook metadata
├── auth_info.json     # Auth status
└── browser_state/     # Browser cookies
    └── state.json
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
# UV handles dependencies automatically
result = subprocess.run([
    "./scripts/ask_question.py",
    "--question", "Question"
], capture_output=True, text=True)

if result.returncode != 0:
    error = result.stderr
    if "rate limit" in error.lower():
        # Wait or switch accounts
        pass
    elif "not authenticated" in error.lower():
        # Run auth setup
        subprocess.run(["./scripts/auth_manager.py", "setup"])
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
        "./scripts/ask_question.py",
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
            "./scripts/ask_question.py",
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

### AuthManager
- `is_authenticated()`
- `setup_auth(headless=False)`
- `get_auth_info()`
- `clear_auth()`
- `validate_auth()`

### BrowserSession (internal)
- Handles browser automation
- Manages stealth behavior
- Not intended for direct use

## Best Practices

1. **Install UV first** - Required for all operations
2. **Make scripts executable** - `chmod +x scripts/*.py` (Unix/Mac)
3. **Check auth first** - Before operations
4. **Handle rate limits** - Implement retries
5. **Include context** - Questions are independent
6. **Clean sessions** - Use cleanup_manager
7. **First run delay** - Dependencies install automatically (~30s)