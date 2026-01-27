---
name: notebooklm
description: Use this skill to query your Google NotebookLM notebooks directly from Claude Code for source-grounded, citation-backed answers from Gemini. Browser automation, library management, persistent auth. Drastically reduced hallucinations through document-only responses.
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
python3 scripts/run.py ask_question.py --question "What is the content of this notebook? What topics are covered? Provide a complete overview briefly and concisely" --notebook-url "[URL]"

# Step 2: Use the discovered information to add it
python3 scripts/run.py notebook_manager.py add --url "[URL]" --name "[Based on content]" --description "[Based on content]" --topics "[Based on content]"
```

**MANUAL ADD**: If user provides all details:
- `--url` - The NotebookLM URL
- `--name` - A descriptive name
- `--description` - What the notebook contains (REQUIRED!)
- `--topics` - Comma-separated topics (REQUIRED!)

NEVER guess or use generic descriptions! If details missing, use Smart Add to discover them.

## Critical: Always Use run.py Wrapper

**NEVER call scripts directly. ALWAYS use `python3 scripts/run.py [script]`:**

> **Note:** Use `python3` if available, otherwise use `python`. Check with `which python3 || which python`.

```bash
# ✅ CORRECT - Always use run.py:
python3 scripts/run.py auth_manager.py status
python3 scripts/run.py notebook_manager.py list
python3 scripts/run.py ask_question.py --question "..."

# ❌ WRONG - Never call directly:
python scripts/auth_manager.py status  # Fails without venv!
```

The `run.py` wrapper automatically:
1. Creates `.venv` if needed
2. Installs all dependencies
3. Activates environment
4. Executes script properly

## Core Workflow

### Step 1: Check Authentication Status
```bash
python3 scripts/run.py auth_manager.py status
```

If not authenticated, proceed to setup.

### Step 2: Authenticate (One-Time Setup)
```bash
# Browser MUST be visible for manual Google login
python3 scripts/run.py auth_manager.py setup
```

**Important:**
- Browser is VISIBLE for authentication
- Browser window opens automatically
- User must manually log in to Google
- Tell user: "A browser window will open for Google login"

### Step 3: Manage Notebook Library

```bash
# List all notebooks
python3 scripts/run.py notebook_manager.py list

# BEFORE ADDING: Ask user for metadata if unknown!
# "What does this notebook contain?"
# "What topics should I tag it with?"

# Add notebook to library (ALL parameters are REQUIRED!)
python3 scripts/run.py notebook_manager.py add \
  --url "https://notebooklm.google.com/notebook/..." \
  --name "Descriptive Name" \
  --description "What this notebook contains" \  # REQUIRED - ASK USER IF UNKNOWN!
  --topics "topic1,topic2,topic3"  # REQUIRED - ASK USER IF UNKNOWN!

# Search notebooks by topic
python3 scripts/run.py notebook_manager.py search --query "keyword"

# Set active notebook
python3 scripts/run.py notebook_manager.py activate --id notebook-id

# Remove notebook
python3 scripts/run.py notebook_manager.py remove --id notebook-id
```

### Quick Workflow
1. Check library: `python3 scripts/run.py notebook_manager.py list`
2. Ask question: `python3 scripts/run.py ask_question.py --question "..." --notebook-id ID`

### Step 4: Ask Questions

```bash
# Basic query (uses active notebook if set)
python3 scripts/run.py ask_question.py --question "Your question here"

# Query specific notebook
python3 scripts/run.py ask_question.py --question "..." --notebook-id notebook-id

# Query with notebook URL directly
python3 scripts/run.py ask_question.py --question "..." --notebook-url "https://..."

# Show browser for debugging
python3 scripts/run.py ask_question.py --question "..." --show-browser
```

### Step 5: Add Sources to Notebooks

Add new sources directly to your NotebookLM notebooks:

```bash
# Upload a file (PDF, txt, md, docx, etc.) - uses native file upload
python3 scripts/run.py add_source.py --file /path/to/document.pdf

# Add a website URL
python3 scripts/run.py add_source.py --url "https://example.com/article"

