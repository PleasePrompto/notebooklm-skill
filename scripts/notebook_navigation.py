#!/usr/bin/env python3
"""
Navigation helpers for NotebookLM pages.
"""

import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from patchright.sync_api import Page

from config import (
    HOME_READY_SELECTORS,
    NOTEBOOKLM_APP_URL,
    NOTEBOOKLM_PUBLIC_URL,
    NOTEBOOK_READY_SELECTORS,
)


ACCOUNT_TILE_SELECTORS = [
    "[data-identifier]",
    "li [data-identifier]",
    "div[data-identifier]",
]

PASSWORD_CHALLENGE_PATTERNS = [
    "signin/challenge/pwd",
    "challenge/pwd",
    "challenge/password",
]


def normalize_notebooklm_url(url: str) -> str:
    """Normalize NotebookLM URLs while preserving the app host for notebook deep links."""
    normalized = url.rstrip("/")
    if normalized.startswith("https://notebooklm.google.com"):
        return normalized

    if is_notebook_url(normalized) and normalized.startswith("https://notebooklm.google"):
        return normalized.replace("https://notebooklm.google", NOTEBOOKLM_APP_URL, 1)

    if normalized.startswith("https://notebooklm.google"):
        return normalized.replace("https://notebooklm.google", NOTEBOOKLM_PUBLIC_URL, 1)

    return normalized


def is_google_auth_url(url: str) -> bool:
    return "accounts.google.com" in (url or "")


def is_account_chooser_url(url: str) -> bool:
    lower_url = (url or "").lower()
    return is_google_auth_url(lower_url) and "accountchooser" in lower_url


def is_password_challenge_url(url: str) -> bool:
    lower_url = (url or "").lower()
    return is_google_auth_url(lower_url) and any(pattern in lower_url for pattern in PASSWORD_CHALLENGE_PATTERNS)


def is_notebook_url(url: str) -> bool:
    return "/notebook/" in (url or "")


def is_notebooklm_app_url(url: str) -> bool:
    return (url or "").startswith(NOTEBOOKLM_APP_URL)


def is_notebooklm_home_url(url: str) -> bool:
    parsed = urlparse(url or "")
    if parsed.netloc not in {"notebooklm.google.com", "notebooklm.google"}:
        return False
    path = parsed.path.rstrip("/")
    return path in {"", "/"}


def list_account_choices(page: Page) -> List[str]:
    """Return unique Google account emails shown on an account chooser page."""
    seen: List[str] = []

    for selector in ACCOUNT_TILE_SELECTORS:
        try:
            locators = page.locator(selector)
            count = locators.count()
        except Exception:
            continue

        for index in range(count):
            try:
                value = (locators.nth(index).get_attribute("data-identifier") or "").strip()
            except Exception:
                continue
            if value and value not in seen:
                seen.append(value)

        if seen:
            break

    if seen:
        return seen

    try:
        body_text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        body_text = ""

    for match in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", body_text):
        if match not in seen:
            seen.append(match)

    return seen


