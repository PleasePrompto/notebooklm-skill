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
AUDIO_GENERATION_TIMEOUT = 600000  # 10 minutes for audio generation

# ===========================================
# NOTEBOOK CREATION SELECTORS
# ===========================================
CREATE_NOTEBOOK_SELECTORS = [
    'button:has-text("Create new")',           # Homepage top-right blue button
    'button:has-text("Create notebook")',       # Inside notebook header
    '[aria-label="Create new notebook"]',
]

# ===========================================
# SOURCE MANAGEMENT SELECTORS
# ===========================================
ADD_SOURCE_SELECTORS = [
    'button:has-text("Add sources")',           # Left sidebar button with "+"
    'button:has-text("+ Add sources")',         # With plus sign
    '[aria-label="Add sources"]',
    'div:has-text("Add sources")',              # Div version
    '.add-sources-button',
]

WEB_SEARCH_INPUT_SELECTORS = [
    'input[placeholder*="Search the web"]',     # Web search input
    '[aria-label="Search the web for new sources"]',
]

# Source type buttons (in add source dialog)
SOURCE_TYPE_SELECTORS = {
    'web': ['button:has-text("Web")', '[aria-label="Web"]'],
    'text': ['button:has-text("Copied text")', 'button:has-text("Text")'],
}

# ===========================================
# AUDIO OVERVIEW SELECTORS
# ===========================================
# Studio panel - Audio Overview card
AUDIO_OVERVIEW_CARD_SELECTORS = [
    'div:has-text("Audio Overview")',           # Card in Studio panel
    '[aria-label="Audio Overview"]',
]

# Pencil/edit icon to open customize dialog
AUDIO_CUSTOMIZE_BUTTON_SELECTORS = [
    'button[aria-label="Customize Audio Overview"]',
    'div:has-text("Audio Overview") button',    # Pencil icon next to card
]

# Format selection in customize dialog
AUDIO_FORMAT_SELECTORS = {
    'deep_dive': ['div:has-text("Deep Dive")'],
    'brief': ['div:has-text("Brief")'],
    'critique': ['div:has-text("Critique")'],
    'debate': ['div:has-text("Debate")'],
}

# Length selection buttons
AUDIO_LENGTH_SELECTORS = {
    'short': ['button:has-text("Short")'],
    'default': ['button:has-text("Default")'],
    'long': ['button:has-text("Long")'],
}

# Custom instructions textarea
AUDIO_INSTRUCTIONS_SELECTORS = [
    'textarea[placeholder*="Things to try"]',
    'textarea[placeholder*="focus"]',
    '[aria-label="What should the AI hosts focus on"]',
]

# Generate button (blue)
AUDIO_GENERATE_BUTTON_SELECTORS = [
    'button:has-text("Generate")',
    '[aria-label="Generate"]',
]

# ===========================================
# AUDIO DOWNLOAD SELECTORS
# ===========================================
# Three-dot menu on generated audio
AUDIO_MENU_BUTTON_SELECTORS = [
    'button[aria-label="More options"]',
    'button:has([data-icon="more_vert"])',      # Vertical dots icon
]

# Download option in menu
AUDIO_DOWNLOAD_MENU_SELECTORS = [
    'li:has-text("Download")',
    'button:has-text("Download")',
    '[role="menuitem"]:has-text("Download")',
]

# ===========================================
# LOADING/PROGRESS INDICATORS
# ===========================================
AUDIO_GENERATING_SELECTORS = [
    '[aria-label="Generating"]',
    '.generating-indicator',
    'div:has-text("Generating")',
]
