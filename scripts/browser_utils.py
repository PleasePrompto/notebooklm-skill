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
            channel="chrome",  # Use real Chrome
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
    """Handles file downloads from browser"""

    @staticmethod
    def setup_download_dir(context: BrowserContext, download_dir: str):
        """
        Note: Patchright/Playwright handles downloads via events.
        This is a placeholder for any pre-configuration if needed.
        """
        pass

    @staticmethod
    def wait_for_download(page: Page, trigger_action, download_dir: str, timeout: int = 60000) -> Optional[str]:
        """
        Wait for download to complete after triggering an action.

        Args:
            page: The browser page
            trigger_action: A callable that triggers the download (e.g., clicking download button)
            download_dir: Directory to save the downloaded file
            timeout: Maximum time to wait in milliseconds

        Returns:
            Path to the downloaded file, or None if failed
        """
        from pathlib import Path

        download_path = None

        try:
            # Set up download handler
            with page.expect_download(timeout=timeout) as download_info:
                # Execute the action that triggers download
                trigger_action()

            download = download_info.value

            # Get suggested filename
            suggested_filename = download.suggested_filename

            # Save to specified directory
            save_path = Path(download_dir) / suggested_filename
            download.save_as(str(save_path))

            print(f"  💾 Downloaded: {save_path}")
            download_path = str(save_path)

        except Exception as e:
            print(f"  ❌ Download failed: {e}")

        return download_path

    @staticmethod
    def download_with_custom_name(page: Page, trigger_action, download_dir: str, filename: str, timeout: int = 60000) -> Optional[str]:
        """
        Download file with a custom filename.

        Args:
            page: The browser page
            trigger_action: A callable that triggers the download
            download_dir: Directory to save the downloaded file
            filename: Custom filename to use
            timeout: Maximum time to wait in milliseconds

        Returns:
            Path to the downloaded file, or None if failed
        """
        from pathlib import Path

        download_path = None

        try:
            with page.expect_download(timeout=timeout) as download_info:
                trigger_action()

            download = download_info.value

            # Save with custom filename
            save_path = Path(download_dir) / filename
            download.save_as(str(save_path))

            print(f"  💾 Downloaded: {save_path}")
            download_path = str(save_path)

        except Exception as e:
            print(f"  ❌ Download failed: {e}")

        return download_path
