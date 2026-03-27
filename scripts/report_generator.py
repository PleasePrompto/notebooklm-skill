#!/usr/bin/env python3
"""
Dashboard Report Generator
Generates compliance dashboard reports in text, JSON, and HTML formats.
Aggregates data from workflow, clients, sanctions, prices, and rates.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
REPORTS_DIR = DATA_DIR / "reports"


def generate_compliance_report(format: str = "text") -> Dict[str, Any]:
    """Generate a full compliance dashboard report.

    Aggregates:
      - Workflow items status
      - Client database stats
      - Sanctions screening status
      - Price & rate snapshots
      - Audit trail summary
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TIMEZONE)
    report_id = now.strftime("%Y%m%d_%H%M%S")

    sections = {}

    # 1. Workflow summary
    try:
        from workflow_manager import WorkflowManager
        wf = WorkflowManager()
        dash = wf.dashboard()
        due = wf.check_due()
        sections["workflow"] = {
            "total_items": dash["total_items"],
            "active_items": dash["active_items"],
            "by_type": dash["by_type"],
            "by_priority": dash["by_priority"],
            "overdue": len(due["overdue"]),
            "due_today": len(due["due_today"]) + len(due["due_soon"]),
            "upcoming_7d": len(due["upcoming_7_days"]),
            "overdue_items": [{"title": i["title"], "type": i["type_label"], "due": i["due"][:16]} for i in due["overdue"][:10]],
        }
    except Exception as e:
        sections["workflow"] = {"error": str(e)}

    # 2. Client database
    try:
        from client_database import ClientDatabase
        db = ClientDatabase()
        stats = db.get_stats()
        reviews = db.get_review_due()
        sections["clients"] = {
            **stats,
            "review_overdue_names": [c["name"] for c in reviews["overdue"][:10]],
            "review_upcoming_names": [c["name"] for c in reviews["upcoming"][:10]],
        }
    except Exception as e:
        sections["clients"] = {"error": str(e)}

    # 3. Sanctions lists status
    try:
        from sanctions_checker import get_list_status
        sections["sanctions"] = get_list_status()
    except Exception as e:
        sections["sanctions"] = {"error": str(e)}

    # 4. Latest prices
    try:
        from price_tracker import PRICES_FILE
        if PRICES_FILE.exists():
            with open(PRICES_FILE, "r") as f:
                pdata = json.load(f)
            history = pdata.get("history", [])
            if history:
                latest = history[-1]
                sections["prices"] = {
                    "XAU": latest.get("XAU"),
                    "XAG": latest.get("XAG"),
                    "timestamp": latest.get("timestamp"),
                }
            else:
                sections["prices"] = {"note": "No price data yet. Run check_prices."}
        else:
            sections["prices"] = {"note": "No price data yet."}
    except Exception as e:
        sections["prices"] = {"error": str(e)}

    # 5. Latest exchange rates
    try:
        from currency_tracker import RATES_FILE
        if RATES_FILE.exists():
            with open(RATES_FILE, "r") as f:
                rdata = json.load(f)
            history = rdata.get("history", [])
            if history:
                latest = history[-1]
                sections["exchange_rates"] = {
                    "base": latest.get("base"),
                    "rates": latest.get("rates"),
                    "timestamp": latest.get("timestamp"),
                }
            else:
                sections["exchange_rates"] = {"note": "No rate data yet. Run check_rates."}
        else:
            sections["exchange_rates"] = {"note": "No rate data yet."}
    except Exception as e:
        sections["exchange_rates"] = {"error": str(e)}

    # 6. Audit trail summary
    try:
        from audit_trail import audit_stats
        sections["audit_trail"] = audit_stats()
    except Exception as e:
        sections["audit_trail"] = {"error": str(e)}

    report = {
        "report_id": report_id,
        "title": f"Compliance Dashboard Report - {now.strftime('%B %d, %Y')}",
        "generated_at": now.isoformat(),
        "timezone": "Asia/Dubai (GST, UTC+4)",
        "sections": sections,
    }

    # Save JSON
    json_path = REPORTS_DIR / f"report_{report_id}.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    if format == "json":
        return report

    # Generate text format
    if format in ("text", "both"):
        text = _render_text(report)
        text_path = REPORTS_DIR / f"report_{report_id}.txt"
        with open(text_path, "w") as f:
            f.write(text)
        report["text"] = text
        report["text_path"] = str(text_path)

    # Generate HTML format
    if format in ("html", "both"):
        html = _render_html(report)
        html_path = REPORTS_DIR / f"report_{report_id}.html"
        with open(html_path, "w") as f:
            f.write(html)
        report["html_path"] = str(html_path)

    report["json_path"] = str(json_path)
    return report


