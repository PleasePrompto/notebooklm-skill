#!/usr/bin/env python3
"""
Add Sources to NotebookLM from Google Drive
Automatically adds new files from a Google Drive folder to a NotebookLM notebook
"""

import sys
import json
import time
import argparse
from pathlib import Path
from typing import List, Optional

from patchright.sync_api import sync_playwright, Page, BrowserContext

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from browser_utils import BrowserFactory, StealthUtils
from config import STATE_FILE


class SourceAdder:
    """Adds sources from Google Drive to NotebookLM notebooks"""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.stealth = StealthUtils()
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.main_page: Optional[Page] = None  # Keep reference to main page
        self.playwright = None

    def __enter__(self):
        self.playwright = sync_playwright().start()
        self.context = BrowserFactory.launch_persistent_context(
            self.playwright,
            headless=self.headless
        )
        self.page = self.context.new_page()
        self.main_page = self.page  # Save reference
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.main_page:
            try:
                self.main_page.close()
            except:
                pass
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()

    def add_sources_from_drive(
        self,
        notebook_url: str,
        drive_folder: str,
        file_names: Optional[List[str]] = None
    ) -> dict:
        """
        Add sources from a Google Drive folder to a NotebookLM notebook

        Args:
            notebook_url: The NotebookLM notebook URL
            drive_folder: Path in Google Drive (e.g., "NotebookLM-Sources/Argus")
            file_names: Optional list of specific files to add (adds all if None)

        Returns:
            Dict with status and details
        """
        try:
            print(f"🚀 Opening notebook: {notebook_url}")
            self.page.goto(notebook_url, wait_until="domcontentloaded", timeout=30000)

            # Check if login needed
            if "accounts.google.com" in self.page.url:
                raise RuntimeError("Authentication required. Run auth_manager.py setup first.")

            # Wait for page to load
            self.stealth.random_delay(2000, 3000)

            # Click "Add source" button (新增來源)
            print("📎 Looking for Add source button...")
            add_source_btn = self._find_add_source_button()
            if not add_source_btn:
                raise RuntimeError("Could not find Add source button")

            add_source_btn.click()
            self.stealth.random_delay(1000, 1500)

            # Click Google Drive option
            print("📁 Selecting Google Drive...")
            drive_option = self._find_drive_option()
            if not drive_option:
                raise RuntimeError("Could not find Google Drive option")

            drive_option.click()
            self.stealth.random_delay(3000, 4000)

            # Check if Drive picker is in an iframe
            self._switch_to_picker_iframe()

            # Navigate to folder in Drive picker
            print(f"📂 Navigating to: {drive_folder}")
            self._navigate_to_drive_folder(drive_folder)

            # Select files
            print("📄 Selecting files...")
            selected_count = self._select_files(file_names)

            if selected_count == 0:
                print("⚠️ No files found to add")
                return {
                    "status": "no_files",
                    "message": "No new files found in folder",
                    "notebook_url": notebook_url,
                    "drive_folder": drive_folder
                }

            # Click Insert/Add button
            print(f"✅ Adding {selected_count} files...")
            self._click_insert_button()

            # Wait for processing
            self.stealth.random_delay(3000, 5000)

            print(f"✅ Successfully added {selected_count} sources!")
            return {
                "status": "success",
                "files_added": selected_count,
                "notebook_url": notebook_url,
                "drive_folder": drive_folder
            }

        except Exception as e:
            print(f"❌ Error: {e}")
            # Take screenshot for debugging
            try:
                screenshot_path = Path(__file__).parent.parent / "data" / "error_screenshot.png"
                self.page.screenshot(path=str(screenshot_path))
                print(f"📸 Screenshot saved: {screenshot_path}")
            except:
                pass
            return {
                "status": "error",
                "error": str(e),
                "notebook_url": notebook_url
            }

    def _switch_to_picker_iframe(self):
        """Switch to Google Picker iframe if present"""
        try:
            # Look for picker iframe
            iframes = self.page.query_selector_all('iframe')
            print(f"  Found {len(iframes)} iframes")

            for iframe in iframes:
                src = iframe.get_attribute('src') or ''
                name = iframe.get_attribute('name') or ''
                print(f"  Iframe: src={src[:50]}..., name={name}")

                # Google Picker iframes usually have these patterns
                if 'picker' in src.lower() or 'drive' in src.lower() or 'docs.google' in src:
                    frame = iframe.content_frame()
                    if frame:
                        self.page = frame
                        print("  ✓ Switched to picker iframe")
                        self._take_debug_screenshot("inside_iframe")
                        return True

            print("  No picker iframe found, staying on main page")
            return False
        except Exception as e:
            print(f"  ⚠️ Iframe handling error: {e}")
            return False

    def _find_add_source_button(self):
        """Find the Add source button"""
        # Try various selectors for Add source button
        selectors = [
            'button:has-text("新增來源")',
            'button:has-text("Add source")',
            'button:has-text("新增")',
            '[aria-label="Add source"]',
            '[aria-label="新增來源"]',
            'button.add-source-button',
            # Fallback: look for plus icon button
            'button:has(mat-icon:has-text("add"))',
        ]

        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    return element
            except:
                continue

        # Try finding by text content
        buttons = self.page.query_selector_all('button')
        for btn in buttons:
            try:
                text = btn.inner_text().lower()
                if '新增' in text or 'add' in text or 'source' in text:
                    if btn.is_visible():
                        return btn
            except:
                continue

        return None

    def _find_drive_option(self):
        """Find the Google Drive option in the source picker"""
        self._take_debug_screenshot("before_drive_click")

        # First, try to find the exact "Google 雲端硬碟" chip/button
        # It appears as a clickable chip inside the Google Workspace section
        try:
            # Try using locator with text
            drive_btn = self.page.locator('text="Google 雲端硬碟"').first
            if drive_btn and drive_btn.is_visible():
                print("  Found: Google 雲端硬碟 via locator")
                return drive_btn
        except:
            pass

        try:
            drive_btn = self.page.locator('text="Google Drive"').first
            if drive_btn and drive_btn.is_visible():
                print("  Found: Google Drive via locator")
                return drive_btn
        except:
            pass

        # Try query selector with various patterns
        selectors = [
            'div:has-text("Google 雲端硬碟")',
            'span:has-text("Google 雲端硬碟")',
            'button:has-text("Google 雲端硬碟")',
            '[data-value="google_drive"]',
            '.source-option:has-text("雲端硬碟")',
        ]

        for selector in selectors:
            try:
                elements = self.page.query_selector_all(selector)
                for element in elements:
                    if element.is_visible():
                        text = element.inner_text()
                        if '雲端硬碟' in text or 'Drive' in text:
                            print(f"  Found via selector: {selector}")
                            return element
            except:
                continue

        # Fallback: find all clickable elements and look for Drive text
        clickables = self.page.query_selector_all('div, span, button, a')
        for elem in clickables:
            try:
                text = elem.inner_text()
                # Look for exact match to avoid matching parent containers
                if text.strip() == 'Google 雲端硬碟' or text.strip() == 'Google Drive':
                    if elem.is_visible():
                        box = elem.bounding_box()
                        if box and box['width'] > 50 and box['height'] > 20:
                            print(f"  Found clickable: {text.strip()}")
                            return elem
            except:
                continue

        print("  ⚠️ Could not find Google Drive option")
        return None

    def _navigate_to_drive_folder(self, folder_path: str):
        """Navigate through Google Drive folder structure using search"""
        # Wait for Drive picker to load
        self.stealth.random_delay(2000, 3000)
        self._take_debug_screenshot("drive_picker_opened")

        # Use search bar to find the folder directly
        last_folder = folder_path.split('/')[-1]
        print(f"  🔍 Searching for folder: {last_folder}")

        # Find and click the search input
        try:
            search_input = self.page.query_selector('input[type="text"]')
            if search_input and search_input.is_visible():
                search_input.click()
                self.stealth.random_delay(300, 500)
                search_input.fill(last_folder)
                self.stealth.random_delay(500, 800)
                self.main_page.keyboard.press("Enter")  # Use main_page for keyboard
                self.stealth.random_delay(2000, 3000)
                print(f"  ✓ Searched for: {last_folder}")
                self._take_debug_screenshot("after_search")

                # Now find and double-click the folder in search results
                try:
                    folder_result = self.page.locator(f'text="{last_folder}"').first
                    if folder_result and folder_result.is_visible():
                        folder_result.dblclick()
                        self.stealth.random_delay(2000, 3000)
                        print(f"  ✓ Entered folder: {last_folder}")
                        self._take_debug_screenshot("inside_folder")
                        return
                except:
                    pass
        except Exception as e:
            print(f"  ⚠️ Search failed: {e}")

        # Fallback: Try clicking the tab approach
        print("  📁 Trying tab navigation...")

        # Click 我的雲端硬碟 tab by finding the tab bar
        try:
            tabs = self.page.query_selector_all('[role="tab"], .tab-item, div[data-tab]')
            for tab in tabs:
                text = tab.inner_text()
                if '我的雲端硬碟' in text or 'My Drive' in text:
                    tab.click()
                    self.stealth.random_delay(1500, 2000)
                    print(f"  ✓ Clicked tab: {text}")
                    self._take_debug_screenshot("after_tab_click")
                    break
        except:
            pass

        # Navigate through folders
        folders = folder_path.split('/')
        for folder_name in folders:
            if not folder_name:
                continue

            self.stealth.random_delay(1000, 1500)
            print(f"  📂 Looking for folder: {folder_name}")

            clicked = False
            try:
                folder_elem = self.page.locator(f'text="{folder_name}"').first
                if folder_elem and folder_elem.is_visible():
                    folder_elem.dblclick()
                    clicked = True
                    print(f"  ✓ Entered folder: {folder_name}")
                    self.stealth.random_delay(1500, 2000)
            except:
                pass

            if not clicked:
                self._take_debug_screenshot(f"could_not_find_{folder_name}")
                print(f"  ⚠️ Could not find folder: {folder_name}")

    def _take_debug_screenshot(self, name: str):
        """Take a debug screenshot"""
        try:
            screenshot_dir = Path(__file__).parent.parent / "data" / "debug_screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = screenshot_dir / f"{name}.png"
            # Use main_page for screenshots (Frame doesn't support screenshot)
            self.main_page.screenshot(path=str(path))
            print(f"  📸 Screenshot: {path.name}")
        except Exception as e:
            print(f"  ⚠️ Screenshot failed: {e}")

    def _select_files(self, file_names: Optional[List[str]] = None) -> int:
        """Select files in the Drive picker"""
        self.stealth.random_delay(1500, 2000)
        self._take_debug_screenshot("before_file_selection")

        selected = 0

        try:
            # Find all clickable items in the picker
            # Look for file items (usually divs with specific classes or data attributes)
            file_items = self.page.query_selector_all('[role="option"], [role="gridcell"], .picker-item, div[data-id]')
            print(f"  Found {len(file_items)} potential items")

            for item in file_items:
                try:
                    text = item.inner_text().strip()

                    # Skip navigation elements and folders
                    skip_texts = ['My Drive', '我的雲端硬碟', '資料夾', 'folder', '近期存取', 'Recent']
                    if any(skip in text for skip in skip_texts):
                        continue

                    # Look for files (PDF, doc, etc.) - check if text contains file extension or is a document
                    is_file = any(ext in text.lower() for ext in ['.pdf', '.doc', '.txt', '.md', '投顧', '簡報', '月報', 'ms_', 'Semi', 'NVDA', 'Alchip', 'ASML'])

                    if not is_file:
                        continue

                    # If specific files requested, check if this is one of them
                    if file_names:
                        if not any(fn in text for fn in file_names):
                            continue

                    # Click to select (Ctrl+Click for multi-select on Mac use Meta/Cmd)
                    modifier = ["Meta"] if selected > 0 else []  # Cmd key on Mac
                    item.click(modifiers=modifier)
                    selected += 1
                    print(f"  ✓ Selected: {text[:60]}...")
                    self.stealth.random_delay(300, 500)

                except Exception as e:
                    continue

            if selected == 0:
                # Try alternative approach: click on visible thumbnails
                thumbnails = self.page.query_selector_all('img[src*="thumbnail"], .picker-thumbnail')
                print(f"  Trying thumbnails: found {len(thumbnails)}")
                for thumb in thumbnails[:10]:  # Limit to first 10
                    try:
                        # Click parent of thumbnail
                        parent = thumb.evaluate_handle('el => el.parentElement').as_element()
                        if parent:
                            text = parent.inner_text()
                            if any(ext in text.lower() for ext in ['.pdf', 'ms_', 'sino', '投顧', '月報']):
                                modifier = ["Meta"] if selected > 0 else []
                                parent.click(modifiers=modifier)
                                selected += 1
                                print(f"  ✓ Selected via thumbnail: {text[:40]}...")
                                self.stealth.random_delay(300, 500)
                    except:
                        continue

        except Exception as e:
            print(f"  ⚠️ Error selecting files: {e}")

        self._take_debug_screenshot("after_file_selection")
        return selected

    def _click_insert_button(self):
        """Click the Insert/Add button to confirm selection"""
        selectors = [
            'button:has-text("插入")',
            'button:has-text("Insert")',
            'button:has-text("選取")',
            'button:has-text("Select")',
            'button:has-text("新增")',
            'button:has-text("Add")',
            'button[data-mdc-dialog-action="accept"]',
            'button.primary-button',
        ]

        for selector in selectors:
            try:
                btn = self.page.query_selector(selector)
                if btn and btn.is_visible():
                    btn.click()
                    print(f"  ✓ Clicked button: {selector}")
                    return
            except:
                continue

        # Fallback: press Enter
        self.main_page.keyboard.press("Enter")
        print("  ✓ Pressed Enter as fallback")


def main():
    parser = argparse.ArgumentParser(description='Add sources to NotebookLM from Google Drive')
    parser.add_argument('--notebook-url', required=True, help='NotebookLM notebook URL')
    parser.add_argument('--drive-folder', required=True, help='Google Drive folder path')
    parser.add_argument('--files', nargs='*', help='Specific file names to add (optional)')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')

    args = parser.parse_args()

    print("\n🔧 NotebookLM Source Adder")
    print("=" * 40)

    with SourceAdder(headless=args.headless) as adder:
        result = adder.add_sources_from_drive(
            notebook_url=args.notebook_url,
            drive_folder=args.drive_folder,
            file_names=args.files
        )

    print("\n📊 Result:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0 if result.get('status') == 'success' else 1


if __name__ == "__main__":
    sys.exit(main())