# Add a YouTube video (transcript will be imported)
python3 scripts/run.py add_source.py --url "https://www.youtube.com/watch?v=VIDEO_ID"

# Add copied text directly
python3 scripts/run.py add_source.py --text "Your text content here"

# Add text from a file (reads file and pastes as copied text)
python3 scripts/run.py add_source.py --text-file /path/to/content.txt

# Specify notebook (uses active notebook if not specified)
python3 scripts/run.py add_source.py --notebook-id ID --file /path/to/file.pdf

# Show browser for debugging
python3 scripts/run.py add_source.py --file /path/to/file.pdf --show-browser
```

**Supported File Types (via --file):**
NotebookLM natively supports: PDF, TXT, Markdown, Google Docs, Google Slides, and more.
Files are uploaded directly and processed by NotebookLM for best results.

**URL Sources (via --url):**
- Websites: Only visible text is imported; paid articles not supported
- YouTube: Only public videos with transcripts supported

**Text Sources (via --text or --text-file):**
- Direct text paste for content not in a file
- Use --text-file to read from a local text file

### Step 6: Generate Audio Overview

Generate podcast-style audio summaries of your notebook content with customizable prompts:

```bash
# Basic audio generation (uses default settings)
python3 scripts/run.py audio_generator.py --notebook-url "https://notebooklm.google.com/notebook/..."

# With custom prompt/instructions
python3 scripts/run.py audio_generator.py --notebook-url URL --instructions "Focus on the main arguments and explain like I'm a beginner"

# Choose format and length
python3 scripts/run.py audio_generator.py --notebook-id ID --format brief --length short

# Choose a different language
python3 scripts/run.py audio_generator.py --notebook-id ID --language "Spanish"

# Full customization with output filename
python3 scripts/run.py audio_generator.py --notebook-id ID \
  --format deep_dive \
  --length long \
  --language "Japanese" \
  --instructions "Discuss the technical implementation details" \
  --output "my_podcast.wav"

# Show browser for debugging
python3 scripts/run.py audio_generator.py --notebook-url URL --show-browser
```

**Audio Format Options:**
| Format | Description |
|--------|-------------|
| `deep_dive` | A lively conversation between two hosts, unpacking and connecting topics (default) |
| `brief` | A bite-sized overview to grasp core ideas quickly |
| `critique` | An expert review with constructive feedback |
| `debate` | A thoughtful debate illuminating different perspectives |

**Audio Length Options:**
- `short` - Quick summary
- `default` - Standard length
- `long` - Extended discussion

**Language (--language):**
Specify a language for the audio output (e.g., "English", "Spanish", "Japanese", "French", "German", etc.). Defaults to English if not specified.

**Custom Instructions (--instructions):**
Guide what the AI hosts focus on:
- Focus on a specific source: "only cover the article about Italy"
- Focus on a specific topic: "just discuss the novel's main character"
- Target an audience: "explain to someone new to biology"
- Request a style: "make it conversational and fun"

**Note:** Audio generation can take 5-10 minutes. The script will show progress updates while waiting.

### Step 9: Generate Video Overview

Generate video summaries of your notebook content with customizable format, visual style, and instructions:

```bash
# Basic video generation (uses default settings)
python3 scripts/run.py video_generator.py --notebook-url "https://notebooklm.google.com/notebook/..."

# With custom prompt/instructions
python3 scripts/run.py video_generator.py --notebook-url URL --instructions "Focus on the key concepts and explain visually"

# Choose format and visual style
python3 scripts/run.py video_generator.py --notebook-id ID --format brief --style whiteboard

# Choose a different language
python3 scripts/run.py video_generator.py --notebook-id ID --language "French"

# Full customization with output filename
python3 scripts/run.py video_generator.py --notebook-id ID \
  --format explainer \
  --style kawaii \
  --language "Japanese" \
  --instructions "Present this to a book club" \
  --output "my_video.mp4"

