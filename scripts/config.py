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

# Add Source Selectors
ADD_SOURCE_BUTTON_SELECTORS = [
    'button.add-source-button',
    'button[aria-label="Add source"]',
    'button:has-text("Add sources")',
    'button:has-text("Upload a source")',  # Empty notebook state
    'button:has-text("+ Add sources")',
]

# Paste Text Flow Selectors
PASTE_TEXT_CHIP_SELECTORS = [
    'mat-chip:has-text("Copied text")',
    'button:has-text("Copied text")',
    '[class*="chip"]:has-text("Copied text")',
]

PASTE_TEXT_TEXTAREA_SELECTORS = [
    'textarea.text-area',
    '[role="dialog"] textarea.mat-mdc-input-element',
    '[role="dialog"] textarea',
]

INSERT_BUTTON_SELECTORS = [
    '[role="dialog"] button:has-text("Insert")',
    'button[type="submit"]:has-text("Insert")',
    'button:has-text("Insert")',
]

CLOSE_DIALOG_BUTTON_SELECTORS = [
    'button[aria-label="Close dialog"]',
    '[role="dialog"] button:has-text("close")',
]

BACK_TO_SOURCES_BUTTON_SELECTORS = [
    'button[aria-label="Return to upload sources dialog"]',
    '[role="dialog"] button:has-text("arrow_back")',
]

# Source verification
SOURCE_ITEM_SELECTORS = [
    '.source-item',
    '[class*="source-list"] [class*="item"]',
    '.sources-list .source',
]

# URL Source Selectors (Website/YouTube)
URL_CHIP_SELECTORS = [
    'mat-chip:has-text("Website")',
    'mat-chip:has-text("YouTube")',
    'button:has-text("Website")',
    'button:has-text("YouTube")',
]

URL_INPUT_SELECTORS = [
    'textarea.text-area',
    'textarea[placeholder*="URL" i]',
    'textarea[placeholder*="Paste" i]',
    '[role="dialog"] textarea',
    'input[placeholder*="URL" i]',
]
