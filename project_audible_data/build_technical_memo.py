#!/usr/bin/env python3
"""Generate a concise, strictly 1-page Word Technical Memo in Submit/Project Audible Technical Memo.docx."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

W_NS = 'http://schemas.microsoft.com/office/word/2003/wordml'
W_MAIN = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def r_xml(text: str, bold: bool = False, italic: bool = False, size_half_pt: int = 19,
          color: str = '0F172A', font: str = 'Calibri') -> str:
    b_tag = '<w:b/><w:bCs/>' if bold else ''
    i_tag = '<w:i/><w:iCs/>' if italic else ''
    return (
        f'<w:r>'
        f'<w:rPr>'
        f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>'
        f'{b_tag}{i_tag}'
        f'<w:color w:val="{color}"/>'
        f'<w:sz w:val="{size_half_pt}"/><w:szCs w:val="{size_half_pt}"/>'
        f'</w:rPr>'
        f'<w:t xml:space="preserve">{escape(text)}</w:t>'
        f'</w:r>'
    )


def p_xml(runs: list[str], before: int = 24, after: int = 24, line: int = 215,
          bottom_border: bool = False, left_indent: int = 0, hanging: int = 0) -> str:
    bdr = (
        '<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="CBD5E1"/></w:pBdr>'
        if bottom_border else ''
    )
    ind = f'<w:ind w:left="{left_indent}" w:hanging="{hanging}"/>' if (left_indent or hanging) else ''
    return (
        f'<w:p>'
        f'<w:pPr>'
        f'{bdr}{ind}'
        f'<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>'
        f'</w:pPr>'
        f'{"".join(runs)}'
        f'</w:p>'
    )


def section_heading(title: str) -> str:
    return p_xml(
        [r_xml(title, bold=True, size_half_pt=20, color='0F172A')],
        before=85, after=32, line=218, bottom_border=True
    )


def bullet_p(lead: str, body: str, size_half_pt: int = 18) -> str:
    return p_xml(
        [
            r_xml('• ', bold=True, size_half_pt=size_half_pt, color='B45309'),
            r_xml(lead, bold=True, size_half_pt=size_half_pt, color='0F172A'),
            r_xml(body, bold=False, size_half_pt=size_half_pt, color='1E293B'),
        ],
        before=18, after=22, line=214, left_indent=180, hanging=180
    )


def table_xml(headers: list[str], rows: list[list[str]], col_widths: list[int]) -> str:
    total_w = sum(col_widths)
    grid_cols = ''.join(f'<w:gridCol w:w="{w}"/>' for w in col_widths)

    def cell_xml(text: str, width: int, is_header: bool = False, bold_first: bool = False) -> str:
        shd = '<w:shd w:val="clear" w:color="auto" w:fill="F1F5F9"/>' if is_header else ''
        run = r_xml(
            text,
            bold=(is_header or bold_first),
            size_half_pt=17,
            color='0F172A' if (is_header or bold_first) else '1E293B',
        )
        return (
            f'<w:tc>'
            f'<w:tcPr>'
            f'<w:tcW w:w="{width}" w:type="dxa"/>'
            f'{shd}'
            f'<w:tcMar>'
            f'<w:top w:w="32" w:type="dxa"/><w:bottom w:w="32" w:type="dxa"/>'
            f'<w:left w:w="68" w:type="dxa"/><w:right w:w="68" w:type="dxa"/>'
            f'</w:tcMar>'
            f'</w:tcPr>'
            f'{p_xml([run], before=8, after=8, line=198)}'
            f'</w:tc>'
        )

    header_tr = '<w:tr>' + ''.join(
        cell_xml(h, w, is_header=True) for h, w in zip(headers, col_widths)
    ) + '</w:tr>'

    body_trs = []
    for row in rows:
        cells = [
            cell_xml(val, w, is_header=False, bold_first=(idx == 0))
            for idx, (val, w) in enumerate(zip(row, col_widths))
        ]
        body_trs.append('<w:tr>' + ''.join(cells) + '</w:tr>')

    return (
        f'<w:tbl>'
        f'<w:tblPr>'
        f'<w:tblW w:w="{total_w}" w:type="dxa"/>'
        f'<w:tblBorders>'
        f'<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        f'<w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        f'<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        f'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        f'</w:tblBorders>'
        f'</w:tblPr>'
        f'<w:tblGrid>{grid_cols}</w:tblGrid>'
        f'{header_tr}{"".join(body_trs)}'
        f'</w:tbl>'
    )


def build_document_xml() -> str:
    parts = []

    # Header
    parts.append(p_xml([
        r_xml('FINTECH 590 — PROJECT AUDIBLE: TECHNICAL MEMO', bold=True, size_half_pt=22, color='0F172A'),
    ], before=0, after=12, line=215))
    parts.append(p_xml([
        r_xml('Topic: ', bold=True, size_half_pt=18, color='B45309'),
        r_xml('Fintech vs. Bank Mortgage Pricing   |   ', size_half_pt=18, color='334155'),
        r_xml('Audience: ', bold=True, size_half_pt=18, color='B45309'),
        r_xml('American Fintech Council (AFC)   |   ', size_half_pt=18, color='334155'),
        r_xml('Date: ', bold=True, size_half_pt=18, color='B45309'),
        r_xml('October 26, 2026', size_half_pt=18, color='334155'),
    ], before=0, after=38, line=205, bottom_border=True))

    # 1. Data Sources and Provenance (8 pts)
    parts.append(section_heading('1. Data Sources and Provenance'))
    parts.append(table_xml(
        headers=['Source Dataset', 'Version & Access Date', 'Retrieval & Verification'],
        rows=[
            [
                'FFIEC / CFPB 2025 HMDA Static Snapshot (LAR & TS)',
                '2025 Snapshot (Jun 23, 2026);\nAccessed Oct 22, 2026',
                'Downloaded via download_hmda.py from files.ffiec.cfpb.gov (2025_public_lar_csv.zip, SHA-256: 9b25c05d...; 2025_public_ts_csv.zip, SHA-256: 6d4157af...). Static archive used instead of live API.'
            ],
            [
                'NYU Stern Fintech List (Fuster et al., 2019)',
                'Cumulative 2017 list;\nAccessed Oct 22, 2026',
                'Pulled from pages.stern.nyu.edu (fintech_classification.xlsx, SHA-256: bc59ce16...). Identifies 18 online-origination lenders by RSSD ID (15 active in 2025 HMDA; 14 in controlled baseline).'
            ],
            [
                'Philadelphia Fed HMDA Lender File (2018–2025)',
                'Version Jul 15, 2026;\nAccessed Oct 22, 2026',
                'Fetched via classify_lenders_nyu.py from philadelphiafed.org (SHA-256: a7e72d98...). Bridges 2025 HMDA LEIs to Federal Reserve RSSD IDs and institution TYPE codes (banks 10/14/20; nonbanks 40/41).'
            ],
        ],
        col_widths=[2400, 2200, 5900],
    ))

    # 2. Data Pipeline & Key Measures (8 pts)
    parts.append(section_heading('2. Data Pipeline, Transformations, and Key Measures'))
    parts.append(bullet_p(
        'Step 1 — HMDA Extract (download_hmda.py -> mortgages_2025.csv, 1,508,076 loans): ',
        'Streams the LAR archive, joins lender names on LEI, and filters to originated (action_taken=1), conventional (loan_type=1), first-lien (lien_status=1), owner-occupied (occupancy_type=1), home-purchase (loan_purpose=1), conforming (C), 30-year fixed-rate (loan_term=360, intro_rate_period=NA) loans.'
    ))
    parts.append(bullet_p(
        'Step 2 — Lender Classification (classify_lenders_nyu.py -> mortgages_2025_classified.csv): ',
        'Maps LEI -> RSSD ID and TYPE via the Philadelphia Fed file. Tags NYU lenders as Fintech (175,928 loans; 15 lenders) and non-NYU depository banks (TYPE 10/14/20) as the Bank comparator (347,634 loans; 662 lenders). Non-fintech independent mortgage banks (TYPE 40/41) are tracked separately as an alternative comparator.'
    ))
    parts.append(bullet_p(
        'Step 3 — Lossless Cleaning & Binning (clean_mortgages.py -> mortgages_2025_clean.csv): ',
        'Retains all 1,508,076 rows and raw strings (NA, Exempt, zeroes) while adding parsed numeric fields, anomaly flags, and 4 risk bins: Standard DTI (<30%, 30%-<36%, 36%-43%, 44%-49%), CLTV (<=80%, 80.01%-90%, 90.01%-95%, >95%), Income (<=$75k, $75k-$125k, $125k-$200k, >$200k), and Loan Size (<=$200k, $200k-$350k, $350k-$500k, >$500k).'
    ))
    parts.append(bullet_p(
        'Step 4 & 5 — Pricing Metrics & Dashboard (analyze_pricing.py & build_dashboard.py): ',
        'Evaluates the controlled baseline (valid DTI, CLTV, income, loan size, and DTI <50%: 511,199 loans — 173,033 Fintech vs. 338,166 Bank) across three metrics: (1) Main: Rate-Spread Gap = 100 * (Median Spread_Fintech - Median Spread_Bank) (+16.4 bps: 0.213% vs. 0.049%); (2) Upfront Fee Ratio = 100 * (origination_charges / loan_amount) (+37.2 bps: 0.947% vs. 0.575%); (3) Interest Rate (+12.5 bps: 6.625% vs. 6.500%).'
    ))

    # 3. Reproducibility & Parameters (5 pts)
    parts.append(section_heading('3. Reproducibility, Parameters, and Assumptions'))
    parts.append(bullet_p(
        'Pipeline Execution (project_audible_data/README.md): ',
        'Run in sequence from project_audible_data/: python3 download_hmda.py -> classify_lenders_nyu.py -> clean_mortgages.py -> analyze_pricing.py -> build_dashboard.py -> build_position_memo.py. Run tests via python3 -m unittest -v (Python 3.10+ standard library; pandas and openpyxl required only for Step 2).'
    ))
    parts.append(bullet_p(
        'Core Parameters & Assumptions: ',
        '(1) Cell coverage threshold: >=100 loans/side, >=3 Fintech lenders, >=10 Bank lenders; (2) Materiality threshold: >= +5.0 bps gap; (3) Conforming DTI cap: <50% (Fannie/Freddie automated limit, covering 99.6% of valid-DTI loans); (4) Missing values (NA/Exempt) are never imputed as zero, while $0 fees are kept as valid; (5) Public HMDA omits credit scores (FICO) and rate-lock dates.'
    ))

    # 4. Design Choices Justified (4 pts)
    parts.append(section_heading('4. Justification of Design Choices (Chosen vs. Tried and Rejected)'))
    parts.append(bullet_p(
        'Stratified Medians & IQR (p25–p75) Over Means/OLS: ',
        'Mortgage rate spreads and fee ratios exhibit skewed tails. Comparing non-parametric medians and IQRs across the 16 DTI x CLTV cells (Fintech higher in all 16 of 16 cells, +10.3 to +31.6 bps) controls for observable risk without outlier distortion.'
    ))
    parts.append(bullet_p(
        'Rejected #1 — Including DTI >=50% and Incomplete Borrower Rows in Baseline: ',
        'An initial unadjusted run (+17.2 bps) included DTI >=50% (<0.4% of loans), producing a misleading +197.3 bps spike driven by 499 manufactured-housing loans from 21st Mortgage with missing CLTV (CLTV=NA). Restricting the baseline to complete 4-variable rows with DTI <50% (511,199 loans; +16.4 bps) eliminated missing-CLTV distortion and made all dashboard views 100% additive.'
    ))
    parts.append(bullet_p(
        'Rejected #2 — Raw Dollar Fees & Pooled Nonbank Benchmark: ',
        'Raw dollar origination_charges were rejected because they scale with loan size; dividing by loan_amount standardizes upfront cost. Pooling non-NYU mortgage companies into the main benchmark was also rejected because many unlisted nonbanks lend online; we use depository banks (TYPE 10/14/20) as the main benchmark and test non-fintech nonbanks (TYPE 40/41; -1.2 bps gap) separately.'
    ))

    sect_pr = (
        '<w:sectPr>'
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="720" w:right="864" w:bottom="720" w:left="864" '
        'w:header="432" w:footer="432" w:gutter="0"/>'
        '</w:sectPr>'
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_MAIN}">'
        f'<w:body>{"".join(parts)}{sect_pr}</w:body>'
        '</w:document>'
    )


def main():
    base_dir = Path(__file__).resolve().parent.parent
    template_docx = base_dir / 'Project Audible Initial Pitch AFC.docx'
    submit_dir = base_dir / 'Submit'
    submit_dir.mkdir(parents=True, exist_ok=True)
    out_docx = submit_dir / 'Project Audible Technical Memo.docx'

    doc_xml = build_document_xml().encode('utf-8')

    with ZipFile(template_docx, 'r') as zin:
        with ZipFile(out_docx, 'w', compression=ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == 'word/document.xml':
                    zout.writestr(item, doc_xml)
                else:
                    zout.writestr(item, zin.read(item.filename))

    print(f'Wrote {out_docx} ({out_docx.stat().st_size / 1024:.1f} KiB)')


if __name__ == '__main__':
    main()
