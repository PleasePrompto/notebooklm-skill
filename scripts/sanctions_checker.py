#!/usr/bin/env python3
"""
Sanctions List Fetcher
Downloads and searches against official sanctions lists:
  - UN Security Council Consolidated List
  - EU Consolidated Sanctions List
  - UK HMT Sanctions List
  - UAE Local Terrorist List / CBUAE
  - US OFAC SDN List

Stores downloaded lists in data/sanctions/ for offline searching.
"""

import json
import sys
import csv
import io
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
import ssl
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
SANCTIONS_DIR = DATA_DIR / "sanctions"

# Official list URLs
SANCTIONS_SOURCES = {
    "UN": {
        "name": "UN Security Council Consolidated List",
        "url": "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
        "format": "xml",
    },
    "EU": {
        "name": "EU Consolidated Sanctions List",
        "url": "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw",
        "format": "xml",
    },
    "UK": {
        "name": "UK HMT Financial Sanctions",
        "url": "https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv",
        "format": "csv",
    },
    "OFAC": {
        "name": "US OFAC SDN List",
        "url": "https://www.treasury.gov/ofac/downloads/sdn.csv",
        "format": "csv",
    },
    "UAE": {
        "name": "UAE CBUAE / Local Terrorist List",
        "url": "https://www.centralbank.ae/media/gxjpfasp/combined-terror-list.xlsx",
        "format": "manual",
    },
}


def _make_request(url: str) -> bytes:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; ComplianceBot/1.0)")
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return resp.read()


# ── List downloading & parsing ───────────────────────────────────

def download_list(source_key: str) -> Dict[str, Any]:
    """Download and parse a sanctions list. Returns parsed entries."""
    SANCTIONS_DIR.mkdir(parents=True, exist_ok=True)
    source = SANCTIONS_SOURCES.get(source_key)
    if not source:
        raise ValueError(f"Unknown source: {source_key}. Available: {list(SANCTIONS_SOURCES.keys())}")

    if source["format"] == "manual":
        return {
            "source": source_key,
            "name": source["name"],
            "entries": [],
            "count": 0,
            "note": "UAE list requires manual download from CBUAE website. Upload to data/sanctions/uae_list.json",
            "updated_at": datetime.now(TIMEZONE).isoformat(),
        }

    try:
        raw = _make_request(source["url"])
    except Exception as e:
        return {"source": source_key, "error": f"Download failed: {e}"}

    entries = []
    if source["format"] == "xml":
        entries = _parse_xml_list(raw, source_key)
    elif source["format"] == "csv":
        entries = _parse_csv_list(raw, source_key)

    # Save to disk
    result = {
        "source": source_key,
        "name": source["name"],
        "entries": entries,
        "count": len(entries),
        "updated_at": datetime.now(TIMEZONE).isoformat(),
    }

    save_path = SANCTIONS_DIR / f"{source_key.lower()}_list.json"
    with open(save_path, "w") as f:
        json.dump(result, f, indent=2)

    return result


