"""Minimal Hunter domain search adapter using urllib."""
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..models import EnrichResult, Lead


class HunterProvider:
    name = "hunter"
    cost_per_call = 1.0

    def enrich(self, lead: Lead) -> EnrichResult:
        key = os.environ.get("HUNTER_API_KEY")
        if not key:
            raise RuntimeError("HUNTER_API_KEY is required")
        if not lead.domain:
            return EnrichResult(self.name, {}, 0.0, False)
        query = urlencode({"domain": lead.domain, "api_key": key, "type": "personal"})
        req = Request("https://api.hunter.io/v2/domain-search?" + query)
        with urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        emails = (data.get("data") or {}).get("emails") or []
        person = next((item for item in emails if item.get("first_name", "").lower() == lead.first_name.lower() and item.get("last_name", "").lower() == lead.last_name.lower()), None)
        person = person or (emails[0] if emails else {})
        fields = {k: v for k, v in {"email": person.get("value"), "title": person.get("position"), "first_name": person.get("first_name"), "last_name": person.get("last_name"), "phone": person.get("phone_number")}.items() if v}
        return EnrichResult(self.name, fields, self.cost_per_call if fields else 0.0, bool(fields))
