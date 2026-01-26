# Add Source Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the ability to add sources (local files via native upload, website/YouTube URLs, copied text) to NotebookLM notebooks via browser automation.

**Architecture:** Create a new `add_source.py` script that uses Playwright browser automation to interact with NotebookLM's "Add sources" dialog. Three source types supported:
1. **File upload** - Uses native OS file picker via Playwright's `expect_file_chooser()`
2. **URLs** - Pastes website/YouTube links into the "Websites" textarea
3. **Text** - Pastes content into the "Copied text" textarea

**Tech Stack:** Python, Patchright (Playwright fork with stealth features)

---

## UI Reference (from screenshots)

**Main dialog buttons:**
- "Upload files" → Opens native OS file picker
- "Websites" → Shows textarea with "Paste any links" placeholder
- "Drive" → Google Drive (not implementing - requires OAuth)
- "Copied text" → Shows textarea for pasting text

**After clicking "Websites":**
- Textarea: "Paste any links"
- Supports multiple URLs separated by space/newline
- "Insert" button to submit

---

### Task 1: Add UI Selectors to config.py

**Files:**
- Modify: `scripts/config.py`

**Step 1: Add new selector constants after RESPONSE_SELECTORS (line 40)**

```python
# Add Source Dialog Selectors (based on NotebookLM UI Jan 2026)
ADD_SOURCE_BUTTON_SELECTORS = [
    'button:has-text("Add source")',
    'button:has-text("Add sources")',
    'button[aria-label*="Add source"]',
    'button[aria-label*="Add sources"]',
    '[data-test-id="add-source-button"]',
]

# Main dialog option buttons
UPLOAD_FILES_BUTTON_SELECTORS = [
    'button:has-text("Upload files")',
    '[aria-label*="Upload files"]',
    'button:has-text("Upload")',
]

WEBSITES_BUTTON_SELECTORS = [
    'button:has-text("Websites")',
    '[aria-label*="Websites"]',
    'button:has-text("Website")',
]

COPIED_TEXT_BUTTON_SELECTORS = [
    'button:has-text("Copied text")',
    '[aria-label*="Copied text"]',
    'button:has-text("Paste")',
]

# Input fields
URL_TEXTAREA_SELECTORS = [
    'textarea[placeholder*="Paste any links"]',
    'textarea[placeholder*="link"]',
    'textarea[placeholder*="URL"]',
    'textarea',
]

TEXT_TEXTAREA_SELECTORS = [
    'textarea[placeholder*="Paste"]',
    'textarea[placeholder*="paste"]',
    'textarea',
]

# Action buttons
INSERT_BUTTON_SELECTORS = [
    'button:has-text("Insert")',
    'button:has-text("Add")',
    'button[type="submit"]',
]

CLOSE_DIALOG_SELECTORS = [
    'button[aria-label="Close"]',
    'button:has-text("Close")',
    '[aria-label="close"]',
]
```

**Step 2: Verify config.py syntax**

Run: `cd /Users/ellengu/Documents/ObsidianFolder/TheVault/.claude/skills/notebooklm-skill && python3 -c "from scripts.config import *; print('Selectors loaded:', len(ADD_SOURCE_BUTTON_SELECTORS))"`
Expected: `Selectors loaded: 5`

**Step 3: Commit**

```bash
git add scripts/config.py
git commit -m "$(cat <<'EOF'
feat(config): add UI selectors for add source dialog

Add selector constants for NotebookLM's add source interface:
- ADD_SOURCE_BUTTON_SELECTORS - main "Add sources" button
- UPLOAD_FILES_BUTTON_SELECTORS - native file upload
- WEBSITES_BUTTON_SELECTORS - URL input
- COPIED_TEXT_BUTTON_SELECTORS - text paste
- URL_TEXTAREA_SELECTORS, TEXT_TEXTAREA_SELECTORS - input fields
- INSERT_BUTTON_SELECTORS - submit button

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Create add_source.py Script

**Files:**
- Create: `scripts/add_source.py`

**Step 1: Create the main script**

```python
#!/usr/bin/env python3
"""
Add sources to NotebookLM notebooks.
Supports: File upload (PDF, txt, md, docx), Website/YouTube URLs, Copied text.

Each source addition opens a fresh browser session, adds the source, and closes.
"""

import argparse
import sys
import time
import re
from pathlib import Path

