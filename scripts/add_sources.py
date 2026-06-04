#!/usr/bin/env python3
"""
Add sources to a NEW NotebookLM notebook (fills the gap the skill lacks).

Reuses the skill's authenticated persistent browser profile (BrowserFactory)
so it works after `auth_manager.py setup`. Creates a notebook, bulk-uploads
local source files (.txt/.pdf/.md), optionally renames it, and prints the URL.

Usage:
  python scripts/run.py add_sources.py --sources-dir /path/to/sources --name "My Notebook"
  python scripts/run.py add_sources.py --probe        # just open home + screenshot to inspect UI
Flags:
  --headless     run hidden (default: visible)
  --keep-open    leave browser open at end (default: close)
  --timeout-s    seconds to wait for source processing (default: 240)
"""
import argparse, sys, time, glob, os, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from patchright.sync_api import sync_playwright
from auth_manager import AuthManager
from browser_utils import BrowserFactory
from config import DATA_DIR

SHOTS = DATA_DIR / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

def shot(page, name):
    try:
        p = str(SHOTS / name)
        page.screenshot(path=p, full_page=False)
        print(f"  📸 {p}")
    except Exception as e:
        print(f"  ⚠️ screenshot failed: {e}")

def dump_buttons(page, limit=40):
    """Print visible clickable labels to help adapt selectors."""
    try:
        texts = page.eval_on_selector_all(
            "button, [role=button], a, mat-card, .upload-button",
            "els => els.map(e => (e.innerText||e.getAttribute('aria-label')||'').trim()).filter(Boolean).slice(0, %d)" % limit,
        )
        print("  🔎 clickable labels:", [t[:40] for t in texts])
    except Exception as e:
        print(f"  ⚠️ dump failed: {e}")

def try_click(page, candidates, what, timeout=8000):
    """Try a list of (kind, value) locators; click the first that works."""
    for kind, val in candidates:
        try:
            if kind == "role_btn":
                loc = page.get_by_role("button", name=re.compile(val, re.I))
            elif kind == "text":
                loc = page.get_by_text(re.compile(val, re.I))
            elif kind == "css":
                loc = page.locator(val)
            else:
                continue
            loc = loc.first
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            print(f"  ✅ clicked {what} via {kind}:{val}")
            return True
        except Exception:
            continue
    print(f"  ❌ could not click {what}")
    return False

