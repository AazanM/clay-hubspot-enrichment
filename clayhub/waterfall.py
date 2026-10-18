"""Run enrichment providers in priority order."""
from .models import Lead

_REQUIRED = ("email", "title", "employees", "industry", "country")


def _complete(lead: Lead) -> bool:
    return all(getattr(lead, field) not in (None, "") for field in _REQUIRED)


def run_waterfall(leads: list[Lead], providers: list) -> dict[str, dict]:
    stats = {p.name: {"calls": 0, "hits": 0, "credits": 0.0} for p in providers}
    for lead in leads:
        for provider in providers:
            if _complete(lead):
                break
            stats[provider.name]["calls"] += 1
            result = provider.enrich(lead)
            stats[provider.name]["credits"] += result.credits
            if result.found:
                stats[provider.name]["hits"] += 1
            for field, value in result.fields.items():
                if hasattr(lead, field) and getattr(lead, field) in (None, "") and value not in (None, ""):
                    setattr(lead, field, value)
                    lead.sources[field] = result.provider
    return stats
