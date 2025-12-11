#!/usr/bin/env python3
"""
Add sources to NotebookLM notebooks
Supports: Paste text, Website URLs, YouTube URLs

Each source addition opens a fresh browser session, adds the source, and closes.
"""

import argparse
import sys
import time
import re
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import (
    DATA_DIR,
    ADD_SOURCE_BUTTON_SELECTORS,
    PASTE_TEXT_CHIP_SELECTORS,
    PASTE_TEXT_TEXTAREA_SELECTORS,
    INSERT_BUTTON_SELECTORS,
    URL_CHIP_SELECTORS,
    URL_INPUT_SELECTORS,
)
from browser_utils import BrowserFactory, StealthUtils


def add_text_source(notebook_url: str, content: str, headless: bool = True) -> str:
    """
    Add pasted text as a source to a NotebookLM notebook.

    Args:
        notebook_url: NotebookLM notebook URL
        content: Text content to add as source
        headless: Run browser in headless mode

    Returns:
        Success message or None on failure
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("⚠️ Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return None

    if not content or not content.strip():
        print("❌ Content cannot be empty")
        return None

    # Truncate content preview for logging
    content_preview = content[:100] + "..." if len(content) > 100 else content
    print(f"📝 Adding text source ({len(content)} chars)")
    print(f"  Preview: {content_preview}")
    print(f"📚 Notebook: {notebook_url}")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
        page = context.new_page()

        # Navigate to notebook
        print("  🌐 Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded")
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=10000)
        time.sleep(3)  # Let UI render

        # Check if we're on the notebook page
        if "/notebook/" not in page.url:
            print(f"  ❌ Redirected away from notebook: {page.url}")
            return None

        # Click Sources tab if visible
        try:
            sources_tab = page.query_selector('button:has-text("Sources"), [role="tab"]:has-text("Sources")')
            if sources_tab and sources_tab.is_visible():
                sources_tab.click()
                time.sleep(1)
        except:
            pass

        # Find and click "Add sources" button
        print("  ⏳ Looking for Add sources button...")
        add_btn = None
        for selector in ADD_SOURCE_BUTTON_SELECTORS:
            try:
                add_btn = page.wait_for_selector(selector, timeout=5000, state="visible")
                if add_btn:
                    print(f"  ✓ Found: {selector}")
                    break
            except:
                continue

        if not add_btn:
            # Take debug screenshot
            debug_path = DATA_DIR / "add_source_debug.png"
            page.screenshot(path=str(debug_path))
            print(f"  ❌ Could not find Add sources button")
            print(f"  📸 Debug screenshot: {debug_path}")
            return None

        add_btn.click()
        time.sleep(1.5)

        # Click "Copied text" chip
        print("  ⏳ Selecting 'Copied text' option...")
        chip = None
        for selector in PASTE_TEXT_CHIP_SELECTORS:
            try:
                chip = page.wait_for_selector(selector, timeout=3000, state="visible")
                if chip:
                    print(f"  ✓ Found: {selector}")
                    break
            except:
                continue

        if not chip:
            print("  ❌ Could not find 'Copied text' option")
            return None

        chip.click()
        time.sleep(1)

        # Find textarea and enter content
        print("  ⏳ Entering text content...")
        textarea = None
        for selector in PASTE_TEXT_TEXTAREA_SELECTORS:
            try:
                textarea = page.wait_for_selector(selector, timeout=3000, state="visible")
                if textarea:
                    print(f"  ✓ Found: {selector}")
                    break
            except:
                continue

        if not textarea:
            print("  ❌ Could not find text input")
            return None

        textarea.click()
        StealthUtils.random_delay(200, 400)

        # Use fill() for large content, human_type for small
        if len(content) > 500:
            textarea.fill(content)
        else:
            StealthUtils.human_type(page, PASTE_TEXT_TEXTAREA_SELECTORS[0], content)

        time.sleep(0.5)

        # Click Insert button
        print("  ⏳ Clicking Insert...")
        time.sleep(1)  # Wait for button to enable

        insert_btn = None
        for selector in INSERT_BUTTON_SELECTORS:
            try:
                insert_btn = page.wait_for_selector(selector, timeout=3000, state="visible")
                if insert_btn:
                    print(f"  ✓ Found: {selector}")
                    break
            except:
                continue

        if not insert_btn:
            print("  ❌ Could not find Insert button")
            return None

        insert_btn.click()
        time.sleep(3)  # Wait for source to be added

        # Check for errors
        try:
            error = page.query_selector('[class*="error"]')
            if error and error.is_visible():
                print(f"  ❌ Error: {error.inner_text().strip()}")
                return None
        except:
            pass

        print("  ✅ Text source added!")
        return f"Successfully added text source ({len(content)} characters)"

    except Exception as e:
        print(f"  ❌ Error: {e}")
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
    Add a website or YouTube URL as a source to a NotebookLM notebook.

    Args:
        notebook_url: NotebookLM notebook URL
        source_url: Website or YouTube URL to add
        headless: Run browser in headless mode

    Returns:
        Success message or None on failure
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("⚠️ Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return None

    if not source_url or not source_url.strip():
        print("❌ URL cannot be empty")
        return None

    # Determine source type
    is_youtube = "youtube.com" in source_url or "youtu.be" in source_url
    source_type = "YouTube" if is_youtube else "Website"

    print(f"🔗 Adding {source_type} source")
    print(f"  URL: {source_url}")
    print(f"📚 Notebook: {notebook_url}")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
        page = context.new_page()

        # Navigate to notebook
        print("  🌐 Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded")
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=10000)
        time.sleep(3)

        # Click Sources tab if visible
        try:
            sources_tab = page.query_selector('button:has-text("Sources"), [role="tab"]:has-text("Sources")')
            if sources_tab and sources_tab.is_visible():
                sources_tab.click()
                time.sleep(1)
        except:
            pass

        # Find and click "Add sources" button
        print("  ⏳ Looking for Add sources button...")
        add_btn = None
        for selector in ADD_SOURCE_BUTTON_SELECTORS:
            try:
                add_btn = page.wait_for_selector(selector, timeout=5000, state="visible")
                if add_btn:
                    break
            except:
                continue

        if not add_btn:
            print("  ❌ Could not find Add sources button")
            return None

        add_btn.click()
        time.sleep(1.5)

        # Click Website or YouTube chip
        print(f"  ⏳ Selecting '{source_type}' option...")
        chip = None
        chip_selector = f'mat-chip:has-text("{source_type}")'
        for selector in [chip_selector] + URL_CHIP_SELECTORS:
            try:
                chip = page.wait_for_selector(selector, timeout=3000, state="visible")
                if chip:
                    break
            except:
                continue

        if not chip:
            print(f"  ❌ Could not find '{source_type}' option")
            return None

        chip.click()
        time.sleep(1)

        # Find URL input and enter URL
        print("  ⏳ Entering URL...")
        url_input = None
        for selector in URL_INPUT_SELECTORS:
            try:
                url_input = page.wait_for_selector(selector, timeout=3000, state="visible")
                if url_input:
                    break
            except:
                continue

        if not url_input:
            print("  ❌ Could not find URL input")
            return None

        url_input.click()
        StealthUtils.random_delay(200, 400)
        url_input.fill(source_url)
        time.sleep(0.5)

        # Click Insert button
        print("  ⏳ Submitting...")
        insert_btn = None
        for selector in INSERT_BUTTON_SELECTORS:
            try:
                insert_btn = page.query_selector(selector)
                if insert_btn and insert_btn.is_visible():
                    insert_btn.click()
                    break
            except:
                continue

        if not insert_btn:
            # Fallback to Enter key
            page.keyboard.press("Enter")

        time.sleep(4)  # Wait for URL to be processed

        print(f"  ✅ {source_type} source added!")
        return f"Successfully added {source_type} source: {source_url}"

    except Exception as e:
        print(f"  ❌ Error: {e}")
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
    parser = argparse.ArgumentParser(description='Add sources to NotebookLM notebooks')

    parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    parser.add_argument('--notebook-id', help='Notebook ID from library')

    # Source types (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('--text', help='Text content to paste as source')
    source_group.add_argument('--file', help='Path to text file to read and paste')
    source_group.add_argument('--url', help='Website or YouTube URL to add')

    parser.add_argument('--show-browser', action='store_true', help='Show browser')

    args = parser.parse_args()

    # Resolve notebook URL
    notebook_url = args.notebook_url

    if not notebook_url and args.notebook_id:
        library = NotebookLibrary()
        notebook = library.get_notebook(args.notebook_id)
        if notebook:
            notebook_url = notebook['url']
            print(f"📚 Using notebook: {notebook['name']}")
        else:
            print(f"❌ Notebook '{args.notebook_id}' not found")
            return 1

    if not notebook_url:
        # Try active notebook
        library = NotebookLibrary()
        active = library.get_active_notebook()
        if active:
            notebook_url = active['url']
            print(f"📚 Using active notebook: {active['name']}")
        else:
            print("❌ No notebook specified. Use --notebook-url or --notebook-id")
            return 1

    # Execute based on source type
    result = None

    if args.text:
        result = add_text_source(
            notebook_url=notebook_url,
            content=args.text,
            headless=not args.show_browser
        )

    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"❌ File not found: {args.file}")
            return 1

        print(f"📄 Reading: {args.file}")
        content = file_path.read_text(encoding='utf-8')
        print(f"  Size: {len(content)} characters")

        result = add_text_source(
            notebook_url=notebook_url,
            content=content,
            headless=not args.show_browser
        )

    elif args.url:
        result = add_url_source(
            notebook_url=notebook_url,
            source_url=args.url,
            headless=not args.show_browser
        )

    # Print result
    print("\n" + "=" * 50)
    if result:
        print(f"✅ {result}")
        return 0
    else:
        print("❌ Failed to add source")
        return 1


if __name__ == "__main__":
    sys.exit(main())
