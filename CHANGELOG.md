# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-01-24

### Added
- **Intelligent Source Filtering** - LLM-based relevance scoring before each query
  - Uses Gemini or Claude to score each source (1-10) based on semantic relevance
  - Automatically deselects irrelevant sources in browser for faster responses
  - Fallback chain: Gemini CLI → Claude CLI → keyword matching
  - Configurable threshold (`--threshold N`) for filtering sensitivity
  - `--keyword-filter` flag to use keyword matching instead of LLM
  - `--no-filter` flag to disable filtering entirely

- **Source Summary Caching** - Automated extraction and caching of source metadata
  - New `source_extractor.py` - Click-based extraction of Source Guide content
  - New `source_filter.py` - LLM scoring and browser checkbox automation
  - Auto-extracts source summaries when adding notebooks
  - Cached in `data/library-source-summary/{notebook-id}.md`
  - Incremental updates - only fetches NEW sources not in cache

- **Source Management Commands**
  - `update-sources --id ID` - Update source summary for a notebook
  - `update-sources --id ID --force` - Re-extract all sources
  - `update-sources --all` - Update all notebooks
  - `show-sources --id ID` - Display cached source summaries

### Changed
- **Python 3 Enforcement** - All scripts now use `python3` instead of `python`
- **Browser Switch** - Changed from Chrome to Chromium for better compatibility
- **ask_question.py** - Now integrates source filtering before each query

### Fixed
- **Checkbox Automation** - Uses Playwright native clicks for reliable Angular interaction
  - JavaScript `.click()` didn't trigger Angular change detection
  - Now uses `checkbox.click(force=True)` for proper event handling
  - Each deselection is verified after clicking

## [1.3.0] - 2025-11-21

### Added
- **Modular Architecture** - Refactored codebase for better maintainability
  - New `config.py` - Centralized configuration (paths, selectors, timeouts)
  - New `browser_utils.py` - BrowserFactory and StealthUtils classes
  - Cleaner separation of concerns across all scripts

### Changed
- **Timeout increased to 120 seconds** - Long queries no longer timeout prematurely
  - `ask_question.py`: 30s → 120s
  - `browser_session.py`: 30s → 120s
  - Resolves Issue #4

### Fixed
- **Thinking Message Detection** - Fixed incomplete answers showing placeholder text
  - Now waits for `div.thinking-message` element to disappear before reading answer
  - Answers like "Reviewing the content..." or "Looking for answers..." no longer returned prematurely
  - Works reliably across all languages and NotebookLM UI changes

- **Correct CSS Selectors** - Updated to match current NotebookLM UI
  - Changed from `.response-content, .message-content` to `.to-user-container .message-text-content`
  - Consistent selectors across all scripts

- **Stability Detection** - Improved answer completeness check
  - Now requires 3 consecutive stable polls instead of 1 second wait
  - Prevents truncated responses during streaming

## [1.2.0] - 2025-10-28

### Added
- Initial public release
- NotebookLM integration via browser automation
- Session-based conversations with Gemini 2.5
- Notebook library management
- Knowledge base preparation tools
- Google authentication with persistent sessions
