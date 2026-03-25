#!/usr/bin/env python3
"""
NotebookLM MCP Server
Exposes NotebookLM + Workflow Management capabilities as MCP tools.

Notebook tools: query, list, add, get, trigger_action
Workflow tools: create/list/get/update/complete/snooze/delete workflow items
                (tasks, projects, meetings, documents, trainings, reports,
                 messages, follow-ups, reminders)
Alert tools:    send_alert, check_workflow, workflow_dashboard, email_status
Price tools:    check_prices, set_price_alert, list_price_alerts, delete_price_alert, price_history

Run via stdio (MCP protocol):
  python scripts/mcp_server.py
"""

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from notebook_manager import NotebookLibrary
from workflow_manager import WorkflowManager, ITEM_TYPES, PRIORITIES, STATUSES, RECURRENCE_TYPES
from email_notifier import send_email, send_workflow_alert, get_status as email_status_info, is_configured as email_configured
from price_tracker import (
    fetch_prices, set_price_alert, list_price_alerts,
    delete_price_alert, check_price_alerts, get_price_history
)
from monitor import ProgressMonitor


def send_response(response: dict):
    """Write a JSON-RPC response to stdout."""
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def send_error(req_id, code: int, message: str):
    send_response({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message}
    })


def handle_initialize(req_id, _params):
    send_response({
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "notebooklm", "version": "2.0.0"}
        }
    })


# ── Tool type/enum constants for schemas ─────────────────────────

_TYPE_ENUM = list(ITEM_TYPES.keys())
_PRIORITY_ENUM = list(PRIORITIES)
_STATUS_ENUM = list(STATUSES)
_RECURRENCE_ENUM = list(RECURRENCE_TYPES)


