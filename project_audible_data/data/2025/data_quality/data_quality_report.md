# Data quality report — HMDA 2025 cleansed sample

Generated: 2026-10-23T00:17:43+00:00 by `clean_mortgages.py`.

No loan was deleted and no value was imputed. Each indicator uses only the loans whose required variables are valid.

## 1. Eligible loans per indicator

| Indicator | Fintech | Bank comparator | Main comparison | All loans |
|---|---:|---:|---:|---:|
| Median rate spread (main measure) | 175,754 (99.90%) | 346,999 (99.82%) | 522,753 (99.85%) | 1,501,905 (99.59%) |
| Median interest rate (supporting) | 175,917 (99.99%) | 347,571 (99.98%) | 523,488 (99.99%) | 1,507,188 (99.94%) |
| Median origination charges / loan amount (supporting) | 175,569 (99.80%) | 346,870 (99.78%) | 522,439 (99.79%) | 1,498,724 (99.38%) |
| All three pricing measures available (common subset) | 175,543 (99.78%) | 346,572 (99.69%) | 522,115 (99.72%) | 1,493,906 (99.06%) |
| Rate spread within DTI, CLTV, income and loan-amount groups | 173,253 (98.48%) | 339,609 (97.69%) | 512,862 (97.96%) | 1,467,097 (97.28%) |
| Rate spread by property state | 175,754 (99.90%) | 346,994 (99.82%) | 522,748 (99.84%) | 1,501,732 (99.58%) |

## 2. Not-usable values: Fintech vs Bank comparator

"Not usable" = NA + Exempt + blank + invalid.

| Variable | Fintech | Bank comparator | Difference (pp) |
|---|---:|---:|---:|
| `rate_spread` | 174 (0.10%) | 635 (0.18%) | -0.08 |
| `interest_rate` | 11 (0.01%) | 63 (0.02%) | -0.01 |
| `origination_charges` | 359 (0.20%) | 764 (0.22%) | -0.02 |
| `loan_amount` | 0 (0.00%) | 0 (0.00%) | +0.00 |
| `debt_to_income_ratio` | 61 (0.03%) | 386 (0.11%) | -0.08 |
| `combined_loan_to_value_ratio` | 1,680 (0.95%) | 33 (0.01%) | +0.95 |
| `income` | 821 (0.47%) | 7,365 (2.12%) | -1.65 |
| `state_code` | 0 (0.00%) | 5 (0.00%) | -0.00 |
| `county_code` | 0 (0.00%) | 77 (0.02%) | -0.02 |

## 3. Review flags (kept in calculations, used for robustness checks)

| Flag | Fintech | Bank comparator | All loans |
|---|---:|---:|---:|
| `CLTV_UNUSUAL` | 0 | 20 | 146 |
| `INCOME_GT10M` | 3 | 2 | 701 |
| `INCOME_ZERO_OR_NEGATIVE` | 27 | 105 | 2,246 |
| `IR_UNUSUAL` | 0 | 46 | 225 |
| `IR_ZERO_OR_NEGATIVE` | 11 | 54 | 771 |
| `ORIG_PCT_GT5` | 155 | 314 | 2,757 |
| `RS_UNUSUAL` | 29 | 518 | 1,649 |

## 4. Lender concentration of unavailable rate spread

**Fintech** — top 5 lenders by unavailable rate spread:

| Lender | Loans | Unavailable | Share of group unavailable |
|---|---:|---:|---:|
| GUARANTEED RATE, INC. | 27,081 | 156 | 89.7% |
| American Neighborhood Mortgage Acceptance Company | 4,931 | 5 | 2.9% |
| MOVEMENT MORTGAGE, LLC | 20,440 | 3 | 1.7% |
| EVERETT FINANCIAL, INC. | 5,586 | 3 | 1.7% |
| ENVOY MORTGAGE, LTD | 2,770 | 3 | 1.7% |

**Bank comparator** — top 5 lenders by unavailable rate spread:

| Lender | Loans | Unavailable | Share of group unavailable |
|---|---:|---:|---:|
| Bank of America NA | 13,116 | 151 | 23.8% |
| FIRST HORIZON BANK | 2,222 | 116 | 18.3% |
| Banco Popular | 540 | 36 | 5.7% |
| American Commercial Bank & Trust, National Association | 70 | 24 | 3.8% |
| Community Bank, N.A. | 1,203 | 23 | 3.6% |

## 5. Distribution check of eligible values (not yet a comparison result)

| Group | Variable | n | p01 | median | p99 |
|---|---|---:|---:|---:|---:|
| Fintech | `rate_spread` | 175,754 | -1.568 | 0.217 | 1.930 |
| Fintech | `interest_rate` | 175,917 | 4.990 | 6.625 | 8.125 |
| Fintech | `orig_charge_pct` | 175,569 | 0.000 | 0.956 | 4.147 |
| Bank comparator | `rate_spread` | 346,999 | -1.395 | 0.045 | 1.655 |
| Bank comparator | `interest_rate` | 347,571 | 5.125 | 6.500 | 7.875 |
| Bank comparator | `orig_charge_pct` | 346,870 | 0.000 | 0.568 | 3.777 |

Medians here are descriptive checks only. They do not control for borrower differences and are not the project finding.

## 6. Cleansing rules

| Variable | Invalid when | Review flag when |
|---|---|---|
| `rate_spread` | non-numeric, or below -10 percentage points (would imply a negative APR, because the 2025 APOR for these loans was far below 10%) | below -3 or above 5 percentage points (flag RS_UNUSUAL) |
| `interest_rate` | non-numeric or <= 0 (a 0% conventional purchase mortgage is not plausible) | below 2% or above 12% (flag IR_UNUSUAL) |
| `origination_charges` | non-numeric or negative (0 is valid: the loan had no origination charges) | origination charges above 5% of loan amount (flag ORIG_PCT_GT5) |
| `loan_amount` | non-numeric or <= 0 | none |
| `debt_to_income_ratio` | anything other than an exact value 36-49 or an official HMDA range | none (ranges are valid categories, not missing values) |
| `combined_loan_to_value_ratio` | non-numeric or <= 0 | below 5% or above 150% (flag CLTV_UNUSUAL) |
| `income` | non-numeric or <= 0 (cannot be placed in an income group); HMDA income is in thousands of dollars | above 10,000 thousand = $10 million per year (flag INCOME_GT10M) |
| `state_code` | not a two-letter code | none |
| `county_code` | not a numeric FIPS code | none |

Total loans: 1,508,076.
