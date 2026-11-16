#!/usr/bin/env python3
"""Build the capstone HTML dashboard for Project Audible: one data model, three
audience pages (Executive = decision, Analyst = evidence & failure modes,
Regulator = traceability).

Reads:
  data/2025/mortgages_2025_clean.csv            (skipped with --from-json)
  data/2025/analysis/pricing_summary.json
  data/2025/manifest.json, sample_summary.json,
  nyu_classification_summary.json, data_quality/cleaning_summary.json  (provenance)
  data/2025/source_check.json                   (optional, written by check_source.py)

Writes:
  ../Submit/Project Audible Dashboard.html
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
  <title>Project Audible Capstone — AFC Mortgage Pricing (Executive, Analyst, Regulator)</title>
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

    /* ---- Capstone additions: audience pages ---- */
    .meta-line {
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-block-start: -0.5rem;
    }
    .page-kicker {
      font-size: 0.75rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-muted);
    }
    .chain {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 1.5rem;
    }
    .chain > .kpi-card { position: relative; }
    .chain > .kpi-card + .kpi-card::before {
      content: "\\2192";
      position: absolute;
      inset-inline-start: -1.2rem;
      inset-block-start: 50%;
      transform: translateY(-50%);
      color: var(--text-muted);
      font-weight: 700;
    }
    @media (max-width: 760px) {
      .chain { grid-template-columns: 1fr; }
      .chain > .kpi-card + .kpi-card::before { display: none; }
    }
    .dot-key { white-space: nowrap; margin-inline: 0.35rem; }
    .dot {
      display: inline-block;
      inline-size: 0.7rem;
      block-size: 0.7rem;
      border-radius: 999px;
      margin-inline-end: 0.25rem;
      vertical-align: -0.05rem;
    }
    .dot-bank { background: var(--bank-fill); }
    .dot-nb { background: #0f766e; }
    .db-row {
      display: grid;
      grid-template-columns: minmax(9rem, 15rem) 1fr 6.5rem;
      align-items: safe center;
      gap: 0.75rem;
      font-size: 0.875rem;
      padding-block: 0.35rem;
      padding-inline: 0.45rem;
      border-radius: 0.4rem;
    }
    .db-row.db-prio { background: #fffbeb; }
    .db-track {
      position: relative;
      block-size: 2.9rem;
      border-block-end: 1px dashed var(--border-col);
    }
    .db-track .zero-line { inset-block: 0; }
    .db-link {
      position: absolute;
      inset-block-start: calc(50% - 1px);
      block-size: 2px;
      background: #cbd5e1;
    }
    .db-track .dot {
      position: absolute;
      inset-block-start: 50%;
      transform: translate(-50%, -50%);
      margin: 0;
      inline-size: 0.8rem;
      block-size: 0.8rem;
      z-index: 3;
    }
    .db-lab {
      position: absolute;
      transform: translateX(-50%);
      font-size: 0.6875rem;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .db-lab-bank { inset-block-start: 0; color: var(--bank-col); }
    .db-lab-nb { inset-block-end: 0; color: #0f766e; }
    .db-fee { font-size: 0.875rem; color: var(--text-muted); }
    .db-fee.fee-hot { color: var(--fintech-col); }
    .start-tag {
      font-size: 0.6875rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--fintech-col);
      margin-inline-start: 0.25rem;
    }
    .db-axis {
      display: grid;
      grid-template-columns: minmax(9rem, 15rem) 1fr 6.5rem;
      gap: 0.75rem;
      padding-inline: 0.45rem;
      margin-block-start: -0.5rem;
    }
    .db-ticks { position: relative; block-size: 1rem; }
    .db-ticks span {
      position: absolute;
      transform: translateX(-50%);
      font-size: 0.6875rem;
      color: var(--text-muted);
      font-variant-numeric: tabular-nums;
    }
    .db-unit { font-size: 0.6875rem; color: var(--text-muted); }
    .steps {
      margin: 0;
      padding-inline-start: 1.25rem;
      display: grid;
      gap: 0.5rem;
      font-size: 0.875rem;
    }
    .footnote { font-size: 0.75rem; color: var(--text-muted); }
    .badge-neutral { background: var(--bg-subtle); color: var(--text-muted); }
    .peer-row td, .peer-row th { background: #f0fdfa; }
    .reg-table td, .reg-table th { font-size: 0.75rem; vertical-align: top; }
    .reg-table code, .plain-list code, .panel-subtitle code {
      font-size: 0.6875rem;
      background: var(--bg-subtle);
      padding: 0.05rem 0.25rem;
      border-radius: 0.2rem;
      overflow-wrap: anywhere;
    }
    .plain-list {
      margin: 0;
      padding-inline-start: 1.1rem;
      display: grid;
      gap: 0.5rem;
      font-size: 0.8125rem;
    }
  </style>
</head>
<body>
  <div id="live-announcer" class="sr-only" aria-live="polite" aria-atomic="true"></div>

  <div class="page-shell">
    <!-- TOP BAR: one data model, three audience pages -->
    <div class="top-bar">
      <div class="eyebrow">
        FINTECH 590 Capstone &bull; Project Audible &bull; American Fintech Council (AFC)
      </div>
      <nav aria-label="Audience pages">
        <div class="minimal-tabs" role="tablist">
          <button type="button" class="page-tab-btn" role="tab" id="tab-btn-exec" aria-controls="panel-exec" aria-selected="true">
            Executive &middot; Decision
          </button>
          <button type="button" class="page-tab-btn" role="tab" id="tab-btn-analyst" aria-controls="panel-analyst" aria-selected="false">
            Analyst &middot; Evidence &amp; Risk
          </button>
          <button type="button" class="page-tab-btn" role="tab" id="tab-btn-reg" aria-controls="panel-reg" aria-selected="false">
            Regulator &middot; Traceability
          </button>
        </div>
      </nav>
    </div>
    <p id="data-asof" class="meta-line"></p>

    <main id="tab-panels-root" style="display:grid; gap:1.125rem;">

      <!-- ================= PAGE 1: EXECUTIVE ================= -->
      <section id="panel-exec" role="tabpanel" aria-labelledby="tab-btn-exec">
        <div class="tab-panel-inner">
          <header class="header-card">
            <span class="page-kicker">Recommendation</span>
            <h1 id="exec-title" class="headline-title balance-heading"></h1>
            <ul class="key-points" aria-label="Key takeaway points">
              <li><span class="kp-tag">What:</span> <span id="kp-what"></span></li>
              <li><span class="kp-tag">So What:</span> <span id="kp-sowhat"></span></li>
              <li><span class="kp-tag">Now What:</span> <span id="kp-nowwhat"></span></li>
            </ul>
          </header>

          <section class="chain" aria-label="From the headline gap to the gap that remains">
            <div class="kpi-card">
              <span class="kpi-label">1 &middot; What the public sees</span>
              <div id="ex-k1" class="kpi-value"></div>
              <p id="ex-k1-sub" class="kpi-sub"></p>
            </div>
            <div class="kpi-card">
              <span class="kpi-label">2 &middot; Against the fair benchmark</span>
              <div id="ex-k2" class="kpi-value"></div>
              <p id="ex-k2-sub" class="kpi-sub"></p>
            </div>
            <div class="kpi-card primary-kpi">
              <span class="kpi-label">3 &middot; What remains to explain</span>
              <div id="ex-k3" class="kpi-value fintech-higher"></div>
              <p id="ex-k3-sub" class="kpi-sub"></p>
            </div>
          </section>

          <div class="panel-card">
            <div class="panel-header">
              <div>
                <h2 class="panel-title">Fintech borrowers pay more than at banks, but about the same as at other nonbanks</h2>
                <p class="panel-subtitle">
                  Median rate-spread gap (fintech minus comparator, bps) by borrower group.
                  <span class="dot-key"><i class="dot dot-bank"></i>vs. banks</span>
                  <span class="dot-key"><i class="dot dot-nb"></i>vs. other nonbanks</span>
                  Right column: origination-fee gap vs. other nonbanks.
                </p>
              </div>
            </div>
            <div id="exec-dumbbell" class="chart-rows" role="img" aria-label="Rate-spread gap versus banks and versus nonbanks by borrower group"></div>
            <div id="exec-axis" class="db-axis" aria-hidden="true"></div>
          </div>

          <div class="panel-card">
            <h2 class="panel-title">Proposed next steps for AFC</h2>
            <ol class="steps">
              <li><strong>Q1 2027 &mdash; Invite and benchmark.</strong> Invite members to join; publish the HMDA benchmarks against banks <em>and</em> nonbank peers.</li>
              <li><strong>Members explain their gap.</strong> Start with origination fees in <span id="ex-step2-focus"></span>, using data public HMDA omits: credit score, LLPAs, rate-lock date, discount points, lender credits.</li>
              <li><strong>AFC reports in aggregate.</strong> Show how much of the gap credit risk and the nonbank model explain; members act only on the unexplained part. If little is left, AFC publishes that as evidence.</li>
            </ol>
            <p class="footnote">The review is diagnostic: a price gap alone does not justify telling any member to change prices. Public HMDA has no credit scores; it describes 2025 pricing, not current offers.</p>
          </div>
        </div>
      </section>

      <!-- ================= PAGE 2: ANALYST / RISK ================= -->
      <section id="panel-analyst" role="tabpanel" aria-labelledby="tab-btn-analyst" hidden="until-found">
        <div class="tab-panel-inner">
          <header class="header-card">
            <span class="page-kicker">Evidence &amp; failure modes</span>
            <h1 id="an-title" class="headline-title balance-heading"></h1>
            <p id="an-sub" class="panel-subtitle"></p>
          </header>

          <search aria-label="Segment filters">
            <div class="slicer-card">
              <div class="slicer-field">
                <label for="sel-state">Property state</label>
                <select id="sel-state"></select>
              </div>
              <div class="slicer-field">
                <label for="sel-dti">Debt-to-income (DTI &lt;50%)</label>
                <select id="sel-dti">
                  <option value="ALL">All DTI groups</option>
                  <option value="<30%">&lt;30%</option>
                  <option value="30%-<36%">30%&ndash;&lt;36%</option>
                  <option value="36%-43%">36%&ndash;43%</option>
                  <option value="44%-49%">44%&ndash;49%</option>
                </select>
              </div>
              <div class="slicer-field">
                <label for="sel-cltv">Combined LTV (down payment)</label>
                <select id="sel-cltv">
                  <option value="ALL">All CLTV groups</option>
                  <option value="<=80%">&le;80% (20%+ down)</option>
                  <option value="80.01%-90%">80.01%&ndash;90% (10&ndash;20% down)</option>
                  <option value="90.01%-95%">90.01%&ndash;95% (5&ndash;10% down)</option>
                  <option value=">95%">&gt;95% (&lt;5% down)</option>
                </select>
              </div>
              <button type="button" id="btn-reset" class="btn-reset">Reset</button>
            </div>
          </search>

          <section aria-label="Pricing gap for the selected slice" class="kpi-grid">
            <div class="kpi-card">
              <span class="kpi-label">Rate-spread gap vs. banks</span>
              <div id="kpi-rs-gap" class="kpi-value"></div>
              <p id="kpi-rs-detail" class="kpi-sub"></p>
            </div>
            <div class="kpi-card">
              <span class="kpi-label">Origination-fee gap vs. banks</span>
              <div id="kpi-oc-gap" class="kpi-value"></div>
              <p id="kpi-oc-detail" class="kpi-sub"></p>
            </div>
            <div class="kpi-card">
              <span class="kpi-label">Sample &amp; materiality</span>
              <div id="kpi-cov-badge" class="badge badge-ok"></div>
              <p id="kpi-cov-loans" class="kpi-sub"></p>
            </div>
          </section>

          <div class="two-col-grid">
            <div class="panel-card">
              <div>
                <h2 class="panel-title">Fintech prices higher in <span id="matrix-count"></span> DTI &times; CLTV risk cells</h2>
                <p class="panel-subtitle">Rate-spread gap vs. banks (bps). Click a cell to filter; grey = fewer than 100 loans per side.</p>
              </div>
              <div class="table-scroll" tabindex="0">
                <table class="clean-table">
                  <caption>100 &times; (fintech median rate spread &minus; bank median rate spread), conforming DTI &lt;50%.</caption>
                  <thead>
                    <tr>
                      <th scope="col">DTI \\ CLTV</th>
                      <th scope="col">&le;80%</th>
                      <th scope="col">80.01%&ndash;90%</th>
                      <th scope="col">90.01%&ndash;95%</th>
                      <th scope="col">&gt;95%</th>
                    </tr>
                  </thead>
                  <tbody id="matrix-tbody"></tbody>
                </table>
              </div>
            </div>

            <div class="panel-card">
              <div>
                <h2 id="drill-title" class="panel-title"></h2>
                <p class="panel-subtitle">Medians are not the whole story: the shaded band is the middle 50% of loans.</p>
              </div>
              <div class="visual-compare-grid">
                <div class="vc-block">
                  <div class="vc-head">
                    <span>Rate spread (APR &minus; APOR): median &amp; middle 50%</span>
                    <span id="vc-rs-badge"></span>
                  </div>
                  <div class="dual-bar-row">
                    <strong style="color:var(--fintech-col);">Fintech</strong>
                    <div class="iqr-track">
                      <div id="iqr-zero-1" class="zero-line"></div>
                      <div id="iqr-box-f" class="iqr-box" style="background:var(--fintech-fill);"></div>
                      <div id="iqr-med-f" class="iqr-median-dot" style="background:var(--fintech-col);"></div>
                    </div>
                    <strong id="vc-rs-f" style="text-align:end;"></strong>
                  </div>
                  <div class="dual-bar-row">
                    <strong style="color:var(--bank-col);">Bank</strong>
                    <div class="iqr-track">
                      <div id="iqr-zero-2" class="zero-line"></div>
                      <div id="iqr-box-b" class="iqr-box" style="background:var(--bank-fill);"></div>
                      <div id="iqr-med-b" class="iqr-median-dot" style="background:var(--bank-col);"></div>
                    </div>
                    <strong id="vc-rs-b" style="text-align:end;"></strong>
                  </div>
                  <div id="vc-iqr-caption" class="footnote"></div>
                </div>
                <div class="vc-block">
                  <div class="vc-head">
                    <span>Origination charges (% of loan)</span>
                    <span id="vc-oc-badge"></span>
                  </div>
                  <div class="dual-bar-row">
                    <span style="color:var(--fintech-col); font-weight:700;">Fintech</span>
                    <div class="dual-track"><div id="bar-oc-f" class="dual-fill" style="background:var(--fintech-fill);"></div></div>
                    <strong id="vc-oc-f" style="text-align:end;"></strong>
                  </div>
                  <div class="dual-bar-row">
                    <span style="color:var(--bank-col); font-weight:700;">Bank</span>
                    <div class="dual-track"><div id="bar-oc-b" class="dual-fill" style="background:var(--bank-fill);"></div></div>
                    <strong id="vc-oc-b" style="text-align:end;"></strong>
                  </div>
                  <div class="footnote">Bars start at 0% of loan amount (scale 0&ndash;2%).</div>
                </div>
                <div class="vc-block">
                  <div class="vc-head">
                    <span>Contract interest rate (median)</span>
                    <span id="vc-ir-badge"></span>
                  </div>
                  <p id="vc-ir-text" class="kpi-sub"></p>
                </div>
              </div>
            </div>
          </div>

          <div class="panel-card">
            <div class="panel-header">
              <div>
                <h2 id="overview-chart-title" class="panel-title"></h2>
                <p class="panel-subtitle">Fintech minus bank median (bps); 0 = parity. Bars for CLTV and DTI are clickable filters.</p>
              </div>
              <div class="pill-group" role="group" aria-label="Select borrower dimension">
                <button type="button" class="pill-btn" data-dim="cltv" aria-pressed="true">CLTV</button>
                <button type="button" class="pill-btn" data-dim="dti" aria-pressed="false">DTI</button>
                <button type="button" class="pill-btn" data-dim="loan" aria-pressed="false">Loan size</button>
                <button type="button" class="pill-btn" data-dim="income" aria-pressed="false">Income</button>
              </div>
            </div>
            <div class="pill-group" role="group" aria-label="Select pricing measure">
              <button type="button" class="pill-btn metric-btn" data-metric="gap_rs" aria-pressed="true">Rate spread</button>
              <button type="button" class="pill-btn metric-btn" data-metric="gap_oc" aria-pressed="false">Origination fee</button>
            </div>
            <div id="overview-bar-container" class="chart-rows"></div>
          </div>

          <div class="two-col-grid">
            <div class="panel-card">
              <div>
                <h2 id="lender-title" class="panel-title"></h2>
                <p class="panel-subtitle"><span id="lender-summary"></span></p>
              </div>
              <div id="lender-bar-container" class="chart-rows"></div>
            </div>

            <div class="panel-card">
              <div>
                <h2 class="panel-title">The gap vs. banks barely moves across sample definitions</h2>
                <p class="panel-subtitle"><span id="robust-summary"></span></p>
              </div>
              <div class="table-scroll" tabindex="0">
                <table class="clean-table">
                  <caption>National median gaps (bps) under alternative sample definitions</caption>
                  <thead>
                    <tr>
                      <th scope="col" style="text-align:start;">Specification</th>
                      <th scope="col">Fintech N</th>
                      <th scope="col">Comparator N</th>
                      <th scope="col">Spread gap</th>
                      <th scope="col">Fee gap</th>
                    </tr>
                  </thead>
                  <tbody id="robustness-tbody"></tbody>
                </table>
              </div>
            </div>
          </div>

          <div class="panel-card">
            <div>
              <h2 class="panel-title">What would change our recommendation</h2>
              <p class="panel-subtitle">Decision rule from the initial pitch, checked against today&rsquo;s numbers.</p>
            </div>
            <div class="table-scroll" tabindex="0">
              <table class="clean-table cond-table">
                <thead>
                  <tr>
                    <th scope="col" style="text-align:start;">If this happened&hellip;</th>
                    <th scope="col" style="text-align:start;">&hellip;we would</th>
                    <th scope="col" style="text-align:start;">Today</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody id="cond-tbody"></tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <!-- ================= PAGE 3: REGULATOR / COMPLIANCE ================= -->
      <section id="panel-reg" role="tabpanel" aria-labelledby="tab-btn-reg" hidden="until-found">
        <div class="tab-panel-inner">
          <header class="header-card">
            <span class="page-kicker">Accountability &amp; traceability</span>
            <h1 class="headline-title balance-heading">Every number on this dashboard traces to a public HMDA field and a logged pipeline step</h1>
            <p class="panel-subtitle">Method: descriptive medians and interquartile ranges on public data. No fitted or predictive model, no imputation, no borrower-level data beyond public HMDA.</p>
          </header>

          <div class="panel-card">
            <div>
              <h2 class="panel-title">Fact sheet: the numbers used on every page, in the memo and on slide 1</h2>
              <p class="panel-subtitle">Values are read from the pipeline outputs at build time; none are typed by hand.</p>
            </div>
            <div class="table-scroll" tabindex="0">
              <table class="clean-table reg-table">
                <thead>
                  <tr>
                    <th scope="col">ID</th>
                    <th scope="col" style="text-align:start;">Claim</th>
                    <th scope="col">Value</th>
                    <th scope="col" style="text-align:start;">Definition &amp; HMDA fields</th>
                    <th scope="col" style="text-align:start;">Computed in</th>
                  </tr>
                </thead>
                <tbody id="facts-tbody"></tbody>
              </table>
            </div>
          </div>

          <div class="two-col-grid">
            <div class="panel-card">
              <div>
                <h2 class="panel-title">Data lineage: 13.5 million records to the 511,199-loan baseline</h2>
                <p class="panel-subtitle">Each step is a script in <code>project_audible_data/</code>; counts are read from its logged output.</p>
              </div>
              <div class="table-scroll" tabindex="0">
                <table class="clean-table reg-table">
                  <thead>
                    <tr>
                      <th scope="col" style="text-align:start;">Step &amp; rule</th>
                      <th scope="col" style="text-align:start;">Script</th>
                      <th scope="col">Loans</th>
                    </tr>
                  </thead>
                  <tbody id="lineage-tbody"></tbody>
                </table>
              </div>
            </div>

            <div class="panel-card">
              <div>
                <h2 class="panel-title">Parameters fixed before the analysis</h2>
                <p class="panel-subtitle">Set in <code>analyze_pricing.py</code>; the same thresholds drive grey-outs and status labels on every page.</p>
              </div>
              <div class="table-scroll" tabindex="0">
                <table class="clean-table reg-table">
                  <tbody id="params-tbody"></tbody>
                </table>
              </div>
            </div>
          </div>

          <div class="panel-card">
            <div>
              <h2 class="panel-title">Sources, versions and checksums</h2>
              <p id="source-check" class="panel-subtitle"></p>
            </div>
            <div class="table-scroll" tabindex="0">
              <table class="clean-table reg-table">
                <thead>
                  <tr>
                    <th scope="col" style="text-align:start;">Source</th>
                    <th scope="col" style="text-align:start;">Version / published</th>
                    <th scope="col" style="text-align:start;">Retrieved</th>
                    <th scope="col" style="text-align:start;">SHA-256 (first 12)</th>
                  </tr>
                </thead>
                <tbody id="sources-tbody"></tbody>
              </table>
            </div>
          </div>

          <div class="two-col-grid">
            <div class="panel-card">
              <h2 class="panel-title">What this analysis does not claim</h2>
              <ul class="plain-list">
                <li><strong>No fair-lending conclusion.</strong> No analysis by race, ethnicity, sex or age was run; the gaps by income and down payment are pricing differences, not evidence of disparate treatment or impact.</li>
                <li><strong>No intent or markup finding.</strong> Public HMDA omits credit scores, LLPAs and exact rate-lock dates, so risk-based pricing is not fully controlled.</li>
                <li><strong>Not current offers.</strong> HMDA 2025 records originated loans; it does not show today&rsquo;s rate sheets.</li>
                <li><strong>&ldquo;Fintech&rdquo; is a defined list.</strong> NYU Stern / Fuster et al. (2019) fully online lenders, last updated 2017 (<span id="nyu-match"></span> matched in 2025). Unlisted online nonbanks sit in the nonbank comparator, which pulls that gap toward zero.</li>
              </ul>
            </div>
            <div class="panel-card">
              <h2 class="panel-title">How to reproduce and audit</h2>
              <ul class="plain-list">
                <li><code>./run_demo.sh</code> &mdash; runs the unit tests, checks the HMDA source, rebuilds this dashboard from saved results (no manual steps).</li>
                <li><code>./run_demo.sh --full</code> &mdash; reruns all five pipeline steps from the FFIEC download.</li>
                <li>Missing values (NA, Exempt) are never imputed; $0 fees are kept as valid.</li>
                <li>AI-assisted code and text are documented, with corrections, in <em>Project Audible LLM Validation Log</em>.</li>
              </ul>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const DATA = __DASHBOARD_JSON__;
    const PROV = __PROVENANCE_JSON__;

    const DTI_ORDER = ["<30%", "30%-<36%", "36%-43%", "44%-49%"];
    const CLTV_ORDER = ["<=80%", "80.01%-90%", "90.01%-95%", ">95%"];
    const LOAN_ORDER = ["<=$200k", "$200k-$350k", "$350k-$500k", ">$500k"];
    const INC_ORDER = ["<=$75k", "$75k-$125k", "$125k-$200k", ">$200k"];
    const MATERIAL_BPS = (PROV.thresholds && PROV.thresholds.meaningful_gap_bps) || 5;

    const $ = (id) => document.getElementById(id);
    const stateSelect = $("sel-state");
    const dtiSelect = $("sel-dti");
    const cltvSelect = $("sel-cltv");
    const announcer = $("live-announcer");

    let activeDim = "cltv";
    let activeMetric = "gap_rs";

    /* ---------- Formatting: round half up, same rule as the Word memos ---------- */
    function round1(v) {
      return Math.sign(v) * Math.round(Math.abs(v) * 10 + 1e-9) / 10;
    }
    function fmtBps(val, unit = true) {
      if (val === null || val === undefined) return "N/A";
      const r = round1(val);
      const sign = r > 0 ? "+" : r < 0 ? "−" : "";
      return `${sign}${Math.abs(r).toFixed(1)}${unit ? " bps" : ""}`;
    }
    function fmtPct(val, digits = 3) {
      if (val === null || val === undefined) return "N/A";
      return `${val.toFixed(digits)}%`;
    }
    const fmtN = (n) => (n === null || n === undefined ? "N/A" : n.toLocaleString("en-US"));
    function clampPct(val, lo, hi) {
      return Math.max(0, Math.min(100, ((val - lo) / (hi - lo)) * 100));
    }
    function fmtDate(iso) {
      if (!iso) return "N/A";
      const d = new Date(iso);
      if (isNaN(d)) return iso;
      return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
    }

    /* ---------- Fact sheet: single source for every page ---------- */
    const HM = DATA.headline_metrics;
    const BASE = DATA.slices_data.slices["ALL|ALL|ALL"];
    const NB = HM.national_vs_nonbank || null;
    const isPeerRow = (r) => r.slice.startsWith("Alternative comparator");
    const nbSeg = (dim, grp) => (DATA.nonbank_by_segment || []).find((r) => r.dimension === dim && r.group === grp) || null;
    const bankBar = (key) => DATA.slices_data.bars[`ALL|${key}`] || null;
    const cells16 = [];
    DTI_ORDER.forEach((d) => CLTV_ORDER.forEach((c) => cells16.push(DATA.slices_data.slices[`ALL|${d}|${c}`])));
    const robGaps = DATA.robustness_checks.filter((r) => !isPeerRow(r)).map((r) => r.rate_spread_gap_bps).filter((v) => v !== null);
    const PRIORITY = (DATA.nonbank_priority && DATA.nonbank_priority.segments) || [];

    const F = {
      gapBank: BASE.gap_rs, rsF: BASE.rs_f, rsB: BASE.rs_b, feeBank: BASE.gap_oc,
      nF: BASE.nf, nB: BASE.nb, lF: BASE.lf, lB: BASE.lb,
      gapNB: NB ? NB.rate_spread_gap_bps : null,
      feeNB: NB ? NB.orig_pct_gap_bps : null,
      rsNB: NB ? (NB.comparator_median_rate_spread ?? NB.bank_median_rate_spread) : null,
      nNB: NB ? (NB.comparator_loans_rs || NB.bank_loans_rs) : null,
      lNB: NB ? (NB.comparator_lenders || NB.bank_lenders) : null,
      cellsHigher: cells16.filter((c) => c && c.ok && c.gap_rs >= MATERIAL_BPS).length,
      cellsTotal: cells16.length,
      lendersAbove: DATA.lender_stats.above_bank,
      lendersTotal: DATA.lender_stats.total,
      lenders5: DATA.lender_stats.above_5bps,
      robMin: Math.min(...robGaps), robMax: Math.max(...robGaps),
      ci: HM.baseline_lender_cluster_ci95_bps || [null, null],
      fourWay: HM.four_way_cells_fintech_higher, fourWayTot: HM.four_way_cells_min25_per_side,
      exRocket: PROV.ex_rocket ? PROV.ex_rocket.rate_spread_gap_bps : null,
      rocketShare: DATA.fintech_lenders.length ? DATA.fintech_lenders[0].share_of_fintech_loans_pct : null,
      rocketName: DATA.fintech_lenders.length ? DATA.fintech_lenders[0].lender_name : "",
      priority: PRIORITY,
    };
    const priorityText = PRIORITY.length
      ? PRIORITY.map((s) => s.label).join(" and ")
      : "all borrower groups";
    const priorityFees = PRIORITY.map((s) => `${fmtBps(s.orig_pct_gap_bps)} (${s.label})`).join("; ");

    /* ---------- Tabs ---------- */
    const tabButtons = Array.from(document.querySelectorAll(".page-tab-btn[role='tab']"));
    const tabPanels = ["panel-exec", "panel-analyst", "panel-reg"].map($);
    const supportsUntilFound = "onbeforematch" in HTMLElement.prototype;
    function hidePanel(p) { if (supportsUntilFound) p.setAttribute("hidden", "until-found"); else p.hidden = true; }
    function activateTab(btn) {
      const target = btn.getAttribute("aria-controls");
      tabButtons.forEach((b) => b.setAttribute("aria-selected", String(b === btn)));
      tabPanels.forEach((p) => (p.id === target ? p.removeAttribute("hidden") : hidePanel(p)));
      if (location.hash !== "#" + target.replace("panel-", "")) history.replaceState(null, "", "#" + target.replace("panel-", ""));
    }
    tabButtons.forEach((b) => b.addEventListener("click", () => activateTab(b)));
    $("tab-panels-root").addEventListener("beforematch", (e) => {
      const p = tabPanels.find((x) => x === e.target || x.contains(e.target));
      if (p) activateTab(tabButtons.find((b) => b.getAttribute("aria-controls") === p.id));
    });
    if (!supportsUntilFound) tabPanels.slice(1).forEach((p) => { p.hidden = true; });

    /* ---------- Shared bar renderer ---------- */
    function buildBarRows(container, items, minFloor, maxCeil, onClickRow) {
      container.innerHTML = "";
      const vals = items.map((d) => d.val).filter((v) => v !== null && v !== undefined);
      const minVal = Math.min(0, ...vals, minFloor);
      const maxVal = Math.max(maxCeil, ...vals);
      const span = (maxVal - minVal) || 1;
      const zeroPct = ((0 - minVal) / span) * 100;
      items.forEach((item) => {
        const row = document.createElement("div");
        row.className = "bar-row" + (onClickRow ? " interactive-row" : "") + (item.active ? " active-slice" : "");
        if (onClickRow) row.addEventListener("click", () => onClickRow(item));
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
          fill.style.insetInlineStart = `${Math.min(zeroPct, valPct)}%`;
          fill.style.inlineSize = `${Math.max(0.8, Math.abs(valPct - zeroPct))}%`;
          fill.style.backgroundColor = !item.ok ? "#94a3b8" : item.val >= 0 ? "var(--fintech-fill)" : "var(--bank-fill)";
          track.appendChild(fill);
        }
        const valEl = document.createElement("div");
        valEl.className = "bar-val";
        valEl.style.color = !item.ok ? "#64748b" : (item.val || 0) >= 0 ? "var(--fintech-col)" : "var(--bank-col)";
        valEl.textContent = fmtBps(item.val);
        row.append(lbl, track, valEl);
        container.appendChild(row);
      });
    }

    /* ================= PAGE 1: EXECUTIVE ================= */
    function renderExecutive() {
      $("exec-title").textContent =
        `AFC should launch a voluntary member pricing review benchmarked against nonbank peers, starting with origination fees on ${priorityText}`;
      $("kp-what").innerHTML =
        `Fintech borrowers paid a median rate spread <strong>${fmtBps(F.gapBank)}</strong> above bank borrowers with comparable observed profiles, in <strong>${F.cellsHigher} of ${F.cellsTotal}</strong> debt-to-income &times; down-payment groups.`;
      $("kp-sowhat").innerHTML = F.gapNB === null ? "Nonbank comparison not available." :
        `Against other nonbank lenders the gap is <strong>${fmtBps(F.gapNB)}</strong>: the premium follows the nonbank business model, not a fintech markup. Origination fees remain <strong>${fmtBps(F.feeNB)}</strong> above nonbank peers.`;
      $("kp-nowwhat").innerHTML =
        `Lead the answer before regulators and the press compare members with banks: benchmark each member against nonbank peers and start with <strong>fees on ${priorityText}</strong>.`;

      $("ex-k1").textContent = fmtBps(F.gapBank);
      $("ex-k1").className = "kpi-value fintech-higher";
      $("ex-k1-sub").textContent = `Rate-spread gap vs. ${fmtN(F.lB)} banks (fintech ${fmtPct(F.rsF)} vs. bank ${fmtPct(F.rsB)})`;
      $("ex-k2").textContent = fmtBps(F.gapNB);
      $("ex-k2-sub").textContent = `Rate-spread gap vs. ${fmtN(F.lNB)} other nonbank lenders: within ±${MATERIAL_BPS} bps, i.e. in line`;
      $("ex-k3").textContent = fmtBps(F.feeNB);
      $("ex-k3-sub").textContent = `Origination-fee gap vs. nonbank peers; largest in ${priorityFees}`;
      $("ex-step2-focus").textContent = priorityText;

      const rows = [
        { label: "All comparable loans", sub: `${fmtN(F.nF)} fintech / ${fmtN(F.nB)} bank loans`, bank: BASE.gap_rs, nb: F.gapNB, fee: F.feeNB, prio: false },
      ];
      [
        ["cltv", "cltv_group", "<=80%", "Down payment 20%+ (CLTV ≤80%)"],
        ["cltv", "cltv_group", ">95%", "Down payment under 5% (CLTV >95%)"],
        ["loan", "loan_amount_group", "<=$200k", "Loan ≤$200k"],
        ["income", "income_group", "<=$75k", "Income ≤$75k"],
        ["income", "income_group", ">$200k", "Income >$200k"],
      ].forEach(([k, dim, grp, label]) => {
        const b = bankBar(`${k}|${grp}`);
        const n = nbSeg(dim, grp);
        rows.push({
          label, sub: b ? `${fmtN(b.nf)} fintech / ${fmtN(b.nb)} bank loans` : "",
          bank: b ? b.gap_rs : null, nb: n ? n.rate_spread_gap_bps : null, fee: n ? n.orig_pct_gap_bps : null,
          prio: PRIORITY.some((p) => p.dimension === dim && p.group === grp),
        });
      });

      const vals = rows.flatMap((r) => [r.bank, r.nb]).filter((v) => v !== null);
      const lo = Math.min(-10, Math.floor(Math.min(...vals) / 10) * 10);
      const hi = Math.max(30, Math.ceil((Math.max(...vals) + 3) / 10) * 10);
      const pos = (v) => clampPct(v, lo, hi);
      const box = $("exec-dumbbell");
      box.innerHTML = "";
      rows.forEach((r) => {
        const row = document.createElement("div");
        row.className = "db-row" + (r.prio ? " db-prio" : "");
        const a = pos(r.nb ?? 0), b = pos(r.bank ?? 0);
        row.innerHTML =
          `<div class="bar-label">${r.label}${r.prio ? ' <span class="start-tag">start here</span>' : ""}<span class="bar-label-sub">${r.sub}</span></div>` +
          `<div class="db-track"><div class="zero-line" style="inset-inline-start:${pos(0)}%"></div>` +
          `<div class="db-link" style="inset-inline-start:${Math.min(a, b)}%; inline-size:${Math.abs(b - a)}%"></div>` +
          (r.nb !== null ? `<i class="dot dot-nb" style="inset-inline-start:${a}%" title="vs. nonbanks ${fmtBps(r.nb)}"></i><span class="db-lab db-lab-nb" style="inset-inline-start:${a}%">${fmtBps(r.nb, false)}</span>` : "") +
          (r.bank !== null ? `<i class="dot dot-bank" style="inset-inline-start:${b}%" title="vs. banks ${fmtBps(r.bank)}"></i><span class="db-lab db-lab-bank" style="inset-inline-start:${b}%">${fmtBps(r.bank, false)}</span>` : "") +
          `</div><div class="bar-val db-fee${r.prio || r === rows[0] ? " fee-hot" : ""}">${fmtBps(r.fee)}<span class="bar-label-sub">fee vs. nonbanks</span></div>`;
        box.appendChild(row);
      });
      const axis = $("exec-axis");
      axis.innerHTML = '<div></div><div class="db-ticks">' +
        [lo, ...Array.from({ length: Math.round((hi - lo) / 10) - 1 }, (_, i) => lo + 10 * (i + 1)), hi]
          .map((t) => `<span style="inset-inline-start:${pos(t)}%">${t > 0 ? "+" : ""}${t}</span>`).join("") +
        '</div><div class="db-unit">bps</div>';
    }

    /* ================= PAGE 2: ANALYST ================= */
    function initDropdowns() {
      const all = document.createElement("option");
      all.value = "ALL";
      all.textContent = "All U.S.";
      stateSelect.appendChild(all);
      DATA.slices_data.states.forEach((st) => {
        const o = document.createElement("option");
        o.value = st.code;
        o.textContent = `${st.code} — ${st.name}`;
        stateSelect.appendChild(o);
      });
    }
    const getSlice = (st, dti, cltv) => DATA.slices_data.slices[`${st}|${dti}|${cltv}`] || null;

    function renderAnalystHeader() {
      $("an-title").textContent = F.gapNB !== null && F.gapNB < MATERIAL_BPS
        ? `The ${fmtBps(F.gapBank)} premium vs. banks survives every test we ran, but it disappears against other nonbank lenders`
        : `The ${fmtBps(F.gapBank)} premium vs. banks survives every test we ran, and persists against other nonbank lenders`;
      $("an-sub").innerHTML =
        `Banks: ${F.cellsHigher} of ${F.cellsTotal} risk cells, ${F.lendersAbove} of ${F.lendersTotal} fintech lenders above the bank median, ` +
        `${fmtBps(F.robMin)} to ${fmtBps(F.robMax)} across sample definitions. Other nonbanks: ${fmtBps(F.gapNB)} on rate spread, ${fmtBps(F.feeNB)} on fees.`;
      $("matrix-count").textContent = `${F.cellsHigher} of ${F.cellsTotal}`;
    }

    function updateKPIsAndDrill() {
      const st = stateSelect.value, dti = dtiSelect.value, cltv = cltvSelect.value;
      const s = getSlice(st, dti, cltv);
      const label = `${st === "ALL" ? "All U.S." : st} • DTI ${dti === "ALL" ? "all" : dti} • CLTV ${cltv === "ALL" ? "all" : cltv}`;
      $("drill-title").textContent = `Selected slice: ${label}`;
      const badge = $("kpi-cov-badge");
      if (!s || s.nf === 0 || s.nb === 0) {
        $("kpi-rs-gap").textContent = "No data";
        $("kpi-rs-gap").className = "kpi-value";
        $("kpi-rs-detail").textContent = "No matching loans in both groups";
        $("kpi-oc-gap").textContent = "N/A";
        $("kpi-oc-detail").textContent = "";
        badge.textContent = "No coverage";
        badge.className = "badge badge-warn";
        $("kpi-cov-loans").textContent = "Reset filters to view a broader sample";
        return;
      }
      $("kpi-rs-gap").textContent = fmtBps(s.gap_rs);
      $("kpi-rs-gap").className = "kpi-value " + (!s.ok ? "" : s.gap_rs >= 0 ? "fintech-higher" : "bank-higher");
      $("kpi-rs-detail").textContent = `Fintech ${fmtPct(s.rs_f)} vs. bank ${fmtPct(s.rs_b)}`;
      $("kpi-oc-gap").textContent = fmtBps(s.gap_oc);
      $("kpi-oc-gap").className = "kpi-value " + (!s.ok ? "" : s.gap_oc >= 0 ? "fintech-higher" : "bank-higher");
      $("kpi-oc-detail").textContent = `Fintech ${fmtPct(s.oc_f)} vs. bank ${fmtPct(s.oc_b)} of loan`;
      $("kpi-cov-loans").textContent = `${fmtN(s.nf)} fintech (${s.lf} lenders) vs. ${fmtN(s.nb)} bank (${s.lb} lenders)`;
      if (!s.ok) { badge.textContent = "Low coverage: do not interpret"; badge.className = "badge badge-warn"; }
      else if (s.gap_rs >= MATERIAL_BPS) { badge.textContent = `Material: gap ≥ +${MATERIAL_BPS} bps`; badge.className = "badge badge-ok"; }
      else { badge.textContent = `Below the ${MATERIAL_BPS} bps materiality line`; badge.className = "badge badge-neutral"; }

      const lo = -0.6, hi = 1.2;
      const z = clampPct(0, lo, hi);
      $("iqr-zero-1").style.insetInlineStart = `${z}%`;
      $("iqr-zero-2").style.insetInlineStart = `${z}%`;
      [["f", s.f_p25, s.f_p75, s.rs_f], ["b", s.b_p25, s.b_p75, s.rs_b]].forEach(([k, p25, p75, med]) => {
        const l = clampPct(p25 ?? 0, lo, hi), r = clampPct(p75 ?? 0, lo, hi);
        $(`iqr-box-${k}`).style.insetInlineStart = `${Math.min(l, r)}%`;
        $(`iqr-box-${k}`).style.inlineSize = `${Math.max(1.5, Math.abs(r - l))}%`;
        $(`iqr-med-${k}`).style.insetInlineStart = `${clampPct(med ?? 0, lo, hi)}%`;
      });
      $("vc-rs-f").textContent = fmtPct(s.rs_f);
      $("vc-rs-b").textContent = fmtPct(s.rs_b);
      $("vc-rs-badge").textContent = fmtBps(s.gap_rs);
      $("vc-iqr-caption").textContent =
        `Middle 50%: fintech ${fmtPct(s.f_p25, 2)} to ${fmtPct(s.f_p75, 2)}; bank ${fmtPct(s.b_p25, 2)} to ${fmtPct(s.b_p75, 2)}. Scale −0.6% to +1.2%; grey line = 0 (APR equals APOR).`;
      $("bar-oc-f").style.inlineSize = `${clampPct(s.oc_f ?? 0, 0, 2.0)}%`;
      $("bar-oc-b").style.inlineSize = `${clampPct(s.oc_b ?? 0, 0, 2.0)}%`;
      $("vc-oc-f").textContent = fmtPct(s.oc_f);
      $("vc-oc-b").textContent = fmtPct(s.oc_b);
      $("vc-oc-badge").textContent = fmtBps(s.gap_oc);
      $("vc-ir-badge").textContent = fmtBps(s.gap_ir);
      $("vc-ir-text").textContent = `Fintech ${fmtPct(s.ir_f)} vs. bank ${fmtPct(s.ir_b)}. Note rates are quoted in 1/8-point steps, so medians move in 12.5 bps increments; the rate spread above is the main measure.`;
      announcer.textContent = `Updated slice: rate spread gap ${fmtBps(s.gap_rs)}.`;
    }

    function renderSegmentChart() {
      const st = stateSelect.value;
      const order = { cltv: CLTV_ORDER, dti: DTI_ORDER, loan: LOAN_ORDER, income: INC_ORDER }[activeDim];
      const dimTitle = { cltv: "down payment (CLTV)", dti: "debt-to-income", loan: "loan size", income: "borrower income" }[activeDim];
      const metricTitle = activeMetric === "gap_rs" ? "Rate-spread gap" : "Origination-fee gap";
      $("overview-chart-title").textContent = `${metricTitle} vs. banks by ${dimTitle}${st === "ALL" ? "" : " — " + st}`;
      const items = order.map((bin) => {
        const b = DATA.slices_data.bars[`${st}|${activeDim}|${bin}`];
        return {
          label: bin, bin,
          sub: b ? `${fmtN(b.nf)} fintech • ${fmtN(b.nb)} bank${b.ok ? "" : " (low N)"}` : "No data",
          val: b ? b[activeMetric] : null, ok: b ? b.ok : false,
          active: (activeDim === "cltv" && cltvSelect.value === bin) || (activeDim === "dti" && dtiSelect.value === bin),
        };
      });
      const canFilter = activeDim === "cltv" || activeDim === "dti";
      buildBarRows($("overview-bar-container"), items, -5, activeMetric === "gap_rs" ? 35 : 70, canFilter ? (item) => {
        const sel = activeDim === "cltv" ? cltvSelect : dtiSelect;
        sel.value = sel.value === item.bin ? "ALL" : item.bin;
        refreshAll();
      } : null);
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
      const tbody = $("matrix-tbody");
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
          td.className = "matrix-cell" + (dtiSelect.value === dti && cltvSelect.value === cltv ? " selected-cell" : "");
          if (!s || s.nf === 0 || s.nb === 0) {
            td.style.backgroundColor = "#f8fafc";
            td.innerHTML = `<span class="cell-gap" style="color:#94a3b8;">N/A</span><span class="cell-meta">0 loans</span>`;
          } else {
            td.style.backgroundColor = heatColor(s.gap_rs, s.ok);
            const c = !s.ok ? "#64748b" : s.gap_rs >= 0 ? "#92400e" : "#1e40af";
            const tag = s.ok ? `F ${fmtN(s.nf)} / B ${fmtN(s.nb)}` : `Low N (F ${s.nf})`;
            td.innerHTML = `<span class="cell-gap" style="color:${c};">${fmtBps(s.gap_rs, false)}</span><span class="cell-meta">${tag}</span>`;
          }
          td.addEventListener("click", () => {
            const same = dtiSelect.value === dti && cltvSelect.value === cltv;
            dtiSelect.value = same ? "ALL" : dti;
            cltvSelect.value = same ? "ALL" : cltv;
            refreshAll();
          });
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }

    function renderLendersAndRobustness() {
      $("lender-title").textContent = `${F.lendersAbove} of ${F.lendersTotal} fintech lenders price above the bank median`;
      buildBarRows($("lender-bar-container"), DATA.fintech_lenders.map((r) => ({
        label: r.lender_name,
        sub: `${fmtN(r.total_loans)} loans (${r.share_of_fintech_loans_pct.toFixed(1)}% of fintech)`,
        val: r.gap_vs_bank_median_bps, ok: r.total_loans >= 100, active: false,
      })), -30, 50, null);
      $("lender-summary").innerHTML =
        `Rate-spread gap vs. bank median (${fmtPct(F.rsB)}). ${F.lenders5} of ${F.lendersTotal} are above by ${MATERIAL_BPS} bps or more; ` +
        `equal-weighted lender gap ${fmtBps(DATA.lender_stats.equal_weighted_gap_bps)}.` +
        (F.exRocket !== null ? ` ${F.rocketName} is ${F.rocketShare.toFixed(0)}% of fintech loans; without it the gap is <strong>${fmtBps(F.exRocket)}</strong>.` : "");
      $("robust-summary").innerHTML =
        `Versus banks the gap stays between <strong>${fmtBps(F.robMin)} and ${fmtBps(F.robMax)}</strong>` +
        (F.ci[0] !== null ? ` (baseline lender-clustered 95% CI ${fmtBps(F.ci[0])} to ${fmtBps(F.ci[1])})` : "") +
        `. The nonbank row uses a different comparator and is the strongest evidence against a fintech-specific markup.`;
      const tb = $("robustness-tbody");
      tb.innerHTML = "";
      DATA.robustness_checks.forEach((r) => {
        const tr = document.createElement("tr");
        if (isPeerRow(r)) tr.className = "peer-row";
        tr.innerHTML = `<td style="text-align:start;">${r.slice}</td><td>${fmtN(r.fintech_loans_rs)}</td><td>${fmtN(r.bank_loans_rs)}</td>` +
          `<td style="font-weight:700;">${fmtBps(r.rate_spread_gap_bps, false)}</td><td>${fmtBps(r.orig_pct_gap_bps, false)}</td>`;
        tb.appendChild(tr);
      });
    }

    function renderConditions() {
      const pill = (ok, yes = "Recommendation holds", no = "Would change") =>
        `<span class="badge ${ok ? "badge-ok" : "badge-warn"}">${ok ? yes : no}</span>`;
      const minPrioFee = PRIORITY.length ? Math.min(...PRIORITY.map((p) => p.orig_pct_gap_bps)) : null;
      const rows = [
        [`Gap vs. banks falls below +${MATERIAL_BPS} bps in most risk cells`, "Drop the review: no premium to explain",
          `${F.cellsHigher} of ${F.cellsTotal} cells at +${MATERIAL_BPS} bps or more`, pill(F.cellsHigher > F.cellsTotal / 2)],
        ["The premium is driven by a single lender", "Treat it as a lender issue, not an AFC program",
          F.exRocket !== null ? `Without ${F.rocketName}: ${fmtBps(F.exRocket)}; ${F.lendersAbove} of ${F.lendersTotal} lenders above` : `${F.lendersAbove} of ${F.lendersTotal} lenders above`,
          pill(F.exRocket === null || F.exRocket >= MATERIAL_BPS)],
        [`Gap vs. other nonbanks rises above +${MATERIAL_BPS} bps`, "Reframe as a fintech-specific markup and widen the review",
          `${fmtBps(F.gapNB)} on rate spread`, pill(F.gapNB !== null && F.gapNB < MATERIAL_BPS, "Framing holds", "Reframe")],
        [`Fee gap vs. nonbank peers falls below +${MATERIAL_BPS} bps in the priority groups`, "Move the review off fees",
          priorityFees || "No priority groups", pill(minPrioFee !== null && minPrioFee >= MATERIAL_BPS, "Fee focus holds", "Refocus")],
        ["Member data (credit score, LLPAs, lock date) explains the gap", "Publish the result as evidence for members",
          "Not testable with public HMDA; this is Step 2 of the review", `<span class="badge badge-neutral">Open</span>`],
      ];
      $("cond-tbody").innerHTML = rows.map((r) =>
        `<tr><td style="text-align:start;">${r[0]}</td><td style="text-align:start;">${r[1]}</td><td style="text-align:start;">${r[2]}</td><td>${r[3]}</td></tr>`).join("");
    }

    /* ================= PAGE 3: REGULATOR ================= */
    function renderRegulator() {
      const rs = "rate_spread (APR − APOR on the lock date)";
      const fee = "origination_charges ÷ loan_amount × 100";
      const facts = [
        ["F1", "Rate-spread gap vs. banks", fmtBps(F.gapBank), `100 × (median ${rs}, fintech − bank); fintech ${fmtPct(F.rsF)}, bank ${fmtPct(F.rsB)}`, "analyze_pricing.py → headline_metrics.national_controlled_sample"],
        ["F2", "Rate-spread gap vs. other nonbanks", fmtBps(F.gapNB), "Same measure; comparator = non-fintech nonbanks (Philadelphia Fed TYPE 40/41)", "analyze_pricing.py → headline_metrics.national_vs_nonbank"],
        ["F3", "Origination-fee gap vs. other nonbanks", fmtBps(F.feeNB), `Median ${fee}, fintech − comparator`, "analyze_pricing.py → national_vs_nonbank.orig_pct_gap_bps"],
        ...PRIORITY.map((p, i) => [`F${4 + i}`, `Fee gap vs. other nonbanks, ${p.label}`, fmtBps(p.orig_pct_gap_bps), `As F3 within ${p.dimension} = ${p.group}`, "analyze_pricing.py → nonbank_priority"]),
        [`F${4 + PRIORITY.length}`, "Origination-fee gap vs. banks", fmtBps(F.feeBank), `As F3, comparator = banks`, "build_dashboard.py → slices ALL|ALL|ALL"],
        [`F${5 + PRIORITY.length}`, `Risk cells with gap ≥ +${MATERIAL_BPS} bps`, `${F.cellsHigher} of ${F.cellsTotal}`, "debt_to_income_ratio (4 bands <50%) × combined_loan_to_value_ratio (4 bands)", "build_dashboard.py → slices ALL|DTI|CLTV"],
        [`F${6 + PRIORITY.length}`, "Fintech lenders above the bank median", `${F.lendersAbove} of ${F.lendersTotal}`, "Per-lender median rate spread vs. bank median; lender = lei", "build_dashboard.py → lender_stats"],
        [`F${7 + PRIORITY.length}`, "Range across sample definitions (vs. banks)", `${fmtBps(F.robMin, false)} to ${fmtBps(F.robMax, false)}`, "F1 recomputed under each specification on the Analyst page", "build_dashboard.py → robustness_checks"],
        [`F${8 + PRIORITY.length}`, "Lender-clustered 95% CI (baseline)", `${fmtBps(F.ci[0], false)} to ${fmtBps(F.ci[1], false)}`, "Cluster bootstrap at the lender (LEI) level, 300 draws: resamples lenders, not loans", "analyze_pricing.py → baseline_lender_cluster_ci95_bps"],
        [`F${9 + PRIORITY.length}`, "Four-way cells where fintech is higher", `${F.fourWay} of ${F.fourWayTot}`, "DTI × CLTV × income × loan size cells with ≥25 loans per side", "analyze_pricing.py → four_way_cells_*"],
      ];
      $("facts-tbody").innerHTML = facts.map((r) =>
        `<tr><td>${r[0]}</td><td style="text-align:start;">${r[1]}</td><td style="font-weight:800; white-space:nowrap;">${r[2]}</td><td style="text-align:start;">${r[3]}</td><td style="text-align:start;"><code>${r[4]}</code></td></tr>`).join("");

      const fun = PROV.funnel || {};
      const g = PROV.groups || {};
      const lg = PROV.lender_groups || {};
      const lineage = [
        ["HMDA 2025 LAR records read (all actions and products)", "download_hmda.py", fun.rows_read],
        [`Eligible: ${(PROV.filters || []).map((f) => `${f.field}=${f.equals}`).join(", ")}`, "download_hmda.py", PROV.eligible_loans],
        [`Fintech (NYU list, ${fmtN(lg["Fintech"])} lenders) + bank comparator (TYPE 10/14/20, ${fmtN(lg["Bank comparator"])} lenders)`, "classify_lenders_nyu.py", g["Main comparison (Fintech + Bank)"]],
        ["With a reported rate spread", "clean_mortgages.py", HM.national_unadjusted ? HM.national_unadjusted.fintech_loans_rs + HM.national_unadjusted.bank_loans_rs : null],
        [`Controlled baseline: valid DTI, CLTV, income and loan amount; DTI <50% (${fmtN(F.nF)} fintech / ${fmtN(F.nB)} bank)`, "analyze_pricing.py", F.nF + F.nB],
        [`Alternative comparator: non-fintech nonbanks, same filters (${fmtN(F.lNB)} lenders)`, "analyze_pricing.py", F.nNB],
      ];
      $("lineage-tbody").innerHTML = lineage.map((r, i) =>
        `<tr${i === 5 ? ' class="peer-row"' : ""}><td style="text-align:start;">${r[0]}</td><td style="text-align:start;"><code>${r[1]}</code></td><td style="font-weight:700;">${fmtN(r[2])}</td></tr>`).join("");

      const t = PROV.thresholds || {};
      const params = [
        ["Materiality line", `≥ +${fmtN(t.meaningful_gap_bps)} bps gap`],
        ["Minimum coverage per cell", `${fmtN(t.min_loans_per_side)} loans per side, ${fmtN(t.min_lenders_fintech)} fintech and ${fmtN(t.min_lenders_bank)} bank lenders`],
        ["DTI cap", "<50% (agency automated-underwriting limit)"],
        ["Central measure", "Medians and IQRs, not means (skewed spreads and fees)"],
        ["Missing values", "NA and Exempt excluded, never imputed; $0 fees kept"],
      ];
      $("params-tbody").innerHTML = params.map((r) => `<tr><th scope="row">${r[0]}</th><td style="text-align:start;">${r[1]}</td></tr>`).join("");

      const dl = PROV.downloads || {};
      const sh = (s) => (s ? `<code>${s.slice(0, 12)}</code>` : "N/A");
      const srcs = [
        ["FFIEC/CFPB HMDA 2025 LAR (static snapshot)", dl.lar ? dl.lar.last_modified : null, dl.lar ? fmtDate(dl.lar.downloaded_at_utc) : null, dl.lar ? dl.lar.sha256 : null],
        ["FFIEC/CFPB HMDA 2025 Transmittal Sheet", dl.ts ? dl.ts.last_modified : null, dl.ts ? fmtDate(dl.ts.downloaded_at_utc) : null, dl.ts ? dl.ts.sha256 : null],
        ["NYU Stern fintech lender list (Fuster et al., 2019)", "2017 cumulative list", PROV.nyu_created ? fmtDate(PROV.nyu_created) : null, (PROV.nyu_sha || {})["fintech_classification.xlsx"]],
        ["Philadelphia Fed HMDA Lender File (2018–2025)", "Lender TYPE codes", PROV.nyu_created ? fmtDate(PROV.nyu_created) : null, (PROV.nyu_sha || {})["audible_hmda_lender_2018_present.xlsx"]],
      ];
      $("sources-tbody").innerHTML = srcs.map((r) =>
        `<tr><td style="text-align:start;">${r[0]}</td><td style="text-align:start;">${r[1] || "N/A"}</td><td style="text-align:start;">${r[2] || "N/A"}</td><td style="text-align:start;">${sh(r[3])}</td></tr>`).join("");

      const sc = PROV.source_check;
      $("source-check").innerHTML = !sc
        ? "Live source check: not run in this build (run <code>./run_demo.sh</code>)."
        : sc.status === "match"
          ? `<span class="badge badge-ok">Live source check passed</span> ${fmtDate(sc.checked_at_utc)}: the FFIEC server still publishes the same files (ETag and last-modified match the archive used).`
          : sc.status === "changed"
            ? `<span class="badge badge-warn">Source changed</span> ${fmtDate(sc.checked_at_utc)}: FFIEC has republished the snapshot. Rerun <code>./run_demo.sh --full</code> before relying on these numbers.`
            : `<span class="badge badge-neutral">Source not reachable</span> ${fmtDate(sc.checked_at_utc)}: offline check; figures come from the checksummed archive listed below.`;
      $("nyu-match").textContent = PROV.nyu_in_sample ? `${PROV.nyu_in_sample} of ${PROV.nyu_source}` : "N/A";
    }

    function renderAsOf() {
      const lar = (PROV.downloads || {}).lar;
      const sc = PROV.source_check;
      $("data-asof").innerHTML =
        `Data: 2025 HMDA snapshot (FFIEC, published ${lar ? fmtDate(lar.last_modified) : "N/A"}), retrieved ${lar ? fmtDate(lar.downloaded_at_utc) : "N/A"}` +
        ` &bull; results computed ${fmtDate(DATA.generated_at_utc)} &bull; dashboard built ${fmtDate(PROV.built_at_utc)}` +
        (sc ? ` &bull; source check ${sc.status === "match" ? "passed" : sc.status} ${fmtDate(sc.checked_at_utc)}` : "");
    }

    function refreshAll() {
      updateKPIsAndDrill();
      renderSegmentChart();
      renderMatrix();
    }

    [stateSelect, dtiSelect, cltvSelect].forEach((el) => el.addEventListener("change", refreshAll));
    $("btn-reset").addEventListener("click", () => {
      stateSelect.value = "ALL"; dtiSelect.value = "ALL"; cltvSelect.value = "ALL";
      refreshAll();
    });
    document.querySelectorAll(".pill-btn[data-dim]").forEach((btn) => btn.addEventListener("click", () => {
      activeDim = btn.getAttribute("data-dim");
      document.querySelectorAll(".pill-btn[data-dim]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      renderSegmentChart();
    }));
    document.querySelectorAll(".metric-btn[data-metric]").forEach((btn) => btn.addEventListener("click", () => {
      activeMetric = btn.getAttribute("data-metric");
      document.querySelectorAll(".metric-btn[data-metric]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      renderSegmentChart();
    }));

    renderAsOf();
    renderExecutive();
    initDropdowns();
    renderAnalystHeader();
    renderLendersAndRobustness();
    renderConditions();
    renderRegulator();
    refreshAll();
    const startTab = { "#analyst": "tab-btn-analyst", "#reg": "tab-btn-reg" }[location.hash];
    if (startTab) activateTab($(startTab));
  </script>
</body>
</html>
"""


