#!/usr/bin/env python3
"""Generate the concise 1-page Word LLM Validation Log in Submit/Project Audible LLM Validation Log.docx."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

W_MAIN = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def r_xml(text: str, bold: bool = False, italic: bool = False, size_half_pt: int = 18,
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


def p_xml(runs: list[str], before: int = 24, after: int = 24, line: int = 220,
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
        before=90, after=36, line=220, bottom_border=True
    )


def bullet_p(lead: str, body: str, size_half_pt: int = 18) -> str:
    return p_xml(
        [
            r_xml('• ', bold=True, size_half_pt=size_half_pt, color='B45309'),
            r_xml(lead, bold=True, size_half_pt=size_half_pt, color='0F172A'),
            r_xml(body, bold=False, size_half_pt=size_half_pt, color='1E293B'),
        ],
        before=20, after=24, line=216, left_indent=180, hanging=180
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
            f'<w:top w:w="36" w:type="dxa"/><w:bottom w:w="36" w:type="dxa"/>'
            f'<w:left w:w="70" w:type="dxa"/><w:right w:w="70" w:type="dxa"/>'
            f'</w:tcMar>'
            f'</w:tcPr>'
            f'{p_xml([run], before=10, after=10, line=200)}'
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

    # Title Block
    parts.append(p_xml([
        r_xml('FINTECH 590 — PROJECT AUDIBLE: LLM VALIDATION LOG', bold=True, size_half_pt=22, color='0F172A'),
    ], before=0, after=14, line=220))
    parts.append(p_xml([
        r_xml('Human Owners: ', bold=True, size_half_pt=18, color='B45309'),
        r_xml('Angga Lesmana & Violla Tania   |   ', size_half_pt=18, color='334155'),
        r_xml('Topic: ', bold=True, size_half_pt=18, color='B45309'),
        r_xml('Fintech vs. Bank Mortgage Pricing (AFC)   |   ', size_half_pt=18, color='334155'),
        r_xml('Date: ', bold=True, size_half_pt=18, color='B45309'),
        r_xml('October 22–26, 2026', size_half_pt=18, color='334155'),
    ], before=0, after=40, line=210, bottom_border=True))

    # 1. Complete Inventory & Prompts/Outputs Recorded
    parts.append(section_heading('1. LLM Inventory, Prompts, and Recorded Outputs'))
    parts.append(table_xml(
        headers=['Stage & Date', 'Tool & Model', 'Key Human Prompts (Translated / Verbatim)', 'Outputs Used & Artifacts'],
        rows=[
            [
                '1. Pitch Framing\n(Oct 22, 2026)',
                'OpenAI Codex\n(v26.1017)',
                '"My professor asked: Who is the audience, and what is the decision?" -> "What if the audience is the American Fintech Council (AFC)? Give me a straightforward operational decision."',
                'Project Audible Initial Pitch AFC.docx (framed around AFC leadership deciding on a member pricing review).'
            ],
            [
                '2. HMDA Extraction\n(Oct 22, 2026)',
                'OpenAI Codex\n(v26.1017)',
                '"Write Python code to download and filter the 2025 HMDA data." -> "Explain each function and check which pricing fields are missing."',
                'download_hmda.py, test_download_hmda.py, mortgages_2025.csv (1,508,076 loans), manifest.json.'
            ],
            [
                '3. Lender Matching\n(Oct 22, 2026)',
                'OpenAI Codex\n(v26.1017)',
                '"Compare published Fintech lender lists (NYU Stern vs. Buchak et al.) on our 2025 HMDA sample so I can decide." -> "Proceed with the NYU Stern list."',
                'classify_lenders_nyu.py, mortgages_2025_classified.csv (15 NYU Fintechs vs. 662 TYPE 10/14/20 banks).'
            ],
            [
                '4. Data Cleansing\n(Oct 22, 2026)',
                'Google Antigravity\n(Claude Opus 4.5 & Gemini 3.1 Pro)',
                '"Review the project folder and prior session history." -> "Why normalize origination_charges by loan_amount?" -> "Create a lossless cleaned copy and audit tables."',
                'clean_mortgages.py, test_clean_mortgages.py, mortgages_2025_clean.csv, data_quality/ reports.'
            ],
            [
                '5. Analysis & UI\n(Oct 22, 2026)',
                'Google Antigravity\n(Gemini 3.1 Pro)',
                '"Make a clean 3-tab dashboard with straightforward takeaways." -> "Isn\'t DTI >=50% misleading since banks lack CLTV >80% there?" -> "Once DTI >=50% is excluded, use the +16.4 bps 4-variable baseline."',
                'analyze_pricing.py, build_dashboard.py, build_technical_memo.py, Dashboard.html, Technical Memo.docx.'
            ],
            [
                '6. Peer Review\n(Oct 25, 2026)',
                'Claude (claude.ai)\nClaude Opus 5.5',
                '"Review the repository against the rubric, challenge the Fintech vs. nonbank classification, and draft the position memo."',
                'build_position_memo.py, Position Memo.docx, nonbank TYPE 40/41 robustness check, updated tests.'
            ],
        ],
        col_widths=[1550, 1750, 3950, 3250],
    ))

    # 2. Validation Shown: Errors Found, Challenged, and Corrected
    parts.append(section_heading('2. Validation Shown: LLM Errors Challenged and Corrected'))
    parts.append(bullet_p(
        '1. Rejected Invalid Audiences (Session 1): ',
        'Rejected the LLM\'s housing-counselor and finance-editor pitches after checking HUD Handbook 7610.1 (counselors cannot steer borrowers to specific lender types) and the rubric\'s "Now What" requirement. Selected AFC leadership deciding on a Q1 2027 member pricing review.'
    ))
    parts.append(bullet_p(
        '2. Audited Fintech Lists & Resolved ID Mismatch (Session 1): ',
        'Manually supplied the NYU Stern Excel list and directed a cross-audit against Buchak et al., exposing duplicate rows and bank/credit-union contamination in Buchak\'s list. Bridged the 2017 RSSD ID to 2025 LEI gap using the Philadelphia Fed Lender File.'
    ))
    parts.append(bullet_p(
        '3. Replaced Naive Missing-Value Handling (Session 2): ',
        'Rejected early exploratory code that treated "NA", "Exempt", and blanks as identical NaNs. Built a standard-library pipeline (clean_mortgages.py) that preserves all 1,508,076 rows, keeps valid $0 origination fees (28,851 loans), and parses both text DTI bands and exact integers.'
    ))
    parts.append(bullet_p(
        '4. Caught DTI >=50% Distortion & Reconciled +16.4 bps Headline (Session 2): ',
        'Questioned why DTI >=50% lacked bank comparisons at high CLTV; loan-level inspection showed 99.6% of conforming loans have DTI <50% and 69% of Fintech DTI >=50% loans came from one manufactured-housing lender (21st Mortgage) with missing CLTV. Excluded DTI >=50% and corrected the headline from +17.2 bps (unadjusted) to +16.4 bps (controlled baseline).'
    ))
    parts.append(bullet_p(
        '5. Redesigned Dashboard & Added Nonbank Comparator (Sessions 2 & 3): ',
        'Replaced a dense single-page draft with a clean 3-tab layout and visual IQR/bar comparisons. During peer review, rejected a false LLM claim that static HTML lacked data, fixed unverified README figures, and added a non-fintech nonbank (TYPE 40/41) comparator. Its result (-1.2 bps) led the team to reframe the recommendation as a review benchmarked against nonbank peers.'
    ))

    # 3. Clear Human Ownership
    parts.append(section_heading('3. Clear Human Ownership (Decisions and Verified Numbers)'))
    parts.append(bullet_p(
        'Methodology & Design Owned by Humans: ',
        'Angga Lesmana selected the AFC audience, NYU Stern classification, depository bank benchmark (TYPE 10/14/20), fee normalization (origination_charges / loan_amount), conforming DTI <50% scope, and 3-tab dashboard design. Violla Tania directed the peer review, non-fintech nonbank robustness check (TYPE 40/41), and Position Memo structure.'
    ))
    parts.append(bullet_p(
        'Final Figures Verified Against Pipeline Outputs: ',
        '1,508,076 conforming loans extracted; 511,199 controlled baseline loans (173,033 Fintech across 14 lenders vs. 338,166 Bank across 655 lenders); +16.4 bps median rate-spread gap (0.213% vs. 0.049%; lender-clustered 95% CI: +11.5 to +23.3 bps); +12.5 bps rate gap; +37.2 bps origination-fee gap; Fintech higher in 16 of 16 DTI x CLTV cells and 12 of 14 lenders; -1.2 bps spread gap vs. 600 non-fintech nonbanks (808,681 loans).'
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
    out_docx = submit_dir / 'Project Audible LLM Validation Log.docx'

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
