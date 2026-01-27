#!/usr/bin/env python3
"""
List Sources from NotebookLM
Reads source names directly from the UI (more reliable than asking questions)
"""

import argparse
import sys
import re
import time
import traceback
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from browser_utils import BrowserFactory
from config import SOURCE_DETECTION_JS


def list_sources_from_ui(notebook_url: str, headless: bool = True) -> list:
    """
    List all sources in a NotebookLM notebook by reading the UI.

    This is more reliable than asking NotebookLM to list sources via a question.

    Args:
        notebook_url: The NotebookLM notebook URL
        headless: Run browser in headless mode

    Returns:
        List of source names/titles
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("  Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return []

    print(f"  Reading sources from: {notebook_url}")

    playwright = None
    context = None
    sources = []

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

        # Wait for sources panel to load
        print("    Waiting for sources panel...")
        time.sleep(3)

        # Scroll through the sources panel to load all sources
        # (some sources may be lazy-loaded or virtualized)
        print("    Scrolling through sources panel...")

        # Find and scroll the sources container
        page.evaluate("""
            () => {
                // Find the scrollable sources container
                const containers = document.querySelectorAll('[class*="source"], [class*="scroll"], [role="list"]');
                for (const container of containers) {
                    const rect = container.getBoundingClientRect();
                    // Left panel container
                    if (rect.x < 350 && rect.height > 200) {
                        // Scroll down multiple times to load all sources
                        for (let i = 0; i < 10; i++) {
                            container.scrollTop += 300;
                        }
                        // Scroll back to top
                        container.scrollTop = 0;
                        break;
                    }
                }
            }
        """)
        time.sleep(1)

        # Extract source titles using shared JavaScript detection
        sources = page.evaluate(SOURCE_DETECTION_JS)
        # Sort alphabetically for easier reading
        sources.sort()

        print(f"    Found {len(sources)} sources")
        return sources

    except Exception as e:
        print(f"    Error: {e}")
        traceback.print_exc()
        return []

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
    parser = argparse.ArgumentParser(description='List sources in a NotebookLM notebook')

    # Notebook selection (mutually exclusive)
    notebook_group = parser.add_mutually_exclusive_group()
    notebook_group.add_argument('--notebook-url', help='NotebookLM notebook URL')
    notebook_group.add_argument('--notebook-id', help='Notebook ID from library')

    parser.add_argument('--show-browser', action='store_true', help='Show browser window')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    # Resolve notebook URL
    library = NotebookLibrary()

    if args.notebook_id:
        notebook = library.get_notebook(args.notebook_id)
        if not notebook:
            print(f"Notebook not found: {args.notebook_id}")
            return 1
        notebook_url = notebook['url']
        notebook_name = notebook['name']
    elif args.notebook_url:
        notebook_url = args.notebook_url
        notebook_name = "Unknown"
    else:
        # Use active notebook
        active = library.get_active_notebook()
        if active:
            notebook_url = active['url']
            notebook_name = active['name']
            print(f"Using active notebook: {notebook_name}")
        else:
            print("No notebook specified and no active notebook set")
            return 1

    sources = list_sources_from_ui(
        notebook_url=notebook_url,
        headless=not args.show_browser
    )

    if args.json:
        import json
        print(json.dumps(sources, indent=2, ensure_ascii=False))
    else:
        print("\n" + "=" * 60)
        print(f" Sources in: {notebook_name}")
        print("=" * 60)
        for i, source in enumerate(sources, 1):
            print(f"  {i}. {source}")
        print("=" * 60)
        print(f" Total: {len(sources)} sources")

    return 0


if __name__ == "__main__":
    sys.exit(main())
