#!/usr/bin/env python3
"""
Finegold LLC Compliance Platform - One-Click Setup
Run this after cloning the repo to configure everything.

Usage:
    python scripts/setup_compliance.py
"""

import os
import sys
import shutil
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
ENV_FILE = SKILL_DIR / ".env"
ENV_EXAMPLE = SKILL_DIR / ".env.example"
DATA_DIR = SKILL_DIR / "data"

# Default config for Finegold
DEFAULT_CONFIG = {
    "ALERT_EMAIL_TO": "fernanda.mejia@finegold.ae,trex051192@gmail.com",
    "ALERT_EMAIL_FROM": "fgllccompliance@gmail.com",
    "ALERT_SMTP_HOST": "smtp.gmail.com",
    "ALERT_SMTP_PORT": "587",
    "ALERT_SMTP_USER": "fgllccompliance@gmail.com",
    "ALERT_SMTP_PASSWORD": "",
}


def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def step(num, msg):
    print(f"\n  [{num}] {msg}")


def main():
    banner("FINEGOLD LLC COMPLIANCE PLATFORM SETUP")
    print(f"  Working directory: {SKILL_DIR}")

    # ── Step 1: Create data directories ──────────────────────
    step(1, "Creating data directories...")
    dirs = [
        DATA_DIR,
        DATA_DIR / "reports",
        DATA_DIR / "str_reports",
        DATA_DIR / "gap_assessments",
        DATA_DIR / "sanctions_lists",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"       {d.relative_to(SKILL_DIR)}/")

    # ── Step 2: Create .env file ─────────────────────────────
    step(2, "Setting up email configuration (.env)...")
    if ENV_FILE.exists():
        print("       .env already exists - skipping")
        # Check if password is set
        content = ENV_FILE.read_text()
        if "ALERT_SMTP_PASSWORD=" in content:
            for line in content.splitlines():
                if line.startswith("ALERT_SMTP_PASSWORD="):
                    pwd = line.split("=", 1)[1].strip()
                    if pwd:
                        print("       Email password is configured")
                    else:
                        print("       WARNING: ALERT_SMTP_PASSWORD is empty!")
                        print("       Edit .env and add your Gmail App Password")
                        print("       Generate at: https://myaccount.google.com/apppasswords")
    else:
        # Ask for password
        print("       Creating .env with Finegold LLC defaults...")
        print()
        print("       Recipients: fernanda.mejia@finegold.ae, trex051192@gmail.com")
        print("       Sender:     fgllccompliance@gmail.com")
        print("       SMTP:       smtp.gmail.com:587")
        print()

        password = input("       Enter Gmail App Password for fgllccompliance@gmail.com\n"
                        "       (or press Enter to skip and set later): ").strip()

        if not password:
            password = "YOUR_APP_PASSWORD_HERE"
            print("       Skipped - edit .env later to add password")

        env_content = (
            "# Finegold LLC Compliance Alert Configuration\n"
            f"ALERT_EMAIL_TO={DEFAULT_CONFIG['ALERT_EMAIL_TO']}\n"
            f"ALERT_EMAIL_FROM={DEFAULT_CONFIG['ALERT_EMAIL_FROM']}\n"
            f"ALERT_SMTP_HOST={DEFAULT_CONFIG['ALERT_SMTP_HOST']}\n"
            f"ALERT_SMTP_PORT={DEFAULT_CONFIG['ALERT_SMTP_PORT']}\n"
            f"ALERT_SMTP_USER={DEFAULT_CONFIG['ALERT_SMTP_USER']}\n"
            f"ALERT_SMTP_PASSWORD={password}\n"
        )
        ENV_FILE.write_text(env_content)
        print(f"       Created: {ENV_FILE.relative_to(SKILL_DIR)}")

    # ── Step 3: Virtual environment ──────────────────────────
    step(3, "Checking Python virtual environment...")
    venv_dir = SKILL_DIR / ".venv"
    if venv_dir.exists():
        print("       .venv exists")
    else:
        print("       Run: python -m venv .venv && .venv/bin/pip install -r requirements.txt")

    # ── Step 4: Install cron scheduler ───────────────────────
    step(4, "Auto-scheduler (cron jobs)...")
    crontab = shutil.which("crontab")
    if crontab:
        print("       crontab available")
        print("       To install auto-alerts (checks every 5 min + 8 AM Dubai digest):")
        print(f"       python scripts/scheduler.py install")
        print(f"       To uninstall: python scripts/scheduler.py uninstall")
    else:
        print("       crontab not available on this system")
        print("       You can run checks manually or set up Task Scheduler on Windows")

    # ── Step 5: Test email ───────────────────────────────────
    step(5, "Testing email configuration...")
    try:
        sys.path.insert(0, str(SKILL_DIR / "scripts"))
        from email_notifier import is_configured, get_status
        if is_configured():
            status = get_status()
            print(f"       Email: CONFIGURED")
            print(f"       To:    {', '.join(status['recipients'])}")
            print(f"       From:  {status['sender']}")
            print(f"       SMTP:  {status['smtp_host']}:{status['smtp_port']}")

            test = input("\n       Send a test email? (y/n): ").strip().lower()
            if test == 'y':
                from email_notifier import send_email
                result = send_email(
                    "Finegold Compliance Platform - Setup Complete",
                    "Your compliance platform is configured and ready.\n\n"
                    "Tools available:\n"
                    "- Workflow management (tasks, meetings, reminders)\n"
                    "- Sanctions screening (UN, EU, UK, OFAC, UAE)\n"
                    "- Client KYC/AML database\n"
                    "- XAU/XAG price tracking\n"
                    "- Currency exchange rates\n"
                    "- STR/SAR template generator\n"
                    "- Compliance gap assessment\n"
                    "- Regulatory news feed (8 sources)\n"
                    "- UAE compliance calendar\n"
                    "- FATF risk country database\n"
                    "- Branded PDF reports\n"
                    "- Web dashboard\n"
                    "- Immutable audit trail\n\n"
                    "All notifications sent to Dubai time (GST, UTC+4).\n"
                    "Daily digest at 8:00 AM Dubai time.\n",
                    priority="high",
                )
                print(f"       {result}")
        else:
            print("       Email: NOT CONFIGURED")
            print("       Edit .env and add ALERT_SMTP_PASSWORD")
    except Exception as e:
        print(f"       Could not test email: {e}")

    # ── Step 6: Load compliance calendar ─────────────────────
    step(6, "Loading UAE compliance calendar...")
    try:
        from compliance_calendar import get_upcoming_deadlines
        deadlines = get_upcoming_deadlines(30)
        print(f"       {len(deadlines)} deadlines in next 30 days:")
        for d in deadlines[:3]:
            print(f"         [{d['authority']}] {d['title']} - {d['due'][:10]} ({d['days_until']}d)")
        if len(deadlines) > 3:
            print(f"         ... and {len(deadlines) - 3} more")
    except Exception as e:
        print(f"       Calendar error: {e}")

    # ── Step 7: Verify all modules ───────────────────────────
    step(7, "Verifying all modules...")
    modules = [
        ("workflow_manager", "Workflow Management"),
        ("email_notifier", "Email Alerts"),
        ("price_tracker", "XAU/XAG Prices"),
        ("currency_tracker", "Currency Exchange"),
        ("sanctions_checker", "Sanctions Screening"),
        ("client_database", "Client Database"),
        ("audit_trail", "Audit Trail"),
        ("report_generator", "Report Generator"),
        ("pdf_report", "PDF Reports"),
        ("onboarding_checklist", "Client Onboarding"),
        ("risk_countries", "FATF Risk Countries"),
        ("regulatory_feed", "Regulatory Feed"),
        ("compliance_calendar", "Compliance Calendar"),
        ("str_template", "STR/SAR Templates"),
        ("web_dashboard", "Web Dashboard"),
        ("gap_assessment", "Gap Assessment"),
        ("mcp_server", "MCP Server"),
    ]
    ok = 0
    fail = 0
    for mod_name, label in modules:
        try:
            __import__(mod_name)
            print(f"       OK  {label}")
            ok += 1
        except Exception as e:
            print(f"       FAIL  {label}: {e}")
            fail += 1

    # ── Summary ──────────────────────────────────────────────
    banner("SETUP COMPLETE")
    print(f"  Modules: {ok}/{ok+fail} loaded")
    print(f"  Data:    {SKILL_DIR / 'data'}")
    print()
    print("  HOW TO USE:")
    print("  1. Open Claude Code (CLI, Desktop, or VS Code)")
    print("  2. Navigate to this folder")
    print("  3. Ask Claude anything:")
    print('     - "Check my workflow"')
    print('     - "Screen Ahmed Al Maktoum against sanctions"')
    print('     - "Start onboarding for new corporate client"')
    print('     - "Generate executive compliance report"')
    print('     - "What are my upcoming CBUAE deadlines?"')
    print('     - "Run gap assessment on this policy document"')
    print('     - "Check if Iran is on FATF blacklist"')
    print('     - "Generate STR for suspicious client"')
    print()
    print("  WEB DASHBOARD:")
    print("    python scripts/web_dashboard.py")
    print("    Open http://localhost:8080 in your browser")
    print()
    print("  AUTO-SCHEDULER:")
    print("    python scripts/scheduler.py install")
    print("    (Checks every 5 min + daily digest at 8 AM Dubai)")
    print()
    print("  SUPPORT: trex051192@gmail.com")
    print()


if __name__ == "__main__":
    main()
