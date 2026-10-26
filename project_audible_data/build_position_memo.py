#!/usr/bin/env python3
"""Generate the Position Memo (2 pages max) in Submit/Project Audible Position Memo.docx.

Every number is read from the pipeline outputs, so the memo cannot drift from the dashboard:
  data/2025/analysis/dashboard_slices.json   (controlled baseline; same data as the dashboard)
  data/2025/analysis/pricing_summary.json    (confidence intervals, 4-way cells)
  data/2025/analysis/by_dti_cltv_grid.csv    (ex-Rocket cell gaps)

If the non-fintech nonbank check has not been run yet, the memo prints a red
"PENDING" sentence instead of a number. Rerun analyze_pricing.py and build_dashboard.py,
then this script, before submitting.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from build_technical_memo import W_MAIN, bullet_p, p_xml, r_xml, section_heading, table_xml

STD_DTI = ['<30%', '30%-<36%', '36%-43%', '44%-49%']
CLTV = ['<=80%', '80.01%-90%', '90.01%-95%', '>95%']
NONBANK_PREFIX = 'Alternative comparator'
BODY = 19      # half-points (9.5 pt)
INK = '1E293B'
ACCENT = 'B45309'
ALERT = 'B91C1C'


def bps(v):
    """Format like the dashboard (JavaScript toFixed rounds halves up; Python's format would round 12.25 to 12.2)."""
    from decimal import Decimal, ROUND_HALF_UP
    q = Decimal(repr(v)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    return f'{"+" if q > 0 else ""}{q} bps'


def pct(v, d=3):
    return f'{v:.{d}f}%'


def load(analysis_dir: Path):
    dash = json.loads((analysis_dir / 'dashboard_slices.json').read_text(encoding='utf-8'))
    summary = json.loads((analysis_dir / 'pricing_summary.json').read_text(encoding='utf-8'))
    grid = list(csv.DictReader((analysis_dir / 'by_dti_cltv_grid.csv').open(encoding='utf-8')))
    return dash, summary, grid


def facts(dash, summary, grid):
    """Derive every number the memo cites from pipeline outputs."""
    S = dash['slices_data']['slices']
    B = dash['slices_data']['bars']
    base = S['ALL|ALL|ALL']
    cells = [S[f'ALL|{d}|{c}'] for d in STD_DTI for c in CLTV]
    hi_cltv = [S[f'ALL|{d}|>95%']['gap_rs'] for d in STD_DTI]
    ex_rocket = [float(r['ex_rocket_gap_bps']) for r in grid
                 if r['dti_group'] in STD_DTI and r['ex_rocket_gap_bps'] not in ('', None)]
    states = [S[f"{s['code']}|ALL|ALL"] for s in dash['slices_data']['states']]
    lenders = dash['fintech_lenders']
    ls = dash.get('lender_stats') or {
        'above_bank': sum(1 for r in lenders if (r['gap_vs_bank_median_bps'] or 0) > 0),
        'above_5bps': sum(1 for r in lenders if (r['gap_vs_bank_median_bps'] or 0) >= 5),
        'total': len(lenders),
    }
    hm = summary['headline_metrics']
    if hm.get('baseline_lender_cluster_ci95_bps') and None not in hm['baseline_lender_cluster_ci95_bps']:
        ci, ci_label = hm['baseline_lender_cluster_ci95_bps'], 'lender-clustered 95% CI'
    else:
        ci, ci_label = hm['lender_cluster_ci95_bps'], 'lender-clustered 95% CI, full sample'
    nonbank = next((r for r in dash['robustness_checks'] if r['slice'].startswith(NONBANK_PREFIX)), None)
    if nonbank is None and hm.get('national_vs_nonbank'):
        nonbank = hm['national_vs_nonbank']
    # Bank-comparator checks from both outputs, so the memo's range matches the dashboard's.
    bank_specs = [r['rate_spread_gap_bps'] for r in summary.get('robustness_checks', []) + dash['robustness_checks']
                  if not r['slice'].startswith(NONBANK_PREFIX) and r.get('rate_spread_gap_bps') is not None]
    ex_rocket_nat = next((r['rate_spread_gap_bps'] for r in summary.get('robustness_checks', [])
                          if 'excluding Rocket' in r['slice']), None)
    nb_seg = {(r['dimension'], r['group']): r for r in summary.get('nonbank_by_segment', [])}
    rocket = next((r for r in lenders if r['lender_name'].upper().startswith('ROCKET')), None)
    at_parity = sorted((r for r in lenders if (r['gap_vs_bank_median_bps'] or 0) < 5),
                       key=lambda r: r['gap_vs_bank_median_bps'])
    return {
        'base': base, 'n_total': base['nf'] + base['nb'],
        'cells_higher': sum(1 for c in cells if c['ok'] and c['gap_rs'] >= 5), 'cells_total': len(cells),
        'cell_min': min(c['gap_rs'] for c in cells), 'cell_max': max(c['gap_rs'] for c in cells),
        'hi_cltv_min': min(hi_cltv), 'hi_cltv_max': max(hi_cltv),
        'ex_rocket_min': min(ex_rocket) if ex_rocket else None,
        'four_way': (hm.get('four_way_cells_fintech_higher'), hm.get('four_way_cells_min25_per_side')),
        'states_higher': sum(1 for s in states if s['ok'] and s['gap_rs'] >= 5), 'states_total': len(states),
        'state_min': min(s['gap_rs'] for s in states), 'state_max': max(s['gap_rs'] for s in states),
        'ls': ls, 'rocket': rocket, 'at_parity': at_parity, 'ci': ci, 'ci_label': ci_label,
        'nonbank': nonbank, 'nb_seg': nb_seg, 'priority': summary.get('nonbank_priority'),
        'bank_spec_range': (min(bank_specs), max(bank_specs)) if bank_specs else None,
        'ex_rocket_nat': ex_rocket_nat,
        'seg': {
            'cltv_low': B['ALL|cltv|<=80%'], 'cltv_high': B['ALL|cltv|>95%'],
            'loan_small': B['ALL|loan|<=$200k'], 'inc_low': B['ALL|income|<=$75k'],
            'inc_high': B['ALL|income|>$200k'],
        },
    }


def para(runs, before=30, after=40):
    return p_xml(runs, before=before, after=after, line=228)


def t(text, bold=False, color=INK, italic=False):
    return r_xml(text, bold=bold, italic=italic, size_half_pt=BODY, color=color)


def nb_state(f):
    """'pending' (check not run), 'peer' (fintech priced like other nonbanks) or 'fintech' (premium remains)."""
    nb = f['nonbank']
    if not nb or nb.get('rate_spread_gap_bps') is None:
        return 'pending'
    return 'peer' if nb['rate_spread_gap_bps'] < 5 else 'fintech'


def pending(text):
    return t(text, bold=True, color=ALERT)


def focus_text(f):
    """Where the review starts, from analyze_pricing.nonbank_priority (a stated rule, not chosen here)."""
    pr = f['priority']
    if not pr:
        return 'origination fees', None
    names = ' and '.join(s['label'] for s in pr['segments'])
    if pr['basis'] == 'rate_spread':
        return names, pr
    if pr['basis'] == 'fees':
        return f'origination fees, first in {names}', pr
    return 'origination fees', pr


def build_document_xml(f, date_text):
    b, s = f['base'], f['seg']
    ls, rk, nb = f['ls'], f['rocket'], f['nonbank']
    state = nb_state(f)
    focus, pr = focus_text(f)
    parts = []
    parts.append(p_xml([r_xml('FINTECH 590 — PROJECT AUDIBLE: POSITION MEMO', bold=True, size_half_pt=22)],
                       before=0, after=12, line=215))
    parts.append(p_xml([
        r_xml('To: ', bold=True, size_half_pt=18, color=ACCENT),
        r_xml('American Fintech Council (AFC) leadership   |   ', size_half_pt=18, color='334155'),
        r_xml('From: ', bold=True, size_half_pt=18, color=ACCENT),
        r_xml('Angga Lesmana   |   ', size_half_pt=18, color='334155'),
        r_xml('Date: ', bold=True, size_half_pt=18, color=ACCENT),
        r_xml(date_text, size_half_pt=18, color='334155'),
    ], before=0, after=6, line=205))
    parts.append(p_xml([
        r_xml('Decision: ', bold=True, size_half_pt=18, color=ACCENT),
        r_xml('Should AFC launch a mortgage-pricing review program for its members?', size_half_pt=18, color='334155'),
    ], before=0, after=40, line=205, bottom_border=True))

    # Recommendation first (Backwards First)
    parts.append(section_heading(f'Recommendation: Yes — a member pricing review benchmarked against nonbank peers, starting with {focus}'))
    lead = [
        t('In 2025, fintech borrowers paid more than bank borrowers with comparable observed profiles. '),
        t(f'The fintech median rate spread was {bps(b["gap_rs"])} higher than at banks ({pct(b["rs_f"])} vs. {pct(b["rs_b"])}), ', bold=True),
        t(f'in {"all " if f["cells_higher"] == f["cells_total"] else ""}{f["cells_higher"]} of {f["cells_total"]} debt-to-income × loan-to-value groups and {f["states_higher"]} of the '
          f'{f["states_total"]} largest states. '),
    ]
    if state == 'peer':
        lead += [
            t(f'Fintech lenders, however, price in line with other nonbank lenders ({bps(nb["rate_spread_gap_bps"])}), ', bold=True),
            t('so the premium points to the nonbank business model rather than a fintech-specific markup. '
              f'AFC should run a voluntary review that benchmarks each member against nonbank peers as well as banks, starting with {focus}, '
              f'where members still charge more than nonbank peers (fees {bps(nb["orig_pct_gap_bps"])}). '),
        ]
    elif state == 'fintech':
        lead += [
            t(f'Fintech lenders also price {bps(nb["rate_spread_gap_bps"])} above other nonbank lenders, ', bold=True),
            t(f'so the premium is not just a nonbank effect. AFC should run a voluntary review benchmarked against both banks and nonbank peers, starting with {focus}. '),
        ]
    else:
        lead += [pending('PENDING — rerun analyze_pricing.py, build_dashboard.py and this script: the nonbank benchmark is missing. ')]
    lead.append(t('The review is diagnostic: a price gap alone does not justify telling any member to change prices.'))
    parts.append(para(lead))

    # What
    parts.append(section_heading('What the data shows'))
    parts.append(bullet_p(
        'Versus banks, the premium is robust. ',
        f'Sample: 2025 HMDA conventional conforming 30-year fixed purchase loans; {b["nf"]:,} loans from {b["lf"]} fintech lenders '
        f'(NYU Stern list) vs. {b["nb"]:,} from {b["lb"]} banks, valid borrower data, DTI below 50% '
        f'({f["ci_label"]}: {bps(f["ci"][0])} to {bps(f["ci"][1])}). {ls["above_bank"]} of {ls["total"]} fintech lenders price above the '
        f'bank median. Rocket Mortgage is {rk["share_of_fintech_loans_pct"]:.0f}% of fintech loans; without it the gap is '
        f'{bps(f["ex_rocket_nat"]) if f["ex_rocket_nat"] is not None else "unchanged"}.' if rk else '', BODY))
    if state != 'pending':
        parts.append(bullet_p(
            'Versus other nonbanks, it largely disappears. ' if state == 'peer' else 'Versus other nonbanks, a premium remains. ',
            f'Compared with {nb.get("comparator_lenders") or nb["bank_lenders"]:,} non-fintech nonbank lenders '
            f'({nb.get("comparator_loans_rs") or nb["bank_loans_rs"]:,} loans, same filters), the fintech rate-spread gap is '
            f'{bps(nb["rate_spread_gap_bps"])}, the rate gap {bps(nb["interest_rate_gap_bps"])} and the fee gap '
            f'{bps(nb["orig_pct_gap_bps"])}. ' + ('Fees are the one gap that remains.' if state == 'peer' else ''), BODY))
    parts.append(bullet_p(
        'Versus banks, the gap is largest for borrowers with the least room to absorb it. ',
        f'Borrowers with under 5% down face {s["cltv_high"]["gap_rs"] / s["cltv_low"]["gap_rs"]:.1f} times the gap of borrowers with 20% down; '
        f'for incomes of $75k or less it comes through fees ({bps(s["inc_low"]["gap_oc"])}), not the note rate ({bps(s["inc_low"]["gap_ir"])}).', BODY))

    def nb_cells(dim, group):
        r = f['nb_seg'].get((dim, group))
        if not r:
            return ['rerun', 'rerun']
        mark = '' if r['coverage_ok'] else ' (thin)'
        return [bps(r['rate_spread_gap_bps']) + mark, bps(r['orig_pct_gap_bps']) + mark]

    rows = [['All comparable loans', f'{b["nf"]:,} / {b["nb"]:,}', bps(b['gap_rs']),
             bps(nb['rate_spread_gap_bps']) if state != 'pending' else 'rerun',
             bps(nb['orig_pct_gap_bps']) if state != 'pending' else 'rerun']]
    for label, key, dim, group in [('Down payment 20%+ (CLTV ≤80%)', 'cltv_low', 'cltv_group', '<=80%'),
                                   ('Down payment <5% (CLTV >95%)', 'cltv_high', 'cltv_group', '>95%'),
                                   ('Loan ≤$200k', 'loan_small', 'loan_amount_group', '<=$200k'),
                                   ('Income ≤$75k', 'inc_low', 'income_group', '<=$75k'),
                                   ('Income >$200k', 'inc_high', 'income_group', '>$200k')]:
        r = s[key]
        rows.append([label, f'{r["nf"]:,} / {r["nb"]:,}', bps(r['gap_rs'])] + nb_cells(dim, group))
    parts.append(table_xml(
        ['Borrower group', 'Loans (Fintech / Bank)', 'Rate-spread gap vs. banks', 'Rate-spread gap vs. nonbanks', 'Fee gap vs. nonbanks'],
        rows, [3000, 1900, 1900, 1900, 1812]))
    note = ('Gap = Fintech median − comparator median. Rate spread = APR − APOR (benchmark rate on the lock date). '
            'Nonbanks = non-fintech independent mortgage banks (Philadelphia Fed TYPE 40/41). Source: FFIEC 2025 HMDA; '
            'dashboard Overview tab and technical memo.')
    if not f['nb_seg']:
        note += ' "rerun" = segment benchmark not yet computed; rerun analyze_pricing.py.'
    parts.append(p_xml([r_xml(note, italic=True, size_half_pt=16, color='475569')], before=20, after=20, line=200))

    # So what / Now what
    parts.append(section_heading('Why it matters to AFC, and what to do'))
    parts.append(para([
        t('So what: ', bold=True, color=ACCENT),
        t('anyone with public HMDA data, including regulators and the press, will compare fintech lenders with banks and see a '
          'premium that is largest for small down payments and small loans. ' +
          ('Our data suggest the fair comparison is with other nonbanks, where members look similar, but only member data can show that. '
           if state == 'peer' else '') +
          'Running the review first lets AFC lead the answer instead of reacting to someone else’s.'),
    ]))
    parts.append(bullet_p('Step 1 (Q1 2027): ', 'invite members to join; publish the HMDA benchmarks against banks and nonbank peers.', BODY))
    parts.append(bullet_p('Step 2: ', f'each member explains its gap, starting with {focus}, using credit score, LLPAs, rate-lock date, '
                          'discount points and lender credits that public HMDA omits.', BODY))
    parts.append(bullet_p('Step 3: ', 'AFC reports, in aggregate, how much of the gap credit risk and the nonbank model explain; members act only on '
                          'the unexplained part. If little is left, AFC publishes that as evidence.', BODY))

    # Limitations
    parts.append(section_heading('Strongest objection, biggest limitation, and why the position holds'))
    if state == 'peer':
        parts.append(bullet_p(
            'Objection — "This is a nonbank pattern, so why review fintech members?" ',
            'On the rate spread we agree, which is why the benchmark is nonbank peers and the review is voluntary and diagnostic. '
            f'Fees still sit {bps(nb["orig_pct_gap_bps"])} above nonbank peers, and borrowers will still compare members with banks.', BODY))
    parts.append(bullet_p(
        'Limitation — data and definitions. ',
        'Public HMDA has no credit scores or exact lock dates, and risk-based pricing is steepest at high loan-to-value. "Fintech" is the '
        'NYU Stern / Fuster et al. (2019) list of fully online lenders, last updated in 2017 (15 of 18 matched in 2025). Some unlisted '
        'nonbanks also originate online, which pulls the fintech-versus-nonbank gap toward zero.', BODY))
    rng = f['bank_spec_range']
    parts.append(bullet_p(
        'Why the recommendation still holds: ',
        (f'versus banks the gap stays between {bps(rng[0])} and {bps(rng[1])} across every sample definition we tested, and in '
         f'{f["four_way"][0]} of {f["four_way"][1]} groups split four ways (DTI, CLTV, income, loan size). ' if rng else '') +
        'The recommendation follows the evidence: it benchmarks members against their real peers instead of assuming a fintech markup, '
        'it targets the gap that remains, and it is low-cost and voluntary. HMDA describes 2025 pricing, not current offers.', BODY))

    sect_pr = ('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
               '<w:pgMar w:top="720" w:right="864" w:bottom="720" w:left="864" w:header="432" w:footer="432" w:gutter="0"/>'
               '</w:sectPr>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W_MAIN}"><w:body>{"".join(parts)}{sect_pr}</w:body></w:document>')


def main(date_text='October 26, 2026'):
    base_dir = Path(__file__).resolve().parent.parent
    analysis_dir = Path(__file__).resolve().parent / 'data' / '2025' / 'analysis'
    f = facts(*load(analysis_dir))
    template_docx = base_dir / 'Project Audible Initial Pitch AFC.docx'
    out_docx = base_dir / 'Submit' / 'Project Audible Position Memo.docx'
    out_docx.parent.mkdir(parents=True, exist_ok=True)
    doc_xml = build_document_xml(f, date_text).encode('utf-8')
    with ZipFile(template_docx, 'r') as zin, ZipFile(out_docx, 'w', compression=ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, doc_xml if item.filename == 'word/document.xml' else zin.read(item.filename))
    print(f'Wrote {out_docx} ({out_docx.stat().st_size / 1024:.1f} KiB)'
          + ('' if f['nonbank'] else ' — WARNING: nonbank check missing; memo shows a red PENDING line.')
          + ('' if f['nb_seg'] else ' — NOTE: nonbank segment benchmark missing; rerun analyze_pricing.py.'))


if __name__ == '__main__':
    main()
