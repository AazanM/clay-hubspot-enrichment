"""Self-contained HTML run report for portfolio presentation."""
from __future__ import annotations

import html
from pathlib import Path

from .models import RunReport


def write_html_report(report: RunReport, out_dir: str) -> str:
    """Generate a self-contained HTML report and return its path."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    html_path = directory / 'report.html'

    total_credits = sum(float(stats.get('credits', 0)) for stats in report.by_provider.values())
    credits_spent_str = f"{total_credits:g}"

    enriched_pct = (report.enriched / report.total_in * 100) if report.total_in else 0.0
    valid_pct = (report.valid_emails / report.total_in * 100) if report.total_in else 0.0

    # Provider waterfall table rows
    waterfall_rows = []
    for name, stats in report.by_provider.items():
        calls = stats.get('calls', 0)
        hits = stats.get('hits', 0)
        rate = (hits / calls) if calls else 0.0
        credits_val = stats.get('credits', 0)
        waterfall_rows.append(f"""          <tr>
            <td><strong>{html.escape(str(name))}</strong></td>
            <td class="text-right num-mono">{calls}</td>
            <td class="text-right num-mono">{hits}</td>
            <td>
              <div class="bar-container">
                <div class="bar-track">
                  <div class="bar-fill" style="width: {rate * 100:.1f}%;"></div>
                </div>
                <span class="bar-pct">{rate:.1%}</span>
              </div>
            </td>
            <td class="text-right num-mono">{credits_val:g}</td>
          </tr>""")
    waterfall_html = "\n".join(waterfall_rows) if waterfall_rows else """          <tr><td colspan="5" class="empty-state">No provider waterfall data available</td></tr>"""

    # Tier distribution rows (A, B, C, D)
    tier_rows = []
    for tier in ('A', 'B', 'C', 'D'):
        count = report.tiers.get(tier, 0)
        pct = (count / report.total_in * 100) if report.total_in else 0.0
        tier_lower = tier.lower()
        tier_rows.append(f"""        <div class="tier-item">
          <div class="tier-pill-col">
            <span class="pill pill-tier-{tier_lower}">Tier {tier}</span>
          </div>
          <div class="tier-track">
            <div class="tier-fill tier-fill-{tier_lower}" style="width: {pct:.1f}%;"></div>
          </div>
          <div class="tier-stats">
            <span class="tier-count">{count}</span>
            <span class="tier-pct">({pct:.1f}%)</span>
          </div>
        </div>""")
    tiers_html = "\n".join(tier_rows)

    # Dedupe actions rows
    dedupe_rows = []
    for action, count in report.dedupe.items():
        action_label = action.replace('_', ' ').capitalize()
        dedupe_rows.append(f"""        <div class="action-row">
          <span class="action-key">{html.escape(action_label)}</span>
          <span class="action-val num-mono">{count}</span>
        </div>""")
    dedupe_html = "\n".join(dedupe_rows) if dedupe_rows else """        <div class="empty-state">No deduplication actions</div>"""

    # HubSpot actions rows
    hubspot_rows = []
    for action, count in report.hubspot.items():
        action_label = action.replace('_', ' ').capitalize()
        hubspot_rows.append(f"""        <div class="action-row">
          <span class="action-key">{html.escape(action_label)}</span>
          <span class="action-val num-mono">{count}</span>
        </div>""")
    hubspot_html = "\n".join(hubspot_rows) if hubspot_rows else """        <div class="empty-state">No HubSpot actions</div>"""

    # Top leads rows
    top_leads_rows = []
    sorted_leads = sorted(report.top_leads, key=lambda lead: lead.score, reverse=True)
    for lead in sorted_leads:
        name = f"{lead.first_name} {lead.last_name}".strip() or "—"
        company = lead.company or lead.domain or "—"
        title = lead.title or "—"
        tier_lower = lead.tier.lower()
        tags = "".join(f'<span class="reason-tag">{html.escape(r)}</span>' for r in lead.score_reasons)
        if not tags:
            tags = '<span class="text-muted">—</span>'
        top_leads_rows.append(f"""          <tr>
            <td>
              <div class="lead-name">{html.escape(name)}</div>
              {f'<div class="lead-email">{html.escape(lead.email)}</div>' if lead.email else ''}
            </td>
            <td>{html.escape(company)}</td>
            <td>{html.escape(title)}</td>
            <td class="text-right num-mono font-bold">{lead.score}</td>
            <td style="text-align: center;"><span class="pill pill-tier-{tier_lower}">Tier {html.escape(lead.tier)}</span></td>
            <td><div class="reasons-tags">{tags}</div></td>
          </tr>""")
    top_leads_html = "\n".join(top_leads_rows) if top_leads_rows else """          <tr><td colspan="6" class="empty-state">No leads available</td></tr>"""

    # Rejected rows
    if report.rejected:
        rejected_rows = []
        for item in report.rejected:
            row_id = str(item.get('row_id', '—'))
            email = str(item.get('email', '—'))
            reason = str(item.get('reason', '—'))
            rejected_rows.append(f"""          <tr>
            <td class="num-mono">{html.escape(row_id)}</td>
            <td>{html.escape(email)}</td>
            <td><span class="pill pill-rejected">{html.escape(reason)}</span></td>
          </tr>""")
        rejected_content = f"""      <div class="table-wrap">
        <table style="min-width: 500px;">
          <thead>
            <tr>
              <th>Row ID</th>
              <th>Email</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
{chr(10).join(rejected_rows)}
          </tbody>
        </table>
      </div>"""
    else:
        rejected_content = """      <div class="empty-state-success">✓ No rejected rows — all incoming records passed validation checks.</div>"""

    # Errors section (if any)
    errors_section = ""
    if report.errors:
        error_items = "".join(f"<li>{html.escape(err)}</li>" for err in report.errors)
        errors_section = f"""    <div class="card error-card">
      <div class="card-title">Pipeline Errors</div>
      <ul class="error-list">{error_items}</ul>
    </div>"""

    mode_badge = (
        '<span class="badge badge-dry"><span class="badge-dot"></span>Dry run</span>'
        if report.dry_run
        else '<span class="badge badge-applied"><span class="badge-dot"></span>Applied</span>'
    )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Clay → HubSpot enrichment run</title>
  <style>
    :root {{
      --bg: #f4f6fb;
      --text-main: #1b1f3b;
      --text-muted: #5a6482;
      --text-light: #8e9bb4;
      --accent: #ff7a59;
      --accent-light: #fff0ec;
      --card-bg: #ffffff;
      --border: #e2e8f0;
      --border-light: #f1f4f9;
      --shadow-sm: 0 1px 3px rgba(27, 31, 59, 0.04), 0 1px 2px rgba(27, 31, 59, 0.02);
      --shadow-md: 0 4px 16px rgba(27, 31, 59, 0.06), 0 1px 3px rgba(27, 31, 59, 0.03);
      --radius: 12px;
      --radius-sm: 6px;
      --tier-a: #10b981;
      --tier-a-bg: #ecfdf5;
      --tier-b: #3b82f6;
      --tier-b-bg: #eff6ff;
      --tier-c: #f59e0b;
      --tier-c-bg: #fffbeb;
      --tier-d: #64748b;
      --tier-d-bg: #f8fafc;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      background-color: var(--bg);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      font-size: 14px;
      -webkit-font-smoothing: antialiased;
      padding: 32px 16px;
      overflow-x: hidden;
      width: 100%;
    }}

    .container {{
      max-width: 1200px;
      margin: 0 auto;
    }}

    /* Header */
    .report-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 24px;
      padding: 4px 0;
    }}

    .header-title-group h1 {{
      font-size: 24px;
      font-weight: 700;
      color: var(--text-main);
      letter-spacing: -0.02em;
    }}

    .header-subtitle {{
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 2px;
    }}

    .header-meta {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}

    /* Badges */
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 14px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.02em;
    }}

    .badge-dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
    }}

    .badge-dry {{
      background: #fef3c7;
      color: #92400e;
      border: 1px solid #fde68a;
    }}
    .badge-dry .badge-dot {{
      background: #d97706;
    }}

    .badge-applied {{
      background: #dcfce7;
      color: #166534;
      border: 1px solid #bbf7d0;
    }}
    .badge-applied .badge-dot {{
      background: #16a34a;
    }}

    .badge-count {{
      background: #ffffff;
      color: var(--text-main);
      border: 1px solid var(--border);
      box-shadow: var(--shadow-sm);
    }}

    /* Cards */
    .card {{
      background: var(--card-bg);
      border-radius: var(--radius);
      border: 1px solid var(--border);
      box-shadow: var(--shadow-md);
      padding: 24px;
      margin-bottom: 24px;
    }}

    .card-title {{
      font-size: 16px;
      font-weight: 700;
      color: var(--text-main);
      margin-bottom: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    /* Stat Cards */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }}

    .stat-card {{
      background: var(--card-bg);
      border-radius: var(--radius);
      border: 1px solid var(--border);
      box-shadow: var(--shadow-sm);
      padding: 20px;
      display: flex;
      flex-direction: column;
    }}

    .stat-label {{
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 8px;
    }}

    .stat-val {{
      font-size: 30px;
      font-weight: 700;
      color: var(--text-main);
      line-height: 1.1;
    }}

    .stat-sub {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 6px;
    }}

    /* Tables */
    .table-wrap {{
      width: 100%;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }}

    th {{
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      padding: 10px 14px;
      background: var(--border-light);
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }}

    th:first-child {{
      border-top-left-radius: var(--radius-sm);
      border-bottom-left-radius: var(--radius-sm);
    }}

    th:last-child {{
      border-top-right-radius: var(--radius-sm);
      border-bottom-right-radius: var(--radius-sm);
    }}

    td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-light);
      font-size: 13px;
      color: var(--text-main);
      vertical-align: middle;
    }}

    tr:last-child td {{
      border-bottom: none;
    }}

    .text-right {{
      text-align: right;
    }}

    .font-bold {{
      font-weight: 700;
    }}

    .num-mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}

    /* Waterfall bar */
    .bar-container {{
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 140px;
    }}

    .bar-track {{
      flex: 1;
      height: 8px;
      background: #e9eef7;
      border-radius: 9999px;
      overflow: hidden;
    }}

    .bar-fill {{
      height: 100%;
      background: var(--accent);
      border-radius: 9999px;
    }}

    .bar-pct {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-main);
      min-width: 44px;
      text-align: right;
    }}

    /* Tiers */
    .tier-list {{
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}

    .tier-item {{
      display: flex;
      align-items: center;
      gap: 16px;
    }}

    .tier-pill-col {{
      width: 76px;
      flex-shrink: 0;
    }}

    .tier-track {{
      flex: 1;
      height: 12px;
      background: #e9eef7;
      border-radius: 9999px;
      overflow: hidden;
    }}

    .tier-fill {{
      height: 100%;
      border-radius: 9999px;
      transition: width 0.3s ease;
    }}

    .tier-fill-a {{ background: var(--tier-a); }}
    .tier-fill-b {{ background: var(--tier-b); }}
    .tier-fill-c {{ background: var(--tier-c); }}
    .tier-fill-d {{ background: var(--tier-d); }}

    .tier-stats {{
      width: 100px;
      flex-shrink: 0;
      text-align: right;
      font-size: 13px;
    }}

    .tier-count {{
      font-weight: 700;
      color: var(--text-main);
    }}

    .tier-pct {{
      color: var(--text-muted);
      font-size: 12px;
      margin-left: 4px;
    }}

    /* Pills */
    .pill {{
      display: inline-block;
      padding: 3px 10px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      text-align: center;
      white-space: nowrap;
    }}

    .pill-tier-a {{ background: var(--tier-a-bg); color: #065f46; border: 1px solid #a7f3d0; }}
    .pill-tier-b {{ background: var(--tier-b-bg); color: #1e40af; border: 1px solid #bfdbfe; }}
    .pill-tier-c {{ background: var(--tier-c-bg); color: #92400e; border: 1px solid #fde68a; }}
    .pill-tier-d {{ background: var(--tier-d-bg); color: #475569; border: 1px solid #cbd5e1; }}

    .pill-rejected {{ background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }}

    /* Side by side cards */
    .split-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-bottom: 24px;
    }}

    .split-grid .card {{
      margin-bottom: 0;
    }}

    .action-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 0;
      border-bottom: 1px solid var(--border-light);
      font-size: 13px;
    }}

    .action-row:last-child {{
      border-bottom: none;
    }}

    .action-key {{
      color: var(--text-main);
    }}

    .action-val {{
      font-weight: 600;
      background: #f1f4f9;
      color: var(--text-main);
      padding: 2px 10px;
      border-radius: 9999px;
      font-size: 12px;
    }}

    /* Top leads styling */
    .lead-name {{
      font-weight: 600;
      color: var(--text-main);
    }}

    .lead-email {{
      font-size: 12px;
      color: var(--text-muted);
    }}

    .reasons-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}

    .reason-tag {{
      background: #f1f4f9;
      color: #3e4868;
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 4px;
      white-space: nowrap;
    }}

    .empty-state {{
      color: var(--text-muted);
      font-style: italic;
      padding: 12px 0;
      text-align: center;
    }}

    .empty-state-success {{
      color: #065f46;
      background: var(--tier-a-bg);
      padding: 14px 18px;
      border-radius: var(--radius-sm);
      border: 1px solid #a7f3d0;
      font-weight: 500;
    }}

    .error-card {{
      border-color: #fecaca;
      background: #fffafa;
    }}

    .error-list {{
      padding-left: 20px;
      color: #991b1b;
    }}

    /* Responsive */
    @media (max-width: 900px) {{
      .stats-grid {{
        grid-template-columns: repeat(2, 1fr);
      }}
    }}

    @media (max-width: 768px) {{
      .split-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    @media (max-width: 480px) {{
      .stats-grid {{
        grid-template-columns: 1fr;
      }}
      .report-header {{
        flex-direction: column;
        align-items: flex-start;
      }}
      body {{
        padding: 16px 8px;
      }}
      .card {{
        padding: 16px;
      }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <header class="report-header">
      <div class="header-title-group">
        <h1>Clay → HubSpot enrichment run</h1>
        <div class="header-subtitle">Pipeline Run Overview · SaneDevs Portfolio</div>
      </div>
      <div class="header-meta">
        {mode_badge}
        <span class="badge badge-count"><strong>{report.total_in}</strong> leads</span>
      </div>
    </header>

    <!-- Row of 4 Stat Cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Leads In</div>
        <div class="stat-val num-mono">{report.total_in}</div>
        <div class="stat-sub">Total input records</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Enriched</div>
        <div class="stat-val num-mono">{report.enriched}</div>
        <div class="stat-sub">{enriched_pct:.1f}% coverage</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Valid Emails</div>
        <div class="stat-val num-mono">{report.valid_emails}</div>
        <div class="stat-sub">{valid_pct:.1f}% hygiene pass rate</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Credits Spent</div>
        <div class="stat-val num-mono">{credits_spent_str}</div>
        <div class="stat-sub">Across all waterfall providers</div>
      </div>
    </div>

    <!-- Provider Waterfall Table -->
    <div class="card">
      <div class="card-title">Provider Waterfall</div>
      <div class="table-wrap">
        <table style="min-width: 540px;">
          <thead>
            <tr>
              <th>Provider</th>
              <th class="text-right">Calls</th>
              <th class="text-right">Hits</th>
              <th>Hit rate</th>
              <th class="text-right">Credits</th>
            </tr>
          </thead>
          <tbody>
{waterfall_html}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Tier Distribution -->
    <div class="card">
      <div class="card-title">Tier Distribution</div>
      <div class="tier-list">
{tiers_html}
      </div>
    </div>

    <!-- Dedupe and HubSpot actions side-by-side -->
    <div class="split-grid">
      <div class="card">
        <div class="card-title">Dedupe Actions</div>
{dedupe_html}
      </div>
      <div class="card">
        <div class="card-title">HubSpot Actions ({'Planned' if report.dry_run else 'Applied'})</div>
{hubspot_html}
      </div>
    </div>

    <!-- Top Leads Table -->
    <div class="card">
      <div class="card-title">Top Leads</div>
      <div class="table-wrap">
        <table style="min-width: 720px;">
          <thead>
            <tr>
              <th>Name</th>
              <th>Company</th>
              <th>Title</th>
              <th class="text-right">Score</th>
              <th style="text-align: center;">Tier</th>
              <th>Reasons</th>
            </tr>
          </thead>
          <tbody>
{top_leads_html}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Rejected Rows -->
    <div class="card">
      <div class="card-title">Rejected Rows</div>
{rejected_content}
    </div>

    {errors_section}
  </div>
</body>
</html>
"""
    html_path.write_text(doc, encoding='utf-8')
    return str(html_path)
