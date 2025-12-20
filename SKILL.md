---
name: notebooklm
description: Query Google NotebookLM notebooks for source-grounded, citation-backed answers from Gemini. Use when user mentions NotebookLM, shares notebook URLs, asks to query docs/notebooks, or wants document-only answers to avoid hallucinations. Browser automation with persistent auth.
---

# NotebookLM Research Assistant Skill

Interact with Google NotebookLM to query documentation with Gemini's source-grounded answers. Each question opens a fresh browser session, retrieves the answer exclusively from your uploaded documents, and closes.

## When to Use This Skill

Trigger when user:
- Mentions NotebookLM explicitly
- Shares NotebookLM URL (`https://notebooklm.google.com/notebook/...`)
- Asks to query their notebooks/documentation
- Wants to add documentation to NotebookLM library
- Uses phrases like "ask my NotebookLM", "check my docs", "query my notebook"

## ⚠️ CRITICAL: Add Command - Smart Discovery

When user wants to add a notebook without providing details:

**SMART ADD (Recommended)**: Query the notebook first to discover its content:
```bash
# Step 1: Query the notebook about its content
./scripts/ask_question.py --question "What is the content of this notebook? What topics are covered? Provide a complete overview briefly and concisely" --notebook-url "[URL]"

# Step 2: Use the discovered information to add it
./scripts/notebook_manager.py add --url "[URL]" --name "[Based on content]" --description "[Based on content]" --topics "[Based on content]"
```

**MANUAL ADD**: If user provides all details:
- `--url` - The NotebookLM URL
- `--name` - A descriptive name
- `--description` - What the notebook contains (REQUIRED!)
- `--topics` - Comma-separated topics (REQUIRED!)

NEVER guess or use generic descriptions! If details missing, use Smart Add to discover them.

## Running Scripts

All scripts use UV shebang for automatic dependency management.

**Unix/Mac (direct execution):**
```bash
./scripts/auth_manager.py status
./scripts/notebook_manager.py list
./scripts/ask_question.py --question "Your question here"
```

**All platforms (explicit uv):**
```bash
uv run scripts/auth_manager.py status
uv run scripts/notebook_manager.py list
uv run scripts/ask_question.py --question "Your question here"
```

**Windows:**
```bash
uv run scripts\auth_manager.py status
uv run scripts\notebook_manager.py list
uv run scripts\ask_question.py --question "Your question here"
```

**First run:** Dependencies install automatically (one-time, ~30 seconds)
**Subsequent runs:** Instant execution (uv caches dependencies)

## Core Workflow

### Step 1: Check Authentication Status
```bash
./scripts/auth_manager.py status
```

If not authenticated, proceed to setup.

### Step 2: Authenticate (One-Time Setup)
```bash
# Browser MUST be visible for manual Google login
./scripts/auth_manager.py setup
```

**Important:**
- Browser is VISIBLE for authentication
- Browser window opens automatically
- User must manually log in to Google
- Tell user: "A browser window will open for Google login"

### Step 3: Manage Notebook Library

```bash
# List all notebooks
./scripts/notebook_manager.py list

# BEFORE ADDING: Ask user for metadata if unknown!
# "What does this notebook contain?"
# "What topics should I tag it with?"

# Add notebook to library (ALL parameters are REQUIRED!)
./scripts/notebook_manager.py add \
  --url "https://notebooklm.google.com/notebook/..." \
  --name "Descriptive Name" \
  --description "What this notebook contains" \  # REQUIRED - ASK USER IF UNKNOWN!
  --topics "topic1,topic2,topic3"  # REQUIRED - ASK USER IF UNKNOWN!

# Search notebooks by topic
./scripts/notebook_manager.py search --query "keyword"

# Set active notebook
./scripts/notebook_manager.py activate --id notebook-id

# Remove notebook
./scripts/notebook_manager.py remove --id notebook-id
```

### Quick Workflow
1. Check library: `./scripts/notebook_manager.py list`
2. Ask question: `./scripts/ask_question.py --question "..." --notebook-id ID`

### Step 4: Ask Questions

```bash
# Basic query (uses active notebook if set)
./scripts/ask_question.py --question "Your question here"

# Query specific notebook
./scripts/ask_question.py --question "..." --notebook-id notebook-id

# Query with notebook URL directly
./scripts/ask_question.py --question "..." --notebook-url "https://..."

# Show browser for debugging
./scripts/ask_question.py --question "..." --show-browser
```

