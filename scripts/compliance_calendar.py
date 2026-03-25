#!/usr/bin/env python3
"""
UAE Compliance Calendar
Pre-loaded CBUAE reporting deadlines and regulatory dates.
Automatically creates workflow reminders for upcoming deadlines.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE

# ── Pre-loaded CBUAE & UAE regulatory deadlines ──────────────────

ANNUAL_DEADLINES = [
    {
        "title": "Annual Compliance Report submission to CBUAE",
        "month": 3, "day": 31,
        "authority": "CBUAE",
        "description": "Submit annual compliance report covering AML/CFT activities",
        "priority": "critical",
        "tags": ["cbuae", "annual", "report"],
    },
    {
        "title": "Annual AML/CFT Risk Assessment update",
        "month": 1, "day": 31,
        "authority": "CBUAE",
        "description": "Update enterprise-wide ML/TF risk assessment",
        "priority": "critical",
        "tags": ["cbuae", "risk-assessment", "annual"],
    },
    {
        "title": "Annual Independent AML/CFT Audit",
        "month": 6, "day": 30,
        "authority": "CBUAE",
        "description": "Complete independent audit of AML/CFT program",
        "priority": "critical",
        "tags": ["cbuae", "audit", "annual"],
    },
    {
        "title": "Compliance Officer Registration renewal (CBUAE)",
        "month": 12, "day": 31,
        "authority": "CBUAE",
        "description": "Renew Compliance Officer registration with CBUAE",
        "priority": "high",
        "tags": ["cbuae", "registration", "annual"],
    },
    {
        "title": "goAML System registration verification",
        "month": 1, "day": 15,
        "authority": "FIU UAE",
        "description": "Verify goAML portal access and update entity information",
        "priority": "high",
        "tags": ["goaml", "fiu", "annual"],
    },
    {
        "title": "Annual staff AML/CFT training completion",
        "month": 12, "day": 31,
        "authority": "CBUAE",
        "description": "All staff must complete annual AML/CFT awareness training",
        "priority": "high",
        "tags": ["training", "annual", "cbuae"],
    },
    {
        "title": "UAE Ultimate Beneficial Ownership (UBO) Register update",
        "month": 6, "day": 30,
        "authority": "Ministry of Economy",
        "description": "Update UBO information in the national register",
        "priority": "high",
        "tags": ["ubo", "moe", "annual"],
    },
    {
        "title": "Trade License renewal compliance review",
        "month": 12, "day": 31,
        "authority": "DED / Free Zone",
        "description": "Review compliance obligations as part of trade license renewal",
        "priority": "medium",
        "tags": ["license", "annual"],
    },
]

QUARTERLY_DEADLINES = [
    {
        "title": "Quarterly STR/SAR statistics report to MLRO",
        "months": [3, 6, 9, 12], "day": 15,
        "authority": "Internal",
        "description": "Compile quarterly suspicious transaction reporting statistics",
        "priority": "high",
        "tags": ["str", "quarterly", "report"],
    },
    {
        "title": "Quarterly sanctions list update review",
        "months": [3, 6, 9, 12], "day": 10,
        "authority": "CBUAE",
        "description": "Review and update all sanctions lists, rescreeen high-risk clients",
        "priority": "critical",
        "tags": ["sanctions", "quarterly"],
    },
    {
        "title": "Quarterly Board/Management compliance report",
        "months": [3, 6, 9, 12], "day": 20,
        "authority": "Internal / Board",
        "description": "Present compliance status, risks, and STR activity to board/management",
        "priority": "high",
        "tags": ["board", "quarterly", "report"],
    },
    {
        "title": "Quarterly KYC review for high-risk clients",
        "months": [3, 6, 9, 12], "day": 30,
        "authority": "CBUAE",
        "description": "Conduct enhanced review of all high-risk and PEP clients",
        "priority": "critical",
        "tags": ["kyc", "high-risk", "quarterly"],
    },
]

MONTHLY_DEADLINES = [
    {
        "title": "Monthly transaction monitoring review",
        "day": 5,
        "authority": "Internal",
        "description": "Review automated transaction monitoring alerts and dispositions",
        "priority": "high",
        "tags": ["monitoring", "monthly"],
    },
    {
        "title": "Monthly sanctions screening of existing clients",
        "day": 1,
        "authority": "CBUAE",
        "description": "Re-screen all existing clients against updated sanctions lists",
        "priority": "critical",
        "tags": ["sanctions", "screening", "monthly"],
    },
    {
        "title": "Monthly goAML portal check - pending STR cases",
        "day": 10,
        "authority": "FIU UAE",
        "description": "Check goAML portal for FIU feedback on submitted STRs",
        "priority": "high",
        "tags": ["goaml", "str", "monthly"],
    },
]

ONGOING_OBLIGATIONS = [
    {"title": "File STR/SAR within 24 hours of suspicion", "authority": "CBUAE / FIU", "priority": "critical"},
    {"title": "Immediately freeze assets on sanctions match", "authority": "CBUAE", "priority": "critical"},
    {"title": "Report sanctions matches to CBUAE within 24 hours", "authority": "CBUAE", "priority": "critical"},
    {"title": "Maintain records for minimum 5 years after relationship ends", "authority": "CBUAE", "priority": "high"},
    {"title": "Screen all new clients before onboarding", "authority": "CBUAE", "priority": "critical"},
    {"title": "Apply EDD for high-risk clients and PEPs", "authority": "CBUAE", "priority": "critical"},
    {"title": "Report cash transactions above AED 55,000 (or equivalent)", "authority": "CBUAE", "priority": "high"},
]


def get_upcoming_deadlines(days: int = 90) -> List[Dict[str, Any]]:
    """Get all regulatory deadlines within the next N days."""
    now = datetime.now(TIMEZONE)
    cutoff = now + timedelta(days=days)
    year = now.year
    upcoming = []

    # Check annual deadlines
    for d in ANNUAL_DEADLINES:
        deadline = datetime(year, d["month"], d["day"], 17, 0, tzinfo=TIMEZONE)
        if deadline < now:
            deadline = datetime(year + 1, d["month"], d["day"], 17, 0, tzinfo=TIMEZONE)
        if deadline <= cutoff:
            upcoming.append({
                **d,
                "due": deadline.isoformat(),
                "days_until": (deadline - now).days,
                "recurrence": "annual",
            })

    # Check quarterly deadlines
    for d in QUARTERLY_DEADLINES:
        for month in d["months"]:
            deadline = datetime(year, month, d["day"], 17, 0, tzinfo=TIMEZONE)
            if deadline < now:
                # Try next year for this quarter
                if month <= 3:
                    deadline = datetime(year + 1, month, d["day"], 17, 0, tzinfo=TIMEZONE)
                else:
                    continue
            if now <= deadline <= cutoff:
                upcoming.append({
                    "title": d["title"],
                    "authority": d["authority"],
                    "description": d["description"],
                    "priority": d["priority"],
                    "tags": d["tags"],
                    "due": deadline.isoformat(),
                    "days_until": (deadline - now).days,
                    "recurrence": "quarterly",
                })

    # Check monthly deadlines
    for d in MONTHLY_DEADLINES:
        # This month and next month
        for m_offset in range(0, 4):
            month = now.month + m_offset
            yr = year
            if month > 12:
                month -= 12
                yr += 1
            try:
                deadline = datetime(yr, month, d["day"], 17, 0, tzinfo=TIMEZONE)
            except ValueError:
                continue
            if now <= deadline <= cutoff:
                upcoming.append({
                    "title": d["title"],
                    "authority": d["authority"],
                    "description": d["description"],
                    "priority": d["priority"],
                    "tags": d["tags"],
                    "due": deadline.isoformat(),
                    "days_until": (deadline - now).days,
                    "recurrence": "monthly",
                })

    upcoming.sort(key=lambda x: x["due"])
    return upcoming


def load_calendar_to_workflow() -> Dict[str, Any]:
    """Create workflow items for all upcoming regulatory deadlines."""
    from workflow_manager import WorkflowManager
    wf = WorkflowManager()

    deadlines = get_upcoming_deadlines(days=90)
    created = []

    for d in deadlines:
        # Check if already exists
        existing = wf.list_items(search=d["title"][:40])
        if existing:
            continue

        item = wf.create(
            item_type="reminder",
            title=d["title"],
            due=d["due"],
            description=f"{d['description']} (Authority: {d['authority']})",
            priority=d["priority"],
            tags=d.get("tags", []) + ["regulatory", "calendar"],
            details={"authority": d["authority"], "recurrence": d["recurrence"]},
        )
        created.append(item)

    return {
        "total_deadlines": len(deadlines),
        "new_items_created": len(created),
        "items": created,
    }


def get_ongoing_obligations() -> List[Dict[str, Any]]:
    """Return list of ongoing compliance obligations."""
    return ONGOING_OBLIGATIONS


def get_full_calendar() -> Dict[str, Any]:
    """Return complete calendar data."""
    return {
        "annual": ANNUAL_DEADLINES,
        "quarterly": QUARTERLY_DEADLINES,
        "monthly": MONTHLY_DEADLINES,
        "ongoing": ONGOING_OBLIGATIONS,
        "upcoming_90_days": get_upcoming_deadlines(90),
    }
