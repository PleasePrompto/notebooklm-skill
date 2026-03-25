#!/usr/bin/env python3
"""
Currency Exchange Rate Tracker
Fetches live exchange rates for AED, USD, EUR, GBP and other currencies.
Supports rate alerts and history tracking.
"""

import json
import sys
import urllib.request
import ssl
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
RATES_FILE = DATA_DIR / "exchange_rates.json"

# Default currencies relevant to UAE/compliance
DEFAULT_CURRENCIES = ["AED", "USD", "EUR", "GBP", "CHF", "SAR", "INR", "CNY"]
BASE_CURRENCY = "USD"


def _make_request(url: str) -> str:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; RateTracker/1.0)")
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        return resp.read().decode("utf-8")


# ── Rate fetching ────────────────────────────────────────────────

def fetch_rates(base: str = "USD", currencies: Optional[List[str]] = None) -> Dict[str, Any]:
    """Fetch current exchange rates.

    Uses free APIs in order:
      1. exchangerate.host
      2. frankfurter.app (ECB data)
    """
    if not currencies:
        currencies = DEFAULT_CURRENCIES

    base = base.upper()
    targets = ",".join([c.upper() for c in currencies if c.upper() != base])
    errors = []

    # Source 1: exchangerate.host (free, no key)
    try:
        url = f"https://api.exchangerate.host/latest?base={base}&symbols={targets}"
        data = json.loads(_make_request(url))
        if data.get("success") or data.get("rates"):
            return _build_rate_result(base, data.get("rates", {}), "exchangerate.host")
    except Exception as e:
        errors.append(f"exchangerate.host: {e}")

    # Source 2: frankfurter.app (ECB, free)
    try:
        url = f"https://api.frankfurter.app/latest?from={base}&to={targets}"
        data = json.loads(_make_request(url))
        if data.get("rates"):
            return _build_rate_result(base, data["rates"], "frankfurter.app (ECB)")
    except Exception as e:
        errors.append(f"frankfurter.app: {e}")

    # Source 3: open.er-api.com (free)
    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        data = json.loads(_make_request(url))
        if data.get("rates"):
            filtered = {k: v for k, v in data["rates"].items() if k in [c.upper() for c in currencies]}
            return _build_rate_result(base, filtered, "open.er-api.com")
    except Exception as e:
        errors.append(f"open.er-api.com: {e}")

    return {"error": f"Could not fetch rates. Tried: {'; '.join(errors)}"}


def _build_rate_result(base: str, rates: Dict[str, float], source: str) -> Dict[str, Any]:
    now = datetime.now(TIMEZONE)
    result = {
        "base": base,
        "rates": {k: round(v, 4) for k, v in rates.items()},
        "source": source,
        "timestamp": now.isoformat(),
    }

    # Add AED cross-rates if base is USD (1 USD = 3.6725 AED fixed peg)
    if base == "USD" and "AED" not in rates:
        result["rates"]["AED"] = 3.6725

    # Save history
    _save_rate_history(result)
    return result


def convert(amount: float, from_curr: str, to_curr: str) -> Dict[str, Any]:
    """Convert an amount between currencies."""
    from_curr = from_curr.upper()
    to_curr = to_curr.upper()

    rates_data = fetch_rates("USD", [from_curr, to_curr])
    if "error" in rates_data:
        return rates_data

    rates = rates_data["rates"]

    # Convert via USD
    if from_curr == "USD":
        from_rate = 1.0
    elif from_curr in rates:
        from_rate = rates[from_curr]
    else:
        return {"error": f"Rate not available for {from_curr}"}

    if to_curr == "USD":
        to_rate = 1.0
    elif to_curr in rates:
        to_rate = rates[to_curr]
    else:
        return {"error": f"Rate not available for {to_curr}"}

    # amount in from_curr -> USD -> to_curr
    usd_amount = amount / from_rate
    converted = usd_amount * to_rate

    return {
        "from": from_curr,
        "to": to_curr,
        "amount": amount,
        "converted": round(converted, 4),
        "rate": round(to_rate / from_rate, 6),
        "source": rates_data["source"],
        "timestamp": rates_data["timestamp"],
    }


