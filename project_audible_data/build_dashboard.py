#!/usr/bin/env python3
"""Build the clean 3-tab interactive HTML dashboard for Project Audible.

Reads:
  data/2025/mortgages_2025_clean.csv
  data/2025/analysis/pricing_summary.json

Writes:
  ../Project Audible Dashboard.html
  data/2025/analysis/dashboard_slices.json
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from analyze_pricing import (
    CLTV_ORDER,
    INCOME_ORDER,
    LOAN_ORDER,
    Bucket,
    comparison_role,
    in_baseline,
    median,
    quantile,
    r2,
    r4,
)

# Focus dashboard segmentation on the 4 standard conforming DTI bands (<50% cap),
# which account for 99.6% of all valid-DTI loans in the main comparison sample.
DTI_STANDARD_ORDER = ['<30%', '30%-<36%', '36%-43%', '44%-49%']

STATE_NAMES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
    'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
    'DC': 'District of Columbia', 'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii',
    'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
    'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine',
    'MD': 'Maryland', 'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota',
    'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska',
    'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico',
    'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio',
    'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania', 'PR': 'Puerto Rico',
    'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota',
    'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont',
    'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
    'WI': 'Wisconsin', 'WY': 'Wyoming',
}


def compact_summary(bucket: Bucket):
    s = bucket.summarize()
    return {
        'nf': s['fintech_loans_rs'],
        'nb': s['bank_loans_rs'],
        'lf': s['fintech_lenders'],
        'lb': s['bank_lenders'],
        'ok': s['coverage_ok'],
        'st': s['status'],
        'rs_f': s['fintech_median_rate_spread'],
        'rs_b': s['bank_median_rate_spread'],
        'gap_rs': s['rate_spread_gap_bps'],
        'f_p25': s['fintech_rs_p25'],
        'f_p75': s['fintech_rs_p75'],
        'b_p25': s['bank_rs_p25'],
        'b_p75': s['bank_rs_p25'] if s['bank_rs_p75'] is None else s['bank_rs_p75'],
        'ir_f': s['fintech_median_interest_rate'],
        'ir_b': s['bank_median_interest_rate'],
        'gap_ir': s['interest_rate_gap_bps'],
        'oc_f': s['fintech_median_orig_pct'],
        'oc_b': s['bank_median_orig_pct'],
        'gap_oc': s['orig_pct_gap_bps'],
    }


def compute_slices(clean_csv: Path):
    state_totals = defaultdict(int)
    with clean_csv.open(newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if (
                r['in_main_comparison'] == '1'
                and r['elig_controlled'] == '1'
                and r['dti_group'] in DTI_STANDARD_ORDER
                and r['elig_state'] == '1'
            ):
                state_totals[r['state_code'].strip()] += 1

    top_states = [st for st, _ in sorted(state_totals.items(), key=lambda kv: -kv[1])[:20]]
    if 'NC' not in top_states:
        top_states.append('NC')
    tracked_states = {'ALL', *top_states}

    slices = defaultdict(Bucket)
    dim_bars = defaultdict(Bucket)
    lender_buckets = {}

    rob_base = Bucket()
    rob_ctrl_all_dti = Bucket()
    rob_site_built = Bucket()
    rob_no_flags = Bucket()
    rob_unadjusted = Bucket()
    rob_vs_nonbank = Bucket()
    base_rs_f = defaultdict(list)
    base_rs_b = defaultdict(list)

    with clean_csv.open(newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            role = comparison_role(r)
            if role is None:
                continue
            if role in ('fintech', 'nonbank') and in_baseline(r):
                rob_vs_nonbank.add(
                    role == 'fintech', r['lei'],
                    float(r['rate_spread_num']) if r['elig_rate_spread'] == '1' else None,
                    float(r['interest_rate_num']) if r['elig_interest_rate'] == '1' else None,
                    float(r['orig_charge_pct']) if r['elig_orig_pct'] == '1' else None,
                )
            if role == 'nonbank':
                continue
            is_f = r['lender_type'] == 'Fintech'
            lei = r['lei']
            lender_name = r['lender_name']
            rs = float(r['rate_spread_num']) if r['elig_rate_spread'] == '1' else None
            ir = float(r['interest_rate_num']) if r['elig_interest_rate'] == '1' else None
            oc = float(r['orig_charge_pct']) if r['elig_orig_pct'] == '1' else None

            rob_unadjusted.add(is_f, lei, rs, ir, oc)
            if r['elig_controlled'] == '1':
                rob_ctrl_all_dti.add(is_f, lei, rs, ir, oc)

            # Main Controlled Sample: all 4 borrower vars valid + standard conforming DTI (<50%)
            if r['elig_controlled'] != '1' or r['dti_group'] not in DTI_STANDARD_ORDER:
                continue

            rob_base.add(is_f, lei, rs, ir, oc)
            if rs is not None:
                (base_rs_f if is_f else base_rs_b)[lei].append(rs)
            if r['construction_method'].strip() == '1' and r['total_units'].strip() == '1':
                rob_site_built.add(is_f, lei, rs, ir, oc)
            if not r['review_flags']:
                rob_no_flags.add(is_f, lei, rs, ir, oc)

            if is_f:
                lb = lender_buckets.setdefault(lei, {
                    'lei': lei, 'lender_name': lender_name,
                    'rs': [], 'ir': [], 'oc': [], 'loans': 0,
                })
                lb['loans'] += 1
                if rs is not None:
                    lb['rs'].append(rs)
                if ir is not None:
                    lb['ir'].append(ir)
                if oc is not None:
                    lb['oc'].append(oc)

            st = r['state_code'].strip() if r['elig_state'] == '1' else ''
            dti = r['dti_group']
            cltv = r['cltv_group']
            inc = r['income_group']
            la = r['loan_amount_group']

            states_for_row = ['ALL']
            if st in tracked_states:
                states_for_row.append(st)

            dtis_for_row = ['ALL', dti]
            cltvs_for_row = ['ALL', cltv]

            for s_code in states_for_row:
                for d_code in dtis_for_row:
                    for c_code in cltvs_for_row:
                        slices[f'{s_code}|{d_code}|{c_code}'].add(is_f, lei, rs, ir, oc)

                dim_bars[f'{s_code}|cltv|{cltv}'].add(is_f, lei, rs, ir, oc)
                dim_bars[f'{s_code}|dti|{dti}'].add(is_f, lei, rs, ir, oc)
                dim_bars[f'{s_code}|loan|{la}'].add(is_f, lei, rs, ir, oc)
                dim_bars[f'{s_code}|income|{inc}'].add(is_f, lei, rs, ir, oc)

    out_slices = {k: compact_summary(b) for k, b in slices.items() if (b.loans_f + b.loans_b) > 0}
    out_bars = {k: compact_summary(b) for k, b in dim_bars.items() if (b.loans_f + b.loans_b) > 0}
    state_list = [
        {'code': st, 'name': STATE_NAMES.get(st, st), 'loans': state_totals[st]}
        for st in top_states
    ]

    base_sum = rob_base.summarize({'slice': 'Controlled baseline (4 borrower vars valid, DTI <50%)'})
    bank_med_rs = base_sum['bank_median_rate_spread']
    bank_med_ir = base_sum['bank_median_interest_rate']
    bank_med_oc = base_sum['bank_median_orig_pct']

    fintech_lenders = []
    for lei, lb in lender_buckets.items():
        rs_s = sorted(lb['rs'])
        med_rs = quantile(rs_s, 0.5)
        med_ir = median(lb['ir'])
        med_oc = median(lb['oc'])
        fintech_lenders.append({
            'lei': lei,
            'lender_name': lb['lender_name'],
            'total_loans': lb['loans'],
            'share_of_fintech_loans_pct': r2(100.0 * lb['loans'] / rob_base.loans_f),
            'loans_with_rate_spread': len(rs_s),
            'median_rate_spread': r4(med_rs),
            'gap_vs_bank_median_bps': r2(100.0 * (med_rs - bank_med_rs)) if med_rs is not None else None,
            'median_interest_rate': r4(med_ir),
            'ir_gap_vs_bank_bps': r2(100.0 * (med_ir - bank_med_ir)) if med_ir is not None else None,
            'median_orig_pct': r4(med_oc),
            'orig_pct_gap_vs_bank_bps': r2(100.0 * (med_oc - bank_med_oc)) if med_oc is not None else None,
        })
    fintech_lenders.sort(key=lambda r: -r['total_loans'])

    f_meds = [median(v) for v in base_rs_f.values() if len(v) >= 10]
    b_meds = [median(v) for v in base_rs_b.values() if len(v) >= 10]
    lender_stats = {
        'above_bank': sum(1 for r in fintech_lenders if (r['gap_vs_bank_median_bps'] or 0) > 0),
        'above_5bps': sum(1 for r in fintech_lenders if (r['gap_vs_bank_median_bps'] or 0) >= 5),
        'total': len(fintech_lenders),
        'equal_weighted_gap_bps': r2(100.0 * (median(f_meds) - median(b_meds))) if f_meds and b_meds else None,
    }

    robustness_checks = [
        base_sum,
        rob_vs_nonbank.summarize({'slice': 'Alternative comparator: Fintech vs non-fintech nonbanks (TYPE 40/41)'}),
        rob_ctrl_all_dti.summarize({'slice': 'Controlled sample (all 4 borrower vars valid, incl. DTI >=50%)'}),
        rob_site_built.summarize({'slice': 'Site-built 1-unit properties only (excl. manufactured & multi-unit)'}),
        rob_no_flags.summarize({'slice': 'Excluding all review-flagged loans'}),
        rob_unadjusted.summarize({'slice': 'Unadjusted full sample (incl. missing borrower vars & 21st Mortgage)'}),
    ]

    return {
        'states': state_list,
        'slices': out_slices,
        'bars': out_bars,
        'fintech_lenders': fintech_lenders,
        'robustness_checks': robustness_checks,
        'lender_stats': lender_stats,
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Project Audible — AFC Mortgage Pricing Dashboard</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    :root {
      --bg-page: #f8fafc;
      --bg-card: #ffffff;
      --bg-subtle: #f1f5f9;
      --text-main: #0f172a;
      --text-muted: #475569;
      --border-col: #e2e8f0;
      --fintech-col: #b45309;
      --fintech-fill: #d97706;
      --fintech-bg: #fef3c7;
      --bank-col: #1d4ed8;
      --bank-fill: #2563eb;
      --bank-bg: #dbeafe;
      --accent-col: #0f172a;
      --ok-col: #15803d;
      --ok-bg: #dcfce7;
      --warn-col: #b91c1c;
      --warn-bg: #fee2e2;
      --gradient-space: ;
    }
    @supports (background: linear-gradient(in oklch, red, blue)) {
      :root { --gradient-space: in oklch; }
    }
    *, *::before, *::after { box-sizing: border-box; }
    html { font-size: 100%; }
    body {
      margin: 0;
      background-color: var(--bg-page);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }
    .page-shell {
      max-inline-size: 76rem;
      margin-inline: auto;
      padding-block: 1.25rem 3rem;
      padding-inline: 1.5rem;
      display: grid;
      gap: 1.125rem;
    }
    h1, h2, h3 {
      margin: 0;
      line-height: 1.25;
      letter-spacing: -0.015em;
    }
    .balance-heading { text-wrap: balance; }
    p { margin: 0; text-wrap: pretty; }

    /* Top Minimalist Bar: Eyebrow + Minimalist Tabs */
    .top-bar {
      display: flex;
      flex-wrap: wrap;
      align-items: safe center;
      justify-content: space-between;
      gap: 0.75rem;
      padding-block-end: 0.5rem;
      border-block-end: 1px solid var(--border-col);
    }
    .eyebrow {
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-muted);
    }
    .minimal-tabs {
      display: inline-flex;
      flex-wrap: wrap;
      gap: 0.25rem;
      background: var(--bg-subtle);
      padding: 0.25rem;
      border-radius: 0.5rem;
      border: 1px solid var(--border-col);
    }
    .page-tab-btn {
      padding-block: 0.35rem;
      padding-inline: 0.85rem;
      font-size: 0.8125rem;
      font-weight: 600;
      border-radius: 0.375rem;
      border: none;
      background: transparent;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .page-tab-btn:hover {
      color: var(--text-main);
    }
    .page-tab-btn[aria-selected="true"] {
      background: var(--bg-card);
      color: var(--text-main);
      font-weight: 700;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
    }

    /* Compact Header Card with Straightforward Key Points */
    .header-card {
      background: var(--bg-card);
      border: 1px solid var(--border-col);
      border-inline-start: 4px solid var(--fintech-col);
      border-radius: 0.75rem;
      padding: 1.125rem 1.35rem;
      display: grid;
      gap: 0.75rem;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
    }
    .headline-title {
      font-size: 1.25rem;
      font-weight: 800;
      color: var(--text-main);
    }
    .key-points {
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
      gap: 0.75rem;
      padding-block-start: 0.65rem;
      border-block-start: 1px solid var(--border-col);
    }
    .key-points li {
      font-size: 0.8125rem;
      color: var(--text-main);
    }
    .kp-tag {
      display: inline-block;
      font-size: 0.75rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--fintech-col);
      margin-inline-end: 0.3rem;
    }

    /* Full-Width Balanced Slicer Bar */
    .slicer-card {
      background: var(--bg-card);
      border: 1px solid var(--border-col);
      border-radius: 0.75rem;
      padding: 0.75rem 1.125rem;
      display: grid;
      grid-template-columns: repeat(3, minmax(10rem, 1fr)) auto;
      align-items: end;
      gap: 0.85rem;
    }
    @media (max-width: 720px) {
      .slicer-card {
        grid-template-columns: 1fr;
      }
    }
    .slicer-field {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      min-inline-size: 0;
    }
    .slicer-field label {
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-muted);
    }
    .slicer-field select {
      inline-size: 100%;
      padding-block: 0.45rem;
      padding-inline: 0.65rem;
      font-size: 0.8125rem;
      font-weight: 600;
      color: var(--text-main);
      background-color: var(--bg-subtle);
      border: 1px solid var(--border-col);
      border-radius: 0.4rem;
      cursor: pointer;
    }
    .btn-reset {
      padding-block: 0.45rem;
      padding-inline: 1rem;
      font-size: 0.8125rem;
      font-weight: 700;
      border-radius: 0.4rem;
      border: 1px solid var(--border-col);
      background: var(--bg-subtle);
      color: var(--text-main);
      cursor: pointer;
      white-space: nowrap;
    }
    .btn-reset:hover { background: #e2e8f0; }

    /* KPI Strip */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
      gap: 0.875rem;
    }
    .kpi-card {
      background: var(--bg-card);
      border: 1px solid var(--border-col);
      border-radius: 0.75rem;
      padding: 0.95rem 1.15rem;
      display: grid;
      gap: 0.25rem;
    }
    .kpi-card.primary-kpi {
      border-color: #f59e0b;
      background: linear-gradient(180deg var(--gradient-space), #fffbeb 0%, #ffffff 70%);
    }
    .kpi-label {
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-muted);
    }
    .kpi-value {
      font-size: 1.6rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: var(--text-main);
      font-variant-numeric: tabular-nums;
    }
    .kpi-value.fintech-higher { color: var(--fintech-col); }
    .kpi-value.bank-higher { color: var(--bank-col); }
    .kpi-sub {
      font-size: 0.8125rem;
      color: var(--text-muted);
    }

    /* Tab Panels */
    .tab-panel-inner {
      display: grid;
      gap: 1.125rem;
    }
    .panel-card {
      background: var(--bg-card);
      border: 1px solid var(--border-col);
      border-radius: 0.75rem;
      padding: 1.25rem 1.4rem;
      display: grid;
      gap: 1rem;
      min-inline-size: 0;
    }
    .two-col-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(22rem, 1fr));
      gap: 1.125rem;
      align-items: start;
    }
    .panel-header {
      display: flex;
      flex-wrap: wrap;
      align-items: safe center;
      justify-content: space-between;
      gap: 0.75rem;
    }
    .panel-title {
      font-size: 1rem;
      font-weight: 700;
    }
    .panel-subtitle {
      font-size: 0.8125rem;
      color: var(--text-muted);
    }
    .pill-group {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
    }
    .pill-btn {
      padding-block: 0.32rem;
      padding-inline: 0.65rem;
      font-size: 0.75rem;
      font-weight: 600;
      border-radius: 0.375rem;
      border: 1px solid var(--border-col);
      background: var(--bg-subtle);
      color: var(--text-muted);
      cursor: pointer;
    }
    .pill-btn[aria-pressed="true"] {
      background: var(--accent-col);
      color: #ffffff;
      border-color: var(--accent-col);
    }

    /* Horizontal Bar Chart */
    .chart-rows {
      display: grid;
      gap: 0.6rem;
    }
    .bar-row {
      display: grid;
      grid-template-columns: minmax(8rem, 13rem) 1fr 5rem;
      align-items: safe center;
      gap: 0.75rem;
      font-size: 0.875rem;
      padding-block: 0.3rem;
      padding-inline: 0.45rem;
      border-radius: 0.4rem;
    }
    .bar-row.interactive-row { cursor: pointer; }
    .bar-row.interactive-row:hover { background: var(--bg-subtle); }
    .bar-row.active-slice {
      background: #fef3c7;
      outline: 1px solid #f59e0b;
    }
    .bar-label {
      font-weight: 600;
      color: var(--text-main);
      min-inline-size: 0;
    }
    .bar-label-sub {
      display: block;
      font-size: 0.75rem;
      font-weight: 400;
      color: var(--text-muted);
    }
    .bar-track {
      position: relative;
      block-size: 1.45rem;
      background: var(--bg-subtle);
      border-radius: 0.3rem;
      overflow: clip;
    }
    .zero-line {
      position: absolute;
      inset-block: 0;
      inline-size: 1.5px;
      background: #64748b;
      z-index: 2;
    }
    .bar-fill {
      position: absolute;
      inset-block: 0.2rem;
      border-radius: 0.2rem;
      transition: inline-size 0.2s ease, inset-inline-start 0.2s ease;
    }
    .bar-val {
      text-align: end;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }

    /* Risk Matrix Table */
    .table-scroll {
      overflow-x: auto;
      scrollbar-gutter: stable;
      overscroll-behavior: contain;
    }
    table.clean-table {
      inline-size: 100%;
      border-collapse: collapse;
      font-size: 0.8125rem;
      font-variant-numeric: tabular-nums;
    }
    .clean-table caption {
      text-align: start;
      font-size: 0.75rem;
      color: var(--text-muted);
      padding-block-end: 0.5rem;
    }
    .clean-table th, .clean-table td {
      border: 1px solid var(--border-col);
      padding: 0.55rem 0.6rem;
      text-align: center;
    }
    .clean-table th {
      background: var(--bg-subtle);
      font-weight: 700;
      color: var(--text-main);
    }
    .clean-table th[scope="row"] {
      text-align: start;
      white-space: nowrap;
    }
    .matrix-cell { cursor: pointer; }
    .matrix-cell:hover { outline: 2px solid var(--accent-col); }
    .matrix-cell.selected-cell { outline: 2.5px solid #0f172a; }
    .cell-gap {
      font-weight: 800;
      font-size: 0.875rem;
      display: block;
    }
    .cell-meta {
      font-size: 0.75rem;
      color: var(--text-muted);
      display: block;
    }

    /* Visual Drill-Down Comparison Card (Right Panel in Tab 2) */
    .visual-compare-grid {
      display: grid;
      gap: 0.9rem;
    }
    .vc-block {
      background: var(--bg-subtle);
      border: 1px solid var(--border-col);
      border-radius: 0.55rem;
      padding: 0.75rem 0.9rem;
      display: grid;
      gap: 0.45rem;
    }
    .vc-head {
      display: flex;
      align-items: safe center;
      justify-content: space-between;
      gap: 0.5rem;
      font-size: 0.8125rem;
      font-weight: 700;
    }
    .dual-bar-row {
      display: grid;
      grid-template-columns: 4.5rem 1fr 4.2rem;
      align-items: safe center;
      gap: 0.5rem;
      font-size: 0.75rem;
      font-variant-numeric: tabular-nums;
    }
    .dual-track {
      position: relative;
      block-size: 0.9rem;
      background: #e2e8f0;
      border-radius: 999px;
      overflow: clip;
    }
    .dual-fill {
      position: absolute;
      inset-block: 0;
      inset-inline-start: 0;
      border-radius: 999px;
      transition: inline-size 0.2s ease;
    }
    .iqr-track {
      position: relative;
      block-size: 1.25rem;
      background: #e2e8f0;
      border-radius: 0.25rem;
      overflow: clip;
    }
    .iqr-box {
      position: absolute;
      inset-block: 0.22rem;
      border-radius: 0.15rem;
      opacity: 0.45;
    }
    .iqr-median-dot {
      position: absolute;
      inset-block: 0.1rem;
      inline-size: 4px;
      border-radius: 2px;
      transform: translateX(-2px);
    }
    .sample-split-bar {
      display: flex;
      block-size: 0.85rem;
      border-radius: 999px;
      overflow: clip;
      background: #e2e8f0;
    }
    .badge {
      display: inline-flex;
      align-items: safe center;
      padding-block: 0.18rem;
      padding-inline: 0.55rem;
      border-radius: 0.35rem;
      font-size: 0.75rem;
      font-weight: 700;
      inline-size: fit-content;
    }
    .badge-ok { background: var(--ok-bg); color: var(--ok-col); }
    .badge-warn { background: var(--warn-bg); color: var(--warn-col); }

    .sr-only {
      position: absolute;
      inline-size: 1px;
      block-size: 1px;
      padding: 0;
      margin: -1px;
      overflow: clip;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
  </style>
</head>
<body>
  <div id="live-announcer" class="sr-only" aria-live="polite" aria-atomic="true"></div>

  <div class="page-shell">
    <!-- 1. TOP BAR: TITLE EYEBROW + MINIMALIST 3-TAB NAVIGATION -->
    <div class="top-bar">
      <div class="eyebrow">
        FINTECH 590 • Project Audible • Audience: American Fintech Council (AFC)
      </div>
      <nav aria-label="Dashboard views">
        <div class="minimal-tabs" role="tablist">
          <button type="button" class="page-tab-btn" role="tab" id="tab-btn-overview" aria-controls="panel-overview" aria-selected="true">
            Overview
          </button>
          <button type="button" class="page-tab-btn" role="tab" id="tab-btn-matrix" aria-controls="panel-matrix" aria-selected="false">
            Segment Drill-Down
          </button>
          <button type="button" class="page-tab-btn" role="tab" id="tab-btn-lenders" aria-controls="panel-lenders" aria-selected="false">
            Lenders &amp; Robustness
          </button>
        </div>
      </nav>
    </div>

    <!-- 2. COMPACT HEADER & KEY POINTS -->
    <header class="header-card">
      <h1 class="headline-title balance-heading">
        Fintech Mortgages Are Priced +16.4 bps Higher on Median Rate Spread Than Traditional Bank Mortgages
      </h1>
      <ul class="key-points" aria-label="Key takeaway points">
        <li>
          <span class="kp-tag">What:</span>
          Fintech median rate spread is <strong>+16.4 bps higher</strong> than banks (<code>0.213%</code> vs. <code>0.049%</code>), alongside higher interest rates (<strong>+12.5 bps</strong>) and higher upfront fees (<strong>+37.2 bps</strong>).
        </li>
        <li>
          <span class="kp-tag">So What:</span>
          Fintech pricing is higher in <strong>all 16 of 16</strong> standard <code>DTI &times; CLTV</code> segments and <strong>12 of 14</strong> controlled Fintech lenders, reaching <strong>+28 to +32 bps higher</strong> when <code>CLTV &gt;95%</code>.
        </li>
        <li>
          <span class="kp-tag">Now What:</span>
          <strong>AFC should launch a member pricing review</strong> focused first on <strong>High-CLTV (&gt;95%)</strong> and <strong>Small-Loan (&le;$200k)</strong> segments.
        </li>
      </ul>
    </header>

    <!-- 3. FULL-WIDTH BALANCED SLICER BAR -->
    <search aria-label="Segment filters">
      <div class="slicer-card">
        <div class="slicer-field">
          <label for="sel-state">Property State</label>
          <select id="sel-state"></select>
        </div>
        <div class="slicer-field">
          <label for="sel-dti">Borrower DTI Group (Conforming &lt;50%)</label>
          <select id="sel-dti">
            <option value="ALL">All Standard DTI Groups (&lt;50%)</option>
            <option value="<30%">&lt;30% (Low debt load)</option>
            <option value="30%-<36%">30%–&lt;36% (Moderate)</option>
            <option value="36%-43%">36%–43% (Standard QM band)</option>
            <option value="44%-49%">44%–49% (Stretched DTI)</option>
          </select>
        </div>
        <div class="slicer-field">
          <label for="sel-cltv">Combined LTV (Down Payment)</label>
          <select id="sel-cltv">
            <option value="ALL">All CLTV Groups</option>
            <option value="<=80%">&le;80% (20%+ down)</option>
            <option value="80.01%-90%">80.01%–90% (10–20% down)</option>
            <option value="90.01%-95%">90.01%–95% (5–10% down)</option>
            <option value=">95%">&gt;95% (&lt;5% down)</option>
          </select>
        </div>
        <button type="button" id="btn-reset" class="btn-reset">Reset Filters</button>
      </div>
    </search>

    <main id="tab-panels-root" style="display:grid; gap:1.125rem;">
      <!-- SHARED KPI STRIP -->
      <section aria-label="Key metrics for selected slice" class="kpi-grid">
        <div class="kpi-card primary-kpi">
          <span class="kpi-label">Median Rate-Spread Gap (Main)</span>
          <div id="kpi-rs-gap" class="kpi-value fintech-higher">+16.4 bps</div>
          <p id="kpi-rs-detail" class="kpi-sub">Fintech 0.213% vs. Bank 0.049%</p>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Median Interest-Rate Gap</span>
          <div id="kpi-ir-gap" class="kpi-value">+12.5 bps</div>
          <p id="kpi-ir-detail" class="kpi-sub">Fintech 6.625% vs. Bank 6.500%</p>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Median Origination-Fee Gap</span>
          <div id="kpi-oc-gap" class="kpi-value">+37.2 bps</div>
          <p id="kpi-oc-detail" class="kpi-sub">Fintech 0.947% vs. Bank 0.575% of loan</p>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Active Slice Coverage</span>
          <div id="kpi-cov-badge" class="badge badge-ok">Sufficient Coverage</div>
          <p id="kpi-cov-loans" class="kpi-sub">173,033 Fintech vs. 338,166 Bank loans</p>
        </div>
      </section>

      <!-- TAB 1: OVERVIEW -->
      <section id="panel-overview" role="tabpanel" aria-labelledby="tab-btn-overview">
        <div class="tab-panel-inner">
          <div class="panel-card">
            <div class="panel-header">
              <div>
                <h2 id="overview-chart-title" class="panel-title">Median Rate-Spread Gap by Borrower Group (bps)</h2>
                <p class="panel-subtitle">
                  Positive values (+bps) mean Fintech pricing is higher than traditional banks (0 bps = parity). Click a bar to filter.
                </p>
              </div>
              <div class="pill-group" role="group" aria-label="Select borrower dimension">
                <button type="button" class="pill-btn" data-dim="cltv" aria-pressed="true">By CLTV</button>
                <button type="button" class="pill-btn" data-dim="dti" aria-pressed="false">By DTI</button>
                <button type="button" class="pill-btn" data-dim="loan" aria-pressed="false">By Loan Amount</button>
                <button type="button" class="pill-btn" data-dim="income" aria-pressed="false">By Income</button>
              </div>
            </div>

            <div class="pill-group" role="group" aria-label="Select pricing measure">
              <button type="button" class="pill-btn metric-btn" data-metric="gap_rs" aria-pressed="true">Rate Spread Gap (Main)</button>
              <button type="button" class="pill-btn metric-btn" data-metric="gap_oc" aria-pressed="false">Origination Fee Gap (% Loan)</button>
              <button type="button" class="pill-btn metric-btn" data-metric="gap_ir" aria-pressed="false">Interest Rate Gap</button>
            </div>

            <div id="overview-bar-container" class="chart-rows"></div>
          </div>
        </div>
      </section>

      <!-- TAB 2: SEGMENT DRILL-DOWN (DTI x CLTV MATRIX + VISUAL PROFILE) -->
      <section id="panel-matrix" role="tabpanel" aria-labelledby="tab-btn-matrix" hidden="until-found">
        <div class="tab-panel-inner">
          <div class="two-col-grid">
            <div class="panel-card">
              <div class="panel-header">
                <div>
                  <h2 class="panel-title">Controlled Risk Matrix: DTI &times; CLTV Rate-Spread Gap (bps)</h2>
                  <p class="panel-subtitle">
                    Click any cell to update the visual comparison on the right. Fintech pricing is higher in <strong>all 16 of 16</strong> standard conforming cells.
                  </p>
                </div>
              </div>

              <div class="table-scroll" tabindex="0">
                <table class="clean-table">
                  <caption>
                    100 &times; (Fintech median rate spread &minus; Bank median rate spread) across the 4 standard conforming DTI bands (&lt;50% underwriting cap, covering 99.6% of valid-DTI loans).
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">DTI \\ CLTV</th>
                      <th scope="col">&le;80%</th>
                      <th scope="col">80.01%–90%</th>
                      <th scope="col">90.01%–95%</th>
                      <th scope="col">&gt;95%</th>
                    </tr>
                  </thead>
                  <tbody id="matrix-tbody"></tbody>
                </table>
              </div>
            </div>

            <!-- VISUAL COMPARISON CARD FOR SELECTED SEGMENT -->
            <div class="panel-card">
              <div class="panel-header">
                <div>
                  <h2 id="drill-title" class="panel-title">Selected Segment: All U.S. • All DTI • All CLTV</h2>
                  <p class="panel-subtitle">Visual side-by-side comparison (Fintech vs. Bank)</p>
                </div>
                <span id="drill-priority" class="badge badge-ok">Priority Segment</span>
              </div>

              <div class="visual-compare-grid">
                <!-- 1. Rate Spread IQR & Median Visual -->
                <div class="vc-block">
                  <div class="vc-head">
                    <span>1. Rate Spread Median &amp; Middle 50% (IQR)</span>
                    <span id="vc-rs-badge" style="color:var(--fintech-col);">+17.2 bps higher</span>
                  </div>
                  <div class="dual-bar-row">
                    <strong style="color:var(--fintech-col);">Fintech</strong>
                    <div class="iqr-track">
                      <div id="iqr-zero-1" class="zero-line"></div>
                      <div id="iqr-box-f" class="iqr-box" style="background:var(--fintech-fill);"></div>
                      <div id="iqr-med-f" class="iqr-median-dot" style="background:var(--fintech-col);"></div>
                    </div>
                    <strong id="vc-rs-f" style="text-align:end;">0.217%</strong>
                  </div>
                  <div class="dual-bar-row">
                    <strong style="color:var(--bank-col);">Bank</strong>
                    <div class="iqr-track">
                      <div id="iqr-zero-2" class="zero-line"></div>
                      <div id="iqr-box-b" class="iqr-box" style="background:var(--bank-fill);"></div>
                      <div id="iqr-med-b" class="iqr-median-dot" style="background:var(--bank-col);"></div>
                    </div>
                    <strong id="vc-rs-b" style="text-align:end;">0.045%</strong>
                  </div>
                  <div id="vc-iqr-caption" style="font-size:0.75rem; color:var(--text-muted);">
                    Shaded band = 25th to 75th percentile; dark marker = median (vertical line = 0% APOR).
                  </div>
                </div>

                <!-- 2. Upfront Origination Charges (% of Loan) -->
                <div class="vc-block">
                  <div class="vc-head">
                    <span>2. Upfront Origination Charges (% of Loan)</span>
                    <span id="vc-oc-badge" style="color:var(--fintech-col);">+38.8 bps higher</span>
                  </div>
                  <div class="dual-bar-row">
                    <span style="color:var(--fintech-col); font-weight:700;">Fintech</span>
                    <div class="dual-track">
                      <div id="bar-oc-f" class="dual-fill" style="background:var(--fintech-fill);"></div>
                    </div>
                    <strong id="vc-oc-f" style="text-align:end;">0.956%</strong>
                  </div>
                  <div class="dual-bar-row">
                    <span style="color:var(--bank-col); font-weight:700;">Bank</span>
                    <div class="dual-track">
                      <div id="bar-oc-b" class="dual-fill" style="background:var(--bank-fill);"></div>
                    </div>
                    <strong id="vc-oc-b" style="text-align:end;">0.568%</strong>
                  </div>
                </div>

                <!-- 3. Contract Interest Rate -->
                <div class="vc-block">
                  <div class="vc-head">
                    <span>3. Contract Interest Rate</span>
                    <span id="vc-ir-badge" style="color:var(--fintech-col);">+12.5 bps higher</span>
                  </div>
                  <div class="dual-bar-row">
                    <span style="color:var(--fintech-col); font-weight:700;">Fintech</span>
                    <div class="dual-track">
                      <div id="bar-ir-f" class="dual-fill" style="background:var(--fintech-fill);"></div>
                    </div>
                    <strong id="vc-ir-f" style="text-align:end;">6.625%</strong>
                  </div>
                  <div class="dual-bar-row">
                    <span style="color:var(--bank-col); font-weight:700;">Bank</span>
                    <div class="dual-track">
                      <div id="bar-ir-b" class="dual-fill" style="background:var(--bank-fill);"></div>
                    </div>
                    <strong id="vc-ir-b" style="text-align:end;">6.500%</strong>
                  </div>
                </div>

                <!-- 4. Sample Split Bar -->
                <div class="vc-block">
                  <div class="vc-head">
                    <span>4. Sample Volume &amp; Lender Mix</span>
                    <span id="vc-total-loans" style="color:var(--text-muted); font-weight:600;">522,753 total loans</span>
                  </div>
                  <div class="sample-split-bar">
                    <div id="split-f" style="background:var(--fintech-fill); inline-size:33.6%;"></div>
                    <div id="split-b" style="background:var(--bank-fill); inline-size:66.4%;"></div>
                  </div>
                  <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--text-muted);">
                    <span id="vc-f-count"><strong style="color:var(--fintech-col);">Fintech:</strong> 175,754 (15 lenders)</span>
                    <span id="vc-b-count"><strong style="color:var(--bank-col);">Bank:</strong> 346,999 (662 lenders)</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- TAB 3: LENDERS & ROBUSTNESS -->
      <section id="panel-lenders" role="tabpanel" aria-labelledby="tab-btn-lenders" hidden="until-found">
        <div class="tab-panel-inner">
          <div class="two-col-grid">
            <div class="panel-card">
              <div class="panel-header">
                <div>
                  <h2 class="panel-title">14 Controlled Fintech Lenders vs. Bank Benchmark (0.049% Spread)</h2>
                  <p class="panel-subtitle">
                    <span id="lender-summary"></span>
                  </p>
                </div>
              </div>
              <div id="lender-bar-container" class="chart-rows"></div>
            </div>

            <div class="panel-card">
              <div class="panel-header">
                <div>
                  <h2 class="panel-title">Robustness Checks &amp; Key Caveat</h2>
                  <p class="panel-subtitle">
                    <span id="robust-summary"></span>
                  </p>
                </div>
              </div>

              <div class="table-scroll" tabindex="0">
                <table class="clean-table">
                  <caption>Sensitivity of national median pricing gaps across sample specifications</caption>
                  <thead>
                    <tr>
                      <th scope="col" style="text-align:start;">Specification</th>
                      <th scope="col">Fintech N</th>
                      <th scope="col">Comparator N</th>
                      <th scope="col">Spread Gap</th>
                      <th scope="col">Fee Gap</th>
                    </tr>
                  </thead>
                  <tbody id="robustness-tbody"></tbody>
                </table>
              </div>

              <div style="font-size:0.8125rem; color:var(--text-muted); display:grid; gap:0.4rem;">
                <p>
                  <strong>Data Source:</strong> 2025 FFIEC HMDA Snapshot (originated conventional, conforming, first-lien, principal-residence, 30-year fixed-rate home-purchase mortgages). Fintech classification follows NYU Stern / Fuster et al. (2019); Bank comparator follows Philadelphia Fed depository codes (10, 14, 20).
                </p>
                <p>
                  <strong>Key Limitation:</strong> Public HMDA omits borrower FICO scores and exact rate-lock dates. AFC's review program should combine HMDA benchmarks with member FICO and rate-sheet data to separate credit-risk pricing from fee markups.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const DATA = __DASHBOARD_JSON__;

    const DTI_ORDER = ["<30%", "30%-<36%", "36%-43%", "44%-49%"];
    const CLTV_ORDER = ["<=80%", "80.01%-90%", "90.01%-95%", ">95%"];
    const LOAN_ORDER = ["<=$200k", "$200k-$350k", "$350k-$500k", ">$500k"];
    const INC_ORDER = ["<=$75k", "$75k-$125k", "$125k-$200k", ">$200k"];

    const stateSelect = document.getElementById("sel-state");
    const dtiSelect = document.getElementById("sel-dti");
    const cltvSelect = document.getElementById("sel-cltv");
    const resetBtn = document.getElementById("btn-reset");
    const announcer = document.getElementById("live-announcer");
    const tabButtons = Array.from(document.querySelectorAll(".page-tab-btn[role='tab']"));
    const tabPanels = [
      document.getElementById("panel-overview"),
      document.getElementById("panel-matrix"),
      document.getElementById("panel-lenders"),
    ];
    const supportsUntilFound = "onbeforematch" in HTMLElement.prototype;

    let activeDim = "cltv";
    let activeMetric = "gap_rs";

    function hidePanel(panel) {
      if (supportsUntilFound) {
        panel.setAttribute("hidden", "until-found");
      } else {
        panel.hidden = true;
      }
    }

    function activateTab(targetBtn) {
      const targetId = targetBtn.getAttribute("aria-controls");
      tabButtons.forEach((btn) => {
        btn.setAttribute("aria-selected", String(btn === targetBtn));
      });
      tabPanels.forEach((panel) => {
        if (panel.id === targetId) {
          panel.removeAttribute("hidden");
        } else {
          hidePanel(panel);
        }
      });
    }

    tabButtons.forEach((btn) => {
      btn.addEventListener("click", () => activateTab(btn));
    });

    document.getElementById("tab-panels-root").addEventListener("beforematch", (e) => {
      const matchedPanel = tabPanels.find((p) => p === e.target || p.contains(e.target));
      if (matchedPanel) {
        const btn = tabButtons.find((b) => b.getAttribute("aria-controls") === matchedPanel.id);
        if (btn) activateTab(btn);
      }
    });

    if (!supportsUntilFound) {
      tabPanels.slice(1).forEach((p) => { p.hidden = true; });
    }

    function initDropdowns() {
      const allOpt = document.createElement("option");
      allOpt.value = "ALL";
      allOpt.textContent = "All U.S. (National)";
      stateSelect.appendChild(allOpt);

      DATA.slices_data.states.forEach((st) => {
        const opt = document.createElement("option");
        opt.value = st.code;
        opt.textContent = `${st.code} — ${st.name}`;
        stateSelect.appendChild(opt);
      });
    }

    function fmtBps(val) {
      if (val === null || val === undefined) return "N/A";
      const sign = val > 0 ? "+" : "";
      return `${sign}${val.toFixed(1)} bps`;
    }

    function fmtPct(val, digits = 3) {
      if (val === null || val === undefined) return "N/A";
      return `${val.toFixed(digits)}%`;
    }

    function clampPct(val, lo, hi) {
      return Math.max(0, Math.min(100, ((val - lo) / (hi - lo)) * 100));
    }

    function getSlice(st, dti, cltv) {
      return DATA.slices_data.slices[`${st}|${dti}|${cltv}`] || null;
    }

    function updateKPIsAndDrill() {
      const st = stateSelect.value;
      const dti = dtiSelect.value;
      const cltv = cltvSelect.value;
      const s = getSlice(st, dti, cltv);

      const rsGapEl = document.getElementById("kpi-rs-gap");
      const rsDetEl = document.getElementById("kpi-rs-detail");
      const irGapEl = document.getElementById("kpi-ir-gap");
      const irDetEl = document.getElementById("kpi-ir-detail");
      const ocGapEl = document.getElementById("kpi-oc-gap");
      const ocDetEl = document.getElementById("kpi-oc-detail");
      const badgeEl = document.getElementById("kpi-cov-badge");
      const loansEl = document.getElementById("kpi-cov-loans");

      const drillTitle = document.getElementById("drill-title");
      drillTitle.textContent = `Selected Segment: ${st === "ALL" ? "All U.S." : st} • DTI: ${dti} • CLTV: ${cltv}`;

      if (!s || s.nf === 0 || s.nb === 0) {
        rsGapEl.textContent = "No Data";
        rsGapEl.className = "kpi-value";
        rsDetEl.textContent = "No matching loans in both groups";
        irGapEl.textContent = "N/A";
        ocGapEl.textContent = "N/A";
        badgeEl.textContent = "Insufficient Coverage";
        badgeEl.className = "badge badge-warn";
        loansEl.textContent = "Reset filters to view broader sample";
        return;
      }

      rsGapEl.textContent = fmtBps(s.gap_rs);
      rsGapEl.className = "kpi-value " + (s.gap_rs >= 0 ? "fintech-higher" : "bank-higher");
      rsDetEl.textContent = `Fintech ${fmtPct(s.rs_f)} vs. Bank ${fmtPct(s.rs_b)}`;

      irGapEl.textContent = fmtBps(s.gap_ir);
      irDetEl.textContent = `Fintech ${fmtPct(s.ir_f)} vs. Bank ${fmtPct(s.ir_b)}`;

      ocGapEl.textContent = fmtBps(s.gap_oc);
      ocDetEl.textContent = `Fintech ${fmtPct(s.oc_f)} vs. Bank ${fmtPct(s.oc_b)} of loan`;

      loansEl.textContent = `${s.nf.toLocaleString()} Fintech (${s.lf}) vs. ${s.nb.toLocaleString()} Bank (${s.lb})`;

      const drillPriority = document.getElementById("drill-priority");
      if (!s.ok) {
        badgeEl.textContent = "Low Coverage (<100 loans)";
        badgeEl.className = "badge badge-warn";
        drillPriority.textContent = "Low N — Do Not Prioritize";
        drillPriority.className = "badge badge-warn";
      } else if (s.gap_rs >= 20) {
        badgeEl.textContent = "High Priority (+20 bps+)";
        badgeEl.className = "badge badge-ok";
        drillPriority.textContent = "Tier-1 Priority Segment";
        drillPriority.className = "badge badge-ok";
      } else if (s.gap_rs >= 5) {
        badgeEl.textContent = "Sufficient Coverage • Fintech Higher";
        badgeEl.className = "badge badge-ok";
        drillPriority.textContent = "Fintech Higher (+5 bps+)";
        drillPriority.className = "badge badge-ok";
      } else {
        badgeEl.textContent = "Fintech Not Higher";
        badgeEl.className = "badge badge-ok";
        drillPriority.textContent = "Lower Priority";
        drillPriority.className = "badge badge-ok";
      }

      // Visual 1: Rate Spread IQR & Median on [-0.6%, +1.2%] scale
      const rsLo = -0.6, rsHi = 1.2;
      const zeroPos = clampPct(0, rsLo, rsHi);
      document.getElementById("iqr-zero-1").style.insetInlineStart = `${zeroPos}%`;
      document.getElementById("iqr-zero-2").style.insetInlineStart = `${zeroPos}%`;

      const fLeft = clampPct(s.f_p25 ?? 0, rsLo, rsHi);
      const fRight = clampPct(s.f_p75 ?? 0, rsLo, rsHi);
      const fMed = clampPct(s.rs_f ?? 0, rsLo, rsHi);
      const boxF = document.getElementById("iqr-box-f");
      boxF.style.insetInlineStart = `${Math.min(fLeft, fRight)}%`;
      boxF.style.inlineSize = `${Math.max(1.5, Math.abs(fRight - fLeft))}%`;
      document.getElementById("iqr-med-f").style.insetInlineStart = `${fMed}%`;

      const bLeft = clampPct(s.b_p25 ?? 0, rsLo, rsHi);
      const bRight = clampPct(s.b_p75 ?? 0, rsLo, rsHi);
      const bMed = clampPct(s.rs_b ?? 0, rsLo, rsHi);
      const boxB = document.getElementById("iqr-box-b");
      boxB.style.insetInlineStart = `${Math.min(bLeft, bRight)}%`;
      boxB.style.inlineSize = `${Math.max(1.5, Math.abs(bRight - bLeft))}%`;
      document.getElementById("iqr-med-b").style.insetInlineStart = `${bMed}%`;

      document.getElementById("vc-rs-f").textContent = fmtPct(s.rs_f);
      document.getElementById("vc-rs-b").textContent = fmtPct(s.rs_b);
      document.getElementById("vc-rs-badge").textContent = `${fmtBps(s.gap_rs)} (${s.gap_rs >= 0 ? "Fintech higher" : "Bank higher"})`;
      document.getElementById("vc-iqr-caption").textContent =
        `Middle 50% range (25th–75th pct): Fintech [${fmtPct(s.f_p25, 2)} to ${fmtPct(s.f_p75, 2)}] vs. Bank [${fmtPct(s.b_p25, 2)} to ${fmtPct(s.b_p75, 2)}] • Grey line = 0% benchmark`;

      // Visual 2: Origination Charges (% of Loan, scale 0% to 2.0%)
      document.getElementById("bar-oc-f").style.inlineSize = `${clampPct(s.oc_f ?? 0, 0, 2.0)}%`;
      document.getElementById("bar-oc-b").style.inlineSize = `${clampPct(s.oc_b ?? 0, 0, 2.0)}%`;
      document.getElementById("vc-oc-f").textContent = fmtPct(s.oc_f);
      document.getElementById("vc-oc-b").textContent = fmtPct(s.oc_b);
      document.getElementById("vc-oc-badge").textContent = fmtBps(s.gap_oc);

      // Visual 3: Contract Interest Rate (scale 5.0% to 8.0%)
      document.getElementById("bar-ir-f").style.inlineSize = `${clampPct(s.ir_f ?? 0, 5.0, 8.0)}%`;
      document.getElementById("bar-ir-b").style.inlineSize = `${clampPct(s.ir_b ?? 0, 5.0, 8.0)}%`;
      document.getElementById("vc-ir-f").textContent = fmtPct(s.ir_f);
      document.getElementById("vc-ir-b").textContent = fmtPct(s.ir_b);
      document.getElementById("vc-ir-badge").textContent = fmtBps(s.gap_ir);

      // Visual 4: Sample Volume Split
      const tot = s.nf + s.nb;
      const fShare = tot > 0 ? (s.nf / tot) * 100 : 50;
      document.getElementById("split-f").style.inlineSize = `${fShare.toFixed(1)}%`;
      document.getElementById("split-b").style.inlineSize = `${(100 - fShare).toFixed(1)}%`;
      document.getElementById("vc-total-loans").textContent = `${tot.toLocaleString()} total loans`;
      document.getElementById("vc-f-count").innerHTML =
        `<strong style="color:var(--fintech-col);">Fintech:</strong> ${s.nf.toLocaleString()} (${s.lf} lenders)`;
      document.getElementById("vc-b-count").innerHTML =
        `<strong style="color:var(--bank-col);">Bank:</strong> ${s.nb.toLocaleString()} (${s.lb} lenders)`;

      announcer.textContent = `Updated slice: Rate spread gap ${fmtBps(s.gap_rs)}.`;
    }

    function buildBarRows(container, items, minFloor, maxCeil, onClickRow) {
      container.innerHTML = "";
      const validVals = items.map((d) => d.val).filter((v) => v !== null && v !== undefined);
      const minVal = Math.min(0, ...validVals, minFloor);
      const maxVal = Math.max(maxCeil, ...validVals);
      const span = (maxVal - minVal) || 1;
      const zeroPct = ((0 - minVal) / span) * 100;

      items.forEach((item) => {
        const row = document.createElement("div");
        row.className = "bar-row" + (onClickRow ? " interactive-row" : "") + (item.active ? " active-slice" : "");
        if (onClickRow) {
          row.addEventListener("click", () => onClickRow(item));
        }

        const lbl = document.createElement("div");
        lbl.className = "bar-label";
        lbl.textContent = item.label;
        const sub = document.createElement("span");
        sub.className = "bar-label-sub";
        sub.textContent = item.sub;
        lbl.appendChild(sub);

        const track = document.createElement("div");
        track.className = "bar-track";
        const zero = document.createElement("div");
        zero.className = "zero-line";
        zero.style.insetInlineStart = `${zeroPct}%`;
        track.appendChild(zero);

        if (item.val !== null && item.val !== undefined) {
          const fill = document.createElement("div");
          fill.className = "bar-fill";
          const valPct = ((item.val - minVal) / span) * 100;
          const left = Math.min(zeroPct, valPct);
          const width = Math.max(0.8, Math.abs(valPct - zeroPct));
          fill.style.insetInlineStart = `${left}%`;
          fill.style.inlineSize = `${width}%`;
          fill.style.backgroundColor = !item.ok
            ? "#94a3b8"
            : item.val >= 0
              ? "#d97706"
              : "#2563eb";
          track.appendChild(fill);
        }

        const valEl = document.createElement("div");
        valEl.className = "bar-val";
        valEl.style.color = !item.ok
          ? "#64748b"
          : (item.val || 0) >= 0
            ? "#b45309"
            : "#1d4ed8";
        valEl.textContent = item.val !== null && item.val !== undefined ? fmtBps(item.val) : "N/A";

        row.appendChild(lbl);
        row.appendChild(track);
        row.appendChild(valEl);
        container.appendChild(row);
      });
    }

    function renderOverviewChart() {
      const st = stateSelect.value;
      const order = activeDim === "cltv"
        ? CLTV_ORDER
        : activeDim === "dti"
          ? DTI_ORDER
          : activeDim === "loan"
            ? LOAN_ORDER
            : INC_ORDER;

      const dimTitle = activeDim === "cltv"
        ? "by Combined LTV (Down Payment)"
        : activeDim === "dti"
          ? "by Debt-to-Income (DTI)"
          : activeDim === "loan"
            ? "by Loan Amount"
            : "by Borrower Income";

      const metricTitle = activeMetric === "gap_rs"
        ? "Median Rate-Spread Gap"
        : activeMetric === "gap_oc"
          ? "Median Origination-Fee Gap"
          : "Median Interest-Rate Gap";

      document.getElementById("overview-chart-title").textContent = `${metricTitle} ${dimTitle} (bps)`;

      const items = order.map((bin) => {
        const b = DATA.slices_data.bars[`${st}|${activeDim}|${bin}`];
        const val = b ? b[activeMetric] : null;
        const isSelected = (activeDim === "cltv" && cltvSelect.value === bin) ||
                           (activeDim === "dti" && dtiSelect.value === bin);
        return {
          label: bin,
          bin: bin,
          sub: b ? `Fintech: ${b.nf.toLocaleString()} • Bank: ${b.nb.toLocaleString()}${b.ok ? "" : " (Low N)"}` : "No data",
          val: val,
          ok: b ? b.ok : false,
          active: isSelected,
        };
      });

      const canFilter = activeDim === "cltv" || activeDim === "dti";
      buildBarRows(
        document.getElementById("overview-bar-container"),
        items,
        -5,
        35,
        canFilter
          ? (item) => {
              if (activeDim === "cltv") {
                cltvSelect.value = cltvSelect.value === item.bin ? "ALL" : item.bin;
              } else {
                dtiSelect.value = dtiSelect.value === item.bin ? "ALL" : item.bin;
              }
              refreshAll();
            }
          : null
      );
    }

    function heatColor(gap, ok) {
      if (!ok || gap === null || gap === undefined) return "#f1f5f9";
      if (gap < 0) return "#dbeafe";
      if (gap >= 25) return "#fde68a";
      if (gap >= 15) return "#fef3c7";
      return "#fffbeb";
    }

    function renderMatrix() {
      const st = stateSelect.value;
      const selDti = dtiSelect.value;
      const selCltv = cltvSelect.value;
      const tbody = document.getElementById("matrix-tbody");
      tbody.innerHTML = "";

      DTI_ORDER.forEach((dti) => {
        const tr = document.createElement("tr");
        const th = document.createElement("th");
        th.scope = "row";
        th.textContent = dti;
        tr.appendChild(th);

        CLTV_ORDER.forEach((cltv) => {
          const td = document.createElement("td");
          const s = getSlice(st, dti, cltv);
          const isSelected = selDti === dti && selCltv === cltv;
          td.className = "matrix-cell" + (isSelected ? " selected-cell" : "");

          if (!s || s.nf === 0 || s.nb === 0) {
            td.style.backgroundColor = "#f8fafc";
            td.innerHTML = `<span class="cell-gap" style="color:#94a3b8;">N/A</span><span class="cell-meta">0 loans</span>`;
          } else {
            td.style.backgroundColor = heatColor(s.gap_rs, s.ok);
            const gapColor = !s.ok ? "#64748b" : s.gap_rs >= 0 ? "#92400e" : "#1e40af";
            const tag = s.ok ? `F:${s.nf.toLocaleString()} / B:${s.nb.toLocaleString()}` : `Low N (F:${s.nf})`;
            td.innerHTML = `<span class="cell-gap" style="color:${gapColor};">${fmtBps(s.gap_rs)}</span><span class="cell-meta">${tag}</span>`;
          }

          td.addEventListener("click", () => {
            if (dtiSelect.value === dti && cltvSelect.value === cltv) {
              dtiSelect.value = "ALL";
              cltvSelect.value = "ALL";
            } else {
              dtiSelect.value = dti;
              cltvSelect.value = cltv;
            }
            refreshAll();
          });
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }

    function renderLendersAndRobustness() {
      const lenderItems = DATA.fintech_lenders.map((r) => ({
        label: r.lender_name,
        sub: `${r.total_loans.toLocaleString()} loans (${r.share_of_fintech_loans_pct.toFixed(1)}%) • Med spread: ${fmtPct(r.median_rate_spread)}`,
        val: r.gap_vs_bank_median_bps,
        ok: r.total_loans >= 100,
        active: false,
      }));
      buildBarRows(document.getElementById("lender-bar-container"), lenderItems, -30, 50, null);

      const ls = DATA.lender_stats;
      document.getElementById("lender-summary").innerHTML =
        `<strong>${ls.above_bank} of ${ls.total}</strong> Fintech lenders in the controlled sample have a median rate spread above the bank median ` +
        `(<strong>${ls.above_5bps} of ${ls.total}</strong> by 5 bps or more); equal-weighted lender-median gap is <strong>${fmtBps(ls.equal_weighted_gap_bps)}</strong>.`;
      const gaps = DATA.robustness_checks.map((r) => r.rate_spread_gap_bps).filter((v) => v !== null);
      const base = DATA.headline_metrics.national_controlled_sample || {};
      const ci = base.lender_cluster_ci95_bps || DATA.headline_metrics.baseline_lender_cluster_ci95_bps;
      document.getElementById("robust-summary").innerHTML =
        `Gap ranges from <strong>${fmtBps(Math.min(...gaps))} to ${fmtBps(Math.max(...gaps))}</strong> across specifications` +
        (ci && ci[0] !== null ? `; baseline lender-clustered 95% CI <strong>${fmtBps(ci[0])} to ${fmtBps(ci[1])}</strong>.` : '.');

      const robTbody = document.getElementById("robustness-tbody");
      robTbody.innerHTML = "";
      DATA.robustness_checks.forEach((r) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td style="text-align:start; font-weight:600;">${r.slice}</td>
          <td>${r.fintech_loans_rs.toLocaleString()}</td>
          <td>${r.bank_loans_rs.toLocaleString()}</td>
          <td style="font-weight:800; color:#b45309;">${fmtBps(r.rate_spread_gap_bps)}</td>
          <td style="font-weight:700;">${fmtBps(r.orig_pct_gap_bps)}</td>
        `;
        robTbody.appendChild(tr);
      });
    }

    function refreshAll() {
      updateKPIsAndDrill();
      renderOverviewChart();
      renderMatrix();
    }

    [stateSelect, dtiSelect, cltvSelect].forEach((el) => {
      el.addEventListener("change", refreshAll);
    });

    resetBtn.addEventListener("click", () => {
      stateSelect.value = "ALL";
      dtiSelect.value = "ALL";
      cltvSelect.value = "ALL";
      refreshAll();
    });

    document.querySelectorAll(".pill-btn[data-dim]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeDim = btn.getAttribute("data-dim");
        document.querySelectorAll(".pill-btn[data-dim]").forEach((b) => {
          b.setAttribute("aria-pressed", String(b === btn));
        });
        renderOverviewChart();
      });
    });

    document.querySelectorAll(".metric-btn[data-metric]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeMetric = btn.getAttribute("data-metric");
        document.querySelectorAll(".metric-btn[data-metric]").forEach((b) => {
          b.setAttribute("aria-pressed", String(b === btn));
        });
        renderOverviewChart();
      });
    });

    initDropdowns();
    renderLendersAndRobustness();
    refreshAll();
  </script>
</body>
</html>
"""