def handle_tools_list(req_id, _params):
    tools = [
        # ── Notebook tools ───────────────────────────────────────
        {
            "name": "query_notebook",
            "description": "Ask a question to a NotebookLM notebook and get a source-grounded answer.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to ask"},
                    "notebook_url": {"type": "string", "description": "NotebookLM notebook URL (overrides active notebook)"},
                    "notebook_id": {"type": "string", "description": "Library notebook ID (optional)"}
                },
                "required": ["question"]
            }
        },
        {
            "name": "list_notebooks",
            "description": "List all notebooks in the local library.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "add_notebook",
            "description": "Add a notebook to the local library.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "NotebookLM URL"},
                    "name": {"type": "string", "description": "Friendly name"},
                    "description": {"type": "string", "description": "What the notebook contains"},
                    "topics": {"type": "string", "description": "Comma-separated topics"}
                },
                "required": ["url", "name", "description", "topics"]
            }
        },
        {
            "name": "get_notebook",
            "description": "Get details of a notebook by ID or name.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "identifier": {"type": "string", "description": "Notebook ID or name"}
                },
                "required": ["identifier"]
            }
        },
        {
            "name": "trigger_action",
            "description": "Trigger a named action on a notebook: summarize, key-points, questions, or custom prompt.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["summarize", "key-points", "questions", "custom"],
                        "description": "Action to trigger"
                    },
                    "notebook_url": {"type": "string", "description": "NotebookLM notebook URL"},
                    "custom_prompt": {"type": "string", "description": "Custom prompt (required when action=custom)"}
                },
                "required": ["action", "notebook_url"]
            }
        },

        # ── Workflow item tools ──────────────────────────────────
        {
            "name": "create_item",
            "description": (
                "Create a workflow item: task, project, meeting, document, training, "
                "report, message, follow_up, or reminder. Supports due dates (ISO-8601, "
                "relative like 'in 2h', or natural like 'tomorrow'), priorities, "
                "recurrence, tags, and type-specific details."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": _TYPE_ENUM, "description": "Item type"},
                    "title": {"type": "string", "description": "Title or message"},
                    "due": {"type": "string", "description": "Due date/time (e.g. 'in 30m', 'tomorrow', 'friday', ISO-8601)"},
                    "description": {"type": "string", "description": "Detailed description"},
                    "priority": {"type": "string", "enum": _PRIORITY_ENUM, "description": "Priority (default: medium)"},
                    "recurrence": {"type": "string", "enum": _RECURRENCE_ENUM, "description": "Recurrence (default: none)"},
                    "tags": {"type": "string", "description": "Comma-separated tags"},
                    "details": {"type": "string", "description": "JSON string of type-specific details (e.g. attendees, assignee, doc_type)"},
                    "notify": {"type": "boolean", "description": "Send email notification on creation (default: false)"}
                },
                "required": ["type", "title"]
            }
        },
        {
            "name": "list_items",
            "description": "List workflow items with optional filters. Sorted by due date.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": _TYPE_ENUM, "description": "Filter by item type"},
                    "status": {"type": "string", "enum": _STATUS_ENUM, "description": "Filter by status"},
                    "priority": {"type": "string", "enum": _PRIORITY_ENUM, "description": "Filter by priority"},
                    "tag": {"type": "string", "description": "Filter by tag"},
                    "search": {"type": "string", "description": "Search in title, description, tags"},
                    "include_done": {"type": "boolean", "description": "Include completed items (default: false)"}
                }
            }
        },
        {
            "name": "get_item",
            "description": "Get full details of a workflow item by ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The item ID"}
                },
                "required": ["item_id"]
            }
        },
        {
            "name": "update_item",
            "description": "Update fields on an existing workflow item.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The item ID to update"},
                    "title": {"type": "string", "description": "New title"},
                    "description": {"type": "string", "description": "New description"},
                    "due": {"type": "string", "description": "New due date"},
                    "priority": {"type": "string", "enum": _PRIORITY_ENUM, "description": "New priority"},
                    "status": {"type": "string", "enum": _STATUS_ENUM, "description": "New status"},
                    "recurrence": {"type": "string", "enum": _RECURRENCE_ENUM, "description": "New recurrence"},
                    "tags": {"type": "string", "description": "Comma-separated tags (replaces existing)"},
                    "details": {"type": "string", "description": "JSON string of detail updates (merged with existing)"}
                },
                "required": ["item_id"]
            }
        },
        {
            "name": "complete_item",
            "description": "Mark a workflow item as done. Recurring items automatically create the next occurrence.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The item ID to complete"}
                },
                "required": ["item_id"]
            }
        },
        {
            "name": "snooze_item",
            "description": "Snooze/postpone a workflow item to a new time.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The item ID to snooze"},
                    "until": {"type": "string", "description": "New due time (e.g. 'in 15m', 'tomorrow')"}
                },
                "required": ["item_id", "until"]
            }
        },
        {
            "name": "delete_item",
            "description": "Permanently delete a workflow item.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The item ID to delete"}
                },
                "required": ["item_id"]
            }
        },
        {
            "name": "add_follow_up",
            "description": "Create a follow-up item linked to an existing item (task, meeting, etc.).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "parent_id": {"type": "string", "description": "ID of the parent item"},
                    "title": {"type": "string", "description": "Follow-up title/action"},
                    "due": {"type": "string", "description": "When the follow-up is due"},
                    "description": {"type": "string", "description": "Details"},
                    "priority": {"type": "string", "enum": _PRIORITY_ENUM, "description": "Priority (default: medium)"},
                    "notify": {"type": "boolean", "description": "Send email notification (default: false)"}
                },
                "required": ["parent_id", "title"]
            }
        },

        # ── Dashboard & alerts ───────────────────────────────────
        {
            "name": "check_workflow",
            "description": "Check for overdue items, items due soon (30 min), due today, and upcoming (7 days). Your workflow at-a-glance.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "workflow_dashboard",
            "description": "Full workflow dashboard: counts by type, status, priority, plus top overdue items.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "send_alert",
            "description": (
                "Send an email alert. Either provide subject+body for a custom email, "
                "or item_id to email about a specific workflow item. "
                "Supports multiple recipients (configured via ALERT_EMAIL_TO in .env). "
                "Can also add one-time extra recipients."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Email body text"},
                    "item_id": {"type": "string", "description": "Send alert for a specific workflow item"},
                    "priority": {"type": "string", "enum": _PRIORITY_ENUM, "description": "Email priority (default: medium)"},
                    "extra_recipients": {"type": "string", "description": "Comma-separated additional email addresses for this alert only"}
                }
            }
        },
        {
            "name": "email_status",
            "description": "Check email notification configuration status.",
            "inputSchema": {"type": "object", "properties": {}}
        },

        # ── Price tracking tools ─────────────────────────────────
        {
            "name": "check_prices",
            "description": "Get current gold and silver prices (USD/oz) from Reuters/LSEG. "
                           "Also shows the gold/silver ratio and checks any active price alerts.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "set_price_alert",
            "description": "Set a price alert for gold or silver. Get emailed when price crosses your threshold.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "metal": {"type": "string", "enum": ["gold", "silver"], "description": "Which metal"},
                    "condition": {"type": "string", "enum": ["above", "below"], "description": "Trigger when price goes above or below target"},
                    "price": {"type": "number", "description": "Target price in USD/oz"},
                    "notify": {"type": "boolean", "description": "Send email when triggered (default: true)"}
                },
                "required": ["metal", "condition", "price"]
            }
        },
        {
            "name": "list_price_alerts",
            "description": "List all active price alerts for gold and silver.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "delete_price_alert",
            "description": "Delete a price alert by ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "alert_id": {"type": "string", "description": "The alert ID to delete"}
                },
                "required": ["alert_id"]
            }
        },
        {
            "name": "price_history",
            "description": "Get price history for gold or silver over a number of days.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "metal": {"type": "string", "enum": ["gold", "silver"], "description": "Which metal (default: gold)"},
                    "days": {"type": "number", "description": "Number of days of history (default: 7)"}
                }
            }
        },
    ]
    send_response({"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}})


ACTION_PROMPTS = {
    "summarize": "Provide a comprehensive summary of all the documents in this notebook. Cover the main themes, key findings, and important details.",
    "key-points": "List the most important key points, facts, and insights from all documents in this notebook. Format as a numbered list.",
    "questions": "Generate 10 insightful questions that can be answered from the documents in this notebook, then answer each one briefly."
}


def handle_tool_call(req_id, params):
    tool_name = params.get("name")
    args = params.get("arguments", {})
    monitor = ProgressMonitor(tool_name)

    try:
        # ── Notebook handlers ────────────────────────────────────

        if tool_name == "list_notebooks":
            monitor.start("Loading notebook library")
            lib = NotebookLibrary()
            notebooks = list(lib.notebooks.values())
            monitor.complete(f"Found {len(notebooks)} notebooks")
            result_text = json.dumps(notebooks, indent=2) if notebooks else "No notebooks in library."
            _tool_result(req_id, result_text)

        elif tool_name == "add_notebook":
            monitor.start("Adding notebook to library")
            lib = NotebookLibrary()
            topics = [t.strip() for t in args.get("topics", "").split(",") if t.strip()]
            nb_id = lib.add_notebook(
                url=args["url"],
                name=args["name"],
                description=args["description"],
                topics=topics
            )
            monitor.complete(f"Notebook added with ID: {nb_id}")
            _tool_result(req_id, f"Notebook added successfully with ID: {nb_id}")

        elif tool_name == "get_notebook":
            monitor.start("Looking up notebook")
            lib = NotebookLibrary()
            identifier = args["identifier"]
            nb = lib.notebooks.get(identifier)
            if not nb:
                for n in lib.notebooks.values():
                    if n.get("name", "").lower() == identifier.lower():
                        nb = n
                        break
            monitor.complete("Done")
            result_text = json.dumps(nb, indent=2) if nb else f"Notebook not found: {identifier}"
            _tool_result(req_id, result_text)

        elif tool_name == "query_notebook":
            _run_query(req_id, args, monitor)

        elif tool_name == "trigger_action":
            action = args.get("action", "")
            if action == "custom":
                question = args.get("custom_prompt", "")
                if not question:
                    send_error(req_id, -32602, "custom_prompt is required for action=custom")
                    return
            else:
                question = ACTION_PROMPTS.get(action)
                if not question:
                    send_error(req_id, -32602, f"Unknown action: {action}")
                    return
            _run_query(req_id, {"question": question, "notebook_url": args.get("notebook_url")}, monitor)

        # ── Workflow item handlers ───────────────────────────────

        elif tool_name == "create_item":
            monitor.start(f"Creating {args.get('type', 'item')}")
            wf = WorkflowManager()
            tags = [t.strip() for t in args.get("tags", "").split(",") if t.strip()] if args.get("tags") else None
            details = json.loads(args["details"]) if args.get("details") else None
            item = wf.create(
                item_type=args["type"],
                title=args["title"],
                due=args.get("due"),
                description=args.get("description", ""),
                priority=args.get("priority", "medium"),
                recurrence=args.get("recurrence", "none"),
                tags=tags,
                details=details,
                notify=args.get("notify", False),
            )
            monitor.complete(f"{item['type_label']} {item['id']} created")
            _tool_result(req_id, json.dumps(item, indent=2))

        elif tool_name == "list_items":
            monitor.start("Listing workflow items")
            wf = WorkflowManager()
            items = wf.list_items(
                item_type=args.get("type"),
                status=args.get("status"),
                priority=args.get("priority"),
                tag=args.get("tag"),
                search=args.get("search"),
                include_done=args.get("include_done", False),
            )
            monitor.complete(f"Found {len(items)} items")
            if items:
                # Compact summary
                lines = []
                for it in items:
                    due = it["due"][:16] if it.get("due") else "no due"
                    lines.append(
                        f"[{it['id']}] {it['type_label']:10s} | {it['priority']:8s} | "
                        f"{it['status']:11s} | {due} | {it['title']}"
                    )
                header = f"{'ID':10s} {'Type':10s} | {'Priority':8s} | {'Status':11s} | {'Due':16s} | Title"
                _tool_result(req_id, header + "\n" + "\n".join(lines))
            else:
                _tool_result(req_id, "No items found.")

        elif tool_name == "get_item":
            monitor.start("Looking up item")
            wf = WorkflowManager()
            item = wf.get(args["item_id"])
            monitor.complete("Done")
            if item:
                _tool_result(req_id, json.dumps(item, indent=2))
            else:
                _tool_result(req_id, f"Item not found: {args['item_id']}")

        elif tool_name == "update_item":
            monitor.start("Updating item")
            wf = WorkflowManager()
            updates = {}
            for field in ("title", "description", "due", "priority", "status", "recurrence"):
                if field in args:
                    updates[field] = args[field]
            if "tags" in args:
                updates["tags"] = [t.strip() for t in args["tags"].split(",") if t.strip()]
            if "details" in args:
                updates["details"] = json.loads(args["details"])
            item = wf.update(args["item_id"], updates)
            monitor.complete(f"Item {args['item_id']} updated")
            _tool_result(req_id, json.dumps(item, indent=2))

        elif tool_name == "complete_item":
            monitor.start("Completing item")
            wf = WorkflowManager()
            result = wf.complete(args["item_id"])
            completed = result["completed"]
            next_occ = result["next_occurrence"]
            monitor.complete(f"Item {args['item_id']} completed")
            msg = f"Completed: {completed['title']}"
            if next_occ:
                msg += f"\nNext occurrence created: {next_occ['id']} (due {next_occ['due']})"
            _tool_result(req_id, msg)

        elif tool_name == "snooze_item":
            monitor.start("Snoozing item")
            wf = WorkflowManager()
            item = wf.snooze(args["item_id"], args["until"])
            monitor.complete(f"Snoozed until {item['due']}")
            _tool_result(req_id, f"Snoozed until {item['due']}\n" + json.dumps(item, indent=2))

        elif tool_name == "delete_item":
            monitor.start("Deleting item")
            wf = WorkflowManager()
            deleted = wf.delete(args["item_id"])
            monitor.complete("Done")
            _tool_result(req_id, f"Item {args['item_id']} deleted." if deleted else f"Item not found: {args['item_id']}")

        elif tool_name == "add_follow_up":
            monitor.start("Creating follow-up")
            wf = WorkflowManager()
            follow_up = wf.add_follow_up(
                parent_id=args["parent_id"],
                title=args["title"],
                due=args.get("due"),
                description=args.get("description", ""),
                priority=args.get("priority", "medium"),
                notify=args.get("notify", False),
            )
            monitor.complete(f"Follow-up {follow_up['id']} created")
            _tool_result(req_id, json.dumps(follow_up, indent=2))

        # ── Dashboard & alert handlers ───────────────────────────

        elif tool_name == "check_workflow":
            monitor.start("Checking workflow")
            wf = WorkflowManager()
            result = wf.check_due()
            monitor.complete("Done")
            parts = []
            for key, label in [("overdue", "OVERDUE"), ("due_soon", "DUE IN 30 MIN"),
                                ("due_today", "DUE TODAY"), ("upcoming_7_days", "NEXT 7 DAYS")]:
                items = result[key]
                if items:
                    lines = []
                    for it in items:
                        due_str = it["due"][:16] if it.get("due") else ""
                        lines.append(f"  [{it['id']}] {it['type_label']}: {it['title']} (due {due_str}, {it['priority']})")
                    parts.append(f"{label} ({len(items)}):\n" + "\n".join(lines))
            if not parts:
                parts.append("All clear - nothing overdue or due soon.")
            _tool_result(req_id, "\n\n".join(parts))

        elif tool_name == "workflow_dashboard":
            monitor.start("Building dashboard")
            wf = WorkflowManager()
            dash = wf.dashboard()
            monitor.complete("Done")
            _tool_result(req_id, json.dumps(dash, indent=2))

        elif tool_name == "send_alert":
            monitor.start("Sending email alert")
            extra = [e.strip() for e in args.get("extra_recipients", "").split(",") if e.strip()] if args.get("extra_recipients") else None
            item_id = args.get("item_id")
            if item_id:
                wf = WorkflowManager()
                item = wf.get(item_id)
                if not item:
                    send_error(req_id, -32602, f"Item not found: {item_id}")
                    return
                result = send_workflow_alert(item, action="alert")
            else:
                subject = args.get("subject", "Workflow Alert")
                body = args.get("body", "")
                if not body:
                    send_error(req_id, -32602, "Either 'body' or 'item_id' is required")
                    return
                result = send_email(subject, body, args.get("priority", "medium"), extra_recipients=extra)
            monitor.complete("Done")
            _tool_result(req_id, result)

        elif tool_name == "email_status":
            monitor.start("Checking email config")
            status = email_status_info()
            monitor.complete("Done")
            if status["configured"]:
                lines = [
                    "Email notifications: CONFIGURED",
                    f"Recipients: {', '.join(status['recipients'])}",
                    f"Sender: {status['sender']}",
                    f"SMTP: {status['smtp_host']}:{status['smtp_port']}",
                ]
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id,
                    "Email notifications: NOT CONFIGURED\n\n"
                    "Add these to your .env file:\n"
                    "  ALERT_EMAIL_TO=work@company.com,personal@gmail.com\n"
                    "  ALERT_SMTP_PASSWORD=your-app-password\n\n"
                    "Optional:\n"
                    "  ALERT_EMAIL_FROM=sender@email.com\n"
                    "  ALERT_SMTP_HOST=smtp.gmail.com\n"
                    "  ALERT_SMTP_PORT=587\n\n"
                    "For Gmail: use an App Password (not your regular password).\n"
                    "Generate at: https://myaccount.google.com/apppasswords\n\n"
                    "Multiple recipients: separate with commas in ALERT_EMAIL_TO.")

        # ── Price tracking handlers ───────────────────────────────

        elif tool_name == "check_prices":
            monitor.start("Fetching gold & silver prices")
            result = fetch_prices()
            monitor.complete("Done")
            if "error" in result:
                _tool_result(req_id, f"Error: {result['error']}")
            else:
                gold = result["gold"]
                silver = result["silver"]
                lines = [
                    f"Gold (XAU):   ${gold['price']:,.2f} USD/oz",
                    f"Silver (XAG): ${silver['price']:,.2f} USD/oz",
                    f"Gold/Silver Ratio: {result['gold_silver_ratio']:.1f}",
                    f"Source: {result['source']}",
                    f"Time: {result['timestamp'][:19]}",
                ]
                # Check alerts
                triggered = check_price_alerts(result)
                if triggered:
                    lines.append("")
                    lines.append("ALERTS TRIGGERED:")
                    for a in triggered:
                        lines.append(f"  {a['metal'].upper()} {a['condition']} ${a['target_price']:.2f} (current: ${a['triggered_price']:.2f})")
                _tool_result(req_id, "\n".join(lines))

        elif tool_name == "set_price_alert":
            monitor.start("Setting price alert")
            alert = set_price_alert(
                metal=args["metal"],
                condition=args["condition"],
                price=float(args["price"]),
                notify=args.get("notify", True),
            )
            monitor.complete("Done")
            _tool_result(req_id,
                f"Price alert set: {alert['metal'].upper()} {alert['condition']} ${alert['target_price']:.2f}\n"
                f"ID: {alert['id']}\n"
                f"Email notification: {'ON' if alert['notify'] else 'OFF'}")

        elif tool_name == "list_price_alerts":
            monitor.start("Loading price alerts")
            alerts = list_price_alerts()
            monitor.complete("Done")
            if alerts:
                lines = []
                for a in alerts:
                    status = "TRIGGERED" if a["triggered"] else "active"
                    lines.append(
                        f"[{a['id']}] {a['metal'].upper()} {a['condition']} "
                        f"${a['target_price']:.2f} - {status}"
                    )
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, "No price alerts set.")

        elif tool_name == "delete_price_alert":
            monitor.start("Deleting price alert")
            deleted = delete_price_alert(args["alert_id"])
            monitor.complete("Done")
            _tool_result(req_id,
                f"Alert {args['alert_id']} deleted." if deleted
                else f"Alert not found: {args['alert_id']}")

        elif tool_name == "price_history":
            monitor.start("Loading price history")
            metal = args.get("metal", "gold")
            days = int(args.get("days", 7))
            history = get_price_history(metal, days)
            monitor.complete("Done")
            if history:
                lines = [f"{metal.upper()} price history (last {days} days):"]
                for h in history[-20:]:  # Last 20 entries
                    lines.append(f"  {h['timestamp'][:16]} - ${h[metal]:,.2f}")
                if len(history) > 20:
                    lines.insert(1, f"  (showing last 20 of {len(history)} entries)")
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, f"No price history for {metal}. Run 'check_prices' first to start tracking.")

        else:
            send_error(req_id, -32601, f"Unknown tool: {tool_name}")

    except Exception as e:
        monitor.error(str(e))
        send_error(req_id, -32603, f"Tool execution failed: {e}\n{traceback.format_exc()}")


