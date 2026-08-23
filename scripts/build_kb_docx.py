#!/usr/bin/env python3
"""
Build a DOCX knowledge base from web-scraping/4000_data.csv.

Includes only schemes that clearly match Agriculture, Education, Loan, or Finance
(plus official myscheme aliases such as Education & Learning and Banking,
Financial Services and Insurance).

Usage (from project root):
    python scripts/build_kb_docx.py
    python scripts/build_kb_docx.py --csv web-scraping/4000_data.csv --out data/knowledge/schemes_agriculture_education_loan_finance.docx
"""

from __future__ import annotations

import argparse
import html
import re
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt, RGBColor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = PROJECT_ROOT / "web-scraping" / "4000_data.csv"
DEFAULT_OUT = (
    PROJECT_ROOT
    / "data"
    / "knowledge"
    / "schemes_agriculture_education_loan_finance.docx"
)

# Official myscheme category aliases (CSV stores some of these without a space
# after the comma, e.g. "Agriculture,Rural & Environment").
AGRI_MARKERS = ("agriculture",)
EDU_MARKERS = ("education",)
BFSI_MARKERS = ("banking", "financial services")

# Whole tokens only — "Financial Assistance" is welfare grants, not finance.
LOAN_FINANCE_TAGS = frozenset({"loan", "finance"})
LOAN_FINANCE_SUBCATS = frozenset({"loan", "banking and money"})
LOAN_FINANCE_SUBCATS_SOFT = frozenset({"micro finance", "credit linked subsidy"})

# If a row only has these categories, do not pull it in via a soft finance signal.
EXCLUDED_ONLY_CATEGORIES = frozenset(
    {
        "social welfare & empowerment",
        "women and child",
        "health & wellness",
        "skills & employment",
        "sports & culture",
        "housing & shelter",
        "public safety",
        "law & justice",
        "utility & sanitation",
        "travel & tourism",
        "transport & infrastructure",
        "science",
        "it & communications",
    }
)

# Fields the chatbot / RAG pipeline actually uses (see SchemeRecord + chunker).
SCHEME_FIELDS = [
    ("Short Title", "Short Title"),
    ("Official URL", "Scheme URL"),
    ("Level", "Level"),
    ("State", "State"),
    ("Beneficiary State", "Beneficiary State"),
    ("Nodal Ministry", "Nodal Ministry"),
    ("Nodal Department", "Nodal Department"),
    ("Implementing Agency", "Implementing Agency"),
    ("Scheme For", "Scheme For"),
    ("Target Beneficiaries", "Target Beneficiaries"),
    ("Categories", "Categories (All)"),
    ("Sub Categories", "Sub Categories"),
    ("Tags", "Tags"),
    ("Open Date", "Open Date"),
    ("Close Date", "Close Date"),
]

SECTION_FIELDS = [
    ("Description", "Description"),
    ("Details", "Details (markdown)"),
    ("Benefits", "Benefits (markdown)"),
    ("Eligibility", "Eligibility (markdown)"),
    ("Documents Required", "Documents Required (markdown)"),
    ("How to Apply", "Application Process (markdown)"),
    ("FAQs", "FAQs (markdown)"),
    ("Sources & References", "Sources & References"),
]

GROUP_ORDER = ("Agriculture", "Education", "Loan", "Finance")

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
HEADING_RE = re.compile(r"^#{1,6}\s+")
WS_RE = re.compile(r"[ \t]+")
# XML 1.0 forbids most C0 controls (NULL, BEL, etc.). Keep tab only.
XML_UNSAFE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def sanitize_xml_text(text: str) -> str:
    text = html.unescape(text)
    text = BR_RE.sub("\n", text)
    return XML_UNSAFE_RE.sub("", text)


def cell(row: pd.Series, key: str) -> str:
    value = row.get(key, "")
    if pd.isna(value):
        return ""
    return sanitize_xml_text(str(value).strip())


