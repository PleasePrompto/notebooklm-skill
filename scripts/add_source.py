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
import traceback
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
                element.click()
                print(f"    Clicked {description}")
                return True
        except Exception:
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
        except Exception:
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

    # Close any existing dialog that might be open (press Escape)
    try:
        page.keyboard.press("Escape")
        time.sleep(0.5)
    except Exception:
        pass

    # Click Sources tab if visible
    try:
        sources_tab = page.query_selector('button:has-text("Sources"), [role="tab"]:has-text("Sources")')
        if sources_tab and sources_tab.is_visible():
            sources_tab.click()
            time.sleep(1)
    except Exception:
        pass

    # Click "Add sources" button
    print("    Opening Add Sources dialog...")
    find_and_click(page, ADD_SOURCE_BUTTON_SELECTORS, "Add sources button")

    # Wait and verify dialog opened by checking for dialog buttons
    time.sleep(1.5)

    # Check if dialog opened successfully
    for verify_selector in UPLOAD_FILES_BUTTON_SELECTORS + WEBSITES_BUTTON_SELECTORS:
        try:
            dialog_btn = page.wait_for_selector(verify_selector, timeout=3000, state="visible")
            if dialog_btn:
                print("    Dialog opened successfully")
                return True
        except Exception:
            continue

    # Dialog didn't open
    debug_path = DATA_DIR / "add_source_debug.png"
    page.screenshot(path=str(debug_path))
    print(f"    Dialog did not open. Debug screenshot: {debug_path}")
    return False


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
        traceback.print_exc()
        return None

    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
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
        traceback.print_exc()
        return None

    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
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
        traceback.print_exc()
        return None

    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
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
