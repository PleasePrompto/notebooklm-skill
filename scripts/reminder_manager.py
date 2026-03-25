#!/usr/bin/env python3
"""
Reminder & Alert Manager
Persistent reminder system with priorities, recurrence, and due-date tracking.
"""

import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import re


class ReminderManager:
    """Manages reminders with persistence, priorities, and recurrence."""

    PRIORITIES = ("low", "medium", "high", "critical")
    RECURRENCE_TYPES = ("none", "daily", "weekly", "monthly")
    STATUSES = ("pending", "done", "snoozed", "overdue")

    def __init__(self):
        skill_dir = Path(__file__).parent.parent
        self.data_dir = skill_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reminders_file = self.data_dir / "reminders.json"
        self.reminders: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────

    def _load(self):
        if self.reminders_file.exists():
            try:
                with open(self.reminders_file, "r") as f:
                    data = json.load(f)
                self.reminders = data.get("reminders", {})
            except Exception:
                self.reminders = {}
        else:
            self._save()

    def _save(self):
        data = {
            "reminders": self.reminders,
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.reminders_file, "w") as f:
            json.dump(data, f, indent=2)

    # ── time parsing ─────────────────────────────────────────────

    @staticmethod
    def parse_due(due_str: str) -> str:
        """Parse a due-date string into ISO-8601.

        Accepts:
          - ISO-8601 (returned as-is)
          - Relative: "in 5m", "in 2h", "in 3d", "in 1w"
          - Natural:  "tomorrow", "next week", "next month"
        """
        due_str = due_str.strip()

        # Already ISO
        try:
            datetime.fromisoformat(due_str)
            return due_str
        except ValueError:
            pass

        now = datetime.now()

        # Relative: "in 5m", "in 2 hours", etc.
        rel = re.match(
            r"in\s+(\d+)\s*(m|min|mins|minutes?|h|hrs?|hours?|d|days?|w|weeks?)",
            due_str,
            re.IGNORECASE,
        )
        if rel:
            amount = int(rel.group(1))
            unit = rel.group(2)[0].lower()
            deltas = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount),
                      "d": timedelta(days=amount), "w": timedelta(weeks=amount)}
            return (now + deltas[unit]).isoformat()

        # Natural language shortcuts
        shortcuts = {
            "tomorrow": now + timedelta(days=1),
            "next week": now + timedelta(weeks=1),
            "next month": now + timedelta(days=30),
            "tonight": now.replace(hour=21, minute=0, second=0, microsecond=0),
            "end of day": now.replace(hour=17, minute=0, second=0, microsecond=0),
            "eod": now.replace(hour=17, minute=0, second=0, microsecond=0),
        }
        for key, dt in shortcuts.items():
            if due_str.lower() == key:
                return dt.isoformat()

        raise ValueError(
            f"Cannot parse due date: '{due_str}'. "
            "Use ISO-8601, relative (in 5m/2h/3d/1w), or natural (tomorrow, next week)."
        )

    # ── CRUD ─────────────────────────────────────────────────────

    def add(
        self,
        message: str,
        due: str,
        priority: str = "medium",
        recurrence: str = "none",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a new reminder."""
        if priority not in self.PRIORITIES:
            raise ValueError(f"Invalid priority '{priority}'. Choose from: {self.PRIORITIES}")
        if recurrence not in self.RECURRENCE_TYPES:
            raise ValueError(f"Invalid recurrence '{recurrence}'. Choose from: {self.RECURRENCE_TYPES}")

        due_iso = self.parse_due(due)
        reminder_id = str(uuid.uuid4())[:8]

        reminder = {
            "id": reminder_id,
            "message": message,
            "due": due_iso,
            "priority": priority,
            "recurrence": recurrence,
            "tags": tags or [],
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "snoozed_until": None,
            "completed_at": None,
        }
        self.reminders[reminder_id] = reminder
        self._save()
        return reminder

    def get(self, reminder_id: str) -> Optional[Dict[str, Any]]:
        return self.reminders.get(reminder_id)

    def delete(self, reminder_id: str) -> bool:
        if reminder_id in self.reminders:
            del self.reminders[reminder_id]
            self._save()
            return True
        return False

    def complete(self, reminder_id: str) -> Dict[str, Any]:
        r = self.reminders.get(reminder_id)
        if not r:
            raise ValueError(f"Reminder not found: {reminder_id}")

        now = datetime.now()

        # Handle recurrence: create next occurrence, keep current as done
        if r["recurrence"] != "none":
            due_dt = datetime.fromisoformat(r["due"])
            deltas = {
                "daily": timedelta(days=1),
                "weekly": timedelta(weeks=1),
                "monthly": timedelta(days=30),
            }
            next_due = due_dt + deltas[r["recurrence"]]
            # Create next occurrence
            self.add(
                message=r["message"],
                due=next_due.isoformat(),
                priority=r["priority"],
                recurrence=r["recurrence"],
                tags=r["tags"],
            )

        r["status"] = "done"
        r["completed_at"] = now.isoformat()
        r["updated_at"] = now.isoformat()
        self._save()
        return r

    def snooze(self, reminder_id: str, duration: str) -> Dict[str, Any]:
        r = self.reminders.get(reminder_id)
        if not r:
            raise ValueError(f"Reminder not found: {reminder_id}")

        new_due = self.parse_due(duration)
        r["due"] = new_due
        r["status"] = "snoozed"
        r["snoozed_until"] = new_due
        r["updated_at"] = datetime.now().isoformat()
        self._save()
        return r

    # ── queries ───────────────────────────────────────────────────

    def list_reminders(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        tag: Optional[str] = None,
        include_done: bool = False,
    ) -> List[Dict[str, Any]]:
        """List reminders with optional filters, sorted by due date."""
        self._update_overdue()

        results = []
        for r in self.reminders.values():
            if not include_done and r["status"] == "done":
                continue
            if status and r["status"] != status:
                continue
            if priority and r["priority"] != priority:
                continue
            if tag and tag not in r["tags"]:
                continue
            results.append(r)

        results.sort(key=lambda x: x["due"])
        return results

    def check_due(self) -> Dict[str, List[Dict[str, Any]]]:
        """Check for due and overdue reminders right now."""
        self._update_overdue()
        now = datetime.now()

        overdue = []
        due_soon = []  # within next 30 minutes

        for r in self.reminders.values():
            if r["status"] == "done":
                continue
            due_dt = datetime.fromisoformat(r["due"])
            if due_dt <= now:
                overdue.append(r)
            elif due_dt <= now + timedelta(minutes=30):
                due_soon.append(r)

        overdue.sort(key=lambda x: x["due"])
        due_soon.sort(key=lambda x: x["due"])

        return {"overdue": overdue, "due_soon": due_soon}

    def _update_overdue(self):
        """Mark pending reminders past their due date as overdue."""
        now = datetime.now()
        changed = False
        for r in self.reminders.values():
            if r["status"] in ("pending", "snoozed"):
                due_dt = datetime.fromisoformat(r["due"])
                if due_dt <= now and r["status"] != "overdue":
                    r["status"] = "overdue"
                    r["updated_at"] = now.isoformat()
                    changed = True
        if changed:
            self._save()
