"""Build reviewable plans, then apply company/contact/association batches."""
from __future__ import annotations

import json

from ..models import DedupeMatch, Lead, SyncPlan
from .client import HubSpotClient


def build_plan(leads: list[Lead], matches: list[DedupeMatch], config: dict) -> SyncPlan:
    plan = SyncPlan()
    by_row = {match.lead_row_id: match for match in matches}
    company_entries = {}
    for lead in leads:
        match = by_row[lead.row_id]
        if (not lead.email or {'invalid_email', 'disposable'}.intersection(lead.flags)
                or match.action == 'skip_duplicate_in_batch'):
            continue
        email = lead.email.strip().casefold()
        domain = lead.domain.strip().casefold()
        properties = {key: value for key, value in {
            'email': email, 'firstname': lead.first_name, 'lastname': lead.last_name,
            'jobtitle': lead.title, 'company': lead.company, 'phone': lead.phone,
            'country': lead.country}.items() if value != ''}
        for prop, field_name in config.get('hubspot', {}).get('contact_props', {}).items():
            value = getattr(lead, field_name)
            if field_name == 'tier' and 'role_address' in lead.flags and value in {'A', 'B'}:
                value = 'C'
            if isinstance(value, (dict, list)):
                value = json.dumps(value, sort_keys=True)
            if value is not None:
                properties[prop] = value
        entry = {'properties': properties}
        if match.contact_id:
            entry['id'] = match.contact_id
            plan.contacts_update.append(entry)
        else:
            entry.update(id=email, idProperty='email')
            plan.contacts_create.append(entry)
        # A matched company can be associated even when this lead has no domain.
        company_key = domain or match.company_id
        if company_key:
            identity = ('id', match.company_id) if match.company_id else ('domain', domain)
            if identity not in company_entries:
                company_props = {key: value for key, value in {'domain': domain, 'name': lead.company}.items() if value}
                company_entry = {'properties': company_props}
                if match.company_id:
                    company_entry['id'] = match.company_id
                    plan.companies_update.append(company_entry)
                else:
                    company_entry.update(id=domain, idProperty='domain')
                    plan.companies_create.append(company_entry)
                company_entries[identity] = company_key
            company_key = company_entries[identity]
            pair = (email, company_key)
            if pair not in plan.associations:
                plan.associations.append(pair)
    return plan


def plan_counts(plan: SyncPlan) -> dict[str, int]:
    return {'companies_created': len(plan.companies_create), 'companies_updated': len(plan.companies_update),
            'contacts_created': len(plan.contacts_create), 'contacts_updated': len(plan.contacts_update),
            'associations': len(plan.associations)}


def apply_plan(plan: SyncPlan, client: HubSpotClient) -> dict[str, int]:
    ids = {'companies': {}, 'contacts': {}}
    counts = plan_counts(plan)
    for object_type, prop, creates, updates in [
        ('companies', 'domain', plan.companies_create, plan.companies_update),
        ('contacts', 'email', plan.contacts_create, plan.contacts_update)]:
        # Keep updates separate so returned IDs also resolve companies without domains.
        for entries in (creates, updates):
            for offset in range(0, len(entries), 100):
                batch = entries[offset:offset + 100]
                results = client.batch_upsert(object_type, prop, batch)
                if len(results) != len(batch):
                    raise RuntimeError(f'Incomplete HubSpot {object_type} batch')
                for result in results:
                    result_id = str(result['id'])
                    ids[object_type][result_id] = result_id
                    key = result.get('properties', {}).get(prop)
                    if key:
                        ids[object_type][key.casefold()] = result_id
    pairs = [(ids['contacts'][email], ids['companies'][domain]) for email, domain in plan.associations]
    applied = 0
    for offset in range(0, len(pairs), 100):
        applied += client.associate_contacts_companies(pairs[offset:offset + 100])
    counts['associations'] = applied
    return counts
