#!/usr/bin/env python3
"""
FATF High-Risk and Grey List Countries
Pre-loaded list of FATF-identified jurisdictions for client screening.
Updated: February 2025 FATF plenary.
"""

import sys
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent))

# FATF Black List — High-Risk Jurisdictions Subject to Call for Action
# These countries have significant strategic deficiencies in AML/CFT
BLACKLIST = [
    {"country": "Iran", "code": "IR", "since": "2009", "reason": "Strategic AML/CFT deficiencies, lack of compliance"},
    {"country": "Myanmar", "code": "MM", "since": "2022", "reason": "Strategic AML/CFT deficiencies"},
    {"country": "North Korea (DPRK)", "code": "KP", "since": "2011", "reason": "WMD proliferation financing, sanctions evasion"},
]

# FATF Grey List — Jurisdictions Under Increased Monitoring
# Countries with strategic deficiencies that have committed to action plans
GREYLIST = [
    {"country": "Algeria", "code": "DZ", "since": "2024"},
    {"country": "Angola", "code": "AO", "since": "2024"},
    {"country": "Bulgaria", "code": "BG", "since": "2024"},
    {"country": "Burkina Faso", "code": "BF", "since": "2021"},
    {"country": "Cameroon", "code": "CM", "since": "2023"},
    {"country": "Côte d'Ivoire", "code": "CI", "since": "2024"},
    {"country": "Croatia", "code": "HR", "since": "2024"},
    {"country": "Democratic Republic of Congo", "code": "CD", "since": "2022"},
    {"country": "Haiti", "code": "HT", "since": "2021"},
    {"country": "Kenya", "code": "KE", "since": "2024"},
    {"country": "Lebanon", "code": "LB", "since": "2024"},
    {"country": "Mali", "code": "ML", "since": "2022"},
    {"country": "Monaco", "code": "MC", "since": "2024"},
    {"country": "Mozambique", "code": "MZ", "since": "2022"},
    {"country": "Namibia", "code": "NA", "since": "2024"},
    {"country": "Nepal", "code": "NP", "since": "2024"},
    {"country": "Nigeria", "code": "NG", "since": "2023"},
    {"country": "Philippines", "code": "PH", "since": "2024"},
    {"country": "South Africa", "code": "ZA", "since": "2023"},
    {"country": "South Sudan", "code": "SS", "since": "2022"},
    {"country": "Syria", "code": "SY", "since": "2010"},
    {"country": "Tanzania", "code": "TZ", "since": "2022"},
    {"country": "Venezuela", "code": "VE", "since": "2024"},
    {"country": "Vietnam", "code": "VN", "since": "2024"},
    {"country": "Yemen", "code": "YE", "since": "2022"},
]

# UAE CBUAE additional high-risk countries (supplements FATF)
UAE_HIGH_RISK = [
    {"country": "Afghanistan", "code": "AF", "reason": "Terrorism financing, sanctions"},
    {"country": "Libya", "code": "LY", "reason": "Political instability, sanctions"},
    {"country": "Somalia", "code": "SO", "reason": "Terrorism financing"},
    {"country": "Sudan", "code": "SD", "reason": "Sanctions, conflict"},
    {"country": "Iraq", "code": "IQ", "reason": "Terrorism financing, sanctions"},
]

# All high-risk country codes for quick lookup
ALL_HIGH_RISK_CODES = set(
    [c["code"] for c in BLACKLIST] +
    [c["code"] for c in GREYLIST] +
    [c["code"] for c in UAE_HIGH_RISK]
)

ALL_HIGH_RISK_NAMES = set(
    [c["country"].lower() for c in BLACKLIST] +
    [c["country"].lower() for c in GREYLIST] +
    [c["country"].lower() for c in UAE_HIGH_RISK]
)


def _match_country(country_lower: str, country_upper: str, entry: Dict) -> bool:
    """Flexible country matching: exact, code, or substring."""
    entry_lower = entry["country"].lower()
    return (country_lower == entry_lower
            or country_upper == entry["code"]
            or country_lower in entry_lower
            or entry_lower.startswith(country_lower))


def check_country(country: str) -> Dict[str, Any]:
    """Check if a country is on any high-risk list."""
    country_lower = country.lower().strip()
    country_upper = country.upper().strip()

    result = {
        "country": country,
        "blacklisted": False,
        "greylisted": False,
        "uae_high_risk": False,
        "risk_level": "standard",
        "details": [],
    }

    for c in BLACKLIST:
        if _match_country(country_lower, country_upper, c):
            result["blacklisted"] = True
            result["risk_level"] = "prohibited"
            result["details"].append({"list": "FATF Blacklist", **c})

    for c in GREYLIST:
        if _match_country(country_lower, country_upper, c):
            result["greylisted"] = True
            if result["risk_level"] == "standard":
                result["risk_level"] = "high"
            result["details"].append({"list": "FATF Greylist", **c})

    for c in UAE_HIGH_RISK:
        if _match_country(country_lower, country_upper, c):
            result["uae_high_risk"] = True
            if result["risk_level"] == "standard":
                result["risk_level"] = "high"
            result["details"].append({"list": "UAE/CBUAE High Risk", **c})

    return result


def check_nationality(nationality: str) -> Dict[str, Any]:
    """Check a client's nationality against risk lists. Alias for check_country."""
    return check_country(nationality)


def get_all_lists() -> Dict[str, Any]:
    """Return all risk country lists."""
    return {
        "blacklist": BLACKLIST,
        "greylist": GREYLIST,
        "uae_high_risk": UAE_HIGH_RISK,
        "total_high_risk_countries": len(ALL_HIGH_RISK_CODES),
    }


def get_fatf_summary() -> Dict[str, Any]:
    return {
        "blacklist_count": len(BLACKLIST),
        "greylist_count": len(GREYLIST),
        "uae_additional_count": len(UAE_HIGH_RISK),
        "total": len(ALL_HIGH_RISK_CODES),
        "last_updated": "February 2025 FATF Plenary",
    }
