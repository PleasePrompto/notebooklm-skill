#!/usr/bin/env python3
"""
Web Dashboard Server
Simple HTTP server that serves an auto-refreshing compliance dashboard.
Run: python scripts/web_dashboard.py [port]
"""

import json
import sys
import http.server
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
DEFAULT_PORT = 8080


def _gather_dashboard_data() -> Dict[str, Any]:
    """Gather all data for the dashboard."""
    data = {"generated_at": datetime.now(TIMEZONE).isoformat()}

    try:
        from workflow_manager import WorkflowManager
        wf = WorkflowManager()
        data["workflow"] = wf.dashboard()
        data["workflow_due"] = wf.check_due()
    except Exception as e:
        data["workflow"] = {"error": str(e)}

    try:
        from client_database import ClientDatabase
        db = ClientDatabase()
        data["clients"] = db.get_stats()
        reviews = db.get_review_due()
        data["reviews_overdue"] = [{"name": c["name"], "risk": c["risk_rating"], "due": (c.get("review_date") or "")[:10]} for c in reviews["overdue"]]
    except Exception:
        data["clients"] = {}

    try:
        from sanctions_checker import get_list_status
        data["sanctions"] = get_list_status()
    except Exception:
        data["sanctions"] = {}

    try:
        from audit_trail import audit_stats
        data["audit"] = audit_stats()
    except Exception:
        data["audit"] = {}

    try:
        from compliance_calendar import get_upcoming_deadlines
        data["deadlines"] = get_upcoming_deadlines(30)[:10]
    except Exception:
        data["deadlines"] = []

    try:
        from regulatory_feed import get_feed_status
        data["feed"] = get_feed_status()
    except Exception:
        data["feed"] = {}

    return data


