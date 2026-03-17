#!/usr/bin/env python3
"""
NotebookLM MCP Server
Exposes NotebookLM capabilities as MCP tools:
  - query_notebook: Ask a question to a specific notebook
  - list_notebooks: List all notebooks in the library
  - add_notebook: Add a new notebook to the library
  - get_notebook: Get notebook details by ID or name
  - trigger_action: Trigger named actions (summarize, key-points, etc.)

Run via stdio (MCP protocol):
  python scripts/mcp_server.py
"""

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from notebook_manager import NotebookLibrary
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
