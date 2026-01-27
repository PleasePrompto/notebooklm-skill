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
import traceback
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import QUERY_INPUT_SELECTORS, RESPONSE_SELECTORS
from browser_utils import BrowserFactory, StealthUtils
from source_filter import SourceFilter, select_sources_in_browser


# Follow-up reminder (adapted from MCP server for stateless operation)
# Since we don't have persistent sessions, we encourage comprehensive questions
FOLLOW_UP_REMINDER = (
    "\n\nEXTREMELY IMPORTANT: Is that ALL you need to know? "
    "You can always ask another question! Think about it carefully: "
    "before you reply to the user, review their original request and this answer. "
    "If anything is still unclear or missing, ask me another comprehensive question "
    "that includes all necessary context (since each question opens a new browser session)."
)


def ask_notebooklm(question: str, notebook_url: str, notebook_id: str = None,
                   headless: bool = True, filter_sources: bool = True,
                   use_llm_filter: bool = True, relevance_threshold: int = 5) -> str:
    """
    Ask a question to NotebookLM

    Args:
        question: Question to ask
        notebook_url: NotebookLM notebook URL
        notebook_id: Notebook ID (for source filtering)
        headless: Run browser in headless mode
        filter_sources: Whether to filter sources based on question relevance
        use_llm_filter: Use Gemini for semantic relevance scoring (default True)
        relevance_threshold: Minimum score (1-10) for LLM filter (default 5)

    Returns:
        Answer text from NotebookLM
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("⚠️ Not authenticated. Run: python auth_manager.py setup")
        return None

    # Load source filter if enabled and notebook_id provided
    source_filter = None
    relevant_sources = None
    all_sources = None

    if filter_sources and notebook_id:
        source_filter = SourceFilter(notebook_id)
        if source_filter.sources:
            relevant_sources = source_filter.get_relevant_sources(
                question,
                use_llm=use_llm_filter,
                threshold=relevance_threshold
            )
            all_sources = source_filter.get_all_source_titles()

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
            except Exception:
                continue

        if not query_element:
            print("  ❌ Could not find query input")
            return None

        # Filter sources if enabled
        if relevant_sources and all_sources and len(relevant_sources) < len(all_sources):
            print(f"  🔧 Filtering to {len(relevant_sources)}/{len(all_sources)} relevant sources...")

            # Wait for source containers to load (they may load after query input)
            try:
                page.wait_for_selector('.single-source-container', timeout=5000, state="attached")
                StealthUtils.random_delay(500, 800)  # Small extra wait for all sources
            except Exception:
                print("    ⚠️ Source containers not found, skipping filter")

            select_sources_in_browser(page, relevant_sources, all_sources)
            StealthUtils.random_delay(500, 1000)

        # Type question (human-like, fast)
        print("  ⏳ Typing question...")
        
        # Use primary selector for typing
        input_selector = QUERY_INPUT_SELECTORS[0]
        StealthUtils.human_type(page, input_selector, question)

        # Submit
        print("  📤 Submitting...")
        page.keyboard.press("Enter")

        # Small pause
        StealthUtils.random_delay(500, 1500)

        # Wait for response (MCP approach: poll for stable text)
        print("  ⏳ Waiting for answer...")

        answer = None
        stable_count = 0
        last_text = None
        deadline = time.time() + 120  # 2 minutes timeout

        while time.time() < deadline:
            # Check if NotebookLM is still thinking (most reliable indicator)
            try:
                thinking_element = page.query_selector('div.thinking-message')
                if thinking_element and thinking_element.is_visible():
                    time.sleep(1)
                    continue
            except Exception:
                pass

            # Try to find response with MCP selectors
            for selector in RESPONSE_SELECTORS:
                try:
                    elements = page.query_selector_all(selector)
                    if elements:
                        # Get last (newest) response
                        latest = elements[-1]
                        text = latest.inner_text().strip()

                        if text:
                            if text == last_text:
                                stable_count += 1
                                if stable_count >= 3:  # Stable for 3 polls
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
        # Add follow-up reminder to encourage Claude to ask more questions
        return answer + FOLLOW_UP_REMINDER

    except Exception as e:
        print(f"  ❌ Error: {e}")
        traceback.print_exc()
        return None

    finally:
        # Always clean up
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
    parser = argparse.ArgumentParser(description='Ask NotebookLM a question')

    parser.add_argument('--question', required=True, help='Question to ask')
    parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    parser.add_argument('--notebook-id', help='Notebook ID from library')
    parser.add_argument('--show-browser', action='store_true', help='Show browser')
    parser.add_argument('--no-filter', action='store_true', help='Disable source filtering')
    parser.add_argument('--keyword-filter', action='store_true',
                        help='Use keyword matching instead of LLM for source filtering')
    parser.add_argument('--threshold', type=int, default=5,
                        help='Relevance threshold for LLM filter (1-10, default: 5)')

    args = parser.parse_args()

    # Resolve notebook URL and ID
    notebook_url = args.notebook_url
    notebook_id = args.notebook_id

    if not notebook_url and args.notebook_id:
        library = NotebookLibrary()
        notebook = library.get_notebook(args.notebook_id)
        if notebook:
            notebook_url = notebook['url']
            notebook_id = notebook['id']
        else:
            print(f"❌ Notebook '{args.notebook_id}' not found")
            return 1

    if not notebook_url:
        # Check for active notebook first
        library = NotebookLibrary()
        active = library.get_active_notebook()
        if active:
            notebook_url = active['url']
            notebook_id = active['id']
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
                print("python3 scripts/run.py notebook_manager.py activate --id ID")
            else:
                print("❌ No notebooks in library. Add one first:")
                print("python3 scripts/run.py notebook_manager.py add --url URL --name NAME --description DESC --topics TOPICS")
            return 1

    # Ask the question
    answer = ask_notebooklm(
        question=args.question,
        notebook_url=notebook_url,
        notebook_id=notebook_id,
        headless=not args.show_browser,
        filter_sources=not args.no_filter,
        use_llm_filter=not args.keyword_filter,
        relevance_threshold=args.threshold
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