def summary_fields(summary):
    """Fields the dashboard takes from pricing_summary.json (analyze_pricing.py output)."""
    return {
        'headline_metrics': summary['headline_metrics'],
        'nonbank_by_segment': summary.get('nonbank_by_segment', []),
        'nonbank_priority': summary.get('nonbank_priority'),
    }


def _read_json(path: Path):
    """Return parsed JSON, or None if the file is missing or unreadable."""
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def load_provenance(data_dir: Path, summary: dict) -> dict:
    """Collect the logged pipeline metadata shown on the Regulator page.

    Every value comes from a file an upstream script wrote; nothing is typed here.
    Missing files simply leave their fields empty (the page shows N/A).
    """
    manifest = _read_json(data_dir / 'manifest.json') or {}
    sample = _read_json(data_dir / 'sample_summary.json') or {}
    nyu = _read_json(data_dir / 'nyu_classification_summary.json') or {}
    cleaning = _read_json(data_dir / 'data_quality' / 'cleaning_summary.json') or {}
    ex_rocket = next((r for r in summary.get('robustness_checks', [])
                      if r.get('slice', '').startswith('Baseline excluding Rocket')), None)
    return {
        'built_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'downloads': manifest.get('downloads', {}),
        'eligible_loans': manifest.get('eligible_loans') or sample.get('eligible_loans'),
        'filters': sample.get('filters_in_order', []),
        'funnel': sample.get('filter_funnel', {}),
        'groups': cleaning.get('loans_by_group', {}),
        'lender_groups': cleaning.get('lenders_by_group', {}),
        'nyu_created': nyu.get('created_at_utc'),
        'nyu_sha': nyu.get('input_sha256', {}),
        'nyu_source': nyu.get('nyu_source_lenders'),
        'nyu_in_sample': nyu.get('nyu_lenders_in_sample'),
        'thresholds': summary.get('thresholds', {}),
        'ex_rocket': ({'rate_spread_gap_bps': ex_rocket.get('rate_spread_gap_bps'),
                       'fintech_loans_rs': ex_rocket.get('fintech_loans_rs')} if ex_rocket else None),
        'source_check': _read_json(data_dir / 'source_check.json'),
    }


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--from-json', action='store_true',
                        help='Rebuild the HTML from the saved dashboard_slices.json plus the current '
                             'pricing_summary.json, without the loan-level CSV (for layout/text changes).')
    args = parser.parse_args(argv)
    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / 'data' / '2025'
    clean_csv = data_dir / 'mortgages_2025_clean.csv'
    pricing_json = data_dir / 'analysis' / 'pricing_summary.json'
    slices_path = data_dir / 'analysis' / 'dashboard_slices.json'
    summary = json.loads(pricing_json.read_text(encoding='utf-8'))

    if args.from_json:
        payload = json.loads(slices_path.read_text(encoding='utf-8'))
        payload.update(summary_fields(summary))
    else:
        print('Computing interactive slice medians from loan records ...')
        slices_data = compute_slices(clean_csv)
        payload = {
            'generated_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            **summary_fields(summary),
            'robustness_checks': slices_data['robustness_checks'],
            'fintech_lenders': slices_data['fintech_lenders'],
            'lender_stats': slices_data['lender_stats'],
            'slices_data': {
                'states': slices_data['states'],
                'slices': slices_data['slices'],
                'bars': slices_data['bars'],
            },
        }

    slices_path.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')

    provenance = load_provenance(data_dir, summary)
    html_content = (HTML_TEMPLATE
                    .replace('__DASHBOARD_JSON__', json.dumps(payload, separators=(',', ':')))
                    .replace('__PROVENANCE_JSON__', json.dumps(provenance, separators=(',', ':'))))
    submit_dir = base_dir.parent / 'Submit'
    submit_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = submit_dir / 'Project Audible Dashboard.html'
    dashboard_path.write_text(html_content, encoding='utf-8')
    print(f'Wrote {dashboard_path} ({dashboard_path.stat().st_size / 1024:.1f} KiB)')


if __name__ == '__main__':
    main()
