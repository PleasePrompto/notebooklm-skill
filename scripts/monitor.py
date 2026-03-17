#!/usr/bin/env python3
"""
Real-Time Monitoring for NotebookLM Skill
Provides a live progress feed, task tracking, and system activity display.

Usage:
  from monitor import ProgressMonitor, LiveDashboard

  # Simple progress tracking
  monitor = ProgressMonitor("query_notebook")
  monitor.start("Opening browser")
  monitor.update("Waiting for response")
  monitor.complete("Done")

  # Full dashboard (interactive CLI)
  python scripts/monitor.py --watch
"""

import sys
import time
import json
import threading
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

# ── Paths ────────────────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).parent.parent
LOG_FILE = SKILL_DIR / "data" / "activity.log"
METRICS_FILE = SKILL_DIR / "data" / "metrics.json"


# ── ANSI helpers ─────────────────────────────────────────────────────────────
def _c(code: str, text: str) -> str:
    """Wrap text in ANSI color (skipped when not a TTY)."""
    if not sys.stderr.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"

GREEN  = lambda t: _c("32", t)
YELLOW = lambda t: _c("33", t)
CYAN   = lambda t: _c("36", t)
RED    = lambda t: _c("31", t)
BOLD   = lambda t: _c("1",  t)
DIM    = lambda t: _c("2",  t)

ICONS = {
    "start":    "▶",
    "update":   "↻",
    "complete": "✓",
    "error":    "✗",
    "metric":   "◈",
    "feed":     "•",
}


# ── Activity log ─────────────────────────────────────────────────────────────

