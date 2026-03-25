#!/usr/bin/env python3
"""
PDF Compliance Report Generator
Generates branded PDF reports for management and auditors.
Uses only Python stdlib (no external PDF libraries required).
Outputs HTML-to-PDF via browser print, or standalone HTML with print CSS.
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
REPORTS_DIR = DATA_DIR / "reports"


def generate_pdf_report(
    report_type: str = "full",
    company_name: str = "Finegold LLC",
    logo_text: str = "FINEGOLD",
    prepared_by: str = "Compliance Department",
    period: str = "",
) -> Dict[str, Any]:
    """Generate a branded compliance report as print-ready HTML.

    report_type: 'full', 'sanctions', 'kyc', 'aml', 'executive'
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TIMEZONE)
    report_id = now.strftime("%Y%m%d_%H%M%S")
    if not period:
        period = now.strftime("%B %Y")

    # Gather data
    sections = _gather_data(report_type)

    html = _render_pdf_html(
        report_type=report_type,
        company_name=company_name,
        logo_text=logo_text,
        prepared_by=prepared_by,
        period=period,
        generated_at=now,
        sections=sections,
    )

    html_path = REPORTS_DIR / f"compliance_report_{report_type}_{report_id}.html"
    with open(html_path, "w") as f:
        f.write(html)

    return {
        "report_id": report_id,
        "type": report_type,
        "html_path": str(html_path),
        "generated_at": now.isoformat(),
        "instructions": "Open the HTML file in a browser and press Ctrl+P / Cmd+P to save as PDF.",
    }


def _gather_data(report_type: str) -> Dict[str, Any]:
    sections = {}

    try:
        from workflow_manager import WorkflowManager
        wf = WorkflowManager()
        sections["workflow"] = wf.dashboard()
        sections["workflow_due"] = wf.check_due()
    except Exception:
        sections["workflow"] = {}

    try:
        from client_database import ClientDatabase
        db = ClientDatabase()
        sections["clients"] = db.get_stats()
        sections["client_reviews"] = db.get_review_due()
        sections["client_list"] = list(db.clients.values())
    except Exception:
        sections["clients"] = {}

    try:
        from sanctions_checker import get_list_status
        sections["sanctions"] = get_list_status()
    except Exception:
        sections["sanctions"] = {}

    try:
        from audit_trail import audit_stats, query_audit
        sections["audit"] = audit_stats()
        sections["recent_audit"] = query_audit(limit=20)
    except Exception:
        sections["audit"] = {}

    try:
        from risk_countries import get_fatf_summary
        sections["risk_countries"] = get_fatf_summary()
    except Exception:
        sections["risk_countries"] = {}

    return sections