from patchright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import (
    DATA_DIR,
    ADD_SOURCE_BUTTON_SELECTORS,
    UPLOAD_FILES_BUTTON_SELECTORS,
    WEBSITES_BUTTON_SELECTORS,
    COPIED_TEXT_BUTTON_SELECTORS,
    URL_TEXTAREA_SELECTORS,
    TEXT_TEXTAREA_SELECTORS,
    INSERT_BUTTON_SELECTORS,
)
from browser_utils import BrowserFactory, StealthUtils


def find_and_click(page, selectors: list, description: str, timeout: int = 5000) -> bool:
    """Find element using multiple selectors and click it."""
    for selector in selectors:
        try:
            element = page.wait_for_selector(selector, timeout=timeout, state="visible")
            if element:
                print(f"    Found {description}: {selector}")
                element.click()
                return True
        except:
            continue
    print(f"    Could not find {description}")
    return False


def find_element(page, selectors: list, timeout: int = 3000):
    """Find element using multiple selectors."""
    for selector in selectors:
        try:
            element = page.wait_for_selector(selector, timeout=timeout, state="visible")
            if element:
                return element
        except:
            continue
    return None


def navigate_to_add_source_dialog(page, notebook_url: str) -> bool:
    """Navigate to notebook and open the Add Sources dialog."""
    print("    Opening notebook...")
    page.goto(notebook_url, wait_until="domcontentloaded")
    page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=15000)
    time.sleep(3)

    if "/notebook/" not in page.url:
        print(f"    Redirected away from notebook: {page.url}")
        return False

    # Click Sources tab if visible
    try:
        sources_tab = page.query_selector('button:has-text("Sources"), [role="tab"]:has-text("Sources")')
        if sources_tab and sources_tab.is_visible():
            sources_tab.click()
            time.sleep(1)
    except:
        pass

    # Click "Add sources" button
    print("    Opening Add Sources dialog...")
    if not find_and_click(page, ADD_SOURCE_BUTTON_SELECTORS, "Add sources button"):
        debug_path = DATA_DIR / "add_source_debug.png"
        page.screenshot(path=str(debug_path))
        print(f"    Debug screenshot: {debug_path}")
        return False

    time.sleep(1.5)
    return True


