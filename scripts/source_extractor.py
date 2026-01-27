#!/usr/bin/env python3
"""
Source Extractor for NotebookLM
Extracts source titles and their Source Guide summaries by clicking each source
"""

import argparse
import sys
import time
import re
import traceback
from pathlib import Path
from datetime import datetime

from patchright.sync_api import sync_playwright

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import SOURCE_SUMMARY_DIR, SOURCE_DETECTION_JS
from browser_utils import BrowserFactory, StealthUtils


def get_existing_sources(notebook_id: str) -> set:
    """
    Get set of source titles already in the summary file

    Args:
        notebook_id: ID of the notebook

    Returns:
        Set of source titles that already exist
    """
    summary_path = SOURCE_SUMMARY_DIR / f"{notebook_id}.md"
    existing_titles = set()

    if summary_path.exists():
        try:
            with open(summary_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Parse out source titles (lines starting with ###)
                for line in content.split('\n'):
                    if line.startswith('### '):
                        title = line[4:].strip()
                        existing_titles.add(title)
        except Exception as e:
            print(f"  ⚠️ Could not read existing summary: {e}")

    return existing_titles


def extract_sources(notebook_url: str, headless: bool = True, existing_titles: set = None) -> list:
    """
    Extract all sources and their Source Guide content from a NotebookLM notebook

    Args:
        notebook_url: NotebookLM notebook URL
        headless: Run browser in headless mode
        existing_titles: Set of titles to skip (already extracted)

    Returns:
        List of dicts with 'title' and 'summary' keys
    """
    if existing_titles is None:
        existing_titles = set()

    auth = AuthManager()

    if not auth.is_authenticated():
        print("⚠️ Not authenticated. Run: python3 scripts/run.py auth_manager.py setup")
        return []

    print(f"📚 Extracting sources from: {notebook_url}")

    playwright = None
    context = None
    sources = []

    try:
        # Start playwright
        playwright = sync_playwright().start()

        # Launch persistent browser context
        context = BrowserFactory.launch_persistent_context(
            playwright,
            headless=headless
        )

        # Navigate to notebook
        page = context.new_page()
        print("  🌐 Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded")

        # Wait for NotebookLM to load
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=15000)

        # Wait for the sources panel to load
        print("  ⏳ Waiting for sources panel...")
        time.sleep(5)  # Give the page time to fully render

        # Find all source items in the sidebar
        # NotebookLM uses a list of source items - we need to find them
        # The sources are typically in a scrollable list on the left

        # Try multiple selectors for source items
        source_selectors = [
            'div[data-source-id]',  # Sources with data attribute
            '.source-item',  # Class-based
            '.source-list-item',
            '[role="listitem"]',  # ARIA role
            'mat-list-item',  # Material list item
        ]

        source_elements = []
        for selector in source_selectors:
            try:
                elements = page.query_selector_all(selector)
                if elements and len(elements) > 0:
                    print(f"  ✓ Found {len(elements)} sources using: {selector}")
                    source_elements = elements
                    break
            except Exception:
                continue

        if not source_elements:
            # Try to find sources by looking for clickable items in the source panel
            print("  🔍 Trying alternative source detection...")

            # Look for the Sources header and find items below it
            try:
                # Wait a bit more for dynamic content
                time.sleep(4)

                # Try finding source titles directly - look for common patterns
                alt_selectors = [
                    '.source-title',
                    '.source-name',
                    '[data-testid*="source"]',
                    'button[class*="source"]',
                    'div[class*="source-list"] button',
                    'div[class*="source-list"] [role="button"]',
                ]

                for selector in alt_selectors:
                    source_elements = page.query_selector_all(selector)
                    if source_elements and len(source_elements) > 0:
                        print(f"  ✓ Found {len(source_elements)} sources using: {selector}")
                        break
            except Exception:
                pass

        if not source_elements:
            print("  ⚠️ Could not find source elements automatically.")
            print("  📸 Taking screenshot for debugging...")

            # Take a screenshot to help debug
            screenshot_path = SOURCE_SUMMARY_DIR / "debug_screenshot.png"
            SOURCE_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path))
            print(f"  📸 Screenshot saved: {screenshot_path}")

            # Try to get page HTML for debugging
            print("  🔍 Attempting to extract sources from page structure...")

            # Use JavaScript to find source elements
            source_data = page.evaluate("""
                () => {
                    const results = [];

                    // Look for source items in various ways
                    // Method 1: Find elements with source-related classes
                    const possibleSources = document.querySelectorAll('[class*="source"], [class*="Source"]');

                    // Method 2: Look for list items that might be sources
                    const listItems = document.querySelectorAll('mat-list-item, .mat-mdc-list-item, [role="listitem"]');

                    // Log what we find
                    console.log('Found possible sources:', possibleSources.length);
                    console.log('Found list items:', listItems.length);

                    // Return info about the page structure
                    return {
                        possibleSourcesCount: possibleSources.length,
                        listItemsCount: listItems.length,
                        bodyClasses: document.body.className,
                        mainContent: document.querySelector('main')?.innerHTML?.substring(0, 500) || 'No main element'
                    };
                }
            """)
            print(f"  📊 Page analysis: {source_data}")

            # If we have existing sources and can't find new ones, that's okay
            if existing_titles:
                print(f"  ℹ️ Could not check for new sources, but {len(existing_titles)} sources already exist")
                return []

            return []

        # First, get all source titles via shared JavaScript detection
        print("  📝 Collecting all source titles...")
        source_titles = page.evaluate(SOURCE_DETECTION_JS)

        if not source_titles:
            print("  ⚠️ Could not get source titles")
            return []

        total_sources = len(source_titles)

        # Filter out already extracted sources
        titles_to_extract = [t for t in source_titles if t not in existing_titles]
        skipped_count = total_sources - len(titles_to_extract)

        if skipped_count > 0:
            print(f"  📋 Found {total_sources} sources, {skipped_count} already extracted, {len(titles_to_extract)} to fetch")
        else:
            print(f"  📋 Found {total_sources} source titles to extract")

        if not titles_to_extract:
            print("  ✅ All sources already extracted!")
            return []

        for i, title in enumerate(titles_to_extract):
            try:
                print(f"  [{i+1}/{len(titles_to_extract)}] {title[:60]}...")

                # Navigate back to the notebook main page to ensure source list is visible
                if i > 0:
                    page.goto(notebook_url, wait_until="domcontentloaded")
                    time.sleep(4)  # Wait for sources panel to reload

                # Use Playwright locator to find and click the source by text
                try:
                    # Try to find the source by its text
                    source_locator = page.locator(f'text="{title}"').first
                    source_locator.click(timeout=5000)
                except Exception:
                    # Fallback: use JavaScript
                    clicked = page.evaluate("""
                        (title) => {
                            const elements = document.querySelectorAll('button, [role="button"], [role="listitem"], .source-title, .source-name, span, div');
                            for (const el of elements) {
                                const text = el.innerText?.trim();
                                if (text === title || (text && text.includes(title.substring(0, 20)))) {
                                    el.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    """, title)

                    if not clicked:
                        print(f"      ⚠️ Could not click source")
                        continue

                StealthUtils.random_delay(4000, 6000)  # Wait longer for Source Guide to load

                # Extract the Source Guide content
                source_guide_text = page.evaluate("""
                    () => {
                        // Look for the Source guide container specifically
                        // The Source Guide is typically in a collapsible section with specific structure

                        // Method 1: Find elements that contain "Source guide" header
                        const allElements = document.querySelectorAll('*');
                        let bestMatch = '';
                        let bestScore = 0;

                        for (const el of allElements) {
                            const text = el.innerText || '';

                            // Skip elements that are too short or too long
                            if (text.length < 100 || text.length > 3000) continue;

                            // Must contain "Source guide"
                            if (!text.includes('Source guide')) continue;

                            // Score based on how focused the content is
                            const hasSourceGuideHeader = text.startsWith('Source guide') ||
                                text.match(/^[\\s\\S]{0,50}Source guide/);

                            // Extract content after "Source guide" header
                            const guideIdx = text.indexOf('Source guide');
                            let content = text.substring(guideIdx + 12).trim();

                            // Remove topic chips at the end (short lines that are keywords)
                            const lines = content.split('\\n');
                            const cleanLines = [];
                            let foundContent = false;

                            for (const line of lines) {
                                const trimmed = line.trim();
                                if (trimmed.length === 0) continue;

                                // If this is a substantial line (part of the summary), keep it
                                if (trimmed.length > 50) {
                                    foundContent = true;
                                    cleanLines.push(trimmed);
                                } else if (foundContent && trimmed.length < 40) {
                                    // Short line after content = likely a topic chip, stop
                                    break;
                                }
                            }

                            const result = cleanLines.join(' ').trim();

                            // Score this result - prefer medium-length results with content
                            if (result.length > 100 && result.length < 2000) {
                                const score = result.length;
                                if (score > bestScore) {
                                    bestScore = score;
                                    bestMatch = result;
                                }
                            }
                        }

                        if (bestMatch) {
                            return bestMatch;
                        }

                        // Fallback: Look for any paragraph that seems like a summary
                        const paragraphs = document.querySelectorAll('p, div');
                        for (const p of paragraphs) {
                            const text = p.innerText?.trim();
                            if (text && text.length > 200 && text.length < 2000) {
                                // Check if it looks like a summary (full sentences)
                                if (text.includes('.') && !text.includes('Source guide')) {
                                    return text;
                                }
                            }
                        }

                        return '';
                    }
                """)

                if source_guide_text and len(source_guide_text) > 30:
                    sources.append({
                        'title': title,
                        'summary': source_guide_text
                    })
                    print(f"      ✓ Got summary ({len(source_guide_text)} chars)")
                else:
                    print(f"      ⚠️ No Source Guide found")
                    sources.append({
                        'title': title,
                        'summary': '(No Source Guide available)'
                    })

                # No need to navigate back - we'll reload the page at the start of next iteration

            except Exception as e:
                print(f"      ❌ Error: {e}")
                continue

        print(f"\n  ✅ Extracted {len(sources)} sources!")
        return sources

    except Exception as e:
        print(f"  ❌ Error: {e}")
        traceback.print_exc()
        return []

    finally:
        # Clean up
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


