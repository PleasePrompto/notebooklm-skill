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
from config import QUERY_INPUT_SELECTORS, RESPONSE_SELECTORS
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
        print("⚠️ Not authenticated. Run: python3 auth_manager.py setup")
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

        # Type question (human-like, fast)
        print("  ⏳ Typing question...")
        
        # Use primary selector for typing
        input_selector = QUERY_INPUT_SELECTORS[0]

        # Snapshot EXISTING bot answers BEFORE submitting. NotebookLM persists the
        # chat thread across browser sessions, so without this the poll locks onto
        # the PREVIOUS answer and returns it instantly (verified 2026-06-11: a fresh
        # question returned the prior query's stale answer). We settle until the
        # persisted thread stops growing, then gate acceptance on a NEW container
        # appearing (count increase) — text-inequality alone races the thread-render
        # and can miss the baseline.
        def _answer_texts():
            for selector in RESPONSE_SELECTORS:
                try:
                    els = page.query_selector_all(selector)
                    if els:
                        return [(e.inner_text() or "").strip() for e in els]
                except Exception:
                    continue
            return []

        # settle: wait for the persisted thread to finish rendering (count stable)
        _prev, _stable, _settle_deadline = -1, 0, time.time() + 12
        while time.time() < _settle_deadline:
            _cur = len(_answer_texts())
            if _cur == _prev:
                _stable += 1
                if _stable >= 3:
                    break
            else:
                _stable, _prev = 0, _cur
            time.sleep(0.6)
        _pre_texts = _answer_texts()
        # Multiset snapshot of the persisted thread's answers. Two artifacts make a
        # naive gate fail (both verified 2026-06-20):
        #   1) the new answer is NOT reliably the DOM-last container — NotebookLM does
        #      not render the thread strictly chronologically, and the count may not
        #      grow, so neither texts[-1] nor len()>pre_count detects it.
        #   2) an answer can be textually identical to an earlier one (e.g. the same
        #      question asked twice), so plain set-membership novelty rejects it.
        # Counter handles both: the fresh answer is the text whose occurrence count is
        # now HIGHER than before submit, found at any index.
        from collections import Counter
        baseline_counter = Counter(_pre_texts)

        StealthUtils.human_type(page, input_selector, question)

        # Submit. The send button is LOCALE-DEPENDENT (e.g. Thai 'ส่ง', icon
        # 'arrow_forward') and only ENABLES once real key events land, so match it
        # by aria-label/icon across languages and nudge with a real keystroke until
        # it is clickable. The old English-only ['Send'/'Submit'] list missed the
        # localized button, and the 'button[type=submit]' fallback clicked the WRONG
        # submit element → silent no-send → the 120s answer timeout. (Diagnosed
        # 2026-06-11: account UI in Thai; auth/notebook-load/response-read all fine.)
        print("  📤 Submitting...")

        def _click_send():
            find_js = """() => {
              const btns = [...document.querySelectorAll('button')];
              const cand = btns.find(b => {
                if (b.disabled) return false;
                const al = (b.getAttribute('aria-label') || '');
                const mi = b.querySelector('mat-icon');
                const ic = mi ? ((mi.getAttribute('fonticon') || mi.textContent) || '').trim() : '';
                return /send|submit|ส่ง/i.test(al) ||
                       ['send', 'arrow_forward', 'arrow_upward'].includes(ic);
              });
              return cand || null;
            }"""
            end = time.time() + 8
            while time.time() < end:
                try:
                    el = page.evaluate_handle(find_js).as_element()
                    if el:
                        el.click(timeout=2000)
                        return True
                except Exception:
                    pass
                # real-key nudge: enables an Angular send button left disabled by fill()
                try:
                    page.locator(input_selector).first.click(timeout=1000)
                    page.keyboard.type(" ")
                    page.keyboard.press("Backspace")
                except Exception:
                    pass
                time.sleep(0.5)
            return False

        if not _click_send():
            print("  ⚠️ send button not found/enabled — falling back to Enter")
            page.keyboard.press("Enter")

        # Small pause
        StealthUtils.random_delay(500, 1500)

        # Wait for response (MCP approach: poll for stable text)
        print("  ⏳ Waiting for answer...")

        answer = None
        stable_count = 0
        last_text = None
        _PLACEHOLDERS = ("finding relevant info", "finding sources", "analyzing")
        deadline = time.time() + 120  # 2 minutes timeout

        while time.time() < deadline:
            # Skip while NotebookLM is still thinking (most reliable indicator)
            try:
                thinking_element = page.query_selector('div.thinking-message')
                if thinking_element and thinking_element.is_visible():
                    time.sleep(1)
                    continue
            except Exception:
                pass

            texts = _answer_texts()
            # The fresh answer = a text that now occurs MORE times than it did before
            # submit (Counter delta), located at any index — robust to both the
            # non-chronological render order and to answers that duplicate an earlier
            # reply. Pick the longest such candidate (the substantive reply, not a
            # one-line echo), then wait for it to stop streaming.
            cur_counter = Counter(texts)
            new_texts = [
                t for t in cur_counter
                if t and cur_counter[t] > baseline_counter[t]
                and not any(p in t.lower() for p in _PLACEHOLDERS)
            ]
            if new_texts:
                text = max(new_texts, key=len)
                if text == last_text:
                    stable_count += 1
                    if stable_count >= 3:  # Stable for 3 polls
                        answer = text
                        break
                else:
                    stable_count = 0
                    last_text = text

            time.sleep(1)

        if not answer:
            print("  ❌ Timeout waiting for answer")
            return None

        print("  ✅ Got answer!")
        # Persist the session on every successful query so continuous use actually
        # EXTENDS auth instead of letting it decay. The state.json session cookies
        # (the bug #36139 workaround set) are otherwise frozen at login time and never
        # refreshed by this read path — so without this, even daily use eventually
        # forces a manual reauth when Google rotates them (verified 2026-06-20: 3
        # successful asks left state.json mtime untouched). Best-effort: a save
        # failure must not lose the answer we already have.
        try:
            auth._save_browser_state(context)
        except Exception as _e:
            print(f"  ⚠️  Could not refresh saved session (non-fatal): {_e}")
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
                print("python3 scripts/run.py notebook_manager.py activate --id ID")
            else:
                print("❌ No notebooks in library. Add one first:")
                print("python3 scripts/run.py notebook_manager.py add --url URL --name NAME --description DESC --topics TOPICS")
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
