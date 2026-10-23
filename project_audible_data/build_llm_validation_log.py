#!/usr/bin/env python3
"""Generate the Word LLM Validation Log in Submit/Project Audible LLM Validation Log.docx."""
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


def p_xml(runs: list[str], before: int = 20, after: int = 20, line: int = 210,
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
        before=75, after=28, line=215, bottom_border=True
    )


def bullet_p(lead: str, body: str, size_half_pt: int = 18) -> str:
    return p_xml(
        [
            r_xml('• ', bold=True, size_half_pt=size_half_pt, color='B45309'),
            r_xml(lead, bold=True, size_half_pt=size_half_pt, color='0F172A'),
            r_xml(body, bold=False, size_half_pt=size_half_pt, color='1E293B'),
        ],
        before=14, after=18, line=206, left_indent=180, hanging=180
    )


def table_xml(headers: list[str], rows: list[list[str]], col_widths: list[int]) -> str:
    total_w = sum(col_widths)
    grid_cols = ''.join(f'<w:gridCol w:w="{w}"/>' for w in col_widths)

    def cell_xml(text: str, width: int, is_header: bool = False, bold_first: bool = False) -> str:
        shd = '<w:shd w:val="clear" w:color="auto" w:fill="F1F5F9"/>' if is_header else ''
        run = r_xml(
            text,
            bold=(is_header or bold_first),
            size_half_pt=16,
            color='0F172A' if (is_header or bold_first) else '1E293B',
        )
        return (
            f'<w:tc>'
            f'<w:tcPr>'
            f'<w:tcW w:w="{width}" w:type="dxa"/>'
            f'{shd}'
            f'<w:tcMar>'
            f'<w:top w:w="26" w:type="dxa"/><w:bottom w:w="26" w:type="dxa"/>'
            f'<w:left w:w="60" w:type="dxa"/><w:right w:w="60" w:type="dxa"/>'
            f'</w:tcMar>'
            f'</w:tcPr>'
            f'{p_xml([run], before=6, after=6, line=192)}'
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
    ], before=0, after=12, line=215))
    parts.append(p_xml([
        r_xml('Author & Human Owner: ', bold=True, size_half_pt=18, color='B45309'),
        r_xml('Angga Lesmana   |   ', size_half_pt=18, color='334155'),
        r_xml('Topic: ', bold=True, size_half_pt=18, color='B45309'),
        r_xml('Fintech vs. Bank Mortgage Pricing (AFC)   |   ', size_half_pt=18, color='334155'),
        r_xml('Date: ', bold=True, size_half_pt=18, color='B45309'),
        r_xml('October 22, 2026', size_half_pt=18, color='334155'),
    ], before=0, after=36, line=205, bottom_border=True))

    # 1. Complete Inventory & Prompts/Outputs Recorded (Rubric Criteria 1 & 2: 11 pts)
    parts.append(section_heading('1. Complete LLM Inventory, Prompts, and Recorded Outputs'))
    parts.append(table_xml(
        headers=['Stage & Date', 'Tool & Model / Version', 'Key Prompts (Summary / Verbatim)', 'Outputs Used & Linked Artifacts'],
        rows=[
            [
                '1. Pitch Revision (Oct 22, 2026, 13:00–14:15)',
                'OpenAI Codex Agent (codex-primary-runtime v26.1017.22136)',
                '"On my initial pitch file, my professor gave me a note: Who is the audience, and what is the decision?" -> "How about if the audience is the FinTech Association?... AFC or FTA? give me a more straightforward proposed decision"',
                'Project Audible Initial Pitch AFC.docx (reframed around American Fintech Council leadership deciding whether to launch a member mortgage-pricing review).'
            ],
            [
                '2. HMDA Extraction (Oct 22, 2026, 17:30–18:15)',
                'OpenAI Codex Agent (v26.1017.22136)',
                '"For the dataset, is it enough to use one data point?" -> "Create a python code to automatically download the data that I need" -> "Jelasin per function di python code kita... ada data yang missing ga?"',
                'download_hmda.py, test_download_hmda.py, mortgages_2025.csv (1,508,076 loans), lender_inventory_2025.csv (2,378 lenders), manifest.json, sample_summary.json.'
            ],
            [
                '3. Lender Classification (Oct 22, 2026, 18:15–19:50)',
                'OpenAI Codex Agent (v26.1017.22136)',
                '"Bantu saya cari kriteria fintech, seinget saya NYU pernah ada publikasi... bantu saya periksa data NYU dan 51 lainnya dari riset si Buchak... kasih hasilnya kesini, nanti saya yang memutuskan" -> "Ok gas langsung pakai yang NYU"',
                'classify_lenders_nyu.py, test_classify_lenders_nyu.py, lender_classification_2025.csv, mortgages_2025_classified.csv (15 NYU Fintechs vs. 662 Philadelphia Fed TYPE 10/14/20 banks).'
            ],
            [
                '4. Data Cleansing (Oct 22, 2026, 19:54–20:30)',
                'Google Antigravity (Claude Opus 4.5 & Gemini 3.1 Pro)',
                '"Cek folder project audible ini, terus baca chat history saya dengan AI agent sebelumnya" -> "Kenapa kita pakai origination_charges / loan?" -> "Buat salinan data untuk cleansing... langkah2 selanjutnya?"',
                'clean_mortgages.py, test_clean_mortgages.py, mortgages_2025_clean.csv, and data_quality/ audit tables (missingness_by_group.csv, indicator_eligibility.csv).'
            ],
            [
                '5. Pricing Analysis & Dashboard (Oct 22, 2026, 20:30–22:25)',
                'Google Antigravity (Gemini 3.1 Pro)',
                '"Buat 3 tab... key point buat straightforward... yang DTI > 50% ini aga misleading ga si? diskusi dulu... ini narasinya tetep pake yang 17.2 bps? bukannya kalau di takeout cuma jadi 16.4 bps?" -> "Opsi A aja yang pake Definisi #4"',
                'analyze_pricing.py, build_dashboard.py, build_technical_memo.py, Submit/Project Audible Dashboard.html, and Submit/Project Audible Technical Memo.docx.'
            ],
        ],
        col_widths=[1650, 1850, 3850, 3150],
    ))

    # 2. Validation Shown: Errors Found, Challenged, and Corrected (Rubric Criterion 3: 6 pts)
    parts.append(section_heading('2. Validation Shown: How LLM Outputs Were Checked and Errors Corrected'))
    parts.append(bullet_p(
        '1. Rejected Invalid Audiences & Weak "Now What" in Initial Pitch (Session 1): ',
        'The LLM initially proposed a North Carolina housing counseling organization and later a consumer-finance editor. I challenged both: (a) checking HUD Housing Counseling Handbook 7610.1 confirmed counselors are prohibited from steering buyers to specific lender types, and (b) a consumer-finance editor lacked an operational decision ("Now What") for the 30-second rubric test. I proposed a U.S. Fintech association (analogous to Indonesia\'s AFTECH) and selected the American Fintech Council (AFC) deciding on a member pricing review. I also caught the contradiction between the title ("Are Fintech Mortgages Cheaper?") and our hypothesis, directing an explicit hypothesis that Fintechs price higher.'
    ))
    parts.append(bullet_p(
        '2. Fixed FFIEC HTTP Rejection, Folder Path Mismatch & Verified Fixed-Rate Rules (Session 1): ',
        'During live execution of download_hmda.py, FFIEC rejected default urllib headers and the raw 2025 LAR CSV schema differed from draft expectations; this was fixed with custom academic headers, ETag resume checks, and exact field mapping. When I noticed the files were downloaded into an old folder (590 Assignment/), I moved them to Project Audible/ and required a full SHA-256 hash verification against manifest.json (confirming 1,508,076 loans and zero byte corruption). I also verified against CFPB Reg C §1003.4(a)(26) why intro_rate_period = NA is required to isolate 30-year fixed-rate loans.'
    ))
    parts.append(bullet_p(
        '3. Audited NYU (Fuster et al.) vs. Buchak et al. Lists & Resolved RSSD-to-LEI ID Mismatch (Session 1): ',
        'Rather than letting the LLM guess Fintech labels, I manually downloaded the NYU Stern Excel file (fintech_classification.xlsx) and instructed the agent to cross-audit it against Buchak et al. (2018/2019). The audit revealed that NYU uses Federal Reserve RSSD IDs while 2025 HMDA uses LEIs, that Buchak\'s "51 fintechs" contained duplicate rows (CashCall listed twice) and banks/credit unions, and that the two lists conflicted on 6 lenders (e.g., Everett, Envoy, Evergreen). We solved the ID gap via the Philadelphia Fed HMDA Lender File (LEI -> RSSD ID) and I locked in the NYU list (15 matched Fintechs) vs. 662 regulated depository banks (TYPE 10, 14, 20).'
    ))
    parts.append(bullet_p(
        '4. Corrected Naive Missing-Value Handling in Exploratory Code (Session 2): ',
        'An early exploratory script (cekdata.py) used pandas na_values=["NA", "Exempt", ""], which conflated distinct HMDA regulatory codes into generic NaNs and failed when the local pandas environment lacked dateutil. We replaced it with a pure standard-library pipeline (clean_mortgages.py) verified by unit tests (test_clean_mortgages.py) that preserves all 1,508,076 raw rows, distinguishes valid 0.0 origination fees (5,048 Fintech and 23,803 Bank zero-fee loans) from NA/Exempt, and preserves HMDA text DTI ranges (<20%, 20%-<30%, 30%-<36%) alongside exact integers (36–49).'
    ))
    parts.append(bullet_p(
        '5. Caught the DTI >=50% / 21st Mortgage Distortion & Reconciled the +17.2 vs. +16.4 bps Headline (Session 2): ',
        'Reviewing the first dashboard draft, I noticed that DTI >=50% had missing/Low-N bank comparisons in CLTV >80% and asked whether DTI >=50% was misleading. Auditing the loan records confirmed that 99.6% of conforming loans have DTI <50% (the Fannie/Freddie automated underwriting cap), and 69% (499 of 719) of Fintech loans in DTI >=50% came from one manufactured-housing lender (21st Mortgage) with missing CLTV (CLTV=NA), creating an artificial +197.3 bps spike in the 1D DTI chart. After removing DTI >=50%, I caught that the LLM still displayed the unadjusted +17.2 bps headline instead of the controlled +16.4 bps figure. We reconciled the entire dashboard to Definition #4 (all 4 borrower variables valid + standard DTI <50%: 511,199 loans, +16.4 bps), making all KPIs, bar charts, and the 16 DTI x CLTV cells 100% additive.'
    ))
    parts.append(bullet_p(
        '6. Rejected Cluttered Dashboard UI & Enforced Visual, Straightforward Design (Session 2): ',
        'I rejected the LLM\'s initial single-page dashboard because it was overly dense, included an unnecessary Presentation Mode button, buried key takeaways in wordy boxes, showed redundant robustness rows (Ex-Rocket, Ex-Top-2, Common Subset), and used a plain text table for the Selected Segment drill-down. I directed a clean 3-tab layout with minimalist top tabs, a full-width balanced slicer bar, direct "higher" wording instead of "premium", and an IQR (p25–p75) + paired-bar visual comparison card.'
    ))

    # 3. Clear Human Ownership (Rubric Criterion 4: 3 pts)
    parts.append(section_heading('3. Clear Human Ownership (Decisions and Numbers Verified by Human)'))
    parts.append(bullet_p(
        'Strategic & Methodological Decisions Owned by Angga Lesmana: ',
        '(1) Selected the American Fintech Council (AFC) audience and member pricing review decision; (2) Chose the NYU Stern (Fuster et al., 2019) Fintech classification over Buchak et al. after reviewing the overlap/conflict audit, and approved the 662 Philadelphia Fed depository bank comparator (TYPE 10/14/20); (3) Mandated lossless non-imputation of missing HMDA fields and verified the economic rationale of normalizing upfront fees via origination_charges / loan_amount; (4) Identified the DTI >=50% anomaly, decided to focus segmentation on the 4 standard conforming DTI bands (<50%), and chose the 4-variable valid controlled sample (+16.4 bps) over the unadjusted sample (+17.2 bps) for mathematical consistency.'
    ))
    parts.append(bullet_p(
        'Final Numbers & Visuals Verified by Human: ',
        'Personally verified all headline and segment metrics reported in the dashboard and memos: 1,508,076 total conforming loans extracted; 511,199 controlled comparison loans (173,033 Fintech across 14 lenders vs. 338,166 Bank across 655 lenders); +16.4 bps median rate-spread gap (0.213% vs. 0.049%); +12.5 bps median interest-rate gap (6.625% vs. 6.500%); +37.2 bps median upfront origination-fee gap (0.947% vs. 0.575%); Fintech pricing higher in 16 of 16 standard DTI x CLTV segments (peaking at +27.9 to +31.6 bps in CLTV >95%) and 12 of 14 controlled Fintech lenders.'
    ))

    sect_pr = (
        '<w:sectPr>'
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="680" w:right="792" w:bottom="680" w:left="792" '
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