def save_sources_markdown(notebook_id: str, notebook_name: str, sources: list, merge: bool = True) -> Path:
    """
    Save extracted sources to a markdown file, optionally merging with existing

    Args:
        notebook_id: ID of the notebook
        notebook_name: Display name of the notebook
        sources: List of dicts with 'title' and 'summary'
        merge: If True, merge with existing file; if False, overwrite

    Returns:
        Path to the saved file
    """
    SOURCE_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SOURCE_SUMMARY_DIR / f"{notebook_id}.md"

    existing_sources = []

    # If merging, load existing sources
    if merge and output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse existing sources
            current_title = None
            current_summary_lines = []

            for line in content.split('\n'):
                if line.startswith('### '):
                    # Save previous source if exists
                    if current_title:
                        existing_sources.append({
                            'title': current_title,
                            'summary': '\n'.join(current_summary_lines).strip()
                        })
                    current_title = line[4:].strip()
                    current_summary_lines = []
                elif line.startswith('---'):
                    continue
                elif line.startswith('# Source Summary:') or line.startswith('**'):
                    continue
                elif current_title:
                    current_summary_lines.append(line)

            # Don't forget the last one
            if current_title:
                existing_sources.append({
                    'title': current_title,
                    'summary': '\n'.join(current_summary_lines).strip()
                })

            print(f"  📄 Loaded {len(existing_sources)} existing sources")
        except Exception as e:
            print(f"  ⚠️ Could not parse existing file: {e}")

    # Merge: add new sources to existing
    all_sources = existing_sources + sources
    total_count = len(all_sources)

    # Build markdown content
    content = f"""# Source Summary: {notebook_name}

**Notebook ID:** `{notebook_id}`
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Total Sources:** {total_count}

---

"""

    for source in all_sources:
        content += f"### {source['title']}\n\n"
        content += f"{source['summary']}\n\n"
        content += "---\n\n"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    if sources:
        print(f"✅ Added {len(sources)} new sources (total: {total_count})")
    print(f"✅ Saved to: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Extract sources from NotebookLM')

    parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    parser.add_argument('--notebook-id', help='Notebook ID from library')
    parser.add_argument('--show-browser', action='store_true', help='Show browser window')
    parser.add_argument('--force', action='store_true', help='Force re-extraction of all sources')

    args = parser.parse_args()

    # Resolve notebook
    notebook_url = args.notebook_url
    notebook_id = args.notebook_id
    notebook_name = "Unknown Notebook"

    library = NotebookLibrary()

    if not notebook_url and args.notebook_id:
        notebook = library.get_notebook(args.notebook_id)
        if notebook:
            notebook_url = notebook['url']
            notebook_name = notebook['name']
            notebook_id = notebook['id']
        else:
            print(f"❌ Notebook '{args.notebook_id}' not found")
            return 1

    if not notebook_url:
        # Use active notebook
        active = library.get_active_notebook()
        if active:
            notebook_url = active['url']
            notebook_name = active['name']
            notebook_id = active['id']
            print(f"📚 Using active notebook: {notebook_name}")
        else:
            print("❌ No notebook specified and no active notebook set")
            return 1

    # Get existing sources (unless force mode)
    existing_titles = set()
    if not args.force:
        existing_titles = get_existing_sources(notebook_id)
        if existing_titles:
            print(f"📄 Found {len(existing_titles)} existing sources in summary file")

    # Extract sources (only new ones)
    sources = extract_sources(
        notebook_url=notebook_url,
        headless=not args.show_browser,
        existing_titles=existing_titles
    )

    if sources:
        # Save to markdown (merge with existing)
        save_sources_markdown(notebook_id, notebook_name, sources, merge=True)
        return 0
    elif existing_titles:
        # No new sources, but we have existing ones - that's okay
        print("✅ No new sources to extract")
        return 0
    else:
        print("❌ No sources extracted")
        return 1


if __name__ == "__main__":
    sys.exit(main())
