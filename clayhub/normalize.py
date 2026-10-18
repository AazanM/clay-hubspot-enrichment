"""Normalization helpers for Clay lead records."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import Lead

_COUNTRIES = {
    "united states": "US", "united states of america": "US", "usa": "US", "us": "US",
    "united kingdom": "GB", "great britain": "GB", "uk": "GB", "gb": "GB",
    "canada": "CA", "ca": "CA", "australia": "AU", "au": "AU",
    "germany": "DE", "de": "DE", "netherlands": "NL", "the netherlands": "NL", "nl": "NL",
    "france": "FR", "india": "IN", "ireland": "IE", "singapore": "SG",
}
_SENIORITY = (
    (7, ("owner", "founder", "chief executive", "ceo", "cxo", "chief ")),
    (6, ("vp", "vice president")),
    (5, ("head of", "head ")),
    (4, ("director",)),
    (3, ("manager",)),
    (2, ("senior", "sr.")),
    (1, ("junior", "jr.")),
)


def seniority(title: str) -> int:
    value = (title or "").strip().lower()
    for level, terms in _SENIORITY:
        if any(term in value for term in terms):
            return level
    return 0


def _domain_from_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else "//" + value)
    return (parsed.hostname or "").lower().removeprefix("www.").rstrip(".")


def normalize_lead(lead: Lead) -> Lead:
    lead.first_name = " ".join(lead.first_name.strip().split()).title()
    lead.last_name = " ".join(lead.last_name.strip().split()).title()
    lead.email = lead.email.strip().lower()
    domain = (lead.domain or "").strip()
    if not domain and "@" in lead.email:
        domain = lead.email.rsplit("@", 1)[-1]
    lead.domain = _domain_from_url(domain)
    if not lead.domain and lead.linkedin_url:
        # A LinkedIn URL is not a company domain; leave it unknown.
        pass
    country = (lead.country or "").strip()
    lead.country = _COUNTRIES.get(country.lower(), country.upper() if len(country) == 2 else country)
    if isinstance(lead.employees, str):
        try:
            lead.employees = int(re.sub(r"[,\s]", "", lead.employees))
        except ValueError:
            lead.employees = None
    return lead
