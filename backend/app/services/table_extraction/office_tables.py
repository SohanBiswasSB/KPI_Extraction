"""Office-format table extraction: Excel, CSV, and DOCX.

Unlike the legacy platform (which flattened everything with df.to_string()),
this preserves real row/column structure as `ExtractedTable` grids.
"""
from __future__ import annotations

import logging
from typing import List

import pandas as pd

from .models import ExtractedTable

logger = logging.getLogger(__name__)


def _df_to_rows(df: pd.DataFrame) -> List[list]:
    """Header row followed by data rows, with NaN -> None."""
    header = [str(c) for c in df.columns]
    body = df.where(pd.notnull(df), None).values.tolist()
    return [header] + body


def extract_excel(path: str) -> List[ExtractedTable]:
    """One ExtractedTable per non-empty sheet."""
    tables: List[ExtractedTable] = []
    xls = pd.ExcelFile(path)
    for sidx, sheet in enumerate(xls.sheet_names, start=1):
        df = pd.read_excel(path, sheet_name=sheet)
        if df.empty:
            continue
        tables.append(ExtractedTable(
            page=sidx, index=0, rows=_df_to_rows(df),
            source="excel", sheet_name=sheet, confidence=1.0,
        ))
    return tables


def extract_csv(path: str) -> List[ExtractedTable]:
    """Extract a CSV file as a single structured table."""
    df = pd.read_csv(path)
    if df.empty:
        return []
    return [ExtractedTable(page=1, index=0, rows=_df_to_rows(df), source="csv", confidence=1.0)]


def extract_docx(path: str) -> List[ExtractedTable]:
    """Every <w:tbl> in the document becomes an ExtractedTable."""
    from docx import Document  # imported lazily; heavy-ish and optional

    doc = Document(path)
    tables: List[ExtractedTable] = []
    for tidx, table in enumerate(doc.tables):
        rows: List[list] = []
        for row in table.rows:
            rows.append([(cell.text.strip() or None) for cell in row.cells])
        tbl = ExtractedTable(page=1, index=tidx, rows=rows, source="docx", confidence=1.0)
        if tbl.is_meaningful():
            tables.append(tbl)
    return tables
