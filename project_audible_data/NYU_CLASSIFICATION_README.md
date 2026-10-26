# NYU lender classification for the 2025 mortgage sample

The selected fintech group uses the cumulative 2017 classification supplied by
Fuster, Plosser, Schnabl and Vickery (2019), hosted by NYU Stern. It is a
historical research classification, not an official regulatory designation or a
verification of lenders' digital processes in 2025. Buchak labels are not used.

## Which files should I use?

- `data/2025/mortgages_2025.csv`: original filtered sample from the downloader.
- `data/2025/lender_classification_2025.csv`: one row per sample LEI, with the
  selected group, NYU source details, 2025 institution type and evidence URLs.
- `data/2025/mortgages_2025_classified.csv`: analysis copy containing every
  original loan and field, plus the five classification columns below. Use this
  for cleaning, analysis and the HTML dashboard.
- `data/2025/nyu_fintech_reference_2017.csv`: all 18 source NYU institutions,
  including the three without a 2025 RSSD match, for auditing coverage.
- `data/2025/nyu_classification_summary.json`: source hashes, counts by group,
  definitions, validation and output hashes.
- `data/2025/raw/hmda_lender_2018_2025_philadelphia_fed.xlsx`: retained institution
  reference; fintech labels do not come from this file.

## Classification columns added to the analysis copy

| Column | Definition |
| --- | --- |
| `lender_type` | Analysis group, defined below |
| `nyu_fintech_flag` | `1`: listed in the historical NYU list and matched by RSSD to the loan's LEI. `0`: not listed; this is not proof of non-fintech status. |
| `nyu_classification_year` | `2017` for matched NYU lenders; blank otherwise. Distinct from loan reporting year 2025. |
| `institution_type_code` | Philadelphia Fed's institution type for the 2025 filer |
| `institution_type` | Plain-language description of that institution type |

The detailed classification table also supplies `nyu_source_rssd`,
`nyu_source_lender_name`, `rssd_id`, `evidence_url`, `institution_source_url`,
`review_date` and `notes`. `review_date` is the identity-mapping processing date;
it does not mean the online lending process was reviewed for 2025.

## Groups and comparison scope

1. `Fintech`: positive match to the selected NYU 2017 list.
2. `Bank comparator`: not NYU-listed and Philadelphia Fed TYPE 10, 14 or 20
   (commercial banks, US branches of foreign banks, savings banks/thrifts).
   This is an institutional comparator, not evidence of non-digital processing.
3. `Credit union`: TYPE 30, kept separate from banks.
4. `Other lender`: other known types, including mortgage companies not in NYU,
   bank subsidiaries and credit-union subsidiaries. Not labeled non-fintech.
5. `Unknown`: institution types not covered by these rules.

For the principal fintech-versus-bank comparison, select only `Fintech` and
`Bank comparator`. Other groups remain in the files for transparency. No loan
is dropped or price imputed during classification. Missing values, `NA`,
`Exempt`, valid zeroes, negative spreads and DTI ranges retain original values.
Metric-specific cleaning remains a separate next step.

## Reproduce

The original downloader requires only standard-library Python. This additional
classification step requires `pandas` and `openpyxl` to read the source Excel
files. From the project code folder:

```sh
python3 classify_lenders_nyu.py
python3 -m unittest -v test_classify_lenders_nyu.py
```

If `data/2025/raw/hmda_lender_2018_2025_philadelphia_fed.xlsx` is missing (it is
gitignored), the script downloads it once from the Philadelphia Fed and never
overwrites an existing copy. If the download is blocked, save the workbook there
manually or pass `--institution-reference`.

Paths default to `data/2025` relative to the script. To use other paths:

```sh
python3 classify_lenders_nyu.py --data-dir /path/to/data/2025 --institution-reference /path/to/hmda-reference.xlsx --output-dir /path/to/derived
```

Running the step regenerates its classification and derived analysis outputs;
it rejects replacement of a nonblank manual classification template. Store any
manual review separately before regenerating generated labels. The original
loan extract, inventory, source NYU workbook and downloader manifest are not
modified. The downloader continues to preserve an existing classification CSV.

## Sources

- NYU data and cumulative 2017 lender list:
  https://pages.stern.nyu.edu/pschnabl/data/data_fintech.htm
- Underlying research, also published as New York Fed Staff Report 836:
  https://www.newyorkfed.org/research/staff_reports/sr836
- Philadelphia Fed 2018–2025 HMDA Lender File, version July 15, 2026:
  https://www.philadelphiafed.org/surveys-and-data/consumer-finance-data/home-mortgage-disclosure-act-lender-file
- Institution type and identifier definitions:
  https://www.philadelphiafed.org/surveys-and-data/consumer-finance-data/hmda-lender-variable-definitions

The two-source approach deliberately separates technology classification
(NYU historical list) from legal institution type (Philadelphia Fed, 2025).
