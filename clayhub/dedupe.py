"""Deterministic contact and company matching."""
from dataclasses import fields
from difflib import SequenceMatcher
import re

from .models import DedupeMatch, Lead
from .hubspot.client import HubSpotClient


def _company_name(name):
    words = re.findall(r'\w+', name.casefold())
    return ' '.join(word for word in words if word not in {'inc', 'llc', 'ltd', 'gmbh'})


def _filled(lead):
    excluded = {'row_id', 'sources', 'flags', 'score', 'tier', 'score_reasons'}
    return sum(getattr(lead, field.name) not in ('', None) for field in fields(Lead) if field.name not in excluded)


def dedupe(leads: list[Lead], hubspot: HubSpotClient) -> list[DedupeMatch]:
    winners = {}
    for index, lead in enumerate(leads):
        email = lead.email.strip().casefold()
        if email and not {'invalid_email', 'disposable'}.intersection(lead.flags):
            previous = winners.get(email)
            if previous is None or _filled(lead) > _filled(leads[previous]):
                winners[email] = index
    matches = []
    for index, lead in enumerate(leads):
        email = lead.email.strip().casefold()
        if email in winners and winners[email] != index:
            matches.append(DedupeMatch(lead.row_id, 'skip_duplicate_in_batch', None, None, 'email'))
            continue
        if not email or {'invalid_email', 'disposable'}.intersection(lead.flags):
            matches.append(DedupeMatch(lead.row_id, 'create', None, None, 'none'))
            continue
        contact = hubspot.search_contact_by_email(email)
        company = hubspot.search_company_by_domain(lead.domain) if lead.domain else None
        matched_on = 'email' if contact else 'domain' if company else 'none'
        if company is None and _company_name(lead.company):
            candidates = hubspot.search_company_by_name(lead.company)
            ranked = [(SequenceMatcher(None, _company_name(lead.company), _company_name(item['properties'].get('name', ''))).ratio(), item) for item in candidates]
            if ranked:
                ratio, candidate = max(ranked, key=lambda pair: pair[0])
                if ratio >= 0.88:
                    company = candidate
                    if contact is None:
                        matched_on = 'company_name'
        matches.append(DedupeMatch(lead.row_id, 'update' if contact or company else 'create',
                                   str(contact['id']) if contact else None,
                                   str(company['id']) if company else None, matched_on))
    return matches
