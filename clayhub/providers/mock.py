"""Deterministic offline provider backed by fixture data or an injected mapping."""
from __future__ import annotations

import json
from pathlib import Path

from ..models import EnrichResult, Lead


class MockProvider:
    cost_per_call = 0.0

    def __init__(self, name: str, responses_path: str = "fixtures/provider_responses.json", responses: dict | None = None):
        self.name = name
        if responses is not None:
            self.responses = responses
        else:
            try:
                self.responses = json.loads(Path(responses_path).read_text(encoding="utf-8"))
            except FileNotFoundError:
                self.responses = {}

    def enrich(self, lead: Lead) -> EnrichResult:
        data = self.responses.get(self.name, {})
        keys = []
        if lead.email:
            keys.append(lead.email.lower())
        if lead.domain:
            keys.append(lead.domain.lower())
        full = f"{lead.first_name} {lead.last_name}@{lead.domain}".strip().lower()
        if lead.first_name or lead.last_name:
            keys.append(full)
        result = next((data[key] for key in keys if key in data), None)
        if not isinstance(result, dict):
            return EnrichResult(provider=self.name, fields={}, credits=0.0, found=False)
        fields = result.get("fields", result)
        return EnrichResult(provider=self.name, fields=dict(fields), credits=float(result.get("credits", 0.0)), found=bool(fields))
