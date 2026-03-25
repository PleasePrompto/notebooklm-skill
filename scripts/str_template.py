#!/usr/bin/env python3
"""
STR/SAR Template Generator
Pre-fills Suspicious Transaction Report templates for UAE goAML submission.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
STR_DIR = DATA_DIR / "str_reports"

# Suspicious activity indicators (CBUAE categories)
INDICATORS = {
    "structuring": "Structuring transactions to avoid reporting thresholds",
    "unusual_cash": "Unusually large cash transactions",
    "rapid_movement": "Rapid movement of funds through accounts",
    "shell_company": "Transactions involving shell companies or nominees",
    "no_economic": "No apparent economic or lawful purpose",
    "sanctions_link": "Connection to sanctioned entities or jurisdictions",
    "pep_unusual": "Unusual activity by a PEP or associate",
    "third_party": "Third party transactions without clear reason",
    "high_risk_country": "Transactions involving FATF high-risk jurisdictions",
    "inconsistent": "Activity inconsistent with client profile or expected behavior",
    "layering": "Complex layering of transactions to obscure origin",
    "trade_based": "Suspected trade-based money laundering",
    "terrorist_financing": "Suspected terrorist financing activity",
    "fraud": "Suspected fraud or forgery",
    "tax_evasion": "Suspected tax evasion",
    "corruption": "Suspected corruption or bribery",
    "identity_fraud": "False or stolen identity documents",
    "unusual_pattern": "Unusual transaction patterns detected by monitoring",
}

# Transaction types
TRANSACTION_TYPES = [
    "Cash deposit", "Cash withdrawal", "Wire transfer (incoming)",
    "Wire transfer (outgoing)", "Check deposit", "Check issuance",
    "Currency exchange", "Trade finance", "Investment",
    "Loan/credit", "Insurance", "Real estate",
    "Virtual asset", "Cross-border transfer", "Internal transfer",
]


def generate_str(
    client_name: str,
    client_id: str = "",
    transaction_date: str = "",
    transaction_amount: str = "",
    transaction_currency: str = "AED",
    transaction_type: str = "",
    indicators: str = "",
    narrative: str = "",
    reporting_entity: str = "Finegold LLC",
    reporting_officer: str = "",
    additional_parties: str = "",
) -> Dict[str, Any]:
    """Generate a pre-filled STR/SAR template.

    Returns structured data ready for goAML submission.
    """
    STR_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TIMEZONE)
    str_id = f"STR-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"

    # Parse indicators
    indicator_list = []
    if indicators:
        for ind in indicators.split(","):
            ind = ind.strip().lower().replace(" ", "_")
            if ind in INDICATORS:
                indicator_list.append({"code": ind, "description": INDICATORS[ind]})
            else:
                indicator_list.append({"code": "other", "description": ind})

    # Get client data if available
    client_data = {}
    if client_id:
        try:
            from client_database import ClientDatabase
            db = ClientDatabase()
            client = db.get_client(client_id)
            if client:
                client_data = {
                    "full_name": client["name"],
                    "client_type": client["client_type"],
                    "nationality": client.get("nationality", ""),
                    "id_number": client.get("id_number", ""),
                    "risk_rating": client["risk_rating"],
                }
        except Exception:
            pass

    if not client_data:
        client_data = {"full_name": client_name}

    str_report = {
        "str_id": str_id,
        "status": "draft",
        "created_at": now.isoformat(),

        "reporting_entity": {
            "name": reporting_entity,
            "reporting_officer": reporting_officer,
            "report_date": now.strftime("%Y-%m-%d"),
            "report_type": "STR",
        },

        "subject": {
            **client_data,
            "client_id": client_id,
        },

        "additional_parties": additional_parties,

        "transaction": {
            "date": transaction_date or now.strftime("%Y-%m-%d"),
            "amount": transaction_amount,
            "currency": transaction_currency,
            "type": transaction_type,
        },

        "suspicion": {
            "indicators": indicator_list,
            "narrative": narrative,
            "date_of_suspicion": now.strftime("%Y-%m-%d"),
        },

        "goaml_fields": {
            "report_code": "STR",
            "submission_date": "",
            "goaml_reference": "",
            "priority": "High" if any(i["code"] in ("sanctions_link", "terrorist_financing") for i in indicator_list) else "Normal",
        },

        "notes": "This is a draft STR. Review and submit via goAML portal within 24 hours of suspicion.",
    }

    # Save
    save_path = STR_DIR / f"{str_id}.json"
    with open(save_path, "w") as f:
        json.dump(str_report, f, indent=2)

    # Generate readable text version
    text = _render_str_text(str_report)
    text_path = STR_DIR / f"{str_id}.txt"
    with open(text_path, "w") as f:
        f.write(text)

    # Log to audit trail
    try:
        from audit_trail import log_action
        log_action(f"STR generated: {str_id} for {client_name}", "screening",
                   client_id=client_id, details={"str_id": str_id})
    except Exception:
        pass

    return {
        "str_id": str_id,
        "json_path": str(save_path),
        "text_path": str(text_path),
        "report": str_report,
    }


def _render_str_text(r: Dict[str, Any]) -> str:
    s = r["subject"]
    t = r["transaction"]
    sp = r["suspicion"]
    re_ = r["reporting_entity"]

    lines = [
        "=" * 60,
        "SUSPICIOUS TRANSACTION REPORT (STR)",
        f"Report ID: {r['str_id']}",
        f"Status: {r['status'].upper()}",
        "=" * 60,
        "",
        "REPORTING ENTITY",
        "-" * 40,
        f"  Entity: {re_['name']}",
        f"  Officer: {re_['reporting_officer']}",
        f"  Date: {re_['report_date']}",
        "",
        "SUBJECT OF REPORT",
        "-" * 40,
        f"  Name: {s.get('full_name', '')}",
        f"  Type: {s.get('client_type', '')}",
        f"  Nationality: {s.get('nationality', '')}",
        f"  ID Number: {s.get('id_number', '')}",
        f"  Risk Rating: {s.get('risk_rating', '')}",
        f"  Client ID: {s.get('client_id', '')}",
        "",
    ]

    if r.get("additional_parties"):
        lines.extend(["ADDITIONAL PARTIES", "-" * 40, f"  {r['additional_parties']}", ""])

    lines.extend([
        "TRANSACTION DETAILS",
        "-" * 40,
        f"  Date: {t['date']}",
        f"  Amount: {t['amount']} {t['currency']}",
        f"  Type: {t['type']}",
        "",
        "REASON FOR SUSPICION",
        "-" * 40,
        f"  Date of Suspicion: {sp['date_of_suspicion']}",
        "  Indicators:",
    ])

    for ind in sp["indicators"]:
        lines.append(f"    - [{ind['code']}] {ind['description']}")

    lines.extend([
        "",
        "  Narrative:",
        f"    {sp['narrative']}",
        "",
        "goAML SUBMISSION",
        "-" * 40,
        f"  Report Code: {r['goaml_fields']['report_code']}",
        f"  Priority: {r['goaml_fields']['priority']}",
        f"  Submission Date: {r['goaml_fields']['submission_date'] or 'PENDING'}",
        f"  goAML Reference: {r['goaml_fields']['goaml_reference'] or 'PENDING'}",
        "",
        "IMPORTANT: Submit this report via goAML within 24 hours of suspicion.",
        "=" * 60,
    ])

    return "\n".join(lines)


def list_str_reports() -> list:
    """List all generated STR reports."""
    STR_DIR.mkdir(parents=True, exist_ok=True)
    reports = []
    for f in sorted(STR_DIR.glob("STR-*.json"), reverse=True):
        try:
            with open(f, "r") as fp:
                data = json.load(fp)
            reports.append({
                "str_id": data["str_id"],
                "client": data["subject"].get("full_name", ""),
                "status": data["status"],
                "created_at": data["created_at"],
                "path": str(f),
            })
        except Exception:
            pass
    return reports


def get_indicators() -> Dict[str, str]:
    """Return all available suspicion indicators."""
    return INDICATORS