def split_items(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def token_set(value: object) -> set[str]:
    return {part.lower() for part in split_items(value)}


def categories_match(cats: set[str], markers: tuple[str, ...]) -> bool:
    return any(any(marker in cat for marker in markers) for cat in cats)


def classify_row(row: pd.Series) -> tuple[str | None, list[str]]:
    """Return (primary_group, matched_labels) or (None, []) if excluded."""
    cats = token_set(row.get("Categories (All)"))
    tags = token_set(row.get("Tags"))
    subs = token_set(row.get("Sub Categories"))
    ministry = cell(row, "Nodal Ministry").lower()

    is_agri = categories_match(cats, AGRI_MARKERS)
    is_edu = categories_match(cats, EDU_MARKERS)
    is_bfsi = categories_match(cats, BFSI_MARKERS)
    is_loan_hard = bool(tags & LOAN_FINANCE_TAGS) or bool(subs & LOAN_FINANCE_SUBCATS)
    welfare_only = bool(cats) and cats <= EXCLUDED_ONLY_CATEGORIES
    is_loan_soft = bool(subs & LOAN_FINANCE_SUBCATS_SOFT) and not welfare_only
    is_mof = "finance" in ministry and not welfare_only

    if not (is_agri or is_edu or is_bfsi or is_loan_hard or is_loan_soft or is_mof):
        return None, []

    matched: list[str] = []
    if is_agri:
        matched.append("Agriculture")
    if is_edu:
        matched.append("Education")
    if "loan" in tags or "loan" in subs:
        matched.append("Loan")
    if is_bfsi or "finance" in tags or is_mof or is_loan_soft:
        if "Finance" not in matched:
            matched.append("Finance")
    elif is_loan_hard and "Loan" not in matched:
        matched.append("Loan")

    # One listing per scheme to keep the file small. Agriculture / Education win
    # over generic loan-finance when a row is clearly in those domains.
    if is_agri:
        primary = "Agriculture"
    elif is_edu:
        primary = "Education"
    elif "loan" in tags or "loan" in subs:
        primary = "Loan"
    else:
        primary = "Finance"

    return primary, matched


def is_placeholder_section(text: str) -> bool:
    """True for blank / punctuation-only long-form sections."""
    cleaned = re.sub(r"[\s\-–—*•.|/\\]+", "", text or "")
    return len(cleaned) < 12


def clean_inline(text: str) -> str:
    text = sanitize_xml_text(text)
    text = LINK_RE.sub(r"\1 (\2)", text)
    text = BOLD_RE.sub(r"\1", text)
    text = HEADING_RE.sub("", text)
    text = text.replace("**", "").replace("__", "")
    return WS_RE.sub(" ", text).strip()


def markdown_lines(text: str) -> list[str]:
    """Flatten markdown into compact display lines; drop empties."""
    if not text:
        return []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    prev_blank = True
    for raw in normalized.split("\n"):
        line = clean_inline(raw)
        if not line:
            if not prev_blank and lines:
                lines.append("")
            prev_blank = True
            continue
        prev_blank = False
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def set_run_font(run, size_pt: float | None = None, bold: bool | None = None) -> None:
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bold


def compact_paragraph_format(paragraph, after: float = 4, before: float = 0) -> None:
    fmt = paragraph.paragraph_format
    fmt.space_after = Pt(after)
    fmt.space_before = Pt(before)
    fmt.line_spacing_rule = WD_LINE_SPACING.SINGLE
    fmt.line_spacing = 1.0


def add_hyperlink(paragraph, text: str, url: str) -> None:
    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    new_run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "20")
    r_fonts = OxmlElement("w:rFonts")
    r_fonts.set(qn("w:ascii"), "Calibri")
    r_fonts.set(qn("w:hAnsi"), "Calibri")
    r_pr.append(r_fonts)
    r_pr.append(color)
    r_pr.append(underline)
    r_pr.append(sz)
    new_run.append(r_pr)
    text_el = OxmlElement("w:t")
    text_el.set(qn("xml:space"), "preserve")
    text_el.text = text
    new_run.append(text_el)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def configure_styles(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)
    normal.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.line_spacing = 1.0

    for style_name, size, before, after in (
        ("Title", 22, 0, 8),
        ("Heading 1", 16, 14, 6),
        ("Heading 2", 13, 10, 4),
        ("Heading 3", 11, 8, 2),
    ):
        style = document.styles[style_name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0x1A, 0x36, 0x5D)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.line_spacing = 1.0

    for section in document.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)