def _parse_xml_list(raw: bytes, source_key: str) -> List[Dict[str, str]]:
    """Parse UN or EU XML sanctions list."""
    entries = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return entries

    if source_key == "UN":
        # UN format: <INDIVIDUALS>/<INDIVIDUAL> and <ENTITIES>/<ENTITY>
        for tag in ["INDIVIDUALS/INDIVIDUAL", "ENTITIES/ENTITY"]:
            for elem in root.findall(f".//{tag}"):
                entry = {
                    "type": "individual" if "INDIVIDUAL" in tag else "entity",
                    "name": "",
                    "aliases": [],
                    "list_id": "",
                }
                first = elem.findtext("FIRST_NAME", "").strip()
                second = elem.findtext("SECOND_NAME", "").strip()
                third = elem.findtext("THIRD_NAME", "").strip()
                entry["name"] = " ".join(filter(None, [first, second, third]))
                entry["list_id"] = elem.findtext("DATAID", "").strip()

                for alias in elem.findall(".//ALIAS"):
                    alias_name = alias.findtext("ALIAS_NAME", "").strip()
                    if alias_name:
                        entry["aliases"].append(alias_name)

                if entry["name"]:
                    entries.append(entry)

    elif source_key == "EU":
        # EU format varies; extract nameAlias elements
        ns = {"eu": "http://eu.europa.ec/fpi/fsd/export"}
        for entity in root.findall(".//eu:sanctionEntity", ns):
            entry = {"type": "entity", "name": "", "aliases": [], "list_id": ""}
            for name_alias in entity.findall(".//eu:nameAlias", ns):
                whole_name = name_alias.get("wholeName", "").strip()
                if whole_name:
                    if not entry["name"]:
                        entry["name"] = whole_name
                    else:
                        entry["aliases"].append(whole_name)
            reg_date = entity.get("designationDate", "")
            entry["list_id"] = entity.get("euReferenceNumber", "")
            if entry["name"]:
                entries.append(entry)

    return entries


def _parse_csv_list(raw: bytes, source_key: str) -> List[Dict[str, str]]:
    """Parse UK HMT or OFAC CSV sanctions list."""
    entries = []
    text = raw.decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(text))

    if source_key == "UK":
        header = None
        for row in reader:
            if header is None:
                header = row
                continue
            if len(row) < 2:
                continue
            # UK format: Name6 is full name, or combine parts
            name_parts = []
            for i, h in enumerate(header):
                if "name" in h.lower() and i < len(row) and row[i].strip():
                    name_parts.append(row[i].strip())
            full_name = " ".join(name_parts[:3]) if name_parts else ""
            if full_name:
                entries.append({
                    "type": "individual" if any("individual" in str(row).lower() for _ in [1]) else "entity",
                    "name": full_name,
                    "aliases": [],
                    "list_id": row[0] if row else "",
                })

    elif source_key == "OFAC":
        for row in reader:
            if len(row) < 2:
                continue
            # OFAC SDN CSV: col 0 = id, col 1 = name, col 2 = type
            name = row[1].strip() if len(row) > 1 else ""
            sdn_type = row[2].strip().lower() if len(row) > 2 else ""
            if name and name != "SDN Name":
                entries.append({
                    "type": "individual" if "individual" in sdn_type else "entity",
                    "name": name,
                    "aliases": [],
                    "list_id": row[0].strip(),
                })

    return entries


# ── Searching ────────────────────────────────────────────────────

def search_sanctions(
    query: str,
    sources: Optional[List[str]] = None,
    threshold: float = 0.8,
) -> Dict[str, Any]:
    """Search all downloaded sanctions lists for a name.

    Uses fuzzy matching to catch transliteration variants.
    """
    SANCTIONS_DIR.mkdir(parents=True, exist_ok=True)
    query_lower = query.lower().strip()
    query_parts = set(query_lower.split())

    if not sources:
        sources = list(SANCTIONS_SOURCES.keys())

    results = {"query": query, "matches": [], "sources_checked": [], "checked_at": datetime.now(TIMEZONE).isoformat()}

    for source_key in sources:
        list_file = SANCTIONS_DIR / f"{source_key.lower()}_list.json"
        if not list_file.exists():
            results["sources_checked"].append({"source": source_key, "status": "not_downloaded"})
            continue

        with open(list_file, "r") as f:
            data = json.load(f)

        entries = data.get("entries", [])
        results["sources_checked"].append({
            "source": source_key,
            "status": "checked",
            "entries_count": len(entries),
            "last_updated": data.get("updated_at", "unknown"),
        })

        for entry in entries:
            # Check main name
            score = _fuzzy_match(query_lower, query_parts, entry.get("name", ""))
            if score >= threshold:
                results["matches"].append({
                    "source": source_key,
                    "name": entry["name"],
                    "type": entry.get("type", "unknown"),
                    "match_score": round(score, 2),
                    "matched_on": "primary_name",
                    "list_id": entry.get("list_id", ""),
                })
                continue

            # Check aliases
            for alias in entry.get("aliases", []):
                score = _fuzzy_match(query_lower, query_parts, alias)
                if score >= threshold:
                    results["matches"].append({
                        "source": source_key,
                        "name": entry["name"],
                        "alias_matched": alias,
                        "type": entry.get("type", "unknown"),
                        "match_score": round(score, 2),
                        "matched_on": "alias",
                        "list_id": entry.get("list_id", ""),
                    })
                    break

    results["total_matches"] = len(results["matches"])
    results["matches"].sort(key=lambda x: x["match_score"], reverse=True)

    # Log the screening
    _log_screening(query, results)

    return results


