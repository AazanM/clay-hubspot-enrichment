"""Shared data contract for the pipeline. See SPEC.md."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Lead:
    row_id: str                 # Clay row id or CSV line number
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    title: str = ""
    company: str = ""
    domain: str = ""
    linkedin_url: str = ""
    country: str = ""           # ISO-2 after normalize
    employees: int | None = None
    industry: str = ""
    phone: str = ""
    sources: dict[str, str] = field(default_factory=dict)  # field -> provider name that filled it
    flags: list[str] = field(default_factory=list)          # e.g. "role_address","free_mail","invalid_email","disposable"
    score: int = 0
    tier: str = "D"
    score_reasons: list[str] = field(default_factory=list)

@dataclass
class EnrichResult:            # what a provider returns for one lead
    provider: str
    fields: dict[str, object]   # any Lead field names
    credits: float = 0.0
    found: bool = False

@dataclass
class DedupeMatch:
    lead_row_id: str
    action: str                 # "create" | "update" | "skip_duplicate_in_batch"
    contact_id: str | None
    company_id: str | None
    matched_on: str             # "email" | "domain" | "company_name" | "none"

@dataclass
class SyncPlan:
    companies_create: list[dict] = field(default_factory=list)
    companies_update: list[dict] = field(default_factory=list)
    contacts_create: list[dict] = field(default_factory=list)
    contacts_update: list[dict] = field(default_factory=list)
    associations: list[tuple[str, str]] = field(default_factory=list)  # (contact email, company domain)

@dataclass
class RunReport:
    total_in: int = 0
    enriched: int = 0
    valid_emails: int = 0
    by_provider: dict[str, dict] = field(default_factory=dict)          # name -> {"calls","hits","credits"}
    tiers: dict[str, int] = field(default_factory=dict)
    dedupe: dict[str, int] = field(default_factory=dict)                # action -> count
    hubspot: dict[str, int] = field(default_factory=dict)               # created/updated contacts/companies, associations
    dry_run: bool = True
    rejected: list[dict] = field(default_factory=list)   # {"row_id","email","reason"}
    top_leads: list[Lead] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
