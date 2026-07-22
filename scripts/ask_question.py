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
import sys
import time
import re
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import QUERY_INPUT_SELECTORS, RESPONSE_SELECTORS, NOTEBOOK_TITLE_SELECTORS
from browser_utils import BrowserFactory, StealthUtils


# Follow-up reminder (adapted from MCP server for stateless operation)
# Since we don't have persistent sessions, we encourage comprehensive questions
FOLLOW_UP_REMINDER = (
    "\n\nEXTREMELY IMPORTANT: Is that ALL you need to know? "
    "You can always ask another question! Think about it carefully: "
    "before you reply to the user, review their original request and this answer. "
    "If anything is still unclear or missing, ask me another comprehensive question "
    "that includes all necessary context (since each question opens a new browser session)."
)


def detect_notebook_title(page) -> str:
    """
    Detect the actual notebook title from the NotebookLM page.
    Uses page.title() which contains "Notebook Name - Gemini Notebook".
    Returns the notebook name if found, None otherwise.
    """
    try:
        page_title = page.title()
        if page_title and " - Gemini Notebook" in page_title:
            return page_title.replace(" - Gemini Notebook", "").strip()
        elif page_title and " - NotebookLM" in page_title:
            return page_title.replace(" - NotebookLM", "").strip()
    except:
        pass

    # Fallback: try DOM selectors
    for selector in NOTEBOOK_TITLE_SELECTORS:
        try:
            element = page.query_selector(selector)
            if element:
                title = element.inner_text().strip()
                if title and len(title) > 0 and len(title) < 200:
                    return title
        except:
            continue
    return None


def sync_notebook_title(notebook_url: str, detected_title: str):
    """
    Update the local library if the detected title differs from stored name.
    """
    if not detected_title:
        return

    library = NotebookLibrary()

    # Find notebook by URL
    for notebook_id, notebook in library.notebooks.items():
        if notebook['url'] == notebook_url:
            stored_name = notebook.get('name', '')
            if stored_name != detected_title:
                print(f"  📝 Title sync: '{stored_name}' → '{detected_title}'")
                library.update_notebook(notebook_id, name=detected_title)
            return


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
        # Start playwright
        playwright = sync_playwright().start()

        # Launch persistent browser context using factory
        context = BrowserFactory.launch_persistent_context(
            playwright,
            headless=headless
        )

        # Navigate to notebook
        page = context.new_page()
        print("  🌐 Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded")

        # Wait for NotebookLM
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=10000)

        # Detect and sync notebook title
        time.sleep(1)  # Allow page to render title
        detected_title = detect_notebook_title(page)
        if detected_title:
            print(f"  📓 Notebook: {detected_title}")
            sync_notebook_title(notebook_url, detected_title)

        # Wait for query input (MCP approach)
        print("  ⏳ Waiting for query input...")
        query_element = None

        for selector in QUERY_INPUT_SELECTORS:
            try:
                query_element = page.wait_for_selector(
                    selector,
                    timeout=10000,
                    state="visible"  # Only check visibility, not disabled!
                )
                if query_element:
                    print(f"  ✓ Found input: {selector}")
                    break
            except:
                continue

        if not query_element:
            print("  ❌ Could not find query input")
            return None

        # Type question
        print("  ⏳ Typing question...")

        # Use primary selector for typing
        input_selector = QUERY_INPUT_SELECTORS[0]
        StealthUtils.human_type(page, input_selector, question)

        # Verify the question was typed correctly
        time.sleep(0.3)
        try:
            typed_text = page.input_value(input_selector)
            if typed_text != question:
                print(f"  ⚠️ Question mismatch! Expected: '{question[:50]}...'")
                print(f"  ⚠️ Got: '{typed_text[:50]}...'")
            else:
                print(f"  ✓ Question verified ({len(question)} chars)")
        except Exception as e:
            print(f"  ⚠️ Could not verify question: {e}")

        # Wait for chat history to load before capturing baseline
        # This ensures we don't miscount async-loaded history as "new" responses
        primary_selector = RESPONSE_SELECTORS[0]  # Use consistent selector
        print("  📊 Waiting for chat history to load...")
        time.sleep(3)  # Give time for existing responses to render

        # Poll until response count stabilizes (history fully loaded)
        initial_response_count = 0
        baseline_texts = set()  # Store hashes of ALL existing response texts
        stable_history_count = 0
        for _ in range(10):  # Max 10 attempts
            try:
                elements = page.query_selector_all(primary_selector)
                current_count = len(elements) if elements else 0
                if current_count == initial_response_count:
                    stable_history_count += 1
                    if stable_history_count >= 2:
                        # Use hash of full text to handle similar responses
                        baseline_texts = {hash(el.inner_text().strip()) for el in elements}
                        break
                else:
                    initial_response_count = current_count
                    stable_history_count = 0
            except:
                pass
            time.sleep(0.5)

        print(f"  📊 Existing responses: {initial_response_count}")

        # Submit
        print("  📤 Submitting...")
        page.keyboard.press("Enter")

        # Wait for response - must be a NEW response (count > initial)
        print("  ⏳ Waiting for answer...")

        answer = None
        stable_count = 0
        last_text = None
        new_response_detected = False
        deadline = time.time() + 120  # 2 minutes timeout

        while time.time() < deadline:
            # Check if NotebookLM is still thinking (most reliable indicator)
            try:
                thinking_element = page.query_selector('div.thinking-message')
                if thinking_element and thinking_element.is_visible():
                    time.sleep(1)
                    continue
            except:
                pass

            # Check for new response by finding text NOT in baseline
            try:
                elements = page.query_selector_all(primary_selector)
                current_count = len(elements) if elements else 0

                # Find the NEW response - one whose hash isn't in our baseline
                new_text = None
                for el in elements:
                    text = el.inner_text().strip()
                    text_hash = hash(text)
                    if text_hash not in baseline_texts and text:
                        new_text = text
                        break

                if new_text:
                    if not new_response_detected:
                        print(f"  ✨ New response detected (count: {initial_response_count} → {current_count})")
                        new_response_detected = True

                    if new_text == last_text:
                        stable_count += 1
                        if stable_count >= 3:  # Stable for 3 polls
                            answer = new_text
                            break
                    else:
                        stable_count = 0
                        last_text = new_text
            except:
                pass

            if answer:
                break

            time.sleep(1)

        if not answer:
            print("  ❌ Timeout waiting for answer")
            return None

        print("  ✅ Got answer!")
        # Add follow-up reminder to encourage Claude to ask more questions
        return answer + FOLLOW_UP_REMINDER

    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        # Always clean up
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

    # Resolve notebook URL
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
        # Check for active notebook first
        library = NotebookLibrary()
        active = library.get_active_notebook()
        if active:
            notebook_url = active['url']
            print(f"📚 Using active notebook: {active['name']}")
        else:
            # Show available notebooks
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
                print("python scripts/run.py notebook_manager.py add --url URL --name NAME --description DESC --topics TOPICS")
            return 1

    # Ask the question
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
