#!/usr/bin/env python3
"""
Audit Trail Logger
Immutable, append-only audit log for all compliance-relevant actions.
Every action is timestamped with Dubai time and cannot be modified.
"""

import json
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
AUDIT_FILE = DATA_DIR / "audit_trail.json"

ACTION_CATEGORIES = (
    "screening", "kyc", "client", "alert", "report",
    "document", "workflow", "price_check", "rate_check",
    "sanctions", "login", "config", "export",
)


class AuditTrail:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.audit_file = AUDIT_FILE

    def log(
        self,
        action: str,
        category: str,
        details: Optional[Dict[str, Any]] = None,
        user: str = "system",
        client_id: Optional[str] = None,
        item_id: Optional[str] = None,
        result: str = "success",
    ) -> Dict[str, Any]:
        """Log an audit event. Entries are append-only and hashed for integrity."""
        now = datetime.now(TIMEZONE)
        entries = self._load()

        # Create hash chain for tamper detection
        prev_hash = entries[-1]["hash"] if entries else "genesis"

        entry = {
            "id": len(entries) + 1,
            "timestamp": now.isoformat(),
            "action": action,
            "category": category,
            "details": details or {},
            "user": user,
            "client_id": client_id,
            "item_id": item_id,
            "result": result,
            "prev_hash": prev_hash,
        }

        # Hash this entry for integrity chain
        entry_str = json.dumps(entry, sort_keys=True)
        entry["hash"] = hashlib.sha256(entry_str.encode()).hexdigest()[:16]

        entries.append(entry)
        self._save(entries)
        return entry

    def query(
        self,
        category: Optional[str] = None,
        client_id: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query audit trail with filters."""
        entries = self._load()
        results = []

        for entry in reversed(entries):
            if category and entry.get("category") != category:
                continue
            if client_id and entry.get("client_id") != client_id:
                continue
            if action and action.lower() not in entry.get("action", "").lower():
                continue
            if start_date and entry["timestamp"] < start_date:
                continue
            if end_date and entry["timestamp"] > end_date:
                continue
            results.append(entry)
            if len(results) >= limit:
                break

        return results

    def verify_integrity(self) -> Dict[str, Any]:
        """Verify the audit trail hash chain hasn't been tampered with."""
        entries = self._load()
        if not entries:
            return {"valid": True, "entries_checked": 0}

        errors = []
        for i, entry in enumerate(entries):
            # Check prev_hash chain
            if i == 0:
                if entry.get("prev_hash") != "genesis":
                    errors.append({"entry_id": entry["id"], "error": "Invalid genesis hash"})
            else:
                if entry.get("prev_hash") != entries[i - 1].get("hash"):
                    errors.append({"entry_id": entry["id"], "error": "Hash chain broken"})

            # Verify entry hash
            stored_hash = entry.get("hash")
            entry_copy = {k: v for k, v in entry.items() if k != "hash"}
            entry_str = json.dumps(entry_copy, sort_keys=True)
            computed_hash = hashlib.sha256(entry_str.encode()).hexdigest()[:16]
            if stored_hash != computed_hash:
                errors.append({"entry_id": entry["id"], "error": "Entry hash mismatch"})

        return {
            "valid": len(errors) == 0,
            "entries_checked": len(entries),
            "errors": errors,
            "checked_at": datetime.now(TIMEZONE).isoformat(),
        }

    def get_stats(self) -> Dict[str, Any]:
        entries = self._load()
        by_category = {}
        by_result = {}
        for e in entries:
            cat = e.get("category", "unknown")
            res = e.get("result", "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1
            by_result[res] = by_result.get(res, 0) + 1

        return {
            "total_entries": len(entries),
            "by_category": by_category,
            "by_result": by_result,
            "first_entry": entries[0]["timestamp"] if entries else None,
            "last_entry": entries[-1]["timestamp"] if entries else None,
        }

    def _load(self) -> List[Dict[str, Any]]:
        if self.audit_file.exists():
            try:
                with open(self.audit_file, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save(self, entries: List[Dict[str, Any]]):
        with open(self.audit_file, "w") as f:
            json.dump(entries, f, indent=2)


# Singleton for easy import
_audit = AuditTrail()

def log_action(action: str, category: str, **kwargs) -> Dict[str, Any]:
    """Convenience function to log an audit event."""
    return _audit.log(action, category, **kwargs)

def query_audit(**kwargs) -> List[Dict[str, Any]]:
    return _audit.query(**kwargs)

def verify_audit() -> Dict[str, Any]:
    return _audit.verify_integrity()

def audit_stats() -> Dict[str, Any]:
    return _audit.get_stats()
