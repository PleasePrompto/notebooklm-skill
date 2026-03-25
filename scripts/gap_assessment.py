#!/usr/bin/env python3
"""
Gap Assessment Tool
Analyzes uploaded documents (policies, procedures, regulations) against
compliance requirements and identifies gaps.
"""

import json
import sys
import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
GAP_DIR = DATA_DIR / "gap_assessments"

# ── Compliance requirement frameworks ────────────────────────────

FRAMEWORKS = {
    "cbuae_aml": {
        "name": "CBUAE AML/CFT Requirements",
        "authority": "CBUAE",
        "requirements": [
            {"id": "CBUAE-01", "title": "AML/CFT Policy", "description": "Written AML/CFT policy approved by senior management", "category": "governance", "keywords": ["aml policy", "anti-money laundering policy", "cft policy", "board approved"]},
            {"id": "CBUAE-02", "title": "Risk Assessment", "description": "Enterprise-wide ML/TF risk assessment", "category": "risk", "keywords": ["risk assessment", "ml/tf risk", "enterprise risk", "risk-based approach"]},
            {"id": "CBUAE-03", "title": "Compliance Officer", "description": "Designated Compliance Officer / MLRO registered with CBUAE", "category": "governance", "keywords": ["compliance officer", "mlro", "money laundering reporting officer", "designated officer"]},
            {"id": "CBUAE-04", "title": "KYC/CDD Procedures", "description": "Customer Due Diligence procedures for identification and verification", "category": "kyc", "keywords": ["kyc", "customer due diligence", "cdd", "identification", "verification", "identity"]},
            {"id": "CBUAE-05", "title": "Enhanced Due Diligence", "description": "EDD procedures for high-risk clients, PEPs, and complex structures", "category": "kyc", "keywords": ["enhanced due diligence", "edd", "pep", "politically exposed", "high risk", "high-risk"]},
            {"id": "CBUAE-06", "title": "Ongoing Monitoring", "description": "Continuous monitoring of transactions and client activity", "category": "monitoring", "keywords": ["ongoing monitoring", "transaction monitoring", "continuous monitoring", "surveillance"]},
            {"id": "CBUAE-07", "title": "STR Filing", "description": "Procedures for filing Suspicious Transaction Reports via goAML", "category": "reporting", "keywords": ["suspicious transaction", "str", "sar", "goaml", "suspicious activity"]},
            {"id": "CBUAE-08", "title": "Sanctions Screening", "description": "Screening against UN, EU, UK, OFAC, UAE sanctions lists", "category": "sanctions", "keywords": ["sanctions", "screening", "sanctioned", "designated persons", "frozen assets"]},
            {"id": "CBUAE-09", "title": "Record Keeping", "description": "Maintain records for minimum 5 years after relationship ends", "category": "records", "keywords": ["record keeping", "record retention", "5 years", "five years", "documentation"]},
            {"id": "CBUAE-10", "title": "Staff Training", "description": "Regular AML/CFT training for all staff", "category": "training", "keywords": ["training", "awareness", "staff training", "employee training", "aml training"]},
            {"id": "CBUAE-11", "title": "Independent Audit", "description": "Annual independent audit of AML/CFT program", "category": "audit", "keywords": ["independent audit", "internal audit", "external audit", "annual audit"]},
            {"id": "CBUAE-12", "title": "Beneficial Ownership", "description": "Identification of Ultimate Beneficial Owners (UBO)", "category": "kyc", "keywords": ["beneficial owner", "ubo", "ultimate beneficial", "ownership structure"]},
            {"id": "CBUAE-13", "title": "Wire Transfer Rules", "description": "Originator and beneficiary information for wire transfers", "category": "monitoring", "keywords": ["wire transfer", "originator", "beneficiary", "funds transfer"]},
            {"id": "CBUAE-14", "title": "Correspondent Banking", "description": "Due diligence for correspondent banking relationships", "category": "kyc", "keywords": ["correspondent bank", "respondent", "nested", "payable-through"]},
            {"id": "CBUAE-15", "title": "New Technologies", "description": "Risk assessment for new products, services, and technologies", "category": "risk", "keywords": ["new product", "new technology", "fintech", "virtual asset", "digital"]},
        ]
    },
    "fatf_recommendations": {
        "name": "FATF 40 Recommendations (Key Areas)",
        "authority": "FATF",
        "requirements": [
            {"id": "FATF-R1", "title": "Risk Assessment & RBA", "description": "Countries should apply a risk-based approach", "category": "risk", "keywords": ["risk-based approach", "rba", "risk assessment", "national risk"]},
            {"id": "FATF-R10", "title": "Customer Due Diligence", "description": "CDD measures when establishing business relationships", "category": "kyc", "keywords": ["customer due diligence", "cdd", "business relationship", "verification"]},
            {"id": "FATF-R12", "title": "PEPs", "description": "Enhanced measures for Politically Exposed Persons", "category": "kyc", "keywords": ["pep", "politically exposed", "senior political", "public function"]},
            {"id": "FATF-R15", "title": "New Technologies", "description": "Risk assessment of new technologies including virtual assets", "category": "risk", "keywords": ["new technologies", "virtual asset", "vasp", "innovation"]},
            {"id": "FATF-R20", "title": "Suspicious Transaction Reporting", "description": "Report suspicions of ML/TF to FIU", "category": "reporting", "keywords": ["suspicious transaction", "str", "fiu", "reporting"]},
            {"id": "FATF-R24", "title": "Beneficial Ownership (Legal Persons)", "description": "Transparency of beneficial ownership of legal persons", "category": "kyc", "keywords": ["beneficial ownership", "legal person", "transparency", "company"]},
            {"id": "FATF-R25", "title": "Beneficial Ownership (Legal Arrangements)", "description": "Transparency of beneficial ownership of trusts", "category": "kyc", "keywords": ["trust", "legal arrangement", "settlor", "trustee"]},
        ]
    },
    "lbma_rgd": {
        "name": "LBMA Responsible Gold/Silver Due Diligence",
        "authority": "LBMA",
        "requirements": [
            {"id": "LBMA-01", "title": "Management System", "description": "Establish strong management systems for supply chain due diligence", "category": "governance", "keywords": ["management system", "supply chain", "due diligence", "responsible sourcing"]},
            {"id": "LBMA-02", "title": "Risk Identification", "description": "Identify and assess risks in the gold/silver supply chain", "category": "risk", "keywords": ["supply chain risk", "conflict", "high-risk area", "conflict-affected"]},
            {"id": "LBMA-03", "title": "Risk Mitigation", "description": "Design and implement strategy to respond to identified risks", "category": "risk", "keywords": ["risk mitigation", "risk response", "corrective action", "risk management"]},
            {"id": "LBMA-04", "title": "Independent Audit", "description": "Third-party audit of supply chain due diligence", "category": "audit", "keywords": ["third party audit", "independent audit", "assurance", "external review"]},
            {"id": "LBMA-05", "title": "KYC for Counterparties", "description": "Know Your Counterparty procedures for all supply chain participants", "category": "kyc", "keywords": ["counterparty", "kyc", "supplier", "refiner", "miner"]},
            {"id": "LBMA-06", "title": "Transaction Due Diligence", "description": "Due diligence on individual transactions for recycled/mined material", "category": "monitoring", "keywords": ["transaction due diligence", "recycled", "mined", "material origin"]},
            {"id": "LBMA-07", "title": "AML/CFT Compliance", "description": "Ensure compliance with all applicable AML/CFT regulations", "category": "sanctions", "keywords": ["aml", "cft", "money laundering", "terrorist financing", "sanctions"]},
        ]
    },
}

