"""Config-driven ICP scoring."""
import json
from pathlib import Path

from .models import Lead
from .normalize import seniority


def load_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def score_lead(lead: Lead, config: dict) -> Lead:
    score = 0
    reasons = []
    for rule in config.get("rules", []):
        field, op, expected = rule.get("field"), rule.get("op"), rule.get("value")
        actual = getattr(lead, field, None)
        matched = False
        if op == "between" and actual is not None:
            matched = expected[0] <= actual <= expected[1]
        elif op == "in":
            matched = actual in expected
        elif op == "seniority_at_least":
            ladder = {"ic": 0, "senior": 2, "manager": 3, "director": 4, "head": 5, "vp": 6, "owner": 7, "founder": 7, "ceo": 7, "cxo": 7}
            matched = seniority(lead.title) >= ladder.get(str(expected).lower(), 0)
        elif op == "not_contains":
            matched = expected not in (actual or [])
        if matched:
            score += int(rule.get("points", 0))
            reasons.append(str(rule.get("reason", f"Matched {field}")))
    lead.score = min(100, max(0, score))
    thresholds = config.get("tiers", {"A": 80, "B": 60, "C": 40})
    lead.tier = next((tier for tier in ("A", "B", "C") if lead.score >= thresholds.get(tier, 101)), "D")
    if "role_address" in lead.flags and lead.tier in ("A", "B"):
        lead.tier = "C"
    lead.score_reasons = reasons
    return lead