def add_body(document: Document, text: str, *, bold: bool = False) -> None:
    """One paragraph per section (line breaks inside) to keep the DOCX small."""
    lines = [line for line in markdown_lines(text) if line]
    if not lines:
        return
    para = document.add_paragraph()
    compact_paragraph_format(para)
    run = para.add_run("\n".join(lines))
    set_run_font(run, 10, bold)


def add_meta_line(document: Document, label: str, value: str, url: str | None = None) -> None:
    if not value:
        return
    para = document.add_paragraph()
    compact_paragraph_format(para, after=2)
    label_run = para.add_run(f"{label}: ")
    set_run_font(label_run, 10, True)
    if url and value.startswith("http"):
        add_hyperlink(para, value, url)
    else:
        value_run = para.add_run(value)
        set_run_font(value_run, 10, False)


def add_facts_block(document: Document, pairs: list[tuple[str, str]]) -> None:
    """Pack several short metadata fields into one paragraph."""
    parts = [f"{label}: {value}" for label, value in pairs if value]
    if not parts:
        return
    para = document.add_paragraph()
    compact_paragraph_format(para, after=4)
    run = para.add_run("  |  ".join(parts))
    set_run_font(run, 10, False)


def add_title_page(document: Document, counts: Counter[str], total: int, csv_name: str) -> None:
    title = document.add_paragraph("GovScheme Knowledge Base")
    title.style = document.styles["Title"]
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if title.runs:
        set_run_font(title.runs[0], 22, True)

    subtitle = document.add_paragraph(
        "Agriculture · Education · Loan · Finance"
    )
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    compact_paragraph_format(subtitle, after=10)
    if subtitle.runs:
        set_run_font(subtitle.runs[0], 13, False)

    intro = (
        "This document is the filtered knowledge base for the GovScheme WhatsApp "
        "chatbot. It contains only schemes that match Agriculture, Education, Loan, "
        "or Finance (including official myScheme aliases). Each scheme is listed "
        "once under a primary category. Overlaps are noted on the scheme page."
    )
    add_body(document, intro)

    add_meta_line(document, "Source", f"myScheme.gov.in via {csv_name}")
    add_meta_line(document, "Generated", date.today().isoformat())
    add_meta_line(document, "Schemes included", str(total))
    for group in GROUP_ORDER:
        add_meta_line(document, f"  {group}", str(counts.get(group, 0)))

    add_body(
        document,
        "Fields follow what the chatbot retrieves: name, eligibility, benefits, "
        "documents required, how to apply, official links, ministry/state, and FAQs. "
        "Empty fields are omitted. This is guidance only — confirm on the official site.",
    )


def add_index(document: Document, grouped: dict[str, list[dict]]) -> None:
    document.add_heading("Category index", level=1)
    add_body(
        document,
        "Word’s automatic table of contents is not used. Use this index, or the "
        "Navigation pane (Headings), to jump to a scheme.",
    )
    for group in GROUP_ORDER:
        rows = grouped.get(group, [])
        document.add_heading(f"{group} ({len(rows)})", level=2)
        names = []
        for i, item in enumerate(rows, start=1):
            line = item["name"]
            short = item["short_title"]
            if short:
                line = f"{line} ({short})"
            names.append(f"{i}. {line}")
        add_body(document, "\n".join(names))


