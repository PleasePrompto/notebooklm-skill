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
from currency_tracker import (
    fetch_rates, convert as convert_currency, set_rate_alert,
    list_rate_alerts, delete_rate_alert, check_rate_alerts, get_rate_history
)
from sanctions_checker import (
    download_list as download_sanctions, download_all_lists as download_all_sanctions,
    search_sanctions, batch_screen, get_list_status as sanctions_status
)
from client_database import ClientDatabase, RISK_RATINGS, KYC_STATUSES, CLIENT_TYPES
from audit_trail import log_action, query_audit, verify_audit, audit_stats
from report_generator import generate_compliance_report, list_reports
from pdf_report import generate_pdf_report
from onboarding_checklist import create_onboarding, get_onboarding_status, CHECKLISTS
from risk_countries import check_country, check_nationality, get_all_lists as get_risk_lists, get_fatf_summary
from regulatory_feed import fetch_updates as fetch_reg_updates, get_unread as get_unread_articles, mark_read as mark_articles_read, get_feed_status
from compliance_calendar import get_upcoming_deadlines, load_calendar_to_workflow, get_ongoing_obligations, get_full_calendar
from str_template import generate_str, list_str_reports, get_indicators as get_str_indicators
from web_dashboard import start_dashboard, generate_static_dashboard
from gap_assessment import run_gap_assessment, list_assessments as list_gap_assessments, get_frameworks
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
            "description": "Get current XAU (gold) and XAG (silver) prices (USD/oz) from Reuters/LSEG. "
                           "Also shows the XAU/XAG ratio and checks any active price alerts.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "set_price_alert",
            "description": "Set a price alert for XAU (gold) or XAG (silver). Get emailed when price crosses your threshold.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "metal": {"type": "string", "enum": ["XAU", "XAG"], "description": "XAU (gold) or XAG (silver)"},
                    "condition": {"type": "string", "enum": ["above", "below"], "description": "Trigger when price goes above or below target"},
                    "price": {"type": "number", "description": "Target price in USD/oz"},
                    "notify": {"type": "boolean", "description": "Send email when triggered (default: true)"}
                },
                "required": ["metal", "condition", "price"]
            }
        },
        {
            "name": "list_price_alerts",
            "description": "List all active price alerts for XAU and XAG.",
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
            "description": "Get price history for XAU (gold) or XAG (silver) over a number of days.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "metal": {"type": "string", "enum": ["XAU", "XAG"], "description": "XAU (gold) or XAG (silver). Default: XAU"},
                    "days": {"type": "number", "description": "Number of days of history (default: 7)"}
                }
            }
        },

        # ── Currency exchange rate tools ─────────────────────────
        {
            "name": "check_rates",
            "description": "Get current exchange rates for AED, EUR, GBP, CHF, SAR and more. Base currency defaults to USD.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "base": {"type": "string", "description": "Base currency (default: USD)"},
                    "currencies": {"type": "string", "description": "Comma-separated target currencies (default: AED,EUR,GBP,CHF,SAR,INR,CNY)"}
                }
            }
        },
        {
            "name": "convert_currency",
            "description": "Convert an amount between currencies (e.g. 1000 AED to USD).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Amount to convert"},
                    "from": {"type": "string", "description": "Source currency code (e.g. AED)"},
                    "to": {"type": "string", "description": "Target currency code (e.g. USD)"}
                },
                "required": ["amount", "from", "to"]
            }
        },
        {
            "name": "set_rate_alert",
            "description": "Set an exchange rate alert. Get emailed when a rate crosses your threshold.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "currency": {"type": "string", "description": "Currency to watch (e.g. EUR)"},
                    "condition": {"type": "string", "enum": ["above", "below"], "description": "Trigger when rate goes above or below"},
                    "rate": {"type": "number", "description": "Target rate"},
                    "base": {"type": "string", "description": "Base currency (default: USD)"}
                },
                "required": ["currency", "condition", "rate"]
            }
        },
        {
            "name": "rate_history",
            "description": "Get exchange rate history for a currency over N days.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "currency": {"type": "string", "description": "Currency code (default: AED)"},
                    "days": {"type": "number", "description": "Number of days (default: 7)"}
                }
            }
        },

        # ── Sanctions screening tools ────────────────────────────
        {
            "name": "screen_name",
            "description": "Screen a name against UN, EU, UK, UAE, and OFAC sanctions lists. Uses fuzzy matching for transliteration variants.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name to screen"},
                    "sources": {"type": "string", "description": "Comma-separated sources to check (default: all). Options: UN,EU,UK,OFAC,UAE"}
                },
                "required": ["name"]
            }
        },
        {
            "name": "batch_screen",
            "description": "Screen multiple names at once against sanctions lists.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "names": {"type": "string", "description": "Comma-separated names to screen"}
                },
                "required": ["names"]
            }
        },
        {
            "name": "download_sanctions_lists",
            "description": "Download/update sanctions lists from official sources (UN, EU, UK, OFAC). Run this periodically to keep lists current.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Specific list to download (UN/EU/UK/OFAC/UAE) or leave empty for all"}
                }
            }
        },
        {
            "name": "sanctions_list_status",
            "description": "Check which sanctions lists are downloaded and when they were last updated.",
            "inputSchema": {"type": "object", "properties": {}}
        },

        # ── Client database tools ────────────────────────────────
        {
            "name": "add_client",
            "description": "Add a new client to the database with KYC/AML tracking. Auto-sets review date based on risk rating.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Client full name"},
                    "client_type": {"type": "string", "enum": list(CLIENT_TYPES), "description": "Client type (default: individual)"},
                    "risk_rating": {"type": "string", "enum": list(RISK_RATINGS), "description": "Risk rating (default: medium)"},
                    "kyc_status": {"type": "string", "enum": list(KYC_STATUSES), "description": "KYC status (default: pending)"},
                    "nationality": {"type": "string", "description": "Client nationality"},
                    "id_number": {"type": "string", "description": "ID/passport number"},
                    "email": {"type": "string", "description": "Client email"},
                    "phone": {"type": "string", "description": "Client phone"},
                    "notes": {"type": "string", "description": "Additional notes"},
                    "tags": {"type": "string", "description": "Comma-separated tags"}
                },
                "required": ["name"]
            }
        },
        {
            "name": "search_clients",
            "description": "Search clients by name, risk rating, KYC status, type, or tag. Use review_due=true to find clients needing KYC review.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search by name/notes/tags"},
                    "risk_rating": {"type": "string", "enum": list(RISK_RATINGS), "description": "Filter by risk"},
                    "kyc_status": {"type": "string", "enum": list(KYC_STATUSES), "description": "Filter by KYC status"},
                    "client_type": {"type": "string", "enum": list(CLIENT_TYPES), "description": "Filter by type"},
                    "review_due": {"type": "boolean", "description": "Only show clients with overdue reviews"}
                }
            }
        },
        {
            "name": "get_client",
            "description": "Get full details of a client including screening history.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string", "description": "Client ID"}
                },
                "required": ["client_id"]
            }
        },
        {
            "name": "update_client",
            "description": "Update client details (risk rating, KYC status, notes, etc.).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string", "description": "Client ID"},
                    "name": {"type": "string"},
                    "risk_rating": {"type": "string", "enum": list(RISK_RATINGS)},
                    "kyc_status": {"type": "string", "enum": list(KYC_STATUSES)},
                    "nationality": {"type": "string"},
                    "notes": {"type": "string"},
                    "tags": {"type": "string", "description": "Comma-separated tags"},
                    "review_date": {"type": "string", "description": "Next review date (ISO-8601)"}
                },
                "required": ["client_id"]
            }
        },
        {
            "name": "screen_client",
            "description": "Run a sanctions screening on an existing client and store results.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string", "description": "Client ID to screen"}
                },
                "required": ["client_id"]
            }
        },
        {
            "name": "client_reviews_due",
            "description": "List clients with overdue or upcoming KYC reviews.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "client_stats",
            "description": "Client database statistics: counts by risk, KYC status, type.",
            "inputSchema": {"type": "object", "properties": {}}
        },

        # ── Audit trail tools ────────────────────────────────────
        {
            "name": "audit_log",
            "description": "Query the audit trail. Filter by category, client, action, or date range.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter: screening, kyc, client, alert, report, sanctions, etc."},
                    "client_id": {"type": "string", "description": "Filter by client ID"},
                    "action": {"type": "string", "description": "Search in action text"},
                    "start_date": {"type": "string", "description": "Start date (ISO-8601)"},
                    "end_date": {"type": "string", "description": "End date (ISO-8601)"},
                    "limit": {"type": "number", "description": "Max entries to return (default: 50)"}
                }
            }
        },
        {
            "name": "audit_verify",
            "description": "Verify the audit trail integrity (hash chain validation). Detects tampering.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "audit_summary",
            "description": "Audit trail statistics: total entries, by category, by result.",
            "inputSchema": {"type": "object", "properties": {}}
        },

        # ── Report generator tools ───────────────────────────────
        {
            "name": "generate_report",
            "description": "Generate a full compliance dashboard report. Aggregates workflow, clients, sanctions, prices, rates, and audit data.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["text", "json", "html", "both"], "description": "Report format (default: text). 'both' generates text + HTML."}
                }
            }
        },
        {
            "name": "list_reports",
            "description": "List all previously generated compliance reports.",
            "inputSchema": {"type": "object", "properties": {}}
        },

        # ── PDF branded report tools ──────────────────────────────
        {
            "name": "generate_pdf_report",
            "description": "Generate a branded, print-ready HTML report (open in browser and Ctrl+P to save as PDF). Types: full, sanctions, kyc, aml, executive.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "report_type": {"type": "string", "enum": ["full", "sanctions", "kyc", "aml", "executive"], "description": "Report type (default: full)"},
                    "title": {"type": "string", "description": "Custom report title (optional)"},
                    "client_id": {"type": "string", "description": "Generate report for specific client"}
                }
            }
        },

        # ── Client onboarding tools ───────────────────────────────
        {
            "name": "start_onboarding",
            "description": "Start a KYC/AML onboarding checklist for a new client. Creates a project with all required steps based on client type (individual, corporate, trust, government, npo).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string", "description": "Client name"},
                    "client_type": {"type": "string", "enum": list(CHECKLISTS.keys()), "description": "Client type (default: individual)"},
                    "client_id": {"type": "string", "description": "Existing client ID (optional)"}
                },
                "required": ["client_name"]
            }
        },
        {
            "name": "onboarding_status",
            "description": "Check progress of a client onboarding (percentage complete, pending steps).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string", "description": "Client name used in onboarding"}
                },
                "required": ["client_name"]
            }
        },

        # ── Risk country tools ────────────────────────────────────
        {
            "name": "check_country_risk",
            "description": "Check if a country is on FATF blacklist/greylist or UAE high-risk list.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "country": {"type": "string", "description": "Country name or 2-letter code"}
                },
                "required": ["country"]
            }
        },
        {
            "name": "fatf_lists",
            "description": "Get all FATF blacklist, greylist, and UAE high-risk country lists.",
            "inputSchema": {"type": "object", "properties": {}}
        },

        # ── Regulatory news feed tools ────────────────────────────
        {
            "name": "fetch_regulatory_news",
            "description": "Fetch latest regulatory updates from CBUAE, FATF, UAE Ministry of Economy, and NAMLCFTC.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Specific source (CBUAE, FATF, UAE_MOE, NAMLCFTC) or leave empty for all"}
                }
            }
        },
        {
            "name": "unread_regulatory_news",
            "description": "Get unread regulatory news articles.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "mark_news_read",
            "description": "Mark regulatory news as read. Provide article_id for one, or leave empty to mark all as read.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "article_id": {"type": "string", "description": "Article ID (leave empty for all)"}
                }
            }
        },
        {
            "name": "regulatory_feed_status",
            "description": "Check regulatory news feed status and last fetch times.",
            "inputSchema": {"type": "object", "properties": {}}
        },

        # ── Compliance calendar tools ─────────────────────────────
        {
            "name": "upcoming_deadlines",
            "description": "Get upcoming UAE regulatory deadlines (CBUAE, FIU, FATF reporting dates).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "days": {"type": "number", "description": "Look-ahead days (default: 90)"}
                }
            }
        },
        {
            "name": "load_compliance_calendar",
            "description": "Create workflow reminders for all upcoming regulatory deadlines (auto-populates your workflow).",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "ongoing_obligations",
            "description": "List all ongoing compliance obligations (STR filing, sanctions freezing, record keeping, etc.).",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "full_calendar",
            "description": "Get complete compliance calendar: annual, quarterly, monthly deadlines and ongoing obligations.",
            "inputSchema": {"type": "object", "properties": {}}
        },

        # ── STR/SAR template tools ────────────────────────────────
        {
            "name": "generate_str",
            "description": "Generate a pre-filled Suspicious Transaction Report (STR/SAR) template for goAML submission.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string", "description": "Subject of the report"},
                    "client_id": {"type": "string", "description": "Client ID (auto-fills details)"},
                    "transaction_date": {"type": "string", "description": "Transaction date (ISO-8601)"},
                    "transaction_amount": {"type": "string", "description": "Transaction amount"},
                    "transaction_currency": {"type": "string", "description": "Currency (default: AED)"},
                    "transaction_type": {"type": "string", "description": "Transaction type (e.g. Wire transfer, Cash deposit)"},
                    "indicators": {"type": "string", "description": "Comma-separated suspicion indicators (e.g. structuring, sanctions_link, unusual_cash)"},
                    "narrative": {"type": "string", "description": "Narrative describing the suspicious activity"},
                    "reporting_officer": {"type": "string", "description": "Name of reporting officer"},
                    "additional_parties": {"type": "string", "description": "Additional parties involved"}
                },
                "required": ["client_name"]
            }
        },
        {
            "name": "list_str_reports",
            "description": "List all generated STR/SAR reports.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "str_indicators",
            "description": "List all available STR suspicion indicators (CBUAE categories).",
            "inputSchema": {"type": "object", "properties": {}}
        },

        # ── Web dashboard tools ───────────────────────────────────
        {
            "name": "start_web_dashboard",
            "description": "Start the auto-refreshing web compliance dashboard (opens in browser).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "port": {"type": "number", "description": "Port number (default: 8080)"}
                }
            }
        },
        {
            "name": "generate_dashboard_html",
            "description": "Generate a static HTML dashboard file (for offline viewing or sharing).",
            "inputSchema": {"type": "object", "properties": {}}
        },

        # ── Gap assessment tools ──────────────────────────────────
        {
            "name": "gap_assessment",
            "description": "Run a compliance gap assessment on a document. Analyzes text against CBUAE AML, FATF, and LBMA requirements. Identifies covered areas, partial coverage, and gaps with priority actions.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "document_text": {"type": "string", "description": "The full text content of the document to assess"},
                    "document_name": {"type": "string", "description": "Name/title of the document"},
                    "framework": {"type": "string", "enum": ["cbuae_aml", "fatf_recommendations", "lbma_rgd"], "description": "Primary framework (default: cbuae_aml)"},
                    "additional_frameworks": {"type": "string", "description": "Comma-separated additional frameworks to check (e.g. 'fatf_recommendations,lbma_rgd')"}
                },
                "required": ["document_text"]
            }
        },
        {
            "name": "list_gap_assessments",
            "description": "List all previous gap assessments with scores and gap counts.",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "compliance_frameworks",
            "description": "List available compliance frameworks for gap assessment (CBUAE AML, FATF, LBMA).",
            "inputSchema": {"type": "object", "properties": {}}
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
                xau = result["XAU"]
                xag = result["XAG"]
                lines = [
                    f"XAU (Gold):   ${xau['price']:,.2f} USD/oz",
                    f"XAG (Silver): ${xag['price']:,.2f} USD/oz",
                    f"XAU/XAG Ratio: {result['XAU_XAG_ratio']:.1f}",
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
            metal = args.get("metal", "XAU")
            days = int(args.get("days", 7))
            history = get_price_history(metal, days)
            monitor.complete("Done")
            if history:
                lines = [f"{metal} price history (last {days} days):"]
                for h in history[-20:]:  # Last 20 entries
                    lines.append(f"  {h['timestamp'][:16]} - ${h['price']:,.2f}")
                if len(history) > 20:
                    lines.insert(1, f"  (showing last 20 of {len(history)} entries)")
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, f"No price history for {metal}. Run 'check_prices' first to start tracking.")

        # ── Currency exchange handlers ────────────────────────────

        elif tool_name == "check_rates":
            monitor.start("Fetching exchange rates")
            base = args.get("base", "USD")
            currencies = [c.strip() for c in args.get("currencies", "").split(",") if c.strip()] or None
            result = fetch_rates(base, currencies)
            if "error" in result:
                _tool_result(req_id, f"Error: {result['error']}")
            else:
                lines = [f"Exchange Rates (Base: {result['base']})"]
                for curr, rate in sorted(result["rates"].items()):
                    lines.append(f"  {curr}: {rate}")
                lines.append(f"Source: {result['source']}")
                lines.append(f"Time: {result['timestamp'][:19]}")
                triggered = check_rate_alerts(result)
                if triggered:
                    lines.append("\nRATE ALERTS TRIGGERED:")
                    for a in triggered:
                        lines.append(f"  {a['base']}/{a['currency']} {a['condition']} {a['target_rate']} (now: {a['triggered_rate']})")
                _tool_result(req_id, "\n".join(lines))
            log_action("check_rates", "rate_check", details={"base": base})
            monitor.complete("Done")

        elif tool_name == "convert_currency":
            monitor.start("Converting currency")
            result = convert_currency(float(args["amount"]), args["from"], args["to"])
            monitor.complete("Done")
            if "error" in result:
                _tool_result(req_id, f"Error: {result['error']}")
            else:
                _tool_result(req_id,
                    f"{result['amount']:,.2f} {result['from']} = {result['converted']:,.2f} {result['to']}\n"
                    f"Rate: {result['rate']}\nSource: {result['source']}")

        elif tool_name == "set_rate_alert":
            monitor.start("Setting rate alert")
            alert = set_rate_alert(args["currency"], args["condition"], float(args["rate"]), args.get("base", "USD"))
            monitor.complete("Done")
            _tool_result(req_id, f"Rate alert set: {alert['base']}/{alert['currency']} {alert['condition']} {alert['target_rate']}\nID: {alert['id']}")

        elif tool_name == "rate_history":
            monitor.start("Loading rate history")
            currency = args.get("currency", "AED")
            days = int(args.get("days", 7))
            history = get_rate_history(currency, days)
            monitor.complete("Done")
            if history:
                lines = [f"{currency} rate history (last {days} days):"]
                for h in history[-20:]:
                    lines.append(f"  {h['timestamp'][:16]} - {h['rate']} (base: {h['base']})")
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, f"No rate history for {currency}. Run 'check_rates' first.")

        # ── Sanctions screening handlers ─────────────────────────

        elif tool_name == "screen_name":
            monitor.start(f"Screening: {args['name']}")
            sources = [s.strip() for s in args.get("sources", "").split(",") if s.strip()] or None
            result = search_sanctions(args["name"], sources)
            log_action(f"Screen: {args['name']}", "screening", details={"matches": result["total_matches"]})
            monitor.complete(f"Found {result['total_matches']} matches")
            if result["total_matches"] > 0:
                lines = [f"MATCHES FOUND: {result['total_matches']} for '{args['name']}'"]
                for m in result["matches"]:
                    lines.append(f"  [{m['source']}] {m['name']} (score: {m['match_score']}, type: {m['type']})")
                    if m.get("alias_matched"):
                        lines.append(f"    Alias matched: {m['alias_matched']}")
                _tool_result(req_id, "\n".join(lines))
            else:
                checked = ", ".join(s["source"] for s in result["sources_checked"])
                _tool_result(req_id, f"CLEAR: No matches found for '{args['name']}'\nSources checked: {checked}")

        elif tool_name == "batch_screen":
            monitor.start("Batch screening")
            names = [n.strip() for n in args["names"].split(",") if n.strip()]
            result = batch_screen(names)
            log_action(f"Batch screen: {len(names)} names", "screening", details={"flagged": result["total_flagged"]})
            monitor.complete(f"Screened {result['total_screened']}, flagged {result['total_flagged']}")
            lines = [f"Screened: {result['total_screened']} | Flagged: {result['total_flagged']}"]
            if result["flagged"]:
                lines.append("\nFLAGGED:")
                for f in result["flagged"]:
                    lines.append(f"  {f['name']} - {f['matches']} match(es)")
            if result["clean"]:
                lines.append(f"\nCLEAR: {', '.join(result['clean'])}")
            _tool_result(req_id, "\n".join(lines))

        elif tool_name == "download_sanctions_lists":
            source = args.get("source", "").strip()
            if source:
                monitor.start(f"Downloading {source} sanctions list")
                result = download_sanctions(source.upper())
                monitor.complete("Done")
                if "error" in result:
                    _tool_result(req_id, f"Error: {result['error']}")
                else:
                    _tool_result(req_id, f"Downloaded: {result['name']}\nEntries: {result.get('count', 0)}\nUpdated: {result.get('updated_at', '')}")
            else:
                monitor.start("Downloading all sanctions lists")
                results = download_all_sanctions()
                monitor.complete("Done")
                lines = ["Sanctions lists update:"]
                for key, r in results.items():
                    if "error" in r:
                        lines.append(f"  {key}: ERROR - {r['error']}")
                    else:
                        lines.append(f"  {key}: {r.get('count', 0)} entries ({r.get('name', '')})")
                _tool_result(req_id, "\n".join(lines))
            log_action("Download sanctions lists", "sanctions")

        elif tool_name == "sanctions_list_status":
            monitor.start("Checking sanctions lists")
            status = sanctions_status()
            monitor.complete("Done")
            lines = ["Sanctions Lists Status:"]
            for key, info in status.items():
                if info.get("downloaded"):
                    lines.append(f"  {key}: {info['entries']} entries (updated: {info['updated_at'][:16]})")
                else:
                    lines.append(f"  {key}: Not downloaded")
            _tool_result(req_id, "\n".join(lines))

        # ── Client database handlers ─────────────────────────────

        elif tool_name == "add_client":
            monitor.start("Adding client")
            db = ClientDatabase()
            tags = [t.strip() for t in args.get("tags", "").split(",") if t.strip()] if args.get("tags") else None
            client = db.add_client(
                name=args["name"],
                client_type=args.get("client_type", "individual"),
                risk_rating=args.get("risk_rating", "medium"),
                kyc_status=args.get("kyc_status", "pending"),
                nationality=args.get("nationality", ""),
                id_number=args.get("id_number", ""),
                email=args.get("email", ""),
                phone=args.get("phone", ""),
                notes=args.get("notes", ""),
                tags=tags,
            )
            log_action(f"Add client: {args['name']}", "client", client_id=client["id"])
            monitor.complete(f"Client {client['id']} added")
            _tool_result(req_id, json.dumps(client, indent=2))

        elif tool_name == "search_clients":
            monitor.start("Searching clients")
            db = ClientDatabase()
            clients = db.search_clients(
                query=args.get("query"),
                risk_rating=args.get("risk_rating"),
                kyc_status=args.get("kyc_status"),
                client_type=args.get("client_type"),
                review_due=args.get("review_due", False),
            )
            monitor.complete(f"Found {len(clients)} clients")
            if clients:
                lines = []
                for c in clients:
                    lines.append(f"[{c['id']}] {c['name']} | {c['risk_rating']:10s} | KYC: {c['kyc_status']} | Review: {(c.get('review_date') or 'N/A')[:10]}")
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, "No clients found.")

        elif tool_name == "get_client":
            monitor.start("Loading client")
            db = ClientDatabase()
            client = db.get_client(args["client_id"])
            monitor.complete("Done")
            _tool_result(req_id, json.dumps(client, indent=2) if client else f"Client not found: {args['client_id']}")

        elif tool_name == "update_client":
            monitor.start("Updating client")
            db = ClientDatabase()
            updates = {}
            for field in ("name", "risk_rating", "kyc_status", "nationality", "notes", "review_date"):
                if field in args:
                    updates[field] = args[field]
            if "tags" in args:
                updates["tags"] = [t.strip() for t in args["tags"].split(",") if t.strip()]
            client = db.update_client(args["client_id"], updates)
            log_action(f"Update client", "client", client_id=args["client_id"], details=updates)
            monitor.complete("Done")
            _tool_result(req_id, json.dumps(client, indent=2))

        elif tool_name == "screen_client":
            monitor.start("Screening client")
            db = ClientDatabase()
            client = db.get_client(args["client_id"])
            if not client:
                send_error(req_id, -32602, f"Client not found: {args['client_id']}")
                return
            result = search_sanctions(client["name"])
            db.add_screening_result(args["client_id"], result)
            log_action(f"Screen client: {client['name']}", "screening", client_id=args["client_id"],
                       details={"matches": result["total_matches"]})
            monitor.complete(f"{result['total_matches']} matches")
            if result["total_matches"] > 0:
                lines = [f"MATCHES for {client['name']}: {result['total_matches']}"]
                for m in result["matches"]:
                    lines.append(f"  [{m['source']}] {m['name']} (score: {m['match_score']})")
                lines.append("\nClient risk rating auto-updated to HIGH. KYC set to UNDER_REVIEW.")
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, f"CLEAR: {client['name']} - no sanctions matches found.")

        elif tool_name == "client_reviews_due":
            monitor.start("Checking client reviews")
            db = ClientDatabase()
            reviews = db.get_review_due()
            monitor.complete("Done")
            parts = []
            if reviews["overdue"]:
                lines = [f"OVERDUE REVIEWS ({len(reviews['overdue'])}):" ]
                for c in reviews["overdue"]:
                    lines.append(f"  [{c['id']}] {c['name']} | Risk: {c['risk_rating']} | Due: {(c.get('review_date') or '')[:10]}")
                parts.append("\n".join(lines))
            if reviews["upcoming"]:
                lines = [f"UPCOMING REVIEWS ({len(reviews['upcoming'])}):" ]
                for c in reviews["upcoming"]:
                    lines.append(f"  [{c['id']}] {c['name']} | Risk: {c['risk_rating']} | Due: {(c.get('review_date') or '')[:10]}")
                parts.append("\n".join(lines))
            if not parts:
                parts.append("No reviews due.")
            _tool_result(req_id, "\n\n".join(parts))

        elif tool_name == "client_stats":
            monitor.start("Loading client stats")
            db = ClientDatabase()
            stats = db.get_stats()
            monitor.complete("Done")
            _tool_result(req_id, json.dumps(stats, indent=2))

        # ── Audit trail handlers ─────────────────────────────────

        elif tool_name == "audit_log":
            monitor.start("Querying audit trail")
            entries = query_audit(
                category=args.get("category"),
                client_id=args.get("client_id"),
                action=args.get("action"),
                start_date=args.get("start_date"),
                end_date=args.get("end_date"),
                limit=int(args.get("limit", 50)),
            )
            monitor.complete(f"Found {len(entries)} entries")
            if entries:
                lines = []
                for e in entries:
                    lines.append(f"[{e['id']}] {e['timestamp'][:19]} | {e['category']:12s} | {e['action']}")
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, "No audit entries found.")

        elif tool_name == "audit_verify":
            monitor.start("Verifying audit trail integrity")
            result = verify_audit()
            monitor.complete("Done")
            if result["valid"]:
                _tool_result(req_id, f"INTEGRITY OK: {result['entries_checked']} entries verified. Hash chain intact.")
            else:
                _tool_result(req_id, f"INTEGRITY FAILED: {len(result['errors'])} error(s) found.\n" + json.dumps(result["errors"], indent=2))

        elif tool_name == "audit_summary":
            monitor.start("Loading audit stats")
            stats = audit_stats()
            monitor.complete("Done")
            _tool_result(req_id, json.dumps(stats, indent=2))

        # ── Report generator handlers ────────────────────────────

        elif tool_name == "generate_report":
            fmt = args.get("format", "text")
            monitor.start(f"Generating {fmt} report")
            report = generate_compliance_report(fmt)
            log_action("Generate compliance report", "report", details={"format": fmt})
            monitor.complete("Done")
            if fmt == "json":
                _tool_result(req_id, json.dumps(report, indent=2))
            else:
                text = report.get("text", json.dumps(report["sections"], indent=2))
                paths = []
                if report.get("json_path"):
                    paths.append(f"JSON: {report['json_path']}")
                if report.get("text_path"):
                    paths.append(f"Text: {report['text_path']}")
                if report.get("html_path"):
                    paths.append(f"HTML: {report['html_path']}")
                _tool_result(req_id, text + "\n\nSaved to:\n" + "\n".join(paths))

        elif tool_name == "list_reports":
            monitor.start("Listing reports")
            reports = list_reports()
            monitor.complete("Done")
            if reports:
                lines = ["Generated reports:"]
                for r in reports[:20]:
                    lines.append(f"  [{r['report_id']}] {r['title']} ({r['generated_at'][:16]})")
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, "No reports generated yet. Use 'generate_report' to create one.")

        # ── PDF branded report handlers ───────────────────────────

        elif tool_name == "generate_pdf_report":
            report_type = args.get("report_type", "full")
            monitor.start(f"Generating {report_type} PDF report")
            result = generate_pdf_report(
                report_type=report_type,
                prepared_by=args.get("title", "Compliance Department"),
            )
            log_action(f"PDF report generated: {report_type}", "report", details={"type": report_type})
            monitor.complete("Done")
            _tool_result(req_id,
                f"PDF report generated: {result['type']}\n"
                f"Path: {result['html_path']}\n\n"
                f"Open in browser and use Ctrl+P (or Cmd+P) to save as PDF.\n"
                f"The report includes Finegold LLC branding and is print-optimized.")

        # ── Client onboarding handlers ────────────────────────────

        elif tool_name == "start_onboarding":
            monitor.start(f"Creating onboarding for {args['client_name']}")
            result = create_onboarding(
                client_name=args["client_name"],
                client_type=args.get("client_type", "individual"),
                client_id=args.get("client_id"),
            )
            project_id = result["project"]["id"]
            log_action(f"Onboarding started: {args['client_name']}", "kyc",
                       client_id=args.get("client_id"), details={"project_id": project_id})
            monitor.complete("Done")
            _tool_result(req_id,
                f"Onboarding project created: {project_id}\n"
                f"Client: {result['client_name']} ({result['client_type']})\n"
                f"Total steps: {result['total_steps']}\n"
                f"Due: {result['due_date'][:10]}\n\n"
                f"Use 'list_items' with tag 'onboarding' to see all steps.\n"
                f"Complete each step with 'complete_item'.")

        elif tool_name == "onboarding_status":
            monitor.start("Checking onboarding progress")
            result = get_onboarding_status(args["client_name"])
            monitor.complete("Done")
            lines = [
                f"Onboarding: {result['client_name']}",
                f"Progress: {result['progress_pct']:.0f}% ({result['completed']}/{result['total_steps']})",
                f"Pending: {result['pending']} | Overdue: {result['overdue']}",
            ]
            pending_items = [i for i in result.get("items", []) if i["status"] in ("pending", "in_progress")]
            if pending_items:
                lines.append(f"\nPending steps ({len(pending_items)}):")
                for s in pending_items[:10]:
                    lines.append(f"  [{s['id']}] {s['title']}")
            _tool_result(req_id, "\n".join(lines))

        # ── Risk country handlers ─────────────────────────────────

        elif tool_name == "check_country_risk":
            monitor.start(f"Checking: {args['country']}")
            result = check_country(args["country"])
            monitor.complete("Done")
            if result["risk_level"] == "standard":
                _tool_result(req_id, f"{args['country']}: STANDARD RISK - not on any FATF or UAE high-risk list.")
            else:
                lines = [f"{args['country']}: {result['risk_level'].upper()} RISK"]
                if result["blacklisted"]:
                    lines.append("  FATF BLACKLISTED - Call for Action (counter-measures required)")
                if result["greylisted"]:
                    lines.append("  FATF GREYLISTED - Under Increased Monitoring (EDD required)")
                if result["uae_high_risk"]:
                    lines.append("  UAE/CBUAE HIGH RISK")
                for d in result["details"]:
                    lines.append(f"  List: {d['list']} | Since: {d.get('since', '')} | {d.get('reason', '')}")
                _tool_result(req_id, "\n".join(lines))

        elif tool_name == "fatf_lists":
            monitor.start("Loading FATF lists")
            summary = get_fatf_summary()
            lists = get_risk_lists()
            monitor.complete("Done")
            lines = [
                f"FATF Risk Countries (Updated: {summary['last_updated']})",
                f"Total high-risk: {summary['total']}",
                f"\nBLACKLIST ({summary['blacklist_count']}) - Call for Action:",
            ]
            for c in lists["blacklist"]:
                lines.append(f"  {c['country']} ({c['code']}) - {c.get('reason', '')}")
            lines.append(f"\nGREYLIST ({summary['greylist_count']}) - Increased Monitoring:")
            for c in lists["greylist"]:
                lines.append(f"  {c['country']} ({c['code']}) - since {c.get('since', '')}")
            lines.append(f"\nUAE/CBUAE Additional ({summary['uae_additional_count']}):")
            for c in lists["uae_high_risk"]:
                lines.append(f"  {c['country']} ({c['code']}) - {c.get('reason', '')}")
            _tool_result(req_id, "\n".join(lines))

        # ── Regulatory feed handlers ──────────────────────────────

        elif tool_name == "fetch_regulatory_news":
            source = args.get("source")
            monitor.start(f"Fetching regulatory news{(' from ' + source) if source else ''}")
            result = fetch_reg_updates(source)
            monitor.complete("Done")
            lines = [f"New articles: {result['new_articles']} | Total: {result['total_articles']}"]
            if result.get("errors"):
                lines.append(f"Errors: {', '.join(result['errors'])}")
            if result.get("articles"):
                lines.append("\nLatest articles:")
                for a in result["articles"][:10]:
                    lines.append(f"  [{a['id']}] [{a.get('source', '')}] {a['title']}")
            _tool_result(req_id, "\n".join(lines))

        elif tool_name == "unread_regulatory_news":
            monitor.start("Loading unread news")
            articles = get_unread_articles()
            monitor.complete("Done")
            if articles:
                lines = [f"Unread regulatory news ({len(articles)}):"]
                for a in articles[:20]:
                    lines.append(f"  [{a['id']}] [{a.get('source', '')}] {a['title']}")
                    if a.get("link"):
                        lines.append(f"    {a['link']}")
                if len(articles) > 20:
                    lines.append(f"  ... and {len(articles) - 20} more")
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, "No unread regulatory news. Use 'fetch_regulatory_news' to check for updates.")

        elif tool_name == "mark_news_read":
            monitor.start("Marking as read")
            article_id = args.get("article_id")
            count = mark_articles_read(article_id if article_id else None)
            monitor.complete("Done")
            _tool_result(req_id, f"Marked {count} article(s) as read.")

        elif tool_name == "regulatory_feed_status":
            monitor.start("Checking feed status")
            status = get_feed_status()
            monitor.complete("Done")
            lines = [
                f"Total articles: {status['total_articles']}",
                f"Unread: {status['unread']}",
                "\nSources:",
            ]
            for key, name in status.get("sources", {}).items():
                last = status.get("last_fetch", {}).get(key, "never")
                if last != "never":
                    last = last[:16]
                lines.append(f"  {key}: {name} (last fetch: {last})")
            _tool_result(req_id, "\n".join(lines))

        # ── Compliance calendar handlers ──────────────────────────

        elif tool_name == "upcoming_deadlines":
            days = int(args.get("days", 90))
            monitor.start(f"Loading deadlines ({days} days)")
            deadlines = get_upcoming_deadlines(days)
            monitor.complete("Done")
            if deadlines:
                lines = [f"Upcoming regulatory deadlines ({len(deadlines)} in next {days} days):"]
                for d in deadlines:
                    lines.append(
                        f"  [{d['authority']}] {d['title']}\n"
                        f"    Due: {d['due'][:10]} ({d['days_until']} days) | Priority: {d['priority']} | {d['recurrence']}"
                    )
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, f"No deadlines in the next {days} days.")

        elif tool_name == "load_compliance_calendar":
            monitor.start("Loading calendar to workflow")
            result = load_calendar_to_workflow()
            log_action("Compliance calendar loaded", "calendar", details={"new_items": result["new_items_created"]})
            monitor.complete("Done")
            _tool_result(req_id,
                f"Compliance calendar loaded.\n"
                f"Total deadlines found: {result['total_deadlines']}\n"
                f"New workflow items created: {result['new_items_created']}")

        elif tool_name == "ongoing_obligations":
            monitor.start("Loading obligations")
            obligations = get_ongoing_obligations()
            monitor.complete("Done")
            lines = [f"Ongoing compliance obligations ({len(obligations)}):"]
            for o in obligations:
                lines.append(f"  [{o['priority'].upper()}] {o['title']} (Authority: {o['authority']})")
            _tool_result(req_id, "\n".join(lines))

        elif tool_name == "full_calendar":
            monitor.start("Loading full calendar")
            cal = get_full_calendar()
            monitor.complete("Done")
            _tool_result(req_id, json.dumps(cal, indent=2, default=str))

        # ── STR/SAR template handlers ─────────────────────────────

        elif tool_name == "generate_str":
            monitor.start(f"Generating STR for {args['client_name']}")
            result = generate_str(
                client_name=args["client_name"],
                client_id=args.get("client_id", ""),
                transaction_date=args.get("transaction_date", ""),
                transaction_amount=args.get("transaction_amount", ""),
                transaction_currency=args.get("transaction_currency", "AED"),
                transaction_type=args.get("transaction_type", ""),
                indicators=args.get("indicators", ""),
                narrative=args.get("narrative", ""),
                reporting_officer=args.get("reporting_officer", ""),
                additional_parties=args.get("additional_parties", ""),
            )
            monitor.complete("Done")
            lines = [
                f"STR generated: {result['str_id']}",
                f"JSON: {result['json_path']}",
                f"Text: {result['text_path']}",
                "",
                "IMPORTANT: Review and submit via goAML portal within 24 hours of suspicion.",
            ]
            _tool_result(req_id, "\n".join(lines))

        elif tool_name == "list_str_reports":
            monitor.start("Listing STR reports")
            reports = list_str_reports()
            monitor.complete("Done")
            if reports:
                lines = [f"STR/SAR Reports ({len(reports)}):"]
                for r in reports:
                    lines.append(f"  [{r['str_id']}] {r['client']} | Status: {r['status']} | {r['created_at'][:16]}")
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, "No STR reports generated yet.")

        elif tool_name == "str_indicators":
            monitor.start("Loading indicators")
            indicators = get_str_indicators()
            monitor.complete("Done")
            lines = ["STR Suspicion Indicators (CBUAE categories):"]
            for code, desc in indicators.items():
                lines.append(f"  {code}: {desc}")
            _tool_result(req_id, "\n".join(lines))

        # ── Web dashboard handlers ────────────────────────────────

        elif tool_name == "start_web_dashboard":
            port = int(args.get("port", 8080))
            monitor.start(f"Starting dashboard on port {port}")
            result = start_dashboard(port)
            monitor.complete("Done")
            _tool_result(req_id, f"{result}\nOpen in your browser to view the auto-refreshing compliance dashboard.")

        elif tool_name == "generate_dashboard_html":
            monitor.start("Generating static dashboard")
            path = generate_static_dashboard()
            monitor.complete("Done")
            _tool_result(req_id, f"Static dashboard generated: {path}\nOpen in browser to view.")

        # ── Gap assessment handlers ───────────────────────────────

        elif tool_name == "gap_assessment":
            doc_name = args.get("document_name", "Uploaded Document")
            monitor.start(f"Assessing: {doc_name}")
            result = run_gap_assessment(
                document_text=args["document_text"],
                document_name=doc_name,
                framework=args.get("framework", "cbuae_aml"),
                additional_frameworks=args.get("additional_frameworks", ""),
            )
            monitor.complete("Done")
            lines = [
                f"Gap Assessment: {result['assessment_id']}",
                f"Document: {doc_name}",
                f"Overall Score: {result['overall_score']}%",
                f"",
                f"Summary: {result['summary']['covered']} covered | {result['summary']['partial']} partial | {result['summary']['gaps']} gaps",
                f"",
            ]
            for fw_key, fw_res in result["results"].items():
                lines.append(f"--- {fw_res['framework']} ---")
                for req in fw_res["requirements"]:
                    icon = "OK" if req["status"] == "covered" else "PARTIAL" if req["status"] == "partial" else "GAP"
                    lines.append(f"  [{icon}] {req['id']}: {req['title']} ({req['coverage_score']}%)")
                lines.append("")

            if result.get("priority_actions"):
                lines.append("PRIORITY ACTIONS:")
                for a in result["priority_actions"][:10]:
                    lines.append(f"  [{a['priority'].upper()}] {a['requirement']}: {a['action']}")

            lines.append(f"\nSaved: {result.get('path', '')}")
            _tool_result(req_id, "\n".join(lines))

        elif tool_name == "list_gap_assessments":
            monitor.start("Listing assessments")
            assessments = list_gap_assessments()
            monitor.complete("Done")
            if assessments:
                lines = [f"Gap Assessments ({len(assessments)}):"]
                for a in assessments[:20]:
                    lines.append(
                        f"  [{a['assessment_id']}] {a['document_name']} | "
                        f"Score: {a['overall_score']}% | Gaps: {a['gaps']} | {a['assessed_at'][:16]}"
                    )
                _tool_result(req_id, "\n".join(lines))
            else:
                _tool_result(req_id, "No gap assessments yet. Use 'gap_assessment' to analyze a document.")

        elif tool_name == "compliance_frameworks":
            monitor.start("Loading frameworks")
            frameworks = get_frameworks()
            monitor.complete("Done")
            lines = ["Available compliance frameworks:"]
            for key, fw in frameworks.items():
                lines.append(f"  {key}: {fw['name']} ({fw['authority']}) - {fw['requirements']} requirements")
            _tool_result(req_id, "\n".join(lines))

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
