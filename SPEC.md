# Clay → HubSpot enrichment pipeline: spec

A SaneDevs portfolio demo. It takes leads exported from a Clay table (CSV) or posted by a Clay
"HTTP API / webhook" column, enriches them through a provider **waterfall**, validates them,
scores them against an ICP, dedupes them against HubSpot, and upserts contacts and companies
into HubSpot with associations. A dry run writes a report and changes nothing.

Runs fully offline by default (mock providers + an in-memory mock HubSpot). Real mode uses env
vars only: `HUBSPOT_TOKEN` (private app token) and optional `APOLLO_API_KEY`, `HUNTER_API_KEY`.
Never commit keys; `.env.example` lists names only.

**Python 3.11+, standard library only** (no pip installs). Tests use `unittest`.

## Layout

```
clayhub/
  __init__.py
  models.py        # dataclasses (shared contract, below)
  io_clay.py       # read Clay CSV export / webhook JSON -> list[Lead]; normalize fields
  normalize.py     # domain from email/url, name casing, title seniority, country codes
  providers/
    __init__.py    # Provider protocol + registry
    base.py
    mock.py        # MockProvider: answers from fixtures/provider_responses.json
    apollo.py      # real adapter (urllib), used only when APOLLO_API_KEY set
    hunter.py      # real adapter (urllib), used only when HUNTER_API_KEY set
  waterfall.py     # run providers in order, stop per field when filled, track credits
  validate.py      # email syntax, role-address (info@, sales@) flag, free-mail flag, disposable list
  scoring.py       # ICP rules from config/icp.json -> score 0..100 + tier A/B/C/D + reasons
  dedupe.py        # match against HubSpot: email exact, then company domain, then fuzzy company name
  hubspot/
    __init__.py
    client.py      # HubSpotClient protocol; RealHubSpotClient (urllib, CRM v3 batch upsert)
    mock.py        # MockHubSpot in-memory store, seeded from fixtures/hubspot_seed.json
    sync.py        # build batch payloads, upsert companies then contacts, associate, chunk by 100
  report.py        # write out/report.md and out/report.json
  cli.py           # python -m clayhub run ...
  __main__.py
config/icp.json
fixtures/clay_export.csv, fixtures/clay_webhook.json, fixtures/provider_responses.json, fixtures/hubspot_seed.json
tests/test_*.py
```

## Shared contract (models.py)

```python
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
    companies_create: list[dict]; companies_update: list[dict]
    contacts_create: list[dict]; contacts_update: list[dict]
    associations: list[tuple[str, str]]   # (contact key, company key)

@dataclass
class RunReport:
    total_in: int; enriched: int; valid_emails: int
    by_provider: dict[str, dict]          # name -> {"calls","hits","credits"}
    tiers: dict[str, int]
    dedupe: dict[str, int]                # action -> count
    hubspot: dict[str, int]               # created/updated contacts/companies, associations
    dry_run: bool
    errors: list[str]
```

Provider protocol: `name: str`, `cost_per_call: float`, `def enrich(self, lead: Lead) -> EnrichResult`.
The waterfall order comes from `config/icp.json` key `"waterfall": ["mock_apollo","mock_hunter","mock_dropcontact"]`.
`MockProvider(name)` looks up `provider_responses.json[name][<email or domain or "first last@domain">]`.

The waterfall only fills empty fields; the first provider to fill a field wins, recorded in `lead.sources`.
It stops calling providers for a lead once `email`, `title`, `employees`, `industry` and `country` are filled.

## config/icp.json

```json
{
  "waterfall": ["mock_apollo", "mock_hunter", "mock_dropcontact"],
  "rules": [
    {"field": "employees", "op": "between", "value": [20, 500], "points": 30, "reason": "Company size in ICP"},
    {"field": "industry", "op": "in", "value": ["Software", "SaaS", "IT Services", "Marketing Services"], "points": 25, "reason": "Target industry"},
    {"field": "title", "op": "seniority_at_least", "value": "director", "points": 25, "reason": "Decision-maker title"},
    {"field": "country", "op": "in", "value": ["US", "GB", "CA", "AU", "DE", "NL"], "points": 10, "reason": "Target market"},
    {"field": "flags", "op": "not_contains", "value": "free_mail", "points": 10, "reason": "Business email"}
  ],
  "tiers": {"A": 80, "B": 60, "C": 40},
  "hubspot": {"contact_props": {"sd_icp_score": "score", "sd_icp_tier": "tier", "sd_enrichment_source": "sources"}}
}
```
Seniority ladder: `owner/founder/ceo/cxo > vp > head > director > manager > senior > ic`.

