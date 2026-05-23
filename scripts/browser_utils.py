"""
Browser Utilities for NotebookLM Skill
Handles browser launching, stealth features, and common interactions
"""

import json
import time
import random
from typing import Optional, List

from patchright.sync_api import Playwright, BrowserContext, Page
from config import BROWSER_PROFILE_DIR, STATE_FILE, BROWSER_ARGS, USER_AGENT


class BrowserFactory:
    """Factory for creating configured browser contexts"""

    @staticmethod
    def launch_persistent_context(
        playwright: Playwright,
        headless: bool = True,
        user_data_dir: str = str(BROWSER_PROFILE_DIR)
    ) -> BrowserContext:
        """
        Launch a persistent browser context with anti-detection features
        and cookie workaround.
        """
        # Launch persistent context
        # channel="chrome" requires system Google Chrome (needs sudo to install on macOS).
        # Fall back to patchright's bundled chromium build when Chrome is absent.
        import os as _os
        _chrome_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
        _has_chrome = any(_os.path.exists(p) for p in _chrome_paths)
        _launch_kwargs = dict(
            user_data_dir=user_data_dir,
            headless=headless,
            no_viewport=True,
            ignore_default_args=["--enable-automation"],
            user_agent=USER_AGENT,
            args=BROWSER_ARGS,
        )
        if _has_chrome:
            _launch_kwargs["channel"] = "chrome"
        context = playwright.chromium.launch_persistent_context(**_launch_kwargs)

        # Cookie Workaround for Playwright bug #36139
        # Session cookies (expires=-1) don't persist in user_data_dir automatically
        BrowserFactory._inject_cookies(context)

        return context

    @staticmethod
    def _inject_cookies(context: BrowserContext):
        """Inject cookies from state.json if available"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    if 'cookies' in state and len(state['cookies']) > 0:
                        context.add_cookies(state['cookies'])
                        # print(f"  🔧 Injected {len(state['cookies'])} cookies from state.json")
            except Exception as e:
                print(f"  ⚠️  Could not load state.json: {e}")


class StealthUtils:
    """Human-like interaction utilities"""

    @staticmethod
    def random_delay(min_ms: int = 100, max_ms: int = 500):
        """Add random delay"""
        time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

    @staticmethod
    def human_type(page: Page, selector: str, text: str, wpm_min: int = 320, wpm_max: int = 480):
        """Type into a query box that re-renders once during Angular hydration.

        NotebookLM renders the textarea, then swaps the node ~once shortly after
        load (and never reaches networkidle, since it long-polls). A cached
        ElementHandle goes stale mid-type ('Element is not attached to the DOM');
        a single long settle wait misses the box entirely if the swap lands inside
        the wait. Fix: a retry loop that RE-LOCATES the box each attempt (Locator
        API auto-resolves at action time), atomically fills it, and verifies the
        value actually landed — so whichever instance of the box is live when we
        act, one attempt succeeds.
        """
        deadline = time.time() + 30
        attempt = 0
        last_err = None
        while time.time() < deadline:
            attempt += 1
            try:
                loc = page.locator(selector).first
                loc.wait_for(state="visible", timeout=5000)
                loc.click(timeout=3000)
                loc.fill("", timeout=3000)        # clear any partial text
                loc.fill(text, timeout=3000)      # atomic set + input event
                # fill() alone may not fire keydown/keyup, which Angular Material
                # needs to ENABLE the send button. Fire real key events (net text
                # unchanged) so the subsequent Enter actually submits.
                try:
                    loc.press("Space", timeout=2000)
                    loc.press("Backspace", timeout=2000)
                except Exception:
                    pass
                val = loc.input_value(timeout=2000)
                if val and val.strip():
                    return
            except Exception as e:
                last_err = e
            time.sleep(0.6)
        print(f"⚠️ human_type failed after {attempt} attempts: {last_err}")

    @staticmethod
    def realistic_click(page: Page, selector: str):
        """Click with realistic movement"""
        element = page.query_selector(selector)
        if not element:
            return

        # Optional: Move mouse to element (simplified)
        box = element.bounding_box()
        if box:
            x = box['x'] + box['width'] / 2
            y = box['y'] + box['height'] / 2
            page.mouse.move(x, y, steps=5)

        StealthUtils.random_delay(100, 300)
        element.click()
        StealthUtils.random_delay(100, 300)