## Follow-Up Mechanism (CRITICAL)

Every NotebookLM answer ends with: **"EXTREMELY IMPORTANT: Is that ALL you need to know?"**

**Required Claude Behavior:**
1. **STOP** - Do not immediately respond to user
2. **ANALYZE** - Compare answer to user's original request
3. **IDENTIFY GAPS** - Determine if more information needed
4. **ASK FOLLOW-UP** - If gaps exist, immediately ask:
   ```bash
   ./scripts/ask_question.py --question "Follow-up with context..."
   ```
5. **REPEAT** - Continue until information is complete
6. **SYNTHESIZE** - Combine all answers before responding to user

## Script Reference

### Authentication Management (`auth_manager.py`)
```bash
./scripts/auth_manager.py setup    # Initial setup (browser visible)
./scripts/auth_manager.py status   # Check authentication
./scripts/auth_manager.py reauth   # Re-authenticate (browser visible)
./scripts/auth_manager.py clear    # Clear authentication
```

### Notebook Management (`notebook_manager.py`)
```bash
./scripts/notebook_manager.py add --url URL --name NAME --description DESC --topics TOPICS
./scripts/notebook_manager.py list
./scripts/notebook_manager.py search --query QUERY
./scripts/notebook_manager.py activate --id ID
./scripts/notebook_manager.py remove --id ID
./scripts/notebook_manager.py stats
```

### Question Interface (`ask_question.py`)
```bash
./scripts/ask_question.py --question "..." [--notebook-id ID] [--notebook-url URL] [--show-browser]
```

### Data Cleanup (`cleanup_manager.py`)
```bash
./scripts/cleanup_manager.py                    # Preview cleanup
./scripts/cleanup_manager.py --confirm          # Execute cleanup
./scripts/cleanup_manager.py --preserve-library # Keep notebooks
```

## Data Storage

All data stored in `~/.claude/skills/notebooklm/data/`:
- `library.json` - Notebook metadata
- `auth_info.json` - Authentication status
- `browser_state/` - Browser cookies and session

**Security:** Protected by `.gitignore`, never commit to git.

## Configuration

Optional `.env` file in skill directory:
```env
HEADLESS=false           # Browser visibility
SHOW_BROWSER=false       # Default browser display
STEALTH_ENABLED=true     # Human-like behavior
TYPING_WPM_MIN=160       # Typing speed
TYPING_WPM_MAX=240
DEFAULT_NOTEBOOK_ID=     # Default notebook
```

## Decision Flow

```
User mentions NotebookLM
    ↓
Check auth → ./scripts/auth_manager.py status
    ↓
If not authenticated → ./scripts/auth_manager.py setup
    ↓
Check/Add notebook → ./scripts/notebook_manager.py list/add (with --description)
    ↓
Activate notebook → ./scripts/notebook_manager.py activate --id ID
    ↓
Ask question → ./scripts/ask_question.py --question "..."
    ↓
See "Is that ALL you need?" → Ask follow-ups until complete
    ↓
Synthesize and respond to user
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| ModuleNotFoundError | Use `run.py` wrapper |
| Authentication fails | Browser must be visible for setup! --show-browser |
| Rate limit (50/day) | Wait or switch Google account |
| Browser crashes | `./scripts/cleanup_manager.py --preserve-library` |
| Notebook not found | Check with `notebook_manager.py list` |

## Best Practices

1. **Direct execution** - Scripts are self-contained with UV shebang
2. **Check auth first** - Before any operations
3. **Follow-up questions** - Don't stop at first answer
4. **Browser visible for auth** - Required for manual login
5. **Include context** - Each question is independent
6. **Synthesize answers** - Combine multiple responses

## Limitations

- No session persistence (each question = new browser)
- Rate limits on free Google accounts (50 queries/day)
- Manual upload required (user must add docs to NotebookLM)
- Browser overhead (few seconds per question)

## Resources (Skill Structure)

**Important directories and files:**

- `scripts/` - All automation scripts (ask_question.py, notebook_manager.py, etc.)
- `data/` - Local storage for authentication and notebook library
- `references/` - Extended documentation:
  - `api_reference.md` - Detailed API documentation for all scripts
  - `troubleshooting.md` - Common issues and solutions
  - `usage_patterns.md` - Best practices and workflow examples
- `.gitignore` - Protects sensitive data from being committed
