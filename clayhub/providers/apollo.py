"""Minimal Apollo enrichment adapter using urllib."""
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..models import EnrichResult, Lead


class ApolloProvider:
    name = "apollo"
    cost_per_call = 1.0

    def enrich(self, lead: Lead) -> EnrichResult:
        key = os.environ.get("APOLLO_API_KEY")
        if not key:
            raise RuntimeError("APOLLO_API_KEY is required")
        params = {k: v for k, v in {"email": lead.email, "domain": lead.domain, "name": f"{lead.first_name} {lead.last_name}".strip()}.items() if v}
        req = Request("https://api.apollo.io/api/v1/people/match?" + urlencode(params), headers={"x-api-key": key, "Cache-Control": "no-cache"})
        with urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        person = data.get("person") or {}
        org = person.get("organization") or {}
        fields = {k: v for k, v in {"email": person.get("email"), "title": person.get("title"), "first_name": person.get("first_name"), "last_name": person.get("last_name"), "company": org.get("name"), "domain": org.get("primary_domain"), "employees": org.get("estimated_num_employees"), "industry": org.get("industry")}.items() if v is not None}
        return EnrichResult(self.name, fields, self.cost_per_call, bool(fields))