# Show browser for debugging
python3 scripts/run.py video_generator.py --notebook-url URL --show-browser
```

**Video Format Options:**
| Format | Description |
|--------|-------------|
| `explainer` | A structured, comprehensive overview that connects the dots within your sources (default) |
| `brief` | A bite-sized overview to help you quickly grasp core ideas |

**Visual Style Options:**
| Style | Description |
|-------|-------------|
| `auto` | Auto-select the best style for your content (default) |
| `custom` | Custom visual style |
| `classic` | Classic presentation style |
| `whiteboard` | Whiteboard-style animations |
| `kawaii` | Cute, friendly visual style |
| `anime` | Anime-inspired visuals |

**Language (--language):**
Specify a language for the video output (e.g., "English", "Spanish", "Japanese", "French", "German", etc.). Defaults to English if not specified.

**Custom Instructions (--instructions):**
Guide what the AI hosts focus on:
- Target a specific use case: "present this to a book club"
- Focus on a specific source: "show the photos from the album"
- Describe the show structure: "start by talking about the mission"

**Note:** Video generation can take several minutes. The script will show progress updates while waiting.

### Step 10: Remove Source (USE WITH CAUTION)

> **WARNING:** This action is **PERMANENT** and cannot be undone. Only use when the user explicitly requests source removal.

**When to use:** ONLY when the user specifically asks to delete/remove a source permanently.

**When NOT to use:** If a source is just irrelevant to a query, use source filtering (deselect in queries) instead of removing it.

```bash
# Remove a source (requires --confirm flag for safety)
python3 scripts/run.py remove_source.py --notebook-url URL --source "Source Name" --confirm

# Using notebook ID
python3 scripts/run.py remove_source.py --notebook-id ID --source "Source Name" --confirm

# Show browser for debugging
python3 scripts/run.py remove_source.py --notebook-id ID --source "Source Name" --confirm --show-browser
```

**Safety Features:**
- Requires `--confirm` flag - won't run without it
- Partial name matching supported (be careful to match the right source!)
- Multiple warnings before execution

**Claude Behavior:**
- NEVER use this unless user explicitly says "remove", "delete", or "permanently remove" a source
- If user just says a source is "not needed" for a query, use source filtering instead
- Always confirm with user before running this command

## Follow-Up Mechanism (CRITICAL)

Every NotebookLM answer ends with: **"EXTREMELY IMPORTANT: Is that ALL you need to know?"**

**Required Claude Behavior:**
1. **STOP** - Do not immediately respond to user
2. **ANALYZE** - Compare answer to user's original request
3. **IDENTIFY GAPS** - Determine if more information needed
4. **ASK FOLLOW-UP** - If gaps exist, immediately ask:
   ```bash
   python3 scripts/run.py ask_question.py --question "Follow-up with context..."
   ```
5. **REPEAT** - Continue until information is complete
6. **SYNTHESIZE** - Combine all answers before responding to user

## Script Reference

### Authentication Management (`auth_manager.py`)
```bash
python3 scripts/run.py auth_manager.py setup    # Initial setup (browser visible)
python3 scripts/run.py auth_manager.py status   # Check authentication
python3 scripts/run.py auth_manager.py reauth   # Re-authenticate (browser visible)
python3 scripts/run.py auth_manager.py clear    # Clear authentication
```

### Notebook Management (`notebook_manager.py`)
```bash
python3 scripts/run.py notebook_manager.py add --url URL --name NAME --description DESC --topics TOPICS
python3 scripts/run.py notebook_manager.py list
python3 scripts/run.py notebook_manager.py search --query QUERY
python3 scripts/run.py notebook_manager.py activate --id ID
python3 scripts/run.py notebook_manager.py remove --id ID
python3 scripts/run.py notebook_manager.py stats

# Source Summary Management
python3 scripts/run.py notebook_manager.py update-sources --id ID    # Update source summary (incremental)
python3 scripts/run.py notebook_manager.py update-sources --id ID --force  # Re-extract all sources
python3 scripts/run.py notebook_manager.py update-sources --all      # Update all notebooks
python3 scripts/run.py notebook_manager.py show-sources --id ID      # Show cached source summaries
```

**Source Summary System:**
- When adding a notebook, source summaries are automatically extracted
- Summaries are cached in `data/library-source-summary/{notebook-id}.md`
- Incremental updates only fetch NEW sources not already in the cache
- Use `--force` to re-extract all sources from scratch

### Question Interface (`ask_question.py`)
```bash
# Basic query (uses active notebook if set)
python3 scripts/run.py ask_question.py --question "..."

