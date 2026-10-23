#!/usr/bin/env python3
"""Build NYU historical lender labels and a separate, lossless HMDA analysis CSV.

Requires pandas and openpyxl for reading the two source workbooks.
Loan processing uses the standard-library CSV reader to preserve NA/Exempt/blanks.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

NYU_URL = 'https://pages.stern.nyu.edu/pschnabl/data/data_fintech.htm'
FED_URL = 'https://www.philadelphiafed.org/surveys-and-data/consumer-finance-data/home-mortgage-disclosure-act-lender-file'
FED_DOWNLOAD = 'https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/hmda/hmda-2018-present.xlsx'
TYPE_LABELS = {
    10: 'Commercial bank', 11: 'Commercial bank subsidiary',
    12: 'Bank or financial holding company subsidiary',
    13: 'Failed commercial bank without successor', 14: 'US branch of foreign bank',
    20: 'Other depository bank / thrift', 21: 'Thrift subsidiary',
    22: 'Thrift holding company subsidiary', 23: 'Failed thrift without successor',
    30: 'Credit union', 31: 'Credit union subsidiary',
    32: 'Credit union service company', 33: 'Failed credit union without successor',
    40: 'Independent mortgage bank', 41: 'Independent mortgage bank with depository affiliation',
}
LOAN_LABELS = ['lender_type', 'nyu_fintech_flag', 'nyu_classification_year',
               'institution_type_code', 'institution_type']
CLASS_FIELDS = ['lei', 'lender_name', 'lender_type', 'evidence_url', 'review_date',
                'notes', 'nyu_fintech_flag', 'nyu_classification_year',
                'nyu_source_rssd', 'nyu_source_lender_name', 'rssd_id',
                'institution_type_code', 'institution_type', 'eligible_loans',
                'institution_source_url']


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path, rows, fields):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def read_nyu(path):
    """Read only the cumulative 2017 section, not both repeated year lists."""
    data = pd.read_excel(path, sheet_name='fintech classification', header=None,
                         dtype=str, keep_default_na=False)
    result, section = {}, False
    for values in data.itertuples(index=False, name=None):
        first, name = str(values[0]).strip(), str(values[1]).strip()
        if 'Lenders classified as fintech as of 2017' in first:
            section = True
            continue
        if section and first.isdigit():
            rssd = int(first)
            if not name or rssd in result:
                raise ValueError('Blank name or duplicate RSSD in NYU 2017 section')
            result[rssd] = name
    if not result:
        raise ValueError('NYU cumulative 2017 classification section not found')
    return result


def match_nyu(nyu, institutions):
    if institutions.LEI.duplicated().any():
        raise ValueError('Duplicate LEI in the reporting-year institution reference')
    mapped = {}
    for rssd, name in nyu.items():
        matches = institutions[institutions.RSSD.eq(rssd)]
        if len(matches) > 1:
            raise ValueError(f'Ambiguous NYU RSSD: {rssd} maps to multiple LEIs')
        if len(matches) == 1:
            lei = matches.iloc[0].LEI
            if lei in mapped:
                raise ValueError('Multiple NYU institutions map to the same LEI')
            mapped[lei] = {'rssd': rssd, 'name': name}
    return mapped


def group_for(nyu_flag, institution_type):
    if nyu_flag:
        return 'Fintech'
    if institution_type in {10, 14, 20}:
        return 'Bank comparator'
    if institution_type == 30:
        return 'Credit union'
    if institution_type in TYPE_LABELS:
        return 'Other lender'
    return 'Unknown'


def join_loans(source, output, classifications, expected_counts, year):
    """Many loans to one classified LEI; preserve every original field and row."""
    tmp = output.with_suffix(output.suffix + '.tmp')
    observed, groups = Counter(), Counter()
    try:
        with source.open(encoding='utf-8-sig', newline='') as incoming, tmp.open('w', encoding='utf-8', newline='') as outgoing:
            reader = csv.DictReader(incoming)
            if not {'lei', 'activity_year'}.issubset(reader.fieldnames or []):
                raise ValueError('Mortgage file is missing LEI or activity_year')
            if set(LOAN_LABELS) & set(reader.fieldnames):
                raise ValueError('Source already has classification columns')
            writer = csv.DictWriter(outgoing, fieldnames=reader.fieldnames + LOAN_LABELS)
            writer.writeheader()
            for row in reader:
                if None in row or None in row.values():
                    raise ValueError('Malformed mortgage CSV row')
                if row['activity_year'] != str(year):
                    raise ValueError('Unexpected mortgage reporting year')
                lei = row['lei']
                if lei not in classifications:
                    raise ValueError(f'Mortgage LEI absent from classification: {lei}')
                label = classifications[lei]
                row.update({field: label[field] for field in LOAN_LABELS})
                writer.writerow(row)
                observed[lei] += 1
                groups[label['lender_type']] += 1
        if dict(observed) != dict(expected_counts):
            raise ValueError('Loan counts by LEI do not reconcile to inventory')
        os.replace(tmp, output)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return observed, groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, default=2025)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--institution-reference', type=Path)
    args = parser.parse_args()
    data = args.data_dir or Path(__file__).resolve().parent / 'data' / str(args.year)
    out = args.output_dir or data
    reference = args.institution_reference or data / 'raw' / 'hmda_lender_2018_2025_philadelphia_fed.xlsx'
    out.mkdir(parents=True, exist_ok=True)
    class_path = out / f'lender_classification_{args.year}.csv'
    if class_path.exists():
        existing = pd.read_csv(class_path, dtype=str, keep_default_na=False)
        if 'nyu_fintech_flag' not in existing.columns and existing['lender_type'].str.strip().ne('').any():
            raise ValueError('Existing manual classifications must be reviewed before replacement')

    nyu_path = data / 'fintech_classification.xlsx'
    mortgage = data / f'mortgages_{args.year}.csv'
    inventory_path = data / f'lender_inventory_{args.year}.csv'
    inputs = {p.name: sha256(p) for p in [nyu_path, mortgage, inventory_path, reference]}
    nyu = read_nyu(nyu_path)
    institutions = pd.read_excel(reference, usecols=['YEAR', 'LEI', 'RSSD', 'TYPE', 'NAMET'],
                                 dtype={'LEI': str, 'NAMET': str})
    institutions = institutions[institutions.YEAR.eq(args.year)].copy()
    if institutions.empty:
        raise ValueError('Reporting year absent from institution reference')
    institutions['LEI'] = institutions.LEI.str.strip()
    mapped = match_nyu(nyu, institutions)
    institutions = institutions.set_index('LEI')
    inventory = pd.read_csv(inventory_path, dtype=str, keep_default_na=False)
    if inventory.lei.eq('').any() or inventory.lei.duplicated().any():
        raise ValueError('Missing or duplicate LEI in lender inventory')
    labels, counts = {}, {}
    stamp = datetime.now(timezone.utc).date().isoformat()
    for row in inventory.itertuples(index=False):
        if row.lei not in institutions.index:
            raise ValueError(f'Inventory LEI missing from institution reference: {row.lei}')
        inst = institutions.loc[row.lei]
        code = int(inst.TYPE)
        positive = row.lei in mapped
        historic = mapped.get(row.lei, {})
        label = {
            'lei': row.lei, 'lender_name': row.lender_name,
            'lender_type': group_for(positive, code),
            'evidence_url': NYU_URL if positive else FED_URL,
            'review_date': stamp,
            'notes': ('NYU 2017 historical classification matched by RSSD to 2025 LEI; digital process not reverified for 2025.' if positive else
                      'Not listed in NYU 2017; this does not establish non-fintech status. Institution type is from the 2025 Philadelphia Fed reference.'),
            'nyu_fintech_flag': '1' if positive else '0',
            'nyu_classification_year': '2017' if positive else '',
            'nyu_source_rssd': str(historic.get('rssd', '')),
            'nyu_source_lender_name': historic.get('name', ''),
            'rssd_id': str(int(inst.RSSD)), 'institution_type_code': str(code),
            'institution_type': TYPE_LABELS.get(code, 'Unknown'),
            'eligible_loans': row.eligible_loans, 'institution_source_url': FED_URL,
        }
        labels[row.lei] = label
        counts[row.lei] = int(row.eligible_loans)

    reference_rows = []
    for rssd, name in nyu.items():
        hits = [lei for lei, value in mapped.items() if value['rssd'] == rssd]
        lei = hits[0] if hits else ''
        reference_rows.append({
            'nyu_rssd': str(rssd), 'nyu_lender_name': name, 'nyu_classification_year': '2017',
            f'lei_{args.year}': lei,
            f'lender_name_{args.year}': str(institutions.loc[lei, 'NAMET']) if lei else '',
            'in_project_sample': '1' if lei in labels else '0',
            'eligible_loans': str(counts.get(lei, 0)),
            'match_status': 'Matched to project sample' if lei in labels else 'Matched to reporting-year reference; outside sample' if lei else 'No RSSD match in reporting-year reference',
            'source_url': NYU_URL,
        })
    ref_path = out / 'nyu_fintech_reference_2017.csv'
    write_csv(class_path, labels.values(), CLASS_FIELDS)
    write_csv(ref_path, reference_rows, list(reference_rows[0]))
    output = out / f'mortgages_{args.year}_classified.csv'
    observed, loan_groups = join_loans(mortgage, output, labels, counts, args.year)
    if sha256(mortgage) != inputs[mortgage.name]:
        raise ValueError('Source mortgage file changed during classification')
    raw = out / 'raw'
    raw.mkdir(exist_ok=True)
    retained_reference = raw / 'hmda_lender_2018_2025_philadelphia_fed.xlsx'
    if reference.resolve() != retained_reference.resolve():
        shutil.copy2(reference, retained_reference)
    outputs = [class_path, ref_path, output]
    summary = {
        'status': 'complete', 'reporting_year': args.year, 'nyu_classification_year': 2017,
        'created_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'sources': {'nyu': NYU_URL, 'institution_reference': FED_URL, 'institution_download': FED_DOWNLOAD},
        'input_sha256': inputs, 'nyu_source_lenders': len(nyu),
        'nyu_lenders_in_sample': sum(v['nyu_fintech_flag'] == '1' for v in labels.values()),
        'lenders_by_group': dict(Counter(v['lender_type'] for v in labels.values())),
        'loans_by_group': dict(loan_groups), 'total_loans': sum(observed.values()),
        'loan_columns_added': LOAN_LABELS,
        'definitions': {
            'nyu_fintech_flag': '1 = listed in the historical NYU 2017 list; 0 = not listed, not proof of non-fintech status.',
            'Bank comparator': 'Philadelphia Fed TYPE 10, 14 or 20, excluding any NYU-listed entity. This group is not verified as digitally non-fintech.',
            'Other lender': 'Other known institution types; not an inference of non-fintech status.',
            'review_date': 'Date the source identity mapping was processed; not a review of the 2025 online application process.',
            'nyu_classification_year': 'Year of the source classification, not HMDA reporting year.',
        },
        'validation': {'unique_lender_lei': True, 'all_sample_lenders_have_institution_reference': True,
                       'loan_counts_by_lei_equal_inventory': True, 'source_mortgage_hash_unchanged': True},
        'outputs': [{'file': p.name, 'bytes': p.stat().st_size, 'sha256': sha256(p)} for p in outputs],
    }
    (out / 'nyu_classification_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: summary[k] for k in ['status', 'nyu_source_lenders', 'nyu_lenders_in_sample', 'lenders_by_group', 'loans_by_group', 'total_loans']}, indent=2))


if __name__ == '__main__':
    main()
