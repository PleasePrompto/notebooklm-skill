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
AUDIO_GENERATION_TIMEOUT = 900000  # 15 minutes for audio generation

# Audio Overview Selectors
AUDIO_OVERVIEW_CARD_SELECTORS = [
    'div:has-text("Audio Overview")',
    '[aria-label="Audio Overview"]',
]

AUDIO_CUSTOMIZE_BUTTON_SELECTORS = [
    'button[aria-label="Customize Audio Overview"]',
    'div:has-text("Audio Overview") button',
]

AUDIO_FORMAT_SELECTORS = {
    'deep_dive': [
        'div:has-text("Deep Dive")',
        '[data-format="deep_dive"]',
    ],
    'brief': [
        'div:has-text("Brief")',
        '[data-format="brief"]',
    ],
    'critique': [
        'div:has-text("Critique")',
        '[data-format="critique"]',
    ],
    'debate': [
        'div:has-text("Debate")',
        '[data-format="debate"]',
    ],
}

AUDIO_LENGTH_SELECTORS = {
    'short': [
        'button:has-text("Short")',
        '[data-length="short"]',
    ],
    'default': [
        'button:has-text("Default")',
        '[data-length="default"]',
    ],
    'long': [
        'button:has-text("Long")',
        '[data-length="long"]',
    ],
}

AUDIO_INSTRUCTIONS_SELECTORS = [
    'textarea[placeholder*="Things to try"]',
    'textarea[placeholder*="focus"]',
    '[aria-label*="What should the AI hosts focus on"]',
    'textarea',
]

AUDIO_GENERATE_BUTTON_SELECTORS = [
    'button:has-text("Generate")',
    '[aria-label="Generate"]',
    'button.generate-button',
]

AUDIO_MENU_BUTTON_SELECTORS = [
    'button[aria-label="More options"]',
    'button[aria-label="Options"]',
    'button:has([data-icon="more_vert"])',
]

AUDIO_DOWNLOAD_MENU_SELECTORS = [
    '[role="menuitem"]:has-text("Download")',
    'li:has-text("Download")',
    'button:has-text("Download")',
    'div:has-text("Download")',
]

AUDIO_GENERATING_SELECTORS = [
    'div:has-text("Generating Audio Overview")',
    ':text("Generating Audio Overview")',
    ':text("Come back in a few minutes")',
    '[aria-label="Generating"]',
]

# Source Management Selectors (for removing/renaming sources)
SOURCE_ITEM_SELECTORS = [
    '[data-test-id="source-item"]',
    '.source-item',
    'div[role="listitem"]',
]

SOURCE_MENU_BUTTON_SELECTORS = [
    'button[aria-label="More options"]',
    'button[aria-label="Source options"]',
    'button:has([data-icon="more_vert"])',
    'button:has-text("⋮")',
]

SOURCE_REMOVE_MENU_SELECTORS = [
    '[role="menuitem"]:has-text("Remove source")',
    'li:has-text("Remove source")',
    'button:has-text("Remove source")',
    'div:has-text("Remove source")',
]

SOURCE_CONFIRM_REMOVE_SELECTORS = [
    'button:has-text("Remove")',
    'button:has-text("Delete")',
    'button:has-text("Confirm")',
    '[data-action="confirm-remove"]',
]