## HubSpot behaviour (real client)
- Companies: `POST /crm/v3/objects/companies/batch/upsert` with `idProperty: "domain"`. Contacts: `POST /crm/v3/objects/contacts/batch/upsert` with `idProperty: "email"`.
- Associations: `PUT /crm/v4/associations/contacts/companies/batch/associate/default`.
- Batch size 100; on 429, retry with backoff honouring `Retry-After`, max 5 tries; 5xx retried 3 times.
- Search for dedupe: `POST /crm/v3/objects/{type}/search` (email EQ, domain EQ).
- Leads flagged `invalid_email` or `disposable` are never pushed; `role_address` is pushed but tier capped at C.
- Within one batch, leads sharing the same email: keep the one with the most filled fields, others `skip_duplicate_in_batch`.

## CLI
```
python -m clayhub run --input fixtures/clay_export.csv [--webhook-json FILE] [--dry-run] [--out out/] [--config config/icp.json]
python -m clayhub serve --port 8787 --dry-run     # POST /clay-webhook accepts one row or {"rows":[...]}
```
Without `HUBSPOT_TOKEN` the CLI uses MockHubSpot and says so in the first line of output. `--dry-run` builds the SyncPlan and report but applies nothing, even against the mock.

## Report (out/report.md)
Headline counts, provider table (calls/hits/hit-rate/credits), tier distribution, dedupe actions,
HubSpot actions (planned or applied), top 10 leads by score with reasons, list of rejected rows and why.

## Fixtures (fictional only)
- At least 40 leads.
- Domains must be fictional (`*.example`, `*.test`, or invented names on `.example.com`); people are invented.
- Coverage must include: missing emails, a free-mail address (`@gmail.com` is fine for a fake person), a role address (`info@`), an invalid email, an in-batch duplicate, three leads that already exist in `hubspot_seed.json` by email, two that match by domain only, and one by company name with a different domain spelling.
- Provider hit rates should differ (apollo ~60%, hunter ~40% of the rest, dropcontact fills a few).

## Function signatures (both halves code against these)

```python
# io_clay.py
def read_clay_csv(path: str) -> list[Lead]            # column names: see below, case-insensitive
def read_clay_webhook(payload: dict | list) -> list[Lead]   # one row dict, a list, or {"rows": [...]}
# normalize.py
def normalize_lead(lead: Lead) -> Lead                 # in place + returns it
def seniority(title: str) -> int                       # 0 (ic) .. 7 (owner/founder/ceo)
# providers/__init__.py
def build_providers(names: list[str]) -> list[Provider]   # "mock_*" -> MockProvider; "apollo"/"hunter" real if key set
# waterfall.py
def run_waterfall(leads: list[Lead], providers: list[Provider]) -> dict[str, dict]  # by_provider stats {"calls","hits","credits"}
# validate.py
def validate_lead(lead: Lead) -> Lead                  # adds flags
# scoring.py
def load_config(path: str) -> dict
def score_lead(lead: Lead, config: dict) -> Lead       # sets score, tier, score_reasons; role_address caps tier at C
# dedupe.py
def dedupe(leads: list[Lead], hubspot: HubSpotClient) -> list[DedupeMatch]
# hubspot/client.py
class HubSpotClient(Protocol):
    def search_contact_by_email(self, email: str) -> dict | None   # {"id", "properties"}
    def search_company_by_domain(self, domain: str) -> dict | None
    def search_company_by_name(self, name: str) -> list[dict]
    def batch_upsert(self, object_type: str, id_property: str, inputs: list[dict]) -> list[dict]  # returns [{"id","properties"}]
    def associate_contacts_companies(self, pairs: list[tuple[str, str]]) -> int   # pairs of ids
def get_client() -> HubSpotClient                      # Real if HUBSPOT_TOKEN else MockHubSpot (seeded)
# hubspot/sync.py
def build_plan(leads: list[Lead], matches: list[DedupeMatch], config: dict) -> SyncPlan
def apply_plan(plan: SyncPlan, client: HubSpotClient) -> dict[str, int]
# report.py
def write_report(report: RunReport, out_dir: str) -> tuple[str, str]   # paths to report.md, report.json
# cli.py
def main(argv: list[str] | None = None) -> int
```

CSV columns (Clay export): `Row ID, First Name, Last Name, Email, Job Title, Company Name, Company Domain, LinkedIn URL, Country, Employee Count, Industry, Phone`. Blank cells mean unknown.
Pipeline order in `cli.run`: read → normalize → waterfall → normalize again → validate → score → dedupe → build_plan → (apply unless dry run) → report.
