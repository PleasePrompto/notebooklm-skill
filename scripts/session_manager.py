#!/usr/bin/env python3
"""
Persistent session manager for NotebookLM.

This module keeps a long-lived background process alive so multiple CLI
invocations can reuse the same Playwright + BrowserContext + Page objects.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from patchright.sync_api import sync_playwright

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from browser_session import BrowserSession
from config import DATA_DIR, QUERY_TIMEOUT_SECONDS
from notebook_navigation import normalize_notebooklm_url


SESSIONS_FILE = DATA_DIR / "sessions.json"
SESSIONS_LOCK_FILE = DATA_DIR / "sessions.lock"
RUNTIME_DIR = DATA_DIR / "session_runtime"
SOCKET_FILE = RUNTIME_DIR / "session_manager.sock"
PID_FILE = RUNTIME_DIR / "session_manager.pid"
DEFAULT_IDLE_TIMEOUT_SECONDS = int(os.getenv("NOTEBOOKLM_SESSION_IDLE_TIMEOUT", "1800"))
DEFAULT_CLIENT_TIMEOUT_SECONDS = max(QUERY_TIMEOUT_SECONDS + 90, 210)
DAEMON_START_TIMEOUT_SECONDS = 12
ACTIVE_STATUSES = {"active", "busy"}
TERMINAL_STATUSES = {"closed", "expired", "orphaned", "error"}


class SessionManagerError(RuntimeError):
    """Raised when a session manager command fails."""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class SessionMetadataStore:
    """Persists serializable session metadata to data/sessions.json."""

    def __init__(self, path: Path = SESSIONS_FILE):
        self.path = path
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _default_state(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "updated_at": utcnow_iso(),
            "daemon": {
                "pid": None,
                "started_at": None,
                "socket": str(SOCKET_FILE),
                "idle_timeout_seconds": DEFAULT_IDLE_TIMEOUT_SECONDS,
                "status": "stopped",
            },
            "sessions": {},
        }

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._default_state()

        with file_lock(SESSIONS_LOCK_FILE):
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                return self._default_state()

        if not isinstance(data, dict):
            return self._default_state()
        data.setdefault("version", 1)
        data.setdefault("updated_at", utcnow_iso())
        data.setdefault("daemon", self._default_state()["daemon"])
        data.setdefault("sessions", {})
        return data

    def save(self, data: Dict[str, Any]):
        data["updated_at"] = utcnow_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(SESSIONS_LOCK_FILE):
            with tempfile.NamedTemporaryFile("w", delete=False, dir=str(self.path.parent), encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
                tmp_path = Path(handle.name)
            os.replace(tmp_path, self.path)

    def list_sessions(self) -> List[Dict[str, Any]]:
        data = self.load()
        sessions = list(data.get("sessions", {}).values())
        sessions.sort(key=lambda item: item.get("last_activity", ""), reverse=True)
        return sessions

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        data = self.load()
        return data.get("sessions", {}).get(session_id)

    def upsert_session(self, session: Dict[str, Any]):
        data = self.load()
        data["sessions"][session["session_id"]] = session
        self.save(data)

    def update_session(self, session_id: str, **updates):
        data = self.load()
        session = data.get("sessions", {}).get(session_id)
        if not session:
            return None
        session.update(updates)
        data["sessions"][session_id] = session
        self.save(data)
        return session

    def set_daemon(self, *, pid: Optional[int], started_at: Optional[str], status: str, idle_timeout_seconds: int):
        data = self.load()
        data["daemon"] = {
            "pid": pid,
            "started_at": started_at,
            "socket": str(SOCKET_FILE),
            "idle_timeout_seconds": idle_timeout_seconds,
            "status": status,
        }
        self.save(data)

    def mark_runtime_sessions_orphaned(self, reason: str = "session daemon is not running anymore") -> int:
        data = self.load()
        changed = 0
        for session in data.get("sessions", {}).values():
            if session.get("status") in ACTIVE_STATUSES:
                session["status"] = "orphaned"
                session["last_error"] = reason
                changed += 1
        if changed:
            daemon = data.get("daemon", {})
            daemon["status"] = "stopped"
            daemon["pid"] = None
            data["daemon"] = daemon
            self.save(data)
        return changed


class SessionManagerClient:
    """Client for sending commands to the background daemon."""

    def __init__(self, socket_path: Path = SOCKET_FILE):
        self.socket_path = socket_path
        self.store = SessionMetadataStore()

    def is_daemon_running(self) -> bool:
        if not self.socket_path.exists():
            return False
        try:
            self._send({"command": "ping"}, timeout_seconds=5)
            return True
        except Exception:
            return False

    def reconcile_runtime_state(self) -> int:
        if self.is_daemon_running():
            return 0
        self._cleanup_stale_runtime_files()
        return self.store.mark_runtime_sessions_orphaned()

    def ensure_daemon(self):
        if self.is_daemon_running():
            return

        self._cleanup_stale_runtime_files()

        cmd = [sys.executable, str(Path(__file__).resolve()), "_serve"]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(Path(__file__).parent.parent),
        )

        deadline = time.time() + DAEMON_START_TIMEOUT_SECONDS
        last_error = None
        while time.time() < deadline:
            try:
                if self.is_daemon_running():
                    return
            except Exception as error:
                last_error = error
            time.sleep(0.2)

        raise SessionManagerError(
            f"Failed to start session daemon within {DAEMON_START_TIMEOUT_SECONDS}s"
            + (f": {last_error}" if last_error else "")
        )

    def request(self, command: str, *, auto_start: bool = False, timeout_seconds: Optional[int] = None, **payload) -> Dict[str, Any]:
        if auto_start:
            self.ensure_daemon()
        else:
            self.reconcile_runtime_state()
            if not self.is_daemon_running():
                raise SessionManagerError("Session daemon is not running")

        request = {"command": command, **payload}
        response = self._send(request, timeout_seconds=timeout_seconds or DEFAULT_CLIENT_TIMEOUT_SECONDS)
        if not response.get("ok"):
            raise SessionManagerError(response.get("error", "Unknown session manager error"))
        return response["result"]

    def _cleanup_stale_runtime_files(self):
        if SOCKET_FILE.exists():
            try:
                SOCKET_FILE.unlink()
            except OSError:
                pass
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except OSError:
                pass

    def _send(self, request: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_seconds)
            sock.connect(str(self.socket_path))
            payload = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
            sock.sendall(payload)
            sock.shutdown(socket.SHUT_WR)

            chunks: List[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)

        raw = b"".join(chunks).decode("utf-8").strip()
        if not raw:
            raise SessionManagerError("Empty response from session daemon")
        return json.loads(raw)


def ask_via_session_manager(session_id: str, question: str) -> Dict[str, Any]:
    """Public helper for ask_question.py."""
    client = SessionManagerClient()
    return client.request(
        "ask",
        session_id=session_id,
        question=question,
        timeout_seconds=DEFAULT_CLIENT_TIMEOUT_SECONDS,
    )


class NotebookSessionDaemon:
    """Long-lived process that keeps Playwright + BrowserContext alive."""

    def __init__(self, idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS):
        self.idle_timeout_seconds = idle_timeout_seconds
        self.store = SessionMetadataStore()
        self.auth = AuthManager()
        self.playwright = None
        self.context = None
        self.sessions: Dict[str, BrowserSession] = {}
        self.running = True
        self.started_at = utcnow_iso()
        self.pid = os.getpid()
        self.preferred_email = self.auth.get_auth_info().get("google_account_email")

    def run(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

        self.store.mark_runtime_sessions_orphaned("session daemon restarted before live sessions could be reused")
        self.store.set_daemon(
            pid=self.pid,
            started_at=self.started_at,
            status="running",
            idle_timeout_seconds=self.idle_timeout_seconds,
        )

        self._install_signal_handlers()
        atexit.register(self._cleanup_runtime_files)

        if SOCKET_FILE.exists():
            SOCKET_FILE.unlink()

        with open(PID_FILE, "w", encoding="utf-8") as handle:
            handle.write(str(self.pid))

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(SOCKET_FILE))
            os.chmod(SOCKET_FILE, 0o600)
            server.listen(16)
            server.settimeout(1.0)

            while self.running:
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    self.gc_sessions()
                    continue
                except KeyboardInterrupt:
                    break

                with conn:
                    response = self._handle_connection(conn)
                    conn.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))

        self.shutdown()

    def _handle_connection(self, conn: socket.socket) -> Dict[str, Any]:
        chunks: List[bytes] = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks).decode("utf-8").strip()
        if not raw:
            return {"ok": False, "error": "Empty request"}

        try:
            request = json.loads(raw)
            result = self._dispatch(request)
            return {"ok": True, "result": result}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    def _dispatch(self, request: Dict[str, Any]) -> Dict[str, Any]:
        command = request.get("command")

        if command == "ping":
            return {
                "status": "ok",
                "pid": self.pid,
                "started_at": self.started_at,
                "session_count": len(self.sessions),
                "idle_timeout_seconds": self.idle_timeout_seconds,
            }
        if command == "create":
            notebook_url = request.get("notebook_url")
            if not notebook_url:
                raise SessionManagerError("Missing notebook_url")
            return self.create_session(notebook_url)
        if command == "ask":
            return self.ask_session(request.get("session_id"), request.get("question"))
        if command == "list":
            return self.list_sessions()
        if command == "info":
            return self.info_session(request.get("session_id"))
        if command == "reset":
            return self.reset_session(request.get("session_id"))
        if command == "close":
            return self.close_session(request.get("session_id"), reason="closed")
        if command == "gc":
            return self.gc_sessions()

        raise SessionManagerError(f"Unsupported command: {command}")

    def _install_signal_handlers(self):
        def handle_signal(signum, _frame):
            self.running = False

        for signum in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(signum, handle_signal)
            except Exception:
                pass

    def _cleanup_runtime_files(self):
        for path in (SOCKET_FILE, PID_FILE):
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass

    def _ensure_browser(self):
        if self.context is not None:
            return
        if not self.auth.is_authenticated():
            raise SessionManagerError("NotebookLM authentication is missing. Run: python scripts/run.py auth_manager.py setup")

        self.playwright = sync_playwright().start()
        from browser_utils import BrowserFactory  # local import to avoid import cycles during daemon spawn

        self.context = BrowserFactory.launch_persistent_context(
            self.playwright,
            headless=True,
        )
        self.preferred_email = self.auth.get_auth_info().get("google_account_email")

    def _build_metadata(self, session: BrowserSession, *, status: str, last_error: Optional[str] = None) -> Dict[str, Any]:
        return {
            "session_id": session.id,
            "notebook_url": session.notebook_url,
            "created_at": datetime.fromtimestamp(session.created_at, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "last_activity": datetime.fromtimestamp(session.last_activity, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "message_count": session.message_count,
            "status": status,
            "last_error": last_error,
            "daemon_pid": self.pid,
            "idle_timeout_seconds": self.idle_timeout_seconds,
        }

    def _get_live_session(self, session_id: Optional[str]) -> BrowserSession:
        if not session_id:
            raise SessionManagerError("Missing session_id")
        session = self.sessions.get(session_id)
        if session is None:
            metadata = self.store.get_session(session_id)
            if metadata and metadata.get("status") == "orphaned":
                raise SessionManagerError(
                    "Session exists in metadata but its live browser process is gone. Create a new session instead."
                )
            raise SessionManagerError(f"Live session not found: {session_id}")
        return session

    def create_session(self, notebook_url: str) -> Dict[str, Any]:
        self.gc_sessions()
        self._ensure_browser()

        session_id = f"session-{uuid.uuid4().hex[:12]}"
        normalized_url = normalize_notebooklm_url(notebook_url)
        session = BrowserSession(
            session_id=session_id,
            context=self.context,
            notebook_url=normalized_url,
            preferred_email=self.preferred_email,
        )
        self.sessions[session_id] = session
        metadata = self._build_metadata(session, status="active")
        self.store.upsert_session(metadata)
        return metadata

    def ask_session(self, session_id: Optional[str], question: Optional[str]) -> Dict[str, Any]:
        if not question:
            raise SessionManagerError("Missing question")
        session = self._get_live_session(session_id)

        self.store.update_session(session.id, status="busy", last_error=None)
        result = session.ask(question)
        if result.get("status") != "success":
            error_message = result.get("error", "Unknown NotebookLM error")
            self.store.update_session(
                session.id,
                status="active",
                last_error=error_message,
                last_activity=datetime.fromtimestamp(session.last_activity, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                message_count=session.message_count,
            )
            raise SessionManagerError(error_message)

        metadata = self._build_metadata(session, status="active")
        self.store.upsert_session(metadata)
        return {
            **metadata,
            "question": question,
            "answer": result["answer"],
        }

    def list_sessions(self) -> Dict[str, Any]:
        self.gc_sessions()
        sessions = []
        for record in self.store.list_sessions():
            record = dict(record)
            record["live"] = record.get("session_id") in self.sessions
            sessions.append(record)
        return {
            "count": len(sessions),
            "sessions": sessions,
            "daemon_pid": self.pid,
            "idle_timeout_seconds": self.idle_timeout_seconds,
        }

    def info_session(self, session_id: Optional[str]) -> Dict[str, Any]:
        if not session_id:
            raise SessionManagerError("Missing session_id")
        self.gc_sessions()
        record = self.store.get_session(session_id)
        if not record:
            raise SessionManagerError(f"Session not found: {session_id}")
        record = dict(record)
        record["live"] = session_id in self.sessions
        return record

    def reset_session(self, session_id: Optional[str]) -> Dict[str, Any]:
        session = self._get_live_session(session_id)
        notebook_url = session.notebook_url
        created_at = session.created_at
        session.close()

        replacement = BrowserSession(
            session_id=session.id,
            context=self.context,
            notebook_url=notebook_url,
            preferred_email=self.preferred_email,
        )
        replacement.created_at = created_at
        self.sessions[session.id] = replacement
        metadata = self._build_metadata(replacement, status="active")
        self.store.upsert_session(metadata)
        return metadata

    def close_session(self, session_id: Optional[str], *, reason: str) -> Dict[str, Any]:
        if not session_id:
            raise SessionManagerError("Missing session_id")
        session = self.sessions.pop(session_id, None)
        record = self.store.get_session(session_id)
        if session is None and record is None:
            raise SessionManagerError(f"Session not found: {session_id}")

        if session is not None:
            session.close()
            record = self._build_metadata(session, status=reason)
        elif record is not None:
            record = dict(record)
            record["status"] = reason

        record["closed_at"] = utcnow_iso()
        record["last_error"] = None if reason == "closed" else record.get("last_error")
        self.store.upsert_session(record)
        return record

    def gc_sessions(self) -> Dict[str, Any]:
        expired_ids: List[str] = []
        for session_id, session in list(self.sessions.items()):
            if session.is_expired(self.idle_timeout_seconds):
                expired_ids.append(session_id)
                self.close_session(session_id, reason="expired")

        return {
            "expired_count": len(expired_ids),
            "expired_session_ids": expired_ids,
            "remaining_live_sessions": len(self.sessions),
        }

    def shutdown(self):
        for session in list(self.sessions.values()):
            try:
                session.close()
            except Exception:
                pass
        self.sessions.clear()

        if self.context is not None:
            try:
                self.context.close()
            except Exception:
                pass
            self.context = None

        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None

        self.store.set_daemon(
            pid=None,
            started_at=self.started_at,
            status="stopped",
            idle_timeout_seconds=self.idle_timeout_seconds,
        )
        self._cleanup_runtime_files()


def _print_session_list(result: Dict[str, Any]):
    sessions = result.get("sessions", [])
    if not sessions:
        print("📭 No sessions recorded")
        return

    print("\n🧠 NotebookLM Sessions:")
    for session in sessions:
        live_mark = " live" if session.get("live") else " stored"
        print(f"\n  • {session['session_id']} [{session['status']}{live_mark}]")
        print(f"    Notebook: {session['notebook_url']}")
        print(f"    Created: {session['created_at']}")
        print(f"    Last activity: {session['last_activity']}")
        print(f"    Messages: {session.get('message_count', 0)}")
        if session.get("last_error"):
            print(f"    Last error: {session['last_error']}")


def _print_session_info(result: Dict[str, Any]):
    print(f"Session ID: {result['session_id']}")
    print(f"Status: {result['status']}")
    print(f"Live: {'yes' if result.get('live') else 'no'}")
    print(f"Notebook: {result['notebook_url']}")
    print(f"Created: {result['created_at']}")
    print(f"Last activity: {result['last_activity']}")
    print(f"Messages: {result.get('message_count', 0)}")
    if result.get("closed_at"):
        print(f"Closed at: {result['closed_at']}")
    if result.get("last_error"):
        print(f"Last error: {result['last_error']}")


def main():
    parser = argparse.ArgumentParser(description="Manage persistent NotebookLM sessions")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    create_parser = subparsers.add_parser("create", help="Create a persistent NotebookLM session")
    create_parser.add_argument("--notebook-url", required=True, help="NotebookLM notebook URL")

    ask_parser = subparsers.add_parser("ask", help="Ask a question through an existing session")
    ask_parser.add_argument("--session-id", required=True, help="Persistent session ID")
    ask_parser.add_argument("--question", required=True, help="Question to ask")

    subparsers.add_parser("list", help="List recorded sessions")

    info_parser = subparsers.add_parser("info", help="Show one session")
    info_parser.add_argument("--session-id", required=True, help="Persistent session ID")

    reset_parser = subparsers.add_parser("reset", help="Reset a live session by recreating its page")
    reset_parser.add_argument("--session-id", required=True, help="Persistent session ID")

    close_parser = subparsers.add_parser("close", help="Close a live session")
    close_parser.add_argument("--session-id", required=True, help="Persistent session ID")

    subparsers.add_parser("gc", help="Collect expired live sessions")
    subparsers.add_parser("_serve", help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.command == "_serve":
        daemon = NotebookSessionDaemon()
        daemon.run()
        return 0

    client = SessionManagerClient()
    client.reconcile_runtime_state()
    store = SessionMetadataStore()

    try:
        if args.command == "create":
            result = client.request("create", auto_start=True, notebook_url=args.notebook_url)
            print(f"✅ Created session: {result['session_id']}")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "ask":
            result = client.request(
                "ask",
                session_id=args.session_id,
                question=args.question,
                timeout_seconds=DEFAULT_CLIENT_TIMEOUT_SECONDS,
            )
            print("\n" + "=" * 60)
            print(f"Session: {result['session_id']}")
            print(f"Question: {result['question']}")
            print("=" * 60)
            print()
            print(result["answer"])
            print()
            print("=" * 60)
            return 0

        if args.command == "list":
            if client.is_daemon_running():
                result = client.request("list")
            else:
                result = {
                    "count": len(store.list_sessions()),
                    "sessions": [
                        {**item, "live": False}
                        for item in store.list_sessions()
                    ],
                }
            _print_session_list(result)
            return 0

        if args.command == "info":
            if client.is_daemon_running():
                result = client.request("info", session_id=args.session_id)
            else:
                record = store.get_session(args.session_id)
                if not record:
                    raise SessionManagerError(f"Session not found: {args.session_id}")
                result = {**record, "live": False}
            _print_session_info(result)
            return 0

        if args.command == "reset":
            result = client.request("reset", session_id=args.session_id)
            print(f"✅ Reset session: {result['session_id']}")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "close":
            result = client.request("close", session_id=args.session_id)
            print(f"✅ Closed session: {result['session_id']}")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "gc":
            if client.is_daemon_running():
                result = client.request("gc")
            else:
                result = {
                    "expired_count": 0,
                    "expired_session_ids": [],
                    "remaining_live_sessions": 0,
                    "note": "Session daemon is not running; only persisted metadata is available.",
                }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        parser.print_help()
        return 0

    except SessionManagerError as error:
        print(f"❌ {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
