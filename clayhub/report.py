"""Portable Markdown and JSON run reports."""
from dataclasses import asdict
import json
from pathlib import Path

from .models import RunReport


def _cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def write_report(report: RunReport, out_dir: str) -> tuple[str, str]:
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    md_path, json_path = directory / 'report.md', directory / 'report.json'
    lines = ['# Clay → HubSpot enrichment report', '',
             f'Mode: {"dry run (planned actions)" if report.dry_run else "applied actions"}', '',
             f'Leads received: {report.total_in} · Enriched: {report.enriched} · Valid emails: {report.valid_emails}', '',
             '## Providers', '', '| Provider | Calls | Hits | Hit rate | Credits |', '| --- | ---: | ---: | ---: | ---: |']
    for name, stats in report.by_provider.items():
        calls, hits = stats.get('calls', 0), stats.get('hits', 0)
        rate = hits / calls if calls else 0
        lines.append(f'| {_cell(name)} | {calls} | {hits} | {rate:.1%} | {stats.get("credits", 0):g} |')
    for heading, values in [('Tier distribution', report.tiers), ('Dedupe actions', report.dedupe),
                            ('HubSpot actions (planned)' if report.dry_run else 'HubSpot actions (applied)', report.hubspot)]:
        lines.extend(['', '## ' + heading, ''])
        lines.extend(f'- {_cell(key)}: {value}' for key, value in values.items())
    lines.extend(['', '## Top 10 leads', '', '| Row | Name | Email | Score | Tier | Reasons |', '| --- | --- | --- | ---: | --- | --- |'])
    for lead in sorted(report.top_leads, key=lambda lead: lead.score, reverse=True)[:10]:
        lines.append('| ' + ' | '.join(_cell(value) for value in [lead.row_id, f'{lead.first_name} {lead.last_name}'.strip(), lead.email, lead.score, lead.tier, '; '.join(lead.score_reasons)]) + ' |')
    lines.extend(['', '## Rejected rows', '', '| Row | Email | Reason |', '| --- | --- | --- |'])
    for rejected in report.rejected:
        lines.append('| ' + ' | '.join(_cell(rejected.get(key, '')) for key in ('row_id', 'email', 'reason')) + ' |')
    if not report.rejected:
        lines.extend(['', 'None.'])
    lines.extend(['', '## Errors', ''])
    lines.extend(['- ' + _cell(error) for error in report.errors] or ['None.'])
    md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    json_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return str(md_path), str(json_path)
