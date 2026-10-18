"""Provider protocol."""
from typing import Protocol

from ..models import EnrichResult, Lead


class Provider(Protocol):
    name: str
    cost_per_call: float

    def enrich(self, lead: Lead) -> EnrichResult: ...
