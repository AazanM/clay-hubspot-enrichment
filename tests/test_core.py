import tempfile
import unittest
from pathlib import Path

from clayhub.io_clay import read_clay_csv, read_clay_webhook
from clayhub.models import EnrichResult, Lead
from clayhub.normalize import normalize_lead, seniority
from clayhub.providers.mock import MockProvider
from clayhub.scoring import score_lead
from clayhub.validate import validate_lead
from clayhub.waterfall import run_waterfall


class CoreTests(unittest.TestCase):
    def test_csv_and_webhook_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leads.csv"
            path.write_text("Row ID,First Name,Email,Employee Count\nabc,ada,ADA@EXAMPLE.TEST,25\n", encoding="utf-8")
            lead = read_clay_csv(str(path))[0]
            self.assertEqual((lead.row_id, lead.first_name, lead.email, lead.employees), ("abc", "Ada", "ada@example.test", 25))
        self.assertEqual(read_clay_webhook({"row_id": "x", "first_name": "Lin"})[0].row_id, "x")
        self.assertEqual(len(read_clay_webhook([{"Row ID": "a"}, {"Row ID": "b"}])), 2)
        self.assertEqual(read_clay_webhook({"rows": [{"Row ID": "c"}]})[0].row_id, "c")

    def test_normalization_and_seniority(self):
        lead = Lead("1", email=" ADA@EXAMPLE.COM ", first_name="ada", last_name="lovelace", country="United States")
        normalize_lead(lead)
        self.assertEqual((lead.domain, lead.first_name, lead.country), ("example.com", "Ada", "US"))
        lead.domain = "https://www.example.org/path"
        normalize_lead(lead)
        self.assertEqual(lead.domain, "example.org")
        self.assertEqual(normalize_lead(Lead("2", country="UK")).country, "GB")
        self.assertEqual([seniority(x) for x in ("IC", "Senior Engineer", "Manager", "Director", "Head of Sales", "VP Sales", "CEO")], [0, 2, 3, 4, 5, 6, 7])

    def test_mock_lookup_priority(self):
        p = MockProvider("mock", responses={"mock": {"a@x.test": {"title": "Email"}, "x.test": {"title": "Domain"}}})
        self.assertEqual(p.enrich(Lead("1", email="a@x.test", domain="x.test")).fields["title"], "Email")

    def test_waterfall_first_wins_completion_and_credits(self):
        class P:
            def __init__(self, name, fields, credits):
                self.name, self.fields, self.credits = name, fields, credits
            def enrich(self, lead):
                return EnrichResult(self.name, self.fields, self.credits, bool(self.fields))
        lead = Lead("1")
        stats = run_waterfall([lead], [P("one", {"email": "a@b.test", "title": "CEO"}, 0.5), P("two", {"email": "other@b.test", "employees": 10, "industry": "SaaS", "country": "US"}, 1)])
        self.assertEqual(lead.email, "a@b.test")
        self.assertEqual(lead.sources["email"], "one")
        self.assertEqual(stats["one"], {"calls": 1, "hits": 1, "credits": 0.5})
        self.assertEqual(stats["two"]["calls"], 1)
        done = Lead("2", email="x@y.test", title="CEO", employees=2, industry="SaaS", country="US")
        calls = run_waterfall([done], [P("later", {}, 0)])
        self.assertEqual(calls["later"]["calls"], 0)

    def test_validation(self):
        lead = validate_lead(Lead("1", email="info@gmail.com"))
        self.assertEqual(set(lead.flags), {"role_address", "free_mail"})
        self.assertIn("invalid_email", validate_lead(Lead("2", email="bad email")).flags)
        self.assertIn("disposable", validate_lead(Lead("3", email="x@mailinator.com")).flags)

    def test_scoring_and_role_tier_cap(self):
        config = {"rules": [
            {"field": "employees", "op": "between", "value": [20, 500], "points": 30, "reason": "size"},
            {"field": "industry", "op": "in", "value": ["SaaS"], "points": 25, "reason": "industry"},
            {"field": "title", "op": "seniority_at_least", "value": "director", "points": 25, "reason": "title"},
            {"field": "country", "op": "in", "value": ["US"], "points": 10, "reason": "country"},
            {"field": "flags", "op": "not_contains", "value": "free_mail", "points": 10, "reason": "email"},
        ], "tiers": {"A": 80, "B": 60, "C": 40}}
        lead = score_lead(Lead("1", title="Director", employees=50, industry="SaaS", country="US"), config)
        self.assertEqual((lead.score, lead.tier), (100, "A"))
        self.assertEqual(len(lead.score_reasons), 5)
        role = score_lead(Lead("2", title="Director", employees=50, industry="SaaS", country="US", flags=["role_address"]), config)
        self.assertEqual(role.tier, "C")


if __name__ == "__main__":
    unittest.main()