def _render_text(report: Dict[str, Any]) -> str:
    s = report["sections"]
    lines = [
        "=" * 60,
        report["title"],
        f"Generated: {report['generated_at'][:19]} ({report['timezone']})",
        "=" * 60,
        "",
    ]

    # Workflow
    wf = s.get("workflow", {})
    if "error" not in wf:
        lines.extend([
            "WORKFLOW STATUS",
            "-" * 40,
            f"  Active items: {wf.get('active_items', 0)} / {wf.get('total_items', 0)}",
            f"  Overdue: {wf.get('overdue', 0)}",
            f"  Due today: {wf.get('due_today', 0)}",
            f"  Upcoming 7 days: {wf.get('upcoming_7d', 0)}",
        ])
        if wf.get("overdue_items"):
            lines.append("  Overdue items:")
            for item in wf["overdue_items"]:
                lines.append(f"    - [{item['type']}] {item['title']} (due {item['due']})")
        lines.append("")

    # Clients
    cl = s.get("clients", {})
    if "error" not in cl:
        lines.extend([
            "CLIENT DATABASE",
            "-" * 40,
            f"  Total clients: {cl.get('total_clients', 0)}",
            f"  By risk: {json.dumps(cl.get('by_risk_rating', {}))}",
            f"  By KYC status: {json.dumps(cl.get('by_kyc_status', {}))}",
            f"  Reviews overdue: {cl.get('reviews_overdue', 0)}",
            f"  Reviews upcoming: {cl.get('reviews_upcoming', 0)}",
        ])
        if cl.get("review_overdue_names"):
            lines.append(f"  Overdue reviews: {', '.join(cl['review_overdue_names'])}")
        lines.append("")

    # Sanctions
    sa = s.get("sanctions", {})
    if "error" not in sa:
        lines.extend(["SANCTIONS LISTS", "-" * 40])
        for key, info in sa.items():
            if isinstance(info, dict):
                status = "Downloaded" if info.get("downloaded") else "Not downloaded"
                entries = f" ({info.get('entries', 0)} entries)" if info.get("downloaded") else ""
                lines.append(f"  {key}: {status}{entries}")
        lines.append("")

    # Prices
    pr = s.get("prices", {})
    if "error" not in pr and "note" not in pr:
        lines.extend([
            "PRECIOUS METALS",
            "-" * 40,
            f"  XAU (Gold):   ${pr.get('XAU', 'N/A')} USD/oz",
            f"  XAG (Silver): ${pr.get('XAG', 'N/A')} USD/oz",
            "",
        ])

    # Rates
    er = s.get("exchange_rates", {})
    if "error" not in er and "note" not in er:
        lines.extend(["EXCHANGE RATES (base: " + er.get("base", "USD") + ")", "-" * 40])
        for curr, rate in er.get("rates", {}).items():
            lines.append(f"  {curr}: {rate}")
        lines.append("")

    # Audit
    au = s.get("audit_trail", {})
    if "error" not in au:
        lines.extend([
            "AUDIT TRAIL",
            "-" * 40,
            f"  Total entries: {au.get('total_entries', 0)}",
            f"  By category: {json.dumps(au.get('by_category', {}))}",
            "",
        ])

    lines.append("=" * 60)
    lines.append("END OF REPORT")
    return "\n".join(lines)


