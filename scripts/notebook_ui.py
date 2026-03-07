#!/usr/bin/env python3
"""
UI automation helpers for NotebookLM notebook discovery and management.
"""

import os
import re
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from patchright.sync_api import Page

from config import (
    CREATE_NOTEBOOK_BUTTON_SELECTORS,
    HOME_READY_SELECTORS,
    NOTEBOOKLM_APP_URL,
    NOTEBOOKLM_PROXY_BYPASS_ENV,
    NOTEBOOKLM_PROXY_URL_ENV,
    SOURCE_FILE_INPUT_SELECTORS,
    SOURCE_PANEL_READY_SELECTORS,
    SOURCE_UPLOAD_TIMEOUT_SECONDS,
    SOURCE_URL_TEXTAREA_SELECTORS,
    TITLE_INPUT_SELECTORS,
    UI_MEDIUM_TIMEOUT_MS,
)
from notebook_navigation import open_home_page, open_notebook_page, wait_for_any_selector, wait_for_url_to_settle


REMOTE_NOTEBOOK_EXTRACTOR = """
(elements, appUrl) => {
  const clean = value => (value || '').replace(/\\s+/g, ' ').trim();
  return elements.map((element) => {
    const titleElement = element.querySelector('.project-button-title');
    const title = clean(titleElement?.textContent || '');
    const titleId = titleElement?.id || '';
    const idMatch = titleId.match(/^project-(.+)-title$/);
    const notebookId = idMatch ? idMatch[1] : null;
    const emoji = clean(element.querySelector('.project-button-box-icon')?.textContent || '');
    const subtitleElement = element.querySelector('.project-button-subtitle');
    const subtitle = clean(subtitleElement?.textContent || '');
    const lines = (element.innerText || '').split(/\\n+/).map(clean).filter(Boolean);
    const filtered = lines.filter(line => !['more_vert', emoji, title].includes(line));
    const fallbackSubtitle = subtitle || (filtered.length ? filtered[filtered.length - 1] : '');
    const descriptionLines = filtered.filter(line => line !== fallbackSubtitle);
    return {
      id: notebookId,
      title,
      url: notebookId ? `${appUrl}/notebook/${notebookId}` : null,
      subtitle: fallbackSubtitle || null,
      visible_description: descriptionLines.length ? descriptionLines.join(' | ') : null,
      visible_updated_at: fallbackSubtitle && fallbackSubtitle.includes('·') ? clean(fallbackSubtitle.split('·')[0]) : null,
      emoji: emoji || null,
    };
  }).filter(item => item.id && item.title);
}
"""


SOURCE_ERROR_PATTERNS = [
    r"upload failed",
    r"failed to import",
    r"couldn.?t import",
    r"can.?t import",
    r"unsupported",
    r"try again",
    r"not available",
    r"unable to",
]

RESEARCH_QUERY_TEXTAREA_SELECTORS = [
    'textarea[aria-label="Discover sources based on the inputted query"]',
    'textarea.query-box-textarea',
]

RESEARCH_MODE_BUTTON_SELECTORS = [
    'button.researcher-menu-trigger',
]

RESEARCH_SUBMIT_BUTTON_SELECTORS = [
    'button.actions-enter-button-active',
    'button[aria-label="Submit"]',
]

RESEARCH_MODE_LABELS = {
    'fast-research': 'Fast Research',
    'deep-research': 'Deep Research',
}

RESEARCH_TIMEOUT_SECONDS = 900
RESEARCH_IMPORT_TIMEOUT_SECONDS = 180
RESEARCH_COMPLETION_TOKENS = {
    'view',
    'delete',
    'import',
    'thumb_up',
    'thumb_down',
    'link',
    'docs',
    'stop',
    'close',
    'add',
    'drive_pdf',
    'folder_copy',
}


class NotebookUIError(RuntimeError):
    """Structured UI automation error."""

    def __init__(self, code: str, message: str, *, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}



def list_remote_notebooks(page: Page, preferred_email: Optional[str] = None) -> List[Dict[str, Any]]:
    navigation = open_home_page(page, preferred_email=preferred_email)
    if navigation["status"] != "ok":
        raise NotebookUIError(navigation["status"], "Failed to open NotebookLM home page", details=navigation)

    _load_all_notebook_cards(page)
    cards = page.locator("div.my-projects-container project-button")
    return cards.evaluate_all(REMOTE_NOTEBOOK_EXTRACTOR, NOTEBOOKLM_APP_URL)