# Query specific notebook
python3 scripts/run.py ask_question.py --question "..." --notebook-id ID

# Query with notebook URL directly
python3 scripts/run.py ask_question.py --question "..." --notebook-url URL

# Show browser for debugging
python3 scripts/run.py ask_question.py --question "..." --show-browser

# Source filtering options (default: LLM scoring enabled)
python3 scripts/run.py ask_question.py --question "..." --keyword-filter  # Use keyword matching instead of LLM
python3 scripts/run.py ask_question.py --question "..." --threshold 7     # Higher threshold = fewer sources (1-10)
python3 scripts/run.py ask_question.py --question "..." --no-filter       # Disable source filtering entirely
```

### Source Addition (`add_source.py`)
```bash
# Upload file (native upload - best for PDFs)
python3 scripts/run.py add_source.py --file /path/to/file.pdf

# Add URL (website or YouTube)
python3 scripts/run.py add_source.py --url URL

# Add copied text
python3 scripts/run.py add_source.py --text "Content"
python3 scripts/run.py add_source.py --text-file /path/to/text.txt

# Options
--notebook-url URL    # Target notebook URL
--notebook-id ID      # Target notebook ID from library
--show-browser        # Show browser for debugging
```

### Source Listing (`list_sources.py`)
```bash
# List sources in active notebook (reads UI directly - more reliable than asking)
python3 scripts/run.py list_sources.py

# List sources in specific notebook
python3 scripts/run.py list_sources.py --notebook-id ID
python3 scripts/run.py list_sources.py --notebook-url URL

# Output as JSON
python3 scripts/run.py list_sources.py --json

# Show browser for debugging
python3 scripts/run.py list_sources.py --show-browser
```
**Note:** This reads source names directly from the UI, which is more reliable than asking NotebookLM to list sources via a question. Use this to verify sources before/after removal.

**Source Filtering Behavior:**
Before each query, the skill automatically:
1. Loads cached source summaries from `data/library-source-summary/{notebook-id}.md`
2. Uses LLM (Gemini → Claude → keywords fallback) to score each source's relevance (1-10)
3. Deselects sources below threshold in the browser
4. Queries only relevant sources for faster, focused responses

### Audio Generation (`audio_generator.py`)
```bash
# Generate with defaults
python3 scripts/run.py audio_generator.py --notebook-url URL

# With custom prompt
python3 scripts/run.py audio_generator.py --notebook-id ID --instructions "Your prompt here"

# Full options
python3 scripts/run.py audio_generator.py --notebook-url URL \
  --format deep_dive|brief|critique|debate \
  --length short|default|long \
  --language "English|Spanish|Japanese|..." \
  --instructions "Custom prompt" \
  --output filename.wav \
  --show-browser
```

### Video Generation (`video_generator.py`)
```bash
# Generate with defaults
python3 scripts/run.py video_generator.py --notebook-url URL

# With custom prompt and style
python3 scripts/run.py video_generator.py --notebook-id ID --instructions "Your prompt here" --style whiteboard

# Full options
python3 scripts/run.py video_generator.py --notebook-url URL \
  --format explainer|brief \
  --style auto|custom|classic|whiteboard|kawaii|anime \
  --language "English|Spanish|Japanese|..." \
  --instructions "Custom prompt" \
  --output filename.mp4 \
  --show-browser
```

### Source Removal (`remove_source.py`) - PERMANENT ACTION
```bash
# Remove a source (--confirm REQUIRED)
python3 scripts/run.py remove_source.py --notebook-url URL --source "Source Name" --confirm
python3 scripts/run.py remove_source.py --notebook-id ID --source "Source Name" --confirm --show-browser
```
**WARNING:** Only use when user explicitly requests permanent removal. Use source filtering for temporary exclusion.

### Data Cleanup (`cleanup_manager.py`)
```bash
python3 scripts/run.py cleanup_manager.py                    # Preview cleanup
python3 scripts/run.py cleanup_manager.py --confirm          # Execute cleanup
python3 scripts/run.py cleanup_manager.py --preserve-library # Keep notebooks
```

## Environment Management

The virtual environment is automatically managed:
- First run creates `.venv` automatically
- Dependencies install automatically
- Chromium browser installs automatically
- Everything isolated in skill directory

Manual setup (only if automatic fails):
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
python -m patchright install chromium
```

