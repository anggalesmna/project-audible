#!/usr/bin/env python3
"""Create the analysis-ready (cleansed) copy of the classified HMDA sample.

Input : data/<year>/mortgages_<year>_classified.csv   (never modified)
Output: data/<year>/mortgages_<year>_clean.csv        (all rows, all original
        columns, plus numeric columns, review flags and eligibility flags)
        data/<year>/data_quality/                     (quality reports)

Principles agreed for Project Audible:
* No loan is deleted and no value is imputed (no zero/mean/median filling).
* NA, Exempt and blank are kept distinct from each other.
* Eligibility is decided per indicator: a loan missing one variable is excluded
  only from calculations that need that variable.
* Values that are impossible are marked invalid for that variable only.
  Values that are possible but unusual receive a review flag and stay eligible.

Standard library only, so it runs with any Python 3.10+ installation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from array import array
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

GROUP_ORDER = ['Fintech', 'Bank comparator', 'Credit union', 'Other lender']
MAIN_GROUPS = {'Fintech', 'Bank comparator'}
MAIN_LABEL = 'Main comparison (Fintech + Bank)'
ALL_LABEL = 'All loans'
REPORT_GROUPS = GROUP_ORDER + [MAIN_LABEL, ALL_LABEL]

# Values that HMDA uses to say "no value".
UNAVAILABLE = {'NA': 'na', 'EXEMPT': 'exempt', '': 'blank'}

# DTI is reported as exact values for 36-49 and as ranges elsewhere.
DTI_RANGES = ['<20%', '20%-<30%', '30%-<36%', '50%-60%', '>60%']
DTI_EXACT = {str(v) for v in range(36, 50)}

# Variables audited in the missing-value report.
AUDITED = ['rate_spread', 'interest_rate', 'origination_charges', 'loan_amount',
           'debt_to_income_ratio', 'combined_loan_to_value_ratio', 'income',
           'state_code', 'county_code']
STATUSES = ['valid', 'na', 'exempt', 'blank', 'invalid']

# Rules for impossible values (-> invalid) and unusual values (-> review flag).
RULES = {
    'rate_spread': {
        'invalid': 'non-numeric, or below -10 percentage points (would imply a '
                   'negative APR, because the 2025 APOR for these loans was far below 10%)',
        'review': 'below -3 or above 5 percentage points (flag RS_UNUSUAL)',
    },
    'interest_rate': {
        'invalid': 'non-numeric or <= 0 (a 0% conventional purchase mortgage is not plausible)',
        'review': 'below 2% or above 12% (flag IR_UNUSUAL)',
    },
    'origination_charges': {
        'invalid': 'non-numeric or negative (0 is valid: the loan had no origination charges)',
        'review': 'origination charges above 5% of loan amount (flag ORIG_PCT_GT5)',
    },
    'loan_amount': {'invalid': 'non-numeric or <= 0', 'review': 'none'},
    'debt_to_income_ratio': {
        'invalid': 'anything other than an exact value 36-49 or an official HMDA range',
        'review': 'none (ranges are valid categories, not missing values)',
    },
    'combined_loan_to_value_ratio': {
        'invalid': 'non-numeric or <= 0',
        'review': 'below 5% or above 150% (flag CLTV_UNUSUAL)',
    },
    'income': {
        'invalid': 'non-numeric or <= 0 (cannot be placed in an income group); '
                   'HMDA income is in thousands of dollars',
        'review': 'above 10,000 thousand = $10 million per year (flag INCOME_GT10M)',
    },
    'state_code': {'invalid': 'not a two-letter code', 'review': 'none'},
    'county_code': {'invalid': 'not a numeric FIPS code', 'review': 'none'},
}

# Each indicator lists the variables that must be valid for a loan to count.
INDICATORS = {
    'elig_rate_spread': ('Median rate spread (main measure)', ['rate_spread']),
    'elig_interest_rate': ('Median interest rate (supporting)', ['interest_rate']),
    'elig_orig_pct': ('Median origination charges / loan amount (supporting)',
                      ['origination_charges', 'loan_amount']),
    'elig_all_pricing': ('All three pricing measures available (common subset)',
                         ['rate_spread', 'interest_rate', 'origination_charges', 'loan_amount']),
    'elig_controlled': ('Rate spread within DTI, CLTV, income and loan-amount groups',
                        ['rate_spread', 'debt_to_income_ratio', 'combined_loan_to_value_ratio',
                         'income', 'loan_amount']),
    'elig_state': ('Rate spread by property state', ['rate_spread', 'state_code']),
}

NEW_FIELDS = ['rate_spread_num', 'interest_rate_num', 'origination_charges_num',
              'loan_amount_num', 'orig_charge_pct', 'dti_category', 'dti_num',
              'cltv_num', 'income_k_num', 'dti_group', 'cltv_group',
              'income_group', 'loan_amount_group', 'review_flags',
              'in_main_comparison', *INDICATORS]


def dti_group_for(dti_cat):
    if not dti_cat:
        return ''
    if dti_cat in {'<20%', '20%-<30%'}:
        return '<30%'
    if dti_cat == '30%-<36%':
        return '30%-<36%'
    if dti_cat in {str(v) for v in range(36, 44)}:
        return '36%-43%'
    if dti_cat in {str(v) for v in range(44, 50)}:
        return '44%-49%'
    if dti_cat in {'50%-60%', '>60%'}:
        return '>=50%'
    return ''


def cltv_group_for(cltv):
    if cltv is None:
        return ''
    if cltv <= 80:
        return '<=80%'
    if cltv <= 90:
        return '80.01%-90%'
    if cltv <= 95:
        return '90.01%-95%'
    return '>95%'


def income_group_for(inc):
    if inc is None:
        return ''
    if inc <= 75:
        return '<=$75k'
    if inc <= 125:
        return '$75k-$125k'
    if inc <= 200:
        return '$125k-$200k'
    return '>$200k'


def loan_amount_group_for(la):
    if la is None:
        return ''
    if la <= 200000:
        return '<=$200k'
    if la <= 350000:
        return '$200k-$350k'
    if la <= 500000:
        return '$350k-$500k'
    return '>$500k'


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def number(raw):
    """Return (status, value). Status is valid/na/exempt/blank/invalid."""
    text = raw.strip()
    if text.upper() in UNAVAILABLE:
        return UNAVAILABLE[text.upper()], None
    try:
        value = float(text)
    except ValueError:
        return 'invalid', None
    return ('valid', value) if math.isfinite(value) else ('invalid', None)


def fmt(value, digits=6):
    if value is None:
        return ''
    text = f'{value:.{digits}f}'
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return '0' if text in {'', '-0'} else text


def clean_row(row):
    """Return (status by audited variable, new output fields, review flags)."""
    status, flags = {}, []

    s, rs = number(row['rate_spread'])
    if s == 'valid' and rs < -10:
        s, rs = 'invalid', None
    status['rate_spread'] = s
    if rs is not None and (rs < -3 or rs > 5):
        flags.append('RS_UNUSUAL')

    s, ir = number(row['interest_rate'])
    if s == 'valid' and ir <= 0:
        s, ir = 'invalid', None
        flags.append('IR_ZERO_OR_NEGATIVE')
    status['interest_rate'] = s
    if ir is not None and (ir < 2 or ir > 12):
        flags.append('IR_UNUSUAL')

    s, oc = number(row['origination_charges'])
    if s == 'valid' and oc < 0:
        s, oc = 'invalid', None
    status['origination_charges'] = s

    s, la = number(row['loan_amount'])
    if s == 'valid' and la <= 0:
        s, la = 'invalid', None
    status['loan_amount'] = s

    pct = oc / la * 100 if oc is not None and la is not None else None
    if pct is not None and pct > 5:
        flags.append('ORIG_PCT_GT5')

    dti_raw = row['debt_to_income_ratio'].strip()
    dti_cat = dti_num = None
    if dti_raw.upper() in UNAVAILABLE:
        status['debt_to_income_ratio'] = UNAVAILABLE[dti_raw.upper()]
    elif dti_raw in DTI_EXACT:
        status['debt_to_income_ratio'] = 'valid'
        dti_cat, dti_num = dti_raw, float(dti_raw)
    elif dti_raw in DTI_RANGES:
        status['debt_to_income_ratio'] = 'valid'
        dti_cat = dti_raw
    else:
        status['debt_to_income_ratio'] = 'invalid'

    s, cltv = number(row['combined_loan_to_value_ratio'])
    if s == 'valid' and cltv <= 0:
        s, cltv = 'invalid', None
    status['combined_loan_to_value_ratio'] = s
    if cltv is not None and (cltv < 5 or cltv > 150):
        flags.append('CLTV_UNUSUAL')

    s, inc = number(row['income'])
    if s == 'valid' and inc <= 0:
        s, inc = 'invalid', None
        flags.append('INCOME_ZERO_OR_NEGATIVE')
    status['income'] = s
    if inc is not None and inc > 10000:
        flags.append('INCOME_GT10M')

    state = row['state_code'].strip()
    if state.upper() in UNAVAILABLE:
        status['state_code'] = UNAVAILABLE[state.upper()]
    else:
        status['state_code'] = 'valid' if len(state) == 2 and state.isalpha() else 'invalid'

    county = row['county_code'].strip()
    if county.upper() in UNAVAILABLE:
        status['county_code'] = UNAVAILABLE[county.upper()]
    else:
        status['county_code'] = 'valid' if county.isdigit() else 'invalid'

    new = {
        'rate_spread_num': fmt(rs), 'interest_rate_num': fmt(ir),
        'origination_charges_num': fmt(oc, 2), 'loan_amount_num': fmt(la, 0),
        'orig_charge_pct': fmt(pct), 'dti_category': dti_cat or '',
        'dti_num': fmt(dti_num, 0), 'cltv_num': fmt(cltv),
        'income_k_num': fmt(inc),
        'dti_group': dti_group_for(dti_cat),
        'cltv_group': cltv_group_for(cltv),
        'income_group': income_group_for(inc),
        'loan_amount_group': loan_amount_group_for(la),
        'review_flags': ';'.join(flags),
        'in_main_comparison': '1' if row['lender_type'] in MAIN_GROUPS else '0',
    }
    for name, (_, needs) in INDICATORS.items():
        new[name] = '1' if all(status[v] == 'valid' for v in needs) else '0'
    return status, new, flags


def percentiles(values):
    if not values:
        return {}
    data = sorted(values)
    pick = lambda q: data[min(len(data) - 1, int(round(q * (len(data) - 1))))]
    return {'n': len(data), 'min': data[0], 'p01': pick(0.01), 'p25': pick(0.25),
            'median': pick(0.5), 'p75': pick(0.75), 'p99': pick(0.99), 'max': data[-1]}


def write_csv(path, rows, fields):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def pct(part, whole):
    return round(100 * part / whole, 4) if whole else 0.0


def process(source, output, quality_dir):
    status_counts = defaultdict(Counter)            # (group, variable) -> status counts
    review_counts = defaultdict(Counter)            # group -> flag counts
    totals = Counter()                              # group -> loans
    eligible = defaultdict(Counter)                 # indicator -> group -> loans
    eligible_lenders = defaultdict(lambda: defaultdict(set))
    lenders = defaultdict(set)
    per_lender = {}
    distributions = {g: {v: array('d') for v in ['rate_spread', 'interest_rate', 'orig_charge_pct']}
                     for g in GROUP_ORDER}

    tmp = output.with_suffix(output.suffix + '.tmp')
    with source.open(newline='', encoding='utf-8') as src, \
            tmp.open('w', newline='', encoding='utf-8') as dst:
        reader = csv.DictReader(src)
        missing = {'lei', 'lender_name', 'lender_type', *AUDITED} - set(reader.fieldnames)
        if missing:
            raise SystemExit(f'Input is missing required columns: {sorted(missing)}')
        writer = csv.DictWriter(dst, fieldnames=list(reader.fieldnames) + NEW_FIELDS)
        writer.writeheader()
        for i, row in enumerate(reader, 1):
            group = row['lender_type']
            if group not in GROUP_ORDER:
                raise SystemExit(f'Row {i}: unknown lender_type {group!r}')
            status, new, flags = clean_row(row)
            writer.writerow({**row, **new})

            labels = [group, ALL_LABEL] + ([MAIN_LABEL] if group in MAIN_GROUPS else [])
            for label in labels:
                totals[label] += 1
                lenders[label].add(row['lei'])
                for var in AUDITED:
                    status_counts[label, var][status[var]] += 1
                review_counts[label].update(flags)
                for name in INDICATORS:
                    if new[name] == '1':
                        eligible[name][label] += 1
                        eligible_lenders[name][label].add(row['lei'])

            if new['elig_rate_spread'] == '1':
                distributions[group]['rate_spread'].append(float(new['rate_spread_num']))
            if new['elig_interest_rate'] == '1':
                distributions[group]['interest_rate'].append(float(new['interest_rate_num']))
            if new['elig_orig_pct'] == '1':
                distributions[group]['orig_charge_pct'].append(float(new['orig_charge_pct']))

            if group in MAIN_GROUPS:
                rec = per_lender.setdefault(row['lei'], Counter(
                    lei=0, lender_name=row['lender_name'], lender_type=group))
                rec['loans'] += 1
                for var in ['rate_spread', 'interest_rate', 'origination_charges']:
                    rec[f'{var}_unavailable'] += status[var] != 'valid'
                rec['not_eligible_controlled'] += new['elig_controlled'] == '0'
                rec['review_flagged'] += bool(flags)
            if i % 250000 == 0:
                print(f'  processed {i:,} loans')
    os.replace(tmp, output)

    # 1. Missing values by group and variable.
    missing_rows = []
    for label in REPORT_GROUPS:
        for var in AUDITED:
            c = status_counts[label, var]
            unavailable = sum(c[s] for s in STATUSES if s != 'valid')
            missing_rows.append({
                'group': label, 'variable': var, 'total_loans': totals[label],
                **{s: c[s] for s in STATUSES},
                'not_usable_total': unavailable,
                'not_usable_pct': pct(unavailable, totals[label]),
            })
    write_csv(quality_dir / 'missing_by_group.csv', missing_rows,
              ['group', 'variable', 'total_loans', *STATUSES, 'not_usable_total', 'not_usable_pct'])

    # 2. Eligible loans by indicator and group.
    elig_rows = []
    for name, (description, needs) in INDICATORS.items():
        for label in REPORT_GROUPS:
            elig_rows.append({
                'indicator': name, 'description': description,
                'required_valid_variables': ' + '.join(needs), 'group': label,
                'total_loans': totals[label], 'eligible_loans': eligible[name][label],
                'eligible_pct': pct(eligible[name][label], totals[label]),
                'excluded_loans': totals[label] - eligible[name][label],
                'total_lenders': len(lenders[label]),
                'eligible_lenders': len(eligible_lenders[name][label]),
            })
    write_csv(quality_dir / 'eligible_loans_by_indicator.csv', elig_rows,
              ['indicator', 'description', 'required_valid_variables', 'group', 'total_loans',
               'eligible_loans', 'eligible_pct', 'excluded_loans', 'total_lenders',
               'eligible_lenders'])

    # 3. Review flags by group.
    flag_names = sorted({f for c in review_counts.values() for f in c})
    flag_rows = [{'group': label, 'total_loans': totals[label],
                  **{f: review_counts[label][f] for f in flag_names}} for label in REPORT_GROUPS]
    write_csv(quality_dir / 'review_flags_by_group.csv', flag_rows,
              ['group', 'total_loans', *flag_names])

    # 4. Lender-level concentration of unavailable values (main comparison only).
    group_missing = Counter()
    for rec in per_lender.values():
        group_missing[rec['lender_type']] += rec['rate_spread_unavailable']
    lender_rows = []
    for lei, rec in per_lender.items():
        lender_rows.append({
            'lei': lei, 'lender_name': rec['lender_name'], 'lender_type': rec['lender_type'],
            'loans': rec['loans'],
            'rate_spread_unavailable': rec['rate_spread_unavailable'],
            'rate_spread_unavailable_pct': pct(rec['rate_spread_unavailable'], rec['loans']),
            'share_of_group_rate_spread_unavailable_pct':
                pct(rec['rate_spread_unavailable'], group_missing[rec['lender_type']]),
            'interest_rate_unavailable': rec['interest_rate_unavailable'],
            'origination_charges_unavailable': rec['origination_charges_unavailable'],
            'not_eligible_controlled': rec['not_eligible_controlled'],
            'review_flagged': rec['review_flagged'],
        })
    lender_rows.sort(key=lambda r: (r['lender_type'], -r['rate_spread_unavailable'], -r['loans']))
    write_csv(quality_dir / 'missing_by_lender_main_groups.csv', lender_rows,
              list(lender_rows[0]))

    dist = {g: {v: percentiles(a) for v, a in d.items()} for g, d in distributions.items()}
    return {
        'totals': dict(totals), 'lenders': {k: len(v) for k, v in lenders.items()},
        'missing_rows': missing_rows, 'eligible_rows': elig_rows,
        'review_counts': {k: dict(v) for k, v in review_counts.items()},
        'distributions': dist, 'lender_rows': lender_rows,
    }


def write_markdown(path, result, year):
    t = result['totals']
    lines = [f'# Data quality report — HMDA {year} cleansed sample', '',
             f'Generated: {utc_now()} by `clean_mortgages.py`.', '',
             'No loan was deleted and no value was imputed. Each indicator uses only the '
             'loans whose required variables are valid.', '',
             '## 1. Eligible loans per indicator', '',
             '| Indicator | Fintech | Bank comparator | Main comparison | All loans |',
             '|---|---:|---:|---:|---:|']
    rows = {(r['indicator'], r['group']): r for r in result['eligible_rows']}
    for name, (desc, _) in INDICATORS.items():
        cells = []
        for g in ['Fintech', 'Bank comparator', MAIN_LABEL, ALL_LABEL]:
            r = rows[name, g]
            cells.append(f"{r['eligible_loans']:,} ({r['eligible_pct']:.2f}%)")
        lines.append(f'| {desc} | ' + ' | '.join(cells) + ' |')
    lines += ['', '## 2. Not-usable values: Fintech vs Bank comparator', '',
              '"Not usable" = NA + Exempt + blank + invalid.', '',
              '| Variable | Fintech | Bank comparator | Difference (pp) |', '|---|---:|---:|---:|']
    m = {(r['group'], r['variable']): r for r in result['missing_rows']}
    for var in AUDITED:
        f, b = m['Fintech', var], m['Bank comparator', var]
        lines.append(f"| `{var}` | {f['not_usable_total']:,} ({f['not_usable_pct']:.2f}%) | "
                     f"{b['not_usable_total']:,} ({b['not_usable_pct']:.2f}%) | "
                     f"{f['not_usable_pct'] - b['not_usable_pct']:+.2f} |")
    lines += ['', '## 3. Review flags (kept in calculations, used for robustness checks)', '',
              '| Flag | Fintech | Bank comparator | All loans |', '|---|---:|---:|---:|']
    rc = result['review_counts']
    for flag in sorted({f for c in rc.values() for f in c}):
        lines.append(f"| `{flag}` | {rc.get('Fintech', {}).get(flag, 0):,} | "
                     f"{rc.get('Bank comparator', {}).get(flag, 0):,} | "
                     f"{rc.get(ALL_LABEL, {}).get(flag, 0):,} |")
    lines += ['', '## 4. Lender concentration of unavailable rate spread', '']
    for g in ['Fintech', 'Bank comparator']:
        top = [r for r in result['lender_rows'] if r['lender_type'] == g][:5]
        lines += [f'**{g}** — top 5 lenders by unavailable rate spread:', '',
                  '| Lender | Loans | Unavailable | Share of group unavailable |',
                  '|---|---:|---:|---:|']
        for r in top:
            lines.append(f"| {r['lender_name']} | {r['loans']:,} | {r['rate_spread_unavailable']:,} | "
                         f"{r['share_of_group_rate_spread_unavailable_pct']:.1f}% |")
        lines.append('')
    lines += ['## 5. Distribution check of eligible values (not yet a comparison result)', '',
              '| Group | Variable | n | p01 | median | p99 |', '|---|---|---:|---:|---:|---:|']
    for g in ['Fintech', 'Bank comparator']:
        for var, d in result['distributions'][g].items():
            if d:
                lines.append(f"| {g} | `{var}` | {d['n']:,} | {d['p01']:.3f} | "
                             f"{d['median']:.3f} | {d['p99']:.3f} |")
    lines += ['', 'Medians here are descriptive checks only. They do not control for borrower '
              'differences and are not the project finding.', '',
              '## 6. Cleansing rules', '', '| Variable | Invalid when | Review flag when |',
              '|---|---|---|']
    for var, r in RULES.items():
        lines.append(f"| `{var}` | {r['invalid']} | {r['review']} |")
    lines += ['', 'Total loans: ' + f"{t[ALL_LABEL]:,}" + '.', '']
    path.write_text('\n'.join(lines), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--year', type=int, default=2025)
    parser.add_argument('--data-dir', type=Path,
                        help='Folder containing mortgages_<year>_classified.csv')
    args = parser.parse_args(argv)
    data_dir = args.data_dir or Path(__file__).resolve().parent / 'data' / str(args.year)
    source = data_dir / f'mortgages_{args.year}_classified.csv'
    output = data_dir / f'mortgages_{args.year}_clean.csv'
    quality_dir = data_dir / 'data_quality'
    if not source.exists():
        raise SystemExit(f'Missing input: {source}. Run classify_lenders_nyu.py first.')
    quality_dir.mkdir(parents=True, exist_ok=True)

    started = utc_now()
    print(f'Reading {source.name} and writing {output.name} ...')
    source_hash_before = sha256(source)
    result = process(source, output, quality_dir)
    if sha256(source) != source_hash_before:
        raise SystemExit('Input file changed during processing; outputs are not reliable.')
    write_markdown(quality_dir / 'data_quality_report.md', result, args.year)

    summary = {
        'status': 'complete', 'reporting_year': args.year,
        'started_at_utc': started, 'finished_at_utc': utc_now(),
        'input': {'file': source.name, 'sha256': source_hash_before},
        'output': {'file': output.name, 'sha256': sha256(output)},
        'script_sha256': sha256(Path(__file__).resolve()),
        'loans_by_group': result['totals'], 'lenders_by_group': result['lenders'],
        'columns_added': NEW_FIELDS,
        'indicators': {k: {'description': d, 'requires_valid': n} for k, (d, n) in INDICATORS.items()},
        'eligible_loans': {r['indicator']: {} for r in result['eligible_rows']},
        'review_flags_by_group': result['review_counts'],
        'rules': RULES,
        'principles': ['No rows deleted', 'No values imputed',
                       'NA, Exempt and blank kept distinct',
                       'Eligibility decided per indicator',
                       'Review-flagged values stay eligible; exclude them only in robustness checks'],
        'distributions_of_eligible_values': result['distributions'],
    }
    for r in result['eligible_rows']:
        summary['eligible_loans'][r['indicator']][r['group']] = r['eligible_loans']
    tmp = quality_dir / 'cleaning_summary.json.tmp'
    tmp.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    os.replace(tmp, quality_dir / 'cleaning_summary.json')
    print(f"Done: {result['totals'][ALL_LABEL]:,} loans written to {output}")
    print(f'Reports saved in {quality_dir}')


if __name__ == '__main__':
    main()