def create_notebook(page: Page, name: Optional[str] = None, preferred_email: Optional[str] = None) -> Dict[str, Any]:
    navigation = open_home_page(page, preferred_email=preferred_email)
    if navigation["status"] != "ok":
        raise NotebookUIError(navigation["status"], "Failed to open NotebookLM home page", details=navigation)

    selector = wait_for_any_selector(page, CREATE_NOTEBOOK_BUTTON_SELECTORS, timeout_ms=UI_MEDIUM_TIMEOUT_MS)
    if not selector:
        raise NotebookUIError("create-button-missing", "NotebookLM did not expose a create notebook action")

    create_button = page.locator(selector).first
    create_button.click(timeout=UI_MEDIUM_TIMEOUT_MS)

    _wait_for_notebook_url(page)
    title = _read_current_notebook_title(page)
    rename_status = None
    if name:
        rename_status = rename_current_notebook(page, name)
        title = rename_status["title"]

    result = {
        "status": "ok",
        "url": wait_for_url_to_settle(page),
        "title": title,
    }
    if rename_status and rename_status.get("status") != "ok":
        result["rename_status"] = rename_status
    return result



def rename_current_notebook(page: Page, name: str) -> Dict[str, Any]:
    input_locator = _find_first_visible(page, TITLE_INPUT_SELECTORS)
    if not input_locator:
        return {
            "status": "rename-unavailable",
            "title": _read_current_notebook_title(page),
            "message": "Notebook title input is not editable in the current UI",
        }

    input_locator.fill(name, timeout=UI_MEDIUM_TIMEOUT_MS)
    try:
        input_locator.press("Enter")
    except Exception:
        pass

    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            value = input_locator.input_value(timeout=1000).strip()
        except Exception:
            value = ""
        if value == name:
            return {
                "status": "ok",
                "title": value,
            }
        page.wait_for_timeout(250)

    return {
        "status": "rename-timeout",
        "title": _read_current_notebook_title(page),
        "message": "Notebook title did not settle to the requested value",
    }



def add_source(
    page: Page,
    notebook_url: str,
    *,
    source_url: Optional[str] = None,
    file_path: Optional[str] = None,
    preferred_email: Optional[str] = None,
) -> Dict[str, Any]:
    navigation = open_notebook_page(page, notebook_url, preferred_email=preferred_email)
    if navigation["status"] != "ok":
        raise NotebookUIError(navigation["status"], "Failed to open NotebookLM notebook", details=navigation)

    baseline_count = get_source_count(page)
    _ensure_source_panel_open(page)

    temporary_file: Optional[Path] = None
    source_kind = None
    try:
        if file_path:
            upload_target = Path(file_path).expanduser().resolve()
            if not upload_target.exists() or not upload_target.is_file():
                raise NotebookUIError("file-not-found", f"Local file not found: {upload_target}")
            source_kind = _classify_file_source(upload_target)
            _upload_local_file(page, upload_target)
        elif source_url:
            if _looks_like_pdf_url(source_url):
                temporary_file = _download_pdf(source_url)
                source_kind = "pdf-url"
                _upload_local_file(page, temporary_file)
            else:
                source_kind = _classify_url_source(source_url)
                _insert_source_url(page, source_url)
        else:
            raise NotebookUIError("missing-source", "Either source_url or file_path is required")

        final_count = _wait_for_source_count_increase(page, baseline_count)
        return {
            "status": "ok",
            "notebook_url": wait_for_url_to_settle(page),
            "source_kind": source_kind,
            "source_count_before": baseline_count,
            "source_count_after": final_count,
            "title": _read_current_notebook_title(page),
        }
    finally:
        if temporary_file and temporary_file.exists():
            try:
                temporary_file.unlink()
            except Exception:
                pass



