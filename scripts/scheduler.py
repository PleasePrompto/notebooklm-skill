#!/usr/bin/env python3
"""
Workflow Auto-Alerter / Scheduler
Runs on a schedule (via cron) to check for due/overdue items and send email alerts.

Usage:
  # Check and send alerts for due items:
  python scripts/scheduler.py check

  # Install as a cron job (every 5 minutes):
  python scripts/scheduler.py install --interval 5

  # Uninstall the cron job:
  python scripts/scheduler.py uninstall

  # Show current cron status:
  python scripts/scheduler.py status

  # Dry run (show what would be sent, don't actually email):
  python scripts/scheduler.py check --dry-run
"""

import json
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE, TIMEZONE_NAME, DIGEST_CRON_UTC_HOUR

sys.path.insert(0, str(Path(__file__).parent))

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
DATA_DIR = SKILL_DIR / "data"
WORKFLOW_FILE = DATA_DIR / "workflow.json"
NOTIFIED_FILE = DATA_DIR / "notified.json"
SCHEDULER_LOG = DATA_DIR / "scheduler.log"
CRON_TAG = "notebooklm-workflow-scheduler"


# ── Notification tracking (prevent duplicates) ──────────────────

def _load_notified() -> Dict[str, str]:
    """Load set of already-notified item IDs with their notification type."""
    if NOTIFIED_FILE.exists():
        try:
            with open(NOTIFIED_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_notified(notified: Dict[str, str]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(NOTIFIED_FILE, "w") as f:
        json.dump(notified, f, indent=2)


def _log(message: str):
    """Append to scheduler log."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    with open(SCHEDULER_LOG, "a") as f:
        f.write(line)
    print(line.strip())


# ── Core check logic ────────────────────────────────────────────

def check_and_alert(dry_run: bool = False) -> Dict[str, Any]:
    """Check for due/overdue items and send email alerts.

    Returns summary of actions taken.
    """
    if not WORKFLOW_FILE.exists():
        _log("No workflow.json found. Nothing to check.")
        return {"checked": 0, "alerted": 0}

    with open(WORKFLOW_FILE, "r") as f:
        data = json.load(f)

    items = data.get("items", {})
    if not items:
        return {"checked": 0, "alerted": 0}

    now = datetime.now(TIMEZONE)
    notified = _load_notified()
    alerts_sent = 0
    alerts_detail = []

    # Import email notifier
    from email_notifier import send_workflow_alert, is_configured

    if not is_configured():
        _log("Email not configured. Set ALERT_EMAIL_TO and ALERT_SMTP_PASSWORD in .env")
        return {"checked": len(items), "alerted": 0, "error": "email_not_configured"}

    for item_id, item in items.items():
        if item.get("status") in ("done", "cancelled"):
            continue
        if not item.get("due"):
            continue

        try:
            due_dt = datetime.fromisoformat(item["due"])
        except ValueError:
            continue

        priority = item.get("priority", "medium")
        notification_key = None
        action = None

        # Determine what kind of alert to send
        if due_dt <= now:
            # Overdue
            prev_notification = notified.get(item_id)
            if prev_notification != "overdue":
                notification_key = "overdue"
                action = "OVERDUE"
                # Update status in workflow.json
                if item.get("status") not in ("overdue",):
                    item["status"] = "overdue"
                    item["updated_at"] = now.isoformat()

        elif due_dt <= now + timedelta(minutes=30):
            # Due soon (within 30 min)
            if item_id not in notified:
                notification_key = "due_soon"
                action = "due in 30 min"

        elif due_dt <= now + timedelta(hours=1) and priority in ("critical", "high"):
            # High/critical items: alert 1 hour ahead
            if item_id not in notified:
                notification_key = "due_1h"
                action = "due in 1 hour"

        if notification_key and action:
            type_label = item.get("type_label", item.get("type", "Item"))
            _log(f"ALERT: [{type_label}] {item['title']} - {action}")

            if not dry_run:
                result = send_workflow_alert(item, action=action)
                _log(f"  Email: {result}")

            notified[item_id] = notification_key
            alerts_sent += 1
            alerts_detail.append({
                "id": item_id,
                "title": item["title"],
                "type": type_label,
                "action": action,
            })

    # Save updated notifications and workflow state
    if not dry_run:
        _save_notified(notified)
        with open(WORKFLOW_FILE, "w") as f:
            json.dump(data, f, indent=2)

    # Clean up old notifications (items that are done/deleted)
    active_ids = set(items.keys())
    stale = [k for k in notified if k not in active_ids]
    for k in stale:
        del notified[k]
    if stale and not dry_run:
        _save_notified(notified)

    # Check price alerts too
    price_alerts_triggered = []
    try:
        from price_tracker import fetch_prices, check_price_alerts
        prices = fetch_prices()
        if "error" not in prices:
            triggered = check_price_alerts(prices)
            for a in triggered:
                _log(f"PRICE ALERT: {a['metal'].upper()} {a['condition']} ${a['target_price']:.2f} (now ${a['triggered_price']:.2f})")
                price_alerts_triggered.append(a)
                alerts_sent += 1
    except Exception as e:
        _log(f"Price check skipped: {e}")

    summary = {
        "checked": len(items),
        "alerted": alerts_sent,
        "alerts": alerts_detail,
        "price_alerts": price_alerts_triggered,
        "checked_at": now.isoformat(),
        "dry_run": dry_run,
    }

    if alerts_sent:
        _log(f"Sent {alerts_sent} alert(s)")
    else:
        _log("No new alerts")

    return summary


# ── Daily digest ─────────────────────────────────────────────────

def send_daily_digest(dry_run: bool = False) -> str:
    """Send a daily summary email of all active workflow items."""
    if not WORKFLOW_FILE.exists():
        return "No workflow data found."

    from email_notifier import send_email, is_configured
    if not is_configured():
        return "Email not configured."

    with open(WORKFLOW_FILE, "r") as f:
        data = json.load(f)

    items = data.get("items", {})
    now = datetime.now(TIMEZONE)

    overdue = []
    due_today = []
    upcoming = []
    in_progress = []

    today_end = now.replace(hour=23, minute=59, second=59)
    week_end = now + timedelta(days=7)

    for item in items.values():
        if item.get("status") in ("done", "cancelled"):
            continue

        if item.get("status") == "in_progress":
            in_progress.append(item)

        if not item.get("due"):
            continue

        try:
            due_dt = datetime.fromisoformat(item["due"])
        except ValueError:
            continue

        if due_dt <= now:
            overdue.append(item)
        elif due_dt <= today_end:
            due_today.append(item)
        elif due_dt <= week_end:
            upcoming.append(item)

    # Build digest
    lines = [
        f"Workflow Daily Digest - {now.strftime('%A, %B %d, %Y')}",
        "=" * 50,
        "",
    ]

    if overdue:
        lines.append(f"OVERDUE ({len(overdue)}):")
        for it in sorted(overdue, key=lambda x: x["due"]):
            lines.append(f"  [{it['priority'].upper()}] {it.get('type_label', it['type'])}: {it['title']} (due {it['due'][:16]})")
        lines.append("")

    if due_today:
        lines.append(f"DUE TODAY ({len(due_today)}):")
        for it in sorted(due_today, key=lambda x: x["due"]):
            lines.append(f"  [{it['priority'].upper()}] {it.get('type_label', it['type'])}: {it['title']} (due {it['due'][:16]})")
        lines.append("")

    if in_progress:
        lines.append(f"IN PROGRESS ({len(in_progress)}):")
        for it in in_progress:
            due_str = f" (due {it['due'][:16]})" if it.get("due") else ""
            lines.append(f"  {it.get('type_label', it['type'])}: {it['title']}{due_str}")
        lines.append("")

    if upcoming:
        lines.append(f"UPCOMING 7 DAYS ({len(upcoming)}):")
        for it in sorted(upcoming, key=lambda x: x["due"]):
            lines.append(f"  {it.get('type_label', it['type'])}: {it['title']} (due {it['due'][:16]})")
        lines.append("")

    if not any([overdue, due_today, in_progress, upcoming]):
        lines.append("All clear! No pending items.")

    body = "\n".join(lines)

    if dry_run:
        print(body)
        return "Dry run - digest not sent"

    subject = f"Workflow Digest - {now.strftime('%b %d')} | {len(overdue)} overdue, {len(due_today)} due today"
    result = send_email(subject, body, "high" if overdue else "medium")
    _log(f"Daily digest: {result}")
    return result


# ── Cron management ──────────────────────────────────────────────

def _get_python_path() -> str:
    """Get the Python interpreter path (prefer venv)."""
    venv_python = SKILL_DIR / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def install_cron(interval: int = 5, include_digest: bool = True):
    """Install cron jobs for auto-alerting."""
    python = _get_python_path()
    script = str(SCRIPT_DIR / "scheduler.py")

    # Alert check every N minutes
    alert_job = f"*/{interval} * * * * cd {SKILL_DIR} && {python} {script} check  # {CRON_TAG}"

    # Daily digest at 8:00 AM Dubai time (UTC+4 = 4 AM UTC)
    digest_job = f"0 {DIGEST_CRON_UTC_HOUR} * * * cd {SKILL_DIR} && {python} {script} digest  # {CRON_TAG}"

    # Get existing crontab (excluding our jobs)
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        current_lines = existing.stdout.strip().split("\n") if existing.returncode == 0 else []
    except FileNotFoundError:
        current_lines = []

    # Remove old entries
    filtered = [line for line in current_lines if CRON_TAG not in line and line.strip()]

    # Add new entries
    filtered.append(alert_job)
    if include_digest:
        filtered.append(digest_job)

    new_crontab = "\n".join(filtered) + "\n"

    # Install
    proc = subprocess.run(["crontab", "-"], input=new_crontab, capture_output=True, text=True)
    if proc.returncode == 0:
        _log(f"Cron installed: check every {interval}min, daily digest at 8AM")
        print(f"Installed cron jobs:")
        print(f"  Alert check: every {interval} minutes")
        if include_digest:
            print(f"  Daily digest: 8:00 AM Dubai time ({TIMEZONE_NAME})")
        print(f"\nView with: crontab -l")
    else:
        print(f"Failed to install cron: {proc.stderr}")


def uninstall_cron():
    """Remove scheduler cron jobs."""
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if existing.returncode != 0:
            print("No crontab found.")
            return
        current_lines = existing.stdout.strip().split("\n")
    except FileNotFoundError:
        print("crontab not available.")
        return

    filtered = [line for line in current_lines if CRON_TAG not in line and line.strip()]
    new_crontab = "\n".join(filtered) + "\n" if filtered else ""

    subprocess.run(["crontab", "-"], input=new_crontab, capture_output=True, text=True)
    _log("Cron jobs uninstalled")
    print("Scheduler cron jobs removed.")


def cron_status():
    """Show current cron job status."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0:
            print("No crontab configured.")
            return

        our_jobs = [line for line in result.stdout.split("\n") if CRON_TAG in line]
        if our_jobs:
            print("Active scheduler jobs:")
            for job in our_jobs:
                print(f"  {job}")
        else:
            print("No scheduler cron jobs installed.")
            print("Install with: python scripts/scheduler.py install")
    except FileNotFoundError:
        print("crontab not available on this system.")

    # Show last log entries
    if SCHEDULER_LOG.exists():
        print(f"\nRecent log ({SCHEDULER_LOG}):")
        lines = SCHEDULER_LOG.read_text().strip().split("\n")
        for line in lines[-10:]:
            print(f"  {line}")

    # Show notification state
    if NOTIFIED_FILE.exists():
        notified = _load_notified()
        print(f"\nTracked notifications: {len(notified)} items")


# ── CLI ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Workflow Auto-Alerter")
    subparsers = parser.add_subparsers(dest="command")

    # check
    check_p = subparsers.add_parser("check", help="Check for due items and send alerts")
    check_p.add_argument("--dry-run", action="store_true", help="Show what would be sent without emailing")

    # digest
    digest_p = subparsers.add_parser("digest", help="Send daily digest email")
    digest_p.add_argument("--dry-run", action="store_true", help="Print digest without sending")

    # install
    install_p = subparsers.add_parser("install", help="Install as cron job")
    install_p.add_argument("--interval", type=int, default=5, help="Check interval in minutes (default: 5)")
    install_p.add_argument("--no-digest", action="store_true", help="Skip daily digest job")

    # uninstall
    subparsers.add_parser("uninstall", help="Remove cron jobs")

    # status
    subparsers.add_parser("status", help="Show scheduler status")

    args = parser.parse_args()

    if args.command == "check":
        result = check_and_alert(dry_run=args.dry_run)
        print(json.dumps(result, indent=2))

    elif args.command == "digest":
        result = send_daily_digest(dry_run=args.dry_run)
        print(result)

    elif args.command == "install":
        install_cron(interval=args.interval, include_digest=not args.no_digest)

    elif args.command == "uninstall":
        uninstall_cron()

    elif args.command == "status":
        cron_status()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
