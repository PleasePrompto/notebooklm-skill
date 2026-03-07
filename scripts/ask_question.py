#!/usr/bin/env python3
"""
Simple NotebookLM Question Interface
Based on MCP server implementation - simplified without sessions

Implements hybrid auth approach:
- Persistent browser profile (user_data_dir) for fingerprint consistency
- Manual cookie injection from state.json for session cookies (Playwright bug workaround)
See: https://github.com/microsoft/playwright/issues/36139
"""

import argparse
import os
import sys
import time
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import NOTEBOOKLM_GOOGLE_ACCOUNT_ENV, QUERY_INPUT_SELECTORS, RESPONSE_SELECTORS
from browser_utils import BrowserFactory, StealthUtils
from notebook_navigation import explain_navigation_failure, open_notebook_page
from session_manager import ask_via_session_manager, SessionManagerError


FOLLOW_UP_REMINDER = (
    "\n\nEXTREMELY IMPORTANT: Is that ALL you need to know? "
    "You can always ask another question! Think about it carefully: "
    "before you reply to the user, review their original request and this answer. "
    "If anything is still unclear or missing, ask me another comprehensive question "
    "that includes all necessary context (since each question opens a new browser session)."
)


def ask_notebooklm(question: str, notebook_url: str, headless: bool = True) -> str:
    """
    Ask a question to NotebookLM

    Args:
        question: Question to ask
        notebook_url: NotebookLM notebook URL
        headless: Run browser in headless mode

    Returns:
        Answer text from NotebookLM
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("⚠️ Not authenticated. Run: python auth_manager.py setup")
        return None

    print(f"💬 Asking: {question}")
    print(f"📚 Notebook: {notebook_url}")

    playwright = None
    context = None

    try:
        playwright = sync_playwright().start()
        context = BrowserFactory.launch_persistent_context(
            playwright,
            headless=headless,
        )

        page = context.new_page()
        print("  🌐 Opening notebook...")
        auth_info = auth.get_auth_info()
        preferred_email = os.getenv(NOTEBOOKLM_GOOGLE_ACCOUNT_ENV) or auth_info.get("google_account_email")
        navigation = open_notebook_page(
            page,
            notebook_url,
            preferred_email=preferred_email,
        )

        if navigation["status"] != "ok":
            for line in explain_navigation_failure(navigation, preferred_email=preferred_email):
                print(line)
            if navigation["status"] == "multiple-accounts":
                print(f"     Set {NOTEBOOKLM_GOOGLE_ACCOUNT_ENV}=you@example.com and retry")
            return None

        print("  ⏳ Waiting for query input...")
        query_element = None
        input_selector = None

        for selector in QUERY_INPUT_SELECTORS:
            try:
                query_element = page.wait_for_selector(selector, timeout=10000, state="visible")
                if query_element:
                    input_selector = selector
                    print(f"  ✓ Found input: {selector}")
                    break
            except Exception:
                continue

        if not query_element or not input_selector:
            print("  ❌ Could not find query input")
            return None

        print("  ⏳ Typing question...")
        StealthUtils.human_type(page, input_selector, question)

        print("  📤 Submitting...")
        page.keyboard.press("Enter")
        StealthUtils.random_delay(500, 1500)

        print("  ⏳ Waiting for answer...")
        answer = None
        stable_count = 0
        last_text = None
        deadline = time.time() + 120

        while time.time() < deadline:
            try:
                thinking_element = page.query_selector("div.thinking-message")
                if thinking_element and thinking_element.is_visible():
                    time.sleep(1)
                    continue
            except Exception:
                pass

            for selector in RESPONSE_SELECTORS:
                try:
                    elements = page.query_selector_all(selector)
                    if not elements:
                        continue

                    latest = elements[-1]
                    text = latest.inner_text().strip()
                    if not text:
                        continue

                    if text == last_text:
                        stable_count += 1
                        if stable_count >= 3:
                            answer = text
                            break
                    else:
                        stable_count = 0
                        last_text = text
                except Exception:
                    continue

            if answer:
                break

            time.sleep(1)

        if not answer:
            print("  ❌ Timeout waiting for answer")
            return None

        print("  ✅ Got answer!")
        return answer + FOLLOW_UP_REMINDER

    except Exception as error:
        print(f"  ❌ Error: {error}")
        import traceback
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
    parser = argparse.ArgumentParser(description="Ask NotebookLM a question")

    parser.add_argument("--question", required=True, help="Question to ask")
    parser.add_argument("--notebook-url", help="NotebookLM notebook URL")
    parser.add_argument("--notebook-id", help="Notebook ID from library")
    parser.add_argument("--session-id", help="Persistent session ID managed by session_manager.py")
    parser.add_argument("--show-browser", action="store_true", help="Show browser")

    args = parser.parse_args()

    if args.session_id:
        try:
            result = ask_via_session_manager(args.session_id, args.question)
        except SessionManagerError as error:
            print(f"❌ {error}")
            return 1

        print("\n" + "=" * 60)
        print(f"Session: {result['session_id']}")
        print(f"Question: {result['question']}")
        print("=" * 60)
        print()
        print(result["answer"])
        print()
        print("=" * 60)
        return 0

    notebook_url = args.notebook_url

    if not notebook_url and args.notebook_id:
        library = NotebookLibrary()
        notebook = library.get_notebook(args.notebook_id) or library.get_remote_notebook(args.notebook_id)
        if notebook:
            notebook_url = notebook["url"]
        else:
            print(f"❌ Notebook '{args.notebook_id}' not found")
            return 1

    if not notebook_url:
        library = NotebookLibrary()
        active = library.get_active_notebook()
        if active:
            notebook_url = active["url"]
            print(f"📚 Using active notebook: {active['name']}")
        else:
            notebooks = library.list_notebooks()
            if notebooks:
                print("\n📚 Available notebooks:")
                for notebook in notebooks:
                    mark = " [ACTIVE]" if notebook.get("id") == library.active_notebook_id else ""
                    print(f"  {notebook['id']}: {notebook['name']}{mark}")
                print("\nSpecify with --notebook-id or set active:")
                print("python scripts/run.py notebook_manager.py activate --id ID")
            else:
                print("❌ No notebooks in library. Add one first:")
                print("python scripts/run.py notebook_manager.py add --url URL --name NAME --description DESC --topics TOPICS")
            return 1

    answer = ask_notebooklm(
        question=args.question,
        notebook_url=notebook_url,
        headless=not args.show_browser,
    )

    if answer:
        print("\n" + "=" * 60)
        print(f"Question: {args.question}")
        print("=" * 60)
        print()
        print(answer)
        print()
        print("=" * 60)
        return 0

    print("\n❌ Failed to get answer")
    return 1


if __name__ == "__main__":
    sys.exit(main())
