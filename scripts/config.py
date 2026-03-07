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

# NotebookLM URLs
NOTEBOOKLM_PUBLIC_URL = "https://notebooklm.google"
NOTEBOOKLM_APP_URL = "https://notebooklm.google.com"
NOTEBOOKLM_BASE_URL = NOTEBOOKLM_APP_URL
NOTEBOOKLM_URL_REGEX = r"^https://notebooklm\.google(?:\.com)?(?:/|$)"

# Optional Google account hint for account chooser pages
NOTEBOOKLM_GOOGLE_ACCOUNT_ENV = "NOTEBOOKLM_GOOGLE_ACCOUNT"
NOTEBOOKLM_PROXY_URL_ENV = "NOTEBOOKLM_PROXY_URL"
NOTEBOOKLM_PROXY_BYPASS_ENV = "NOTEBOOKLM_PROXY_BYPASS"

# NotebookLM Selectors
QUERY_INPUT_SELECTORS = [
    "textarea.query-box-input",
    'textarea[aria-label="Feld für Anfragen"]',
    'textarea[aria-label="Input for queries"]',
]

RESPONSE_SELECTORS = [
    ".to-user-container .message-text-content",
    "[data-message-author='bot']",
    "[data-message-author='assistant']",
]

HOME_READY_SELECTORS = [
    'button[aria-label="Create new notebook"]',
    "mat-card.create-new-action-button",
    "div.my-projects-container project-button",
]

NOTEBOOK_READY_SELECTORS = [
    "input.title-input",
    "input[aria-label='Notebook title']",
    "button[aria-label='Share notebook']",
    "button[aria-label='Configure notebook']",
]

TITLE_INPUT_SELECTORS = [
    "input.title-input",
    "header input",
]

SOURCE_PANEL_READY_SELECTORS = [
    "input[type='file'][name='Filedata']",
    "input[type='file']",
    'textarea[aria-label="Enter URLs"]',
    'textarea[placeholder="Paste any links"]',
    'button:has-text("Upload files")',
    'button:has-text("Websites")',
    'button:has-text("Drive")',
    'button:has-text("Copied text")',
]

SOURCE_URL_TEXTAREA_SELECTORS = [
    'textarea[aria-label="Enter URLs"]',
    'textarea[placeholder="Paste any links"]',
]

SOURCE_FILE_INPUT_SELECTORS = [
    "input[type='file'][name='Filedata']",
    "input[type='file']",
]

CREATE_NOTEBOOK_BUTTON_SELECTORS = [
    'button[aria-label="Create new notebook"]',
    "mat-card.create-new-action-button",
]

# Browser Configuration
BROWSER_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--no-first-run',
    '--no-default-browser-check',
]

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

# Timeouts
LOGIN_TIMEOUT_MINUTES = 10
QUERY_TIMEOUT_SECONDS = 120
PAGE_LOAD_TIMEOUT = 30000
UI_SHORT_TIMEOUT_MS = 5000
UI_MEDIUM_TIMEOUT_MS = 10000
UI_LONG_TIMEOUT_MS = 30000
SOURCE_UPLOAD_TIMEOUT_SECONDS = 180
