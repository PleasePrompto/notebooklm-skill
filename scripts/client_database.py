#!/usr/bin/env python3
"""
Client Database with KYC/AML tracking
Manages clients with risk ratings, KYC status, review dates,
and links to sanctions screening results.
"""

import json
import uuid
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
CLIENTS_FILE = DATA_DIR / "clients.json"

RISK_RATINGS = ("low", "medium", "high", "critical", "pep", "sanctioned")
KYC_STATUSES = ("pending", "in_progress", "approved", "rejected", "expired", "under_review")
CLIENT_TYPES = ("individual", "corporate", "trust", "government", "npo")


class ClientDatabase:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db_file = CLIENTS_FILE
        self.clients: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if self.db_file.exists():
            try:
                with open(self.db_file, "r") as f:
                    data = json.load(f)
                self.clients = data.get("clients", {})
            except Exception:
                self.clients = {}
        else:
            self._save()

    def _save(self):
        with open(self.db_file, "w") as f:
            json.dump({
                "clients": self.clients,
                "updated_at": datetime.now(TIMEZONE).isoformat(),
            }, f, indent=2)

    def add_client(
        self,
        name: str,
        client_type: str = "individual",
        risk_rating: str = "medium",
        kyc_status: str = "pending",
        nationality: str = "",
        id_number: str = "",
        email: str = "",
        phone: str = "",
        address: str = "",
        notes: str = "",
        tags: Optional[List[str]] = None,
        review_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        if client_type not in CLIENT_TYPES:
            raise ValueError(f"Invalid client type. Choose from: {CLIENT_TYPES}")
        if risk_rating not in RISK_RATINGS:
            raise ValueError(f"Invalid risk rating. Choose from: {RISK_RATINGS}")
        if kyc_status not in KYC_STATUSES:
            raise ValueError(f"Invalid KYC status. Choose from: {KYC_STATUSES}")

        client_id = str(uuid.uuid4())[:8]
        now = datetime.now(TIMEZONE)

        # Default review date based on risk
        if not review_date:
            review_deltas = {
                "low": timedelta(days=365),
                "medium": timedelta(days=180),
                "high": timedelta(days=90),
                "critical": timedelta(days=30),
                "pep": timedelta(days=90),
                "sanctioned": timedelta(days=0),
            }
            review_dt = now + review_deltas.get(risk_rating, timedelta(days=180))
            review_date = review_dt.isoformat()

        client = {
            "id": client_id,
            "name": name,
            "client_type": client_type,
            "risk_rating": risk_rating,
            "kyc_status": kyc_status,
            "nationality": nationality,
            "id_number": id_number,
            "email": email,
            "phone": phone,
            "address": address,
            "notes": notes,
            "tags": tags or [],
            "review_date": review_date,
            "screening_history": [],
            "documents": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        self.clients[client_id] = client
        self._save()
        return client

    def get_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        return self.clients.get(client_id)

    def update_client(self, client_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        client = self.clients.get(client_id)
        if not client:
            raise ValueError(f"Client not found: {client_id}")

        allowed = {
            "name", "client_type", "risk_rating", "kyc_status",
            "nationality", "id_number", "email", "phone", "address",
            "notes", "tags", "review_date",
        }
        for key, value in updates.items():
            if key in allowed:
                client[key] = value

        client["updated_at"] = datetime.now(TIMEZONE).isoformat()
        self._save()
        return client

    def delete_client(self, client_id: str) -> bool:
        if client_id in self.clients:
            del self.clients[client_id]
            self._save()
            return True
        return False

    def search_clients(
        self,
        query: Optional[str] = None,
        risk_rating: Optional[str] = None,
        kyc_status: Optional[str] = None,
        client_type: Optional[str] = None,
        tag: Optional[str] = None,
        review_due: bool = False,
    ) -> List[Dict[str, Any]]:
        results = []
        now = datetime.now(TIMEZONE)

        for client in self.clients.values():
            if risk_rating and client["risk_rating"] != risk_rating:
                continue
            if kyc_status and client["kyc_status"] != kyc_status:
                continue
            if client_type and client["client_type"] != client_type:
                continue
            if tag and tag not in client.get("tags", []):
                continue
            if review_due and client.get("review_date"):
                review_dt = datetime.fromisoformat(client["review_date"])
                if review_dt.tzinfo is None:
                    review_dt = review_dt.replace(tzinfo=TIMEZONE)
                if review_dt > now:
                    continue
            if query:
                q = query.lower()
                searchable = f"{client['name']} {client.get('nationality', '')} {client.get('notes', '')} {' '.join(client.get('tags', []))}".lower()
                if q not in searchable:
                    continue
            results.append(client)

        results.sort(key=lambda x: x.get("review_date") or "9999")
        return results

    def add_screening_result(self, client_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        client = self.clients.get(client_id)
        if not client:
            raise ValueError(f"Client not found: {client_id}")

        screening = {
            "timestamp": datetime.now(TIMEZONE).isoformat(),
            "matches": result.get("total_matches", 0),
            "sources": [s["source"] for s in result.get("sources_checked", [])],
            "flagged": result.get("total_matches", 0) > 0,
        }
        client["screening_history"].append(screening)
        client["updated_at"] = datetime.now(TIMEZONE).isoformat()

        # Auto-update risk if matches found
        if screening["flagged"] and client["risk_rating"] not in ("critical", "sanctioned", "pep"):
            client["risk_rating"] = "high"
            client["kyc_status"] = "under_review"

        self._save()
        return client

    def get_review_due(self) -> List[Dict[str, Any]]:
        """Get clients with overdue or upcoming KYC reviews."""
        now = datetime.now(TIMEZONE)
        week_ahead = now + timedelta(days=7)

        overdue = []
        upcoming = []

        for client in self.clients.values():
            if not client.get("review_date"):
                continue
            review_dt = datetime.fromisoformat(client["review_date"])
            if review_dt.tzinfo is None:
                review_dt = review_dt.replace(tzinfo=TIMEZONE)

            if review_dt <= now:
                overdue.append(client)
            elif review_dt <= week_ahead:
                upcoming.append(client)

        return {"overdue": overdue, "upcoming": upcoming}

    def get_stats(self) -> Dict[str, Any]:
        by_risk = {}
        by_kyc = {}
        by_type = {}
        for c in self.clients.values():
            by_risk[c["risk_rating"]] = by_risk.get(c["risk_rating"], 0) + 1
            by_kyc[c["kyc_status"]] = by_kyc.get(c["kyc_status"], 0) + 1
            by_type[c["client_type"]] = by_type.get(c["client_type"], 0) + 1

        reviews = self.get_review_due()
        return {
            "total_clients": len(self.clients),
            "by_risk_rating": by_risk,
            "by_kyc_status": by_kyc,
            "by_client_type": by_type,
            "reviews_overdue": len(reviews["overdue"]),
            "reviews_upcoming": len(reviews["upcoming"]),
        }