# ── History ──────────────────────────────────────────────────────

def _load_data() -> Dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if RATES_FILE.exists():
        try:
            with open(RATES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"history": [], "alerts": []}


def _save_data(data: Dict[str, Any]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(RATES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _save_rate_history(result: Dict[str, Any]):
    data = _load_data()
    data["history"].append({
        "base": result["base"],
        "rates": result["rates"],
        "source": result["source"],
        "timestamp": result["timestamp"],
    })
    data["history"] = data["history"][-10000:]
    _save_data(data)


def get_rate_history(currency: str = "AED", days: int = 7) -> List[Dict[str, Any]]:
    currency = currency.upper()
    data = _load_data()
    cutoff = (datetime.now(TIMEZONE) - timedelta(days=days)).isoformat()
    results = []
    for h in data["history"]:
        if h["timestamp"] >= cutoff and currency in h.get("rates", {}):
            results.append({
                "rate": h["rates"][currency],
                "base": h["base"],
                "timestamp": h["timestamp"],
            })
    return results


# ── Rate alerts ──────────────────────────────────────────────────

def set_rate_alert(
    currency: str,
    condition: str,
    rate: float,
    base: str = "USD",
    notify: bool = True,
) -> Dict[str, Any]:
    currency = currency.upper()
    base = base.upper()
    if condition not in ("above", "below"):
        raise ValueError("Condition must be 'above' or 'below'")

    data = _load_data()
    alert = {
        "id": f"{base}-{currency}-{condition}-{rate}",
        "base": base,
        "currency": currency,
        "condition": condition,
        "target_rate": rate,
        "notify": notify,
        "created_at": datetime.now(TIMEZONE).isoformat(),
        "triggered": False,
        "triggered_at": None,
    }
    data["alerts"] = [a for a in data["alerts"] if a["id"] != alert["id"]]
    data["alerts"].append(alert)
    _save_data(data)
    return alert


def check_rate_alerts(current_rates: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = _load_data()
    triggered = []
    rates = current_rates.get("rates", {})

    for alert in data["alerts"]:
        if alert["triggered"]:
            continue
        currency = alert["currency"]
        current = rates.get(currency)
        if current is None:
            continue

        hit = (alert["condition"] == "above" and current >= alert["target_rate"]) or \
              (alert["condition"] == "below" and current <= alert["target_rate"])

        if hit:
            alert["triggered"] = True
            alert["triggered_at"] = datetime.now(TIMEZONE).isoformat()
            alert["triggered_rate"] = current
            triggered.append(alert)

            if alert.get("notify"):
                try:
                    from email_notifier import send_email, is_configured
                    if is_configured():
                        direction = "risen above" if alert["condition"] == "above" else "fallen below"
                        subject = f"RATE ALERT: {alert['base']}/{currency} has {direction} {alert['target_rate']}"
                        body = (
                            f"Exchange Rate Alert!\n\n"
                            f"{alert['base']}/{currency} {alert['condition']} {alert['target_rate']}\n"
                            f"Current rate: {current}\n"
                            f"Time: {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')} Dubai"
                        )
                        send_email(subject, body, "high")
                except Exception:
                    pass

    if triggered:
        _save_data(data)
    return triggered


def list_rate_alerts() -> List[Dict[str, Any]]:
    return _load_data().get("alerts", [])


def delete_rate_alert(alert_id: str) -> bool:
    data = _load_data()
    before = len(data["alerts"])
    data["alerts"] = [a for a in data["alerts"] if a["id"] != alert_id]
    if len(data["alerts"]) < before:
        _save_data(data)
        return True
    return False