def _render_html(report: Dict[str, Any]) -> str:
    s = report["sections"]
    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>{report['title']}</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; background: #f5f5f5; }}
.report {{ background: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
h1 {{ color: #1a237e; border-bottom: 3px solid #1a237e; padding-bottom: 10px; }}
h2 {{ color: #283593; margin-top: 30px; border-left: 4px solid #283593; padding-left: 12px; }}
.meta {{ color: #666; font-size: 14px; }}
.stat {{ display: inline-block; background: #e8eaf6; padding: 8px 16px; margin: 4px; border-radius: 4px; }}
.stat.critical {{ background: #ffcdd2; color: #b71c1c; }}
.stat.warning {{ background: #fff9c4; color: #f57f17; }}
.stat.ok {{ background: #c8e6c9; color: #1b5e20; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
th {{ background: #e8eaf6; font-weight: 600; }}
.overdue {{ color: #b71c1c; font-weight: 600; }}
</style>
</head><body>
<div class="report">
<h1>{report['title']}</h1>
<p class="meta">Generated: {report['generated_at'][:19]} | Timezone: {report['timezone']}</p>
"""

    # Workflow
    wf = s.get("workflow", {})
    if "error" not in wf:
        overdue_class = "critical" if wf.get("overdue", 0) > 0 else "ok"
        html += f"""
<h2>Workflow Status</h2>
<div>
<span class="stat">Active: {wf.get('active_items', 0)}/{wf.get('total_items', 0)}</span>
<span class="stat {overdue_class}">Overdue: {wf.get('overdue', 0)}</span>
<span class="stat warning">Due Today: {wf.get('due_today', 0)}</span>
<span class="stat">Upcoming 7d: {wf.get('upcoming_7d', 0)}</span>
</div>"""
        if wf.get("overdue_items"):
            html += "<table><tr><th>Type</th><th>Title</th><th>Due</th></tr>"
            for item in wf["overdue_items"]:
                html += f"<tr class='overdue'><td>{item['type']}</td><td>{item['title']}</td><td>{item['due']}</td></tr>"
            html += "</table>"

    # Clients
    cl = s.get("clients", {})
    if "error" not in cl:
        html += f"""
<h2>Client Database</h2>
<div>
<span class="stat">Total: {cl.get('total_clients', 0)}</span>
<span class="stat {'critical' if cl.get('reviews_overdue', 0) > 0 else 'ok'}">Reviews Overdue: {cl.get('reviews_overdue', 0)}</span>
<span class="stat">Reviews Upcoming: {cl.get('reviews_upcoming', 0)}</span>
</div>"""

    # Prices
    pr = s.get("prices", {})
    if "error" not in pr and "note" not in pr:
        html += f"""
<h2>Precious Metals</h2>
<div>
<span class="stat">XAU (Gold): ${pr.get('XAU', 'N/A')}</span>
<span class="stat">XAG (Silver): ${pr.get('XAG', 'N/A')}</span>
</div>"""

    # Rates
    er = s.get("exchange_rates", {})
    if "error" not in er and "note" not in er:
        html += f"<h2>Exchange Rates (Base: {er.get('base', 'USD')})</h2><table><tr><th>Currency</th><th>Rate</th></tr>"
        for curr, rate in er.get("rates", {}).items():
            html += f"<tr><td>{curr}</td><td>{rate}</td></tr>"
        html += "</table>"

    # Audit
    au = s.get("audit_trail", {})
    if "error" not in au:
        html += f"""
<h2>Audit Trail</h2>
<span class="stat">Total Entries: {au.get('total_entries', 0)}</span>"""

    html += """
</div></body></html>"""
    return html


def list_reports() -> List[Dict[str, Any]]:
    """List all generated reports."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reports = []
    for f in sorted(REPORTS_DIR.glob("report_*.json"), reverse=True):
        try:
            with open(f, "r") as fp:
                data = json.load(fp)
            reports.append({
                "report_id": data.get("report_id"),
                "title": data.get("title"),
                "generated_at": data.get("generated_at"),
                "path": str(f),
            })
        except Exception:
            pass
    return reports
