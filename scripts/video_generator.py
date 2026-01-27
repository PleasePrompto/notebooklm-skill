#!/usr/bin/env python3
"""
Video Generator for NotebookLM
Generates Video Overview with custom format, visual style, and instructions
"""

import argparse
import sys
import re
import time
import traceback
from pathlib import Path

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import (
    VIDEO_OVERVIEW_CARD_SELECTORS,
    VIDEO_CUSTOMIZE_BUTTON_SELECTORS,
    VIDEO_FORMAT_SELECTORS,
    VIDEO_STYLE_SELECTORS,
    VIDEO_INSTRUCTIONS_SELECTORS,
    VIDEO_GENERATE_BUTTON_SELECTORS,
    VIDEO_GENERATING_SELECTORS,
    VIDEO_GENERATION_TIMEOUT,
    PAGE_LOAD_TIMEOUT,
)
from browser_utils import (
    BrowserFactory,
    StealthUtils,
    find_element_with_selectors,
    select_language,
    get_all_sources_from_ui,
)
from source_filter import select_sources_in_browser


def generate_video(
    notebook_url: str,
    format: str = "explainer",
    style: str = "auto",
    language: str = None,
    instructions: str = None,
    sources: list = None,
    output: str = None,
    headless: bool = True
) -> str:
    """
    Generate Video Overview for a NotebookLM notebook and download it.

    Args:
        notebook_url: The NotebookLM notebook URL
        format: Video format - explainer or brief
        style: Visual style - auto, custom, classic, whiteboard, kawaii, anime
        language: Language for the video (e.g., "English", "Spanish", "Japanese")
        instructions: Custom instructions for AI hosts (the prompt)
        sources: List of source names to include (deselects others). If None, uses all sources.
        output: Custom output filename
        headless: Run browser in headless mode

    Returns:
        Path to downloaded video file, or None if failed
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("  Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return None

    print("  Generating Video Overview...")
    print(f"  Notebook: {notebook_url}")
    print(f"  Format: {format}")
    print(f"  Style: {style}")
    if language:
        print(f"  Language: {language}")
    if sources:
        print(f"  Sources: {len(sources)} selected")
        for s in sources[:3]:
            print(f"    - {s[:50]}...")
        if len(sources) > 3:
            print(f"    ... and {len(sources) - 3} more")
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

        # Handle source selection if specified
        if sources:
            print("    Selecting specific sources...")
            StealthUtils.random_delay(1000, 1500)

            # Get all sources from UI
            all_sources = get_all_sources_from_ui(page)
            print(f"    Found {len(all_sources)} sources in notebook")

            if all_sources:
                # Find matching sources (partial match supported)
                sources_to_keep = []
                for source_name in sources:
                    for ui_source in all_sources:
                        if source_name.lower() in ui_source.lower() or ui_source.lower() in source_name.lower():
                            sources_to_keep.append(ui_source)
                            break

                if sources_to_keep:
                    print(f"    Keeping {len(sources_to_keep)} sources, deselecting {len(all_sources) - len(sources_to_keep)}")
                    select_sources_in_browser(page, sources_to_keep, all_sources)
                    StealthUtils.random_delay(500, 1000)
                else:
                    print("    Warning: No matching sources found, using all sources")

        # First, check if we need to click on "Studio" tab (responsive layout)
        studio_tab = page.query_selector('button:has-text("Studio"), [role="tab"]:has-text("Studio")')
        if studio_tab:
            print("    Found Studio tab, clicking...")
            studio_tab.click()
            StealthUtils.random_delay(1000, 1500)

        # Find the Video Overview card in Studio panel
        print("    Looking for Video Overview in Studio panel...")

        # Click on the pencil/customize icon next to Video Overview
        customize_button, selector = find_element_with_selectors(
            page, VIDEO_CUSTOMIZE_BUTTON_SELECTORS, timeout=10000
        )

        if not customize_button:
            # Try clicking on Video Overview card directly
            video_card, card_selector = find_element_with_selectors(
                page, VIDEO_OVERVIEW_CARD_SELECTORS, timeout=5000
            )
            if video_card:
                print(f"     Found Video Overview card: {card_selector}")
                # Look for pencil icon within or near the card
                pencil = page.query_selector(f'{card_selector} button, {card_selector} + button')
                if pencil:
                    pencil.click()
                    StealthUtils.random_delay(1000, 1500)
                else:
                    # Click the card itself
                    video_card.click()
                    StealthUtils.random_delay(1000, 1500)
            else:
                print("     Could not find Video Overview option")
                return None
        else:
            print(f"     Found customize button: {selector}")
            customize_button.click()
            StealthUtils.random_delay(1000, 1500)

        # Wait for customize dialog to appear
        print("    Waiting for Customize Video Overview dialog...")
        StealthUtils.random_delay(1000, 2000)

        # Select format if specified
        if format:
            print(f"    Selecting format: {format}")
            format_names = {
                'explainer': 'Explainer',
                'brief': 'Brief'
            }
            format_name = format_names.get(format, format)

            # Use Playwright locators to find and click format card
            format_selected = False
            try:
                # Try finding a div that contains exactly the format name as a child div
                format_card = page.locator(f'div:has(div:text-is("{format_name}"))').first
                if format_card.is_visible(timeout=2000):
                    format_card.click()
                    format_selected = True
            except Exception:
                pass

            if not format_selected:
                try:
                    # Fallback: find the text and click its parent card
                    format_el = page.get_by_text(format_name, exact=True).first
                    if format_el.is_visible(timeout=2000):
                        format_el.locator('..').locator('..').click()
                        format_selected = True
                except Exception:
                    pass

            if format_selected:
                StealthUtils.random_delay(500, 800)
                print(f"     Selected: {format_name}")
            else:
                print(f"     Warning: Could not find format card for {format_name}")

        # Select visual style if specified
        if style and style in VIDEO_STYLE_SELECTORS:
            print(f"    Selecting visual style: {style}")
            style_selectors = VIDEO_STYLE_SELECTORS[style]
            style_element, sty_selector = find_element_with_selectors(page, style_selectors, timeout=3000)
            if style_element:
                style_element.click()
                StealthUtils.random_delay(500, 800)
                print(f"     Selected: {sty_selector}")

        # Select language if specified
        if language:
            select_language(page, language)

        # Add custom instructions if provided
        if instructions:
            print("    Adding custom instructions...")
            instructions_input, instr_selector = find_element_with_selectors(
                page, VIDEO_INSTRUCTIONS_SELECTORS, timeout=3000
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
            page, VIDEO_GENERATE_BUTTON_SELECTORS, timeout=5000
        )

        if not generate_button:
            # Try more specific selectors
            generate_button = page.query_selector('button.generate-button, button[type="submit"], button:has-text("Generate")')

        if not generate_button:
            print("     Could not find Generate button")
            page.screenshot(path="/tmp/notebooklm_video_debug.png")
            print("     Debug screenshot saved to /tmp/notebooklm_video_debug.png")
            return None

        print(f"     Found Generate button")

        # Wait for button to be enabled (it may be disabled initially)
        print("    Waiting for Generate button to be enabled...")
        try:
            page.wait_for_selector('button:has-text("Generate"):not([disabled])', timeout=10000)
        except Exception:
            print("     Generate button seems disabled, trying to click anyway...")

        StealthUtils.random_delay(500, 1000)

        # Scroll into view and wait for stability
        generate_button.scroll_into_view_if_needed()
        StealthUtils.random_delay(300, 500)

        try:
            generate_button.click(timeout=10000)
        except Exception as click_error:
            print(f"     Click failed: {click_error}")
            # Try JavaScript click as fallback
            try:
                page.evaluate('(el) => el.click()', generate_button)
                print("     Used JavaScript click fallback")
            except Exception as js_error:
                print(f"     JavaScript click also failed: {js_error}")
                page.screenshot(path="/tmp/notebooklm_generate_debug.png")
                print("     Debug screenshot saved to /tmp/notebooklm_generate_debug.png")
                return None

        print("    Started video generation...")

        # Wait for generation to complete (can take several minutes)
        print("    Waiting for video generation (this may take several minutes)...")
        generation_start = time.time()
        generation_timeout = VIDEO_GENERATION_TIMEOUT / 1000  # Convert to seconds

        # First, wait a few seconds for generation indicator to appear
        StealthUtils.random_delay(3000, 5000)

        last_print_time = 0
        while time.time() - generation_start < generation_timeout:
            # Check if still generating by looking for the generation indicator
            generating = False

            for selector in VIDEO_GENERATING_SELECTORS:
                try:
                    gen_indicator = page.query_selector(selector)
                    if gen_indicator and gen_indicator.is_visible():
                        generating = True
                        break
                except Exception:
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
                # Generation indicator disappeared - check if new video appeared
                print("    Generation indicator disappeared, verifying completion...")
                StealthUtils.random_delay(2000, 3000)

                # Double-check that generation is really complete
                still_generating = False
                for selector in VIDEO_GENERATING_SELECTORS:
                    try:
                        gen_indicator = page.query_selector(selector)
                        if gen_indicator and gen_indicator.is_visible():
                            still_generating = True
                            break
                    except Exception:
                        continue

                if not still_generating:
                    print("    Video generation complete!")
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

        # Find and click the three-dot menu on the most recently generated video
        print("    Looking for video menu...")

        # Use JavaScript to find the correct menu button in the Studio panel
        menu_clicked = page.evaluate("""
            () => {
                // Find all video items - they have metadata like "X source · Xm ago"
                const items = document.querySelectorAll('div');
                let targetButton = null;
                let mostRecent = null;

                for (const item of items) {
                    const text = item.textContent || '';
                    // Look for items that look like generated video
                    if ((text.includes('source') && (text.includes('ago') || text.includes('just now'))) ||
                        (text.includes('Explainer') && text.includes('source')) ||
                        (text.includes('Brief') && text.includes('source'))) {

                        // Check if this item is in the right part of the page (Studio panel)
                        const rect = item.getBoundingClientRect();
                        if (rect.x < 600) continue; // Studio panel is on the right

                        // Find the three-dot menu button within this item
                        const menuButtons = item.querySelectorAll('button');
                        for (const btn of menuButtons) {
                            const btnRect = btn.getBoundingClientRect();
                            if (btnRect.width < 50 && btnRect.height < 50) {
                                const ariaLabel = btn.getAttribute('aria-label') || '';
                                const innerHTML = btn.innerHTML || '';
                                if (ariaLabel.includes('option') || ariaLabel.includes('more') ||
                                    innerHTML.includes('more_vert') || innerHTML.includes('⋮')) {
                                    targetButton = btn;
                                    break;
                                }
                            }
                        }

                        if (targetButton) {
                            if (text.includes('just now') || text.includes('1m ago') || text.includes('2m ago')) {
                                mostRecent = targetButton;
                                break;
                            }
                            if (!mostRecent) mostRecent = targetButton;
                        }
                    }
                }

                if (mostRecent) {
                    mostRecent.click();
                    return true;
                }

                // Fallback
                const allButtons = document.querySelectorAll('button');
                for (const btn of allButtons) {
                    const rect = btn.getBoundingClientRect();
                    if (rect.x < 600) continue;

                    const ariaLabel = btn.getAttribute('aria-label') || '';
                    if (ariaLabel.toLowerCase().includes('option') || ariaLabel.toLowerCase().includes('more')) {
                        btn.click();
                        return true;
                    }
                }

                return false;
            }
        """)

        if not menu_clicked:
            print("     Could not find video menu button")
            page.screenshot(path="/tmp/notebooklm_menu_debug.png")
            print("     Debug screenshot saved to /tmp/notebooklm_menu_debug.png")
            return None

        print("     Clicked menu button")
        StealthUtils.random_delay(1000, 1500)

        # Click Download option from the menu
        print("    Looking for Download option...")
        print("    Waiting for download...")

        try:
            with page.expect_download(timeout=60000) as download_info:
                # Click Download in the menu
                download_clicked = page.evaluate("""
                    () => {
                        const menuItems = document.querySelectorAll('[role="menuitem"], li, button, span');
                        for (const item of menuItems) {
                            const text = item.textContent?.trim() || '';
                            if (text === 'Download') {
                                const rect = item.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    item.click();
                                    return true;
                                }
                            }
                        }
                        return false;
                    }
                """)

                if not download_clicked:
                    raise Exception("Could not find Download option")

            download = download_info.value
            suggested_name = download.suggested_filename
            print(f"     Download started: {suggested_name}")

            if output:
                download_path = f"{download_dir}/{output}"
            else:
                download_path = f"{download_dir}/{suggested_name}"

            download.save_as(download_path)
            print(f"     Saved to: {download_path}")

        except Exception as dl_error:
            print(f"     Download error: {dl_error}")
            page.screenshot(path="/tmp/notebooklm_download_menu_debug.png")
            print("     Debug screenshot saved to /tmp/notebooklm_download_menu_debug.png")
            download_path = None

        if download_path:
            print(f"   Video downloaded successfully: {download_path}")
            return download_path
        else:
            print("   Download failed")
            return None

    except Exception as e:
        print(f"   Error: {e}")
        traceback.print_exc()
        return None

    finally:
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
    parser = argparse.ArgumentParser(description='Generate NotebookLM Video Overview')

    # Notebook selection (mutually exclusive)
    notebook_group = parser.add_mutually_exclusive_group()
    notebook_group.add_argument('--notebook-url', help='NotebookLM notebook URL')
    notebook_group.add_argument('--notebook-id', help='Notebook ID from library')

    # Video customization
    parser.add_argument('--format', choices=['explainer', 'brief'],
                        default='explainer', help='Video format (default: explainer)')
    parser.add_argument('--style', choices=['auto', 'custom', 'classic', 'whiteboard', 'kawaii', 'anime'],
                        default='auto', help='Visual style (default: auto)')
    parser.add_argument('--language', help='Language for the video (e.g., English, Spanish, Japanese)')
    parser.add_argument('--instructions', help='Custom instructions/prompt for AI hosts')
    parser.add_argument('--sources', help='Comma-separated list of source names to include (deselects others)')
    parser.add_argument('--output', help='Custom output filename')
    parser.add_argument('--show-browser', action='store_true', help='Show browser window')

    args = parser.parse_args()

    # Resolve notebook URL
    library = NotebookLibrary()

    if args.notebook_id:
        notebook = library.get_notebook(args.notebook_id)
        if not notebook:
            print(f"Notebook not found: {args.notebook_id}")
            return 1
        notebook_url = notebook['url']
        notebook_name = notebook['name']
    elif args.notebook_url:
        notebook_url = args.notebook_url
        notebook_name = "Unknown"
    else:
        # Use active notebook
        active = library.get_active_notebook()
        if active:
            notebook_url = active['url']
            notebook_name = active['name']
            print(f"Using active notebook: {notebook_name}")
        else:
            print("No notebook specified and no active notebook set")
            return 1

    # Parse sources if provided
    sources_list = None
    if args.sources:
        sources_list = [s.strip() for s in args.sources.split(',')]

    result = generate_video(
        notebook_url=notebook_url,
        format=args.format,
        style=args.style,
        language=args.language,
        instructions=args.instructions,
        sources=sources_list,
        output=args.output,
        headless=not args.show_browser
    )

    if result:
        print("\n" + "=" * 60)
        print(" Video Overview Generated")
        print("=" * 60)
        print(f"File: {result}")
        print(f"Format: {args.format}")
        print(f"Style: {args.style}")
        if args.language:
            print(f"Language: {args.language}")
        if args.instructions:
            print(f"Instructions: {args.instructions[:50]}...")
        print("=" * 60)
        return 0
    else:
        print("\n Failed to generate video")
        return 1


if __name__ == "__main__":
    sys.exit(main())
