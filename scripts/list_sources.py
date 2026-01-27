#!/usr/bin/env python3
"""
List Sources from NotebookLM
Reads source names directly from the UI (more reliable than asking questions)
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
from notebook_manager import NotebookLibrary
from browser_utils import BrowserFactory, StealthUtils


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

        # Extract source titles using JavaScript
        # This reads directly from the DOM - much more reliable than asking questions
        sources = page.evaluate("""
            () => {
                const sources = [];
                const seenTexts = new Set();

                // UI text to skip (exact matches)
                const skipTexts = new Set(['check_box', 'more_vert', 'description', 'drive_pdf',
                                   'markdown', 'web', 'select all', 'select all sources',
                                   'sources', 'add source', 'add sources', 'video_youtube', 'link', 'pdf',
                                   'more', 'less', 'expand', 'collapse', 'chat', 'studio',
                                   'save to note', 'try deep research for an in-depth report and new sources!']);

                // Helper to check if text is a valid source name
                const isValidSource = (text) => {
                    if (!text || text.length < 3 || text.length > 150) return false;
                    if (text.includes('\\n')) return false;

                    // Skip UI elements (exact match, case insensitive)
                    if (skipTexts.has(text.toLowerCase())) return false;

                    // Skip if it starts with bullet points or looks like content
                    if (text.startsWith('•') || text.startsWith('-') || text.startsWith('*')) return false;
                    if (text.startsWith('How ') || text.startsWith('What ') || text.startsWith('Based on')) return false;

                    return true;
                };

                // Primary method: Find the source list container first, then extract titles
                // The source panel is typically on the left side of the page
                // Each source row has: [icon] [title] [checkbox]

                // Look for elements that have a checkbox sibling/child - these are source rows
                const checkboxes = document.querySelectorAll('mat-checkbox, [role="checkbox"]');

                for (const checkbox of checkboxes) {
                    const rect = checkbox.getBoundingClientRect();
                    // Must be in left panel (x < 450) - this filters out main content
                    if (rect.x > 450 || rect.x < 0) continue;

                    // Get the row container (parent that contains both title and checkbox)
                    let row = checkbox.parentElement;
                    for (let i = 0; i < 4 && row; i++) {
                        const rowRect = row.getBoundingClientRect();
                        // Row should be reasonably sized (not too tall = contains multiple items)
                        if (rowRect.height > 30 && rowRect.height < 80) {
                            break;
                        }
                        row = row.parentElement;
                    }

                    if (!row) continue;

                    // Extract the title from this row
                    // Look for span or div elements that contain the source name
                    const textElements = row.querySelectorAll('span, div');
                    for (const el of textElements) {
                        const text = el.innerText?.trim();
                        if (!text) continue;

                        // Skip if it's too short or contains multiple lines
                        if (text.length < 3 || text.length > 150) continue;
                        if (text.includes('\\n')) continue;

                        // Skip icon text
                        if (skipTexts.has(text.toLowerCase())) continue;

                        // This is likely the source title
                        if (!seenTexts.has(text) && isValidSource(text)) {
                            seenTexts.add(text);
                            sources.push(text);
                            break;  // Found title for this row
                        }
                    }
                }

                // Fallback: If we didn't find enough, try looking for .source-title class
                if (sources.length < 3) {
                    const titleElements = document.querySelectorAll('.source-title, .source-name, [class*="source"][class*="title"]');
                    for (const el of titleElements) {
                        const text = el.innerText?.trim();
                        if (text && isValidSource(text) && !seenTexts.has(text)) {
                            seenTexts.add(text);
                            sources.push(text);
                        }
                    }
                }

                // Sort alphabetically for easier reading
                return sources.sort((a, b) => a.localeCompare(b));
            }
        """)

        print(f"    Found {len(sources)} sources")
        return sources

    except Exception as e:
        print(f"    Error: {e}")
        import traceback
        traceback.print_exc()
        return []

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
