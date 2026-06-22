"""Born-digital PDF table extraction via pdfplumber (dual line/text strategy).

Ported from the legacy Self_KPI_Extraction `pdf_table_service.py`. For each page
we run both a 'lines' (ruled tables) and a 'text' (whitespace-aligned) strategy
and keep whichever yields more cells — then emit `ExtractedTable` objects.
"""
from __future__ import annotations

import logging
from typing import List, Set

import pdfplumber

from .models import ExtractedTable

logger = logging.getLogger(__name__)

_STRATEGIES = [
    {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
    {"vertical_strategy": "text", "horizontal_strategy": "text"},
]


def _norm_cell(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    text = str(val).strip()
    return text if text else None


def has_extractable_tables(pdf_path: str) -> bool:
    """Cheap check: does pdfplumber find any ruled/text tables at all?

    Used by the engine to decide whether to fall back to OCR for a scanned PDF.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for strat in _STRATEGIES:
                    if page.extract_tables(table_settings=strat):
                        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("pdfplumber probe failed for %s: %s", pdf_path, exc)
    return False


def extract(pdf_path: str, page_filter: Set[int] | None = None) -> List[ExtractedTable]:
    """Extract structured tables from a born-digital PDF.

    page_filter: optional 1-based set of pages to limit extraction to.
    """
    tables: List[ExtractedTable] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pidx, page in enumerate(pdf.pages, start=1):
            if page_filter is not None and pidx not in page_filter:
                continue

            best: List[list] = []
            best_strat_lines = True
            for i, strat in enumerate(_STRATEGIES):
                try:
                    found = page.extract_tables(table_settings=strat) or []
                    found = [
                        [[_norm_cell(c) for c in (row or [])] for row in (tbl or [])]
                        for tbl in found
                    ]
                    if _cell_count(found) > _cell_count(best):
                        best = found
                        best_strat_lines = i == 0
                except Exception as exc:  # pylint: disable=broad-except
                    logger.debug("extraction failed on p%s with %s: %s", pidx, strat, exc)

            for tidx, grid in enumerate(best):
                tbl = ExtractedTable(
                    page=pidx,
                    index=tidx,
                    rows=grid,
                    source="pdfplumber",
                    # ruled tables are more reliable than whitespace-aligned ones
                    confidence=0.95 if best_strat_lines else 0.8,
                )
                if tbl.is_meaningful():
                    tables.append(tbl)
    return tables


def _cell_count(grids: List[list]) -> int:
    return sum(len(r) for t in grids for r in t)
