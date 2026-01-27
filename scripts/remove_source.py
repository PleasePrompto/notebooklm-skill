#!/usr/bin/env python3
"""
Remove Source from NotebookLM
CAUTION: This permanently removes a source from a notebook. Use with care.
"""

import argparse
import sys
import re
import traceback
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import (
    SOURCE_MENU_BUTTON_SELECTORS,
    SOURCE_REMOVE_MENU_SELECTORS,
    SOURCE_CONFIRM_REMOVE_SELECTORS,
    PAGE_LOAD_TIMEOUT
)
from browser_utils import BrowserFactory, StealthUtils, find_element_with_selectors


def remove_source(
    notebook_url: str,
    source_name: str,
    headless: bool = True,
    confirm: bool = False
) -> bool:
    """
    Remove a source from a NotebookLM notebook.

    CAUTION: This is a PERMANENT action. The source cannot be recovered.

    Args:
        notebook_url: The NotebookLM notebook URL
        source_name: Name/title of the source to remove (partial match supported)
        headless: Run browser in headless mode
        confirm: Must be True to actually remove (safety check)

    Returns:
        True if source was removed, False otherwise
    """
    if not confirm:
        print("  WARNING: Remove source requires --confirm flag")
        print("  This action is PERMANENT and cannot be undone.")
        print("  Re-run with --confirm to proceed.")
        return False

    auth = AuthManager()

    if not auth.is_authenticated():
        print("  Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return False

    print("  Removing source from notebook...")
    print(f"  Notebook: {notebook_url}")
    print(f"  Source to remove: {source_name}")
    print("")
    print("  WARNING: This action is PERMANENT!")
    print("")

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

        # Look for the source in the sources panel (left sidebar)
        print(f"    Looking for source: {source_name}")

        # The sources panel is on the left side of the page
        # Each source appears as a row with: [menu button (⋮)] [icon] [source name] [checkbox]
        # We need to find the specific row containing our source name

        source_row = None
        source_text_found = None

        # Strategy: Find all source rows and look for the one with matching text
        # Source rows are typically in a scrollable list under "Sources" heading

        # First, try to find the sources container
        sources_container = page.query_selector('[aria-label="Sources"], .sources-panel, [data-testid="sources-list"]')
        if not sources_container:
            # Fallback: look for elements that contain source names
            sources_container = page

        # Look for source items - they typically have the source name as text
        # and a checkbox to the right, with a menu button to the left
        potential_sources = page.query_selector_all('div, span, li')

        for el in potential_sources:
            try:
                text = el.text_content() or ''
                # Check if this element contains our source name (case insensitive, partial match)
                if source_name.lower() in text.lower():
                    # Verify this is a source item (not some other element with the text)
                    # Source items are typically compact and don't contain huge amounts of text
                    if len(text) < 200:  # Source names are relatively short
                        # Check if there's a checkbox or icon nearby (indicators of source row)
                        has_checkbox = el.query_selector('input[type="checkbox"], [role="checkbox"]')
                        parent = el.evaluate_handle('el => el.parentElement')

                        # Get bounding box to verify it's in the left panel (x < 400 typically)
                        box = el.bounding_box()
                        if box and box['x'] < 400:  # Left panel check
                            source_row = el
                            source_text_found = text[:50]
                            break
            except Exception:
                continue

        if not source_row:
            print(f"     Could not find source: {source_name}")
            page.screenshot(path="/tmp/notebooklm_source_debug.png")
            print("     Debug screenshot saved to /tmp/notebooklm_source_debug.png")
            return False

        print(f"     Found source: {source_text_found}...")

        # Now find the menu button for THIS specific source
        # The menu button (⋮) is to the LEFT of the source name
        print("    Looking for source menu button...")

        menu_button = None
        source_box = source_row.bounding_box()

        if source_box:
            # Hover over the source row to make the menu button visible
            page.mouse.move(source_box['x'] + source_box['width'] / 2,
                           source_box['y'] + source_box['height'] / 2)
            StealthUtils.random_delay(500, 800)

            # Look for menu buttons that are:
            # 1. On the same vertical level (same Y coordinate ± some tolerance)
            # 2. To the LEFT of the source text (smaller X coordinate)
            # 3. Within the sources panel (X < 400)

            all_buttons = page.query_selector_all('button')
            for btn in all_buttons:
                try:
                    btn_box = btn.bounding_box()
                    if not btn_box:
                        continue

                    # Check if button is on same row (Y within 30px)
                    y_diff = abs(btn_box['y'] - source_box['y'])
                    if y_diff > 30:
                        continue

                    # Check if button is in left panel
                    if btn_box['x'] > 350:
                        continue

                    # Check if button is to the left of source (or at start of row)
                    if btn_box['x'] > source_box['x']:
                        continue

                    # Check aria-label or other indicators that this is a menu button
                    aria_label = btn.get_attribute('aria-label') or ''
                    inner_html = btn.inner_html() or ''

                    # Menu buttons often have "more", "options", or the ⋮ icon
                    if ('more' in aria_label.lower() or
                        'option' in aria_label.lower() or
                        'menu' in aria_label.lower() or
                        'more_vert' in inner_html.lower() or
                        '⋮' in inner_html):
                        menu_button = btn
                        print(f"     Found menu button at ({btn_box['x']}, {btn_box['y']})")
                        break

                    # If no aria-label, check if it's a small button (likely icon-only menu button)
                    if btn_box['width'] < 50 and btn_box['height'] < 50:
                        # This could be the menu button - verify by checking if it's visible
                        if btn.is_visible():
                            menu_button = btn
                            print(f"     Found potential menu button at ({btn_box['x']}, {btn_box['y']})")
                            break
                except Exception:
                    continue

        if not menu_button:
            # Fallback: try clicking directly on the source row to see if menu appears
            print("     Menu button not found, trying direct interaction...")
            try:
                # Right-click might show context menu
                source_row.click(button='right')
                StealthUtils.random_delay(500, 800)

                # Check if a menu appeared with "Remove" option
                remove_check = page.query_selector('[role="menuitem"]:has-text("Remove"), li:has-text("Remove")')
                if remove_check:
                    print("     Context menu appeared!")
                    # Skip to the remove step
                    menu_button = "context_menu_used"
            except Exception:
                pass

        if not menu_button:
            print("     Could not find source menu button")
            page.screenshot(path="/tmp/notebooklm_menu_debug.png")
            print("     Debug screenshot saved to /tmp/notebooklm_menu_debug.png")
            return False

        if menu_button != "context_menu_used":
            print("     Clicking menu button...")
            menu_button.click()
            StealthUtils.random_delay(800, 1200)

        # Look for "Remove source" option in the dropdown
        print("    Looking for 'Remove source' option...")

        remove_option, remove_selector = find_element_with_selectors(
            page, SOURCE_REMOVE_MENU_SELECTORS, timeout=3000
        )

        if not remove_option:
            print("     Could not find 'Remove source' option")
            page.screenshot(path="/tmp/notebooklm_remove_debug.png")
            print("     Debug screenshot saved to /tmp/notebooklm_remove_debug.png")
            return False

        print(f"     Found: {remove_selector}")
        remove_option.click()
        StealthUtils.random_delay(500, 800)

        # Handle confirmation dialog if one appears
        print("    Checking for confirmation dialog...")
        StealthUtils.random_delay(500, 800)

        # Try to find and click confirm button
        confirm_button, confirm_selector = find_element_with_selectors(
            page, SOURCE_CONFIRM_REMOVE_SELECTORS, timeout=3000
        )

        if confirm_button:
            print("     Found confirmation dialog, confirming removal...")
            confirm_button.click()
            StealthUtils.random_delay(1000, 1500)

        # Verify removal
        print("    Verifying source was removed...")
        StealthUtils.random_delay(1500, 2000)

        # Try to find the source again - it should not exist
        still_exists = False

        # Check all elements in the left panel for the source name
        all_elements = page.query_selector_all('div, span')
        for el in all_elements:
            try:
                box = el.bounding_box()
                if not box or box['x'] > 400:  # Only check left panel
                    continue
                text = el.text_content() or ''
                if source_name.lower() in text.lower() and len(text) < 200:
                    if el.is_visible():
                        still_exists = True
                        break
            except Exception:
                continue

        if still_exists:
            print("     Source still appears to exist - removal may have failed")
            return False

        print("   Source removed successfully!")
        return True

    except Exception as e:
        print(f"   Error: {e}")
        traceback.print_exc()
        return False

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
        description='Remove a source from NotebookLM notebook (PERMANENT ACTION)',
        epilog='WARNING: This action cannot be undone. Use with caution.'
    )

    # Notebook selection (mutually exclusive)
    notebook_group = parser.add_mutually_exclusive_group(required=True)
    notebook_group.add_argument('--notebook-url', help='NotebookLM notebook URL')
    notebook_group.add_argument('--notebook-id', help='Notebook ID from library')

    # Source to remove
    parser.add_argument('--source', required=True,
                        help='Name of the source to remove (partial match supported)')

    # Safety flag
    parser.add_argument('--confirm', action='store_true',
                        help='REQUIRED: Confirm you want to permanently remove this source')

    parser.add_argument('--show-browser', action='store_true',
                        help='Show browser window')

    args = parser.parse_args()

    # Resolve notebook URL
    if args.notebook_id:
        library = NotebookLibrary()
        notebook = library.get_notebook(args.notebook_id)
        if not notebook:
            print(f"Notebook not found: {args.notebook_id}")
            return 1
        notebook_url = notebook['url']
    else:
        notebook_url = args.notebook_url

    # Extra warning
    if args.confirm:
        print("")
        print("=" * 60)
        print(" WARNING: PERMANENT ACTION")
        print("=" * 60)
        print(f" You are about to PERMANENTLY remove: {args.source}")
        print(" This cannot be undone!")
        print("=" * 60)
        print("")

    result = remove_source(
        notebook_url=notebook_url,
        source_name=args.source,
        headless=not args.show_browser,
        confirm=args.confirm
    )

    if result:
        print("\n" + "=" * 60)
        print(" Source Removed")
        print("=" * 60)
        print(f" Source: {args.source}")
        print(" Status: Permanently removed")
        print("=" * 60)
        return 0
    else:
        if not args.confirm:
            print("\n To remove the source, re-run with --confirm flag")
        else:
            print("\n Failed to remove source")
        return 1


if __name__ == "__main__":
    sys.exit(main())
