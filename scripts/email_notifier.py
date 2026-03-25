#!/usr/bin/env python3
"""
Email Notifier for Workflow Alerts
Sends email notifications via SMTP (Gmail, Outlook, or custom SMTP).
Supports multiple recipients (comma-separated).

Configuration via environment variables (or .env file):
  ALERT_EMAIL_TO       - Recipient(s), comma-separated (e.g. "work@co.com,personal@gmail.com")
  ALERT_EMAIL_FROM     - Sender email address (defaults to first ALERT_EMAIL_TO)
  ALERT_SMTP_HOST      - SMTP server (default: smtp.gmail.com)
  ALERT_SMTP_PORT      - SMTP port (default: 587)
  ALERT_SMTP_USER      - SMTP username (defaults to ALERT_EMAIL_FROM)
  ALERT_SMTP_PASSWORD  - SMTP password or app password
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE, TIMEZONE_NAME

# Try loading .env from project root
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def _get_config():
    """Load email config from environment."""
    to_raw = os.environ.get("ALERT_EMAIL_TO", "")
    to_list = [e.strip() for e in to_raw.split(",") if e.strip()]
    from_addr = os.environ.get("ALERT_EMAIL_FROM", to_list[0] if to_list else "")
    return {
        "to_list": to_list,
        "to": ", ".join(to_list),
        "from": from_addr,
        "host": os.environ.get("ALERT_SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("ALERT_SMTP_PORT", "587")),
        "user": os.environ.get("ALERT_SMTP_USER", from_addr),
        "password": os.environ.get("ALERT_SMTP_PASSWORD", ""),
    }


def is_configured() -> bool:
    """Check if email notifications are configured."""
    cfg = _get_config()
    return bool(cfg["to_list"] and cfg["password"])


def get_status() -> dict:
    """Return email configuration status (no secrets)."""
    cfg = _get_config()
    return {
        "configured": bool(cfg["to_list"] and cfg["password"]),
        "recipients": cfg["to_list"],
        "sender": cfg["from"],
        "smtp_host": cfg["host"],
        "smtp_port": cfg["port"],
    }


def send_email(
    subject: str,
    body: str,
    priority: str = "medium",
    extra_recipients: Optional[List[str]] = None,
) -> str:
    """Send an email alert to all configured recipients.

    Args:
        subject: Email subject line
        body: Email body (plain text)
        priority: Priority level (affects email X-Priority header)
        extra_recipients: Additional one-time recipients

    Returns:
        Success or error message
    """
    cfg = _get_config()

    recipients = list(cfg["to_list"])
    if extra_recipients:
        recipients.extend(extra_recipients)
    recipients = list(dict.fromkeys(recipients))  # deduplicate, preserve order

    if not recipients:
        return "Email not configured. Set ALERT_EMAIL_TO in your .env file."
    if not cfg["password"]:
        return "Email not configured. Set ALERT_SMTP_PASSWORD in your .env file."

    msg = MIMEMultipart()
    msg["From"] = cfg["from"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    # Email priority header
    priority_map = {
        "critical": "1 (Highest)",
        "high": "2 (High)",
        "medium": "3 (Normal)",
        "low": "5 (Lowest)",
    }
    msg["X-Priority"] = priority_map.get(priority, "3 (Normal)")

    # Build body with footer
    dubai_now = datetime.now(TIMEZONE)
    full_body = (
        f"{body}\n\n"
        f"---\n"
        f"Sent at: {dubai_now.strftime('%Y-%m-%d %H:%M:%S')} ({TIMEZONE_NAME})\n"
        f"From: Workflow Manager - NotebookLM Skill"
    )
    msg.attach(MIMEText(full_body, "plain"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        return f"Email sent to {', '.join(recipients)}"
    except Exception as e:
        return f"Failed to send email: {e}"


def send_reminder_alert(reminder: dict) -> str:
    """Send an email alert for a specific reminder."""
    priority = reminder.get("priority", "medium")
    prefix = {"critical": "CRITICAL", "high": "URGENT"}.get(priority, "")
    subject = f"[Reminder{' - ' + prefix if prefix else ''}] {reminder.get('message', reminder.get('title', ''))}"

    body_lines = [
        f"Reminder: {reminder.get('message', reminder.get('title', ''))}",
        f"Due: {reminder.get('due', 'N/A')}",
        f"Priority: {priority}",
        f"Status: {reminder.get('status', 'pending')}",
    ]
    if reminder.get("tags"):
        body_lines.append(f"Tags: {', '.join(reminder['tags'])}")
    if reminder.get("recurrence", "none") != "none":
        body_lines.append(f"Recurrence: {reminder['recurrence']}")

    return send_email(subject, "\n".join(body_lines), priority)


def send_workflow_alert(item: dict, action: str = "alert") -> str:
    """Send an email alert for a workflow item (task, meeting, etc.)."""
    type_label = item.get("type_label", item.get("type", "Item"))
    priority = item.get("priority", "medium")
    prefix = {"critical": "CRITICAL", "high": "URGENT"}.get(priority, "")
    subject = f"[{type_label}{' - ' + prefix if prefix else ''}] {item['title']} ({action})"

    body_lines = [
        f"Type: {type_label}",
        f"Title: {item['title']}",
    ]
    if item.get("description"):
        body_lines.append(f"Description: {item['description']}")
    if item.get("due"):
        body_lines.append(f"Due: {item['due']}")
    body_lines.append(f"Priority: {priority}")
    body_lines.append(f"Status: {item.get('status', 'pending')}")
    if item.get("tags"):
        body_lines.append(f"Tags: {', '.join(item['tags'])}")
    if item.get("details"):
        body_lines.append("")
        body_lines.append("Details:")
        for k, v in item["details"].items():
            if v:
                body_lines.append(f"  {k.replace('_', ' ').title()}: {v}")

    return send_email(subject, "\n".join(body_lines), priority)