def _fuzzy_match(query_lower: str, query_parts: set, target: str) -> float:
    """Simple fuzzy matching: exact substring, token overlap, and containment."""
    if not target:
        return 0.0

    target_lower = target.lower().strip()
    target_parts = set(target_lower.split())

    # Exact match
    if query_lower == target_lower:
        return 1.0

    # Substring containment
    if query_lower in target_lower or target_lower in query_lower:
        return 0.95

    # Token overlap (Jaccard-like)
    if query_parts and target_parts:
        intersection = query_parts & target_parts
        union = query_parts | target_parts
        jaccard = len(intersection) / len(union)
        if jaccard > 0:
            return 0.5 + (jaccard * 0.45)

    # Partial token match (any query token in any target token)
    for qp in query_parts:
        for tp in target_parts:
            if qp in tp or tp in qp:
                return 0.7

    return 0.0


def _log_screening(query: str, results: Dict[str, Any]):
    """Log screening to audit trail."""
    log_file = DATA_DIR / "screening_log.json"
    logs = []
    if log_file.exists():
        try:
            with open(log_file, "r") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    logs.append({
        "query": query,
        "total_matches": results["total_matches"],
        "sources_checked": [s["source"] for s in results["sources_checked"]],
        "timestamp": datetime.now(TIMEZONE).isoformat(),
    })

    # Keep last 10000 entries
    logs = logs[-10000:]
    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2)


# ── Batch screening ──────────────────────────────────────────────

def batch_screen(names: List[str], sources: Optional[List[str]] = None) -> Dict[str, Any]:
    """Screen multiple names at once."""
    all_results = []
    flagged = []

    for name in names:
        result = search_sanctions(name, sources)
        entry = {"name": name, "matches": result["total_matches"]}
        if result["total_matches"] > 0:
            entry["details"] = result["matches"][:5]  # Top 5 matches
            flagged.append(entry)
        all_results.append(entry)

    return {
        "total_screened": len(names),
        "total_flagged": len(flagged),
        "flagged": flagged,
        "clean": [r["name"] for r in all_results if r["matches"] == 0],
        "checked_at": datetime.now(TIMEZONE).isoformat(),
    }


def get_list_status() -> Dict[str, Any]:
    """Check which sanctions lists are downloaded and when last updated."""
    SANCTIONS_DIR.mkdir(parents=True, exist_ok=True)
    status = {}
    for key, source in SANCTIONS_SOURCES.items():
        list_file = SANCTIONS_DIR / f"{key.lower()}_list.json"
        if list_file.exists():
            with open(list_file, "r") as f:
                data = json.load(f)
            status[key] = {
                "name": source["name"],
                "downloaded": True,
                "entries": data.get("count", 0),
                "updated_at": data.get("updated_at", "unknown"),
            }
        else:
            status[key] = {
                "name": source["name"],
                "downloaded": False,
            }
    return status


def download_all_lists() -> Dict[str, Any]:
    """Download all available sanctions lists."""
    results = {}
    for key in SANCTIONS_SOURCES:
        results[key] = download_list(key)
    return results
