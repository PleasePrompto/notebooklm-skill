#!/usr/bin/env python3
"""
Client Onboarding Checklists
Step-by-step KYC checklists per client type: individual, corporate, trust, government, NPO.
Creates workflow items for each step and tracks completion.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE

# ── Checklists by client type ────────────────────────────────────

CHECKLISTS = {
    "individual": {
        "name": "Individual Client Onboarding",
        "steps": [
            {"title": "Collect valid passport/Emirates ID copy", "category": "identity", "priority": "critical"},
            {"title": "Collect proof of address (utility bill/bank statement, <3 months)", "category": "identity", "priority": "critical"},
            {"title": "Obtain signed KYC form", "category": "documentation", "priority": "critical"},
            {"title": "Verify source of funds documentation", "category": "aml", "priority": "critical"},
            {"title": "Verify source of wealth documentation", "category": "aml", "priority": "high"},
            {"title": "Run PEP (Politically Exposed Person) screening", "category": "screening", "priority": "critical"},
            {"title": "Run sanctions screening (UN/EU/UK/UAE/OFAC)", "category": "screening", "priority": "critical"},
            {"title": "Run adverse media screening", "category": "screening", "priority": "high"},
            {"title": "Verify against FATF high-risk country list", "category": "screening", "priority": "high"},
            {"title": "Assess and assign risk rating", "category": "risk", "priority": "critical"},
            {"title": "Obtain management approval for high-risk clients", "category": "approval", "priority": "high"},
            {"title": "Set up enhanced due diligence (EDD) if required", "category": "edd", "priority": "high"},
            {"title": "Record all data in client database", "category": "documentation", "priority": "medium"},
            {"title": "Schedule next KYC review date", "category": "review", "priority": "medium"},
            {"title": "Send client welcome pack and T&Cs", "category": "communication", "priority": "low"},
        ],
    },
    "corporate": {
        "name": "Corporate Client Onboarding",
        "steps": [
            {"title": "Collect Certificate of Incorporation / Trade License", "category": "identity", "priority": "critical"},
            {"title": "Collect Memorandum & Articles of Association", "category": "identity", "priority": "critical"},
            {"title": "Collect shareholders register / ownership structure", "category": "identity", "priority": "critical"},
            {"title": "Identify and verify Ultimate Beneficial Owners (UBOs >25%)", "category": "identity", "priority": "critical"},
            {"title": "Collect passport/ID of all directors and UBOs", "category": "identity", "priority": "critical"},
            {"title": "Collect board resolution authorizing account opening", "category": "documentation", "priority": "high"},
            {"title": "Collect proof of registered address", "category": "identity", "priority": "high"},
            {"title": "Obtain audited financial statements (last 2 years)", "category": "documentation", "priority": "high"},
            {"title": "Verify source of funds and business activities", "category": "aml", "priority": "critical"},
            {"title": "Run sanctions screening on company name", "category": "screening", "priority": "critical"},
            {"title": "Run sanctions screening on all directors and UBOs", "category": "screening", "priority": "critical"},
            {"title": "Run PEP screening on directors and UBOs", "category": "screening", "priority": "critical"},
            {"title": "Run adverse media screening on company", "category": "screening", "priority": "high"},
            {"title": "Check company against FATF high-risk jurisdictions", "category": "screening", "priority": "high"},
            {"title": "Verify company registration with official registry", "category": "verification", "priority": "high"},
            {"title": "Assess and assign corporate risk rating", "category": "risk", "priority": "critical"},
            {"title": "Obtain MLRO approval for high-risk entities", "category": "approval", "priority": "high"},
            {"title": "Set up enhanced due diligence (EDD) if required", "category": "edd", "priority": "high"},
            {"title": "Record all data in client database", "category": "documentation", "priority": "medium"},
            {"title": "Schedule next KYC review date", "category": "review", "priority": "medium"},
        ],
    },
    "trust": {
        "name": "Trust / Foundation Onboarding",
        "steps": [
            {"title": "Collect Trust Deed / Foundation Charter", "category": "identity", "priority": "critical"},
            {"title": "Identify and verify settlor(s)", "category": "identity", "priority": "critical"},
            {"title": "Identify and verify trustee(s)", "category": "identity", "priority": "critical"},
            {"title": "Identify and verify protector(s) if applicable", "category": "identity", "priority": "high"},
            {"title": "Identify beneficiaries (named or class)", "category": "identity", "priority": "critical"},
            {"title": "Collect passport/ID of settlor, trustees, protectors", "category": "identity", "priority": "critical"},
            {"title": "Verify source of trust assets/funds", "category": "aml", "priority": "critical"},
            {"title": "Collect proof of trust registration (if applicable)", "category": "documentation", "priority": "high"},
            {"title": "Run sanctions screening on all parties", "category": "screening", "priority": "critical"},
            {"title": "Run PEP screening on all parties", "category": "screening", "priority": "critical"},
            {"title": "Run adverse media screening", "category": "screening", "priority": "high"},
            {"title": "Assess purpose of trust and risk rating", "category": "risk", "priority": "critical"},
            {"title": "Obtain senior management approval", "category": "approval", "priority": "high"},
            {"title": "Set up enhanced due diligence (EDD)", "category": "edd", "priority": "high"},
            {"title": "Record all data in client database", "category": "documentation", "priority": "medium"},
            {"title": "Schedule next KYC review date", "category": "review", "priority": "medium"},
        ],
    },
    "government": {
        "name": "Government Entity Onboarding",
        "steps": [
            {"title": "Collect official establishment decree/law", "category": "identity", "priority": "critical"},
            {"title": "Collect authorization letter from authorized signatory", "category": "documentation", "priority": "critical"},
            {"title": "Verify identity of authorized representatives", "category": "identity", "priority": "critical"},
            {"title": "Verify entity against sanctions lists", "category": "screening", "priority": "critical"},
            {"title": "Screen authorized representatives (PEP/sanctions)", "category": "screening", "priority": "critical"},
            {"title": "Assess risk rating (simplified due diligence may apply)", "category": "risk", "priority": "high"},
            {"title": "Record all data in client database", "category": "documentation", "priority": "medium"},
            {"title": "Schedule review date", "category": "review", "priority": "medium"},
        ],
    },
    "npo": {
        "name": "Non-Profit Organization Onboarding",
        "steps": [
            {"title": "Collect NPO registration certificate", "category": "identity", "priority": "critical"},
            {"title": "Collect constitution / bylaws", "category": "identity", "priority": "critical"},
            {"title": "Identify board members and key officers", "category": "identity", "priority": "critical"},
            {"title": "Collect passport/ID of board members", "category": "identity", "priority": "critical"},
            {"title": "Verify source of funding and donor information", "category": "aml", "priority": "critical"},
            {"title": "Assess geographic areas of operation", "category": "risk", "priority": "critical"},
            {"title": "Run sanctions screening on NPO and board members", "category": "screening", "priority": "critical"},
            {"title": "Run PEP screening on board members", "category": "screening", "priority": "critical"},
            {"title": "Run adverse media screening", "category": "screening", "priority": "high"},
            {"title": "Assess risk (NPOs are inherently higher risk per FATF)", "category": "risk", "priority": "critical"},
            {"title": "Obtain MLRO and senior management approval", "category": "approval", "priority": "critical"},
            {"title": "Set up enhanced monitoring", "category": "edd", "priority": "high"},
            {"title": "Record all data in client database", "category": "documentation", "priority": "medium"},
            {"title": "Schedule next KYC review (recommend 6 months)", "category": "review", "priority": "medium"},
        ],
    },
}


def get_checklist(client_type: str) -> Dict[str, Any]:
    """Get the onboarding checklist for a client type."""
    ct = client_type.lower()
    if ct not in CHECKLISTS:
        raise ValueError(f"Unknown client type: {ct}. Choose from: {list(CHECKLISTS.keys())}")
    return CHECKLISTS[ct]


def create_onboarding(
    client_name: str,
    client_type: str = "individual",
    client_id: Optional[str] = None,
    due_days: int = 14,
) -> Dict[str, Any]:
    """Create a full onboarding workflow for a client.

    Creates workflow items for each checklist step.
    Returns the created items.
    """
    from workflow_manager import WorkflowManager

    checklist = get_checklist(client_type)
    wf = WorkflowManager()
    now = datetime.now(TIMEZONE)
    due = (now + timedelta(days=due_days)).isoformat()

    # Create parent project
    project = wf.create(
        item_type="project",
        title=f"Onboarding: {client_name} ({checklist['name']})",
        due=due,
        description=f"KYC onboarding for {client_name}. Client type: {client_type}",
        priority="high",
        tags=["onboarding", "kyc", client_type],
        details={"client_name": client_name, "client_id": client_id or "", "client_type": client_type},
    )

    # Create task for each step
    items = []
    for i, step in enumerate(checklist["steps"], 1):
        item = wf.create(
            item_type="task",
            title=f"[{client_name}] {step['title']}",
            due=due,
            priority=step["priority"],
            tags=["onboarding", step["category"], client_type],
            details={
                "project_id": project["id"],
                "client_name": client_name,
                "client_id": client_id or "",
                "step_number": i,
                "category": step["category"],
            },
        )
        items.append(item)

    return {
        "project": project,
        "items": items,
        "total_steps": len(items),
        "client_name": client_name,
        "client_type": client_type,
        "due_date": due,
    }


def get_onboarding_status(client_name: str) -> Dict[str, Any]:
    """Check onboarding progress for a client."""
    from workflow_manager import WorkflowManager
    wf = WorkflowManager()
    items = wf.list_items(tag="onboarding", search=client_name, include_done=True)

    total = len(items)
    done = sum(1 for i in items if i["status"] == "done")
    pending = sum(1 for i in items if i["status"] in ("pending", "in_progress"))
    overdue = sum(1 for i in items if i["status"] == "overdue")

    return {
        "client_name": client_name,
        "total_steps": total,
        "completed": done,
        "pending": pending,
        "overdue": overdue,
        "progress_pct": round(done / total * 100, 1) if total > 0 else 0,
        "items": items,
    }