def discover_sources(
    page: Page,
    notebook_url: str,
    *,
    query: str,
    mode: str = "fast-research",
    auto_import: bool = True,
    preferred_email: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    normalized_mode = (mode or "fast-research").strip().lower()
    if normalized_mode not in RESEARCH_MODE_LABELS:
        raise NotebookUIError("research-mode-invalid", f"Unsupported research mode: {mode}")

    navigation = open_notebook_page(page, notebook_url, preferred_email=preferred_email)
    if navigation["status"] != "ok":
        raise NotebookUIError(navigation["status"], "Failed to open NotebookLM notebook", details=navigation)

    baseline_count = get_source_count(page)
    _ensure_source_panel_open(page)
    _ensure_research_controls_ready(page)
    _fill_research_query(page, query)
    selected_mode = _select_research_mode(page, normalized_mode)
    _submit_research_query(page)

    result = _wait_for_research_completion(
        page,
        requested_mode=normalized_mode,
        progress_callback=progress_callback,
    )
    result.update(
        {
            "status": "ok",
            "query": query,
            "mode_requested": normalized_mode,
            "mode_selected": selected_mode,
            "notebook_url": wait_for_url_to_settle(page),
            "title": _read_current_notebook_title(page),
            "source_count_before": baseline_count,
            "auto_import_requested": auto_import,
        }
    )

    if auto_import:
        import_result = _import_research_results(
            page,
            notebook_url,
            baseline_count,
            preferred_email=preferred_email,
            progress_callback=progress_callback,
        )
        result["import_result"] = import_result
        result["source_count_after"] = import_result["source_count_after"]
    else:
        result["source_count_after"] = baseline_count

    return result



def get_source_count(page: Page) -> int:
    body_text = _safe_body_text(page)
    explicit_count = _extract_explicit_source_count(body_text)

    try:
        checkboxes = page.locator("input[type='checkbox']")
        count = checkboxes.count()
        labels = []
        for index in range(count):
            try:
                aria = (checkboxes.nth(index).get_attribute("aria-label") or "").strip()
            except Exception:
                aria = ""
            if aria and aria.lower() != "select all sources":
                labels.append(aria)
        checkbox_count = len(labels)
    except Exception:
        checkbox_count = 0

    candidates = re.findall(r"\((\d+)\)", body_text)
    candidate_count = max(int(value) for value in candidates) if candidates else 0

    return max(explicit_count, candidate_count, checkbox_count)



def _extract_explicit_source_count(body_text: str) -> int:
    explicit = re.findall(r"(\d+)\s+source(?:s)?", body_text.lower())
    if explicit:
        return max(int(value) for value in explicit)
    return 0



def _ensure_research_controls_ready(page: Page):
    query_box = _find_first_visible(page, RESEARCH_QUERY_TEXTAREA_SELECTORS)
    if query_box:
        return
    raise NotebookUIError(
        "research-controls-missing",
        "NotebookLM did not expose the research query controls in the Sources view",
        details={"body_excerpt": _safe_body_text(page)[:1200]},
    )



def _fill_research_query(page: Page, query: str):
    query_box = _find_first_visible(page, RESEARCH_QUERY_TEXTAREA_SELECTORS)
    if not query_box:
        raise NotebookUIError("research-query-input-missing", "NotebookLM did not expose the research query input")

    try:
        query_box.click(timeout=UI_MEDIUM_TIMEOUT_MS)
        query_box.press("Control+A")
        query_box.press("Backspace")
    except Exception:
        pass

    try:
        query_box.fill("")
    except Exception:
        pass

    try:
        query_box.type(query, delay=20)
    except Exception as error:
        raise NotebookUIError("research-query-input-failed", f"Failed to type research query: {error}") from error

    page.wait_for_timeout(600)



def _select_research_mode(page: Page, mode: str) -> str:
    label = RESEARCH_MODE_LABELS[mode]
    mode_button = _find_research_mode_button(page)
    if not mode_button:
        raise NotebookUIError("research-mode-control-missing", "NotebookLM did not expose the Fast Research / Deep Research selector")

    current_text = _safe_locator_text(mode_button)
    if label.lower() in current_text.lower():
        return mode

    try:
        mode_button.click(timeout=UI_MEDIUM_TIMEOUT_MS)
    except Exception as error:
        raise NotebookUIError("research-mode-open-failed", f"Failed to open the research mode menu: {error}") from error

    option = page.get_by_role("menuitem", name=label).first
    if option.count() == 0:
        raise NotebookUIError(
            f"{mode}-control-missing",
            f"NotebookLM did not expose the {label} option",
            details={"body_excerpt": _safe_body_text(page)[:1200]},
        )

    try:
        option.click(timeout=UI_MEDIUM_TIMEOUT_MS)
    except Exception as error:
        raise NotebookUIError("research-mode-select-failed", f"Failed to select {label}: {error}") from error

    deadline = time.time() + 8
    while time.time() < deadline:
        current_text = _safe_locator_text(_find_research_mode_button(page))
        if label.lower() in current_text.lower():
            return mode
        page.wait_for_timeout(250)

    raise NotebookUIError("research-mode-not-applied", f"NotebookLM did not switch the selector to {label}")



def _submit_research_query(page: Page):
    submit_button = _find_research_submit_button(page)
    if not submit_button:
        raise NotebookUIError("research-submit-missing", "NotebookLM did not expose an enabled research submit action")

    try:
        submit_button.click(timeout=UI_MEDIUM_TIMEOUT_MS)
    except Exception as error:
        raise NotebookUIError("research-submit-failed", f"Failed to submit the research query: {error}") from error

    deadline = time.time() + 12
    while time.time() < deadline:
        body_text = _safe_body_text(page)
        progress = _classify_research_progress(body_text)
        if progress["phase"] in {"running", "completed"}:
            return
        page.wait_for_timeout(500)

    raise NotebookUIError(
        "research-submit-not-started",
        "NotebookLM did not start the research workflow after query submission",
        details={"body_excerpt": _safe_body_text(page)[:1200]},
    )



def _wait_for_research_completion(
    page: Page,
    *,
    requested_mode: str,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    deadline = time.time() + RESEARCH_TIMEOUT_SECONDS
    progress_updates: List[str] = []
    last_progress_key = None
    inferred_mode = requested_mode
    last_body_text = ""

    while time.time() < deadline:
        body_text = _safe_body_text(page)
        last_body_text = body_text
        progress = _classify_research_progress(body_text)
        if progress.get("mode") == "deep-research":
            inferred_mode = "deep-research"
        elif progress.get("mode") == "fast-research" and inferred_mode != "deep-research":
            inferred_mode = "fast-research"

        progress_key = progress.get("key")
        progress_message = progress.get("message")
        if progress_message and progress_key != last_progress_key:
            progress_updates.append(progress_message)
            if progress_callback:
                progress_callback(progress_message)
            last_progress_key = progress_key

        if progress["phase"] == "completed" or _research_results_ready(body_text):
            visible_results = _extract_visible_results(body_text)
            discovered_count = _extract_discovered_source_count(body_text)
            more_sources_count = _extract_more_sources_count(body_text)
            deep_research_details = None
            if inferred_mode == "deep-research":
                deep_research_details = _extract_deep_research_details(page)
                if deep_research_details.get("report_title") and not visible_results:
                    visible_results = [deep_research_details["report_title"]]
                if deep_research_details.get("cited_count") is not None:
                    discovered_count = deep_research_details["cited_count"]
            if not visible_results and discovered_count is None and more_sources_count is None:
                raise NotebookUIError(
                    "research-results-missing",
                    "NotebookLM finished the research workflow but did not expose visible source results",
                    details={"body_excerpt": body_text[:1600]},
                )
            result = {
                "research_status": "completed",
                "progress_updates": progress_updates,
                "mode_observed": inferred_mode,
                "completion_message": progress_message or "Research completed",
                "discovered_count": discovered_count,
                "more_sources_count": more_sources_count,
                "visible_results": visible_results,
            }
            if deep_research_details:
                result["deep_research_details"] = deep_research_details
            return result

        if progress["phase"] == "error":
            raise NotebookUIError(
                progress["key"],
                progress_message or "NotebookLM reported a research failure",
                details={"body_excerpt": body_text[:1600]},
            )

        page.wait_for_timeout(2000)

    raise NotebookUIError(
        "research-timeout",
        "NotebookLM did not finish the research workflow before timeout",
        details={
            "body_excerpt": last_body_text[:1600],
            "progress_updates": progress_updates,
        },
    )



def _import_research_results(
    page: Page,
    notebook_url: str,
    baseline_count: int,
    *,
    preferred_email: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    import_button = page.get_by_role("button", name="Import").first
    if import_button.count() == 0 or not import_button.is_visible():
        raise NotebookUIError(
            "research-import-unavailable",
            "NotebookLM research results were generated, but no Import action was available",
            details={"body_excerpt": _safe_body_text(page)[:1600]},
        )

    try:
        import_button.click(timeout=UI_MEDIUM_TIMEOUT_MS)
    except Exception as error:
        raise NotebookUIError("research-import-click-failed", f"Failed to click Import: {error}") from error

    if progress_callback:
        progress_callback("Import clicked")

    deadline = time.time() + RESEARCH_IMPORT_TIMEOUT_SECONDS
    stable_count = None
    stable_rounds = 0
    last_body_text = ""

    while time.time() < deadline:
        page.wait_for_timeout(2000)
        navigation = open_notebook_page(page, notebook_url, preferred_email=preferred_email)
        if navigation["status"] != "ok":
            raise NotebookUIError(navigation["status"], "Failed to reopen the notebook after Import", details=navigation)

        current_count = get_source_count(page)
        last_body_text = _safe_body_text(page)
        if current_count > baseline_count:
            if current_count == stable_count:
                stable_rounds += 1
            else:
                stable_count = current_count
                stable_rounds = 1
            if stable_rounds >= 2:
                if progress_callback:
                    progress_callback(f"Import persisted with {current_count} sources")
                return {
                    "status": "ok",
                    "source_count_before": baseline_count,
                    "source_count_after": current_count,
                }

    raise NotebookUIError(
        "research-import-not-persisted",
        "NotebookLM showed Import, but the added sources did not persist before timeout",
        details={"body_excerpt": last_body_text[:1600]},
    )



def _find_research_mode_button(page: Page):
    return _find_first_visible(page, RESEARCH_MODE_BUTTON_SELECTORS)



def _find_research_submit_button(page: Page):
    for selector in RESEARCH_SUBMIT_BUTTON_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible():
                disabled = (locator.get_attribute("disabled") or "").strip().lower()
                aria_disabled = (locator.get_attribute("aria-disabled") or "").strip().lower()
                classes = (locator.get_attribute("class") or "").strip().lower()
                if disabled or aria_disabled == "true":
                    continue
                if selector == 'button[aria-label="Submit"]' and 'disabled' in classes and 'active' not in classes:
                    continue
                return locator
        except Exception:
            continue
    return None



def _classify_research_progress(body_text: str) -> Dict[str, Any]:
    lower_text = body_text.lower()

    if "deep research completed!" in lower_text:
        return {"phase": "completed", "key": "deep-research-completed", "message": "Deep Research completed!", "mode": "deep-research"}
    if "fast research completed!" in lower_text:
        return {"phase": "completed", "key": "fast-research-completed", "message": "Fast Research completed!", "mode": "fast-research"}

    step_match = re.search(r"step\s+(\d+)\s*/\s*(\d+)\s+complete", body_text, re.IGNORECASE)
    if step_match:
        current_step = int(step_match.group(1))
        total_steps = int(step_match.group(2))
        return {
            "phase": "running",
            "key": f"deep-step-{current_step}-of-{total_steps}",
            "message": f"Step {current_step}/{total_steps} Complete",
            "mode": "deep-research",
        }

    if "planning... please stay on this page" in lower_text:
        return {"phase": "running", "key": "planning-stay", "message": "Planning... Please stay on this page", "mode": "deep-research"}
    if "planning... feel free to leave" in lower_text:
        return {"phase": "running", "key": "planning-leave", "message": "Planning... Feel free to leave", "mode": "deep-research"}
    if "researching websites..." in lower_text:
        return {"phase": "running", "key": "researching-websites", "message": "Researching Websites...", "mode": None}
    if "analyzing results..." in lower_text:
        return {"phase": "running", "key": "analyzing-results", "message": "Analyzing Results...", "mode": "deep-research"}

    for pattern in SOURCE_ERROR_PATTERNS:
        match = re.search(pattern, lower_text)
        if match:
            return {"phase": "error", "key": "research-ui-error", "message": f"NotebookLM reported: {match.group(0)}", "mode": None}

    return {"phase": "idle", "key": "idle", "message": None, "mode": None}



def _research_results_ready(body_text: str) -> bool:
    lower_text = body_text.lower()
    return "import" in lower_text and (
        "sources discovered" in lower_text
        or "more sources" in lower_text
        or "thumb_up" in lower_text
        or "thumb_down" in lower_text
        or "view" in lower_text
    )



def _extract_discovered_source_count(body_text: str) -> Optional[int]:
    match = re.search(r"(\d+)\s+source(?:s)?\s+discovered", body_text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None



def _extract_more_sources_count(body_text: str) -> Optional[int]:
    match = re.search(r"(\d+)\s+more\s+source(?:s)?", body_text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None



def _extract_visible_results(body_text: str) -> List[str]:
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    start_index = None
    for index, line in enumerate(lines):
        lowered = line.lower()
        if "completed!" in lowered or "sources discovered" in lowered:
            start_index = index + 1
            break

    if start_index is None:
        return []

    results: List[str] = []
    for line in lines[start_index:]:
        lowered = line.lower()
        if lowered in RESEARCH_COMPLETION_TOKENS:
            continue
        if lowered.startswith("saved sources will appear here"):
            break
        if lowered.startswith("click add source above"):
            break
        if lowered.startswith("import or delete results before"):
            break
        if lowered.startswith("select all sources"):
            break
        if re.fullmatch(r"\d+\s+more\s+source(?:s)?", lowered):
            continue
        if re.fullmatch(r"\d+\s+source(?:s)?\s+discovered", lowered):
            continue
        if re.fullmatch(r"top\s+\d+\s+source(?:s)?", lowered):
            continue
        results.append(line)
        if len(results) >= 12:
            break
    return results



def _extract_deep_research_details(page: Page) -> Dict[str, Any]:
    if not _open_deep_research_detailed_view(page):
        return {}

    report_title = _safe_locator_text(page.locator('.deep-research-report-header-text-title').first)
    report_subtitle = _safe_locator_text(page.locator('.deep-research-report-header-text-subtitle').first)
    cited_count, not_cited_count = _extract_deep_research_tab_counts(page)

    details = {
        "report_title": report_title or None,
        "report_subtitle": report_subtitle or None,
        "cited_count": cited_count,
        "not_cited_count": not_cited_count,
        "cited_sources": _extract_deep_research_source_entries(page, tab_name="Cited in Report"),
    }

    if not_cited_count is not None and not_cited_count > 0:
        details["not_cited_sources"] = _extract_deep_research_source_entries(page, tab_name="Not cited")
    else:
        details["not_cited_sources"] = []

    if cited_count is not None:
        try:
            page.get_by_role("tab", name=re.compile(r"^Cited in Report", re.IGNORECASE)).first.click(timeout=UI_MEDIUM_TIMEOUT_MS)
            page.wait_for_timeout(500)
        except Exception:
            pass

    return details



def _open_deep_research_detailed_view(page: Page) -> bool:
    container = page.locator('.deep-research-sources-container').first
    if container.count() and container.is_visible():
        return True

    view_button = page.get_by_role('button', name='View sources').first
    if view_button.count() == 0 or not view_button.is_visible():
        return False

    try:
        view_button.click(timeout=UI_MEDIUM_TIMEOUT_MS)
    except Exception as error:
        raise NotebookUIError('deep-research-view-open-failed', f'Failed to open Deep Research detailed sources view: {error}') from error

    deadline = time.time() + 10
    while time.time() < deadline:
        if container.count() and container.is_visible():
            return True
        page.wait_for_timeout(250)

    raise NotebookUIError(
        'deep-research-view-missing',
        'Deep Research completed, but NotebookLM did not open the detailed sources view',
        details={'body_excerpt': _safe_body_text(page)[:1600]},
    )



def _extract_deep_research_tab_counts(page: Page) -> tuple[Optional[int], Optional[int]]:
    cited_count = None
    not_cited_count = None
    tabs = page.locator('.deep-research-sources-tabs-group [role="tab"]')
    for index in range(tabs.count()):
        text = _safe_locator_text(tabs.nth(index))
        if not text:
            continue
        match = re.search(r'(\d+)', text)
        if 'cited in report' in text.lower() and match:
            cited_count = int(match.group(1))
        elif 'not cited' in text.lower() and match:
            not_cited_count = int(match.group(1))
    return cited_count, not_cited_count



def _extract_deep_research_source_entries(page: Page, *, tab_name: str) -> List[Dict[str, Any]]:
    tab = page.get_by_role('tab', name=re.compile(rf'^{re.escape(tab_name)}', re.IGNORECASE)).first
    if tab.count() == 0:
        return []

    try:
        tab.click(timeout=UI_MEDIUM_TIMEOUT_MS)
        page.wait_for_timeout(800)
    except Exception as error:
        raise NotebookUIError('deep-research-tab-open-failed', f'Failed to open the {tab_name} tab: {error}') from error

    _scroll_deep_research_sources(page)
    containers = page.locator('.deep-research-sources-container .source-container')
    if containers.count() == 0:
        return []

    return containers.evaluate_all(
        """
        (nodes) => nodes.map((node) => {
          const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
          const title = clean(node.querySelector('.source-text-header-title')?.textContent || '');
          const subtitle = clean(node.querySelector('.source-text-subtitle')?.textContent || '');
          const header = clean(node.querySelector('.source-text-header')?.textContent || '');
          return {
            title: title || header.replace(/\s*open_in_new\s*/g, '').trim() || null,
            snippet: subtitle || null,
          };
        }).filter(item => item.title)
        """
    )



def _scroll_deep_research_sources(page: Page):
    last_count = -1
    stable_rounds = 0
    deadline = time.time() + 20
    while time.time() < deadline and stable_rounds < 3:
        count = page.locator('.deep-research-sources-container .source-container').count()
        if count == last_count:
            stable_rounds += 1
        else:
            last_count = count
            stable_rounds = 0
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(800)
    page.mouse.wheel(0, -3000)
    page.wait_for_timeout(400)



def _safe_locator_text(locator) -> str:
    if not locator:
        return ""
    try:
        return (locator.inner_text(timeout=1000) or "").strip()
    except Exception:
        return ""



def _load_all_notebook_cards(page: Page):
    stable_rounds = 0
    last_count = -1
    deadline = time.time() + 20
    while time.time() < deadline and stable_rounds < 3:
        count = page.locator("div.my-projects-container project-button").count()
        if count == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_count = count

        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1200)

    page.mouse.wheel(0, -3000)
    page.wait_for_timeout(400)



def _wait_for_notebook_url(page: Page):
    deadline = time.time() + 30
    while time.time() < deadline:
        current_url = wait_for_url_to_settle(page, settle_ms=800, timeout_ms=1500)
        if "/notebook/" in current_url:
            if wait_for_any_selector(page, HOME_READY_SELECTORS + TITLE_INPUT_SELECTORS, timeout_ms=UI_MEDIUM_TIMEOUT_MS):
                return
        page.wait_for_timeout(250)
    raise NotebookUIError("create-navigation-timeout", "NotebookLM did not navigate to the new notebook in time")



def _read_current_notebook_title(page: Page) -> str:
    input_locator = _find_first_visible(page, TITLE_INPUT_SELECTORS)
    if input_locator:
        try:
            value = input_locator.input_value(timeout=1000).strip()
            if value:
                return value
        except Exception:
            pass

    body_text = _safe_body_text(page)
    for line in body_text.splitlines():
        stripped = line.strip()
        if stripped and stripped not in {"settings", "PRO", "Sources", "Chat", "Studio", "more_vert"}:
            if "source" not in stripped.lower() and stripped not in {"Create notebook"}:
                return stripped
    return "Untitled notebook"



def _ensure_source_panel_open(page: Page):
    if _source_panel_is_open(page):
        return

    openers = [
        page.locator('button[aria-label=" Opens the upload source dialog"]').first,
        page.get_by_role("button", name="Upload a source").first,
        page.get_by_role("button", name="Upload files").first,
    ]
    for locator in openers:
        try:
            if locator.count() and locator.is_visible():
                locator.click(timeout=UI_MEDIUM_TIMEOUT_MS)
                page.wait_for_timeout(600)
                if _source_panel_is_open(page):
                    return
        except Exception:
            continue

    try:
        sources_tab = page.get_by_role("tab", name="Sources").first
        if sources_tab.count() and sources_tab.is_visible():
            sources_tab.click(timeout=UI_MEDIUM_TIMEOUT_MS)
            page.wait_for_timeout(800)
            if _source_panel_is_open(page):
                return
            add_source_button = page.get_by_role("button", name="Add source").first
            if add_source_button.count() and add_source_button.is_visible():
                add_source_button.click(timeout=UI_MEDIUM_TIMEOUT_MS)
                page.wait_for_timeout(800)
                if _source_panel_is_open(page):
                    return
    except Exception:
        pass

    raise NotebookUIError("source-panel-unavailable", "NotebookLM did not open the source upload panel")



def _insert_source_url(page: Page, source_url: str):
    textarea = _find_first_visible(page, SOURCE_URL_TEXTAREA_SELECTORS)
    if not textarea:
        try:
            page.get_by_role("button", name="Websites").first.click(timeout=UI_MEDIUM_TIMEOUT_MS)
        except Exception:
            pass
        textarea = _find_first_visible(page, SOURCE_URL_TEXTAREA_SELECTORS)
    if not textarea:
        raise NotebookUIError("source-url-input-missing", "NotebookLM did not expose the URL source input")

    textarea.fill(source_url, timeout=UI_MEDIUM_TIMEOUT_MS)
    insert_button = page.get_by_role("button", name="Insert").first
    if insert_button.count() == 0:
        raise NotebookUIError("source-url-insert-missing", "NotebookLM did not expose the URL insert action")
    insert_button.click(timeout=UI_MEDIUM_TIMEOUT_MS)



def _upload_local_file(page: Page, file_path: Path):
    input_locator = _find_first_existing(page, SOURCE_FILE_INPUT_SELECTORS)
    if not input_locator:
        try:
            page.get_by_role("button", name="Upload files").first.click(timeout=UI_MEDIUM_TIMEOUT_MS)
        except Exception:
            pass
        input_locator = _find_first_existing(page, SOURCE_FILE_INPUT_SELECTORS)
    if not input_locator:
        raise NotebookUIError("source-file-input-missing", "NotebookLM did not expose the local file upload input")

    input_locator.set_input_files(str(file_path))



def _wait_for_source_count_increase(page: Page, baseline_count: int) -> int:
    deadline = time.time() + SOURCE_UPLOAD_TIMEOUT_SECONDS
    last_error = None
    stable_count = None
    stable_rounds = 0
    while time.time() < deadline:
        current_count = get_source_count(page)
        if current_count > baseline_count:
            if current_count == stable_count:
                stable_rounds += 1
            else:
                stable_count = current_count
                stable_rounds = 1
            if stable_rounds >= 2:
                return current_count

        body_text = _safe_body_text(page).lower()
        for pattern in SOURCE_ERROR_PATTERNS:
            match = re.search(pattern, body_text)
            if match:
                last_error = match.group(0)
                break
        if last_error:
            raise NotebookUIError(
                "source-upload-failed",
                f"NotebookLM reported a source import failure: {last_error}",
                details={"body_excerpt": _safe_body_text(page)[:1200]},
            )

        page.wait_for_timeout(1000)

    raise NotebookUIError(
        "source-processing-timeout",
        "NotebookLM did not confirm the source upload/import before timeout",
        details={"body_excerpt": _safe_body_text(page)[:1200]},
    )



def _find_first_visible(page: Page, selectors: List[str]):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible():
                return locator
        except Exception:
            continue
    return None



def _source_panel_is_open(page: Page) -> bool:
    try:
        for button_name in ["Upload files", "Websites", "Drive", "Copied text"]:
            locator = page.get_by_role("button", name=button_name).first
            if locator.count() and locator.is_visible():
                return True
    except Exception:
        pass

    return bool(wait_for_any_selector(page, SOURCE_PANEL_READY_SELECTORS, timeout_ms=1200))



def _find_first_existing(page: Page, selectors: List[str]):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count():
                return locator
        except Exception:
            continue
    return None



def _looks_like_pdf_url(source_url: str) -> bool:
    return ".pdf" in source_url.lower().split("#", 1)[0].split("?", 1)[0]



def _download_pdf(source_url: str) -> Path:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    }
    request = urllib.request.Request(source_url, headers=headers)
    proxy_url = (
        os.getenv(NOTEBOOKLM_PROXY_URL_ENV)
        or os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("HTTP_PROXY")
        or os.getenv("http_proxy")
        or os.getenv("ALL_PROXY")
        or os.getenv("all_proxy")
    )
    proxies = {}
    if proxy_url:
        proxies["http"] = proxy_url
        proxies["https"] = proxy_url
    bypass = os.getenv(NOTEBOOKLM_PROXY_BYPASS_ENV) or os.getenv("NO_PROXY") or os.getenv("no_proxy")
    if bypass:
        for host in [item.strip() for item in bypass.split(',') if item.strip()]:
            proxies[host] = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
    try:
        with opener.open(request, timeout=60) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "pdf" not in content_type and not _looks_like_pdf_url(source_url):
                raise NotebookUIError(
                    "pdf-download-not-pdf",
                    f"URL did not return a PDF document (Content-Type: {content_type or 'unknown'})",
                )
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
                handle.write(response.read())
                return Path(handle.name)
    except NotebookUIError:
        raise
    except Exception as error:
        raise NotebookUIError("pdf-download-failed", f"Failed to download PDF URL: {error}") from error



def _classify_url_source(source_url: str) -> str:
    lowered = source_url.lower()
    if "youtube.com/" in lowered or "youtu.be/" in lowered:
        return "youtube-url"
    if "docs.google.com/document/" in lowered:
        return "google-docs-url"
    if "docs.google.com/presentation/" in lowered:
        return "google-slides-url"
    return "web-url"



def _classify_file_source(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return "local-pdf"
    return f"local-file:{suffix or 'unknown'}"



def _safe_body_text(page: Page) -> str:
    try:
        return page.locator("body").inner_text(timeout=3000)
    except Exception:
        return ""
