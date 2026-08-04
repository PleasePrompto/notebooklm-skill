"""
Configuration for NotebookLM Skill
Centralizes constants, selectors, and paths
"""

from pathlib import Path
from urllib.parse import urlparse

# Paths
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
BROWSER_STATE_DIR = DATA_DIR / "browser_state"
BROWSER_PROFILE_DIR = BROWSER_STATE_DIR / "browser_profile"
STATE_FILE = BROWSER_STATE_DIR / "state.json"
AUTH_INFO_FILE = DATA_DIR / "auth_info.json"
LIBRARY_FILE = DATA_DIR / "library.json"

# Product hosts.
# NotebookLM was rebranded to "Gemini Notebook" and moved to notebook.google.com.
# The old host still redirects, and saved notebook URLs in library.json may use
# either one, so both are accepted everywhere.
NOTEBOOK_HOSTS = (
    "notebook.google.com",       # Current (Gemini Notebook)
    "notebooklm.google.com",     # Legacy (redirects to the above)
)

# Default landing page used when signing in / validating a session
NOTEBOOK_HOME_URL = "https://notebook.google.com"


def is_notebook_url(url: str) -> bool:
    """
    True if the URL is a signed-in Notebook page.

    The single source of truth for "is this an authenticated Notebook URL" — used
    both for direct checks and as the wait_for_url() predicate. Excludes Google's
    sign-in pages and Notebook's own /login route: the latter is served on the
    Notebook host while the user is still logged out, so treating it as success
    would persist an unauthenticated session.
    """
    if not url:
        return False
    parsed = urlparse(url)
    # Equality on netloc, not a substring test: "notebook.google.com.evil.com"
    # must not be accepted as a Notebook host.
    if parsed.netloc not in NOTEBOOK_HOSTS:
        return False
    return not parsed.path.startswith("/login")


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
