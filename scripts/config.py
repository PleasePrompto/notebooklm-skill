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
        'div:has(> div:text-is("Deep Dive"))',
        'div.format-card:has-text("Deep Dive")',
        '[data-format="deep_dive"]',
    ],
    'brief': [
        'div:has(> div:text-is("Brief"))',
        'div.format-card:has-text("Brief")',
        '[data-format="brief"]',
    ],
    'critique': [
        'div:has(> div:text-is("Critique"))',
        'div.format-card:has-text("Critique")',
        '[data-format="critique"]',
    ],
    'debate': [
        'div:has(> div:text-is("Debate"))',
        'div.format-card:has-text("Debate")',
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

AUDIO_LANGUAGE_DROPDOWN_SELECTORS = [
    'div:has-text("Choose language") + div',
    '[aria-label*="language"]',
    '[aria-haspopup="listbox"]',
    'mat-select',
    '.language-select',
]

# Language name mapping: English name -> NotebookLM display name (native script)
# Based on NotebookLM's language dropdown options
LANGUAGE_MAP = {
    # East Asian
    'japanese': '日本語',
    'chinese': '中文（简体）',
    'simplified chinese': '中文（简体）',
    'traditional chinese': '中文（繁體）',
    'korean': '한국어',

    # European - Latin script
    'english': 'English',
    'spanish': 'español',
    'french': 'français',
    'german': 'Deutsch',
    'italian': 'italiano',
    'portuguese': 'português',
    'dutch': 'Nederlands',
    'polish': 'polski',
    'swedish': 'svenska',
    'danish': 'dansk',
    'norwegian': 'norsk',
    'finnish': 'suomi',
    'czech': 'čeština',
    'romanian': 'română',
    'hungarian': 'magyar',
    'turkish': 'Türkçe',
    'indonesian': 'Indonesia',
    'vietnamese': 'Tiếng Việt',
    'malay': 'Melayu',
    'tagalog': 'Tagalog',
    'estonian': 'eesti',
    'latvian': 'latviešu',
    'lithuanian': 'lietuvių',
    'slovenian': 'slovenščina',
    'croatian': 'hrvatski',
    'slovak': 'slovenčina',
    'catalan': 'català',
    'haitian creole': 'créole haïtien',

    # Cyrillic
    'russian': 'русский',
    'ukrainian': 'українська',
    'bulgarian': 'български',

    # Other scripts
    'arabic': 'العربية',
    'hebrew': 'עברית',
    'hindi': 'हिन्दी',
    'thai': 'ไทย',
    'greek': 'Ελληνικά',
    'bengali': 'বাংলা',
    'tamil': 'தமிழ்',
    'telugu': 'తెలుగు',
    'marathi': 'मराठी',
    'gujarati': 'ગુજરાતી',
    'kannada': 'ಕನ್ನಡ',
    'malayalam': 'മലയാളം',
    'punjabi': 'ਪੰਜਾਬੀ',
    'urdu': 'اردو',
    'persian': 'فارسی',
    'farsi': 'فارسی',
    'swahili': 'Kiswahili',
    'afrikaans': 'Afrikaans',
}

def get_language_display_name(language: str) -> str:
    """
    Get the NotebookLM display name for a language.

    Args:
        language: Language name in English (case-insensitive) or native script

    Returns:
        The display name used in NotebookLM's dropdown
    """
    # Check if it's already a native script name (pass through)
    if language in LANGUAGE_MAP.values():
        return language

    # Look up by English name (case-insensitive)
    return LANGUAGE_MAP.get(language.lower(), language)

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

# Video Overview Selectors
VIDEO_GENERATION_TIMEOUT = 900000  # 15 minutes for video generation

VIDEO_OVERVIEW_CARD_SELECTORS = [
    'div:has-text("Video Overview")',
    '[aria-label="Video Overview"]',
]

VIDEO_CUSTOMIZE_BUTTON_SELECTORS = [
    'button[aria-label="Customize Video Overview"]',
    'div:has-text("Video Overview") button',
]

VIDEO_FORMAT_SELECTORS = {
    'explainer': [
        'div:has-text("Explainer")',
        '[data-format="explainer"]',
    ],
    'brief': [
        'div:has-text("Brief")',
        '[data-format="brief"]',
    ],
}

VIDEO_STYLE_SELECTORS = {
    'auto': [
        'div:has-text("Auto-select")',
        '[data-style="auto"]',
    ],
    'custom': [
        'div:has-text("Custom")',
        '[data-style="custom"]',
    ],
    'classic': [
        'div:has-text("Classic")',
        '[data-style="classic"]',
    ],
    'whiteboard': [
        'div:has-text("Whiteboard")',
        '[data-style="whiteboard"]',
    ],
    'kawaii': [
        'div:has-text("Kawaii")',
        '[data-style="kawaii"]',
    ],
    'anime': [
        'div:has-text("Anime")',
        '[data-style="anime"]',
    ],
}

VIDEO_LANGUAGE_DROPDOWN_SELECTORS = [
    'div:has-text("Choose language") + div',
    '[aria-label*="language"]',
    '[aria-haspopup="listbox"]',
    'mat-select',
    '.language-select',
]

VIDEO_INSTRUCTIONS_SELECTORS = [
    'textarea[placeholder*="Things to try"]',
    'textarea[placeholder*="focus"]',
    '[aria-label*="What should the AI hosts focus on"]',
    'textarea',
]

VIDEO_GENERATE_BUTTON_SELECTORS = [
    'button:has-text("Generate")',
    '[aria-label="Generate"]',
    'button.generate-button',
]

VIDEO_MENU_BUTTON_SELECTORS = [
    'button[aria-label="More options"]',
    'button[aria-label="Options"]',
    'button:has([data-icon="more_vert"])',
]

VIDEO_DOWNLOAD_MENU_SELECTORS = [
    '[role="menuitem"]:has-text("Download")',
    'li:has-text("Download")',
    'button:has-text("Download")',
    'div:has-text("Download")',
]

VIDEO_GENERATING_SELECTORS = [
    'div:has-text("Generating Video Overview")',
    ':text("Generating Video Overview")',
    ':text("Come back in a few minutes")',
    '[aria-label="Generating"]',
]

# Shared JavaScript for source detection from UI
# Used by list_sources.py and source_extractor.py
SOURCE_DETECTION_JS = """
() => {
    const sources = [];
    const seenTexts = new Set();

    // UI text to skip (exact matches)
    const skipTexts = new Set(['check_box', 'more_vert', 'description', 'drive_pdf',
                       'markdown', 'web', 'select all', 'select all sources',
                       'sources', 'add source', 'add sources', 'video_youtube', 'link', 'pdf',
                       'more', 'less', 'expand', 'collapse', 'chat', 'studio',
                       'save to note', 'try deep research for an in-depth report and new sources!']);

    // Helper to check if text is a valid source name
    const isValidSource = (text) => {
        if (!text || text.length < 3 || text.length > 150) return false;
        if (text.includes('\\n')) return false;

        // Skip UI elements (exact match, case insensitive)
        if (skipTexts.has(text.toLowerCase())) return false;

        // Skip if it starts with bullet points or looks like content
        if (text.startsWith('•') || text.startsWith('-') || text.startsWith('*')) return false;
        if (text.startsWith('How ') || text.startsWith('What ') || text.startsWith('Based on')) return false;

        return true;
    };

    // Primary method: Find checkbox elements and extract source titles from their rows
    const checkboxes = document.querySelectorAll('mat-checkbox, [role="checkbox"]');

    for (const checkbox of checkboxes) {
        const rect = checkbox.getBoundingClientRect();
        // Must be in left panel (x < 450) - filters out main content
        if (rect.x > 450 || rect.x < 0) continue;

        // Get the row container (parent that contains both title and checkbox)
        let row = checkbox.parentElement;
        for (let i = 0; i < 4 && row; i++) {
            const rowRect = row.getBoundingClientRect();
            // Row should be reasonably sized (not too tall = contains multiple items)
            if (rowRect.height > 30 && rowRect.height < 80) {
                break;
            }
            row = row.parentElement;
        }

        if (!row) continue;

        // Extract the title from this row
        const textElements = row.querySelectorAll('span, div');
        for (const el of textElements) {
            const text = el.innerText?.trim();
            if (!text) continue;

            // Skip if too short or contains multiple lines
            if (text.length < 3 || text.length > 150) continue;
            if (text.includes('\\n')) continue;

            // Skip icon text
            if (skipTexts.has(text.toLowerCase())) continue;

            // This is likely the source title
            if (!seenTexts.has(text) && isValidSource(text)) {
                seenTexts.add(text);
                sources.push(text);
                break;  // Found title for this row
            }
        }
    }

    // Fallback: If we didn't find enough, try looking for .source-title class
    if (sources.length < 3) {
        const titleElements = document.querySelectorAll('.source-title, .source-name, [class*="source"][class*="title"]');
        for (const el of titleElements) {
            const text = el.innerText?.trim();
            if (text && isValidSource(text) && !seenTexts.has(text)) {
                seenTexts.add(text);
                sources.push(text);
            }
        }
    }

    return sources;
}
"""
