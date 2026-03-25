#!/usr/bin/env python3
"""
Email Notifier for Reminders & Alerts
Sends email notifications via SMTP (Gmail, Outlook, or custom SMTP).

Configuration via environment variables:
  ALERT_EMAIL_TO       - Recipient email address
  ALERT_EMAIL_FROM     - Sender email address (defaults to ALERT_EMAIL_TO)
  ALERT_SMTP_HOST      - SMTP server (default: smtp.gmail.com)
  ALERT_SMTP_PORT      - SMTP port (default: 587)
  ALERT_SMTP_USER      - SMTP username (defaults to ALERT_EMAIL_FROM)
  ALERT_SMTP_PASSWORD  - SMTP password or app password
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

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
    to_addr = os.environ.get("ALERT_EMAIL_TO", "")
    from_addr = os.environ.get("ALERT_EMAIL_FROM", to_addr)
    return {
        "to": to_addr,
        "from": from_addr,
        "host": os.environ.get("ALERT_SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("ALERT_SMTP_PORT", "587")),
        "user": os.environ.get("ALERT_SMTP_USER", from_addr),
        "password": os.environ.get("ALERT_SMTP_PASSWORD", ""),
    }


def is_configured() -> bool:
    """Check if email notifications are configured."""
    cfg = _get_config()
    return bool(cfg["to"] and cfg["password"])


def send_email(subject: str, body: str, priority: str = "medium") -> str:
    """Send an email alert.

    Args:
        subject: Email subject line
        body: Email body (plain text)
        priority: Reminder priority (affects email priority header)

    Returns:
        Success or error message
    """
    cfg = _get_config()

    if not cfg["to"]:
        return "Email not configured. Set ALERT_EMAIL_TO in your .env file."
    if not cfg["password"]:
        return "Email not configured. Set ALERT_SMTP_PASSWORD in your .env file."

    msg = MIMEMultipart()
    msg["From"] = cfg["from"]
    msg["To"] = cfg["to"]
    msg["Subject"] = subject

    # Set email priority header
    priority_map = {
        "critical": "1 (Highest)",
        "high": "2 (High)",
        "medium": "3 (Normal)",
        "low": "5 (Lowest)",
    }
    msg["X-Priority"] = priority_map.get(priority, "3 (Normal)")

    # Build body with timestamp
    full_body = f"{body}\n\n---\nSent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nFrom: NotebookLM Skill - Reminder System"
    msg.attach(MIMEText(full_body, "plain"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        return f"Email sent to {cfg['to']}"
    except Exception as e:
        return f"Failed to send email: {e}"


def send_reminder_alert(reminder: dict) -> str:
    """Send an email alert for a specific reminder."""
    priority = reminder.get("priority", "medium")
    prefix = {"critical": "CRITICAL", "high": "URGENT", "medium": "", "low": ""}.get(priority, "")
    subject = f"[Reminder{' - ' + prefix if prefix else ''}] {reminder['message']}"

    body_lines = [
        f"Reminder: {reminder['message']}",
        f"Due: {reminder.get('due', 'N/A')}",
        f"Priority: {priority}",
        f"Status: {reminder.get('status', 'pending')}",
    ]
    if reminder.get("tags"):
        body_lines.append(f"Tags: {', '.join(reminder['tags'])}")
    if reminder.get("recurrence", "none") != "none":
        body_lines.append(f"Recurrence: {reminder['recurrence']}")

    return send_email(subject, "\n".join(body_lines), priority)
