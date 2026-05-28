#!/usr/bin/env python3
"""
Simple NotebookLM Question Interface
Based on MCP server implementation - simplified without sessions

Auth approach:
- Persistent browser profile (user_data_dir) for Google auth state
- Manual cookie injection from state.json for session cookies (Playwright bug workaround)
  See: https://github.com/microsoft/playwright/issues/36139

Stale-cache fix:
- Navigate to notebooklm.google.com root first and wipe IndexedDB/localStorage.
  NotebookLM caches the full conversation client-side; without this step,
  every run reloads the accumulated history and the answer-detection loop
  sees old messages as "already answered".
"""

import argparse
import sys
import time
import re
from pathlib import Path

from patchright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import QUERY_INPUT_SELECTORS, RESPONSE_SELECTORS
from browser_utils import BrowserFactory, StealthUtils


FOLLOW_UP_REMINDER = (
    "\n\nEXTREMELY IMPORTANT: Is that ALL you need to know? "
    "You can always ask another question! Think about it carefully: "
    "before you reply to the user, review their original request and this answer. "
    "If anything is still unclear or missing, ask me another comprehensive question "
    "that includes all necessary context (since each question opens a new browser session)."
)


def ask_notebooklm(question: str, notebook_url: str, headless: bool = True) -> str:
    """
    Ask a question to NotebookLM and return the answer text.

    Args:
        question: Question to ask
        notebook_url: NotebookLM notebook URL
        headless: Run browser in headless mode

    Returns:
        Answer text from NotebookLM, or None on failure
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
            headless=headless
        )

        page = context.new_page()

        # Wipe IndexedDB/localStorage before loading the notebook.
        # NotebookLM persists the full conversation in the browser; clearing it
        # ensures previous-run messages don't contaminate the response detector.
        try:
            page.goto("https://notebooklm.google.com/", wait_until="domcontentloaded", timeout=15000)
            page.evaluate("""async () => {
                try { localStorage.clear(); } catch(e) {}
                try { sessionStorage.clear(); } catch(e) {}
                try {
                    const dbs = await indexedDB.databases();
                    await Promise.all(dbs.map(d => new Promise((res, rej) => {
                        const req = indexedDB.deleteDatabase(d.name);
                        req.onsuccess = res; req.onerror = rej;
                    })));
                } catch(e) {}
            }""")
            print("  🧹 Cleared local storage / IndexedDB")
        except Exception as e:
            print(f"  ⚠️  Storage clear skipped ({e})")

        print("  🌐 Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded")
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=10000)

        print("  ⏳ Waiting for query input...")
        query_element = None
        for selector in QUERY_INPUT_SELECTORS:
            try:
                query_element = page.wait_for_selector(selector, timeout=10000, state="visible")
                if query_element:
                    print(f"  ✓ Found input: {selector}")
                    break
            except:
                continue

        if not query_element:
            print("  ❌ Could not find query input")
            return None

        print("  ⏳ Typing question...")
        input_selector = QUERY_INPUT_SELECTORS[0]
        # JS focus avoids click being blocked by any lingering overlay backdrop
        page.evaluate(f"document.querySelector('{input_selector}')?.focus()")
        StealthUtils.human_type(page, input_selector, question)

        # After clearing IndexedDB the page starts with 0 messages, so any
        # response that appears is the answer to our question.
        previous_count = 0
        previous_answer = None

        print("  📤 Submitting...")
        page.keyboard.press("Enter")

        # Wait for textarea to clear — reliable confirmation that the question
        # was accepted by NotebookLM before we start polling for the answer.
        try:
            page.wait_for_function(
                "() => { const el = document.querySelector('textarea.query-box-input'); "
                "return el && el.value.trim() === ''; }",
                timeout=15000
            )
        except:
            pass

        print("  ⏳ Waiting for answer...")

        answer = None
        stable_count = 0
        last_candidate = None
        deadline = time.time() + 120

        while time.time() < deadline:
            for selector in RESPONSE_SELECTORS:
                try:
                    elements = page.query_selector_all(selector)
                    if not elements:
                        continue

                    text  = elements[-1].inner_text().strip()
                    count = len(elements)

                    # Accept the response once a new or changed message appears
                    # and stays stable across 3 consecutive polls (~1.5 s).
                    is_new_response = (count > previous_count) or (text != previous_answer)

                    if text and is_new_response:
                        if text == last_candidate:
                            stable_count += 1
                            if stable_count >= 3:
                                answer = text
                                break
                        else:
                            stable_count = 1
                            last_candidate = text
                    break  # use only the first selector that returns elements
                except:
                    continue

            if answer:
                break

            time.sleep(0.5)

        if not answer:
            print("  ❌ Timeout waiting for answer")
            return None

        print("  ✅ Got answer!")
        return answer + FOLLOW_UP_REMINDER

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


def main():
    parser = argparse.ArgumentParser(description='Ask NotebookLM a question')
    parser.add_argument('--question', required=True, help='Question to ask')
    parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    parser.add_argument('--notebook-id', help='Notebook ID from library')
    parser.add_argument('--show-browser', action='store_true', help='Show browser')
    args = parser.parse_args()

    notebook_url = args.notebook_url

    if not notebook_url and args.notebook_id:
        library = NotebookLibrary()
        notebook = library.get_notebook(args.notebook_id)
        if notebook:
            notebook_url = notebook['url']
        else:
            print(f"❌ Notebook '{args.notebook_id}' not found")
            return 1

    if not notebook_url:
        library = NotebookLibrary()
        active = library.get_active_notebook()
        if active:
            notebook_url = active['url']
            print(f"📚 Using active notebook: {active['name']}")
        else:
            notebooks = library.list_notebooks()
            if notebooks:
                print("\n📚 Available notebooks:")
                for nb in notebooks:
                    mark = " [ACTIVE]" if nb.get('id') == library.active_notebook_id else ""
                    print(f"  {nb['id']}: {nb['name']}{mark}")
                print("\nSpecify with --notebook-id or set active:")
                print("python scripts/run.py notebook_manager.py activate --id ID")
            else:
                print("❌ No notebooks in library. Add one first:")
                print("python scripts/run.py notebook_manager.py add --url URL --name NAME "
                      "--description DESC --topics TOPICS")
            return 1

    answer = ask_notebooklm(
        question=args.question,
        notebook_url=notebook_url,
        headless=not args.show_browser
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
    else:
        print("\n❌ Failed to get answer")
        return 1


if __name__ == "__main__":
    sys.exit(main())
