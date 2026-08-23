"""
Load government schemes from the CSV file.

The CSV lives at: web-scraping/4000_data.csv
Each row = one scheme with columns like Description, Eligibility, Benefits, etc.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SchemeRecord:
    """One scheme row from the CSV, with all fields we care about."""

    name: str
    short_title: str
    slug: str
    url: str
    description: str
    level: str
    ministry: str
    department: str
    state: str
    beneficiary_state: str
    scheme_for: str
    tags: str
    categories: str
    target_beneficiaries: str
    sub_categories: str
    open_date: str
    close_date: str
    implementing_agency: str
    # Section text (used by the chunker)
    details_md: str
    benefits_md: str
    eligibility_md: str
    application_md: str
    documents_md: str
    faqs_md: str
    sources: str

    @classmethod
    def from_row(cls, row: pd.Series) -> "SchemeRecord":
        def cell(key: str) -> str:
            value = row.get(key, "")
            if pd.isna(value):
                return ""
            return str(value).strip()

        return cls(
            name=cell("Scheme Name"),
            short_title=cell("Short Title"),
            slug=cell("Slug"),
            url=cell("Scheme URL"),
            description=cell("Description"),
            level=cell("Level"),
            ministry=cell("Nodal Ministry"),
            department=cell("Nodal Department"),
            state=cell("State"),
            beneficiary_state=cell("Beneficiary State"),
            scheme_for=cell("Scheme For"),
            tags=cell("Tags"),
            categories=cell("Categories (All)"),
            target_beneficiaries=cell("Target Beneficiaries"),
            sub_categories=cell("Sub Categories"),
            open_date=cell("Open Date"),
            close_date=cell("Close Date"),
            implementing_agency=cell("Implementing Agency"),
            details_md=cell("Details (markdown)") or cell("Description"),
            benefits_md=cell("Benefits (markdown)"),
            eligibility_md=cell("Eligibility (markdown)"),
            application_md=cell("Application Process (markdown)"),
            documents_md=cell("Documents Required (markdown)"),
            faqs_md=cell("FAQs (markdown)"),
            sources=cell("Sources & References"),
        )


def load_schemes(csv_path: Path = None) -> list[SchemeRecord]:
    """Read the CSV and return a list of SchemeRecord objects."""
    path = csv_path or settings.schemes_csv_path
    if not path.exists():
        raise FileNotFoundError(f"Scheme CSV not found: {path}")

    df = pd.read_csv(path)
    records = [SchemeRecord.from_row(row) for _, row in df.iterrows()]
    logger.info("Loaded %d schemes from %s", len(records), path.name)
    return records
