#!/usr/bin/env python3
"""
Browser Session Management for NotebookLM
Individual browser session for persistent NotebookLM conversations
Based on the original NotebookLM API implementation
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from patchright.sync_api import BrowserContext

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from browser_utils import StealthUtils
from config import QUERY_INPUT_SELECTORS, QUERY_TIMEOUT_SECONDS, RESPONSE_SELECTORS
from notebook_navigation import explain_navigation_failure, open_notebook_page


class BrowserSession:
    """
    Represents a single persistent browser session for NotebookLM

    Each session gets its own Page (tab) within a shared BrowserContext,
    allowing for contextual conversations where NotebookLM remembers
    previous messages.
    """

    def __init__(
        self,
        session_id: str,
        context: BrowserContext,
        notebook_url: str,
        preferred_email: Optional[str] = None,
    ):
        """
        Initialize a new browser session

        Args:
            session_id: Unique identifier for this session
            context: Browser context (shared or dedicated)
            notebook_url: Target NotebookLM URL for this session
            preferred_email: Optional Google account email hint for chooser pages
        """
        self.id = session_id
        self.created_at = time.time()
        self.last_activity = time.time()
        self.message_count = 0
        self.notebook_url = notebook_url
        self.context = context
        self.preferred_email = preferred_email
        self.page = None
        self.stealth = StealthUtils()

        self._initialize()

    def _initialize(self):
        """Initialize the browser session and navigate to NotebookLM"""
        print(f"🚀 Creating session {self.id}...")

        self.page = self.context.new_page()
        print("  🌐 Navigating to NotebookLM...")

        try:
            navigation = open_notebook_page(
                self.page,
                self.notebook_url,
                preferred_email=self.preferred_email,
            )
            if navigation["status"] != "ok":
                message = " ".join(line.strip() for line in explain_navigation_failure(navigation))
                raise RuntimeError(message)

            self._wait_for_ready()
            self.stealth.random_mouse_movement(self.page)
            self.stealth.random_delay(300, 600)

            print(f"✅ Session {self.id} ready!")

        except Exception as error:
            print(f"❌ Failed to initialize session: {error}")
            if self.page:
                self.page.close()
            raise

    def _wait_for_ready(self):
        """Wait for NotebookLM page to be ready"""
        for selector in QUERY_INPUT_SELECTORS:
            try:
                self.page.wait_for_selector(selector, timeout=10000, state="visible")
                return
            except Exception:
                continue
        raise TimeoutError("NotebookLM query input did not become ready")

    def ask(self, question: str) -> Dict[str, Any]:
        """
        Ask a question in this session

        Args:
            question: The question to ask

        Returns:
            Dict with status, question, answer, session_id
        """
        try:
            self.last_activity = time.time()
            self.message_count += 1

            print(f"💬 [{self.id}] Asking: {question}")

            previous_answer = self._snapshot_latest_response()

            chat_input_selector = None
            for selector in QUERY_INPUT_SELECTORS:
                try:
                    self.page.wait_for_selector(selector, timeout=5000, state="visible")
                    chat_input_selector = selector
                    break
                except Exception:
                    continue

            if not chat_input_selector:
                raise TimeoutError("Could not find NotebookLM query input")

            self.stealth.realistic_click(self.page, chat_input_selector)
            self.stealth.human_type(self.page, chat_input_selector, question)
            self.stealth.random_delay(300, 800)
            self.page.keyboard.press("Enter")

            print("  ⏳ Waiting for response...")
            self.stealth.random_delay(1500, 3000)

            answer = self._wait_for_latest_answer(previous_answer)
            if not answer:
                raise RuntimeError("Empty response from NotebookLM")

            print(f"  ✅ Got response ({len(answer)} chars)")
            return {
                "status": "success",
                "question": question,
                "answer": answer,
                "session_id": self.id,
                "notebook_url": self.notebook_url,
            }

        except Exception as error:
            print(f"  ❌ Error: {error}")
            return {
                "status": "error",
                "question": question,
                "error": str(error),
                "session_id": self.id,
            }

    def _snapshot_latest_response(self) -> Optional[str]:
        """Get the current latest response text"""
        for selector in RESPONSE_SELECTORS:
            try:
                responses = self.page.query_selector_all(selector)
                if responses:
                    return responses[-1].inner_text()
            except Exception:
                continue
        return None

    def _wait_for_latest_answer(self, previous_answer: Optional[str], timeout: int = QUERY_TIMEOUT_SECONDS) -> str:
        """Wait for and extract the new answer"""
        start_time = time.time()
        last_candidate = None
        stable_count = 0

        while time.time() - start_time < timeout:
            try:
                thinking_element = self.page.query_selector("div.thinking-message")
                if thinking_element and thinking_element.is_visible():
                    time.sleep(0.5)
                    continue
            except Exception:
                pass

            try:
                for selector in RESPONSE_SELECTORS:
                    responses = self.page.query_selector_all(selector)
                    if not responses:
                        continue

                    latest_text = responses[-1].inner_text().strip()
                    if latest_text and latest_text != previous_answer:
                        if latest_text == last_candidate:
                            stable_count += 1
                            if stable_count >= 3:
                                return latest_text
                        else:
                            stable_count = 1
                            last_candidate = latest_text
                    break
            except Exception:
                pass

            time.sleep(0.5)

        raise TimeoutError(f"No response received within {timeout} seconds")

    def reset(self):
        """Reset the chat by reloading the page"""
        print(f"🔄 Resetting session {self.id}...")

        self.page.reload(wait_until="domcontentloaded")
        self._wait_for_ready()

        previous_count = self.message_count
        self.message_count = 0
        self.last_activity = time.time()

        print(f"✅ Session reset (cleared {previous_count} messages)")
        return previous_count

    def close(self):
        """Close this session and clean up resources"""
        print(f"🛑 Closing session {self.id}...")

        if self.page:
            try:
                self.page.close()
            except Exception as error:
                print(f"  ⚠️ Error closing page: {error}")
            finally:
                self.page = None

        print(f"✅ Session {self.id} closed")

    def get_info(self) -> Dict[str, Any]:
        """Get information about this session"""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "age_seconds": time.time() - self.created_at,
            "inactive_seconds": time.time() - self.last_activity,
            "message_count": self.message_count,
            "notebook_url": self.notebook_url,
        }

    def is_expired(self, timeout_seconds: int = 900) -> bool:
        """Check if session has expired (default: 15 minutes)"""
        return (time.time() - self.last_activity) > timeout_seconds


if __name__ == "__main__":
    print("Browser Session Module - Use ask_question.py for main interface")
    print("This module provides low-level browser session management.")
