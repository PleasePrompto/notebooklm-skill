"""
Browser Utilities for NotebookLM Skill
Handles browser launching, stealth features, and common interactions
"""

import json
import os
import random
import shutil
import tempfile
import time
from typing import List, Optional
from urllib.parse import urlparse

from patchright.sync_api import BrowserContext, Page, Playwright

from config import (
    BROWSER_ARGS,
    BROWSER_PROFILE_DIR,
    NOTEBOOKLM_PROXY_BYPASS_ENV,
    NOTEBOOKLM_PROXY_URL_ENV,
    STATE_FILE,
    USER_AGENT,
)


class BrowserFactory:
    """Factory for creating configured browser contexts"""

    @staticmethod
    def _get_proxy_settings() -> tuple[Optional[dict], List[str]]:
        """Build Playwright proxy settings and Chrome args from environment."""
        proxy_url = (
            os.getenv(NOTEBOOKLM_PROXY_URL_ENV)
            or os.getenv("HTTPS_PROXY")
            or os.getenv("https_proxy")
            or os.getenv("HTTP_PROXY")
            or os.getenv("http_proxy")
            or os.getenv("ALL_PROXY")
            or os.getenv("all_proxy")
        )

        if not proxy_url:
            return None, []

        parsed = urlparse(proxy_url)
        if not parsed.scheme or not parsed.hostname:
            print(f"  ⚠️  Ignoring invalid proxy URL: {proxy_url}")
            return None, []

        server = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            server += f":{parsed.port}"

        proxy = {"server": server}
        if parsed.username:
            proxy["username"] = parsed.username
        if parsed.password:
            proxy["password"] = parsed.password

        bypass = (
            os.getenv(NOTEBOOKLM_PROXY_BYPASS_ENV)
            or os.getenv("NO_PROXY")
            or os.getenv("no_proxy")
        )
        if bypass:
            proxy["bypass"] = bypass

        chrome_args = [f"--proxy-server={server}"]
        return proxy, chrome_args

    @staticmethod
    def launch_persistent_context(
        playwright: Playwright,
        headless: bool = True,
        user_data_dir: str = str(BROWSER_PROFILE_DIR),
    ) -> BrowserContext:
        """
        Launch a persistent browser context with anti-detection features
        and cookie workaround.
        """
        proxy, proxy_args = BrowserFactory._get_proxy_settings()

        launch_kwargs = dict(
            user_data_dir=user_data_dir,
            channel="chrome",
            headless=headless,
            no_viewport=True,
            ignore_default_args=["--enable-automation"],
            user_agent=USER_AGENT,
            args=BROWSER_ARGS + proxy_args,
            proxy=proxy,
        )

        try:
            context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as error:
            if "ProcessSingleton" not in str(error):
                raise
            fallback_root = tempfile.mkdtemp(prefix="notebooklm-profile-")
            fallback_dir = os.path.join(fallback_root, "browser_profile")
            print("  ⚠️  Browser profile is already in use; cloning it to a temporary profile")
            try:
                shutil.copytree(user_data_dir, fallback_dir, dirs_exist_ok=True)
                for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "DevToolsActivePort"]:
                    lock_path = os.path.join(fallback_dir, lock_name)
                    if os.path.exists(lock_path):
                        os.remove(lock_path)
            except Exception as copy_error:
                print(f"  ⚠️  Could not clone browser profile cleanly: {copy_error}")
                os.makedirs(fallback_dir, exist_ok=True)
            launch_kwargs["user_data_dir"] = fallback_dir
            context = playwright.chromium.launch_persistent_context(**launch_kwargs)

        BrowserFactory._inject_cookies(context)
        return context

    @staticmethod
    def _inject_cookies(context: BrowserContext):
        """Inject cookies from state.json if available"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as handle:
                    state = json.load(handle)
                    if "cookies" in state and len(state["cookies"]) > 0:
                        context.add_cookies(state["cookies"])
            except Exception as error:
                print(f"  ⚠️  Could not load state.json: {error}")


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
            try:
                element = page.wait_for_selector(selector, timeout=2000)
            except Exception:
                pass

        if not element:
            print(f"⚠️ Element not found for typing: {selector}")
            return

        element.click()
        for char in text:
            element.type(char, delay=random.uniform(25, 75))
            if random.random() < 0.05:
                time.sleep(random.uniform(0.15, 0.4))

    @staticmethod
    def random_mouse_movement(page: Page):
        """Move the mouse a little to look less robotic."""
        try:
            for _ in range(random.randint(2, 4)):
                page.mouse.move(
                    random.randint(50, 900),
                    random.randint(50, 700),
                    steps=random.randint(3, 8),
                )
                StealthUtils.random_delay(60, 180)
        except Exception:
            pass

    @staticmethod
    def realistic_click(page: Page, selector: str):
        """Click with realistic movement"""
        element = page.query_selector(selector)
        if not element:
            return

        box = element.bounding_box()
        if box:
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            page.mouse.move(x, y, steps=5)

        StealthUtils.random_delay(100, 300)
        element.click()
        StealthUtils.random_delay(100, 300)