# ── Compliance checklist categories ──────────────────────────────
CATEGORIES = ["governance", "risk", "kyc", "monitoring", "reporting", "sanctions", "records", "training", "audit"]


def run_gap_assessment(
    document_text: str,
    document_name: str = "Uploaded Document",
    framework: str = "cbuae_aml",
    additional_frameworks: str = "",
) -> Dict[str, Any]:
    """Analyze document text against compliance requirements and identify gaps.

    Args:
        document_text: The text content of the document to assess
        document_name: Name/title of the document
        framework: Primary framework to assess against
        additional_frameworks: Comma-separated additional frameworks
    """
    GAP_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TIMEZONE)
    assessment_id = f"GAP-{now.strftime('%Y%m%d-%H%M%S')}"

    # Determine frameworks to check
    frameworks_to_check = [framework]
    if additional_frameworks:
        for f in additional_frameworks.split(","):
            f = f.strip().lower()
            if f in FRAMEWORKS and f not in frameworks_to_check:
                frameworks_to_check.append(f)

    doc_lower = document_text.lower()
    doc_words = set(re.findall(r'\b\w+\b', doc_lower))

    results = {}
    total_reqs = 0
    total_covered = 0
    total_gaps = 0
    total_partial = 0

    for fw_key in frameworks_to_check:
        fw = FRAMEWORKS.get(fw_key)
        if not fw:
            continue

        fw_results = {
            "framework": fw["name"],
            "authority": fw["authority"],
            "requirements": [],
            "covered": 0,
            "partial": 0,
            "gaps": 0,
        }

        for req in fw["requirements"]:
            # Score how well the document covers this requirement
            score = _score_coverage(doc_lower, doc_words, req)
            status = "covered" if score >= 70 else "partial" if score >= 30 else "gap"

            fw_results["requirements"].append({
                "id": req["id"],
                "title": req["title"],
                "description": req["description"],
                "category": req["category"],
                "coverage_score": score,
                "status": status,
                "matched_keywords": _find_matched_keywords(doc_lower, req["keywords"]),
                "recommendation": _get_recommendation(req, status),
            })

            if status == "covered":
                fw_results["covered"] += 1
                total_covered += 1
            elif status == "partial":
                fw_results["partial"] += 1
                total_partial += 1
            else:
                fw_results["gaps"] += 1
                total_gaps += 1
            total_reqs += 1

        results[fw_key] = fw_results

    # Overall score
    overall_score = round(((total_covered * 100) + (total_partial * 50)) / max(total_reqs, 1), 1)

    assessment = {
        "assessment_id": assessment_id,
        "document_name": document_name,
        "assessed_at": now.isoformat(),
        "frameworks_checked": frameworks_to_check,
        "overall_score": overall_score,
        "summary": {
            "total_requirements": total_reqs,
            "covered": total_covered,
            "partial": total_partial,
            "gaps": total_gaps,
        },
        "results": results,
        "priority_actions": _get_priority_actions(results),
    }

    # Save assessment
    save_path = GAP_DIR / f"{assessment_id}.json"
    with open(save_path, "w") as f:
        json.dump(assessment, f, indent=2)

    # Log to audit trail
    try:
        from audit_trail import log_action
        log_action(f"Gap assessment: {document_name}", "compliance",
                   details={"assessment_id": assessment_id, "score": overall_score})
    except Exception:
        pass

    assessment["path"] = str(save_path)
    return assessment


