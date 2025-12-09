#!/usr/bin/env python3
"""
Source Manager for NotebookLM
Adds sources (URLs, text) to existing notebooks via browser automation
"""

import argparse
import sys
import re
import time
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from config import (
    ADD_SOURCE_SELECTORS,
    WEB_SEARCH_INPUT_SELECTORS,
    SOURCE_TYPE_SELECTORS,
    PAGE_LOAD_TIMEOUT
)
from browser_utils import BrowserFactory, StealthUtils


def find_element_with_selectors(page, selectors: list, timeout: int = 5000):
    """Try multiple selectors and return first match."""
    for selector in selectors:
        try:
            element = page.wait_for_selector(selector, timeout=timeout, state="visible")
            if element:
                return element, selector
        except:
            continue
    return None, None


def add_url_source(notebook_url: str, source_url: str, headless: bool = True) -> bool:
    """
    Add a URL source to a NotebookLM notebook.

    Args:
        notebook_url: The NotebookLM notebook URL
        source_url: URL to add as source
        headless: Run browser in headless mode

    Returns:
        True if successful, False otherwise
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("  Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return False

    print(f"  Adding URL source to notebook...")
    print(f"  Source URL: {source_url}")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()

        context = BrowserFactory.launch_persistent_context(
            playwright,
            headless=headless
        )

        page = context.new_page()
        print("    Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded")

        # Wait for notebook to load
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=60000)
        StealthUtils.random_delay(3000, 4000)  # Give more time for page to fully load

        # Check if add source dialog is already open (new notebook case)
        web_search_visible = page.query_selector('input[placeholder*="Search the web"]')
        websites_button = page.query_selector('button:has-text("Websites")')

        if web_search_visible or websites_button:
            print("    Add sources dialog already open")
        else:
            # Find and click "Add sources" button
            print("    Looking for Add sources button...")
            add_button, selector = find_element_with_selectors(page, ADD_SOURCE_SELECTORS, timeout=10000)

            if not add_button:
                # Try alternative approach - look for any button in sources panel
                print("     Trying alternative selectors...")
                add_button = page.query_selector('button[class*="add"], button[class*="source"], [data-action="add-source"]')
                if not add_button:
                    print("     Could not find Add sources button")
                    # Take screenshot for debugging
                    page.screenshot(path="/tmp/notebooklm_debug.png")
                    print("     Debug screenshot saved to /tmp/notebooklm_debug.png")
                    return False
                selector = "alternative"

            print(f"     Found: {selector}")
            StealthUtils.random_delay(300, 600)
            add_button.click()
            StealthUtils.random_delay(1000, 1500)

        # Look for web/URL input or Websites button
        print("    Looking for URL input or Websites button...")

        # First, try to click "Websites" button (seen in screenshot)
        websites_button = page.query_selector('button:has-text("Websites")')
        if websites_button:
            print("     Found Websites button, clicking...")
            websites_button.click()
            StealthUtils.random_delay(1500, 2000)

        # After clicking Websites, look for "Paste any links" textarea
        url_textarea = page.query_selector('textarea')
        if not url_textarea:
            # Try more specific selectors
            url_textarea = page.query_selector('[contenteditable="true"], textarea[placeholder*="link"], textarea[placeholder*="Paste"]')

        if url_textarea:
            print("     Found URL textarea (Paste any links)")
            # Click to focus
            url_textarea.click()
            StealthUtils.random_delay(200, 400)

            # Paste the URL
            url_textarea.fill(source_url)
            StealthUtils.random_delay(500, 1000)

            # Look for "Insert" button
            insert_button = page.query_selector('button:has-text("Insert")')
            if insert_button:
                print("     Found Insert button, clicking...")
                # Wait for button to be enabled (might need URL validation)
                StealthUtils.random_delay(500, 800)
                insert_button.click()
            else:
                print("     Insert button not found, pressing Enter...")
                page.keyboard.press("Enter")

            # Wait for source to be processed
            print("    Waiting for source to be indexed...")
            StealthUtils.random_delay(5000, 10000)

            print("   URL source submitted!")
            return True

        # Fallback: Try input field approach
        url_input = page.query_selector('input[placeholder*="Search the web"], input[placeholder*="URL"], input[type="url"]')
        if url_input:
            print("     Found URL input field")
            url_input.click()
            StealthUtils.random_delay(200, 400)
            url_input.fill(source_url)
            StealthUtils.random_delay(500, 1000)
            page.keyboard.press("Enter")
            print("    Submitted URL")
            time.sleep(5)
            print("   URL source added successfully!")
            return True

        print("     Could not find URL input field")
        page.screenshot(path="/tmp/notebooklm_url_debug.png")
        print("     Debug screenshot saved to /tmp/notebooklm_url_debug.png")
        return False

    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        return False

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


def add_text_source(notebook_url: str, title: str, content: str = None, file_path: str = None, headless: bool = True) -> bool:
    """
    Add a text/paste source to a NotebookLM notebook.

    Args:
        notebook_url: The NotebookLM notebook URL
        title: Title for the text source
        content: Text content to add (either content or file_path required)
        file_path: Path to file containing text content
        headless: Run browser in headless mode

    Returns:
        True if successful, False otherwise
    """
    # Get content from file if provided
    if file_path and not content:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"   Could not read file: {e}")
            return False

    if not content:
        print("   No content provided (use --content or --file)")
        return False

    auth = AuthManager()

    if not auth.is_authenticated():
        print("  Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return False

    print(f"  Adding text source to notebook...")
    print(f"  Title: {title}")
    print(f"  Content length: {len(content)} characters")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()

        context = BrowserFactory.launch_persistent_context(
            playwright,
            headless=headless
        )

        page = context.new_page()
        print("    Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded")

        # Wait for notebook to load
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=60000)
        StealthUtils.random_delay(2000, 3000)

        # Find and click "Add sources" button
        print("    Looking for Add sources button...")
        add_button, selector = find_element_with_selectors(page, ADD_SOURCE_SELECTORS)

        if not add_button:
            print("     Could not find Add sources button")
            return False

        print(f"     Found: {selector}")
        StealthUtils.random_delay(300, 600)
        add_button.click()
        StealthUtils.random_delay(1000, 1500)

        # Look for "Copied text" or "Text" button
        print("    Looking for Text/Paste option...")
        text_selectors = SOURCE_TYPE_SELECTORS.get('text', [])
        text_button, text_selector = find_element_with_selectors(page, text_selectors)

        if not text_button:
            print("     Could not find Text/Paste option")
            return False

        print(f"     Found: {text_selector}")
        text_button.click()
        StealthUtils.random_delay(1000, 1500)

        # Look for title input
        print("    Looking for title input...")
        title_input = page.query_selector('input[placeholder*="title"], input[placeholder*="Title"], input[type="text"]')

        if title_input:
            title_input.click()
            StealthUtils.random_delay(200, 400)
            for char in title:
                title_input.type(char, delay=30)
            StealthUtils.random_delay(300, 500)

        # Look for content textarea
        print("    Looking for content textarea...")
        content_input = page.query_selector('textarea[placeholder*="paste"], textarea[placeholder*="Paste"], textarea')

        if content_input:
            content_input.click()
            StealthUtils.random_delay(200, 400)
            # For large content, use fill instead of typing character by character
            content_input.fill(content)
            StealthUtils.random_delay(500, 1000)
        else:
            print("     Could not find content textarea")
            return False

        # Look for submit/add button
        print("    Looking for submit button...")
        submit_button = page.query_selector('button:has-text("Insert"), button:has-text("Add"), button:has-text("Save"), button[type="submit"]')

        if submit_button:
            submit_button.click()
            print("    Submitted text source")
            StealthUtils.random_delay(3000, 5000)
            print("   Text source added successfully!")
            return True
        else:
            # Try pressing Enter
            page.keyboard.press("Enter")
            StealthUtils.random_delay(3000, 5000)
            print("   Text source submitted (via Enter)")
            return True

    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        return False

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
    parser = argparse.ArgumentParser(description='Manage NotebookLM sources')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # add-url command
    url_parser = subparsers.add_parser('add-url', help='Add a URL source')
    url_parser.add_argument('--notebook-url', required=True, help='NotebookLM notebook URL')
    url_parser.add_argument('--source-url', required=True, help='URL to add as source')
    url_parser.add_argument('--show-browser', action='store_true', help='Show browser window')

    # add-text command
    text_parser = subparsers.add_parser('add-text', help='Add a text source')
    text_parser.add_argument('--notebook-url', required=True, help='NotebookLM notebook URL')
    text_parser.add_argument('--title', required=True, help='Title for the text source')
    text_parser.add_argument('--content', help='Text content to add')
    text_parser.add_argument('--file', help='Path to file containing text content')
    text_parser.add_argument('--show-browser', action='store_true', help='Show browser window')

    args = parser.parse_args()

    if args.command == 'add-url':
        success = add_url_source(
            notebook_url=args.notebook_url,
            source_url=args.source_url,
            headless=not args.show_browser
        )
        return 0 if success else 1

    elif args.command == 'add-text':
        success = add_text_source(
            notebook_url=args.notebook_url,
            title=args.title,
            content=args.content,
            file_path=args.file,
            headless=not args.show_browser
        )
        return 0 if success else 1

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