def _render_pdf_html(report_type, company_name, logo_text, prepared_by, period, generated_at, sections):
    now = generated_at
    s = sections

    # Title based on type
    titles = {
        "full": "Comprehensive Compliance Report",
        "sanctions": "Sanctions Screening Report",
        "kyc": "KYC/AML Compliance Report",
        "aml": "Anti-Money Laundering Report",
        "executive": "Executive Summary - Compliance",
    }
    title = titles.get(report_type, "Compliance Report")

    wf = s.get("workflow", {})
    cl = s.get("clients", {})
    sa = s.get("sanctions", {})
    au = s.get("audit", {})
    reviews = s.get("client_reviews", {})
    clients = s.get("client_list", [])
    risk = s.get("risk_countries", {})

    # Build client table rows
    client_rows = ""
    for c in clients[:50]:
        risk_class = "risk-high" if c.get("risk_rating") in ("high", "critical", "pep", "sanctioned") else ""
        client_rows += f"""<tr class="{risk_class}">
            <td>{c.get('name','')}</td><td>{c.get('client_type','')}</td>
            <td>{c.get('risk_rating','')}</td><td>{c.get('kyc_status','')}</td>
            <td>{c.get('nationality','')}</td><td>{(c.get('review_date','') or '')[:10]}</td>
        </tr>"""

    # Sanctions status rows
    sanc_rows = ""
    for key, info in sa.items():
        if isinstance(info, dict):
            status = f"{info.get('entries',0)} entries" if info.get("downloaded") else "Not downloaded"
            updated = info.get("updated_at", "")[:16] if info.get("downloaded") else "-"
            sanc_rows += f"<tr><td>{key}</td><td>{info.get('name','')}</td><td>{status}</td><td>{updated}</td></tr>"

    # Audit rows
    audit_rows = ""
    for e in s.get("recent_audit", [])[:15]:
        audit_rows += f"<tr><td>{e.get('timestamp','')[:19]}</td><td>{e.get('category','')}</td><td>{e.get('action','')}</td><td>{e.get('result','')}</td></tr>"

    # Overdue items
    overdue_rows = ""
    for item in (s.get("workflow_due", {}).get("overdue", []))[:10]:
        overdue_rows += f"<tr class='risk-high'><td>{item.get('type_label','')}</td><td>{item.get('title','')}</td><td>{(item.get('due',''))[:16]}</td><td>{item.get('priority','')}</td></tr>"

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>{title} - {company_name}</title>
<style>
@page {{ size: A4; margin: 20mm; }}
@media print {{
    .no-print {{ display: none; }}
    body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; font-size: 11px; line-height: 1.5; color: #1a1a2e; background: #f0f0f0; }}
.page {{ max-width: 210mm; margin: 20px auto; background: white; padding: 30px 40px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
.header {{ border-bottom: 3px solid #0d1b2a; padding-bottom: 15px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
.logo {{ font-size: 28px; font-weight: 800; color: #0d1b2a; letter-spacing: 3px; }}
.logo-sub {{ font-size: 10px; color: #666; letter-spacing: 1px; }}
.header-right {{ text-align: right; font-size: 10px; color: #666; }}
.title {{ font-size: 20px; color: #0d1b2a; font-weight: 700; margin: 15px 0 5px; }}
.subtitle {{ font-size: 12px; color: #666; margin-bottom: 20px; }}
h2 {{ font-size: 14px; color: #0d1b2a; margin: 20px 0 10px; padding: 6px 12px; background: #e8eaf6; border-left: 4px solid #1a237e; }}
table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 10px; }}
th {{ background: #1a237e; color: white; padding: 6px 8px; text-align: left; font-weight: 600; }}
td {{ padding: 5px 8px; border-bottom: 1px solid #e0e0e0; }}
tr:nth-child(even) {{ background: #f8f9fa; }}
.risk-high {{ background: #ffebee !important; }}
.risk-high td {{ color: #b71c1c; font-weight: 600; }}
.stats {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 10px 0; }}
.stat-box {{ background: #f5f5f5; border: 1px solid #e0e0e0; padding: 10px 15px; border-radius: 4px; text-align: center; min-width: 100px; }}
.stat-box .number {{ font-size: 22px; font-weight: 700; color: #1a237e; }}
.stat-box .label {{ font-size: 9px; color: #666; text-transform: uppercase; }}
.stat-box.critical {{ border-color: #b71c1c; background: #ffebee; }}
.stat-box.critical .number {{ color: #b71c1c; }}
.stat-box.ok {{ border-color: #2e7d32; background: #e8f5e9; }}
.stat-box.ok .number {{ color: #2e7d32; }}
.footer {{ margin-top: 30px; padding-top: 15px; border-top: 2px solid #0d1b2a; font-size: 9px; color: #666; display: flex; justify-content: space-between; }}
.confidential {{ color: #b71c1c; font-weight: 700; font-size: 10px; }}
.print-btn {{ position: fixed; top: 10px; right: 10px; background: #1a237e; color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px; font-size: 14px; z-index: 1000; }}
</style>
</head><body>
<button class="print-btn no-print" onclick="window.print()">Save as PDF</button>
<div class="page">
<div class="header">
    <div>
        <div class="logo">{logo_text}</div>
        <div class="logo-sub">{company_name}</div>
    </div>
    <div class="header-right">
        <div class="confidential">CONFIDENTIAL</div>
        <div>Report ID: {now.strftime('%Y%m%d_%H%M%S')}</div>
        <div>Generated: {now.strftime('%d %B %Y, %H:%M')} GST</div>
        <div>Prepared by: {prepared_by}</div>
    </div>
</div>

<div class="title">{title}</div>
<div class="subtitle">Period: {period} | Classification: Confidential</div>

<h2>1. Compliance Overview</h2>
<div class="stats">
    <div class="stat-box"><div class="number">{wf.get('total_items',0)}</div><div class="label">Total Items</div></div>
    <div class="stat-box"><div class="number">{wf.get('active_items',0)}</div><div class="label">Active</div></div>
    <div class="stat-box {'critical' if wf.get('overdue_count',0) > 0 else 'ok'}"><div class="number">{wf.get('overdue_count',0)}</div><div class="label">Overdue</div></div>
    <div class="stat-box"><div class="number">{wf.get('due_today_count',0)}</div><div class="label">Due Today</div></div>
    <div class="stat-box"><div class="number">{cl.get('total_clients',0)}</div><div class="label">Clients</div></div>
    <div class="stat-box"><div class="number">{cl.get('reviews_overdue',0)}</div><div class="label">Reviews Due</div></div>
    <div class="stat-box"><div class="number">{au.get('total_entries',0)}</div><div class="label">Audit Entries</div></div>
</div>

{"<h2>2. Overdue Items</h2><table><tr><th>Type</th><th>Title</th><th>Due</th><th>Priority</th></tr>" + overdue_rows + "</table>" if overdue_rows else ""}

<h2>{'3' if overdue_rows else '2'}. Client Database</h2>
<div class="stats">
    <div class="stat-box"><div class="number">{cl.get('total_clients',0)}</div><div class="label">Total Clients</div></div>
    {"".join(f'<div class="stat-box {"critical" if k in ("high","critical","pep","sanctioned") else ""}"><div class="number">{v}</div><div class="label">{k}</div></div>' for k,v in cl.get("by_risk_rating",{}).items())}
</div>
{f'<table><tr><th>Name</th><th>Type</th><th>Risk</th><th>KYC Status</th><th>Nationality</th><th>Review Date</th></tr>{client_rows}</table>' if client_rows else ''}

<h2>Sanctions Lists Status</h2>
{f'<table><tr><th>Source</th><th>Name</th><th>Status</th><th>Last Updated</th></tr>{sanc_rows}</table>' if sanc_rows else '<p>No sanctions data.</p>'}

<h2>Audit Trail (Recent)</h2>
{f'<table><tr><th>Timestamp</th><th>Category</th><th>Action</th><th>Result</th></tr>{audit_rows}</table>' if audit_rows else '<p>No audit entries.</p>'}

<div class="footer">
    <div>{company_name} - {prepared_by}</div>
    <div class="confidential">CONFIDENTIAL - FOR INTERNAL USE ONLY</div>
    <div>Page 1 | {now.strftime('%d/%m/%Y')}</div>
</div>
</div>
</body></html>"""
