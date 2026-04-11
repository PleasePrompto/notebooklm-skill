#!/usr/bin/env python3
"""
Source Management for NotebookLM
Manages sources (documents, websites, text) within NotebookLM notebooks via browser automation.
"""

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from patchright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from browser_utils import BrowserFactory, StealthUtils
from config import (
    SOURCE_ITEM_SELECTOR,
    MORE_VERT_SELECTOR,
    REMOVE_MENU_SELECTOR,
    DELETE_DIALOG_SELECTOR,
    WEBSITE_URL_INPUT_SELECTOR,
    COPIED_TEXT_INPUT_SELECTOR,
)


class SourceManager:
    """Manages sources within a NotebookLM notebook via browser automation."""

    def __init__(self, notebook_url: str, headless: bool = True):
        self.notebook_url = notebook_url
        self.headless = headless

    def _open_sources_tab(self, page) -> bool:
        """Navigate to notebook and open the Sources tab."""
        try:
            print("  🌐 Opening notebook...")
            page.goto(self.notebook_url, wait_until="domcontentloaded")
            page.wait_for_url(
                re.compile(r"^https://notebooklm\.google\.com/"), timeout=15000
            )
            time.sleep(3)

            print("  📑 Opening Sources tab...")
            sources_tab = page.get_by_text("Sources", exact=True).first
            sources_tab.click()
            time.sleep(2)
            return True
        except Exception as e:
            print(f"  ❌ Failed to open Sources tab: {e}")
            return False

    def _get_source_names(self, page) -> List[str]:
        """Read all source names from the Sources panel."""
        elements = page.query_selector_all(SOURCE_ITEM_SELECTOR)
        names = []
        for el in elements:
            label = el.get_attribute("aria-label") or ""
            if label:
                names.append(label)
        return names

    def _find_source_index(self, page, name: str) -> Optional[int]:
        """Find a source by name. Exact match first, then case-insensitive substring."""
        sources = page.query_selector_all(SOURCE_ITEM_SELECTOR)
        # Exact match
        for i, el in enumerate(sources):
            label = el.get_attribute("aria-label") or ""
            if label == name:
                return i
        # Case-insensitive substring
        name_lower = name.lower()
        for i, el in enumerate(sources):
            label = el.get_attribute("aria-label") or ""
            if name_lower in label.lower():
                print(f"  ⚠️  Fuzzy match: '{label}'")
                return i
        return None

    def _wait_for_source_count(self, page, expected_count: int, timeout: int = 60) -> bool:
        """Poll until source count reaches expected value or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            current = len(page.query_selector_all(SOURCE_ITEM_SELECTOR))
            if current >= expected_count:
                return True
            time.sleep(2)
        return False

    def _run_browser_op(self, operation):
        """Shared browser lifecycle: auth check, launch, run operation, cleanup."""
        auth = AuthManager()
        if not auth.is_authenticated():
            print("⚠️  Not authenticated. Run: python auth_manager.py setup")
            return None

        playwright = None
        context = None
        try:
            playwright = sync_playwright().start()
            context = BrowserFactory.launch_persistent_context(
                playwright, headless=self.headless
            )
            page = context.new_page()
            if not self.headless:
                page.set_viewport_size({"width": 1200, "height": 800})

            if not self._open_sources_tab(page):
                return None

            return operation(page)

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

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def list_sources(self) -> Optional[List[Dict[str, str]]]:
        """List all sources in the notebook."""

        def _op(page):
            names = self._get_source_names(page)
            print(f"\n📚 Sources ({len(names)}):")
            for i, name in enumerate(names):
                print(f"  [{i}] {name}")
            return [{"name": n, "index": i} for i, n in enumerate(names)]

        return self._run_browser_op(_op)

    def add_source_text(self, text: str) -> bool:
        """Add a copied-text source to the notebook."""

        def _op(page):
            initial_count = len(page.query_selector_all(SOURCE_ITEM_SELECTOR))
            print(f"  📝 Adding text source ({len(text)} chars)...")

            # Open Add Source dialog
            page.get_by_role(
                "button", name=re.compile("add source", re.I)
            ).first.click()
            time.sleep(2)

            # Click "Copied text"
            page.get_by_text("Copied text", exact=True).first.click()
            time.sleep(2)

            # Fill the textarea
            textarea = page.query_selector(COPIED_TEXT_INPUT_SELECTOR)
            if not textarea:
                print("  ❌ Could not find text input")
                return False
            textarea.fill(text)
            time.sleep(1)

            # Click Insert
            insert_btn = page.query_selector('button:has-text("Insert")')
            if not insert_btn:
                print("  ❌ Could not find Insert button")
                return False
            insert_btn.click()
            print("  ⏳ Waiting for processing...")

            if self._wait_for_source_count(page, initial_count + 1):
                names = self._get_source_names(page)
                print(f"  ✅ Source added! Now {len(names)} sources.")
                return True
            else:
                print("  ❌ Timeout waiting for source to be added")
                return False

        result = self._run_browser_op(_op)
        return result if result is not None else False

    def add_source_website(self, urls: List[str]) -> bool:
        """Add website/YouTube URL sources to the notebook.

        NOTE: This uses --show-browser mode and requires manual confirmation.
        NotebookLM's Angular form validation blocks programmatic URL input.
        The browser will open with the URLs pre-filled, but you must click Submit.
        """
        for url in urls:
            if not url.startswith(("http://", "https://")):
                print(f"  ❌ Invalid URL: {url}")
                return False

        # Force visible browser for URL input (user must click Submit)
        saved_headless = self.headless
        self.headless = False

        def _op(page):
            initial_count = len(page.query_selector_all(SOURCE_ITEM_SELECTOR))
            print(f"  🔗 Adding {len(urls)} URL source(s)...")

            page.get_by_role(
                "button", name=re.compile("add source", re.I)
            ).first.click()
            time.sleep(2)

            page.get_by_text("Websites", exact=True).first.click()
            time.sleep(2)

            # Type URLs into the textarea
            locator = page.locator(WEBSITE_URL_INPUT_SELECTOR)
            locator.click()
            time.sleep(0.5)
            locator.press_sequentially("\n".join(urls), delay=30)

            print("  ⚠️  Browser is open — please click Submit manually.")
            print("  ⏳ Waiting up to 120s for source to appear...")

            if self._wait_for_source_count(page, initial_count + 1, timeout=120):
                names = self._get_source_names(page)
                print(f"  ✅ Source(s) added! Now {len(names)} sources.")
                return True
            else:
                current = len(page.query_selector_all(SOURCE_ITEM_SELECTOR))
                if current > initial_count:
                    print(f"  ✅ {current - initial_count} source(s) added.")
                    return True
                print("  ❌ Timeout — source was not added")
                return False

        try:
            result = self._run_browser_op(_op)
            return result if result is not None else False
        finally:
            self.headless = saved_headless

    def add_source_file(self, file_path: str) -> bool:
        """Upload a file as a source to the notebook."""
        path = Path(file_path)
        if not path.exists():
            print(f"  ❌ File not found: {file_path}")
            return False

        def _op(page):
            initial_count = len(page.query_selector_all(SOURCE_ITEM_SELECTOR))
            print(f"  📁 Uploading: {path.name}")

            # Open Add Source dialog
            page.get_by_role(
                "button", name=re.compile("add source", re.I)
            ).first.click()
            time.sleep(2)

            # Click "Upload files" and handle file chooser
            upload_btn = page.get_by_text("Upload files", exact=True).first
            with page.expect_file_chooser() as fc_info:
                upload_btn.click()
            file_chooser = fc_info.value
            file_chooser.set_files(str(path))
            print("  ⏳ Waiting for processing...")

            if self._wait_for_source_count(page, initial_count + 1):
                names = self._get_source_names(page)
                print(f"  ✅ File uploaded! Now {len(names)} sources.")
                return True
            else:
                print("  ❌ Timeout waiting for file to be processed")
                return False

        result = self._run_browser_op(_op)
        return result if result is not None else False

    def read_source(self, source_name: str) -> Optional[str]:
        """Read a source's content (AI summary + document text)."""

        def _op(page):
            idx = self._find_source_index(page, source_name)
            if idx is None:
                print(f"  ❌ Source not found: {source_name}")
                return None

            sources = page.query_selector_all(SOURCE_ITEM_SELECTOR)
            label = sources[idx].get_attribute("aria-label") or source_name
            print(f"  📖 Reading: {label}")

            # Click the source to open its detail view
            sources[idx].click()
            time.sleep(4)

            # Extract the source guide content from the left panel
            # The source detail replaces the sources list with guide + content
            content_parts = []

            # Try to get the source guide summary
            guide = page.query_selector(".source-guide, [class*='source-guide']")
            if guide:
                content_parts.append("=== Source Guide ===")
                content_parts.append(guide.inner_text())

            # Get the full panel text as fallback/supplement
            # The Sources panel shows the source content after clicking
            panel = page.query_selector(
                "source-detail, [class*='source-detail'], [class*='source-content']"
            )
            if panel:
                content_parts.append("\n=== Source Content ===")
                content_parts.append(panel.inner_text())

            # If no specific selectors matched, grab the whole left panel
            if not content_parts:
                # The sources column is the first major section
                try:
                    # Get all text from the sources/detail area
                    left_panel = page.evaluate("""() => {
                        const el = document.querySelector('notebook');
                        if (!el) return '';
                        // Get the first column's text
                        const cols = el.querySelectorAll('[class*="column"], [class*="panel"]');
                        for (const col of cols) {
                            const text = col.innerText;
                            if (text.length > 200) return text;
                        }
                        return '';
                    }""")
                    if left_panel:
                        content_parts.append(left_panel)
                except:
                    pass

            if not content_parts:
                # Last resort: dump visible body text and look for the source content
                body_text = page.inner_text("body")
                # The source name appears followed by its content
                if label in body_text:
                    start = body_text.index(label)
                    content_parts.append(body_text[start : start + 5000])

            content = "\n".join(content_parts).strip()
            if content:
                print(f"  ✅ Read {len(content)} characters")
                return content
            else:
                print("  ❌ Could not extract source content")
                return None

        return self._run_browser_op(_op)

    def remove_source(self, source_name: str) -> bool:
        """Remove a source from the notebook."""

        def _op(page):
            idx = self._find_source_index(page, source_name)
            if idx is None:
                print(f"  ❌ Source not found: {source_name}")
                return False

            sources = page.query_selector_all(SOURCE_ITEM_SELECTOR)
            label = sources[idx].get_attribute("aria-label") or source_name
            initial_count = len(sources)
            print(f"  🗑️  Removing: {label}")

            # Hover to reveal more_vert menu
            sources[idx].hover()
            time.sleep(1)

            # Find the more_vert button closest to this source
            target_box = sources[idx].bounding_box()
            more_btns = []
            for mb in page.query_selector_all(MORE_VERT_SELECTOR):
                try:
                    if mb.is_visible():
                        box = mb.bounding_box()
                        if box and box["x"] < 400:
                            more_btns.append((mb, box))
                except:
                    pass

            if not more_btns:
                print("  ❌ Could not find source menu button")
                return False

            # Click the one closest vertically to the target source
            best = min(more_btns, key=lambda x: abs(x[1]["y"] - target_box["y"]))
            best[0].click()
            time.sleep(1)

            # Click "Remove source"
            remove_item = page.query_selector(REMOVE_MENU_SELECTOR)
            if not remove_item:
                print("  ❌ Could not find Remove option")
                return False
            remove_item.click()
            time.sleep(2)

            # Confirm deletion inside the dialog
            dialog = page.query_selector(DELETE_DIALOG_SELECTOR)
            if dialog:
                delete_btn = dialog.query_selector('button:has-text("Delete")')
                if delete_btn:
                    delete_btn.click(force=True)
                    time.sleep(3)
                else:
                    print("  ❌ Could not find Delete confirmation button")
                    return False
            else:
                # Fallback: force-click any visible Delete button
                delete_btn = page.query_selector('button:has-text("Delete")')
                if delete_btn:
                    delete_btn.click(force=True)
                    time.sleep(3)
                else:
                    print("  ❌ No confirmation dialog found")
                    return False

            # Verify deletion
            final_count = len(page.query_selector_all(SOURCE_ITEM_SELECTOR))
            if final_count < initial_count:
                print(f"  ✅ Removed! Now {final_count} sources.")
                return True
            else:
                print("  ❌ Source count unchanged after deletion")
                return False

        result = self._run_browser_op(_op)
        return result if result is not None else False

    def run_test(self) -> bool:
        """Integration test: add text source, read it, remove it."""
        print("\n🧪 Running source management integration test...")

        # Step 1: List initial sources
        print("\n--- Step 1: List sources ---")
        initial = self.list_sources()
        if initial is None:
            print("❌ FAIL: Could not list sources")
            return False
        initial_count = len(initial)
        print(f"  Initial count: {initial_count}")

        # Step 2: Add a text source
        print("\n--- Step 2: Add text source ---")
        test_text = (
            "INTEGRATION TEST SOURCE - This is a temporary source created by "
            "the source_manager.py integration test. It will be deleted shortly. "
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if not self.add_source_text(test_text):
            print("❌ FAIL: Could not add text source")
            return False

        # Step 3: Verify count increased
        print("\n--- Step 3: Verify source added ---")
        after_add = self.list_sources()
        if after_add is None or len(after_add) != initial_count + 1:
            print(f"❌ FAIL: Expected {initial_count + 1} sources, got {len(after_add) if after_add else 'None'}")
            return False

        # Find the new source name
        initial_names = {s["name"] for s in initial}
        new_sources = [s for s in after_add if s["name"] not in initial_names]
        if not new_sources:
            print("❌ FAIL: Could not identify new source")
            return False
        new_name = new_sources[0]["name"]
        print(f"  New source: {new_name}")

        # Step 4: Read the source
        print("\n--- Step 4: Read source ---")
        content = self.read_source(new_name)
        if not content:
            print("⚠️  WARN: Could not read source content (continuing)")

        # Step 5: Remove the source
        print("\n--- Step 5: Remove source ---")
        if not self.remove_source(new_name):
            print("❌ FAIL: Could not remove source")
            return False

        # Step 6: Verify count restored
        print("\n--- Step 6: Verify source removed ---")
        after_remove = self.list_sources()
        if after_remove is None or len(after_remove) != initial_count:
            print(f"❌ FAIL: Expected {initial_count} sources, got {len(after_remove) if after_remove else 'None'}")
            return False

        print(f"\n✅ ALL TESTS PASSED ({initial_count} → {initial_count + 1} → {initial_count})")
        return True


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #


def resolve_notebook_url(args) -> Optional[str]:
    """Resolve notebook URL from args, matching ask_question.py pattern."""
    if hasattr(args, "notebook_url") and args.notebook_url:
        return args.notebook_url

    if hasattr(args, "notebook_id") and args.notebook_id:
        library = NotebookLibrary()
        notebook = library.get_notebook(args.notebook_id)
        if notebook:
            return notebook["url"]
        print(f"❌ Notebook '{args.notebook_id}' not found")
        return None

    # Try active notebook
    library = NotebookLibrary()
    active = library.get_active_notebook()
    if active:
        print(f"📚 Using active notebook: {active['name']}")
        return active["url"]

    # Show available
    notebooks = library.list_notebooks()
    if notebooks:
        print("\n📚 Available notebooks:")
        for nb in notebooks:
            mark = " [ACTIVE]" if nb.get("id") == library.active_notebook_id else ""
            print(f"  {nb['id']}: {nb['name']}{mark}")
        print("\nSpecify with --notebook-id or --notebook-url")
    else:
        print("❌ No notebooks in library. Add one first with notebook_manager.py")
    return None


def add_common_args(parser):
    """Add notebook selection and browser args shared by all subcommands."""
    parser.add_argument("--notebook-url", help="NotebookLM notebook URL")
    parser.add_argument("--notebook-id", help="Notebook ID from library")
    parser.add_argument("--show-browser", action="store_true", help="Show browser window")


def main():
    parser = argparse.ArgumentParser(description="Manage NotebookLM sources")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # list
    list_parser = subparsers.add_parser("list", help="List sources in a notebook")
    add_common_args(list_parser)

    # add-text
    add_text_parser = subparsers.add_parser("add-text", help="Add copied text as source")
    add_text_parser.add_argument("--text", help="Text content to add")
    add_text_parser.add_argument(
        "--from-file", help="Read text from a local file instead"
    )
    add_common_args(add_text_parser)

    # add-website
    add_web_parser = subparsers.add_parser(
        "add-website", help="Add website/YouTube URLs as sources"
    )
    add_web_parser.add_argument(
        "--urls", required=True, help="Comma-separated URLs"
    )
    add_common_args(add_web_parser)

    # add-file
    add_file_parser = subparsers.add_parser("add-file", help="Upload a file as source")
    add_file_parser.add_argument("--file", required=True, help="Path to file")
    add_common_args(add_file_parser)

    # read
    read_parser = subparsers.add_parser("read", help="Read a source's content")
    read_parser.add_argument("--name", required=True, help="Source name")
    add_common_args(read_parser)

    # remove
    remove_parser = subparsers.add_parser("remove", help="Remove a source")
    remove_parser.add_argument("--name", required=True, help="Source name")
    add_common_args(remove_parser)

    # test
    test_parser = subparsers.add_parser(
        "test", help="Run integration test (add/read/remove)"
    )
    add_common_args(test_parser)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Resolve notebook
    notebook_url = resolve_notebook_url(args)
    if not notebook_url:
        return 1

    headless = not args.show_browser
    mgr = SourceManager(notebook_url, headless=headless)

    if args.command == "list":
        result = mgr.list_sources()
        return 0 if result is not None else 1

    elif args.command == "add-text":
        text = args.text
        if not text and args.from_file:
            path = Path(args.from_file)
            if not path.exists():
                print(f"❌ File not found: {args.from_file}")
                return 1
            text = path.read_text()
        if not text:
            print("❌ Provide --text or --from-file")
            return 1
        return 0 if mgr.add_source_text(text) else 1

    elif args.command == "add-website":
        urls = [u.strip() for u in args.urls.split(",")]
        return 0 if mgr.add_source_website(urls) else 1

    elif args.command == "add-file":
        return 0 if mgr.add_source_file(args.file) else 1

    elif args.command == "read":
        content = mgr.read_source(args.name)
        if content:
            print("\n" + "=" * 60)
            print(content)
            print("=" * 60)
            return 0
        return 1

    elif args.command == "remove":
        return 0 if mgr.remove_source(args.name) else 1

    elif args.command == "test":
        return 0 if mgr.run_test() else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