def _click_account_tile(page: Page, email: str) -> bool:
    """Click the Google account chooser tile for the provided email."""
    selectors = [
        f'[data-identifier="{email}"]',
        f'li [data-identifier="{email}"]',
        f'div[data-identifier="{email}"]',
        f'text="{email}"',
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            locator.click(timeout=3000)
            return True
        except Exception:
            try:
                locator.evaluate("el => el.click()")
                return True
            except Exception:
                continue

    return False


def maybe_choose_google_account(
    page: Page,
    preferred_email: Optional[str] = None,
    timeout_ms: int = 10000,
) -> Dict[str, Any]:
    """
    Auto-select a Google account on account chooser pages when possible.
    """
    if not is_account_chooser_url(page.url):
        return {"status": "not-needed"}

    deadline = time.time() + timeout_ms / 1000
    emails: List[str] = []

    while time.time() < deadline:
        emails = list_account_choices(page)
        if emails:
            break
        try:
            page.wait_for_timeout(250)
        except Exception:
            time.sleep(0.25)

    if not emails:
        return {
            "status": "no-accounts-found",
            "current_url": page.url,
        }

    selected_email: Optional[str] = None
    if preferred_email:
        preferred_lower = preferred_email.lower()
        for email in emails:
            if email.lower() == preferred_lower:
                selected_email = email
                break
        if not selected_email:
            return {
                "status": "preferred-account-missing",
                "emails": emails,
                "preferred_email": preferred_email,
                "current_url": page.url,
            }
    elif len(emails) == 1:
        selected_email = emails[0]
    else:
        return {
            "status": "multiple-accounts",
            "emails": emails,
            "current_url": page.url,
        }

    if not _click_account_tile(page, selected_email):
        return {
            "status": "account-click-failed",
            "email": selected_email,
            "emails": emails,
            "current_url": page.url,
        }

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        current_url = page.url.rstrip("/")
        if is_password_challenge_url(current_url):
            return {
                "status": "password-challenge",
                "email": selected_email,
                "emails": emails,
                "current_url": current_url,
            }
        if not is_account_chooser_url(current_url):
            return {
                "status": "selected",
                "email": selected_email,
                "emails": emails,
                "current_url": current_url,
            }
        try:
            page.wait_for_timeout(250)
        except Exception:
            time.sleep(0.25)

    return {
        "status": "account-selection-timeout",
        "email": selected_email,
        "emails": emails,
        "current_url": page.url,
    }


def wait_for_url_to_settle(page: Page, settle_ms: int = 1500, timeout_ms: int = 6000) -> str:
    """Wait for SPA redirects to settle before classifying the page."""
    last_url = page.url.rstrip("/")
    stable_since = time.time()
    deadline = time.time() + timeout_ms / 1000

    while time.time() < deadline:
        try:
            page.wait_for_timeout(250)
        except Exception:
            time.sleep(0.25)

        current_url = page.url.rstrip("/")
        if current_url != last_url:
            last_url = current_url
            stable_since = time.time()
            continue

        if (time.time() - stable_since) * 1000 >= settle_ms:
            break

    return page.url.rstrip("/")


def wait_for_any_selector(page: Page, selectors: List[str], timeout_ms: int = 10000) -> Optional[str]:
    """Wait until any selector becomes visible and return the selector."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible():
                    return selector
            except Exception:
                continue
        try:
            page.wait_for_timeout(250)
        except Exception:
            time.sleep(0.25)
    return None


def classify_notebooklm_state(page: Page) -> Dict[str, Any]:
    """Classify the current page into NotebookLM, auth, or redirect states."""
    current_url = wait_for_url_to_settle(page)
    if is_password_challenge_url(current_url):
        return {"status": "password-challenge", "current_url": current_url}
    if is_account_chooser_url(current_url):
        return {"status": "account-chooser", "current_url": current_url}
    if is_google_auth_url(current_url):
        return {"status": "google-login", "current_url": current_url}
    if is_notebooklm_app_url(current_url):
        return {"status": "ok", "current_url": current_url}
    return {"status": "unexpected-url", "current_url": current_url}


def open_home_page(
    page: Page,
    preferred_email: Optional[str] = None,
    timeout_ms: int = 30000,
) -> Dict[str, Any]:
    """Open NotebookLM home/list page and classify auth failures precisely."""
    page.goto(NOTEBOOKLM_APP_URL, wait_until="domcontentloaded", timeout=timeout_ms)

    chooser_result = maybe_choose_google_account(page, preferred_email=preferred_email)
    if chooser_result["status"] not in {"not-needed", "selected"}:
        chooser_result.setdefault("target_url", NOTEBOOKLM_APP_URL)
        return chooser_result

    classified = classify_notebooklm_state(page)
    if classified["status"] != "ok":
        classified["target_url"] = NOTEBOOKLM_APP_URL
        return classified

    if not wait_for_any_selector(page, HOME_READY_SELECTORS, timeout_ms=timeout_ms):
        return {
            "status": "home-not-ready",
            "current_url": page.url.rstrip("/"),
            "target_url": NOTEBOOKLM_APP_URL,
        }

    return {
        "status": "ok",
        "current_url": page.url.rstrip("/"),
        "target_url": NOTEBOOKLM_APP_URL,
    }


def open_notebook_page(
    page: Page,
    notebook_url: str,
    preferred_email: Optional[str] = None,
    timeout_ms: int = 30000,
) -> Dict[str, Any]:
    """
    Navigate to a NotebookLM notebook and classify failures precisely.
    """
    target_url = normalize_notebooklm_url(notebook_url)

    for attempt in range(2):
        if attempt == 1 and is_notebook_url(target_url):
            page.goto(NOTEBOOKLM_APP_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_timeout(1000)
            except Exception:
                time.sleep(1)

        page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)

        chooser_result = maybe_choose_google_account(page, preferred_email=preferred_email)
        if chooser_result["status"] not in {"not-needed", "selected"}:
            chooser_result.setdefault("target_url", target_url)
            return chooser_result

        classified = classify_notebooklm_state(page)
        current_url = classified["current_url"]
        if classified["status"] in {"google-login", "password-challenge", "account-chooser", "unexpected-url"}:
            classified["target_url"] = target_url
            return classified

        if is_notebook_url(target_url) and not is_notebook_url(current_url):
            if attempt == 0:
                continue
            return {
                "status": "home-redirect",
                "current_url": current_url,
                "target_url": target_url,
            }

        if not wait_for_any_selector(page, NOTEBOOK_READY_SELECTORS, timeout_ms=timeout_ms):
            return {
                "status": "notebook-not-ready",
                "current_url": current_url,
                "target_url": target_url,
            }

        return {
            "status": "ok",
            "current_url": current_url,
            "target_url": target_url,
        }

    return {
        "status": "unknown",
        "current_url": page.url.rstrip("/"),
        "target_url": target_url,
    }


def explain_navigation_failure(navigation: Dict[str, Any], preferred_email: Optional[str] = None) -> List[str]:
    """Return user-facing failure lines for common NotebookLM navigation outcomes."""
    status = navigation.get("status")
    lines: List[str] = []

    if status == "google-login":
        lines.append("  ❌ NotebookLM redirected to the Google login page")
        lines.append("     Current browser profile is not fully signed in to NotebookLM")
    elif status == "password-challenge":
        lines.append("  ❌ Google sent the browser to a password challenge page")
        if navigation.get("email"):
            lines.append(f"     Google account: {navigation['email']}")
    elif status == "home-redirect":
        lines.append("  ❌ Notebook URL redirected to the NotebookLM home page")
        lines.append("     Likely cause: wrong Google account for this notebook, or the notebook is not shared to this account")
        if preferred_email:
            lines.append(f"     Current Google account: {preferred_email}")
    elif status == "multiple-accounts":
        accounts = ", ".join(navigation.get("emails", []))
        lines.append("  ❌ Google showed an account chooser with multiple accounts")
        if accounts:
            lines.append(f"     Available accounts: {accounts}")
    elif status == "preferred-account-missing":
        accounts = ", ".join(navigation.get("emails", []))
        lines.append(f"  ❌ Preferred Google account not found: {navigation.get('preferred_email')}")
        if accounts:
            lines.append(f"     Available accounts: {accounts}")
    elif status == "account-click-failed":
        lines.append(f"  ❌ Failed to click Google account tile: {navigation.get('email')}")
    elif status == "account-selection-timeout":
        lines.append(f"  ❌ Timed out after selecting Google account: {navigation.get('email')}")
    elif status == "no-accounts-found":
        lines.append("  ❌ Google account chooser opened, but no account tiles were detected")
    elif status == "home-not-ready":
        lines.append("  ❌ Entered NotebookLM, but the home page never became interactive")
    elif status == "notebook-not-ready":
        lines.append("  ❌ Entered the notebook URL, but the notebook shell never became interactive")
    elif status == "account-chooser":
        lines.append("  ❌ NotebookLM remained on the Google account chooser page")
    elif status == "unexpected-url":
        lines.append("  ❌ NotebookLM ended on an unexpected URL")
    else:
        lines.append(f"  ❌ Failed to open NotebookLM ({status})")

    if navigation.get("current_url"):
        lines.append(f"     Final URL: {navigation['current_url']}")
    return lines
