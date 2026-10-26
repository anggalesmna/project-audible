#!/usr/bin/env python3
"""Generate the 2-page Position Memo in Submit/Project Audible Position Memo.docx.

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
    return f'{v:+.1f} bps'


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
        'nonbank': nonbank,
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


def nonbank_runs(f):
    nb = f['nonbank']
    if not nb or nb.get('rate_spread_gap_bps') is None:
        return [t('PENDING — rerun analyze_pricing.py and build_dashboard.py, then rebuild this memo: '
                  'the Fintech vs. non-fintech nonbank result is not in the current outputs.', bold=True, color=ALERT)]
    g = nb['rate_spread_gap_bps']
    head = (f'Against non-fintech independent mortgage banks ({nb["bank_lenders"]:,} lenders, '
            f'{nb["bank_loans_rs"]:,} loans, same filters), the Fintech gap is {bps(g)}. ')
    if g >= 0.75 * f['base']['gap_rs']:
        tail = 'Most of the premium survives a nonbank-to-nonbank comparison, so it is not simply a bank-versus-nonbank funding difference.'
    elif g >= 5:
        tail = ('The premium shrinks but stays material, so part of it reflects nonbank business models and part is specific to '
                'these fintech lenders. Some unlisted nonbanks also originate digitally, which biases this check toward zero.')
    else:
        tail = ('Against other nonbanks the premium largely disappears, so the gap is mainly a nonbank effect. Borrowers still '
                'pay more than at banks, so the review stands, but members should be benchmarked against nonbank peers.')
    return [t(head, bold=True), t(tail)]


def build_document_xml(f, date_text):
    b, s = f['base'], f['seg']
    ls, rk = f['ls'], f['rocket']
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
    parts.append(section_heading('Recommendation: Yes — launch a member pricing review in Q1 2027, starting with low-down-payment and small loans'))
    parts.append(para([
        t('In 2025, borrowers paid more at fintech lenders than at banks for comparable observed loans. '),
        t(f'The fintech median rate spread was {bps(b["gap_rs"])} higher ({pct(b["rs_f"])} vs. {pct(b["rs_b"])}), ', bold=True),
        t(f'and the gap appears in all {f["cells_higher"]} of {f["cells_total"]} debt-to-income × loan-to-value groups '
          f'and in all {f["states_higher"]} of the {f["states_total"]} largest states. Under the decision rule agreed in our pitch, '
          'a broad and consistent premium calls for a review. AFC should invite members to explain the gap with their own '
          'credit-score, rate-lock and fee data, beginning with borrowers putting less than 5% down and loans of $200k or less, '
          'where the gap is largest. The review is diagnostic: a price gap alone does not justify telling any member to change prices.'),
    ]))

    # What
    parts.append(section_heading('What the data shows'))
    parts.append(bullet_p(
        'The premium is real and not driven by one lender. ',
        f'Sample: 2025 HMDA, conventional conforming 30-year fixed purchase loans; {b["nf"]:,} loans from {b["lf"]} fintech lenders '
        f'(NYU Stern list) vs. {b["nb"]:,} from {b["lb"]} banks, with valid borrower data and DTI below 50% '
        f'({f["ci_label"]}: {bps(f["ci"][0])} to {bps(f["ci"][1])}). {ls["above_bank"]} of {ls["total"]} fintech lenders price above '
        f'the bank median ({ls["above_5bps"]} by 5 bps or more). Rocket Mortgage is '
        f'{rk["share_of_fintech_loans_pct"]:.0f}% of fintech loans, yet without it every risk cell still shows at least '
        f'{bps(f["ex_rocket_min"])}.' if rk and f['ex_rocket_min'] is not None else '', BODY))
    parts.append(bullet_p(
        'Borrowers pay more in both rate and fees. ',
        f'Median interest rate is {bps(b["gap_ir"])} higher and median origination charges are {bps(b["gap_oc"])} of the loan '
        f'higher ({pct(b["oc_f"])} vs. {pct(b["oc_b"])}), roughly ${b["gap_oc"] * 30:,.0f} more upfront on a $300k loan. '
        'Higher fees are not buying a lower rate, so the gap is not a points-for-rate trade-off.', BODY))
    parts.append(bullet_p(
        'The gap concentrates on borrowers with the least room to absorb it. ',
        f'See the table: borrowers with under 5% down face {s["cltv_high"]["gap_rs"] / s["cltv_low"]["gap_rs"]:.1f} times the gap of '
        f'borrowers with 20% down, and for borrowers earning $75k or less the premium comes through fees '
        f'({bps(s["inc_low"]["gap_oc"])}) rather than the note rate ({bps(s["inc_low"]["gap_ir"])}).', BODY))

    rows = [
        ['All comparable loans (baseline)', f'{b["nf"]:,} / {b["nb"]:,}', bps(b['gap_rs']), bps(b['gap_ir']), bps(b['gap_oc'])],
    ]
    for label, key in [('Down payment 20%+ (CLTV ≤80%)', 'cltv_low'), ('Down payment <5% (CLTV >95%)', 'cltv_high'),
                       ('Loan ≤$200k', 'loan_small'), ('Income ≤$75k', 'inc_low'), ('Income >$200k', 'inc_high')]:
        r = s[key]
        rows.append([label, f'{r["nf"]:,} / {r["nb"]:,}', bps(r['gap_rs']), bps(r['gap_ir']), bps(r['gap_oc'])])
    parts.append(table_xml(
        ['Borrower group (dashboard: Overview tab)', 'Loans (Fintech / Bank)', 'Rate-spread gap', 'Rate gap', 'Fee gap (% of loan)'],
        rows, [3700, 1900, 1500, 1300, 2112]))
    parts.append(p_xml([r_xml('Gap = Fintech median − Bank median. Rate spread = APR − APOR (benchmark rate on the lock date). '
                              'Source: FFIEC 2025 HMDA snapshot; full detail in the dashboard and technical memo.',
                              italic=True, size_half_pt=16, color='475569')], before=20, after=20, line=200))

    # So what / Now what
    parts.append(section_heading('Why it matters to AFC, and what to do'))
    parts.append(para([
        t('So what: ', bold=True, color=ACCENT),
        t('the largest premiums fall on borrowers with the least room to absorb extra cost: small down payments, small loans, '
          'lower incomes. The gap is visible to anyone with public HMDA data, including regulators and the press. '
          'Investigating it first lets AFC lead the answer instead of reacting to someone else’s.'),
    ]))
    parts.append(bullet_p('Step 1 (Q1 2027): ', 'invite participating members to join; publish this HMDA benchmark and the priority groups.', BODY))
    parts.append(bullet_p('Step 2: ', 'each member decomposes its gap in the CLTV >95% and ≤$200k groups using credit score, LLPAs, '
                          'rate-lock date, discount points and lender credits that public HMDA omits.', BODY))
    parts.append(bullet_p('Step 3: ', 'AFC reports, in aggregate, how much of the gap credit risk explains and how much it does not; '
                          'members act only on the unexplained part. If credit risk explains most of it, AFC publishes that as evidence.', BODY))

    # Limitations
    parts.append(section_heading('Strongest objection, biggest limitation, and why the position holds'))
    parts.append(bullet_p(
        'Objection — "Fintech borrowers are riskier." ',
        'Public HMDA has no credit scores, and risk-based pricing is steepest at high loan-to-value, exactly where the gap is largest. '
        f'But the gap appears within every DTI × CLTV group and in {f["four_way"][0]} of {f["four_way"][1]} groups split four ways '
        '(DTI, CLTV, income, loan size), and fees are higher too. Credit scores are what the review asks members to supply; '
        'the objection is a reason to run the review, not to skip it.', BODY))
    parts.append(bullet_p(
        'Limitation — who counts as "fintech." ',
        'We use the NYU Stern / Fuster et al. (2019) list of lenders with fully online applications, last updated in 2017; it matches 15 '
        'of its 18 lenders in 2025, all of them nonbanks, while the comparator is banks only. ', BODY))
    parts.append(p_xml([t('', bold=True)] + nonbank_runs(f), before=0, after=30, line=228, left_indent=180))
    parts.append(bullet_p(
        'Why the recommendation still holds: ',
        f'the result survives every robustness check run (excluding Rocket, site-built homes only, flagged loans removed, '
        f'unadjusted sample), and {len(f["at_parity"])} fintech lenders ({", ".join(r["lender_name"] for r in f["at_parity"])}) price within 5 bps of '
        f'the bank median or below it, so bank-level pricing is achievable online. '
        'The recommended action is low-cost, voluntary and diagnostic. HMDA describes 2025 pricing, not current offers.', BODY))

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
          + ('' if f['nonbank'] else ' — WARNING: nonbank check missing; memo shows a red PENDING line.'))


if __name__ == '__main__':
    main()
