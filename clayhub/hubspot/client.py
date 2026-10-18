"""Minimal HubSpot CRM client with bounded, injectable retries."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class HubSpotClient(Protocol):
    def search_contact_by_email(self, email: str) -> dict | None: ...
    def search_company_by_domain(self, domain: str) -> dict | None: ...
    def search_company_by_name(self, name: str) -> list[dict]: ...
    def batch_upsert(self, object_type: str, id_property: str, inputs: list[dict]) -> list[dict]: ...
    def associate_contacts_companies(self, pairs: list[tuple[str, str]]) -> int: ...


class RealHubSpotClient:
    def __init__(self, token: str | None = None, *, sleep=time.sleep, urlopen=urlopen):
        self.token = token or os.environ.get('HUBSPOT_TOKEN', '')
        if not self.token:
            raise ValueError('HUBSPOT_TOKEN is required')
        self.sleep = sleep
        self.urlopen = urlopen

    def _request(self, method: str, path: str, payload: dict) -> dict:
        request = Request('https://api.hubapi.com' + path,
                          data=json.dumps(payload).encode(), method=method,
                          headers={'Authorization': 'Bearer ' + self.token,
                                   'Content-Type': 'application/json'})
        rate_attempts = server_retries = 0
        while True:
            try:
                with self.urlopen(request, timeout=30) as response:
                    body = response.read()
                    return json.loads(body) if body else {}
            except HTTPError as error:
                if error.code == 429:
                    rate_attempts += 1
                    if rate_attempts >= 5:
                        raise
                    delay = float(2 ** (rate_attempts - 1))
                    retry_after = error.headers.get('Retry-After') if error.headers else None
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            try:
                                delay = max(delay, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
                            except (ValueError, TypeError):
                                pass
                elif 500 <= error.code < 600 and server_retries < 3:
                    delay = float(2 ** server_retries)
                    server_retries += 1
                else:
                    raise
                error.close()
                self.sleep(delay)

    def _search(self, object_type: str, property_name: str, value: str) -> dict | None:
        result = self._request('POST', f'/crm/v3/objects/{object_type}/search', {
            'filterGroups': [{'filters': [{'propertyName': property_name, 'operator': 'EQ', 'value': value}]}],
            'properties': [property_name, 'name'] if object_type == 'companies' else ['email'], 'limit': 1})
        return next(iter(result.get('results', [])), None)

    def search_contact_by_email(self, email: str) -> dict | None:
        return self._search('contacts', 'email', email)

    def search_company_by_domain(self, domain: str) -> dict | None:
        return self._search('companies', 'domain', domain)

    def search_company_by_name(self, name: str) -> list[dict]:
        # Fuzzy comparison needs candidates even when spelling differs. Paginate
        # all named companies rather than incorrectly requiring an exact token.
        payload = {'filterGroups': [{'filters': [{'propertyName': 'name', 'operator': 'HAS_PROPERTY'}]}],
                   'properties': ['domain', 'name'], 'limit': 200}
        results = []
        while True:
            page = self._request('POST', '/crm/v3/objects/companies/search', payload)
            results.extend(page.get('results', []))
            after = page.get('paging', {}).get('next', {}).get('after')
            if after is None:
                return results
            payload['after'] = after

    def batch_upsert(self, object_type: str, id_property: str, inputs: list[dict]) -> list[dict]:
        if object_type not in {'companies', 'contacts'}:
            raise ValueError('Unsupported HubSpot object type')
        results = []
        for offset in range(0, len(inputs), 100):
            batch = []
            for item in inputs[offset:offset + 100]:
                entry = dict(item)
                if 'id' not in entry:
                    entry.update(id=entry['properties'][id_property], idProperty=id_property)
                batch.append(entry)
            response = self._request('POST', f'/crm/v3/objects/{object_type}/batch/upsert', {'inputs': batch})
            if response.get('errors') or response.get('status') == 'PENDING':
                raise RuntimeError('HubSpot batch did not complete successfully: ' + json.dumps(response))
            results.extend(response.get('results', []))
        return results

    def associate_contacts_companies(self, pairs: list[tuple[str, str]]) -> int:
        for offset in range(0, len(pairs), 100):
            response = self._request('PUT', '/crm/v4/associations/contacts/companies/batch/associate/default', {
                'inputs': [{'from': {'id': contact}, 'to': {'id': company}} for contact, company in pairs[offset:offset + 100]]})
            if response.get('errors'):
                raise RuntimeError('HubSpot association failed: ' + json.dumps(response))
        return len(pairs)


def get_client() -> HubSpotClient:
    if os.environ.get('HUBSPOT_TOKEN'):
        return RealHubSpotClient()
    from .mock import MockHubSpot
    return MockHubSpot()
