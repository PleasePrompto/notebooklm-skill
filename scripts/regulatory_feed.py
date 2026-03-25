#!/usr/bin/env python3
"""
Regulatory News Feed
Fetches regulatory updates from CBUAE, FATF, and UAE sources.
Stores and tracks read/unread status.
"""

import json
import sys
import urllib.request
import ssl
import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
FEED_FILE = DATA_DIR / "regulatory_feed.json"

# Regulatory sources
SOURCES = {
    "CBUAE": {
        "name": "Central Bank of UAE",
        "url": "https://www.centralbank.ae/en/our-operations/anti-money-laundering/",
        "rss": None,
        "type": "html",
    },
    "FATF": {
        "name": "Financial Action Task Force",
        "url": "https://www.fatf-gafi.org/en/publications.html",
        "rss": "https://www.fatf-gafi.org/content/fatf-gafi/en/publications.rss.xml",
        "type": "rss",
    },
    "UAE_MOE": {
        "name": "UAE Ministry of Economy",
        "url": "https://www.moec.gov.ae/en/anti-money-laundering",
        "rss": None,
        "type": "html",
    },
    "NAMLCFTC": {
        "name": "UAE National AML/CFT Committee",
        "url": "https://www.namlcftc.gov.ae/en/media-centre/",
        "rss": None,
        "type": "html",
    },
    "LBMA": {
        "name": "London Bullion Market Association",
        "url": "https://www.lbma.org.uk/articles",
        "rss": None,
        "type": "html",
    },
    "OECD": {
        "name": "OECD Financial Action",
        "url": "https://www.oecd.org/en/topics/sub-issues/anti-money-laundering.html",
        "rss": None,
        "type": "html",
    },
    "FIU_UAE": {
        "name": "UAE Financial Intelligence Unit",
        "url": "https://www.uaefiu.gov.ae/en/media-center",
        "rss": None,
        "type": "html",
    },
    "EOCN": {
        "name": "Executive Office for Control & Non-Proliferation",
        "url": "https://www.eocn.gov.ae/en/media-centre",
        "rss": None,
        "type": "html",
    },
}


def _make_request(url: str) -> str:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; ComplianceFeed/1.0)")
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _load_feed() -> Dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if FEED_FILE.exists():
        try:
            with open(FEED_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"articles": [], "last_fetch": {}}


def _save_feed(data: Dict[str, Any]):
    with open(FEED_FILE, "w") as f:
        json.dump(data, f, indent=2)


def fetch_updates(source: Optional[str] = None) -> Dict[str, Any]:
    """Fetch latest regulatory updates from all or specific source."""
    feed = _load_feed()
    sources_to_fetch = {source.upper(): SOURCES[source.upper()]} if source else SOURCES
    new_articles = []
    errors = []

    existing_ids = {a["id"] for a in feed["articles"]}

    for key, src in sources_to_fetch.items():
        try:
            if src.get("rss"):
                articles = _parse_rss(src["rss"], key)
            else:
                articles = _parse_html_feed(src["url"], key)

            for article in articles:
                if article["id"] not in existing_ids:
                    article["source"] = key
                    article["source_name"] = src["name"]
                    article["fetched_at"] = datetime.now(TIMEZONE).isoformat()
                    article["read"] = False
                    feed["articles"].append(article)
                    new_articles.append(article)
                    existing_ids.add(article["id"])

            feed["last_fetch"][key] = datetime.now(TIMEZONE).isoformat()
        except Exception as e:
            errors.append(f"{key}: {e}")

    # Keep last 500 articles
    feed["articles"] = feed["articles"][-500:]
    _save_feed(feed)

    return {
        "new_articles": len(new_articles),
        "total_articles": len(feed["articles"]),
        "errors": errors,
        "articles": new_articles[:10],
    }


def _parse_rss(url: str, source_key: str) -> List[Dict[str, Any]]:
    """Parse RSS feed for articles."""
    import xml.etree.ElementTree as ET

    raw = _make_request(url)
    root = ET.fromstring(raw)
    articles = []

    for item in root.findall(".//item")[:20]:
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        desc = item.findtext("description", "").strip()
        desc = re.sub(r"<[^>]+>", "", desc)[:300]

        if title:
            article_id = hashlib.md5(f"{source_key}:{title}".encode()).hexdigest()[:12]
            articles.append({
                "id": article_id,
                "title": title,
                "link": link,
                "date": pub_date,
                "summary": desc,
            })

    return articles


def _parse_html_feed(url: str, source_key: str) -> List[Dict[str, Any]]:
    """Extract article-like content from HTML pages."""
    try:
        html = _make_request(url)
    except Exception:
        return []

    articles = []

    # Extract links that look like articles/news
    link_pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]{10,200})</a>'
    matches = re.findall(link_pattern, html, re.IGNORECASE)

    keywords = ["aml", "sanction", "compliance", "regulation", "circular", "notice",
                 "guideline", "fatf", "money laundering", "terrorist financing",
                 "suspicious", "reporting", "dnfbp", "designated", "responsible",
                 "gold", "bullion", "precious metal", "lbma", "oecd", "proliferation",
                 "beneficial ownership", "due diligence", "kyc", "risk assessment",
                 "enforcement", "penalty", "fine", "guidance", "consultation"]

    for href, text in matches:
        text_clean = re.sub(r"\s+", " ", text).strip()
        text_lower = text_clean.lower()

        if any(kw in text_lower for kw in keywords) and len(text_clean) > 15:
            article_id = hashlib.md5(f"{source_key}:{text_clean}".encode()).hexdigest()[:12]
            articles.append({
                "id": article_id,
                "title": text_clean,
                "link": href if href.startswith("http") else "",
                "date": "",
                "summary": "",
            })

    return articles[:15]


def get_unread() -> List[Dict[str, Any]]:
    """Get unread regulatory updates."""
    feed = _load_feed()
    return [a for a in feed["articles"] if not a.get("read")]


def mark_read(article_id: Optional[str] = None) -> int:
    """Mark article(s) as read. If no ID, marks all as read."""
    feed = _load_feed()
    count = 0
    for a in feed["articles"]:
        if article_id is None or a["id"] == article_id:
            if not a.get("read"):
                a["read"] = True
                count += 1
    _save_feed(feed)
    return count


def get_feed_status() -> Dict[str, Any]:
    """Get feed status and last fetch times."""
    feed = _load_feed()
    unread = sum(1 for a in feed["articles"] if not a.get("read"))
    return {
        "total_articles": len(feed["articles"]),
        "unread": unread,
        "last_fetch": feed.get("last_fetch", {}),
        "sources": {k: v["name"] for k, v in SOURCES.items()},
    }
