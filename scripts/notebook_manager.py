#!/usr/bin/env python3
"""
Notebook Library Management for NotebookLM
Manages a library of NotebookLM notebooks with metadata.
Supports both local library operations and web-backed operations
(sync, create, rename, delete) via browser automation.
"""

import json
import argparse
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))


class NotebookLibrary:
    """Manages a collection of NotebookLM notebooks with metadata."""

    def __init__(self):
        from config import DATA_DIR, LIBRARY_FILE

        self.data_dir = DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.library_file = LIBRARY_FILE
        self.notebooks: Dict[str, Dict[str, Any]] = {}
        self.active_notebook_id: Optional[str] = None
        self.excluded_ids: List[str] = []
        self._load_library()

    def _load_library(self):
        if self.library_file.exists():
            try:
                with open(self.library_file, "r") as f:
                    data = json.load(f)
                    self.notebooks = data.get("notebooks", {})
                    self.active_notebook_id = data.get("active_notebook_id")
                    self.excluded_ids = data.get("excluded_ids", [])
                    print(f"📚 Loaded library with {len(self.notebooks)} notebooks")
            except Exception as e:
                print(f"⚠️ Error loading library: {e}")
                self.notebooks = {}
                self.active_notebook_id = None
                self.excluded_ids = []
        else:
            self._save_library()

    def _save_library(self):
        try:
            data = {
                "notebooks": self.notebooks,
                "active_notebook_id": self.active_notebook_id,
                "excluded_ids": self.excluded_ids,
                "updated_at": datetime.now().isoformat(),
            }
            with open(self.library_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"❌ Error saving library: {e}")

    @staticmethod
    def _make_id(name: str, url: str = "") -> str:
        slug = name.lower().replace(" ", "-").replace("_", "-")[:50]
        # Append short UUID suffix from URL for uniqueness
        match = re.search(r"/notebook/([a-f0-9-]+)", url)
        if match:
            slug += "-" + match.group(1)[:8]
        return slug

    @staticmethod
    def _extract_notebook_id_from_url(url: str) -> Optional[str]:
        """Extract the UUID from a NotebookLM URL."""
        match = re.search(r"/notebook/([a-f0-9-]+)", url)
        return match.group(1) if match else None

    # ------------------------------------------------------------------ #
    # Local library operations
    # ------------------------------------------------------------------ #

    def add_notebook(
        self,
        url: str,
        name: str,
        description: str = "",
        topics: Optional[List[str]] = None,
        source_count: int = 0,
    ) -> Dict[str, Any]:
        notebook_id = self._make_id(name, url)
        if notebook_id in self.notebooks:
            # Update existing
            return self.update_notebook(
                notebook_id,
                name=name,
                description=description,
                topics=topics,
                url=url,
                source_count=source_count,
            )

        notebook = {
            "id": notebook_id,
            "url": url,
            "name": name,
            "description": description,
            "topics": topics or [],
            "source_count": source_count,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "use_count": 0,
            "last_used": None,
        }
        self.notebooks[notebook_id] = notebook
        if len(self.notebooks) == 1:
            self.active_notebook_id = notebook_id
        self._save_library()
        return notebook

    def remove_notebook(self, notebook_id: str) -> bool:
        if notebook_id in self.notebooks:
            del self.notebooks[notebook_id]
            if self.active_notebook_id == notebook_id:
                self.active_notebook_id = (
                    list(self.notebooks.keys())[0] if self.notebooks else None
                )
            self._save_library()
            print(f"✅ Removed from library: {notebook_id}")
            return True
        print(f"⚠️ Not in library: {notebook_id}")
        return False

    def update_notebook(self, notebook_id: str, **kwargs) -> Dict[str, Any]:
        if notebook_id not in self.notebooks:
            raise ValueError(f"Notebook not found: {notebook_id}")
        nb = self.notebooks[notebook_id]
        for key in ["name", "description", "topics", "url", "source_count"]:
            if key in kwargs and kwargs[key] is not None:
                nb[key] = kwargs[key]
        nb["updated_at"] = datetime.now().isoformat()
        self._save_library()
        return nb

    def get_notebook(self, notebook_id: str) -> Optional[Dict[str, Any]]:
        return self.notebooks.get(notebook_id)

    def list_notebooks(self) -> List[Dict[str, Any]]:
        return list(self.notebooks.values())

    def find_notebooks(self, query: str) -> List[Dict[str, Any]]:
        """Fuzzy search across name, description, and topics."""
        q = query.lower()
        results = []
        for nb in self.notebooks.values():
            searchable = " ".join(
                [
                    nb["name"].lower(),
                    nb.get("description", "").lower(),
                    " ".join(nb.get("topics", [])).lower(),
                ]
            )
            if q in searchable:
                results.append(nb)
        return results

    def select_notebook(self, notebook_id: str) -> Dict[str, Any]:
        if notebook_id not in self.notebooks:
            raise ValueError(f"Notebook not found: {notebook_id}")
        self.active_notebook_id = notebook_id
        self._save_library()
        nb = self.notebooks[notebook_id]
        print(f"✅ Activated: {nb['name']}")
        return nb

    def get_active_notebook(self) -> Optional[Dict[str, Any]]:
        if self.active_notebook_id:
            return self.notebooks.get(self.active_notebook_id)
        return None

    def increment_use_count(self, notebook_id: str) -> Dict[str, Any]:
        if notebook_id not in self.notebooks:
            raise ValueError(f"Notebook not found: {notebook_id}")
        nb = self.notebooks[notebook_id]
        nb["use_count"] += 1
        nb["last_used"] = datetime.now().isoformat()
        self._save_library()
        return nb

    def exclude_notebook(self, notebook_id: str) -> bool:
        """Remove from library and prevent sync from re-adding."""
        self.remove_notebook(notebook_id)
        uuid = None
        # Try to find the UUID from the notebook's URL before removal
        for nb in self.notebooks.values():
            if nb["id"] == notebook_id:
                uuid = self._extract_notebook_id_from_url(nb.get("url", ""))
                break
        if not uuid:
            uuid = notebook_id  # Assume it's already a UUID
        if uuid not in self.excluded_ids:
            self.excluded_ids.append(uuid)
            self._save_library()
            print(f"✅ Excluded: {notebook_id} (won't be re-imported by sync)")
        return True

    def get_stats(self) -> Dict[str, Any]:
        total_notebooks = len(self.notebooks)
        total_topics = set()
        total_use_count = 0
        for nb in self.notebooks.values():
            total_topics.update(nb.get("topics", []))
            total_use_count += nb["use_count"]
        most_used = None
        if self.notebooks:
            most_used = max(self.notebooks.values(), key=lambda n: n["use_count"])
        return {
            "total_notebooks": total_notebooks,
            "total_topics": len(total_topics),
            "total_use_count": total_use_count,
            "active_notebook": self.get_active_notebook(),
            "most_used_notebook": most_used,
            "excluded_count": len(self.excluded_ids),
            "library_path": str(self.library_file),
        }

    # ------------------------------------------------------------------ #
    # Web-backed operations (browser automation)
    # ------------------------------------------------------------------ #

    def _run_browser_op(self, operation, headless=True):
        """Shared browser lifecycle for web operations."""
        from auth_manager import AuthManager
        from browser_utils import BrowserFactory
        from patchright.sync_api import sync_playwright

        auth = AuthManager()
        if not auth.is_authenticated():
            print("⚠️  Not authenticated. Run: python auth_manager.py setup")
            return None

        playwright = None
        context = None
        try:
            playwright = sync_playwright().start()
            context = BrowserFactory.launch_persistent_context(
                playwright, headless=headless
            )
            page = context.new_page()
            if not headless:
                page.set_viewport_size({"width": 1200, "height": 800})
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

    def _navigate_home(self, page) -> bool:
        """Navigate to NotebookLM homepage."""
        from config import NOTEBOOKLM_HOME_URL

        page.goto(NOTEBOOKLM_HOME_URL, wait_until="domcontentloaded")
        time.sleep(5)
        if "notebooklm.google.com" not in page.url:
            print("  ❌ Failed to navigate to NotebookLM")
            return False
        return True

    def _scrape_notebooks(self, page) -> List[Dict[str, str]]:
        """Scrape notebook list from homepage using JavaScript for reliability."""
        results = page.evaluate("""() => {
            const notebooks = [];
            const cards = document.querySelectorAll('mat-card.project-button-card');
            for (const card of cards) {
                try {
                    // Get URL from the stretched link overlay inside the card
                    const link = card.querySelector('a[href*="/notebook/"]')
                        || card.parentElement?.closest('a[href*="/notebook/"]')
                        || card.parentElement?.querySelector('a[href*="/notebook/"]');
                    if (!link) continue;
                    const href = link.getAttribute('href');
                    if (!href) continue;

                    // Get text content, filtering noise
                    const text = card.innerText;
                    const lines = text.split('\\n')
                        .map(l => l.trim())
                        .filter(l => l && l !== 'more_vert' && l !== 'public' && l !== 'add');

                    // Title: first line with 4+ chars, not a date/source line
                    let title = 'Untitled notebook';
                    for (const line of lines) {
                        // Remove emojis
                        const clean = line.replace(/[\\u{1F300}-\\u{1FAFF}\\u{2702}-\\u{27B0}]/gu, '').trim();
                        if (clean.length >= 4
                            && !clean.match(/source/i)
                            && !clean.match(/^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s/)) {
                            title = clean;
                            break;
                        }
                    }

                    // Source count
                    let sourceCount = 0;
                    for (const line of lines) {
                        const m = line.match(/(\\d+)\\s+source/);
                        if (m) { sourceCount = parseInt(m[1]); break; }
                    }

                    const fullUrl = href.startsWith('/')
                        ? 'https://notebooklm.google.com' + href : href;
                    const uuidMatch = href.match(/\\/notebook\\/([a-f0-9-]+)/);

                    notebooks.push({
                        title,
                        url: fullUrl,
                        uuid: uuidMatch ? uuidMatch[1] : '',
                        source_count: sourceCount
                    });
                } catch(e) { continue; }
            }
            return notebooks;
        }""")
        return results

    def sync_from_web(self, library_only=False, force=False, headless=True):
        """Sync notebooks from NotebookLM web UI into local library."""

        def _op(page):
            if not self._navigate_home(page):
                return None

            print("  🔄 Scraping notebooks from web...")
            web_notebooks = self._scrape_notebooks(page)
            print(f"  Found {len(web_notebooks)} notebooks on web")

            added, updated, skipped = 0, 0, 0
            for wnb in web_notebooks:
                uuid = wnb["uuid"]

                # Check exclusions
                if not force and uuid in self.excluded_ids:
                    skipped += 1
                    continue

                # In library-only mode, skip notebooks not already imported
                if library_only:
                    found = any(
                        self._extract_notebook_id_from_url(nb.get("url", "")) == uuid
                        for nb in self.notebooks.values()
                    )
                    if not found:
                        skipped += 1
                        continue

                # Find existing by URL match
                existing_id = None
                for nid, nb in self.notebooks.items():
                    if self._extract_notebook_id_from_url(nb.get("url", "")) == uuid:
                        existing_id = nid
                        break

                if existing_id:
                    self.update_notebook(
                        existing_id,
                        name=wnb["title"],
                        source_count=wnb["source_count"],
                        url=wnb["url"],
                    )
                    updated += 1
                else:
                    self.add_notebook(
                        url=wnb["url"],
                        name=wnb["title"],
                        source_count=wnb["source_count"],
                    )
                    added += 1

            self._save_library()
            print(
                f"  ✅ Sync complete: {added} added, {updated} updated, {skipped} skipped"
            )
            return {"added": added, "updated": updated, "skipped": skipped}

        return self._run_browser_op(_op, headless=headless)

    def import_notebook(self, url: str, headless=True) -> Optional[Dict[str, Any]]:
        """Import a single notebook by URL — auto-discovers title and source count."""

        def _op(page):
            print(f"  🌐 Opening notebook...")
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_url(
                re.compile(r"^https://notebooklm\.google\.com/"), timeout=15000
            )
            time.sleep(4)

            # Extract title from the page
            title = "Untitled notebook"
            # Try the notebook title in the header
            for sel in [
                "input.title-input",
                "[class*='notebook-title']",
                "[class*='project-title']",
            ]:
                el = page.query_selector(sel)
                if el:
                    val = el.evaluate("e => e.value || e.innerText || ''").strip()
                    if val:
                        title = val
                        break

            # If no title found from input, try the page header text
            if title == "Untitled notebook":
                header = page.query_selector("h1, [class*='heading']")
                if header:
                    text = header.inner_text().strip()
                    if text and "Create Audio" not in text:
                        title = text

            # Count sources
            from config import SOURCE_ITEM_SELECTOR

            # Click Sources tab to count
            try:
                sources_tab = page.get_by_text("Sources", exact=True).first
                sources_tab.click()
                time.sleep(2)
                source_count = len(
                    page.query_selector_all(SOURCE_ITEM_SELECTOR)
                )
            except:
                source_count = 0

            print(f"  📓 Title: {title}")
            print(f"  📎 Sources: {source_count}")

            nb = self.add_notebook(
                url=url, name=title, source_count=source_count
            )
            nb_id = nb["id"]

            # Activate it
            self.select_notebook(nb_id)
            print(f"  ✅ Imported and activated: {nb_id}")
            return nb

        return self._run_browser_op(_op, headless=headless)

    def create_notebook_web(self, title: str, headless=True) -> Optional[Dict[str, Any]]:
        """Create a new notebook on the web and add to library."""

        def _op(page):
            if not self._navigate_home(page):
                return None

            print(f"  ➕ Creating notebook: {title}")
            create_btn = page.query_selector(
                "button[aria-label='Create new notebook']"
            )
            if not create_btn:
                print("  ❌ Could not find Create button")
                return None
            create_btn.click()
            time.sleep(5)

            new_url = page.url
            print(f"  📓 URL: {new_url}")

            # Rename it if title isn't "Untitled notebook"
            if title and title != "Untitled notebook":
                # Go back to homepage to rename via menu
                if not self._navigate_home(page):
                    return None

                # Find the new untitled notebook and rename it
                from config import NOTEBOOK_CARD_SELECTOR, NOTEBOOK_MENU_SELECTOR

                cards = page.query_selector_all(NOTEBOOK_CARD_SELECTOR)
                for card in cards:
                    try:
                        text = card.inner_text()
                        href = card.evaluate(
                            "e => e.closest('a')?.getAttribute('href') || ''"
                        )
                        # Match by URL
                        uuid = self._extract_notebook_id_from_url(new_url)
                        if uuid and uuid in href:
                            menu_btn = card.query_selector(NOTEBOOK_MENU_SELECTOR)
                            if menu_btn:
                                menu_btn.click()
                                time.sleep(1)
                                edit_item = page.query_selector(
                                    "[role='menuitem']:has-text('Edit title')"
                                )
                                if edit_item:
                                    edit_item.click()
                                    time.sleep(2)
                                    from config import NOTEBOOK_TITLE_FC_SELECTOR

                                    title_input = page.locator(
                                        NOTEBOOK_TITLE_FC_SELECTOR
                                    )
                                    title_input.fill(title)
                                    time.sleep(1)
                                    page.get_by_role(
                                        "button", name="Save"
                                    ).first.click()
                                    time.sleep(2)
                                    print(f"  ✏️  Renamed to: {title}")
                            break
                    except:
                        continue

            nb = self.add_notebook(url=new_url, name=title, source_count=0)
            self.select_notebook(nb["id"])
            print(f"  ✅ Created and activated: {nb['id']}")
            return nb

        return self._run_browser_op(_op, headless=headless)

    def rename_notebook_web(
        self, notebook_id: str, new_title: str, headless=True
    ) -> bool:
        """Rename a notebook on the web and update library."""
        nb = self.get_notebook(notebook_id)
        if not nb:
            print(f"❌ Notebook not found in library: {notebook_id}")
            return False

        uuid = self._extract_notebook_id_from_url(nb.get("url", ""))
        if not uuid:
            print(f"❌ Could not extract UUID from URL: {nb.get('url')}")
            return False

        def _op(page):
            if not self._navigate_home(page):
                return False

            print(f"  ✏️  Renaming: {nb['name']} → {new_title}")

            from config import NOTEBOOK_CARD_SELECTOR, NOTEBOOK_MENU_SELECTOR

            cards = page.query_selector_all(NOTEBOOK_CARD_SELECTOR)
            for card in cards:
                try:
                    href = card.evaluate(
                        "e => e.closest('a')?.getAttribute('href') || ''"
                    )
                    if uuid in href:
                        menu_btn = card.query_selector(NOTEBOOK_MENU_SELECTOR)
                        menu_btn.click()
                        time.sleep(1)

                        edit_item = page.query_selector(
                            "[role='menuitem']:has-text('Edit title')"
                        )
                        edit_item.click()
                        time.sleep(2)

                        from config import NOTEBOOK_TITLE_FC_SELECTOR

                        title_input = page.locator(NOTEBOOK_TITLE_FC_SELECTOR)
                        title_input.fill(new_title)
                        time.sleep(1)

                        page.get_by_role("button", name="Save").first.click()
                        time.sleep(2)

                        self.update_notebook(notebook_id, name=new_title)
                        print(f"  ✅ Renamed!")
                        return True
                except:
                    continue

            print("  ❌ Notebook not found on web")
            return False

        result = self._run_browser_op(_op, headless=headless)
        return result if result else False

    def delete_notebook_web(
        self, notebook_id: str, confirm: bool = False, headless=True
    ) -> bool:
        """Delete a notebook from the web and remove from library."""
        nb = self.get_notebook(notebook_id)
        if not nb:
            print(f"❌ Notebook not found in library: {notebook_id}")
            return False

        if not confirm:
            print(f'\n⚠️  This will PERMANENTLY DELETE "{nb["name"]}"')
            print("  Run again with --confirm to proceed")
            return False

        uuid = self._extract_notebook_id_from_url(nb.get("url", ""))
        if not uuid:
            print(f"❌ Could not extract UUID from URL: {nb.get('url')}")
            return False

        def _op(page):
            if not self._navigate_home(page):
                return False

            print(f"  🗑️  Deleting: {nb['name']}")

            from config import (
                NOTEBOOK_CARD_SELECTOR,
                NOTEBOOK_MENU_SELECTOR,
                DELETE_DIALOG_SELECTOR,
            )

            cards = page.query_selector_all(NOTEBOOK_CARD_SELECTOR)
            for card in cards:
                try:
                    href = card.evaluate(
                        "e => e.closest('a')?.getAttribute('href') || ''"
                    )
                    if uuid in href:
                        menu_btn = card.query_selector(NOTEBOOK_MENU_SELECTOR)
                        menu_btn.click()
                        time.sleep(1)

                        del_item = page.query_selector(
                            "[role='menuitem']:has-text('Delete')"
                        )
                        del_item.click()
                        time.sleep(2)

                        dialog = page.query_selector(DELETE_DIALOG_SELECTOR)
                        if dialog:
                            del_btn = dialog.query_selector(
                                "button:has-text('Delete')"
                            )
                            if del_btn:
                                del_btn.click(force=True)
                                time.sleep(3)

                        self.remove_notebook(notebook_id)
                        print(f"  ✅ Deleted from web and library")
                        return True
                except:
                    continue

            print("  ❌ Notebook not found on web")
            return False

        result = self._run_browser_op(_op, headless=headless)
        return result if result else False


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #


