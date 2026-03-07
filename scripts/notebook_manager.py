#!/usr/bin/env python3
"""
Notebook Library Management for NotebookLM
Manages manual and remote-discovered NotebookLM notebooks.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from patchright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from browser_utils import BrowserFactory
from config import LIBRARY_FILE, NOTEBOOKLM_GOOGLE_ACCOUNT_ENV
from notebook_navigation import explain_navigation_failure, normalize_notebooklm_url
from notebook_ui import NotebookUIError, add_source, create_notebook, discover_sources, list_remote_notebooks


class NotebookLibrary:
    """Manages manual and remote-discovered NotebookLM notebooks."""

    def __init__(self):
        self.library_file = LIBRARY_FILE
        self.library_file.parent.mkdir(parents=True, exist_ok=True)
        self.notebooks: Dict[str, Dict[str, Any]] = {}
        self.remote_notebooks: Dict[str, Dict[str, Any]] = {}
        self.active_notebook_id: Optional[str] = None
        self._load_library()

    def _load_library(self):
        if self.library_file.exists():
            try:
                with open(self.library_file, 'r') as handle:
                    data = json.load(handle)
                self.notebooks = data.get('notebooks', {})
                self.remote_notebooks = data.get('remote_notebooks', {})
                self.active_notebook_id = data.get('active_notebook_id')
                print(
                    f"📚 Loaded library with {len(self.notebooks)} manual notebooks and "
                    f"{len(self.remote_notebooks)} remote notebooks"
                )
            except Exception as error:
                print(f"⚠️ Error loading library: {error}")
                self.notebooks = {}
                self.remote_notebooks = {}
                self.active_notebook_id = None
        else:
            self._save_library()

    def _save_library(self):
        data = {
            'notebooks': self.notebooks,
            'remote_notebooks': self.remote_notebooks,
            'active_notebook_id': self.active_notebook_id,
            'updated_at': datetime.now().isoformat(),
        }
        with open(self.library_file, 'w') as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)

    def add_notebook(
        self,
        url: str,
        name: str,
        description: str,
        topics: List[str],
        content_types: Optional[List[str]] = None,
        use_cases: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        notebook_id = _slugify_name(name)
        if notebook_id in self.notebooks:
            raise ValueError(f"Notebook with ID '{notebook_id}' already exists")

        now = datetime.now().isoformat()
        notebook = {
            'id': notebook_id,
            'url': normalize_notebooklm_url(url),
            'name': name,
            'description': description,
            'topics': topics,
            'content_types': content_types or [],
            'use_cases': use_cases or [],
            'tags': tags or [],
            'origin': 'manual',
            'created_at': now,
            'updated_at': now,
            'use_count': 0,
            'last_used': None,
        }
        self.notebooks[notebook_id] = notebook
        if len(self.notebooks) == 1 and not self.active_notebook_id:
            self.active_notebook_id = notebook_id
        self._save_library()
        print(f"✅ Added notebook: {name} ({notebook_id})")
        return notebook

    def remove_notebook(self, notebook_id: str) -> bool:
        if notebook_id in self.notebooks:
            del self.notebooks[notebook_id]
            if self.active_notebook_id == notebook_id:
                self.active_notebook_id = next(iter(self.notebooks.keys()), None)
            self._save_library()
            print(f"✅ Removed notebook: {notebook_id}")
            return True
        print(f"⚠️ Notebook not found: {notebook_id}")
        return False

    def update_notebook(
        self,
        notebook_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        topics: Optional[List[str]] = None,
        content_types: Optional[List[str]] = None,
        use_cases: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if notebook_id not in self.notebooks:
            raise ValueError(f"Notebook not found: {notebook_id}")

        notebook = self.notebooks[notebook_id]
        if name is not None:
            notebook['name'] = name
        if description is not None:
            notebook['description'] = description
        if topics is not None:
            notebook['topics'] = topics
        if content_types is not None:
            notebook['content_types'] = content_types
        if use_cases is not None:
            notebook['use_cases'] = use_cases
        if tags is not None:
            notebook['tags'] = tags
        if url is not None:
            notebook['url'] = normalize_notebooklm_url(url)
        notebook['updated_at'] = datetime.now().isoformat()
        self._save_library()
        print(f"✅ Updated notebook: {notebook['name']}")
        return notebook

    def get_notebook(self, notebook_id: str) -> Optional[Dict[str, Any]]:
        return self.notebooks.get(notebook_id)

    def get_remote_notebook(self, notebook_id: str) -> Optional[Dict[str, Any]]:
        return self.remote_notebooks.get(notebook_id)

    def list_notebooks(self) -> List[Dict[str, Any]]:
        return list(self.notebooks.values())

    def list_remote(self) -> List[Dict[str, Any]]:
        return list(self.remote_notebooks.values())

    def search_notebooks(self, query: str) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        results = []
        for notebook in self.notebooks.values():
            searchable = [
                notebook['name'].lower(),
                notebook['description'].lower(),
                ' '.join(notebook['topics']).lower(),
                ' '.join(notebook['tags']).lower(),
                ' '.join(notebook.get('use_cases', [])).lower(),
            ]
            if any(query_lower in field for field in searchable):
                results.append(notebook)
        return results

    def select_notebook(self, notebook_id: str) -> Dict[str, Any]:
        if notebook_id not in self.notebooks:
            raise ValueError(f"Notebook not found: {notebook_id}")
        self.active_notebook_id = notebook_id
        self._save_library()
        notebook = self.notebooks[notebook_id]
        print(f"✅ Activated notebook: {notebook['name']}")
        return notebook

    def get_active_notebook(self) -> Optional[Dict[str, Any]]:
        if self.active_notebook_id:
            return self.notebooks.get(self.active_notebook_id)
        return None

    def increment_use_count(self, notebook_id: str) -> Dict[str, Any]:
        if notebook_id not in self.notebooks:
            raise ValueError(f"Notebook not found: {notebook_id}")
        notebook = self.notebooks[notebook_id]
        notebook['use_count'] += 1
        notebook['last_used'] = datetime.now().isoformat()
        self._save_library()
        return notebook

    def sync_remote_notebooks(self, notebooks: List[Dict[str, Any]]) -> Dict[str, Any]:
        synced_at = datetime.now().isoformat()
        previous_ids = set(self.remote_notebooks.keys())
        incoming_ids = set()
        for notebook in notebooks:
            notebook_id = notebook['id']
            incoming_ids.add(notebook_id)
            previous = self.remote_notebooks.get(notebook_id, {})
            created_at = previous.get('created_at') or synced_at
            merged = {
                **previous,
                **notebook,
                'id': notebook_id,
                'origin': 'remote-sync',
                'created_at': created_at,
                'last_synced_at': synced_at,
            }
            self.remote_notebooks[notebook_id] = merged

        removed_ids = sorted(previous_ids - incoming_ids)
        for notebook_id in removed_ids:
            self.remote_notebooks[notebook_id]['remote_missing_at'] = synced_at
            self.remote_notebooks[notebook_id]['remote_present'] = False
        for notebook_id in incoming_ids:
            self.remote_notebooks[notebook_id]['remote_present'] = True

        self._save_library()
        return {
            'status': 'ok',
            'synced_at': synced_at,
            'count': len(notebooks),
            'new_ids': sorted(incoming_ids - previous_ids),
            'removed_ids': removed_ids,
            'notebooks': notebooks,
        }

    def record_remote_notebook(self, notebook: Dict[str, Any], *, source: str = 'created') -> Dict[str, Any]:
        notebook_id = notebook['id']
        now = datetime.now().isoformat()
        previous = self.remote_notebooks.get(notebook_id, {})
        merged = {
            **previous,
            **notebook,
            'id': notebook_id,
            'origin': source,
            'created_at': previous.get('created_at') or now,
            'last_synced_at': now,
            'remote_present': True,
        }
        self.remote_notebooks[notebook_id] = merged
        self._save_library()
        return merged

    def resolve_notebook_url(self, notebook_id: Optional[str], notebook_url: Optional[str]) -> Optional[str]:
        if notebook_url:
            return normalize_notebooklm_url(notebook_url)
        if notebook_id:
            manual = self.get_notebook(notebook_id)
            if manual:
                return manual['url']
            remote = self.get_remote_notebook(notebook_id)
            if remote:
                return remote['url']
        active = self.get_active_notebook()
        if active:
            return active['url']
        return None

    def get_stats(self) -> Dict[str, Any]:
        total_topics = set()
        total_use_count = 0
        for notebook in self.notebooks.values():
            total_topics.update(notebook['topics'])
            total_use_count += notebook['use_count']

        most_used = None
        if self.notebooks:
            most_used = max(self.notebooks.values(), key=lambda item: item['use_count'])

        return {
            'total_notebooks': len(self.notebooks),
            'total_remote_notebooks': len(self.remote_notebooks),
            'total_topics': len(total_topics),
            'total_use_count': total_use_count,
            'active_notebook': self.get_active_notebook(),
            'most_used_notebook': most_used,
            'library_path': str(self.library_file),
        }



def _slugify_name(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return slug or 'notebook'



def _split_csv(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [item.strip() for item in value.split(',') if item.strip()]



def _remote_entry_from_created(result: Dict[str, Any]) -> Dict[str, Any]:
    notebook_url = normalize_notebooklm_url(result['url'])
    notebook_id = notebook_url.rstrip('/').split('/notebook/')[-1].split('?', 1)[0]
    return {
        'id': notebook_id,
        'url': notebook_url,
        'title': result['title'],
        'subtitle': None,
        'visible_description': None,
        'visible_updated_at': None,
    }



def _print_notebooks(notebooks: List[Dict[str, Any]], *, active_id: Optional[str] = None, remote: bool = False):
    if not notebooks:
        if remote:
            print("📚 No remote notebooks recorded")
        else:
            print("📚 Library is empty. Add notebooks with: notebook_manager.py add")
        return

    label = "Remote notebooks" if remote else "Notebook Library"
    print(f"\n📚 {label}:")
    for notebook in notebooks:
        notebook_id = notebook.get('id')
        name = notebook.get('name') or notebook.get('title')
        active = " [ACTIVE]" if notebook_id == active_id else ""
        print(f"\n  📓 {name}{active}")
        print(f"     ID: {notebook_id}")
        print(f"     URL: {notebook.get('url')}")
        subtitle = notebook.get('subtitle') or notebook.get('visible_updated_at')
        if subtitle:
            print(f"     Summary: {subtitle}")
        description = notebook.get('description') or notebook.get('visible_description')
        if description:
            print(f"     Description: {description}")
        if not remote:
            print(f"     Topics: {', '.join(notebook.get('topics', []))}")
            print(f"     Uses: {notebook.get('use_count', 0)}")



def _run_browser_task(headless: bool, task):
    playwright = None
    context = None
    try:
        playwright = sync_playwright().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
        page = context.new_page()
        return task(page)
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



def _handle_ui_error(error: NotebookUIError, preferred_email: Optional[str]) -> int:
    details = error.details or {}
    if details.get('status'):
        for line in explain_navigation_failure(details, preferred_email=preferred_email):
            print(line)
    else:
        print(f"❌ {error}")
    if details.get('body_excerpt'):
        print("     Body excerpt:")
        for line in details['body_excerpt'].splitlines()[:12]:
            print(f"       {line}")
    return 1



def main():
    parser = argparse.ArgumentParser(description='Manage NotebookLM library and remote notebooks')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    add_parser = subparsers.add_parser('add', help='Add a notebook to the manual library')
    add_parser.add_argument('--url', required=True, help='NotebookLM URL')
    add_parser.add_argument('--name', required=True, help='Display name')
    add_parser.add_argument('--description', required=True, help='Description')
    add_parser.add_argument('--topics', required=True, help='Comma-separated topics')
    add_parser.add_argument('--use-cases', help='Comma-separated use cases')
    add_parser.add_argument('--tags', help='Comma-separated tags')

    subparsers.add_parser('list', help='List manual notebooks')

    search_parser = subparsers.add_parser('search', help='Search manual notebooks')
    search_parser.add_argument('--query', required=True, help='Search query')

    activate_parser = subparsers.add_parser('activate', help='Set active manual notebook')
    activate_parser.add_argument('--id', required=True, help='Notebook ID')

    remove_parser = subparsers.add_parser('remove', help='Remove a manual notebook')
    remove_parser.add_argument('--id', required=True, help='Notebook ID')

    subparsers.add_parser('stats', help='Show library statistics')
    subparsers.add_parser('list-remote', help='Fetch and print accessible remote notebooks without saving')

    sync_parser = subparsers.add_parser('sync-remote', help='Fetch remote notebooks and save them into library.json')
    sync_parser.add_argument('--show-browser', action='store_true', help='Show browser during sync')

    create_parser = subparsers.add_parser('create', help='Create a new NotebookLM notebook')
    create_parser.add_argument('--name', help='Notebook title to set after creation')
    create_parser.add_argument('--show-browser', action='store_true', help='Show browser during creation')

    add_source_parser = subparsers.add_parser('add-source', help='Add a source to a notebook')
    add_source_parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    add_source_parser.add_argument('--notebook-id', help='Notebook ID from manual or remote library')
    add_source_group = add_source_parser.add_mutually_exclusive_group(required=True)
    add_source_group.add_argument('--source-url', help='Source URL to import')
    add_source_group.add_argument('--file', help='Local file path to upload')
    add_source_parser.add_argument('--show-browser', action='store_true', help='Show browser during source import')

    discover_parser = subparsers.add_parser('discover-sources', help='Use Fast Research or Deep Research to discover sources in a notebook')
    discover_parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    discover_parser.add_argument('--notebook-id', help='Notebook ID from manual or remote library')
    discover_parser.add_argument('--query', required=True, help='Research query to run inside NotebookLM Sources')
    discover_parser.add_argument('--mode', choices=['fast-research', 'deep-research'], default='fast-research', help='Research mode')
    discover_parser.add_argument('--no-import', action='store_true', help='Do not auto-import discovered sources')
    discover_parser.add_argument('--show-browser', action='store_true', help='Show browser during research')

    args = parser.parse_args()
    library = NotebookLibrary()

    if args.command == 'add':
        notebook = library.add_notebook(
            url=args.url,
            name=args.name,
            description=args.description,
            topics=[item.strip() for item in args.topics.split(',') if item.strip()],
            use_cases=_split_csv(args.use_cases),
            tags=_split_csv(args.tags),
        )
        print(json.dumps(notebook, indent=2, ensure_ascii=False))
        return 0

    if args.command == 'list':
        _print_notebooks(library.list_notebooks(), active_id=library.active_notebook_id)
        return 0

    if args.command == 'search':
        results = library.search_notebooks(args.query)
        if results:
            _print_notebooks(results, active_id=library.active_notebook_id)
        else:
            print(f"🔍 No notebooks found for: {args.query}")
        return 0

    if args.command == 'activate':
        notebook = library.select_notebook(args.id)
        print(f"Now using: {notebook['name']}")
        return 0

    if args.command == 'remove':
        if library.remove_notebook(args.id):
            print("Notebook removed from library")
            return 0
        return 1

    if args.command == 'stats':
        stats = library.get_stats()
        print("\n📊 Library Statistics:")
        print(f"  Manual notebooks: {stats['total_notebooks']}")
        print(f"  Remote notebooks: {stats['total_remote_notebooks']}")
        print(f"  Total topics: {stats['total_topics']}")
        print(f"  Total uses: {stats['total_use_count']}")
        if stats['active_notebook']:
            print(f"  Active: {stats['active_notebook']['name']}")
        if stats['most_used_notebook']:
            print(
                f"  Most used: {stats['most_used_notebook']['name']} "
                f"({stats['most_used_notebook']['use_count']} uses)"
            )
        print(f"  Library path: {stats['library_path']}")
        return 0

    auth = AuthManager()
    if not auth.is_authenticated():
        print("❌ NotebookLM authentication is missing. Run: python scripts/run.py auth_manager.py setup")
        return 1

    auth_info = auth.get_auth_info()
    preferred_email = os.getenv(NOTEBOOKLM_GOOGLE_ACCOUNT_ENV) or auth_info.get('google_account_email')

    if args.command == 'list-remote':
        try:
            notebooks = _run_browser_task(True, lambda page: list_remote_notebooks(page, preferred_email=preferred_email))
            _print_notebooks(notebooks, remote=True)
            print(json.dumps(notebooks, indent=2, ensure_ascii=False))
            return 0
        except NotebookUIError as error:
            return _handle_ui_error(error, preferred_email)

    if args.command == 'sync-remote':
        try:
            notebooks = _run_browser_task(not args.show_browser, lambda page: list_remote_notebooks(page, preferred_email=preferred_email))
            result = library.sync_remote_notebooks(notebooks)
            print(f"✅ Synced {result['count']} remote notebooks")
            if result['new_ids']:
                print(f"   New IDs: {', '.join(result['new_ids'])}")
            if result['removed_ids']:
                print(f"   Missing remotely now: {', '.join(result['removed_ids'])}")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        except NotebookUIError as error:
            return _handle_ui_error(error, preferred_email)

    if args.command == 'create':
        try:
            result = _run_browser_task(
                not args.show_browser,
                lambda page: create_notebook(page, name=args.name, preferred_email=preferred_email),
            )
            library.record_remote_notebook(_remote_entry_from_created(result), source='created')
            print("✅ Created notebook")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        except NotebookUIError as error:
            return _handle_ui_error(error, preferred_email)

    if args.command == 'add-source':
        notebook_url = library.resolve_notebook_url(args.notebook_id, args.notebook_url)
        if not notebook_url:
            print("❌ Notebook URL not resolved. Pass --notebook-url or --notebook-id, or set an active notebook.")
            return 1
        try:
            result = _run_browser_task(
                not args.show_browser,
                lambda page: add_source(
                    page,
                    notebook_url,
                    source_url=args.source_url,
                    file_path=args.file,
                    preferred_email=preferred_email,
                ),
            )
            print("✅ Added source")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        except NotebookUIError as error:
            return _handle_ui_error(error, preferred_email)

    if args.command == 'discover-sources':
        notebook_url = library.resolve_notebook_url(args.notebook_id, args.notebook_url)
        if not notebook_url:
            print("❌ Notebook URL not resolved. Pass --notebook-url or --notebook-id, or set an active notebook.")
            return 1
        try:
            result = _run_browser_task(
                not args.show_browser,
                lambda page: discover_sources(
                    page,
                    notebook_url,
                    query=args.query,
                    mode=args.mode,
                    auto_import=not args.no_import,
                    preferred_email=preferred_email,
                    progress_callback=lambda message: print(f"  ⏳ {message}"),
                ),
            )
            print("✅ Discover sources completed")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        except NotebookUIError as error:
            return _handle_ui_error(error, preferred_email)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
