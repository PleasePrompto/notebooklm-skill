"""
Configuration for NotebookLM Skill
Centralizes constants, selectors, and paths
"""

from pathlib import Path

# Paths
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
BROWSER_STATE_DIR = DATA_DIR / "browser_state"
BROWSER_PROFILE_DIR = BROWSER_STATE_DIR / "browser_profile"
STATE_FILE = BROWSER_STATE_DIR / "state.json"
AUTH_INFO_FILE = DATA_DIR / "auth_info.json"
LIBRARY_FILE = DATA_DIR / "library.json"
SOURCE_SUMMARY_DIR = DATA_DIR / "library-source-summary"

# Source Summary Query
SOURCE_SUMMARY_QUERY = """List ALL the sources/documents in this notebook. For each source, provide:
1. The exact source name/title as shown in NotebookLM
2. A brief 1-2 sentence summary of what that source contains

Format your response as a markdown table with these columns:
| Source Name | Summary |
|-------------|---------|

Include EVERY source in this notebook, even if there are many."""

# NotebookLM Selectors
QUERY_INPUT_SELECTORS = [
    "textarea.query-box-input",  # Primary
    'textarea[aria-label="Feld für Anfragen"]',  # Fallback German
    'textarea[aria-label="Input for queries"]',  # Fallback English
]

RESPONSE_SELECTORS = [
    ".to-user-container .message-text-content",  # Primary
    "[data-message-author='bot']",
    "[data-message-author='assistant']",
]

# Add Source Dialog Selectors (based on NotebookLM UI Jan 2026)
ADD_SOURCE_BUTTON_SELECTORS = [
    'button:has-text("Add source")',
    'button:has-text("Add sources")',
    'button[aria-label*="Add source"]',
    'button[aria-label*="Add sources"]',
    '[data-test-id="add-source-button"]',
]

# Main dialog option buttons
UPLOAD_FILES_BUTTON_SELECTORS = [
    'button:has-text("Upload files")',
    '[aria-label*="Upload files"]',
    'button:has-text("Upload")',
]

WEBSITES_BUTTON_SELECTORS = [
    'button:has-text("Websites")',
    '[aria-label*="Websites"]',
    'button:has-text("Website")',
]

COPIED_TEXT_BUTTON_SELECTORS = [
    'button:has-text("Copied text")',
    '[aria-label*="Copied text"]',
    'button:has-text("Paste")',
]

# Input fields
URL_TEXTAREA_SELECTORS = [
    'textarea[placeholder*="Paste any links"]',
    'textarea[placeholder*="link"]',
    'textarea[placeholder*="URL"]',
    'textarea',
]

TEXT_TEXTAREA_SELECTORS = [
    'textarea[placeholder*="Paste"]',
    'textarea[placeholder*="paste"]',
    'textarea',
]

# Action buttons
INSERT_BUTTON_SELECTORS = [
    'button:has-text("Insert")',
    'button:has-text("Add")',
    'button[type="submit"]',
]

CLOSE_DIALOG_SELECTORS = [
    'button[aria-label="Close"]',
    'button:has-text("Close")',
    '[aria-label="close"]',
]

# Browser Configuration
BROWSER_ARGS = [
    '--disable-blink-features=AutomationControlled',  # Patches navigator.webdriver
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--no-first-run',
    '--no-default-browser-check'
]

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

# Timeouts
LOGIN_TIMEOUT_MINUTES = 10
QUERY_TIMEOUT_SECONDS = 120
PAGE_LOAD_TIMEOUT = 30000
