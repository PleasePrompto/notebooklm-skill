#!/usr/bin/env python3
"""
Workflow Manager — unified tracking for tasks, projects, meetings,
documents, trainings, reports, messages, and follow-ups.

Every item shares a common schema with type-specific detail fields.
Supports priorities, statuses, deadlines, recurrence, tags, follow-up
chains, and email notifications.
"""

import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from config import TIMEZONE
import re


# ── Item types and their allowed detail fields ────────────────────

ITEM_TYPES = {
    "task": {
        "label": "Task",
        "detail_fields": ["assignee", "project_id", "checklist", "progress"],
    },
    "project": {
        "label": "Project",
        "detail_fields": ["milestones", "team", "goal", "progress"],
    },
    "meeting": {
        "label": "Meeting",
        "detail_fields": ["attendees", "agenda", "location", "meeting_link", "duration", "notes"],
    },
    "document": {
        "label": "Document",
        "detail_fields": ["doc_type", "reviewer", "approval_status", "link", "version"],
    },
    "training": {
        "label": "Training",
        "detail_fields": ["trainer", "trainees", "material_link", "completed_by", "certification"],
    },
    "report": {
        "label": "Report",
        "detail_fields": ["report_type", "recipients", "frequency", "template_link", "submitted"],
    },
    "message": {
        "label": "Message",
        "detail_fields": ["to", "channel", "body", "sent", "response_needed"],
    },
    "follow_up": {
        "label": "Follow-up",
        "detail_fields": ["parent_id", "parent_type", "action_required", "context"],
    },
    "reminder": {
        "label": "Reminder",
        "detail_fields": ["context"],
    },
}

PRIORITIES = ("low", "medium", "high", "critical")
STATUSES = ("pending", "in_progress", "waiting", "done", "overdue", "cancelled", "snoozed")
RECURRENCE_TYPES = ("none", "daily", "weekly", "biweekly", "monthly", "quarterly")


