#!/usr/bin/env python3
"""
Authentication Manager for NotebookLM
Handles Google login and browser state persistence
Based on the MCP server implementation

Implements hybrid auth approach:
- Persistent browser profile (user_data_dir) for fingerprint consistency
- Manual cookie injection from state.json for session cookies (Playwright bug workaround)
See: https://github.com/microsoft/playwright/issues/36139
"""

import json
import time
import argparse
import shutil
import sys
from pathlib import Path
from typing import Dict, Any

from patchright.sync_api import sync_playwright, BrowserContext

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    BROWSER_STATE_DIR, BROWSER_PROFILE_DIR, STATE_FILE, AUTH_INFO_FILE, DATA_DIR,
    NOTEBOOK_HOME_URL, is_notebook_url,
)
from browser_utils import BrowserFactory


def _close_session(playwright, context):
    """Tear down a playwright session, tolerating an already-closed context."""
    if context:
        try:
            context.close()
        except Exception:
            pass
    if playwright:
        try:
            playwright.stop()
        except Exception:
            pass


class AuthManager:
    """
    Manages authentication and browser state for NotebookLM

    Features:
    - Interactive Google login
    - Browser state persistence
    - Session restoration
    - Account switching
    """

    def __init__(self):
        """Initialize the authentication manager"""
        # Ensure directories exist
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)

        self.state_file = STATE_FILE
        self.auth_info_file = AUTH_INFO_FILE
        self.browser_state_dir = BROWSER_STATE_DIR

    def is_authenticated(self) -> bool:
        """Check if valid authentication exists"""
        if not self.state_file.exists():
            return False

        # Check if state file is not too old (7 days)
        age_days = (time.time() - self.state_file.stat().st_mtime) / 86400
        if age_days > 7:
            print(f"⚠️ Browser state is {age_days:.1f} days old, may need re-authentication")

        return True

    def get_auth_info(self) -> Dict[str, Any]:
        """Get authentication information"""
        info = {
            'authenticated': self.is_authenticated(),
            'state_file': str(self.state_file),
            'state_exists': self.state_file.exists(),
            # Hint: a non-empty browser profile may hold a valid login even if state.json
            # is missing. If so, the user can run 'finalize' instead of logging in again.
            'profile_exists': BROWSER_PROFILE_DIR.exists() and any(BROWSER_PROFILE_DIR.iterdir())
        }

        if self.auth_info_file.exists():
            try:
                with open(self.auth_info_file, 'r') as f:
                    saved_info = json.load(f)
                    info.update(saved_info)
            except Exception:
                pass

        if info['state_exists']:
            age_hours = (time.time() - self.state_file.stat().st_mtime) / 3600
            info['state_age_hours'] = age_hours

        return info

    def setup_auth(self, headless: bool = False, timeout_minutes: int = 10) -> bool:
        """
        Perform interactive authentication setup

        Args:
            headless: Run browser in headless mode (False for login)
            timeout_minutes: Maximum time to wait for login

        Returns:
            True if authentication successful
        """
        print("🔐 Starting authentication setup...")
        print(f"  Timeout: {timeout_minutes} minutes")

        playwright = None
        context = None

        try:
            playwright = sync_playwright().start()

            # Launch using factory
            context = BrowserFactory.launch_persistent_context(
                playwright,
                headless=headless
            )

            # Navigate to NotebookLM
            page = context.new_page()
            page.goto(NOTEBOOK_HOME_URL, wait_until="domcontentloaded")

            # Check if already authenticated
            if is_notebook_url(page.url):
                print("  ✅ Already authenticated!")
                self._save_browser_state(context)
                return True

            # Wait for manual login
            print("\n  ⏳ Please log in to your Google account...")
            print(f"  ⏱️  Waiting up to {timeout_minutes} minutes for login...")

            # Wait for the URL to land on NotebookLM. We poll page.url directly instead of
            # wait_for_url: Google's redirects (login/consent/2FA) can throw transient
            # "frame detached" (net::ERR_ABORTED) errors, and wait_for_url also requires a
            # trailing slash that Chrome strips. Either failure would abort a successful login
            # before we persist state. Polling page.url is tolerant of all of this.
            deadline = time.time() + timeout_minutes * 60
            while time.time() < deadline:
                try:
                    current = page.url
                except Exception:
                    # Frame transiently unavailable (mid-navigation); keep waiting.
                    time.sleep(1)
                    continue

                if is_notebook_url(current):
                    # User is logged in and on NotebookLM. Persist state immediately.
                    self._save_browser_state(context)
                    self._save_auth_info()
                    print(f"  ✅ Login successful!")
                    return True

                # Still logging in (accounts.google.com or consent page); keep waiting.
                time.sleep(1)

            print(f"  ❌ Authentication timeout: no login within {timeout_minutes} minutes")
            return False

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return False

        finally:
            _close_session(playwright, context)

    def _save_browser_state(self, context: BrowserContext):
        """Save browser state to disk"""
        try:
            # Save storage state (cookies, localStorage)
            context.storage_state(path=str(self.state_file))
            print(f"  💾 Saved browser state to: {self.state_file}")
        except Exception as e:
            print(f"  ❌ Failed to save browser state: {e}")
            raise

    def _save_auth_info(self):
        """Save authentication metadata"""
        try:
            info = {
                'authenticated_at': time.time(),
                'authenticated_at_iso': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(self.auth_info_file, 'w') as f:
                json.dump(info, f, indent=2)
        except Exception:
            pass  # Non-critical

    def clear_auth(self) -> bool:
        """
        Clear all authentication data

        Returns:
            True if cleared successfully
        """
        print("🗑️ Clearing authentication data...")

        try:
            # Remove browser state
            if self.state_file.exists():
                self.state_file.unlink()
                print("  ✅ Removed browser state")

            # Remove auth info
            if self.auth_info_file.exists():
                self.auth_info_file.unlink()
                print("  ✅ Removed auth info")

            # Clear entire browser state directory
            if self.browser_state_dir.exists():
                shutil.rmtree(self.browser_state_dir)
                self.browser_state_dir.mkdir(parents=True, exist_ok=True)
                print("  ✅ Cleared browser data")

            return True

        except Exception as e:
            print(f"  ❌ Error clearing auth: {e}")
            return False

    def re_auth(self, headless: bool = False, timeout_minutes: int = 10) -> bool:
        """
        Perform re-authentication (clear and setup)

        Args:
            headless: Run browser in headless mode
            timeout_minutes: Login timeout in minutes

        Returns:
            True if successful
        """
        print("🔄 Starting re-authentication...")

        # Clear existing auth
        self.clear_auth()

        # Setup new auth
        return self.setup_auth(headless, timeout_minutes)

    def _launch_and_probe(self, headless: bool, settle: bool = False):
        """
        Launch the persistent profile and check whether it reaches NotebookLM signed in.

        The shared scaffolding for validate/finalize: start playwright, launch the
        persistent context, navigate to NOTEBOOK_HOME_URL, optionally let a redirect
        settle, and return ``(playwright, context)`` if the page is an authenticated
        Notebook page — ``(None, None)`` otherwise (or on error). The caller owns
        persistence and messaging and must close the returned session via
        ``_close_session``.

        Args:
            headless: Run the probe browser headless.
            settle: Poll the URL briefly for a redirect to resolve (used by finalize,
                where the profile may sit behind a transient redirect). Avoids a fixed
                blocking sleep: an already-landed page returns at once.
        """
        playwright = None
        context = None
        try:
            playwright = sync_playwright().start()
            context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
            page = context.new_page()
            page.goto(NOTEBOOK_HOME_URL, wait_until="domcontentloaded", timeout=30000)

            if settle:
                # Let any redirect resolve, but don't block when the page already landed.
                for _ in range(20):  # up to ~2s
                    if is_notebook_url(page.url):
                        break
                    page.wait_for_timeout(100)

            if is_notebook_url(page.url):
                return playwright, context

            # Not authenticated — close the probe session before returning.
            _close_session(playwright, context)
            return None, None

        except Exception as e:
            # A launch/navigation failure is not "not logged in" — surface it so the
            # caller doesn't misreport a broken browser install as an auth redirect.
            print(f"  ⚠️ Session probe failed: {e}")
            _close_session(playwright, context)
            return None, None

    def validate_auth(self) -> bool:
        """
        Validate that stored authentication works
        Uses persistent context to match actual usage pattern

        Returns:
            True if authentication is valid
        """
        if not self.is_authenticated():
            return False

        print("🔍 Validating authentication...")

        playwright, context = self._launch_and_probe(headless=True)
        if context is None:
            print("  ❌ Authentication is invalid (redirected to login)")
            return False

        print("  ✅ Authentication is valid")
        _close_session(playwright, context)
        return True

    def finalize_auth(self, headless: bool = True) -> bool:
        """
        Adopt an existing logged-in browser profile into recorded auth state.

        Launches the persistent profile (headless); if it reaches NotebookLM without a
        login redirect, writes state.json + auth_info.json. Use when the user visibly
        logged in but state.json was never saved (e.g., setup interrupted or it errored
        on a transient navigation failure). Avoids forcing a fresh login.

        Returns:
            True if the profile was authenticated and state was saved
        """
        print("🧩 Finalizing authentication from existing profile...")

        playwright, context = self._launch_and_probe(headless=headless, settle=True)
        if context is None:
            print("  ❌ Profile is not logged in (redirected to login).")
            print("     Run 'setup' to log in again.")
            return False

        print("  ✅ Profile is authenticated; saving state...")
        try:
            self._save_browser_state(context)
            self._save_auth_info()
            print("  ✅ State saved. Authentication is now recognized.")
            return True
        except Exception:
            # _save_browser_state already printed the cause; return a clean failure
            # instead of letting the re-raised exception escape as an uncaught traceback.
            print("  ❌ Finalize failed while saving state (see message above).")
            return False
        finally:
            _close_session(playwright, context)


def main():
    """Command-line interface for authentication management"""
    parser = argparse.ArgumentParser(description='Manage NotebookLM authentication')

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Setup command
    setup_parser = subparsers.add_parser('setup', help='Setup authentication')
    setup_parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    setup_parser.add_argument('--timeout', type=float, default=10, help='Login timeout in minutes (default: 10)')

    # Status command
    subparsers.add_parser('status', help='Check authentication status')

    # Validate command
    subparsers.add_parser('validate', help='Validate authentication')

    # Clear command
    subparsers.add_parser('clear', help='Clear authentication')

    # Re-auth command
    reauth_parser = subparsers.add_parser('reauth', help='Re-authenticate (clear + setup)')
    reauth_parser.add_argument('--timeout', type=float, default=10, help='Login timeout in minutes (default: 10)')

    # Finalize command (adopt an existing logged-in profile without a fresh login)
    finalize_parser = subparsers.add_parser(
        'finalize',
        help='Adopt an existing logged-in profile into auth state (writes state.json)'
    )
    finalize_parser.add_argument('--headless', action='store_true', help='Run in headless mode')

    args = parser.parse_args()

    # Initialize manager
    auth = AuthManager()

    # Execute command
    if args.command == 'setup':
        if auth.setup_auth(headless=args.headless, timeout_minutes=args.timeout):
            print("\n✅ Authentication setup complete!")
            print("You can now use ask_question.py to query NotebookLM")
        else:
            print("\n❌ Authentication setup failed")
            exit(1)

    elif args.command == 'status':
        info = auth.get_auth_info()
        print("\n🔐 Authentication Status:")
        print(f"  Authenticated: {'Yes' if info['authenticated'] else 'No'}")
        if info.get('state_age_hours'):
            print(f"  State age: {info['state_age_hours']:.1f} hours")
        if info.get('authenticated_at_iso'):
            print(f"  Last auth: {info['authenticated_at_iso']}")
        print(f"  State file: {info['state_file']}")
        if not info['authenticated'] and info.get('profile_exists'):
            print("  💡 Browser profile found but no saved state.")
            print("     If you already logged in, run: auth_manager.py finalize")

    elif args.command == 'validate':
        if auth.validate_auth():
            print("Authentication is valid and working")
        else:
            print("Authentication is invalid or expired")
            print("Run: auth_manager.py setup")

    elif args.command == 'clear':
        if auth.clear_auth():
            print("Authentication cleared")

    elif args.command == 'reauth':
        if auth.re_auth(timeout_minutes=args.timeout):
            print("\n✅ Re-authentication complete!")
        else:
            print("\n❌ Re-authentication failed")
            exit(1)

    elif args.command == 'finalize':
        if auth.finalize_auth(headless=args.headless):
            print("\n✅ Finalize complete! Authentication recognized.")
            print("You can now use ask_question.py to query NotebookLM")
        else:
            print("\n❌ Finalize failed (profile not logged in)")
            exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()