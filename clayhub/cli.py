"""CSV and Clay webhook entry points."""
from __future__ import annotations

import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

from .dedupe import dedupe
from .hubspot.client import get_client
from .hubspot.sync import apply_plan, build_plan, plan_counts
from .models import RunReport
from .report import write_report
from .report_html import write_html_report


def run(args, payload=None, client=None):
    # Lazy imports keep the sync modules and their isolated tests independent
    # of the enrichment half of this project.
    from .io_clay import read_clay_csv, read_clay_webhook
    from .normalize import normalize_lead
    from .providers import build_providers
    from .scoring import load_config, score_lead
    from .validate import validate_lead
    from .waterfall import run_waterfall

    config = load_config(args.config)
    if payload is not None:
        leads = read_clay_webhook(payload)
    elif args.webhook_json:
        with open(args.webhook_json, encoding='utf-8') as handle:
            leads = read_clay_webhook(json.load(handle))
    else:
        leads = read_clay_csv(args.input)
    leads = [normalize_lead(lead) for lead in leads]
    stats = run_waterfall(leads, build_providers(config.get('waterfall', [])))
    for lead in leads:
        normalize_lead(lead)
        validate_lead(lead)
        score_lead(lead, config)
    client = client if client is not None else get_client()
    matches = dedupe(leads, client)
    plan = build_plan(leads, matches, config)
    rejected = [{'row_id': lead.row_id, 'email': lead.email,
                 'reason': ', '.join(flag for flag in lead.flags if flag in {'invalid_email', 'disposable'}) or 'missing_email'}
                for lead in leads if not lead.email or {'invalid_email', 'disposable'}.intersection(lead.flags)]
    report = RunReport(total_in=len(leads), enriched=sum(bool(lead.sources) for lead in leads),
                       valid_emails=sum(bool(lead.email) and not {'invalid_email', 'disposable'}.intersection(lead.flags) for lead in leads),
                       by_provider=stats, tiers=dict(Counter(lead.tier for lead in leads)),
                       dedupe=dict(Counter(match.action for match in matches)), hubspot=plan_counts(plan),
                       dry_run=args.dry_run, rejected=rejected, top_leads=sorted(leads, key=lambda lead: lead.score, reverse=True)[:10])
    if not args.dry_run:
        try:
            report.hubspot = apply_plan(plan, client)
        except Exception as error:
            report.errors.append(str(error))
            # Partial remote writes cannot be counted safely as successful writes.
            report.hubspot = {}
            write_report(report, args.out)
            raise
    paths = write_report(report, args.out)
    write_html_report(report, args.out)
    print(f'Processed {len(leads)} leads; report: {paths[0]}')
    return report


def main(argv: list[str] | None = None) -> int:
    if not os.environ.get('HUBSPOT_TOKEN'):
        print('Using mock HubSpot (HUBSPOT_TOKEN is not set).', flush=True)
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    for command in ('run', 'serve'):
        sub = subparsers.add_parser(command)
        sub.add_argument('--dry-run', action='store_true')
        sub.add_argument('--out', default='out/')
        sub.add_argument('--config', default='config/icp.json')
        if command == 'run':
            sub.add_argument('--input', default='fixtures/clay_export.csv')
            sub.add_argument('--webhook-json')
        else:
            sub.add_argument('--port', type=int, default=8787)
    args = parser.parse_args(argv)
    if args.command == 'run':
        try:
            run(args)
        except Exception as error:
            print(f'Pipeline failed: {error}')
            return 1
        return 0

    client = get_client()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != '/clay-webhook':
                self.send_error(404)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 5_000_000:
                    self.send_error(413)
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, (dict, list)):
                    raise ValueError('Expected a row, rows list, or rows object')
            except (ValueError, UnicodeDecodeError) as error:
                self.send_error(400, str(error))
                return
            try:
                report = run(args, payload=payload, client=client)
                body = json.dumps({
                    'total_in': report.total_in,
                    'dry_run': report.dry_run,
                    'tiers': report.tiers,
                    'hubspot': report.hubspot,
                    'rejected': report.rejected,
                    'leads': [{'row_id': lead.row_id, 'email': lead.email, 'score': lead.score,
                               'tier': lead.tier, 'reasons': lead.score_reasons}
                              for lead in report.top_leads],
                }).encode()
            except Exception as error:
                self.send_error(500, str(error))
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    try:
        with HTTPServer(('127.0.0.1', args.port), Handler) as server:
            print(f'Listening on http://127.0.0.1:{args.port}/clay-webhook', flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
