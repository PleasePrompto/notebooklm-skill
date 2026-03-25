#!/usr/bin/env python3
"""
NotebookLM MCP Server
Exposes NotebookLM capabilities as MCP tools:
  - query_notebook: Ask a question to a specific notebook
  - list_notebooks: List all notebooks in the library
  - add_notebook: Add a new notebook to the library
  - get_notebook: Get notebook details by ID or name
  - trigger_action: Trigger named actions (summarize, key-points, etc.)
  - set_reminder: Create a reminder with due time, priority, recurrence
  - list_reminders: List reminders with filters
  - get_reminder: Get reminder details
  - check_reminders: Check for overdue/upcoming reminders
  - complete_reminder: Mark a reminder as done
  - snooze_reminder: Postpone a reminder
  - delete_reminder: Remove a reminder
  - send_alert: Send email notifications
  - email_status: Check email configuration

Run via stdio (MCP protocol):
  python scripts/mcp_server.py
"""

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from notebook_manager import NotebookLibrary
from reminder_manager import ReminderManager
from email_notifier import send_email, send_reminder_alert, is_configured as email_configured
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
            "serverInfo": {"name": "notebooklm", "version": "1.0.0"}
        }
    })


def handle_tools_list(req_id, _params):
    tools = [
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
        }
        # ── Reminder & Alert tools ──
        {
            "name": "set_reminder",
            "description": "Create a reminder with a message, due time, priority, and optional recurrence. "
                           "Due accepts: ISO-8601, relative ('in 5m', 'in 2h', 'in 3d'), or natural ('tomorrow', 'next week', 'eod').",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "What to be reminded about"},
                    "due": {"type": "string", "description": "When the reminder is due (e.g. 'in 30m', 'tomorrow', '2026-04-01T09:00:00')"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"], "description": "Priority level (default: medium)"},
                    "recurrence": {"type": "string", "enum": ["none", "daily", "weekly", "monthly"], "description": "Recurrence pattern (default: none)"},
                    "tags": {"type": "string", "description": "Comma-separated tags for organization"}
                },
                "required": ["message", "due"]
            }
        },
        {
            "name": "list_reminders",
            "description": "List active reminders sorted by due date. Filter by status, priority, or tag.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["pending", "done", "snoozed", "overdue"], "description": "Filter by status"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"], "description": "Filter by priority"},
                    "tag": {"type": "string", "description": "Filter by tag"},
                    "include_done": {"type": "boolean", "description": "Include completed reminders (default: false)"}
                }
            }
        },
        {
            "name": "get_reminder",
            "description": "Get full details of a specific reminder by its ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "string", "description": "The reminder ID"}
                },
                "required": ["reminder_id"]
            }
        },
        {
            "name": "check_reminders",
            "description": "Check for overdue and upcoming (due within 30 min) reminders. Use this to see what needs attention right now.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "complete_reminder",
            "description": "Mark a reminder as done. Recurring reminders automatically create the next occurrence.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "string", "description": "The reminder ID to complete"}
                },
                "required": ["reminder_id"]
            }
        },
        {
            "name": "snooze_reminder",
            "description": "Snooze a reminder to a new time. Accepts same time formats as set_reminder.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "string", "description": "The reminder ID to snooze"},
                    "duration": {"type": "string", "description": "New due time (e.g. 'in 15m', 'in 1h', 'tomorrow')"}
                },
                "required": ["reminder_id", "duration"]
            }
        },
        {
            "name": "send_alert",
            "description": "Send an email alert/notification. Can send a custom message or notify about a specific reminder. "
                           "Requires ALERT_EMAIL_TO and ALERT_SMTP_PASSWORD in .env.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Email body text"},
                    "reminder_id": {"type": "string", "description": "Send alert for a specific reminder (alternative to subject/body)"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"], "description": "Email priority (default: medium)"}
                }
            }
        },
        {
            "name": "email_status",
            "description": "Check if email notifications are configured and working.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "delete_reminder",
            "description": "Permanently delete a reminder.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "string", "description": "The reminder ID to delete"}
                },
                "required": ["reminder_id"]
            }
        }
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
            # Try by ID first, then by name
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

        # ── Reminder tool handlers ──

        elif tool_name == "set_reminder":
            monitor.start("Creating reminder")
            mgr = ReminderManager()
            tags = [t.strip() for t in args.get("tags", "").split(",") if t.strip()] if args.get("tags") else None
            reminder = mgr.add(
                message=args["message"],
                due=args["due"],
                priority=args.get("priority", "medium"),
                recurrence=args.get("recurrence", "none"),
                tags=tags,
            )
            monitor.complete(f"Reminder {reminder['id']} created")
            _tool_result(req_id, json.dumps(reminder, indent=2))

        elif tool_name == "list_reminders":
            monitor.start("Listing reminders")
            mgr = ReminderManager()
            reminders = mgr.list_reminders(
                status=args.get("status"),
                priority=args.get("priority"),
                tag=args.get("tag"),
                include_done=args.get("include_done", False),
            )
            monitor.complete(f"Found {len(reminders)} reminders")
            if reminders:
                _tool_result(req_id, json.dumps(reminders, indent=2))
            else:
                _tool_result(req_id, "No reminders found.")

        elif tool_name == "get_reminder":
            monitor.start("Looking up reminder")
            mgr = ReminderManager()
            reminder = mgr.get(args["reminder_id"])
            monitor.complete("Done")
            if reminder:
                _tool_result(req_id, json.dumps(reminder, indent=2))
            else:
                _tool_result(req_id, f"Reminder not found: {args['reminder_id']}")

        elif tool_name == "check_reminders":
            monitor.start("Checking due reminders")
            mgr = ReminderManager()
            result = mgr.check_due()
            monitor.complete("Done")
            overdue = result["overdue"]
            due_soon = result["due_soon"]
            parts = []
            if overdue:
                parts.append(f"OVERDUE ({len(overdue)}):\n" + json.dumps(overdue, indent=2))
            if due_soon:
                parts.append(f"DUE SOON ({len(due_soon)}):\n" + json.dumps(due_soon, indent=2))
            if not parts:
                parts.append("All clear - no overdue or upcoming reminders.")
            _tool_result(req_id, "\n\n".join(parts))

        elif tool_name == "complete_reminder":
            monitor.start("Completing reminder")
            mgr = ReminderManager()
            reminder = mgr.complete(args["reminder_id"])
            monitor.complete(f"Reminder {args['reminder_id']} completed")
            msg = f"Reminder completed: {reminder['message']}"
            if reminder.get("recurrence") != "none":
                msg += f"\nNext occurrence created ({reminder['recurrence']} recurrence)."
            _tool_result(req_id, msg)

        elif tool_name == "snooze_reminder":
            monitor.start("Snoozing reminder")
            mgr = ReminderManager()
            reminder = mgr.snooze(args["reminder_id"], args["duration"])
            monitor.complete(f"Snoozed until {reminder['due']}")
            _tool_result(req_id, f"Reminder snoozed until {reminder['due']}\n" + json.dumps(reminder, indent=2))

        elif tool_name == "send_alert":
            monitor.start("Sending email alert")
            reminder_id = args.get("reminder_id")
            if reminder_id:
                mgr = ReminderManager()
                reminder = mgr.get(reminder_id)
                if not reminder:
                    send_error(req_id, -32602, f"Reminder not found: {reminder_id}")
                    return
                result = send_reminder_alert(reminder)
            else:
                subject = args.get("subject", "Alert from NotebookLM Skill")
                body = args.get("body", "")
                if not body:
                    send_error(req_id, -32602, "Either 'body' or 'reminder_id' is required")
                    return
                result = send_email(subject, body, args.get("priority", "medium"))
            monitor.complete("Done")
            _tool_result(req_id, result)

        elif tool_name == "email_status":
            monitor.start("Checking email config")
            configured = email_configured()
            monitor.complete("Done")
            if configured:
                _tool_result(req_id, "Email notifications are configured and ready. Use 'send_alert' to send emails.")
            else:
                _tool_result(req_id,
                    "Email notifications are NOT configured.\n\n"
                    "Add these to your .env file:\n"
                    "  ALERT_EMAIL_TO=your@email.com\n"
                    "  ALERT_SMTP_PASSWORD=your-app-password\n\n"
                    "Optional:\n"
                    "  ALERT_EMAIL_FROM=sender@email.com\n"
                    "  ALERT_SMTP_HOST=smtp.gmail.com\n"
                    "  ALERT_SMTP_PORT=587\n"
                    "  ALERT_SMTP_USER=your@email.com\n\n"
                    "For Gmail: use an App Password (not your regular password).\n"
                    "Generate one at: https://myaccount.google.com/apppasswords")

        elif tool_name == "delete_reminder":
            monitor.start("Deleting reminder")
            mgr = ReminderManager()
            deleted = mgr.delete(args["reminder_id"])
            monitor.complete("Done")
            if deleted:
                _tool_result(req_id, f"Reminder {args['reminder_id']} deleted.")
            else:
                _tool_result(req_id, f"Reminder not found: {args['reminder_id']}")

        else:
            send_error(req_id, -32601, f"Unknown tool: {tool_name}")

    except Exception as e:
        monitor.error(str(e))
        send_error(req_id, -32603, f"Tool execution failed: {e}\n{traceback.format_exc()}")


def _run_query(req_id, args, monitor: "ProgressMonitor"):
    """Execute a NotebookLM query (imports ask_question to avoid circular deps)."""
    from ask_question import ask_notebooklm

    question = args.get("question", "")
    notebook_url = args.get("notebook_url")

    if not notebook_url:
        # Try active notebook from library
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
            pass  # No response needed
        elif method == "tools/list":
            handle_tools_list(req_id, params)
        elif method == "tools/call":
            handle_tool_call(req_id, params)
        else:
            send_error(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
