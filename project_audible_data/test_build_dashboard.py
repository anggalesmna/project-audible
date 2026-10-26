#!/usr/bin/env python3
"""Unit tests for build_dashboard.compute_slices."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import build_dashboard as bd
from test_analyze_pricing import FIELDS, loan


class TestComputeSlices(unittest.TestCase):
    def test_baseline_nonbank_row_and_lender_stats(self):
        rows = []
        rows += [loan(f'F{i % 4}', 'Fintech', '40', 0.30) for i in range(160)]
        rows += [loan(f'B{i % 12}', 'Bank comparator', '10', 0.05) for i in range(240)]
        rows += [loan(f'N{i % 10}', 'Other lender', '41', 0.22) for i in range(200)]
        rows += [loan('F0', 'Fintech', '40', 3.00, dti='>=50%') for _ in range(50)]
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'clean.csv'
            with src.open('w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
                w.writerows(rows)
            out = bd.compute_slices(src)

        rob = {r['slice']: r for r in out['robustness_checks']}
        base = out['robustness_checks'][0]
        self.assertEqual(base['fintech_loans_rs'], 160)  # DTI >=50% excluded
        self.assertAlmostEqual(base['rate_spread_gap_bps'], 25.0)
        nonbank = rob['Alternative comparator: Fintech vs non-fintech nonbanks (TYPE 40/41)']
        self.assertEqual(nonbank['bank_loans_rs'], 200)
        self.assertAlmostEqual(nonbank['rate_spread_gap_bps'], 8.0)
        # Nonbank loans never leak into the Fintech-vs-Bank slices.
        self.assertEqual(out['slices']['ALL|ALL|ALL']['nb'], 240)
        self.assertEqual(out['lender_stats'], {
            'above_bank': 4, 'above_5bps': 4, 'total': 4, 'equal_weighted_gap_bps': 25.0,
        })


if __name__ == '__main__':
    unittest.main()