def main():
    parser = argparse.ArgumentParser(description="Manage NotebookLM library")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # --- Local operations ---
    add_p = subparsers.add_parser("add", help="Add a notebook to library")
    add_p.add_argument("--url", required=True, help="NotebookLM URL")
    add_p.add_argument("--name", required=True, help="Display name")
    add_p.add_argument("--description", default="", help="Description")
    add_p.add_argument("--topics", help="Comma-separated topics")

    list_p = subparsers.add_parser("list", help="List all notebooks in library")
    list_p.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    find_p = subparsers.add_parser("find", help="Fuzzy search notebooks")
    find_p.add_argument("query", help="Search query")

    act_p = subparsers.add_parser("activate", help="Set active notebook")
    act_p.add_argument("--id", required=True, help="Notebook ID")

    rm_p = subparsers.add_parser("remove", help="Remove from library (local only)")
    rm_p.add_argument("--id", required=True, help="Notebook ID")

    excl_p = subparsers.add_parser("exclude", help="Remove + prevent sync re-import")
    excl_p.add_argument("--id", required=True, help="Notebook ID")

    subparsers.add_parser("stats", help="Show library statistics")

    # --- Web-backed operations ---
    sync_p = subparsers.add_parser("sync", help="Sync notebooks from web")
    sync_p.add_argument(
        "--library-only", action="store_true", help="Only refresh existing entries"
    )
    sync_p.add_argument(
        "--force", action="store_true", help="Ignore exclusion list"
    )
    sync_p.add_argument("--show-browser", action="store_true")

    imp_p = subparsers.add_parser("import", help="Import notebook by URL")
    imp_p.add_argument("--url", required=True, help="NotebookLM URL")
    imp_p.add_argument("--show-browser", action="store_true")

    create_p = subparsers.add_parser("create", help="Create new notebook on web")
    create_p.add_argument("--title", required=True, help="Notebook title")
    create_p.add_argument("--show-browser", action="store_true")

    ren_p = subparsers.add_parser("rename", help="Rename notebook on web")
    ren_p.add_argument("--id", required=True, help="Notebook ID")
    ren_p.add_argument("--title", required=True, help="New title")
    ren_p.add_argument("--show-browser", action="store_true")

    del_p = subparsers.add_parser("delete", help="Delete notebook from web")
    del_p.add_argument("--id", required=True, help="Notebook ID")
    del_p.add_argument(
        "--confirm", action="store_true", help="Confirm permanent deletion"
    )
    del_p.add_argument("--show-browser", action="store_true")

    args = parser.parse_args()
    library = NotebookLibrary()

    if args.command == "add":
        topics = [t.strip() for t in args.topics.split(",")] if args.topics else []
        nb = library.add_notebook(
            url=args.url,
            name=args.name,
            description=args.description,
            topics=topics,
        )
        print(f"✅ Added: {nb['id']}")
        print(json.dumps(nb, indent=2))

    elif args.command == "list":
        notebooks = library.list_notebooks()
        if args.format == "json":
            print(json.dumps(notebooks, indent=2))
        elif notebooks:
            print(f"\n📚 Notebook Library ({len(notebooks)}):")
            for nb in notebooks:
                active = " ★" if nb["id"] == library.active_notebook_id else ""
                sources = nb.get("source_count", "?")
                print(f"\n  📓 {nb['name']}{active}")
                print(f"     ID: {nb['id']}")
                print(f"     Sources: {sources}")
                if nb.get("description"):
                    print(f"     {nb['description'][:80]}")
        else:
            print("📚 Library empty. Run: notebook_manager.py sync")

    elif args.command == "find":
        results = library.find_notebooks(args.query)
        if results:
            print(f"\n🔍 Found {len(results)} notebooks:")
            for nb in results:
                active = " ★" if nb["id"] == library.active_notebook_id else ""
                print(f"  📓 {nb['name']}{active}  ({nb['id']})")
        else:
            print(f"🔍 No notebooks match: {args.query}")

    elif args.command == "activate":
        nb = library.select_notebook(args.id)
        print(f"Now using: {nb['name']}")

    elif args.command == "remove":
        library.remove_notebook(args.id)

    elif args.command == "exclude":
        library.exclude_notebook(args.id)

    elif args.command == "stats":
        stats = library.get_stats()
        print("\n📊 Library Statistics:")
        print(f"  Notebooks: {stats['total_notebooks']}")
        print(f"  Topics: {stats['total_topics']}")
        print(f"  Uses: {stats['total_use_count']}")
        print(f"  Excluded: {stats['excluded_count']}")
        if stats["active_notebook"]:
            print(f"  Active: {stats['active_notebook']['name']}")
        if stats["most_used_notebook"]:
            print(
                f"  Most used: {stats['most_used_notebook']['name']} ({stats['most_used_notebook']['use_count']})"
            )

    elif args.command == "sync":
        headless = not getattr(args, "show_browser", False)
        library.sync_from_web(
            library_only=args.library_only,
            force=args.force,
            headless=headless,
        )

    elif args.command == "import":
        headless = not getattr(args, "show_browser", False)
        library.import_notebook(args.url, headless=headless)

    elif args.command == "create":
        headless = not getattr(args, "show_browser", False)
        library.create_notebook_web(args.title, headless=headless)

    elif args.command == "rename":
        headless = not getattr(args, "show_browser", False)
        library.rename_notebook_web(args.id, args.title, headless=headless)

    elif args.command == "delete":
        headless = not getattr(args, "show_browser", False)
        library.delete_notebook_web(
            args.id, confirm=args.confirm, headless=headless
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
