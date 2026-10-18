"""Offline in-memory HubSpot implementation."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path


class MockHubSpot:
    def __init__(self, seed_path='fixtures/hubspot_seed.json', *, seed=None):
        if seed is None:
            seed = json.loads(Path(seed_path).read_text())
        self.contacts = {str(item['id']): deepcopy(item) for item in seed.get('contacts', [])}
        self.companies = {str(item['id']): deepcopy(item) for item in seed.get('companies', [])}
        self.associations = set()
        self._next_id = 1

    def _search(self, store, prop, value):
        return next((deepcopy(item) for item in store.values()
                     if str(item['properties'].get(prop, '')).casefold() == value.casefold()), None)

    def search_contact_by_email(self, email):
        return self._search(self.contacts, 'email', email)

    def search_company_by_domain(self, domain):
        return self._search(self.companies, 'domain', domain)

    def search_company_by_name(self, name):
        return deepcopy(list(self.companies.values()))

    def batch_upsert(self, object_type, id_property, inputs):
        if object_type not in {'contacts', 'companies'}:
            raise ValueError('Unsupported HubSpot object type')
        store = getattr(self, object_type)
        results = []
        for item in inputs:
            existing = store.get(str(item.get('id'))) if not item.get('idProperty') else None
            if existing is None:
                existing = self._search(store, id_property, item['properties'][id_property])
            if existing is None:
                while str(self._next_id) in store:
                    self._next_id += 1
                existing = {'id': str(self._next_id), 'properties': {}}
                self._next_id += 1
            existing['properties'].update(deepcopy(item['properties']))
            store[str(existing['id'])] = existing
            results.append(deepcopy(existing))
        return results

    def associate_contacts_companies(self, pairs):
        for contact, company in pairs:
            if contact not in self.contacts or company not in self.companies:
                raise ValueError('Association refers to missing record')
            self.associations.add((contact, company))
        return len(pairs)