def _render_dashboard_html(data: Dict[str, Any]) -> str:
    wf = data.get("workflow", {})
    cl = data.get("clients", {})
    au = data.get("audit", {})
    feed = data.get("feed", {})

    # Compute high-risk client count
    risk_ratings = cl.get("by_risk_rating", {})
    high_risk_count = risk_ratings.get("high", 0) + risk_ratings.get("critical", 0)

    # Overdue items
    overdue_items = data.get("workflow_due", {}).get("overdue", [])
    due_today = data.get("workflow_due", {}).get("due_today", []) + data.get("workflow_due", {}).get("due_soon", [])

    overdue_html = ""
    for item in overdue_items[:8]:
        overdue_html += f"<div class='item overdue'><span class='badge critical'>{item.get('priority','')}</span> <b>{item.get('type_label','')}</b>: {item.get('title','')} <span class='due'>due {(item.get('due',''))[:16]}</span></div>"

    today_html = ""
    for item in due_today[:8]:
        today_html += f"<div class='item'><span class='badge'>{item.get('priority','')}</span> <b>{item.get('type_label','')}</b>: {item.get('title','')} <span class='due'>due {(item.get('due',''))[:16]}</span></div>"

    # Deadlines
    deadline_html = ""
    for d in data.get("deadlines", [])[:8]:
        deadline_html += f"<div class='item'><span class='badge'>{d.get('authority','')}</span> {d.get('title','')} <span class='due'>in {d.get('days_until','')} days</span></div>"

    # Reviews overdue
    reviews_html = ""
    for r in data.get("reviews_overdue", [])[:5]:
        reviews_html += f"<div class='item overdue'>{r['name']} <span class='badge critical'>{r['risk']}</span> <span class='due'>due {r['due']}</span></div>"

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="60">
<title>Compliance Dashboard - Finegold</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }}
.header {{ background: linear-gradient(135deg, #1e293b, #0f172a); padding: 20px 30px; border-bottom: 2px solid #334155; display: flex; justify-content: space-between; align-items: center; }}
.logo {{ font-size: 24px; font-weight: 800; color: #f8fafc; letter-spacing: 2px; }}
.logo span {{ color: #3b82f6; }}
.time {{ color: #94a3b8; font-size: 13px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; padding: 20px; }}
.card {{ background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }}
.card h3 {{ color: #3b82f6; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 10px; }}
.stat {{ background: #0f172a; padding: 12px 16px; border-radius: 8px; text-align: center; min-width: 80px; flex: 1; }}
.stat .num {{ font-size: 28px; font-weight: 700; color: #f8fafc; }}
.stat .label {{ font-size: 10px; color: #64748b; text-transform: uppercase; margin-top: 4px; }}
.stat.critical .num {{ color: #ef4444; }}
.stat.warn .num {{ color: #f59e0b; }}
.stat.ok .num {{ color: #22c55e; }}
.item {{ padding: 8px 12px; border-left: 3px solid #334155; margin: 6px 0; font-size: 12px; background: #0f172a; border-radius: 0 6px 6px 0; }}
.item.overdue {{ border-left-color: #ef4444; background: #1c1017; }}
.badge {{ background: #334155; color: #94a3b8; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; text-transform: uppercase; }}
.badge.critical {{ background: #7f1d1d; color: #fca5a5; }}
.due {{ color: #64748b; font-size: 11px; float: right; }}
.footer {{ text-align: center; padding: 15px; color: #475569; font-size: 11px; }}
.wide {{ grid-column: span 2; }}
@media (max-width: 768px) {{ .wide {{ grid-column: span 1; }} .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head><body>
<div class="header">
    <div>
        <div class="logo">FINE<span>GOLD</span> Compliance</div>
    </div>
    <div class="time">
        <div>Last updated: {data['generated_at'][:19]} GST</div>
        <div>Auto-refreshes every 60 seconds</div>
    </div>
</div>

<div class="grid">
    <div class="card">
        <h3>Workflow Overview</h3>
        <div class="stats">
            <div class="stat"><div class="num">{wf.get('active_items',0)}</div><div class="label">Active</div></div>
            <div class="stat {'critical' if wf.get('overdue_count',0) > 0 else 'ok'}"><div class="num">{wf.get('overdue_count',0)}</div><div class="label">Overdue</div></div>
            <div class="stat warn"><div class="num">{wf.get('due_today_count',0)}</div><div class="label">Due Today</div></div>
            <div class="stat"><div class="num">{wf.get('upcoming_7d_count',0)}</div><div class="label">Next 7d</div></div>
        </div>
    </div>

    <div class="card">
        <h3>Clients & KYC</h3>
        <div class="stats">
            <div class="stat"><div class="num">{cl.get('total_clients',0)}</div><div class="label">Total</div></div>
            <div class="stat critical"><div class="num">{cl.get('reviews_overdue',0)}</div><div class="label">Reviews Due</div></div>
            <div class="stat"><div class="num">{high_risk_count}</div><div class="label">High Risk</div></div>
        </div>
    </div>

    <div class="card">
        <h3>Audit & Feed</h3>
        <div class="stats">
            <div class="stat"><div class="num">{au.get('total_entries',0)}</div><div class="label">Audit Entries</div></div>
            <div class="stat"><div class="num">{feed.get('unread',0)}</div><div class="label">Unread News</div></div>
            <div class="stat"><div class="num">{feed.get('total_articles',0)}</div><div class="label">Total Articles</div></div>
        </div>
    </div>

    <div class="card">
        <h3>Priority by Type</h3>
        <div class="stats">
            {"".join(f'<div class="stat"><div class="num">{v}</div><div class="label">{k}</div></div>' for k,v in wf.get("by_type",{}).items())}
        </div>
    </div>

    <div class="card wide">
        <h3>Overdue Items ({len(overdue_items)})</h3>
        {overdue_html or '<div class="item" style="border-left-color:#22c55e">All clear - no overdue items</div>'}
    </div>

    <div class="card">
        <h3>Due Today ({len(due_today)})</h3>
        {today_html or '<div class="item">Nothing due today</div>'}
    </div>

    <div class="card">
        <h3>Regulatory Deadlines (30 days)</h3>
        {deadline_html or '<div class="item">No upcoming deadlines. Run load_compliance_calendar to populate.</div>'}
    </div>

    <div class="card">
        <h3>KYC Reviews Overdue</h3>
        {reviews_html or '<div class="item" style="border-left-color:#22c55e">No reviews overdue</div>'}
    </div>
</div>

<div class="footer">
    Finegold LLC - Compliance Dashboard | Confidential | Auto-refresh: 60s
</div>
</body></html>"""


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/dashboard":
            data = _gather_dashboard_data()
            html = _render_dashboard_html(data)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
        elif self.path == "/api/data":
            data = _gather_dashboard_data()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logging


def start_dashboard(port: int = DEFAULT_PORT) -> str:
    """Start the web dashboard server."""
    server = http.server.HTTPServer(("0.0.0.0", port), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"Dashboard running at http://localhost:{port}"


def generate_static_dashboard() -> str:
    """Generate a static HTML dashboard file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = _gather_dashboard_data()
    html = _render_dashboard_html(data)
    path = DATA_DIR / "dashboard.html"
    with open(path, "w") as f:
        f.write(html)
    return str(path)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    print(f"Starting compliance dashboard on http://localhost:{port}")
    print("Press Ctrl+C to stop")
    server = http.server.HTTPServer(("0.0.0.0", port), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
