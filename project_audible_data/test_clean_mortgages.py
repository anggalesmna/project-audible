#!/usr/bin/env python3
"""Unit tests for clean_mortgages.py."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import clean_mortgages as cm

BASE_COLS = [
    'activity_year', 'lei', 'state_code', 'county_code', 'rate_spread',
    'interest_rate', 'origination_charges', 'discount_points', 'lender_credits',
    'total_loan_costs', 'total_points_and_fees', 'loan_amount',
    'debt_to_income_ratio', 'combined_loan_to_value_ratio', 'income',
    'action_taken', 'loan_type', 'loan_purpose', 'lien_status', 'occupancy_type',
    'conforming_loan_limit', 'loan_term', 'intro_rate_period', 'total_units',
    'construction_method', 'reverse_mortgage', 'open_end_line_of_credit',
    'business_or_commercial_purpose', 'submission_of_application',
    'initially_payable_to_institution', 'lender_name', 'agency_code',
    'lender_type', 'nyu_fintech_flag', 'nyu_classification_year',
    'institution_type_code', 'institution_type',
]


def make_row(**overrides):
    row = {
        'activity_year': '2025',
        'lei': 'LEI_FINTECH_1',
        'state_code': 'NC',
        'county_code': '37183',
        'rate_spread': '0.25',
        'interest_rate': '6.5',
        'origination_charges': '1500',
        'discount_points': '',
        'lender_credits': '',
        'total_loan_costs': '4500',
        'total_points_and_fees': 'NA',
        'loan_amount': '300000',
        'debt_to_income_ratio': '38',
        'combined_loan_to_value_ratio': '80',
        'income': '120',
        'action_taken': '1',
        'loan_type': '1',
        'loan_purpose': '1',
        'lien_status': '1',
        'occupancy_type': '1',
        'conforming_loan_limit': 'C',
        'loan_term': '360',
        'intro_rate_period': 'NA',
        'total_units': '1',
        'construction_method': '1',
        'reverse_mortgage': '2',
        'open_end_line_of_credit': '2',
        'business_or_commercial_purpose': '2',
        'submission_of_application': '1',
        'initially_payable_to_institution': '1',
        'lender_name': 'Sample Fintech',
        'agency_code': '7',
        'lender_type': 'Fintech',
        'nyu_fintech_flag': '1',
        'nyu_classification_year': '2017',
        'institution_type_code': '40',
        'institution_type': 'Independent mortgage bank',
    }
    row.update(overrides)
    return row


class TestCleanMortgages(unittest.TestCase):
    def test_valid_row_and_origination_ratio(self):
        status, new, flags = cm.clean_row(make_row(debt_to_income_ratio='40'))
        self.assertTrue(all(v == 'valid' for v in status.values()))
        self.assertEqual(new['loan_amount_num'], '300000')
        self.assertEqual(new['orig_charge_pct'], '0.5')
        self.assertEqual(new['dti_category'], '40')
        self.assertEqual(new['dti_num'], '40')
        self.assertEqual(new['dti_group'], '36%-43%')
        self.assertEqual(new['cltv_group'], '<=80%')
        self.assertEqual(new['income_group'], '$75k-$125k')
        self.assertEqual(new['loan_amount_group'], '$200k-$350k')
        self.assertEqual(flags, [])
        for k in cm.INDICATORS:
            self.assertEqual(new[k], '1')

    def test_dti_ranges_are_valid_categories(self):
        status, new, _ = cm.clean_row(make_row(debt_to_income_ratio='20%-<30%'))
        self.assertEqual(status['debt_to_income_ratio'], 'valid')
        self.assertEqual(new['dti_category'], '20%-<30%')
        self.assertEqual(new['dti_num'], '')
        self.assertEqual(new['elig_controlled'], '1')

    def test_per_indicator_eligibility_and_zero_origination_charges(self):
        # Missing origination_charges should NOT exclude from rate_spread
        status, new, _ = cm.clean_row(make_row(origination_charges='NA'))
        self.assertEqual(status['origination_charges'], 'na')
        self.assertEqual(new['elig_rate_spread'], '1')
        self.assertEqual(new['elig_orig_pct'], '0')
        self.assertEqual(new['elig_all_pricing'], '0')

        # Zero origination_charges IS valid
        status0, new0, _ = cm.clean_row(make_row(origination_charges='0'))
        self.assertEqual(status0['origination_charges'], 'valid')
        self.assertEqual(new0['orig_charge_pct'], '0')
        self.assertEqual(new0['elig_orig_pct'], '1')

    def test_impossible_vs_unusual_values(self):
        # Impossible rate_spread (< -10) -> invalid; zero interest_rate -> invalid; zero income -> invalid
        status, new, flags = cm.clean_row(make_row(
            rate_spread='-508.0', interest_rate='0', income='0',
        ))
        self.assertEqual(status['rate_spread'], 'invalid')
        self.assertEqual(status['interest_rate'], 'invalid')
        self.assertEqual(status['income'], 'invalid')
        self.assertEqual(new['elig_rate_spread'], '0')
        self.assertEqual(new['elig_interest_rate'], '0')
        self.assertEqual(new['elig_controlled'], '0')
        self.assertIn('IR_ZERO_OR_NEGATIVE', flags)
        self.assertIn('INCOME_ZERO_OR_NEGATIVE', flags)

        # Unusual but possible values stay eligible and get review flags
        status2, new2, flags2 = cm.clean_row(make_row(
            rate_spread='-3.5', origination_charges='18000', loan_amount='300000',
        ))
        self.assertEqual(status2['rate_spread'], 'valid')
        self.assertEqual(new2['elig_rate_spread'], '1')
        self.assertIn('RS_UNUSUAL', flags2)
        self.assertIn('ORIG_PCT_GT5', flags2)

    def test_end_to_end_pipeline_preserves_rows_and_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            src = data_dir / 'mortgages_2025_classified.csv'
            rows = [
                make_row(lei='F1', lender_type='Fintech', rate_spread='0.40'),
                make_row(lei='B1', lender_name='Bank One', lender_type='Bank comparator',
                         nyu_fintech_flag='0', institution_type_code='10',
                         rate_spread='Exempt', origination_charges='0'),
                make_row(lei='C1', lender_name='CU One', lender_type='Credit union',
                         nyu_fintech_flag='0', institution_type_code='30',
                         debt_to_income_ratio='NA'),
            ]
            with src.open('w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=BASE_COLS)
                w.writeheader()
                w.writerows(rows)

            cm.main(['--year', '2025', '--data-dir', str(data_dir)])

            clean_path = data_dir / 'mortgages_2025_clean.csv'
            self.assertTrue(clean_path.exists())
            with clean_path.open(newline='', encoding='utf-8') as f:
                out_rows = list(csv.DictReader(f))
            self.assertEqual(len(out_rows), 3)
            # Original columns untouched
            for orig, out in zip(rows, out_rows):
                for col in BASE_COLS:
                    self.assertEqual(orig[col], out[col])

            summary = json.loads((data_dir / 'data_quality' / 'cleaning_summary.json').read_text())
            self.assertEqual(summary['loans_by_group']['All loans'], 3)
            self.assertEqual(summary['eligible_loans']['elig_rate_spread']['Fintech'], 1)
            self.assertEqual(summary['eligible_loans']['elig_rate_spread']['Bank comparator'], 0)
            self.assertEqual(summary['eligible_loans']['elig_orig_pct']['Bank comparator'], 1)


if __name__ == '__main__':
    unittest.main()
