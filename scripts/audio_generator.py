#!/usr/bin/env python3
"""
Audio Generator for NotebookLM
Generates Audio Overview and downloads the audio file via browser automation
"""

import argparse
import sys
import re
import time
import os
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from config import (
    AUDIO_OVERVIEW_CARD_SELECTORS,
    AUDIO_CUSTOMIZE_BUTTON_SELECTORS,
    AUDIO_FORMAT_SELECTORS,
    AUDIO_LENGTH_SELECTORS,
    AUDIO_INSTRUCTIONS_SELECTORS,
    AUDIO_GENERATE_BUTTON_SELECTORS,
    AUDIO_MENU_BUTTON_SELECTORS,
    AUDIO_DOWNLOAD_MENU_SELECTORS,
    AUDIO_GENERATING_SELECTORS,
    AUDIO_GENERATION_TIMEOUT,
    PAGE_LOAD_TIMEOUT
)
from browser_utils import BrowserFactory, StealthUtils, DownloadHandler


def find_element_with_selectors(page, selectors: list, timeout: int = 5000):
    """Try multiple selectors and return first match."""
    for selector in selectors:
        try:
            element = page.wait_for_selector(selector, timeout=timeout, state="visible")
            if element:
                return element, selector
        except:
            continue
    return None, None