def _score_coverage(doc_lower: str, doc_words: set, requirement: Dict) -> int:
    """Score how well a document covers a requirement (0-100)."""
    keywords = requirement["keywords"]
    if not keywords:
        return 0

    matches = 0
    total_weight = 0

    for kw in keywords:
        weight = 2 if len(kw.split()) > 1 else 1  # Multi-word phrases weighted more
        total_weight += weight

        if kw.lower() in doc_lower:
            matches += weight
        else:
            # Check individual words of multi-word keywords
            kw_words = set(kw.lower().split())
            if kw_words and kw_words.issubset(doc_words):
                matches += weight * 0.5

    return min(100, int((matches / max(total_weight, 1)) * 100))


def _find_matched_keywords(doc_lower: str, keywords: List[str]) -> List[str]:
    """Find which keywords appear in the document."""
    return [kw for kw in keywords if kw.lower() in doc_lower]


def _get_recommendation(req: Dict, status: str) -> str:
    """Generate a recommendation based on gap status."""
    if status == "covered":
        return "Requirement appears adequately addressed. Verify implementation."
    elif status == "partial":
        return f"Partially addressed. Review and strengthen coverage of: {req['description']}"
    else:
        return f"GAP: No coverage found for '{req['title']}'. Add procedures for: {req['description']}"


def _get_priority_actions(results: Dict) -> List[Dict[str, str]]:
    """Extract priority actions from gaps."""
    actions = []
    for fw_key, fw_result in results.items():
        for req in fw_result["requirements"]:
            if req["status"] == "gap":
                actions.append({
                    "priority": "high",
                    "framework": fw_result["framework"],
                    "requirement": req["id"],
                    "title": req["title"],
                    "action": req["recommendation"],
                })
            elif req["status"] == "partial":
                actions.append({
                    "priority": "medium",
                    "framework": fw_result["framework"],
                    "requirement": req["id"],
                    "title": req["title"],
                    "action": req["recommendation"],
                })
    # Sort: gaps first, then partial
    actions.sort(key=lambda x: 0 if x["priority"] == "high" else 1)
    return actions


def list_assessments() -> List[Dict[str, Any]]:
    """List all gap assessments."""
    GAP_DIR.mkdir(parents=True, exist_ok=True)
    assessments = []
    for f in sorted(GAP_DIR.glob("GAP-*.json"), reverse=True):
        try:
            with open(f, "r") as fp:
                data = json.load(fp)
            assessments.append({
                "assessment_id": data["assessment_id"],
                "document_name": data["document_name"],
                "overall_score": data["overall_score"],
                "frameworks": data["frameworks_checked"],
                "gaps": data["summary"]["gaps"],
                "assessed_at": data["assessed_at"],
                "path": str(f),
            })
        except Exception:
            pass
    return assessments


def get_frameworks() -> Dict[str, Any]:
    """Return available compliance frameworks."""
    return {
        key: {"name": fw["name"], "authority": fw["authority"], "requirements": len(fw["requirements"])}
        for key, fw in FRAMEWORKS.items()
    }
