# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`--log` flag** - Save outputs to log files in logs/ directory
  - By default, only prints output to console (no files saved)
  - When enabled, saves original text, markdown (if --markdown used), and comparison stats
  - Usage: `python scripts/run.py ask_question.py --question "..." --log`

- **`--markdown` flag** - Get formatted markdown output from NotebookLM
  - Clicks the copy button in the NotebookLM UI to get clean markdown
  - Useful for responses with code blocks, lists, tables, and other formatting
  - Automatically falls back to plain text if copy button fails
  - Usage: `python scripts/run.py ask_question.py --question "..." --markdown`

### Changed
- **Logging behavior** - Logs are now opt-in via `--log` flag
  - Previously, logs were always saved when `--markdown` was enabled
  - Now, no files are created unless user explicitly uses `--log`

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