def rename_notebook(page, name):
    """Replace the notebook title. NotebookLM's title is <input class='title-input'>.
    fill() clears+sets and dispatches the input event Angular needs; Tab blurs to commit."""
    input_sels = ["input.title-input", "input[aria-label*='title' i]", "textarea[aria-label*='title' i]"]
    for sel in input_sels:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=4000)
            el.click()
            el.fill("")
            page.wait_for_timeout(200)
            el.fill(name)
            page.wait_for_timeout(200)
            page.keyboard.press("Tab")       # blur to commit (Enter can insert newline)
            page.wait_for_timeout(1200)
            print(f"  ✅ renamed via {sel}")
            return True
        except Exception:
            continue
    # Fallback: contenteditable title
    try:
        el = page.locator("[contenteditable='true']").first
        el.wait_for(state="visible", timeout=3000)
        el.click(click_count=3)
        page.keyboard.press("Meta+A"); page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(name, delay=20)
        page.keyboard.press("Tab")
        print("  ✅ renamed via contenteditable")
        return True
    except Exception:
        pass
    print("  ⚠️ rename: no editable title found")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources-dir")
    ap.add_argument("--name", default="New Notebook")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--keep-open", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--rename-only")  # value = notebook URL to rename
    ap.add_argument("--timeout-s", type=int, default=240)
    args = ap.parse_args()

    if not AuthManager().is_authenticated():
        print("❌ Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return 1

    files = []
    if args.sources_dir:
        for ext in ("*.txt", "*.pdf", "*.md"):
            files += sorted(glob.glob(os.path.join(args.sources_dir, ext)))
        if not files and not args.probe:
            print(f"❌ No source files found in {args.sources_dir}")
            return 1

    pw = sync_playwright().start()
    ctx = BrowserFactory.launch_persistent_context(pw, headless=args.headless)
    try:
        page = ctx.new_page()

        if args.rename_only:
            print(f"✏️  Rename-only: {args.rename_only}")
            page.goto(args.rename_only, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            rename_notebook(page, args.name)
            shot(page, "rename_only.png")
            print(f"DONE rename → {args.name}")
            return 0

        print("🌐 Opening NotebookLM…")
        page.goto("https://notebooklm.google.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        if "accounts.google.com" in page.url:
            print("❌ Redirected to login — auth expired. Re-run auth_manager.py setup")
            shot(page, "auth_redirect.png"); return 1
        shot(page, "01_home.png")

        if args.probe:
            dump_buttons(page)
            print(f"URL: {page.url}")
            if args.keep_open:
                print("Browser open. Ctrl-C to quit.");
                while True: page.wait_for_timeout(2000)
            return 0

        # --- Create a new notebook ---
        print("➕ Creating new notebook…")
        try_click(page, [
            ("role_btn", r"create new|new notebook|create"),
            ("text", r"^\s*Create new\s*$"),
            ("text", r"Create new notebook"),
            ("css", "button.create-new-button"),
            ("css", "[aria-label*='Create' i]"),
        ], "Create-new")
        page.wait_for_timeout(3500)
        shot(page, "02_after_create.png")
        dump_buttons(page)

        # --- Upload files via the file input ---
        print(f"📤 Uploading {len(files)} source files…")
        uploaded = False
        # The add-source modal usually exposes a (often hidden) <input type=file>.
        for attempt in range(2):
            try:
                fi = page.locator("input[type=file]").first
                fi.wait_for(state="attached", timeout=8000)
                fi.set_input_files(files)
                uploaded = True
                print("  ✅ files attached to input[type=file]")
                break
            except Exception as e:
                print(f"  ⚠️ no file input yet ({e}); trying to open upload dialog…")
                try_click(page, [
                    ("text", r"upload sources|upload|choose file|select file"),
                    ("role_btn", r"upload|add source"),
                ], "open-upload")
                page.wait_for_timeout(2500)
        if not uploaded:
            print("  ❌ Could not attach files. Saving screenshot for inspection.")
            shot(page, "03_upload_fail.png"); dump_buttons(page)
            if args.keep_open:
                while True: page.wait_for_timeout(2000)
            return 1

        # --- Wait for processing ---
        print(f"⏳ Waiting up to {args.timeout_s}s for sources to import…")
        deadline = time.time() + args.timeout_s
        last = -1
        while time.time() < deadline:
            page.wait_for_timeout(4000)
            # Heuristic: count source rows / checkboxes in the sources panel
            try:
                n = page.locator(".single-source-container, .source-item, mat-checkbox").count()
            except Exception:
                n = 0
            if n != last:
                print(f"  …sources visible: {n}")
                last = n
            # processing indicators gone?
            try:
                busy = page.locator("mat-progress-bar, mat-spinner, .loading").count()
            except Exception:
                busy = 1
            if last >= len(files) and busy == 0:
                break
        shot(page, "04_sources_loaded.png")

        # --- Rename the notebook (best effort) ---
        print(f"✏️  Renaming notebook to: {args.name}")
        rename_notebook(page, args.name)
        shot(page, "05_done.png")

        url = page.url
        print("\n" + "=" * 60)
        print(f"NOTEBOOK_URL: {url}")
        print(f"SOURCES_UPLOADED: {len(files)}")
        print("=" * 60)

        if args.keep_open:
            print("Browser left open. Ctrl-C to quit.")
            while True:
                page.wait_for_timeout(2000)
        return 0
    finally:
        if not args.keep_open:
            try: ctx.close()
            except Exception: pass
            try: pw.stop()
            except Exception: pass

if __name__ == "__main__":
    sys.exit(main())