def _log_event(event: dict):
    """Append an event to the activity log (thread-safe via line-buffering)."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({"ts": datetime.utcnow().isoformat(), **event}) + "\n"
    with open(LOG_FILE, "a") as f:
        f.write(entry)


# ── Metrics store ─────────────────────────────────────────────────────────────

class MetricsStore:
    """Persists cumulative performance metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict = self._load()

    def _load(self) -> Dict:
        if METRICS_FILE.exists():
            try:
                with open(METRICS_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"queries": 0, "total_duration_s": 0.0, "errors": 0, "sessions": []}

    def _save(self):
        METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(METRICS_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    def record_query(self, duration_s: float, success: bool):
        with self._lock:
            self._data["queries"] += 1
            self._data["total_duration_s"] += duration_s
            if not success:
                self._data["errors"] += 1
            session = {
                "ts": datetime.utcnow().isoformat(),
                "duration_s": round(duration_s, 2),
                "success": success
            }
            self._data.setdefault("sessions", []).append(session)
            # Keep only last 100 sessions
            self._data["sessions"] = self._data["sessions"][-100:]
            self._save()

    def summary(self) -> Dict:
        with self._lock:
            q = self._data.get("queries", 0)
            avg = (self._data.get("total_duration_s", 0) / q) if q else 0
            return {
                "total_queries": q,
                "avg_duration_s": round(avg, 2),
                "errors": self._data.get("errors", 0),
                "success_rate": f"{((q - self._data.get('errors', 0)) / q * 100):.1f}%" if q else "N/A"
            }


_metrics = MetricsStore()


# ── ProgressMonitor ───────────────────────────────────────────────────────────

class ProgressMonitor:
    """
    Tracks and displays real-time progress for a single task.

    Emits to stderr (visible to user) and writes to the activity log.
    """

    def __init__(self, task_name: str):
        self.task = task_name
        self._start_time: Optional[float] = None
        self._last_step: Optional[str] = None

    def start(self, step: str):
        self._start_time = time.time()
        self._last_step = step
        msg = f"[{self.task}] {ICONS['start']} {step}"
        self._emit(GREEN(msg))
        _log_event({"task": self.task, "event": "start", "step": step})

    def update(self, step: str):
        elapsed = self._elapsed()
        self._last_step = step
        msg = f"[{self.task}] {ICONS['update']} {step}  {DIM(elapsed)}"
        self._emit(CYAN(msg))
        _log_event({"task": self.task, "event": "update", "step": step, "elapsed": elapsed})

    def complete(self, step: str = "Done"):
        elapsed = self._elapsed()
        duration = time.time() - (self._start_time or time.time())
        msg = f"[{self.task}] {ICONS['complete']} {step}  {DIM(elapsed)}"
        self._emit(GREEN(BOLD(msg)))
        _log_event({"task": self.task, "event": "complete", "step": step, "elapsed": elapsed})
        _metrics.record_query(duration, success=True)

    def error(self, detail: str):
        elapsed = self._elapsed()
        duration = time.time() - (self._start_time or time.time())
        msg = f"[{self.task}] {ICONS['error']} ERROR: {detail}  {DIM(elapsed)}"
        self._emit(RED(msg))
        _log_event({"task": self.task, "event": "error", "detail": detail, "elapsed": elapsed})
        _metrics.record_query(duration, success=False)

    def _elapsed(self) -> str:
        if self._start_time is None:
            return ""
        s = time.time() - self._start_time
        return f"({s:.1f}s)"

    @staticmethod
    def _emit(text: str):
        print(text, file=sys.stderr, flush=True)


# ── LiveDashboard ─────────────────────────────────────────────────────────────

class LiveDashboard:
    """
    Interactive live feed dashboard for the terminal.
    Displays recent activity, current task progress, and performance metrics.
    """

    def __init__(self, refresh_s: float = 1.0, tail: int = 20):
        self.refresh_s = refresh_s
        self.tail = tail
        self._stop = threading.Event()

    def run(self):
        """Run the dashboard until Ctrl-C."""
        try:
            while not self._stop.is_set():
                self._render()
                time.sleep(self.refresh_s)
        except KeyboardInterrupt:
            pass
        finally:
            print()  # trailing newline

    def stop(self):
        self._stop.set()

    def _render(self):
        # Clear terminal
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(BOLD(f"  NotebookLM Real-Time Monitor  ") + DIM(f"  {now}"))
        print("─" * 60)

        # ── Live Feed section ──────────────────────────────────────
        print(BOLD(f"\n  {ICONS['feed']} Live Feed"))
        events = self._read_log(self.tail)
        if events:
            for ev in events:
                ts = ev.get("ts", "")[-8:]  # HH:MM:SS portion
                task = ev.get("task", "?")
                kind = ev.get("event", "")
                step = ev.get("step") or ev.get("detail", "")
                elapsed = ev.get("elapsed", "")
                icon = ICONS.get(kind, ICONS["feed"])
                line = f"  {DIM(ts)}  [{task}] {icon} {step}  {DIM(elapsed)}"
                if kind == "complete":
                    print(GREEN(line))
                elif kind == "error":
                    print(RED(line))
                elif kind == "start":
                    print(CYAN(line))
                else:
                    print(line)
        else:
            print(DIM("  No activity yet."))

        # ── System Activity / Metrics ──────────────────────────────
        print(BOLD(f"\n  {ICONS['metric']} System Activity"))
        summary = _metrics.summary()
        print(f"  Total queries   : {CYAN(str(summary['total_queries']))}")
        print(f"  Avg duration    : {CYAN(str(summary['avg_duration_s']) + 's')}")
        print(f"  Errors          : {RED(str(summary['errors']))}")
        print(f"  Success rate    : {GREEN(summary['success_rate'])}")

        # ── Task Progress (last 5 running tasks) ───────────────────
        in_progress = self._running_tasks(events)
        if in_progress:
            print(BOLD(f"\n  Task Progress"))
            for task in in_progress:
                print(f"  {YELLOW('↻')} {task}")

        print("\n" + DIM("  Press Ctrl-C to exit"))

    @staticmethod
    def _read_log(n: int) -> List[Dict]:
        if not LOG_FILE.exists():
            return []
        try:
            lines = LOG_FILE.read_text().splitlines()
            events = []
            for line in lines[-n:]:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
            return events
        except Exception:
            return []

    @staticmethod
    def _running_tasks(events: List[Dict]) -> List[str]:
        """Return tasks that have started but not yet completed/errored."""
        started = {}
        for ev in events:
            task = ev.get("task", "")
            kind = ev.get("event", "")
            if kind == "start":
                started[task] = ev.get("step", "")
            elif kind in ("complete", "error"):
                started.pop(task, None)
        return [f"{t}: {s}" for t, s in started.items()]


# ── CLI ───────────────────────────────────────────────────────────────────────

def cli_status():
    """Print a one-shot status summary."""
    print(BOLD("\nNotebookLM Skill — Activity Summary"))
    print("─" * 40)
    summary = _metrics.summary()
    print(f"  Total queries  : {summary['total_queries']}")
    print(f"  Avg duration   : {summary['avg_duration_s']}s")
    print(f"  Errors         : {summary['errors']}")
    print(f"  Success rate   : {summary['success_rate']}")

    print(BOLD("\nRecent Activity (last 10 events):"))
    events = LiveDashboard._read_log(10)
    if not events:
        print(DIM("  No activity logged yet."))
    for ev in events:
        ts = ev.get("ts", "")[-8:]
        task = ev.get("task", "?")
        kind = ev.get("event", "")
        step = ev.get("step") or ev.get("detail", "")
        elapsed = ev.get("elapsed", "")
        icon = ICONS.get(kind, ICONS["feed"])
        print(f"  {DIM(ts)}  [{task}] {icon} {step} {DIM(elapsed)}")
    print()


def main():
    parser = argparse.ArgumentParser(description="NotebookLM Real-Time Monitor")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("watch", help="Live dashboard (refreshes every second)")
    sub.add_parser("status", help="One-shot status summary")
    sub.add_parser("clear", help="Clear activity log and metrics")
    args = parser.parse_args()

    if args.cmd == "watch":
        print(DIM("Starting live dashboard... (Ctrl-C to stop)"))
        time.sleep(0.5)
        LiveDashboard().run()
    elif args.cmd == "clear":
        for f in (LOG_FILE, METRICS_FILE):
            if f.exists():
                f.unlink()
                print(f"Cleared: {f}")
        print("Done.")
    else:
        cli_status()


if __name__ == "__main__":
    main()
