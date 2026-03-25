#!/usr/bin/env python3
"""
Gold & Silver Price Tracker
Fetches live precious metal prices and manages price alerts.

Sources (tried in order):
  1. Reuters/LSEG data feed
  2. Fallback: metals-api / alternative feeds

Stores price history and alerts in data/prices.json
"""

import json
import re
import sys
import urllib.request
import urllib.error
import ssl
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
PRICES_FILE = DATA_DIR / "prices.json"

# Symbols
METALS = {
    "gold": {"symbol": "XAU", "unit": "USD/oz", "name": "Gold"},
    "silver": {"symbol": "XAG", "unit": "USD/oz", "name": "Silver"},
}

# ── Price fetching ───────────────────────────────────────────────

def _make_request(url: str, headers: Optional[Dict] = None) -> str:
    """Make an HTTP request and return the response body."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; WorkflowBot/1.0)")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        return resp.read().decode("utf-8")


def fetch_prices() -> Dict[str, Any]:
    """Fetch current gold and silver prices from multiple sources.

    Returns dict with gold and silver prices, source, and timestamp.
    """
    errors = []

    # Source 1: Reuters/LSEG commodity pages
    try:
        return _fetch_from_reuters()
    except Exception as e:
        errors.append(f"Reuters: {e}")

    # Source 2: Alternative - frankfurter or metals.live
    try:
        return _fetch_from_metals_live()
    except Exception as e:
        errors.append(f"metals.live: {e}")

    # Source 3: GoldAPI.io free tier
    try:
        return _fetch_from_goldapi()
    except Exception as e:
        errors.append(f"goldapi: {e}")

    return {
        "error": f"Could not fetch prices. Tried: {'; '.join(errors)}",
        "timestamp": datetime.now().isoformat(),
    }


def _fetch_from_reuters() -> Dict[str, Any]:
    """Fetch from Reuters/LSEG."""
    # Gold XAU=
    gold_url = "https://www.reuters.com/markets/commodities/gold/"
    html = _make_request(gold_url)

    # Extract price from page data
    gold_price = _extract_price_from_html(html)
    if not gold_price:
        raise ValueError("Could not parse gold price from Reuters")

    # Silver XAG=
    silver_url = "https://www.reuters.com/markets/commodities/silver/"
    html = _make_request(silver_url)
    silver_price = _extract_price_from_html(html)
    if not silver_price:
        raise ValueError("Could not parse silver price from Reuters")

    return _build_result(gold_price, silver_price, "Reuters/LSEG")


def _fetch_from_metals_live() -> Dict[str, Any]:
    """Fetch from metals.live API (free, no key)."""
    data = _make_request("https://api.metals.live/v1/spot")
    prices = json.loads(data)

    gold_price = None
    silver_price = None
    for item in prices:
        if item.get("gold"):
            gold_price = float(item["gold"])
        if item.get("silver"):
            silver_price = float(item["silver"])

    if gold_price and silver_price:
        return _build_result(gold_price, silver_price, "metals.live")

    raise ValueError("Incomplete data from metals.live")


def _fetch_from_goldapi() -> Dict[str, Any]:
    """Fetch from goldapi.io (free tier: 30 req/month)."""
    # Check if API key is configured
    import os
    try:
        from dotenv import load_dotenv
        env_path = SKILL_DIR / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass

    api_key = os.environ.get("GOLDAPI_KEY", "")
    if not api_key:
        raise ValueError("GOLDAPI_KEY not configured")

    headers = {"x-access-token": api_key}

    gold_data = json.loads(_make_request("https://www.goldapi.io/api/XAU/USD", headers))
    silver_data = json.loads(_make_request("https://www.goldapi.io/api/XAG/USD", headers))

    return _build_result(gold_data["price"], silver_data["price"], "goldapi.io")


def _extract_price_from_html(html: str) -> Optional[float]:
    """Extract a commodity price from Reuters HTML."""
    # Look for price patterns in the HTML/JSON data
    patterns = [
        r'"price":\s*([\d,]+\.?\d*)',
        r'"last":\s*([\d,]+\.?\d*)',
        r'data-testid="instrument-price[^"]*"[^>]*>([\d,]+\.?\d*)',
        r'class="[^"]*price[^"]*"[^>]*>\$?([\d,]+\.?\d*)',
        r'([\d,]+\.\d{2})\s*USD',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            price_str = match.group(1).replace(",", "")
            try:
                price = float(price_str)
                # Sanity check: gold ~1500-5000, silver ~15-100
                if price > 10:
                    return price
            except ValueError:
                continue
    return None


def _build_result(gold: float, silver: float, source: str) -> Dict[str, Any]:
    """Build standardized price result."""
    now = datetime.now()
    ratio = gold / silver if silver > 0 else 0

    result = {
        "gold": {
            "price": round(gold, 2),
            "symbol": "XAU",
            "unit": "USD/oz",
            "name": "Gold",
        },
        "silver": {
            "price": round(silver, 2),
            "symbol": "XAG",
            "unit": "USD/oz",
            "name": "Silver",
        },
        "gold_silver_ratio": round(ratio, 2),
        "source": source,
        "timestamp": now.isoformat(),
    }

    # Save to history
    _save_price_history(result)

    return result


# ── Price history & alerts ───────────────────────────────────────

def _load_data() -> Dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if PRICES_FILE.exists():
        try:
            with open(PRICES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"history": [], "alerts": []}


def _save_data(data: Dict[str, Any]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PRICES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _save_price_history(result: Dict[str, Any]):
    """Save a price snapshot to history (keep last 30 days)."""
    data = _load_data()
    data["history"].append({
        "gold": result["gold"]["price"],
        "silver": result["silver"]["price"],
        "source": result["source"],
        "timestamp": result["timestamp"],
    })
    # Keep last 30 days (assuming ~288 checks/day at 5min intervals = 8640, cap at 10000)
    data["history"] = data["history"][-10000:]
    _save_data(data)


def get_price_history(metal: str = "gold", days: int = 7) -> List[Dict[str, Any]]:
    """Get price history for a metal over N days."""
    data = _load_data()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    return [
        h for h in data["history"]
        if h["timestamp"] >= cutoff
    ]


# ── Price alerts ─────────────────────────────────────────────────

def set_price_alert(
    metal: str,
    condition: str,  # "above" or "below"
    price: float,
    notify: bool = True,
) -> Dict[str, Any]:
    """Set a price alert for gold or silver."""
    metal = metal.lower()
    if metal not in METALS:
        raise ValueError(f"Invalid metal '{metal}'. Choose: gold, silver")
    if condition not in ("above", "below"):
        raise ValueError("Condition must be 'above' or 'below'")

    data = _load_data()
    alert = {
        "id": f"{metal}-{condition}-{int(price)}",
        "metal": metal,
        "condition": condition,
        "target_price": price,
        "notify": notify,
        "created_at": datetime.now().isoformat(),
        "triggered": False,
        "triggered_at": None,
    }
    # Remove existing alert with same id
    data["alerts"] = [a for a in data["alerts"] if a["id"] != alert["id"]]
    data["alerts"].append(alert)
    _save_data(data)
    return alert


def check_price_alerts(current_prices: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check if any price alerts have been triggered."""
    data = _load_data()
    triggered = []

    for alert in data["alerts"]:
        if alert["triggered"]:
            continue

        metal = alert["metal"]
        current = current_prices.get(metal, {}).get("price")
        if current is None:
            continue

        target = alert["target_price"]
        condition = alert["condition"]

        hit = (condition == "above" and current >= target) or \
              (condition == "below" and current <= target)

        if hit:
            alert["triggered"] = True
            alert["triggered_at"] = datetime.now().isoformat()
            alert["triggered_price"] = current
            triggered.append(alert)

            # Send email if configured
            if alert.get("notify"):
                try:
                    from email_notifier import send_email, is_configured
                    if is_configured():
                        metal_name = METALS[metal]["name"]
                        direction = "risen above" if condition == "above" else "fallen below"
                        subject = f"PRICE ALERT: {metal_name} has {direction} ${target:.2f}"
                        body = (
                            f"{metal_name} Price Alert Triggered!\n\n"
                            f"Condition: {metal_name} {condition} ${target:.2f}\n"
                            f"Current price: ${current:.2f}\n"
                            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        send_email(subject, body, "critical")
                except Exception:
                    pass

    if triggered:
        _save_data(data)

    return triggered


def list_price_alerts() -> List[Dict[str, Any]]:
    """List all active price alerts."""
    data = _load_data()
    return data.get("alerts", [])


def delete_price_alert(alert_id: str) -> bool:
    """Delete a price alert."""
    data = _load_data()
    before = len(data["alerts"])
    data["alerts"] = [a for a in data["alerts"] if a["id"] != alert_id]
    if len(data["alerts"]) < before:
        _save_data(data)
        return True
    return False