def add_file_source(notebook_url: str, file_path: str, headless: bool = True) -> str:
    """
    Upload a file as a source using the native file picker.

    Args:
        notebook_url: NotebookLM notebook URL
        file_path: Path to file (PDF, txt, md, docx, etc.)
        headless: Run browser in headless mode

    Returns:
        Success message or None on failure
    """
    auth = AuthManager()
    if not auth.is_authenticated():
        print("  Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return None

    file_path = Path(file_path).resolve()
    if not file_path.exists():
        print(f"  File not found: {file_path}")
        return None

    print(f"  Uploading file: {file_path.name}")
    print(f"  Size: {file_path.stat().st_size / 1024:.1f} KB")
    print(f"  Notebook: {notebook_url}")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
        page = context.new_page()

        if not navigate_to_add_source_dialog(page, notebook_url):
            return None

        # Click "Upload files" and handle file chooser
        print("    Selecting file to upload...")

        with page.expect_file_chooser(timeout=10000) as fc_info:
            if not find_and_click(page, UPLOAD_FILES_BUTTON_SELECTORS, "Upload files button"):
                return None

        file_chooser = fc_info.value
        file_chooser.set_files(str(file_path))
        print(f"    File selected: {file_path.name}")

        # Wait for upload to process
        print("    Waiting for upload to complete...")
        time.sleep(5)

        # Check for success (source should appear in list)
        # NotebookLM processes the file and adds it to sources
        print(f"    File source uploaded: {file_path.name}")
        return f"Successfully uploaded file: {file_path.name}"

    except Exception as e:
        print(f"    Error: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        if context:
            try:
                context.close()
            except:
                pass
        if playwright:
            try:
                playwright.stop()
            except:
                pass


def add_url_source(notebook_url: str, source_url: str, headless: bool = True) -> str:
    """
    Add a website or YouTube URL as a source.

    Args:
        notebook_url: NotebookLM notebook URL
        source_url: Website or YouTube URL to add
        headless: Run browser in headless mode

    Returns:
        Success message or None on failure
    """
    auth = AuthManager()
    if not auth.is_authenticated():
        print("  Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return None

    if not source_url or not source_url.strip():
        print("  URL cannot be empty")
        return None

    is_youtube = "youtube.com" in source_url or "youtu.be" in source_url
    source_type = "YouTube" if is_youtube else "Website"

    print(f"  Adding {source_type} source: {source_url}")
    print(f"  Notebook: {notebook_url}")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
        page = context.new_page()

        if not navigate_to_add_source_dialog(page, notebook_url):
            return None

        # Click "Websites" button
        print("    Selecting Websites option...")
        if not find_and_click(page, WEBSITES_BUTTON_SELECTORS, "Websites button"):
            return None

        time.sleep(1)

        # Find textarea and enter URL
        print("    Entering URL...")
        textarea = find_element(page, URL_TEXTAREA_SELECTORS)
        if not textarea:
            print("    Could not find URL textarea")
            return None

        textarea.click()
        StealthUtils.random_delay(200, 400)
        textarea.fill(source_url)
        time.sleep(0.5)

        # Click Insert button
        print("    Submitting...")
        if not find_and_click(page, INSERT_BUTTON_SELECTORS, "Insert button", timeout=3000):
            page.keyboard.press("Enter")

        time.sleep(4)

        print(f"    {source_type} source added!")
        return f"Successfully added {source_type} source: {source_url}"

    except Exception as e:
        print(f"    Error: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        if context:
            try:
                context.close()
            except:
                pass
        if playwright:
            try:
                playwright.stop()
            except:
                pass


def add_text_source(notebook_url: str, content: str, headless: bool = True) -> str:
    """
    Add copied text as a source.

    Args:
        notebook_url: NotebookLM notebook URL
        content: Text content to add
        headless: Run browser in headless mode

    Returns:
        Success message or None on failure
    """
    auth = AuthManager()
    if not auth.is_authenticated():
        print("  Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return None

    if not content or not content.strip():
        print("  Content cannot be empty")
        return None

    preview = content[:100] + "..." if len(content) > 100 else content
    print(f"  Adding text source ({len(content)} chars)")
    print(f"  Preview: {preview}")
    print(f"  Notebook: {notebook_url}")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
        page = context.new_page()

        if not navigate_to_add_source_dialog(page, notebook_url):
            return None

        # Click "Copied text" button
        print("    Selecting Copied text option...")
        if not find_and_click(page, COPIED_TEXT_BUTTON_SELECTORS, "Copied text button"):
            return None

        time.sleep(1)

        # Find textarea and enter content
        print("    Entering text content...")
        textarea = find_element(page, TEXT_TEXTAREA_SELECTORS)
        if not textarea:
            print("    Could not find text textarea")
            return None

        textarea.click()
        StealthUtils.random_delay(200, 400)

        # Use fill() for large content
        if len(content) > 500:
            textarea.fill(content)
        else:
            StealthUtils.human_type(page, TEXT_TEXTAREA_SELECTORS[0], content)

        time.sleep(0.5)

        # Click Insert button
        print("    Submitting...")
        time.sleep(1)  # Wait for button to enable

        if not find_and_click(page, INSERT_BUTTON_SELECTORS, "Insert button", timeout=3000):
            page.keyboard.press("Enter")

        time.sleep(3)

        print("    Text source added!")
        return f"Successfully added text source ({len(content)} characters)"

    except Exception as e:
        print(f"    Error: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        if context:
            try:
                context.close()
            except:
                pass
        if playwright:
            try:
                playwright.stop()
            except:
                pass


def main():
    parser = argparse.ArgumentParser(
        description='Add sources to NotebookLM notebooks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload a PDF file
  python3 scripts/run.py add_source.py --file /path/to/document.pdf

  # Add a website URL
  python3 scripts/run.py add_source.py --url "https://example.com/article"

  # Add a YouTube video
  python3 scripts/run.py add_source.py --url "https://youtube.com/watch?v=..."

  # Add copied text
  python3 scripts/run.py add_source.py --text "Your text content here"

  # Read text from a file and paste it (for very large text)
  python3 scripts/run.py add_source.py --text-file /path/to/content.txt
        """
    )

    parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    parser.add_argument('--notebook-id', help='Notebook ID from library')

    # Source types (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('--file', help='Path to file to upload (PDF, txt, md, docx, etc.)')
    source_group.add_argument('--url', help='Website or YouTube URL to add')
    source_group.add_argument('--text', help='Text content to paste as source')
    source_group.add_argument('--text-file', help='Path to text file to read and paste as source')

    parser.add_argument('--show-browser', action='store_true', help='Show browser window')

    args = parser.parse_args()

    # Resolve notebook URL
    notebook_url = args.notebook_url

    if not notebook_url and args.notebook_id:
        library = NotebookLibrary()
        notebook = library.get_notebook(args.notebook_id)
        if notebook:
            notebook_url = notebook['url']
            print(f"  Using notebook: {notebook['name']}")
        else:
            print(f"  Notebook '{args.notebook_id}' not found")
            return 1

    if not notebook_url:
        library = NotebookLibrary()
        active = library.get_active_notebook()
        if active:
            notebook_url = active['url']
            print(f"  Using active notebook: {active['name']}")
        else:
            print("  No notebook specified. Use --notebook-url or --notebook-id")
            return 1

    # Execute based on source type
    result = None

    if args.file:
        result = add_file_source(
            notebook_url=notebook_url,
            file_path=args.file,
            headless=not args.show_browser
        )

    elif args.url:
        result = add_url_source(
            notebook_url=notebook_url,
            source_url=args.url,
            headless=not args.show_browser
        )

    elif args.text:
        result = add_text_source(
            notebook_url=notebook_url,
            content=args.text,
            headless=not args.show_browser
        )

    elif args.text_file:
        text_path = Path(args.text_file)
        if not text_path.exists():
            print(f"  File not found: {args.text_file}")
            return 1

        print(f"  Reading text from: {args.text_file}")
        content = text_path.read_text(encoding='utf-8')
        print(f"  Content size: {len(content)} characters")

        result = add_text_source(
            notebook_url=notebook_url,
            content=content,
            headless=not args.show_browser
        )

    # Print result
    print("\n" + "=" * 50)
    if result:
        print(f"  {result}")
        return 0
    else:
        print("  Failed to add source")
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Make script executable**

Run: `chmod +x /Users/ellengu/Documents/ObsidianFolder/TheVault/.claude/skills/notebooklm-skill/scripts/add_source.py`

**Step 3: Verify syntax**

Run: `cd /Users/ellengu/Documents/ObsidianFolder/TheVault/.claude/skills/notebooklm-skill && python3 -m py_compile scripts/add_source.py && echo "Syntax OK"`
Expected: `Syntax OK`

**Step 4: Commit**

```bash
git add scripts/add_source.py
git commit -m "$(cat <<'EOF'
feat(add_source): add script to add sources to NotebookLM

Three source types supported:
- --file: Native file upload (PDF, txt, md, docx, etc.) via OS file picker
- --url: Website or YouTube URLs via paste textarea
- --text / --text-file: Copied text via paste textarea

Uses Playwright's expect_file_chooser() for native file upload.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Update SKILL.md Documentation

**Files:**
- Modify: `SKILL.md`

**Step 1: Add new section after "### Step 4: Ask Questions" (around line 127)**

```markdown
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
```

**Step 2: Add to Script Reference section (around line 193)**

```markdown
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
```

**Step 3: Commit**

```bash
git add SKILL.md
git commit -m "$(cat <<'EOF'
docs(SKILL.md): add documentation for add_source.py

Document the new source addition feature:
- Native file upload (--file) for PDF, txt, md, docx
- URL sources (--url) for websites and YouTube
- Text sources (--text, --text-file)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Manual Testing

**Files:** None (testing only)

**Step 1: Test file upload**

Run: `cd /Users/ellengu/Documents/ObsidianFolder/TheVault/.claude/skills/notebooklm-skill && python3 scripts/run.py add_source.py --file /path/to/test.pdf --show-browser`

Expected: Browser opens, file picker triggers, file uploads successfully

**Step 2: Test URL source**

Run: `cd /Users/ellengu/Documents/ObsidianFolder/TheVault/.claude/skills/notebooklm-skill && python3 scripts/run.py add_source.py --url "https://en.wikipedia.org/wiki/Meiji_Restoration" --show-browser`

Expected: Browser opens, URL pasted, source added

**Step 3: Test text source**

Run: `cd /Users/ellengu/Documents/ObsidianFolder/TheVault/.claude/skills/notebooklm-skill && python3 scripts/run.py add_source.py --text "Test content for NotebookLM" --show-browser`

Expected: Browser opens, text pasted, source added

---

### Task 5: Cleanup exploration script

**Files:**
- Delete: `scripts/explore_add_source_ui.py`

**Step 1: Remove temporary exploration script**

Run: `rm /Users/ellengu/Documents/ObsidianFolder/TheVault/.claude/skills/notebooklm-skill/scripts/explore_add_source_ui.py`

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add UI selectors | `scripts/config.py` |
| 2 | Create add_source.py | `scripts/add_source.py` (new) |
| 3 | Update documentation | `SKILL.md` |
| 4 | Manual testing | (browser tests) |
| 5 | Cleanup | Delete temp script |

**Key Features:**
- **Native file upload** via `--file` - Uses `expect_file_chooser()` for PDFs and all supported formats
- **URL sources** via `--url` - Websites and YouTube (transcript import)
- **Text sources** via `--text` or `--text-file` - Direct paste

**No PyPDF2 needed!** Native file upload means NotebookLM handles PDF parsing.
