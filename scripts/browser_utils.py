"""
Browser Utilities for NotebookLM Skill
Handles browser launching, stealth features, and common interactions
"""

import json
import time
import random
import traceback
from typing import Optional, List, Tuple, Any

from patchright.sync_api import Playwright, BrowserContext, Page
from config import BROWSER_PROFILE_DIR, STATE_FILE, BROWSER_ARGS, USER_AGENT, get_language_display_name


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
            except Exception:
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


def find_element_with_selectors(page: Page, selectors: list, timeout: int = 5000) -> Tuple[Optional[Any], Optional[str]]:
    """
    Try multiple selectors and return first visible match.

    Args:
        page: Playwright page object
        selectors: List of CSS selectors to try
        timeout: Timeout in milliseconds for each selector

    Returns:
        Tuple of (element, matched_selector) or (None, None) if not found
    """
    for selector in selectors:
        try:
            element = page.wait_for_selector(selector, timeout=timeout, state="visible")
            if element:
                return element, selector
        except Exception:
            continue
    return None, None


def select_language(page: Page, language: str) -> bool:
    """
    Select a language from the NotebookLM dropdown menu.

    Args:
        page: Playwright page object
        language: Language name in English (e.g., "Japanese") or native script (e.g., "日本語")

    Returns:
        True if language was selected, False otherwise
    """
    display_name = get_language_display_name(language)
    print(f"    Selecting language: {language} → {display_name}")

    try:
        # Step 1: Find and click the language dropdown
        dropdown_opened = False

        # Try clicking on the element that shows current language selection
        try:
            lang_dropdown = page.locator('mat-select:has-text("English"), div[role="combobox"]:has-text("English"), div[role="listbox"]:has-text("English")').first
            if lang_dropdown.is_visible(timeout=2000):
                lang_dropdown.click()
                dropdown_opened = True
        except Exception:
            pass

        if not dropdown_opened:
            # Try finding by structure - look for the language section
            try:
                lang_section = page.locator('div:has-text("Choose language")').first
                if lang_section.is_visible(timeout=1000):
                    dropdown = lang_section.locator('mat-select, [role="combobox"], div:has-text("English")').first
                    if dropdown.is_visible(timeout=1000):
                        dropdown.click()
                        dropdown_opened = True
            except Exception:
                pass

        if not dropdown_opened:
            print("     Could not find language dropdown")
            page.screenshot(path="/tmp/notebooklm_language_debug.png")
            return False

        StealthUtils.random_delay(500, 800)

        # Step 2: Find and click the language option by its display name
        try:
            lang_option = page.locator(f'div:text-is("{display_name}"), span:text-is("{display_name}")').first
            if lang_option.is_visible(timeout=3000):
                lang_option.scroll_into_view_if_needed()
                lang_option.click()
                StealthUtils.random_delay(500, 800)
                print(f"     Selected: {display_name}")
                return True
        except Exception:
            pass

        # Fallback: try get_by_text with exact match
        try:
            lang_option = page.get_by_text(display_name, exact=True).first
            if lang_option.is_visible(timeout=2000):
                lang_option.scroll_into_view_if_needed()
                lang_option.click()
                StealthUtils.random_delay(500, 800)
                print(f"     Selected: {display_name}")
                return True
        except Exception:
            pass

        # Another fallback: use role="option" selector
        try:
            lang_option = page.locator(f'[role="option"]:has-text("{display_name}")').first
            if lang_option.is_visible(timeout=2000):
                lang_option.scroll_into_view_if_needed()
                lang_option.click()
                StealthUtils.random_delay(500, 800)
                print(f"     Selected: {display_name}")
                return True
        except Exception:
            pass

        print(f"     Could not find language option: {display_name}")
        page.screenshot(path="/tmp/notebooklm_language_options_debug.png")
        page.keyboard.press("Escape")
        return False

    except Exception as e:
        print(f"     Language selection error: {e}")
        return False


def get_all_sources_from_ui(page: Page) -> List[str]:
    """
    Get all source titles from the NotebookLM UI.

    Args:
        page: Playwright page object

    Returns:
        List of source titles
    """
    sources = page.evaluate("""
        () => {
            const sources = [];
            const checkboxes = document.querySelectorAll('input[type="checkbox"], [role="checkbox"], mat-checkbox, .mat-checkbox');

            for (const checkbox of checkboxes) {
                let parent = checkbox.parentElement;
                for (let i = 0; i < 5 && parent; i++) {
                    const text = parent.innerText?.trim();
                    if (text && text.length > 5 && text.length < 300) {
                        const lines = text.split('\\n').filter(l => l.trim());
                        for (const line of lines) {
                            const cleaned = line.trim();
                            if (cleaned.length < 5) continue;
                            if (['check_box', 'more_vert', 'description', 'drive_pdf',
                                 'markdown', 'web', 'Select all'].some(p => cleaned.includes(p))) continue;

                            const hasExtension = /\\.(pdf|md|txt|docx)$/i.test(cleaned);
                            const isWikipedia = cleaned.includes('Wikipedia');
                            const hasCJK = /[\\u4e00-\\u9fff]/.test(cleaned);
                            const hasPattern = /--/.test(cleaned) || /_/.test(cleaned);

                            if ((hasExtension || isWikipedia || hasCJK || hasPattern) &&
                                !sources.includes(cleaned)) {
                                sources.push(cleaned);
                                break;
                            }
                        }
                        break;
                    }
                    parent = parent.parentElement;
                }
            }
            return sources;
        }
    """)
    return sources