class WorkflowManager:
    """Unified workflow item manager with persistence."""

    def __init__(self):
        skill_dir = Path(__file__).parent.parent
        self.data_dir = skill_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_file = self.data_dir / "workflow.json"
        self.items: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────

    def _load(self):
        if self.db_file.exists():
            try:
                with open(self.db_file, "r") as f:
                    data = json.load(f)
                self.items = data.get("items", {})
            except Exception:
                self.items = {}
        else:
            self._save()

    def _save(self):
        with open(self.db_file, "w") as f:
            json.dump(
                {"items": self.items, "updated_at": datetime.now(TIMEZONE).isoformat()},
                f,
                indent=2,
            )

    # ── time parsing ─────────────────────────────────────────────

    @staticmethod
    def parse_due(due_str: str) -> str:
        """Parse flexible due-date strings into ISO-8601.

        Accepts:
          - ISO-8601 datetime
          - Relative: "in 5m", "in 2h", "in 3d", "in 1w"
          - Natural:  "tomorrow", "next week", "next month", "eod", "tonight",
                      "monday" .. "friday", "end of week"
        """
        due_str = due_str.strip()

        # Already ISO
        try:
            datetime.fromisoformat(due_str)
            return due_str
        except ValueError:
            pass

        now = datetime.now(TIMEZONE)

        # Relative: "in 5m", "in 2 hours", etc.
        rel = re.match(
            r"in\s+(\d+)\s*(m|min|mins|minutes?|h|hrs?|hours?|d|days?|w|weeks?)",
            due_str,
            re.IGNORECASE,
        )
        if rel:
            amount = int(rel.group(1))
            unit = rel.group(2)[0].lower()
            deltas = {
                "m": timedelta(minutes=amount),
                "h": timedelta(hours=amount),
                "d": timedelta(days=amount),
                "w": timedelta(weeks=amount),
            }
            return (now + deltas[unit]).isoformat()

        # Day names → next occurrence
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        lower = due_str.lower()
        if lower in day_names:
            target_day = day_names.index(lower)
            days_ahead = target_day - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return (now + timedelta(days=days_ahead)).replace(
                hour=9, minute=0, second=0, microsecond=0
            ).isoformat()

        # Natural shortcuts
        shortcuts = {
            "tomorrow": (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0),
            "next week": (now + timedelta(weeks=1)).replace(hour=9, minute=0, second=0, microsecond=0),
            "next month": (now + timedelta(days=30)).replace(hour=9, minute=0, second=0, microsecond=0),
            "tonight": now.replace(hour=21, minute=0, second=0, microsecond=0),
            "end of day": now.replace(hour=17, minute=0, second=0, microsecond=0),
            "eod": now.replace(hour=17, minute=0, second=0, microsecond=0),
            "end of week": (now + timedelta(days=(4 - now.weekday()) % 7)).replace(
                hour=17, minute=0, second=0, microsecond=0
            ),
            "eow": (now + timedelta(days=(4 - now.weekday()) % 7)).replace(
                hour=17, minute=0, second=0, microsecond=0
            ),
        }
        for key, dt in shortcuts.items():
            if lower == key:
                return dt.isoformat()

        raise ValueError(
            f"Cannot parse due date: '{due_str}'. "
            "Use ISO-8601, relative (in 5m/2h/3d/1w), day name, or natural (tomorrow, eod, next week)."
        )

    # ── CRUD ─────────────────────────────────────────────────────

    def create(
        self,
        item_type: str,
        title: str,
        due: Optional[str] = None,
        description: str = "",
        priority: str = "medium",
        recurrence: str = "none",
        tags: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
        notify: bool = False,
    ) -> Dict[str, Any]:
        """Create a new workflow item."""
        if item_type not in ITEM_TYPES:
            raise ValueError(f"Invalid type '{item_type}'. Choose from: {list(ITEM_TYPES.keys())}")
        if priority not in PRIORITIES:
            raise ValueError(f"Invalid priority '{priority}'. Choose from: {list(PRIORITIES)}")
        if recurrence not in RECURRENCE_TYPES:
            raise ValueError(f"Invalid recurrence '{recurrence}'. Choose from: {list(RECURRENCE_TYPES)}")

        item_id = str(uuid.uuid4())[:8]
        now_iso = datetime.now(TIMEZONE).isoformat()

        item = {
            "id": item_id,
            "type": item_type,
            "type_label": ITEM_TYPES[item_type]["label"],
            "title": title,
            "description": description,
            "due": self.parse_due(due) if due else None,
            "priority": priority,
            "recurrence": recurrence,
            "status": "pending",
            "tags": tags or [],
            "details": details or {},
            "created_at": now_iso,
            "updated_at": now_iso,
            "completed_at": None,
            "snoozed_until": None,
            "follow_ups": [],
        }

        self.items[item_id] = item
        self._save()

        # Send email if requested
        if notify:
            self._notify(item, action="created")

        return item

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        return self.items.get(item_id)

    def update(self, item_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update fields on an existing item."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        allowed_fields = {
            "title", "description", "due", "priority", "status",
            "recurrence", "tags", "details",
        }
        for key, value in updates.items():
            if key in allowed_fields:
                if key == "due" and value:
                    value = self.parse_due(value)
                if key == "details":
                    item["details"].update(value)
                else:
                    item[key] = value

        item["updated_at"] = datetime.now(TIMEZONE).isoformat()
        self._save()
        return item

    def delete(self, item_id: str) -> bool:
        if item_id in self.items:
            del self.items[item_id]
            self._save()
            return True
        return False

    def complete(self, item_id: str) -> Dict[str, Any]:
        """Mark item as done. Recurring items spawn next occurrence."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        now = datetime.now(TIMEZONE)

        # Handle recurrence
        next_item = None
        if item["recurrence"] != "none" and item.get("due"):
            due_dt = datetime.fromisoformat(item["due"])
            deltas = {
                "daily": timedelta(days=1),
                "weekly": timedelta(weeks=1),
                "biweekly": timedelta(weeks=2),
                "monthly": timedelta(days=30),
                "quarterly": timedelta(days=91),
            }
            next_due = due_dt + deltas[item["recurrence"]]
            next_item = self.create(
                item_type=item["type"],
                title=item["title"],
                due=next_due.isoformat(),
                description=item["description"],
                priority=item["priority"],
                recurrence=item["recurrence"],
                tags=item["tags"],
                details=item["details"],
            )

        item["status"] = "done"
        item["completed_at"] = now.isoformat()
        item["updated_at"] = now.isoformat()
        self._save()

        return {"completed": item, "next_occurrence": next_item}

    def snooze(self, item_id: str, until: str) -> Dict[str, Any]:
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")

        new_due = self.parse_due(until)
        item["due"] = new_due
        item["status"] = "snoozed"
        item["snoozed_until"] = new_due
        item["updated_at"] = datetime.now(TIMEZONE).isoformat()
        self._save()
        return item

    # ── Follow-ups ───────────────────────────────────────────────

    def add_follow_up(
        self,
        parent_id: str,
        title: str,
        due: Optional[str] = None,
        description: str = "",
        priority: str = "medium",
        notify: bool = False,
    ) -> Dict[str, Any]:
        """Create a follow-up item linked to a parent."""
        parent = self.items.get(parent_id)
        if not parent:
            raise ValueError(f"Parent item not found: {parent_id}")

        follow_up = self.create(
            item_type="follow_up",
            title=title,
            due=due,
            description=description,
            priority=priority,
            details={
                "parent_id": parent_id,
                "parent_type": parent["type"],
                "context": f"Follow-up for: {parent['title']}",
            },
            notify=notify,
        )

        parent["follow_ups"].append(follow_up["id"])
        parent["updated_at"] = datetime.now(TIMEZONE).isoformat()
        self._save()

        return follow_up

    # ── Queries ───────────────────────────────────────────────────

    def list_items(
        self,
        item_type: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        tag: Optional[str] = None,
        include_done: bool = False,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List items with optional filters, sorted by due date."""
        self._update_overdue()
        results = []

        for item in self.items.values():
            if not include_done and item["status"] == "done":
                continue
            if item_type and item["type"] != item_type:
                continue
            if status and item["status"] != status:
                continue
            if priority and item["priority"] != priority:
                continue
            if tag and tag not in item["tags"]:
                continue
            if search:
                search_lower = search.lower()
                searchable = f"{item['title']} {item['description']} {' '.join(item['tags'])}".lower()
                if search_lower not in searchable:
                    continue
            results.append(item)

        # Sort: items with due dates first (by due), then items without
        results.sort(key=lambda x: x["due"] or "9999-99-99")
        return results

    def check_due(self) -> Dict[str, Any]:
        """Dashboard: overdue, due soon (30 min), due today, upcoming (7 days)."""
        self._update_overdue()
        now = datetime.now(TIMEZONE)
        today_end = now.replace(hour=23, minute=59, second=59)
        week_end = now + timedelta(days=7)

        overdue = []
        due_soon = []
        due_today = []
        upcoming = []

        for item in self.items.values():
            if item["status"] in ("done", "cancelled"):
                continue
            if not item.get("due"):
                continue

            due_dt = datetime.fromisoformat(item["due"])

            if due_dt <= now:
                overdue.append(item)
            elif due_dt <= now + timedelta(minutes=30):
                due_soon.append(item)
            elif due_dt <= today_end:
                due_today.append(item)
            elif due_dt <= week_end:
                upcoming.append(item)

        for lst in (overdue, due_soon, due_today, upcoming):
            lst.sort(key=lambda x: x["due"])

        return {
            "overdue": overdue,
            "due_soon": due_soon,
            "due_today": due_today,
            "upcoming_7_days": upcoming,
            "checked_at": now.isoformat(),
        }

    def dashboard(self) -> Dict[str, Any]:
        """Full workflow dashboard with counts by type and status."""
        self._update_overdue()

        by_type: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        by_priority: Dict[str, int] = {}
        total = 0
        active = 0

        for item in self.items.values():
            total += 1
            t = item["type"]
            s = item["status"]
            p = item["priority"]
            by_type[t] = by_type.get(t, 0) + 1
            by_status[s] = by_status.get(s, 0) + 1
            by_priority[p] = by_priority.get(p, 0) + 1
            if s not in ("done", "cancelled"):
                active += 1

        due_check = self.check_due()

        return {
            "total_items": total,
            "active_items": active,
            "by_type": by_type,
            "by_status": by_status,
            "by_priority": by_priority,
            "overdue_count": len(due_check["overdue"]),
            "due_today_count": len(due_check["due_today"]) + len(due_check["due_soon"]),
            "upcoming_7d_count": len(due_check["upcoming_7_days"]),
            "overdue_items": due_check["overdue"][:5],  # top 5 overdue
            "checked_at": due_check["checked_at"],
        }

    # ── internal helpers ─────────────────────────────────────────

    def _update_overdue(self):
        now = datetime.now(TIMEZONE)
        changed = False
        for item in self.items.values():
            if item["status"] in ("pending", "in_progress", "waiting", "snoozed") and item.get("due"):
                due_dt = datetime.fromisoformat(item["due"])
                if due_dt <= now and item["status"] != "overdue":
                    item["status"] = "overdue"
                    item["updated_at"] = now.isoformat()
                    changed = True
        if changed:
            self._save()

    def _notify(self, item: Dict[str, Any], action: str = "created"):
        """Send email notification for an item (best-effort)."""
        try:
            from email_notifier import send_email, is_configured
            if not is_configured():
                return
            type_label = ITEM_TYPES.get(item["type"], {}).get("label", item["type"])
            prefix = ""
            if item["priority"] in ("critical", "high"):
                prefix = f"[{item['priority'].upper()}] "
            subject = f"{prefix}{type_label}: {item['title']} ({action})"
            lines = [
                f"Type: {type_label}",
                f"Title: {item['title']}",
            ]
            if item.get("description"):
                lines.append(f"Description: {item['description']}")
            if item.get("due"):
                lines.append(f"Due: {item['due']}")
            lines.append(f"Priority: {item['priority']}")
            lines.append(f"Status: {item['status']}")
            if item.get("tags"):
                lines.append(f"Tags: {', '.join(item['tags'])}")
            if item.get("details"):
                for k, v in item["details"].items():
                    if v:
                        lines.append(f"{k.replace('_', ' ').title()}: {v}")
            send_email(subject, "\n".join(lines), item["priority"])
        except Exception:
            pass  # best-effort notification