def _run_query(req_id, args, monitor: "ProgressMonitor"):
    """Execute a NotebookLM query."""
    from ask_question import ask_notebooklm

    question = args.get("question", "")
    notebook_url = args.get("notebook_url")

    if not notebook_url:
        lib = NotebookLibrary()
        if lib.active_notebook_id and lib.active_notebook_id in lib.notebooks:
            notebook_url = lib.notebooks[lib.active_notebook_id]["url"]

    if not notebook_url:
        send_error(req_id, -32602, "notebook_url is required (no active notebook set)")
        return

    monitor.start(f"Querying notebook: {notebook_url[:60]}...")
    monitor.update("Opening browser session")
    answer = ask_notebooklm(question, notebook_url, headless=True)
    monitor.complete("Query complete")

    _tool_result(req_id, answer or "No answer received from NotebookLM.")


def _tool_result(req_id, text: str):
    send_response({
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "content": [{"type": "text", "text": text}]
        }
    })


def main():
    """Main MCP server loop — reads JSON-RPC from stdin, writes to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            send_error(None, -32700, f"Parse error: {e}")
            continue

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        if method == "initialize":
            handle_initialize(req_id, params)
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            handle_tools_list(req_id, params)
        elif method == "tools/call":
            handle_tool_call(req_id, params)
        else:
            send_error(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
