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

# Source Management Selectors
SOURCE_ITEM_SELECTOR = "button.source-stretched-button"
MORE_VERT_SELECTOR = 'button:has-text("more_vert")'
REMOVE_MENU_SELECTOR = "[role='menuitem']:has-text('Remove')"
DELETE_DIALOG_SELECTOR = "mat-dialog-container"
WEBSITE_URL_INPUT_SELECTOR = "[formcontrolname='urls']"
COPIED_TEXT_INPUT_SELECTOR = "textarea[placeholder='Paste text here']"

# Notebook Management Selectors (homepage)
NOTEBOOK_CARD_SELECTOR = "mat-card.project-button-card"
NOTEBOOK_LINK_SELECTOR = "a[href*='/notebook/']"
NOTEBOOK_MENU_SELECTOR = "button[aria-label='Project Actions Menu']"
NOTEBOOK_TITLE_FC_SELECTOR = "[formcontrolname='title']"
NOTEBOOKLM_HOME_URL = "https://notebooklm.google.com/"

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
