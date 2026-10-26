#!/usr/bin/env python3
"""Unit tests for analyze_pricing.py."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import analyze_pricing as ap

FIELDS = ['lei', 'lender_name', 'lender_type', 'institution_type_code', 'in_main_comparison',
          'rate_spread_num', 'interest_rate_num', 'orig_charge_pct', 'elig_rate_spread',
          'elig_interest_rate', 'elig_orig_pct', 'elig_all_pricing', 'elig_controlled', 'elig_state',
          'dti_group', 'cltv_group', 'income_group', 'loan_amount_group', 'state_code',
          'construction_method', 'total_units', 'review_flags']


def loan(lei, group, type_code, rs, ir=6.5, oc=0.8, dti='36%-43%', cltv='<=80%'):
    return {
        'lei': lei, 'lender_name': lei, 'lender_type': group, 'institution_type_code': type_code,
        'in_main_comparison': '1' if group in ('Fintech', 'Bank comparator') else '0',
        'rate_spread_num': str(rs), 'interest_rate_num': str(ir), 'orig_charge_pct': str(oc),
        'elig_rate_spread': '1', 'elig_interest_rate': '1', 'elig_orig_pct': '1',
        'elig_all_pricing': '1', 'elig_controlled': '1', 'elig_state': '1',
        'dti_group': dti, 'cltv_group': cltv, 'income_group': '$75k-$125k',
        'loan_amount_group': '$200k-$350k', 'state_code': 'NC',
        'construction_method': '1', 'total_units': '1', 'review_flags': '',
    }


class TestAnalyzePricing(unittest.TestCase):
    def test_bucket_median_and_gap_bps_and_coverage(self):
        b = ap.Bucket()
        # Add 120 Fintech loans across 3 lenders with rate_spread 0.30, ir 6.5, oc 1.0
        for i in range(120):
            b.add(True, f'F_{i % 3}', 0.30, 6.50, 1.00)
        # Add 150 Bank loans across 12 lenders with rate_spread 0.05, ir 6.25, oc 0.60
        for i in range(150):
            b.add(False, f'B_{i % 12}', 0.05, 6.25, 0.60)

        s = b.summarize({'slice': 'test'})
        self.assertTrue(s['coverage_ok'])
        self.assertEqual(s['status'], 'Fintech higher (+5 bps or more)')
        self.assertAlmostEqual(s['fintech_median_rate_spread'], 0.30)
        self.assertAlmostEqual(s['bank_median_rate_spread'], 0.05)
        self.assertAlmostEqual(s['rate_spread_gap_bps'], 25.0)
        self.assertAlmostEqual(s['interest_rate_gap_bps'], 25.0)
        self.assertAlmostEqual(s['orig_pct_gap_bps'], 40.0)

    def test_insufficient_coverage_flagged(self):
        b = ap.Bucket()
        for i in range(50):
            b.add(True, 'F_ONLY_ONE', 0.40, 6.50, 1.00)
        for i in range(200):
            b.add(False, f'B_{i % 15}', 0.10, 6.25, 0.50)
        s = b.summarize()
        self.assertFalse(s['coverage_ok'])
        self.assertEqual(s['status'], 'Insufficient coverage')


    def test_comparison_roles(self):
        self.assertEqual(ap.comparison_role({'lender_type': 'Fintech'}), 'fintech')
        self.assertEqual(ap.comparison_role({'lender_type': 'Bank comparator'}), 'bank')
        self.assertEqual(ap.comparison_role({'lender_type': 'Other lender', 'institution_type_code': '40'}), 'nonbank')
        self.assertEqual(ap.comparison_role({'lender_type': 'Other lender', 'institution_type_code': '41'}), 'nonbank')
        # bank/thrift subsidiaries and credit unions are not the nonbank comparator
        self.assertIsNone(ap.comparison_role({'lender_type': 'Other lender', 'institution_type_code': '11'}))
        self.assertIsNone(ap.comparison_role({'lender_type': 'Credit union', 'institution_type_code': '30'}))

    def test_baseline_excludes_dti_50_and_nonbank_check_uses_same_filters(self):
        rows = []
        rows += [loan(f'F{i % 3}', 'Fintech', '40', 0.30) for i in range(150)]
        rows += [loan(f'B{i % 12}', 'Bank comparator', '10', 0.05) for i in range(200)]
        rows += [loan(f'N{i % 10}', 'Other lender', '40', 0.20) for i in range(200)]
        rows += [loan(f'C{i % 10}', 'Credit union', '30', -1.00) for i in range(200)]
        # High-DTI Fintech loans: in the incl.-DTI>=50% robustness row, never in the baseline.
        rows += [loan('F0', 'Fintech', '40', 3.00, dti='>=50%') for _ in range(400)]
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'clean.csv'
            with src.open('w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
                w.writerows(rows)
            summary = ap.analyze(src, Path(tmp))
            hm = summary['headline_metrics']
            base = hm['national_controlled_sample']
            self.assertEqual(base['slice'], ap.BASELINE_LABEL)
            self.assertEqual(base['fintech_loans_rs'], 150)
            self.assertAlmostEqual(base['rate_spread_gap_bps'], 25.0)
            nb = hm['national_vs_nonbank']
            self.assertEqual(nb['bank_loans_rs'], 200)
            self.assertEqual(nb['bank_lenders'], 10)
            self.assertAlmostEqual(nb['rate_spread_gap_bps'], 10.0)
            slices = {r['slice']: r for r in summary['robustness_checks']}
            self.assertEqual(slices['Controlled sample incl. DTI >=50%']['fintech_loans_rs'], 550)
            self.assertEqual(hm['fintech_lenders_above_bank_median'], '3 of 3')
            self.assertTrue((Path(tmp) / 'analysis_report.md').read_text().count('nonbank') >= 1)
            with (Path(tmp) / 'robustness_checks.csv').open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), len(summary['robustness_checks']))
            json.loads((Path(tmp) / 'pricing_summary.json').read_text())


if __name__ == '__main__':
    unittest.main()
