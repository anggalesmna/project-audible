#!/usr/bin/env python3
"""Step 1 & 2: Borrower group binning and pricing comparison analysis for Project Audible.

Reads:
  data/<year>/mortgages_<year>_clean.csv

Writes to data/<year>/analysis/:
  pricing_summary.json            Complete structured results for memo & HTML dashboard
  analysis_report.md              Human-readable report of all findings & robustness checks
  by_single_dimension.csv         Gaps across DTI, CLTV, Income, and Loan Amount bins
  by_dti_cltv_grid.csv            20-cell DTI x CLTV risk-controlled matrix
  by_four_way_cells.csv           320-cell DTI x CLTV x Income x Loan Amount controlled cells
  by_state.csv                    State-level pricing comparisons
  by_fintech_lender.csv           All 15 NYU Fintech lenders compared to Bank benchmark
  robustness_checks.csv           Baseline vs alternative samples and the non-fintech nonbank comparator

Headline sample ("controlled baseline"): Fintech vs Bank comparator loans with valid rate spread,
DTI, CLTV, income and loan amount, and DTI below 50%. This is the same sample the dashboard uses.

Standard library only (Python 3.10+).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
from array import array
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DTI_ORDER = ['<30%', '30%-<36%', '36%-43%', '44%-49%', '>=50%']
CLTV_ORDER = ['<=80%', '80.01%-90%', '90.01%-95%', '>95%']
INCOME_ORDER = ['<=$75k', '$75k-$125k', '$125k-$200k', '>$200k']
LOAN_ORDER = ['<=$200k', '$200k-$350k', '$350k-$500k', '>$500k']

MIN_LOANS_PER_SIDE = 100
MIN_LENDERS_FINTECH = 3
MIN_LENDERS_BANK = 10
MEANINGFUL_GAP_BPS = 5.0
ROCKET_LEI = '549300FGXN1K3HLB1R50'
TWENTY_FIRST_LEI = '549300XQVJ1XBNFA5536'
DTI_STANDARD_ORDER = DTI_ORDER[:4]  # conforming underwriting cap: DTI below 50%
# Philadelphia Fed TYPE codes for independent mortgage banks (nonbanks).
NONBANK_TYPE_CODES = {'40', '41'}
BASELINE_LABEL = 'Controlled baseline (4 borrower vars valid, DTI <50%)'


def comparison_role(row):
    """Return 'fintech', 'bank', 'nonbank' or None for one cleaned loan row.

    'nonbank' = independent mortgage banks NOT on the NYU list. It is used only as an
    alternative comparator, to test whether the gap is a fintech effect or a nonbank effect.
    """
    group = row['lender_type']
    if group == 'Fintech':
        return 'fintech'
    if group == 'Bank comparator':
        return 'bank'
    if group == 'Other lender' and row.get('institution_type_code', '').strip() in NONBANK_TYPE_CODES:
        return 'nonbank'
    return None


def in_baseline(row):
    """Controlled baseline: all borrower variables valid and DTI below 50%."""
    return row['elig_controlled'] == '1' and row['dti_group'] in DTI_STANDARD_ORDER


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def median(values):
    if not values:
        return None
    data = sorted(values)
    n = len(data)
    mid = n // 2
    return data[mid] if n % 2 == 1 else 0.5 * (data[mid - 1] + data[mid])


def quantile(sorted_vals, q):
    if not sorted_vals:
        return None
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (pos - lo) * (sorted_vals[hi] - sorted_vals[lo])


def r4(val):
    return round(val, 4) if val is not None else None


def r2(val):
    return round(val, 2) if val is not None else None


class Bucket:
    """Holds pricing values and lender sets for Fintech and Bank comparator in a slice."""
    __slots__ = ('rs_f', 'rs_b', 'ir_f', 'ir_b', 'oc_f', 'oc_b',
                 'lenders_f', 'lenders_b', 'loans_f', 'loans_b')

    def __init__(self):
        self.rs_f = array('d')
        self.rs_b = array('d')
        self.ir_f = array('d')
        self.ir_b = array('d')
        self.oc_f = array('d')
        self.oc_b = array('d')
        self.lenders_f = set()
        self.lenders_b = set()
        self.loans_f = 0
        self.loans_b = 0

    def add(self, is_fintech, lei, rs, ir, oc):
        if is_fintech:
            self.loans_f += 1
            self.lenders_f.add(lei)
            if rs is not None:
                self.rs_f.append(rs)
            if ir is not None:
                self.ir_f.append(ir)
            if oc is not None:
                self.oc_f.append(oc)
        else:
            self.loans_b += 1
            self.lenders_b.add(lei)
            if rs is not None:
                self.rs_b.append(rs)
            if ir is not None:
                self.ir_b.append(ir)
            if oc is not None:
                self.oc_b.append(oc)

    def summarize(self, meta=None):
        rs_f_sorted = sorted(self.rs_f)
        rs_b_sorted = sorted(self.rs_b)
        med_rs_f = quantile(rs_f_sorted, 0.5)
        med_rs_b = quantile(rs_b_sorted, 0.5)
        med_ir_f = median(self.ir_f)
        med_ir_b = median(self.ir_b)
        med_oc_f = median(self.oc_f)
        med_oc_b = median(self.oc_b)

        gap_rs_bps = 100.0 * (med_rs_f - med_rs_b) if (med_rs_f is not None and med_rs_b is not None) else None
        gap_ir_bps = 100.0 * (med_ir_f - med_ir_b) if (med_ir_f is not None and med_ir_b is not None) else None
        gap_oc_bps = 100.0 * (med_oc_f - med_oc_b) if (med_oc_f is not None and med_oc_b is not None) else None

        n_rs_f = len(rs_f_sorted)
        n_rs_b = len(rs_b_sorted)
        lf = len(self.lenders_f)
        lb = len(self.lenders_b)
        cov_ok = (
            n_rs_f >= MIN_LOANS_PER_SIDE
            and n_rs_b >= MIN_LOANS_PER_SIDE
            and lf >= MIN_LENDERS_FINTECH
            and lb >= MIN_LENDERS_BANK
        )
        if not cov_ok:
            status = 'Insufficient coverage'
        elif gap_rs_bps is not None and gap_rs_bps >= MEANINGFUL_GAP_BPS:
            status = 'Fintech higher (+5 bps or more)'
        elif gap_rs_bps is not None and gap_rs_bps <= -MEANINGFUL_GAP_BPS:
            status = 'Fintech lower (-5 bps or more)'
        else:
            status = 'Within +/-5 bps'

        out = dict(meta or {})
        out.update({
            'fintech_loans_rs': n_rs_f,
            'bank_loans_rs': n_rs_b,
            'fintech_lenders': lf,
            'bank_lenders': lb,
            'coverage_ok': cov_ok,
            'status': status,
            'fintech_median_rate_spread': r4(med_rs_f),
            'bank_median_rate_spread': r4(med_rs_b),
            'rate_spread_gap_bps': r2(gap_rs_bps),
            'fintech_rs_p25': r4(quantile(rs_f_sorted, 0.25)),
            'fintech_rs_p75': r4(quantile(rs_f_sorted, 0.75)),
            'bank_rs_p25': r4(quantile(rs_b_sorted, 0.25)),
            'bank_rs_p75': r4(quantile(rs_b_sorted, 0.75)),
            'fintech_median_interest_rate': r4(med_ir_f),
            'bank_median_interest_rate': r4(med_ir_b),
            'interest_rate_gap_bps': r2(gap_ir_bps),
            'fintech_median_orig_pct': r4(med_oc_f),
            'bank_median_orig_pct': r4(med_oc_b),
            'orig_pct_gap_bps': r2(gap_oc_bps),
        })
        return out


def write_csv(path, rows, fieldnames=None):
    if not rows and not fieldnames:
        return
    fields = fieldnames or list(rows[0].keys())
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, restval='')
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def bootstrap_ci_bps(rs_f_sorted, rs_b_sorted, iterations=400, seed=42):
    """Order-statistic / bootstrap 95% CI for 100 * (median(F) - median(B))."""
    if not rs_f_sorted or not rs_b_sorted:
        return None, None
    # Normal approximation to median variance via binomial order statistics
    # plus Monte Carlo draw from exact binomial order statistics (instantaneous even for N=350k).
    rng = random.Random(seed)
    nf = len(rs_f_sorted)
    nb = len(rs_b_sorted)
    sf = 0.5 * math.sqrt(nf)
    sb = 0.5 * math.sqrt(nb)
    diffs = []
    for _ in range(iterations):
        idx_f = min(nf - 1, max(0, int(round(nf * 0.5 + rng.gauss(0, sf)))))
        idx_b = min(nb - 1, max(0, int(round(nb * 0.5 + rng.gauss(0, sb)))))
        diffs.append(100.0 * (rs_f_sorted[idx_f] - rs_b_sorted[idx_b]))
    diffs.sort()
    return r2(quantile(diffs, 0.025)), r2(quantile(diffs, 0.975))


def cluster_bootstrap_ci_bps(lender_rs_f, lender_rs_b, iterations=300, seed=42):
    """Cluster bootstrap at the lender (LEI) level for 100 * (median(F) - median(B)).

    Resamples lenders with replacement and computes the loan-level median of each draw
    using pre-binned histograms (1 bp resolution) so 300 draws over 520k loans finish in ~1s.
    """
    if not lender_rs_f or not lender_rs_b:
        return None, None

    # Discretize rate spread to 0.005 percentage point (0.5 bp) bins in [-7.0, 9.0]
    lo, hi, step = -7.0, 9.0, 0.005
    nbins = int(round((hi - lo) / step)) + 1

    def to_hist(vals):
        h = Counter()
        for v in vals:
            b = min(nbins - 1, max(0, int(round((v - lo) / step))))
            h[b] += 1
        return h, len(vals)

    def median_from_hists(chosen):
        merged = Counter()
        total = 0
        for h, n in chosen:
            merged.update(h)
            total += n
        if total == 0:
            return 0.0
        target = total / 2.0
        cum = 0
        for b in sorted(merged):
            cum += merged[b]
            if cum >= target:
                return lo + b * step
        return hi

    hf = [to_hist(v) for v in lender_rs_f.values() if v]
    hb = [to_hist(v) for v in lender_rs_b.values() if v]
    rng = random.Random(seed)
    diffs = []
    for _ in range(iterations):
        draw_f = [rng.choice(hf) for _ in range(len(hf))]
        draw_b = [rng.choice(hb) for _ in range(len(hb))]
        diffs.append(100.0 * (median_from_hists(draw_f) - median_from_hists(draw_b)))
    diffs.sort()
    return r2(quantile(diffs, 0.025)), r2(quantile(diffs, 0.975))


def analyze(clean_csv_path, out_dir):
    national_all = Bucket()
    national_ctrl = Bucket()          # controlled baseline (DTI <50%): headline sample
    ctrl_incl_dti50 = Bucket()        # controlled incl. DTI >=50% (robustness)
    rob_vs_nonbank = Bucket()         # Fintech vs non-fintech independent mortgage banks
    nonbank_dims = {
        'dti_group': {k: Bucket() for k in DTI_STANDARD_ORDER},
        'cltv_group': {k: Bucket() for k in CLTV_ORDER},
        'income_group': {k: Bucket() for k in INCOME_ORDER},
        'loan_amount_group': {k: Bucket() for k in LOAN_ORDER},
    }
    rob_base_no_21st = Bucket()
    rob_base_no_rocket = Bucket()
    base_rs_f = defaultdict(lambda: array('d'))
    base_rs_b = defaultdict(lambda: array('d'))
    base_lenders = {}
    rob_no_rocket = Bucket()
    rob_no_top2 = Bucket()
    rob_no_21st = Bucket()
    rob_site_built_1unit = Bucket()
    rob_no_flags = Bucket()
    rob_common = Bucket()
    rob_ctrl_no_rocket = Bucket()

    by_dim = {
        'dti_group': {k: Bucket() for k in DTI_ORDER},
        'cltv_group': {k: Bucket() for k in CLTV_ORDER},
        'income_group': {k: Bucket() for k in INCOME_ORDER},
        'loan_amount_group': {k: Bucket() for k in LOAN_ORDER},
    }
    grid_dti_cltv = {(d, c): Bucket() for d in DTI_ORDER for c in CLTV_ORDER}
    grid_no_rocket = {(d, c): Bucket() for d in DTI_ORDER for c in CLTV_ORDER}
    four_way = defaultdict(Bucket)
    by_state = defaultdict(Bucket)

    lender_buckets = {}
    lender_rs_f = defaultdict(lambda: array('d'))
    lender_rs_b = defaultdict(lambda: array('d'))

    top2_leis = {ROCKET_LEI, '549300I9322255521985'}  # Rocket + Guaranteed Rate (resolved dynamically below)
    fintech_volume = Counter()

    # First pass over clean CSV
    with clean_csv_path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            role = comparison_role(row)
            if role is None:
                continue
            is_fintech = role == 'fintech'
            lei = row['lei']
            lender_name = row['lender_name']
            rs = float(row['rate_spread_num']) if row['elig_rate_spread'] == '1' else None
            ir = float(row['interest_rate_num']) if row['elig_interest_rate'] == '1' else None
            oc = float(row['orig_charge_pct']) if row['elig_orig_pct'] == '1' else None
            baseline = in_baseline(row)

            # Alternative comparator: Fintech vs non-fintech nonbanks (same baseline filters)
            if baseline and role in ('fintech', 'nonbank'):
                rob_vs_nonbank.add(is_fintech, lei, rs, ir, oc)
                for dim, groups in nonbank_dims.items():
                    if row[dim] in groups:
                        groups[row[dim]].add(is_fintech, lei, rs, ir, oc)
            if role == 'nonbank':
                continue

            if is_fintech:
                fintech_volume[lei] += 1

            if baseline:
                national_ctrl.add(is_fintech, lei, rs, ir, oc)
                if lei != TWENTY_FIRST_LEI:
                    rob_base_no_21st.add(is_fintech, lei, rs, ir, oc)
                if lei != ROCKET_LEI:
                    rob_base_no_rocket.add(is_fintech, lei, rs, ir, oc)
                if rs is not None:
                    (base_rs_f if is_fintech else base_rs_b)[lei].append(rs)
                if is_fintech:
                    lbb = base_lenders.setdefault(lei, {
                        'lei': lei, 'lender_name': lender_name,
                        'rs': array('d'), 'ir': array('d'), 'oc': array('d'), 'loans': 0,
                    })
                    lbb['loans'] += 1
                    for key, val in (('rs', rs), ('ir', ir), ('oc', oc)):
                        if val is not None:
                            lbb[key].append(val)

            national_all.add(is_fintech, lei, rs, ir, oc)

            if rs is not None:
                if is_fintech:
                    lender_rs_f[lei].append(rs)
                else:
                    lender_rs_b[lei].append(rs)

            if is_fintech:
                lb = lender_buckets.setdefault(lei, {
                    'lei': lei, 'lender_name': lender_name,
                    'rs': array('d'), 'ir': array('d'), 'oc': array('d'), 'loans': 0,
                })
                lb['loans'] += 1
                if rs is not None:
                    lb['rs'].append(rs)
                if ir is not None:
                    lb['ir'].append(ir)
                if oc is not None:
                    lb['oc'].append(oc)

            # Robustness slices
            if lei != ROCKET_LEI:
                rob_no_rocket.add(is_fintech, lei, rs, ir, oc)
            if not is_fintech or lender_name not in {'ROCKET MORTGAGE', 'GUARANTEED RATE, INC.'}:
                rob_no_top2.add(is_fintech, lei, rs, ir, oc)
            if lender_name != '21ST MORTGAGE':
                rob_no_21st.add(is_fintech, lei, rs, ir, oc)
            if row['construction_method'].strip() == '1' and row['total_units'].strip() == '1':
                rob_site_built_1unit.add(is_fintech, lei, rs, ir, oc)
            if not row['review_flags']:
                rob_no_flags.add(is_fintech, lei, rs, ir, oc)
            if row['elig_all_pricing'] == '1':
                rob_common.add(is_fintech, lei, rs, ir, oc)

            # Single-dimension borrower groups (require rate_spread + that dimension's variable)
            for dim in ('dti_group', 'cltv_group', 'income_group', 'loan_amount_group'):
                val = row[dim]
                if val in by_dim[dim]:
                    by_dim[dim][val].add(is_fintech, lei, rs, ir, oc)

            # State
            st = row['state_code'].strip()
            if row['elig_state'] == '1' and st:
                by_state[st].add(is_fintech, lei, rs, ir, oc)

            # Controlled sample (DTI, CLTV, Income, Loan Amount, Rate Spread all valid)
            if row['elig_controlled'] == '1':
                dti_g = row['dti_group']
                cltv_g = row['cltv_group']
                inc_g = row['income_group']
                loan_g = row['loan_amount_group']
                ctrl_incl_dti50.add(is_fintech, lei, rs, ir, oc)
                if lei != ROCKET_LEI:
                    rob_ctrl_no_rocket.add(is_fintech, lei, rs, ir, oc)
                if (dti_g, cltv_g) in grid_dti_cltv:
                    grid_dti_cltv[dti_g, cltv_g].add(is_fintech, lei, rs, ir, oc)
                    if lei != ROCKET_LEI:
                        grid_no_rocket[dti_g, cltv_g].add(is_fintech, lei, rs, ir, oc)
                if dti_g and cltv_g and inc_g and loan_g:
                    four_way[dti_g, cltv_g, inc_g, loan_g].add(is_fintech, lei, rs, ir, oc)

    # 1. National & Robustness summaries
    nat_all_sum = national_all.summarize({'slice': 'National — all eligible loans'})
    nat_all_rs_f = sorted(national_all.rs_f)
    nat_all_rs_b = sorted(national_all.rs_b)
    ci_lo, ci_hi = bootstrap_ci_bps(nat_all_rs_f, nat_all_rs_b)
    cl_lo, cl_hi = cluster_bootstrap_ci_bps(lender_rs_f, lender_rs_b)
    nat_all_sum['order_stat_ci95_bps'] = [ci_lo, ci_hi]
    nat_all_sum['lender_cluster_ci95_bps'] = [cl_lo, cl_hi]

    nat_ctrl_sum = national_ctrl.summarize({'slice': BASELINE_LABEL})
    base_ci_lo, base_ci_hi = bootstrap_ci_bps(sorted(national_ctrl.rs_f), sorted(national_ctrl.rs_b))
    base_cl_lo, base_cl_hi = cluster_bootstrap_ci_bps(base_rs_f, base_rs_b)
    nat_ctrl_sum['order_stat_ci95_bps'] = [base_ci_lo, base_ci_hi]
    nat_ctrl_sum['lender_cluster_ci95_bps'] = [base_cl_lo, base_cl_hi]

    # Lender-level medians in the baseline (each lender weighted equally)
    fintech_lender_medians = [median(v) for v in base_rs_f.values() if len(v) >= 10]
    bank_lender_medians = [median(v) for v in base_rs_b.values() if len(v) >= 10]
    equal_lender_gap_bps = r2(100.0 * (median(fintech_lender_medians) - median(bank_lender_medians)))

    nonbank_sum = with_comparator_fields(rob_vs_nonbank.summarize({
        'slice': 'Alternative comparator: Fintech vs non-fintech nonbanks (TYPE 40/41), baseline filters',
        'comparator': 'Non-fintech nonbank',
    }))
    nonbank_segment_rows = []
    for dim, groups in nonbank_dims.items():
        for group, bucket in groups.items():
            nonbank_segment_rows.append(with_comparator_fields(bucket.summarize({
                'dimension': dim, 'group': group, 'comparator': 'Non-fintech nonbank',
            })))
    write_csv(out_dir / 'by_segment_vs_nonbank.csv', nonbank_segment_rows,
              list(dict.fromkeys(k for r in nonbank_segment_rows for k in r)))
    robustness_rows = [
        dict(nat_ctrl_sum),
        nonbank_sum,
        rob_base_no_rocket.summarize({'slice': 'Baseline excluding Rocket Mortgage (47% of Fintech loans)'}),
        rob_base_no_21st.summarize({'slice': 'Baseline excluding 21st Mortgage (manufactured-housing specialist)'}),
        ctrl_incl_dti50.summarize({'slice': 'Controlled sample incl. DTI >=50%'}),
        rob_site_built_1unit.summarize({'slice': 'Site-built 1-unit properties only (excl. manufactured & multi-unit)'}),
        rob_no_flags.summarize({'slice': 'Excluding all review-flagged loans'}),
        dict(nat_all_sum),
    ]
    for r in robustness_rows:
        r.pop('order_stat_ci95_bps', None)
        r.pop('lender_cluster_ci95_bps', None)
    rob_fields = list(dict.fromkeys(k for r in robustness_rows for k in r))
    write_csv(out_dir / 'robustness_checks.csv', robustness_rows, rob_fields)

    # 2. Single-dimension borrower groups
    single_dim_rows = []
    for dim, order in [
        ('dti_group', DTI_ORDER),
        ('cltv_group', CLTV_ORDER),
        ('income_group', INCOME_ORDER),
        ('loan_amount_group', LOAN_ORDER),
    ]:
        for bucket_name in order:
            s = by_dim[dim][bucket_name].summarize({'dimension': dim, 'group': bucket_name})
            single_dim_rows.append(s)
    write_csv(out_dir / 'by_single_dimension.csv', single_dim_rows)

    # 3. 20-cell DTI x CLTV risk grid (with Ex-Rocket check alongside)
    grid_rows = []
    for d in DTI_ORDER:
        for c in CLTV_ORDER:
            base = grid_dti_cltv[d, c].summarize({'dti_group': d, 'cltv_group': c})
            no_rk = grid_no_rocket[d, c].summarize()
            base['ex_rocket_gap_bps'] = no_rk['rate_spread_gap_bps']
            base['ex_rocket_fintech_loans'] = no_rk['fintech_loans_rs']
            grid_rows.append(base)
    write_csv(out_dir / 'by_dti_cltv_grid.csv', grid_rows)

    # 4. 320-cell 4-way controlled cells (DTI x CLTV x Income x Loan Amount)
    four_way_rows = []
    weighted_gap_num_f = 0.0
    weighted_gap_den_f = 0
    weighted_gap_num_b = 0.0
    weighted_gap_den_b = 0
    cells_fintech_higher = 0
    cells_bank_higher = 0
    cells_with_min25 = 0

    for d in DTI_ORDER:
        for c in CLTV_ORDER:
            for inc in INCOME_ORDER:
                for la in LOAN_ORDER:
                    b = four_way[d, c, inc, la]
                    s = b.summarize({
                        'dti_group': d, 'cltv_group': c,
                        'income_group': inc, 'loan_amount_group': la,
                    })
                    four_way_rows.append(s)
                    if s['fintech_loans_rs'] >= 25 and s['bank_loans_rs'] >= 25 and s['rate_spread_gap_bps'] is not None:
                        cells_with_min25 += 1
                        gap = s['rate_spread_gap_bps']
                        weighted_gap_num_f += gap * s['fintech_loans_rs']
                        weighted_gap_den_f += s['fintech_loans_rs']
                        weighted_gap_num_b += gap * s['bank_loans_rs']
                        weighted_gap_den_b += s['bank_loans_rs']
                        if gap > 0:
                            cells_fintech_higher += 1
                        elif gap < 0:
                            cells_bank_higher += 1
    write_csv(out_dir / 'by_four_way_cells.csv', four_way_rows)

    # 5. State-level comparison
    state_rows = []
    for st, b in sorted(by_state.items()):
        state_rows.append(b.summarize({'state_code': st}))
    state_rows.sort(key=lambda r: -(r['fintech_loans_rs'] + r['bank_loans_rs']))
    write_csv(out_dir / 'by_state.csv', state_rows)

    # 6. Individual Fintech lenders vs National Bank Median
    bank_nat_rs = nat_ctrl_sum['bank_median_rate_spread']
    bank_nat_ir = nat_ctrl_sum['bank_median_interest_rate']
    bank_nat_oc = nat_ctrl_sum['bank_median_orig_pct']
    fintech_lender_rows = []
    for lei, lb in base_lenders.items():
        rs_s = sorted(lb['rs'])
        med_rs = quantile(rs_s, 0.5)
        med_ir = median(lb['ir'])
        med_oc = median(lb['oc'])
        fintech_lender_rows.append({
            'lei': lei,
            'lender_name': lb['lender_name'],
            'total_loans': lb['loans'],
            'share_of_fintech_loans_pct': r2(100.0 * lb['loans'] / national_ctrl.loans_f),
            'loans_with_rate_spread': len(rs_s),
            'median_rate_spread': r4(med_rs),
            'gap_vs_bank_median_bps': r2(100.0 * (med_rs - bank_nat_rs)) if med_rs is not None else None,
            'rs_p25': r4(quantile(rs_s, 0.25)),
            'rs_p75': r4(quantile(rs_s, 0.75)),
            'median_interest_rate': r4(med_ir),
            'ir_gap_vs_bank_bps': r2(100.0 * (med_ir - bank_nat_ir)) if med_ir is not None else None,
            'median_orig_pct': r4(med_oc),
            'orig_pct_gap_vs_bank_bps': r2(100.0 * (med_oc - bank_nat_oc)) if med_oc is not None else None,
        })
    fintech_lender_rows.sort(key=lambda r: -r['total_loans'])
    write_csv(out_dir / 'by_fintech_lender.csv', fintech_lender_rows)

    cov_grid = [r for r in grid_rows if r['coverage_ok']]
    cov_grid_fintech_higher = [r for r in cov_grid if r['rate_spread_gap_bps'] >= MEANINGFUL_GAP_BPS]
    std_grid = [r for r in grid_rows if r['dti_group'] in DTI_STANDARD_ORDER]
    std_grid_higher = [r for r in std_grid if r['coverage_ok'] and r['rate_spread_gap_bps'] >= MEANINGFUL_GAP_BPS]
    fintech_lenders_above_bank = sum(1 for r in fintech_lender_rows if (r['gap_vs_bank_median_bps'] or 0) > 0)
    fintech_lenders_above_5bps = sum(1 for r in fintech_lender_rows
                                     if (r['gap_vs_bank_median_bps'] or 0) >= MEANINGFUL_GAP_BPS)

    summary = {
        'generated_at_utc': utc_now(),
        'thresholds': {
            'min_loans_per_side': MIN_LOANS_PER_SIDE,
            'min_lenders_fintech': MIN_LENDERS_FINTECH,
            'min_lenders_bank': MIN_LENDERS_BANK,
            'meaningful_gap_bps': MEANINGFUL_GAP_BPS,
        },
        'bins': {
            'dti_group': DTI_ORDER,
            'cltv_group': CLTV_ORDER,
            'income_group': INCOME_ORDER,
            'loan_amount_group': LOAN_ORDER,
        },
        'headline_metrics': {
            'national_unadjusted': nat_all_sum,
            'national_controlled_sample': nat_ctrl_sum,
            'national_vs_nonbank': nonbank_sum,
            'order_stat_ci95_bps': [ci_lo, ci_hi],
            'lender_cluster_ci95_bps': [cl_lo, cl_hi],
            'baseline_order_stat_ci95_bps': [base_ci_lo, base_ci_hi],
            'baseline_lender_cluster_ci95_bps': [base_cl_lo, base_cl_hi],
            'equal_weighted_lender_median_gap_bps': equal_lender_gap_bps,
            'fintech_lenders_above_bank_median': f'{fintech_lenders_above_bank} of {len(fintech_lender_rows)}',
            'fintech_lenders_above_bank_5bps': f'{fintech_lenders_above_5bps} of {len(fintech_lender_rows)}',
            'standard_dti_cltv_cells_fintech_higher_5bps': f'{len(std_grid_higher)} of {len(std_grid)}',
            'dti_cltv_cells_total': len(grid_rows),
            'dti_cltv_cells_sufficient_coverage': len(cov_grid),
            'dti_cltv_cells_fintech_higher_5bps': len(cov_grid_fintech_higher),
            'four_way_cells_min25_per_side': cells_with_min25,
            'four_way_cells_fintech_higher': cells_fintech_higher,
            'four_way_cells_bank_higher': cells_bank_higher,
            'four_way_reweighted_gap_bps_fintech_weights': r2(weighted_gap_num_f / weighted_gap_den_f) if weighted_gap_den_f else None,
            'four_way_reweighted_gap_bps_bank_weights': r2(weighted_gap_num_b / weighted_gap_den_b) if weighted_gap_den_b else None,
        },
        'robustness_checks': robustness_rows,
        'nonbank_by_segment': nonbank_segment_rows,
        'nonbank_priority': nonbank_priority(nonbank_segment_rows),
        'single_dimension': single_dim_rows,
        'dti_cltv_grid': grid_rows,
        'fintech_lenders': fintech_lender_rows,
        'top_states': state_rows[:15],
    }
    tmp = out_dir / 'pricing_summary.json.tmp'
    tmp.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    os.replace(tmp, out_dir / 'pricing_summary.json')
    write_markdown_report(out_dir / 'analysis_report.md', summary, state_rows)
    return summary


SEGMENT_LABELS = {
    ('dti_group', '<30%'): 'DTI <30%', ('dti_group', '30%-<36%'): 'DTI 30-36%',
    ('dti_group', '36%-43%'): 'DTI 36-43%', ('dti_group', '44%-49%'): 'DTI 44-49%',
    ('cltv_group', '<=80%'): 'CLTV ≤80% (20%+ down)', ('cltv_group', '80.01%-90%'): 'CLTV 80-90%',
    ('cltv_group', '90.01%-95%'): 'CLTV 90-95%', ('cltv_group', '>95%'): 'CLTV >95% (under 5% down)',
    ('income_group', '<=$75k'): 'income ≤$75k', ('income_group', '$75k-$125k'): 'income $75k-$125k',
    ('income_group', '$125k-$200k'): 'income $125k-$200k', ('income_group', '>$200k'): 'income >$200k',
    ('loan_amount_group', '<=$200k'): 'loans ≤$200k', ('loan_amount_group', '$200k-$350k'): 'loans $200k-$350k',
    ('loan_amount_group', '$350k-$500k'): 'loans $350k-$500k', ('loan_amount_group', '>$500k'): 'loans >$500k',
}
PRIORITY_FEE_GAP_BPS = 10.0


def nonbank_priority(segment_rows, top=2):
    """Pick the first review segments from the Fintech-vs-nonbank comparison.

    Rule (stated, not tuned): segments with sufficient coverage where Fintech's median rate
    spread is >= +5 bps above nonbank peers; if none, segments where the fee gap is
    >= +10 bps; if none, the review starts with origination fees overall.
    """
    ok = [r for r in segment_rows if r['coverage_ok']]

    def pick(key, threshold):
        hits = [r for r in ok if r[key] is not None and r[key] >= threshold]
        hits.sort(key=lambda r: -r[key])
        return [{'dimension': r['dimension'], 'group': r['group'],
                 'label': SEGMENT_LABELS.get((r['dimension'], r['group']), r['group']),
                 'rate_spread_gap_bps': r['rate_spread_gap_bps'], 'orig_pct_gap_bps': r['orig_pct_gap_bps']}
                for r in hits[:top]]

    segments = pick('rate_spread_gap_bps', MEANINGFUL_GAP_BPS)
    if segments:
        return {'basis': 'rate_spread', 'segments': segments}
    segments = pick('orig_pct_gap_bps', PRIORITY_FEE_GAP_BPS)
    if segments:
        return {'basis': 'fees', 'segments': segments}
    return {'basis': 'overall_fees', 'segments': []}


COMPARATOR_FIELD_MAP = {
    'bank_loans_rs': 'comparator_loans_rs', 'bank_lenders': 'comparator_lenders',
    'bank_median_rate_spread': 'comparator_median_rate_spread',
    'bank_rs_p25': 'comparator_rs_p25', 'bank_rs_p75': 'comparator_rs_p75',
    'bank_median_interest_rate': 'comparator_median_interest_rate',
    'bank_median_orig_pct': 'comparator_median_orig_pct',
}


def with_comparator_fields(summary):
    """Label a non-bank comparison clearly: Bucket stores the comparator in bank_* fields.

    The bank_* keys are kept for compatibility; comparator_* copies say what they really hold.
    """
    out = dict(summary)
    for src, dst in COMPARATOR_FIELD_MAP.items():
        out[dst] = summary.get(src)
    out['field_note'] = 'In this row bank_* fields hold the non-fintech nonbank comparator; see comparator_* fields.'
    return out


def write_markdown_report(path, summary, state_rows):
    def p3(v):
        return 'n/a' if v is None else f'{v:.3f}%'

    def b1(v):
        return 'n/a' if v is None else f'{v:+.1f}'

    hm = summary['headline_metrics']
    nat = hm['national_unadjusted']
    base = hm['national_controlled_sample']
    nb = hm['national_vs_nonbank']
    def ci(pair):
        return f"`{pair[0]:+.1f}` to `{pair[1]:+.1f}` bps" if pair and None not in pair else 'n/a'
    lines = [
        '# Project Audible — Pricing Analysis Report (2025 HMDA)',
        '',
        f"Generated: {summary['generated_at_utc']} by `analyze_pricing.py`.",
        '',
        '## 1. Headline Finding & AFC Decision Implication',
        '',
        f"- **Controlled baseline (headline; same sample as the dashboard)** — valid DTI, CLTV, income and loan amount, "
        f"DTI <50%: Fintech median rate spread **{p3(base['fintech_median_rate_spread'])}** "
        f"(n = {base['fintech_loans_rs']:,}; {base['fintech_lenders']} lenders) vs. Bank **{p3(base['bank_median_rate_spread'])}** "
        f"(n = {base['bank_loans_rs']:,}; {base['bank_lenders']} lenders) -> **{b1(base['rate_spread_gap_bps'])} bps** "
        f"(order-statistic 95% CI: {ci(hm['baseline_order_stat_ci95_bps'])}; "
        f"lender-clustered 95% CI: {ci(hm['baseline_lender_cluster_ci95_bps'])}).",
        f"- **Unadjusted full sample** (robustness): **{b1(nat['rate_spread_gap_bps'])} bps** "
        f"(n = {nat['fintech_loans_rs']:,} vs. {nat['bank_loans_rs']:,}; lender-clustered 95% CI: {ci(hm['lender_cluster_ci95_bps'])}).",
        f"- **Fintech effect or nonbank effect?** Against non-fintech independent mortgage banks (Philadelphia Fed TYPE 40/41, "
        f"{nb['bank_lenders']} lenders, n = {nb['bank_loans_rs']:,}) under the same baseline filters, the Fintech gap is "
        f"**{b1(nb['rate_spread_gap_bps'])} bps** (fee gap {b1(nb['orig_pct_gap_bps'])} bps).",
        f"- **Composition-Controlled 4-Way Cell Average Gap** (across {hm['four_way_cells_min25_per_side']} "
        f"DTI x CLTV x Income x Loan Amount cells with >=25 loans per side): "
        f"**{b1(hm['four_way_reweighted_gap_bps_fintech_weights'])} bps** (Fintech weights) / "
        f"**{b1(hm['four_way_reweighted_gap_bps_bank_weights'])} bps** (Bank weights). "
        f"Fintech median spread is higher in **{hm['four_way_cells_fintech_higher']} of {hm['four_way_cells_min25_per_side']}** cells.",
        f"- **DTI x CLTV Risk Matrix**: Fintech pricing is >= +5 bps higher in **{hm['standard_dti_cltv_cells_fintech_higher_5bps']}** "
        f"standard (DTI <50%) cells. Including the thin DTI >=50% row, {hm['dti_cltv_cells_sufficient_coverage']} of "
        f"{hm['dti_cltv_cells_total']} cells meet coverage (>=100 loans/side, >=3 Fintech lenders, >=10 Bank lenders).",
        f"- **Persistence Across Lenders (baseline)**: **{hm['fintech_lenders_above_bank_median']}** NYU Fintech lenders have a "
        f"median rate spread above the Bank median; **{hm['fintech_lenders_above_bank_5bps']}** are at least 5 bps above. "
        f"Equal-weighted lender-median gap is **{b1(hm['equal_weighted_lender_median_gap_bps'])} bps**.",
        f"- **Supporting Measures (baseline)**: Fintech median interest rate is **{p3(base['fintech_median_interest_rate'])}** vs. "
        f"**{p3(base['bank_median_interest_rate'])}** at banks (**{b1(base['interest_rate_gap_bps'])} bps**), and "
        f"Fintech median origination charges are **{p3(base['fintech_median_orig_pct'])}** of loan amount vs. "
        f"**{p3(base['bank_median_orig_pct'])}** at banks (**{b1(base['orig_pct_gap_bps'])} bps**).",
        '',
        '## 2. Robustness Checks',
        '',
        '| Specification | Fintech Loans | Comparator Loans | Fintech Med Spread | Comparator Med Spread | Spread Gap (bps) | Rate Gap (bps) | Orig Fee Gap (bps) |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for r in summary['robustness_checks']:
        lines.append(
            f"| {r['slice']} | {r['fintech_loans_rs']:,} | {r['bank_loans_rs']:,} | "
            f"{p3(r['fintech_median_rate_spread'])} | {p3(r['bank_median_rate_spread'])} | "
            f"**{b1(r['rate_spread_gap_bps'])}** | {b1(r['interest_rate_gap_bps'])} | {b1(r['orig_pct_gap_bps'])} |"
        )
    lines += [
        '',
        '### 2a. Fintech vs. Non-Fintech Nonbanks by Borrower Group (baseline filters)',
        '',
        '| Dimension | Group | Fintech Loans | Nonbank Loans | Fintech Med Spread | Nonbank Med Spread | Spread Gap (bps) | Rate Gap (bps) | Orig Fee Gap (bps) | Status |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    for r in summary.get('nonbank_by_segment', []):
        lines.append(
            f"| `{r['dimension']}` | {r['group']} | {r['fintech_loans_rs']:,} | {r['comparator_loans_rs']:,} | "
            f"{p3(r['fintech_median_rate_spread'])} | {p3(r['comparator_median_rate_spread'])} | "
            f"**{b1(r['rate_spread_gap_bps'])}** | {b1(r['interest_rate_gap_bps'])} | {b1(r['orig_pct_gap_bps'])} | {r['status']} |"
        )
    lines += [
        '',
        '## 3. Single-Dimension Borrower Group Comparisons',
        '',
        '| Dimension | Group | Fintech Loans | Bank Loans | Fintech Med Spread | Bank Med Spread | Spread Gap (bps) | Rate Gap (bps) | Orig Fee Gap (bps) | Status |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    for r in summary['single_dimension']:
        lines.append(
            f"| `{r['dimension']}` | {r['group']} | {r['fintech_loans_rs']:,} | {r['bank_loans_rs']:,} | "
            f"{p3(r['fintech_median_rate_spread'])} | {p3(r['bank_median_rate_spread'])} | "
            f"**{b1(r['rate_spread_gap_bps'])}** | {b1(r['interest_rate_gap_bps'])} | "
            f"{b1(r['orig_pct_gap_bps'])} | {r['status']} |"
        )
    lines += [
        '',
        '## 4. Two-Way Risk Matrix: DTI x CLTV (20 Cells)',
        '',
        '| DTI Group | CLTV Group | Fintech Loans | Bank Loans | Fintech Med Spread | Bank Med Spread | Gap (bps) | Ex-Rocket Gap (bps) | Orig Fee Gap (bps) | Status |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    for r in summary['dti_cltv_grid']:
        ex_rk = f"{b1(r['ex_rocket_gap_bps'])}" if r['ex_rocket_gap_bps'] is not None else 'NA'
        lines.append(
            f"| {r['dti_group']} | {r['cltv_group']} | {r['fintech_loans_rs']:,} | {r['bank_loans_rs']:,} | "
            f"{p3(r['fintech_median_rate_spread'])} | {p3(r['bank_median_rate_spread'])} | "
            f"**{b1(r['rate_spread_gap_bps'])}** | {ex_rk} | "
            f"{b1(r['orig_pct_gap_bps'])} | {r['status']} |"
        )
    lines += [
        '',
        '## 5. Individual Fintech Lenders vs. Bank Benchmark',
        '',
        '| Fintech Lender | Loans | Share (%) | Med Rate Spread | Gap vs Bank Med (bps) | Med Interest Rate | Med Orig Charges (% Loan) |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for r in summary['fintech_lenders']:
        lines.append(
            f"| {r['lender_name']} | {r['total_loans']:,} | {r['share_of_fintech_loans_pct']:.1f}% | "
            f"{p3(r['median_rate_spread'])} | **{b1(r['gap_vs_bank_median_bps'])}** | "
            f"{p3(r['median_interest_rate'])} | {p3(r['median_orig_pct'])} |"
        )
    lines += [
        '',
        '## 6. Top 15 Property States by Sample Volume ( plus NC)',
        '',
        '| State | Fintech Loans | Bank Loans | Fintech Med Spread | Bank Med Spread | Gap (bps) | Orig Fee Gap (bps) | Status |',
        '|---|---:|---:|---:|---:|---:|---:|---|',
    ]
    for r in state_rows[:15]:
        lines.append(
            f"| {r['state_code']} | {r['fintech_loans_rs']:,} | {r['bank_loans_rs']:,} | "
            f"{p3(r['fintech_median_rate_spread'])} | {p3(r['bank_median_rate_spread'])} | "
            f"**{b1(r['rate_spread_gap_bps'])}** | {b1(r['orig_pct_gap_bps'])} | {r['status']} |"
        )
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--year', type=int, default=2025)
    parser.add_argument('--data-dir', type=Path,
                        help='Folder containing mortgages_<year>_clean.csv')
    args = parser.parse_args(argv)
    data_dir = args.data_dir or Path(__file__).resolve().parent / 'data' / str(args.year)
    clean_csv = data_dir / f'mortgages_{args.year}_clean.csv'
    out_dir = data_dir / 'analysis'
    if not clean_csv.exists():
        raise SystemExit(f'Missing {clean_csv}. Run clean_mortgages.py first.')
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f'Analyzing {clean_csv.name} ...')
    summary = analyze(clean_csv, out_dir)
    hm = summary['headline_metrics']
    base = hm['national_controlled_sample']
    nb = hm['national_vs_nonbank']
    print(f"Done. Baseline rate-spread gap: {base['rate_spread_gap_bps']:+.2f} bps "
          f"(Fintech {base['fintech_median_rate_spread']:.3f}% vs Bank {base['bank_median_rate_spread']:.3f}%); "
          f"vs non-fintech nonbanks: {nb['rate_spread_gap_bps']:+.2f} bps.")
    print(f'Reports saved in {out_dir}')


if __name__ == '__main__':
    main()
