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
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            # channel="chrome",  # Disabled - using Chromium instead (Chrome not installed)
            headless=headless,
            no_viewport=True,
            ignore_default_args=["--enable-automation"],
            user_agent=USER_AGENT,
            args=BROWSER_ARGS
        )

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
        """Type with human-like speed"""
        element = page.query_selector(selector)
        if not element:
            # Try waiting if not immediately found
            try:
                element = page.wait_for_selector(selector, timeout=2000)
            except:
                pass
        
        if not element:
            print(f"⚠️ Element not found for typing: {selector}")
            return

        # Click to focus
        element.click()
        
        # Type
        for char in text:
            element.type(char, delay=random.uniform(25, 75))
            if random.random() < 0.05:
                time.sleep(random.uniform(0.15, 0.4))

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


class DownloadHandler:
    """Utilities for handling file downloads"""

    @staticmethod
    def wait_for_download(
        page: Page,
        trigger_action,
        download_dir: str,
        timeout: int = 60000
    ) -> Optional[str]:
        """
        Wait for a download to complete after triggering an action.
        Returns the path to the downloaded file.
        """
        try:
            with page.expect_download(timeout=timeout) as download_info:
                trigger_action()

            download = download_info.value
            suggested_filename = download.suggested_filename
            download_path = f"{download_dir}/{suggested_filename}"

            download.save_as(download_path)
            return download_path

        except Exception as e:
            print(f"    Download failed: {e}")
            return None

    @staticmethod
    def download_with_custom_name(
        page: Page,
        trigger_action,
        download_dir: str,
        custom_filename: str,
        timeout: int = 60000
    ) -> Optional[str]:
        """
        Wait for a download and save with a custom filename.
        Returns the path to the downloaded file.
        """
        try:
            with page.expect_download(timeout=timeout) as download_info:
                trigger_action()

            download = download_info.value

            # Preserve extension from suggested filename if custom doesn't have one
            suggested = download.suggested_filename
            if '.' not in custom_filename and '.' in suggested:
                ext = suggested.rsplit('.', 1)[-1]
                custom_filename = f"{custom_filename}.{ext}"

            download_path = f"{download_dir}/{custom_filename}"
            download.save_as(download_path)
            return download_path

        except Exception as e:
            print(f"    Download failed: {e}")
            return None