def generate_audio(
    notebook_url: str,
    format: str = "deep_dive",
    length: str = "default",
    instructions: str = None,
    output: str = None,
    headless: bool = True
) -> str:
    """
    Generate Audio Overview for a NotebookLM notebook and download it.

    Args:
        notebook_url: The NotebookLM notebook URL
        format: Audio format - deep_dive, brief, critique, or debate
        length: Audio length - short, default, or long
        instructions: Custom instructions for AI hosts
        output: Custom output filename
        headless: Run browser in headless mode

    Returns:
        Path to downloaded audio file, or None if failed
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("  Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return None

    print("  Generating Audio Overview...")
    print(f"  Notebook: {notebook_url}")
    print(f"  Format: {format}")
    print(f"  Length: {length}")
    if instructions:
        print(f"  Instructions: {instructions[:50]}...")

    playwright = None
    context = None
    download_dir = os.getcwd()

    try:
        playwright = sync_playwright().start()

        context = BrowserFactory.launch_persistent_context(
            playwright,
            headless=headless
        )

        page = context.new_page()
        print("    Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded")

        # Wait for notebook to load
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=60000)
        StealthUtils.random_delay(2000, 3000)

        # First, check if we need to click on "Studio" tab (responsive layout)
        studio_tab = page.query_selector('button:has-text("Studio"), [role="tab"]:has-text("Studio")')
        if studio_tab:
            print("    Found Studio tab, clicking...")
            studio_tab.click()
            StealthUtils.random_delay(1000, 1500)

        # Find the Audio Overview card in Studio panel
        print("    Looking for Audio Overview in Studio panel...")

        # Click on the pencil/customize icon next to Audio Overview
        customize_button, selector = find_element_with_selectors(
            page, AUDIO_CUSTOMIZE_BUTTON_SELECTORS, timeout=10000
        )

        if not customize_button:
            # Try clicking on Audio Overview card directly
            audio_card, card_selector = find_element_with_selectors(
                page, AUDIO_OVERVIEW_CARD_SELECTORS, timeout=5000
            )
            if audio_card:
                print(f"     Found Audio Overview card: {card_selector}")
                # Look for pencil icon within or near the card
                pencil = page.query_selector(f'{card_selector} button, {card_selector} + button')
                if pencil:
                    pencil.click()
                    StealthUtils.random_delay(1000, 1500)
                else:
                    # Click the card itself
                    audio_card.click()
                    StealthUtils.random_delay(1000, 1500)
            else:
                print("     Could not find Audio Overview option")
                return None
        else:
            print(f"     Found customize button: {selector}")
            customize_button.click()
            StealthUtils.random_delay(1000, 1500)

        # Wait for customize dialog to appear
        print("    Waiting for Customize Audio Overview dialog...")
        StealthUtils.random_delay(1000, 2000)

        # Select format if specified
        if format and format in AUDIO_FORMAT_SELECTORS:
            print(f"    Selecting format: {format}")
            format_selectors = AUDIO_FORMAT_SELECTORS[format]
            format_element, fmt_selector = find_element_with_selectors(page, format_selectors, timeout=3000)
            if format_element:
                format_element.click()
                StealthUtils.random_delay(500, 800)
                print(f"     Selected: {fmt_selector}")

        # Select length if specified
        if length and length in AUDIO_LENGTH_SELECTORS:
            print(f"    Selecting length: {length}")
            length_selectors = AUDIO_LENGTH_SELECTORS[length]
            length_element, len_selector = find_element_with_selectors(page, length_selectors, timeout=3000)
            if length_element:
                length_element.click()
                StealthUtils.random_delay(500, 800)
                print(f"     Selected: {len_selector}")

        # Add custom instructions if provided
        if instructions:
            print("    Adding custom instructions...")
            instructions_input, instr_selector = find_element_with_selectors(
                page, AUDIO_INSTRUCTIONS_SELECTORS, timeout=3000
            )
            if instructions_input:
                instructions_input.click()
                StealthUtils.random_delay(200, 400)
                # Clear existing content and type new instructions
                instructions_input.fill("")
                StealthUtils.random_delay(100, 200)
                instructions_input.fill(instructions)
                StealthUtils.random_delay(500, 800)
                print("     Instructions added")
            else:
                print("     Could not find instructions field")

        # Click Generate button
        print("    Looking for Generate button...")
        generate_button, gen_selector = find_element_with_selectors(
            page, AUDIO_GENERATE_BUTTON_SELECTORS, timeout=5000
        )

        if not generate_button:
            # Try more specific selectors
            generate_button = page.query_selector('button.generate-button, button[type="submit"], button:has-text("Generate")')

        if not generate_button:
            print("     Could not find Generate button")
            page.screenshot(path="/tmp/notebooklm_audio_debug.png")
            print("     Debug screenshot saved to /tmp/notebooklm_audio_debug.png")
            return None

        print(f"     Found Generate button")

        # Wait for button to be enabled (it may be disabled initially)
        print("    Waiting for Generate button to be enabled...")
        try:
            page.wait_for_selector('button:has-text("Generate"):not([disabled])', timeout=10000)
        except:
            print("     Generate button seems disabled, trying to click anyway...")

        StealthUtils.random_delay(500, 1000)

        # Scroll into view and wait for stability
        generate_button.scroll_into_view_if_needed()
        StealthUtils.random_delay(300, 500)

        try:
            generate_button.click(timeout=10000)
        except Exception as click_error:
            print(f"     Click failed: {click_error}")
            # Try JavaScript click as fallback using the element handle
            try:
                page.evaluate('(el) => el.click()', generate_button)
                print("     Used JavaScript click fallback")
            except Exception as js_error:
                print(f"     JavaScript click also failed: {js_error}")
                page.screenshot(path="/tmp/notebooklm_generate_debug.png")
                print("     Debug screenshot saved to /tmp/notebooklm_generate_debug.png")
                return None

        print("    Started audio generation...")

        # Wait for generation to complete (can take 5-10 minutes)
        print("    Waiting for audio generation (this may take several minutes)...")
        generation_start = time.time()
        generation_timeout = AUDIO_GENERATION_TIMEOUT / 1000  # Convert to seconds

        # First, wait a few seconds for generation indicator to appear
        StealthUtils.random_delay(3000, 5000)

        # Then wait for the "Generating Audio Overview..." indicator to disappear
        # This is the most reliable way to know generation is complete
        generating_indicator_selectors = [
            'div:has-text("Generating Audio Overview")',
            ':text("Generating Audio Overview")',
            ':text("Come back in a few minutes")',
        ]

        last_print_time = 0
        while time.time() - generation_start < generation_timeout:
            # Check if still generating by looking for the generation indicator
            generating = False

            for selector in generating_indicator_selectors:
                try:
                    gen_indicator = page.query_selector(selector)
                    if gen_indicator and gen_indicator.is_visible():
                        generating = True
                        break
                except:
                    continue

            if generating:
                elapsed = int(time.time() - generation_start)
                # Print status every 30 seconds
                if elapsed - last_print_time >= 30:
                    print(f"      Still generating... ({elapsed}s)")
                    last_print_time = elapsed
                time.sleep(5)
                continue
            else:
                # Generation indicator disappeared - check if new audio appeared
                print("    Generation indicator disappeared, verifying completion...")
                StealthUtils.random_delay(2000, 3000)

                # Double-check that generation is really complete
                still_generating = False
                for selector in generating_indicator_selectors:
                    try:
                        gen_indicator = page.query_selector(selector)
                        if gen_indicator and gen_indicator.is_visible():
                            still_generating = True
                            break
                    except:
                        continue

                if not still_generating:
                    print("    Audio generation complete!")
                    break
                else:
                    # False alarm, continue waiting
                    time.sleep(5)
                    continue

        else:
            print("     Generation timeout exceeded")
            return None

        # Allow UI to settle after generation
        print("    Waiting for UI to settle...")
        StealthUtils.random_delay(3000, 5000)

        # Find and click the three-dot menu on the most recently generated audio
        # The newest audio should be at the top of the audio list
        print("    Looking for audio menu...")

        # Try multiple approaches to find the menu button
        menu_button = None

        # The audio items have a specific structure - look for ⋮ (three-dot) buttons
        # that are near audio content (not the pencil edit buttons on cards)
        # Audio items have: title, play button, and three-dot menu

        # First scroll down a bit to ensure audio items are in view
        page.evaluate('window.scrollBy(0, 300)')
        StealthUtils.random_delay(500, 800)

        # Look for audio items by their characteristics - they have titles with "Deep Dive" or "Brief" etc.
        # and find the three-dot menu button within/near them
        audio_row_selectors = [
            # Try to find menu button in rows containing audio metadata
            'div:has-text("Deep Dive") button[aria-label*="options"]',
            'div:has-text("Brief") button[aria-label*="options"]',
            'div:has-text("sources") button[aria-label*="options"]',
            # Direct menu button selectors - but filter for actual three-dot menus
            'button[aria-label="More options"]',
            'button[aria-label="Options"]',
        ]

        for selector in audio_row_selectors:
            try:
                menu_buttons = page.query_selector_all(selector)
                if menu_buttons and len(menu_buttons) > 0:
                    menu_button = menu_buttons[0]
                    print(f"     Found {len(menu_buttons)} menu button(s) with: {selector}")
                    break
            except:
                continue

        if not menu_button:
            # Fallback: look for any button with three vertical dots icon
            all_buttons = page.query_selector_all('button')
            for btn in all_buttons:
                try:
                    aria_label = btn.get_attribute('aria-label') or ''
                    if 'option' in aria_label.lower() or 'more' in aria_label.lower():
                        # Check if this button is in the audio section (not in the cards)
                        parent = btn.evaluate('el => el.closest("div")?.textContent || ""')
                        if 'sources' in parent.lower() or 'dive' in parent.lower() or 'brief' in parent.lower():
                            menu_button = btn
                            print(f"     Found menu button via fallback: {aria_label}")
                            break
                except:
                    continue

        if not menu_button:
            print("     Could not find audio menu button")
            page.screenshot(path="/tmp/notebooklm_menu_debug.png")
            print("     Debug screenshot saved to /tmp/notebooklm_menu_debug.png")
            return None

        # Scroll element into view and wait
        menu_button.scroll_into_view_if_needed()
        StealthUtils.random_delay(500, 800)

        # Try clicking with timeout handling
        try:
            menu_button.click(timeout=5000)
        except Exception as click_error:
            print(f"     Normal click failed: {click_error}")
            # Try JavaScript click as fallback
            try:
                page.evaluate('(el) => el.click()', menu_button)
                print("     Used JavaScript click fallback")
            except Exception as js_error:
                print(f"     JavaScript click also failed: {js_error}")
                page.screenshot(path="/tmp/notebooklm_menu_debug.png")
                return None

        # Wait for menu dropdown to appear
        StealthUtils.random_delay(1000, 1500)

        # Click Download option
        print("    Looking for Download option...")

        # Try multiple selectors for download option in menu
        download_selectors = [
            '[role="menuitem"]:has-text("Download")',
            'li:has-text("Download")',
            'button:has-text("Download")',
            'div:has-text("Download")',
            'span:has-text("Download")',
            '[data-action="download"]',
            'mat-menu-item:has-text("Download")',
        ]

        download_option = None
        dl_selector = None

        for selector in download_selectors:
            try:
                download_option = page.wait_for_selector(selector, timeout=2000, state="visible")
                if download_option:
                    dl_selector = selector
                    break
            except:
                continue

        if not download_option:
            # Take a screenshot to see the menu state
            page.screenshot(path="/tmp/notebooklm_download_menu_debug.png")
            print("     Could not find Download option")
            print("     Debug screenshot saved to /tmp/notebooklm_download_menu_debug.png")
            return None

        print(f"     Found: {dl_selector}")

        # Handle download
        def trigger_download():
            download_option.click()

        if output:
            # Use custom filename
            download_path = DownloadHandler.download_with_custom_name(
                page,
                trigger_download,
                download_dir,
                output,
                timeout=60000
            )
        else:
            # Use suggested filename
            download_path = DownloadHandler.wait_for_download(
                page,
                trigger_download,
                download_dir,
                timeout=60000
            )

        if download_path:
            print(f"   Audio downloaded successfully: {download_path}")
            return download_path
        else:
            print("   Download failed")
            return None

    except Exception as e:
        print(f"   Error: {e}")
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
    parser = argparse.ArgumentParser(description='Generate NotebookLM Audio Overview')

    parser.add_argument('--notebook-url', required=True, help='NotebookLM notebook URL')
    parser.add_argument('--format', choices=['deep_dive', 'brief', 'critique', 'debate'],
                        default='deep_dive', help='Audio format (default: deep_dive)')
    parser.add_argument('--length', choices=['short', 'default', 'long'],
                        default='default', help='Audio length (default: default)')
    parser.add_argument('--instructions', help='Custom instructions for AI hosts')
    parser.add_argument('--output', help='Custom output filename')
    parser.add_argument('--show-browser', action='store_true', help='Show browser window')

    args = parser.parse_args()

    result = generate_audio(
        notebook_url=args.notebook_url,
        format=args.format,
        length=args.length,
        instructions=args.instructions,
        output=args.output,
        headless=not args.show_browser
    )

    if result:
        print("\n" + "=" * 60)
        print(" Audio Overview Generated")
        print("=" * 60)
        print(f"File: {result}")
        print(f"Format: {args.format}")
        print(f"Length: {args.length}")
        if args.instructions:
            print(f"Instructions: {args.instructions[:50]}...")
        print("=" * 60)
        return 0
    else:
        print("\n Failed to generate audio")
        return 1


if __name__ == "__main__":
    sys.exit(main())