def add_scheme(document: Document, item: dict) -> None:
    document.add_heading(item["name"], level=2)

    extras = [g for g in item["matched"] if g != item["group"]]
    if extras:
        add_meta_line(document, "Also matches", ", ".join(extras))

    row = item["row"]
    url = cell(row, "Scheme URL")
    if url:
        add_meta_line(document, "Official URL", url, url=url)

    add_facts_block(
        document,
        [
            ("Short Title", cell(row, "Short Title")),
            ("Level", cell(row, "Level")),
            ("State", cell(row, "State")),
            ("Beneficiary State", cell(row, "Beneficiary State")),
            ("Open Date", cell(row, "Open Date")),
            ("Close Date", cell(row, "Close Date")),
        ],
    )
    add_facts_block(
        document,
        [
            ("Nodal Ministry", cell(row, "Nodal Ministry")),
            ("Nodal Department", cell(row, "Nodal Department")),
            ("Implementing Agency", cell(row, "Implementing Agency")),
        ],
    )
    add_facts_block(
        document,
        [
            ("Scheme For", cell(row, "Scheme For")),
            ("Target Beneficiaries", cell(row, "Target Beneficiaries")),
            ("Categories", cell(row, "Categories (All)")),
            ("Sub Categories", cell(row, "Sub Categories")),
            ("Tags", cell(row, "Tags")),
        ],
    )

    details = cell(row, "Details (markdown)")
    description = cell(row, "Description")
    for label, key in SECTION_FIELDS:
        value = cell(row, key)
        if not value or is_placeholder_section(value):
            continue
        # Avoid repeating Description when Details is the same text.
        if key == "Description" and details and description and description[:200] in details:
            continue
        document.add_heading(label, level=3)
        add_body(document, value)


def load_schemes(csv_path: Path) -> tuple[list[dict], Counter[str], Counter[str]]:
    df = pd.read_csv(csv_path)
    included: list[dict] = []
    counts: Counter[str] = Counter()
    excluded_reasons: Counter[str] = Counter()

    for _, row in df.iterrows():
        primary, matched = classify_row(row)
        if not primary:
            cats = split_items(row.get("Categories (All)"))
            lead = cats[0] if cats else "Uncategorised"
            excluded_reasons[lead] += 1
            continue
        included.append(
            {
                "name": cell(row, "Scheme Name") or cell(row, "Short Title") or "Untitled scheme",
                "short_title": cell(row, "Short Title"),
                "slug": cell(row, "Slug"),
                "group": primary,
                "matched": matched,
                "row": row,
            }
        )
        counts[primary] += 1

    included.sort(key=lambda item: (GROUP_ORDER.index(item["group"]), item["name"].lower()))
    return included, counts, excluded_reasons


def build_document(
    csv_path: Path,
    schemes: list[dict],
    counts: Counter[str],
) -> Document:
    grouped: dict[str, list[dict]] = {g: [] for g in GROUP_ORDER}
    for item in schemes:
        grouped[item["group"]].append(item)

    document = Document()
    configure_styles(document)
    add_title_page(document, counts, len(schemes), csv_path.name)
    add_index(document, grouped)

    written = 0
    for group in GROUP_ORDER:
        rows = grouped[group]
        document.add_heading(f"{group} schemes", level=1)
        add_body(document, f"{len(rows)} schemes in this section.")
        for item in rows:
            add_scheme(document, item)
            written += 1
            if written % 250 == 0:
                print(f"  wrote {written}/{len(schemes)} schemes…", flush=True)
    return document


def verify_docx(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise RuntimeError(f"Output is not a valid DOCX zip: {path}")
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if "word/document.xml" not in names:
            raise RuntimeError("DOCX is missing word/document.xml")
        zf.read("word/document.xml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the filtered GovScheme DOCX knowledge base.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to 4000_data.csv")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output .docx path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    csv_path = args.csv.resolve()
    out_path = args.out.resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    schemes, counts, excluded = load_schemes(csv_path)
    print(f"Loaded {len(schemes)} matching schemes from {csv_path.name}", flush=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    document = build_document(csv_path, schemes, counts)
    print("Saving DOCX…", flush=True)
    document.save(out_path)
    verify_docx(out_path)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {out_path}")
    print(f"Size: {size_mb:.2f} MB")
    print(f"Schemes included: {len(schemes)}")
    for group in GROUP_ORDER:
        print(f"  {group}: {counts.get(group, 0)}")
    print(f"Schemes excluded: {sum(excluded.values())}")
    print("Excluded lead categories:")
    for name, n in excluded.most_common():
        print(f"  {n:5d}  {name}")
    if size_mb > 20:
        raise SystemExit(f"ERROR: file is {size_mb:.2f} MB (limit 20 MB)")


if __name__ == "__main__":
    main()