## Data Storage

All data stored in `data/` directory within the skill folder:
- `library.json` - Notebook metadata
- `auth_info.json` - Authentication status
- `browser_state/` - Browser cookies and session
- `library-source-summary/` - Source summaries for each notebook (auto-generated)
  - `{notebook-id}.md` - Markdown file with table of sources and summaries

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

## Intelligent Source Filtering

Before each query, the skill automatically filters sources:

```
Question received
    ↓
Load source summaries from cache
    ↓
LLM scores each source (1-10 relevance)
    ↓
Deselect sources below threshold
    ↓
Query only relevant sources
    ↓
Faster, more focused response
```

**LLM Fallback Chain:**
1. **Gemini CLI** (default) - Fast, semantic understanding
2. **Claude CLI** - Fallback if Gemini not installed
3. **Keywords** - Final fallback if no LLM available

**Threshold Guide:**
- `--threshold 3`: Include most sources (broad search)
- `--threshold 5`: Default, balanced filtering
- `--threshold 7`: Only highly relevant sources (focused search)
- `--threshold 9`: Only direct matches

## Decision Flow

```
User mentions NotebookLM
    ↓
Check auth → python3 scripts/run.py auth_manager.py status
    ↓
If not authenticated → python3 scripts/run.py auth_manager.py setup
    ↓
Check/Add notebook → python3 scripts/run.py notebook_manager.py list/add (with --description)
    ↓
Source summaries auto-extracted and cached
    ↓
Activate notebook → python3 scripts/run.py notebook_manager.py activate --id ID
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Choose action based on user request:                        │
├─────────────────────────────────────────────────────────────┤
│ Ask question → python3 scripts/run.py ask_question.py ...   │
│ Generate audio → python3 scripts/run.py audio_generator.py  │
│ Generate video → python3 scripts/run.py video_generator.py  │
└─────────────────────────────────────────────────────────────┘
    ↓
(For questions) See "Is that ALL you need?" → Ask follow-ups until complete
    ↓
(For audio/video) Wait for generation → Download media file
    ↓
Synthesize and respond to user
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| ModuleNotFoundError | Use `run.py` wrapper |
| Authentication fails | Browser must be visible for setup! --show-browser |
| Rate limit (50/day) | Wait or switch Google account |
| Browser crashes | `python3 scripts/run.py cleanup_manager.py --preserve-library` |
| Notebook not found | Check with `notebook_manager.py list` |
| Source not relevant | Use `--no-filter` or adjust `--threshold` - DON'T remove it |
| Need to delete source | Only use `remove_source.py` if user explicitly requests permanent deletion |

## Best Practices

1. **Always use run.py** - Handles environment automatically
2. **Check auth first** - Before any operations
3. **Follow-up questions** - Don't stop at first answer
4. **Browser visible for auth** - Required for manual login
5. **Include context** - Each question is independent
6. **Synthesize answers** - Combine multiple responses
7. **Filter, don't delete** - Use source filtering for irrelevant sources; only use `remove_source.py` when user explicitly asks for permanent deletion

## Limitations

- No session persistence (each question = new browser)
- Rate limits on free Google accounts (50 queries/day)
- Manual upload required (user must add docs to NotebookLM)
- Browser overhead (few seconds per question)
- Audio/Video generation takes several minutes (NotebookLM limitation)

## Resources (Skill Structure)

**Important directories and files:**

- `scripts/` - All automation scripts (ask_question.py, notebook_manager.py, etc.)
- `data/` - Local storage for authentication and notebook library
- `references/` - Extended documentation:
  - `api_reference.md` - Detailed API documentation for all scripts
  - `troubleshooting.md` - Common issues and solutions
  - `usage_patterns.md` - Best practices and workflow examples
- `.venv/` - Isolated Python environment (auto-created on first run)
- `.gitignore` - Protects sensitive data from being committed