def main():
    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / 'data' / '2025'
    clean_csv = data_dir / 'mortgages_2025_clean.csv'
    pricing_json = data_dir / 'analysis' / 'pricing_summary.json'

    print('Computing interactive slice medians from loan records ...')
    slices_data = compute_slices(clean_csv)
    summary = json.loads(pricing_json.read_text(encoding='utf-8'))

    payload = {
        'generated_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'headline_metrics': summary['headline_metrics'],
        'robustness_checks': slices_data['robustness_checks'],
        'fintech_lenders': slices_data['fintech_lenders'],
        'lender_stats': slices_data['lender_stats'],
        'slices_data': {
            'states': slices_data['states'],
            'slices': slices_data['slices'],
            'bars': slices_data['bars'],
        },
    }

    slices_path = data_dir / 'analysis' / 'dashboard_slices.json'
    slices_path.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')

    html_content = HTML_TEMPLATE.replace('__DASHBOARD_JSON__', json.dumps(payload, separators=(',', ':')))
    submit_dir = base_dir.parent / 'Submit'
    submit_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = submit_dir / 'Project Audible Dashboard.html'
    dashboard_path.write_text(html_content, encoding='utf-8')
    print(f'Wrote {dashboard_path} ({dashboard_path.stat().st_size / 1024:.1f} KiB)')


if __name__ == '__main__':
    main()
