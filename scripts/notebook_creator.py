#!/usr/bin/env python3
"""
Notebook Creator for NotebookLM
Creates new notebooks programmatically via browser automation
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
from config import CREATE_NOTEBOOK_SELECTORS, PAGE_LOAD_TIMEOUT
from browser_utils import BrowserFactory, StealthUtils


def create_notebook(name: str = None, headless: bool = True) -> dict:
    """
    Create a new notebook in NotebookLM.

    Args:
        name: Optional name for the notebook (if None, uses NotebookLM default)
        headless: Run browser in headless mode

    Returns:
        Dictionary with 'url' and 'id' of created notebook, or None if failed
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("  Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return None

    print("  Creating new notebook...")
    if name:
        print(f"  Name: {name}")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()

        context = BrowserFactory.launch_persistent_context(
            playwright,
            headless=headless
        )

        page = context.new_page()
        print("    Opening NotebookLM...")
        page.goto("https://notebooklm.google.com", wait_until="domcontentloaded")

        # Wait for page to load
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=60000)
        StealthUtils.random_delay(1000, 2000)

        # Find and click create button
        print("    Looking for Create button...")
        create_button = None

        for selector in CREATE_NOTEBOOK_SELECTORS:
            try:
                create_button = page.wait_for_selector(selector, timeout=5000, state="visible")
                if create_button:
                    print(f"     Found: {selector}")
                    break
            except:
                continue

        if not create_button:
            print("     Could not find Create button")
            return None

        # Click to create
        StealthUtils.random_delay(300, 600)
        create_button.click()
        print("    Clicked Create button")

        # Wait for new notebook page to load
        StealthUtils.random_delay(2000, 3000)

        # Wait for URL to change to notebook view
        try:
            page.wait_for_url(re.compile(r"https://notebooklm\.google\.com/notebook/"), timeout=30000)
        except:
            print("     Timeout waiting for notebook page")
            return None

        # Get the new notebook URL
        notebook_url = page.url
        print(f"    Notebook created: {notebook_url}")

        # Extract notebook ID from URL
        notebook_id = None
        match = re.search(r'/notebook/([a-zA-Z0-9-]+)', notebook_url)
        if match:
            notebook_id = match.group(1)

        # If name provided, try to rename the notebook
        if name:
            print(f"    Setting notebook name: {name}")
            # Look for title/name input field
            try:
                # Try clicking on the notebook title to edit it
                title_element = page.query_selector('h1, [contenteditable="true"], input[type="text"]')
                if title_element:
                    title_element.click()
                    StealthUtils.random_delay(300, 500)
                    # Select all and type new name
                    page.keyboard.press("Control+a")
                    StealthUtils.random_delay(100, 200)
                    for char in name:
                        page.keyboard.type(char, delay=50)
                    page.keyboard.press("Enter")
                    StealthUtils.random_delay(500, 1000)
                    print("     Name set successfully")
            except Exception as e:
                print(f"     Could not set name: {e}")

        return {
            'url': notebook_url,
            'id': notebook_id,
            'name': name
        }

    except Exception as e:
        print(f"   Error: {e}")
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
    parser = argparse.ArgumentParser(description='Create a new NotebookLM notebook')

    parser.add_argument('--name', help='Name for the new notebook')
    parser.add_argument('--show-browser', action='store_true', help='Show browser window')

    args = parser.parse_args()

    result = create_notebook(
        name=args.name,
        headless=not args.show_browser
    )

    if result:
        print("\n" + "=" * 60)
        print(" New Notebook Created")
        print("=" * 60)
        print(f"URL: {result['url']}")
        print(f"ID:  {result['id']}")
        if result.get('name'):
            print(f"Name: {result['name']}")
        print("=" * 60)
        return 0
    else:
        print("\n Failed to create notebook")
        return 1


if __name__ == "__main__":
    sys.exit(main())
