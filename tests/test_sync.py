"""Sync-half tests: no enrichment modules, fixture files, or network required."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

from clayhub.dedupe import dedupe
from clayhub.hubspot.client import RealHubSpotClient
from clayhub.hubspot.mock import MockHubSpot
from clayhub.hubspot.sync import apply_plan, build_plan
from clayhub.models import Lead, RunReport
from clayhub.report import write_report


CONFIG = {'hubspot': {'contact_props': {'sd_icp_score': 'score', 'sd_icp_tier': 'tier', 'sd_enrichment_source': 'sources'}}}
SEED = {'contacts': [{'id': '10', 'properties': {'email': 'old@acme.example', 'firstname': 'Old'}}],
        'companies': [{'id': '20', 'properties': {'domain': 'acme.example', 'name': 'Acme Inc.'}}]}


class DedupeTests(unittest.TestCase):
    def setUp(self):
        self.client = MockHubSpot(seed=SEED)

    def test_matching_paths(self):
        leads = [Lead('email', email='old@acme.example', domain='acme.example'),
                 Lead('domain', email='new@acme.example', domain='acme.example'),
                 Lead('name', email='new@acmee.example', domain='acmee.example', company='Acme, LLC'),
                 Lead('fuzzy', email='new@other.example', company='Acmee GmbH'),
                 Lead('new', email='new@new.example', company='Different')]
        matches = dedupe(leads, self.client)
        self.assertEqual([m.matched_on for m in matches], ['email', 'domain', 'company_name', 'company_name', 'none'])
        self.assertEqual(matches[0].contact_id, '10')
        self.assertEqual(matches[1].company_id, '20')
        self.assertIsNone(matches[1].contact_id)
        self.assertEqual(matches[-1].action, 'create')

    def test_duplicate_keeps_most_filled_and_first_on_tie(self):
        leads = [Lead('a', email='DUP@new.example'),
                 Lead('b', email='dup@new.example', title='Director'),
                 Lead('c', email='dup@new.example', title='Manager')]
        matches = dedupe(leads, self.client)
        self.assertEqual([m.action for m in matches], ['skip_duplicate_in_batch', 'create', 'skip_duplicate_in_batch'])
        self.assertEqual(len(build_plan(leads, matches, CONFIG).contacts_create), 1)

    def test_rejected_richer_duplicate_cannot_displace_valid(self):
        leads = [Lead('valid', email='x@new.example'),
                 Lead('bad', email='x@new.example', title='CEO', company='Big', flags=['disposable'])]
        plan = build_plan(leads, dedupe(leads, self.client), CONFIG)
        self.assertEqual(len(plan.contacts_create), 1)
        self.assertNotIn('jobtitle', plan.contacts_create[0]['properties'])

    def test_empty_names_do_not_fuzzy_match(self):
        match = dedupe([Lead('1', email='x@new.example', company='Inc LLC')], self.client)[0]
        self.assertIsNone(match.company_id)


class PlanTests(unittest.TestCase):
    def test_mapping_and_company_reuse(self):
        leads = [Lead('1', first_name='Ada', last_name='Stone', email='ada@new.example',
                      title='CEO', company='New', domain='new.example', score=90, tier='A',
                      sources={'title': 'mock_apollo'}),
                 Lead('2', email='two@new.example', company='New', domain='new.example')]
        client = MockHubSpot(seed={})
        plan = build_plan(leads, dedupe(leads, client), CONFIG)
        self.assertEqual(len(plan.companies_create), 1)
        self.assertEqual(plan.associations, [('ada@new.example', 'new.example'), ('two@new.example', 'new.example')])
        props = plan.contacts_create[0]['properties']
        self.assertEqual((props['firstname'], props['lastname'], props['jobtitle'], props['company']), ('Ada', 'Stone', 'CEO', 'New'))
        self.assertEqual(props['sd_icp_score'], 90)
        self.assertEqual(props['sd_icp_tier'], 'A')
        self.assertEqual(json.loads(props['sd_enrichment_source']), {'title': 'mock_apollo'})
        events = []
        original_upsert, original_associate = client.batch_upsert, client.associate_contacts_companies

        def upsert(object_type, prop, inputs):
            events.append(object_type)
            return original_upsert(object_type, prop, inputs)

        def associate(pairs):
            events.append('associations')
            return original_associate(pairs)

        client.batch_upsert, client.associate_contacts_companies = upsert, associate
        result = apply_plan(plan, client)
        self.assertEqual(events, ['companies', 'contacts', 'associations'])
        self.assertEqual(result['contacts_created'], 2)
        self.assertEqual(len(client.associations), 2)

    def test_existing_company_does_not_mark_new_contact_as_update(self):
        client = MockHubSpot(seed=SEED)
        leads = [Lead('1', email='new@acme.example', domain='acme.example')]
        plan = build_plan(leads, dedupe(leads, client), CONFIG)
        self.assertEqual(len(plan.contacts_create), 1)
        self.assertEqual(len(plan.companies_update), 1)
        self.assertEqual(plan.companies_update[0]['id'], '20')
        apply_plan(plan, client)
        self.assertEqual(len(client.companies), 1)

    def test_fuzzy_company_update_uses_existing_id(self):
        client = MockHubSpot(seed=SEED)
        leads = [Lead('1', email='new@acmee.example', domain='acmee.example', company='Acme Ltd')]
        plan = build_plan(leads, dedupe(leads, client), CONFIG)
        apply_plan(plan, client)
        self.assertEqual(len(client.companies), 1)
        self.assertEqual(client.search_company_by_domain('acmee.example')['id'], '20')

    def test_name_match_without_domain_associates_by_id(self):
        client = MockHubSpot(seed=SEED)
        leads = [Lead('1', email='new@other.example', company='Acme')]
        plan = build_plan(leads, dedupe(leads, client), CONFIG)
        apply_plan(plan, client)
        self.assertEqual(next(iter(client.associations))[1], '20')

    def test_exclusions_and_role_tier_cap(self):
        leads = [Lead('1', email='invalid', domain='bad.example', flags=['invalid_email']),
                 Lead('2', email='x@trash.example', domain='trash.example', flags=['disposable']),
                 Lead('3'), Lead('4', email='info@ok.example', domain='ok.example', flags=['role_address'], tier='A')]
        client = MockHubSpot(seed={})
        plan = build_plan(leads, dedupe(leads, client), CONFIG)
        self.assertEqual(len(plan.contacts_create), 1)
        self.assertEqual(len(plan.companies_create), 1)
        self.assertEqual(plan.contacts_create[0]['properties']['sd_icp_tier'], 'C')

    def test_apply_chunks_at_100(self):
        client = MockHubSpot(seed={})
        leads = [Lead(str(i), email=f'p{i}@c{i}.example', domain=f'c{i}.example') for i in range(205)]
        sizes = []
        original = client.batch_upsert

        def upsert(kind, prop, inputs):
            sizes.append((kind, len(inputs)))
            return original(kind, prop, inputs)

        client.batch_upsert = upsert
        result = apply_plan(build_plan(leads, dedupe(leads, client), CONFIG), client)
        self.assertEqual(sizes, [('companies', 100), ('companies', 100), ('companies', 5),
                                 ('contacts', 100), ('contacts', 100), ('contacts', 5)])
        self.assertEqual(result['associations'], 205)


class MockTests(unittest.TestCase):
    def test_upsert_then_search_and_update(self):
        client = MockHubSpot(seed={})
        first = client.batch_upsert('contacts', 'email', [{'properties': {'email': 'a@b.example', 'firstname': 'A'}}])[0]
        second = client.batch_upsert('contacts', 'email', [{'properties': {'email': 'a@b.example', 'lastname': 'B'}}])[0]
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(client.search_contact_by_email('A@B.EXAMPLE')['properties']['firstname'], 'A')
        company = client.batch_upsert('companies', 'domain', [{'properties': {'domain': 'b.example', 'name': 'B'}}])[0]
        self.assertEqual(client.search_company_by_domain('b.example')['id'], company['id'])
        found = client.search_contact_by_email('a@b.example')
        found['properties']['firstname'] = 'Mutated'
        self.assertEqual(client.search_contact_by_email('a@b.example')['properties']['firstname'], 'A')

    def test_seed_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'seed.json'
            path.write_text(json.dumps(SEED))
            self.assertEqual(MockHubSpot(seed_path=path).search_contact_by_email('old@acme.example')['id'], '10')


class Response(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())


def http_error(code, headers=None):
    return HTTPError('https://api.hubapi.com', code, 'test', headers or {}, io.BytesIO())


class RealClientTests(unittest.TestCase):
    def test_429_retry_after_and_auth(self):
        calls, sleeps = [], []

        def open_url(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise http_error(429, {'Retry-After': '7'})
            return Response({'results': [{'id': '1', 'properties': {'email': 'x@y.example'}}]})

        client = RealHubSpotClient('fake', urlopen=open_url, sleep=sleeps.append)
        self.assertEqual(client.search_contact_by_email('x@y.example')['id'], '1')
        self.assertEqual(sleeps, [7])
        self.assertEqual(calls[0].get_header('Authorization'), 'Bearer fake')
        self.assertEqual(json.loads(calls[0].data)['filterGroups'][0]['filters'][0]['operator'], 'EQ')

    def test_429_max_five_tries(self):
        calls, sleeps = [], []

        def open_url(request, timeout):
            calls.append(request)
            raise http_error(429)

        client = RealHubSpotClient('fake', urlopen=open_url, sleep=sleeps.append)
        with self.assertRaises(HTTPError):
            client.search_contact_by_email('x@y.example')
        self.assertEqual(len(calls), 5)
        self.assertEqual(sleeps, [1, 2, 4, 8])

    def test_5xx_retried_three_times(self):
        calls, sleeps = [], []

        def open_url(request, timeout):
            calls.append(request)
            if len(calls) < 4:
                raise http_error(503)
            return Response({'results': []})

        client = RealHubSpotClient('fake', urlopen=open_url, sleep=sleeps.append)
        self.assertIsNone(client.search_company_by_domain('x.example'))
        self.assertEqual(sleeps, [1, 2, 4])
        self.assertEqual(len(calls), 4)

    def test_persistent_5xx_and_non_retryable_errors(self):
        for code, expected_calls in [(500, 4), (400, 1), (401, 1)]:
            calls = []

            def open_url(request, timeout):
                calls.append(request)
                raise http_error(code)

            client = RealHubSpotClient('fake', urlopen=open_url, sleep=lambda _: None)
            with self.assertRaises(HTTPError):
                client.search_contact_by_email('x@y.example')
            self.assertEqual(len(calls), expected_calls)

    def test_real_batches_and_association_payload(self):
        calls = []

        def open_url(request, timeout):
            payload = json.loads(request.data)
            calls.append((request.full_url, request.get_method(), payload))
            return Response({'results': [{'id': str(i), 'properties': entry.get('properties', {})}
                                         for i, entry in enumerate(payload['inputs'])]})

        client = RealHubSpotClient('fake', urlopen=open_url, sleep=lambda _: None)
        inputs = [{'properties': {'email': f'p{i}@x.example'}} for i in range(201)]
        self.assertEqual(len(client.batch_upsert('contacts', 'email', inputs)), 201)
        self.assertEqual([len(call[2]['inputs']) for call in calls], [100, 100, 1])
        self.assertTrue(calls[0][0].endswith('/crm/v3/objects/contacts/batch/upsert'))
        self.assertEqual(calls[0][2]['inputs'][0]['idProperty'], 'email')
        client.batch_upsert('companies', 'domain', [{'properties': {'domain': 'x.example'}}])
        self.assertEqual(calls[-1][2]['inputs'][0]['idProperty'], 'domain')
        self.assertEqual(client.associate_contacts_companies([('c', 'b')] * 101), 101)
        self.assertEqual(calls[-1][1], 'PUT')
        self.assertTrue(calls[-1][0].endswith('/crm/v4/associations/contacts/companies/batch/associate/default'))
        self.assertEqual(calls[-1][2], {'inputs': [{'from': {'id': 'c'}, 'to': {'id': 'b'}}]})

    def test_fuzzy_candidates_paginate(self):
        calls = []

        def open_url(request, timeout):
            calls.append(json.loads(request.data))
            return Response({'results': [{'id': str(len(calls)), 'properties': {'name': 'Acme'}}],
                             **({'paging': {'next': {'after': '200'}}} if len(calls) == 1 else {})})

        client = RealHubSpotClient('fake', urlopen=open_url, sleep=lambda _: None)
        self.assertEqual(len(client.search_company_by_name('Acmee')), 2)
        self.assertEqual(calls[1]['after'], '200')


class ReportTests(unittest.TestCase):
    def test_files_and_contents(self):
        leads = [Lead(str(i), email=f'p{i}@x.example', score=i, score_reasons=['Company size in ICP']) for i in range(12)]
        report = RunReport(total_in=12, enriched=5, valid_emails=11, by_provider={
            'mock_apollo': {'calls': 10, 'hits': 5, 'credits': 2.5},
            'unused': {'calls': 0, 'hits': 0, 'credits': 0}}, tiers={'A': 3}, dedupe={'create': 11},
            hubspot={'contacts_created': 11}, top_leads=leads,
            rejected=[{'row_id': 'bad', 'email': 'bad', 'reason': 'invalid_email'}], errors=['test error'])
        with tempfile.TemporaryDirectory() as directory:
            md, data = write_report(report, str(Path(directory) / 'out'))
            self.assertTrue(Path(md).is_file())
            content = Path(md).read_text()
            self.assertIn('50.0%', content)
            self.assertIn('dry run (planned actions)', content)
            self.assertIn('invalid_email', content)
            self.assertIn('Company size in ICP', content)
            self.assertIn('test error', content)
            self.assertNotIn('p0@x.example', content)
            parsed = json.loads(Path(data).read_text())
            self.assertEqual(parsed['total_in'], 12)
            self.assertEqual(parsed['rejected'][0]['row_id'], 'bad')
            self.assertTrue(parsed['dry_run'])


if __name__ == '__main__':
    unittest.main()
