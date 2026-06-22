"""Format-routing entry point for the unified table-extraction engine.

`extract_tables()` dispatches by file extension/MIME and applies the scanned-PDF
OCR fallback automatically. `export_tables()` writes a multi-sheet XLSX plus one
CSV per table. All backends return the common `ExtractedTable` shape.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import List, Optional, Set

from .models import ExtractedTable
from . import pdf_tables, office_tables, ocr_tables

logger = logging.getLogger(__name__)

# extension -> logical kind
_PDF = {".pdf"}
_EXCEL = {".xlsx", ".xls"}
_CSV = {".csv"}
_DOCX = {".docx"}
_IMAGE = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

SUPPORTED_EXTENSIONS = _PDF | _EXCEL | _CSV | _DOCX | _IMAGE


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def extract_tables(
    path: str,
    *,
    page_filter: Optional[Set[int]] = None,
    ocr_dpi: int = 200,
    ocr_lang: str = "eng",
    allow_ocr: bool = True,
) -> List[ExtractedTable]:
    """Extract structured tables from any supported document.

    For PDFs: try pdfplumber first; if it finds nothing and OCR is available,
    fall back to rendering + Tesseract (scanned/image PDFs).
    """
    ext = _ext(path)
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext or '(none)'}")

    if ext in _EXCEL:
        return office_tables.extract_excel(path)
    if ext in _CSV:
        return office_tables.extract_csv(path)
    if ext in _DOCX:
        return office_tables.extract_docx(path)
    if ext in _IMAGE:
        return _safe_ocr_image(path, ocr_lang, allow_ocr)

    # PDF: born-digital first, OCR fallback for scanned docs.
    tables = pdf_tables.extract(path, page_filter=page_filter)
    if tables:
        return tables

    if allow_ocr and ocr_tables.is_available():
        logger.info("No native tables in %s; falling back to OCR.", path)
        try:
            return ocr_tables.extract_pdf(
                path, dpi=ocr_dpi, lang=ocr_lang, page_filter=page_filter
            )
        except ocr_tables.OCRUnavailable as exc:
            logger.warning("OCR fallback unavailable: %s", exc)
    elif allow_ocr:
        logger.warning("Scanned PDF %s but OCR deps not installed.", path)
    return tables


def _safe_ocr_image(path: str, lang: str, allow_ocr: bool) -> List[ExtractedTable]:
    if not allow_ocr:
        return []
    if not ocr_tables.is_available():
        logger.warning("Image input %s requires OCR deps which are missing.", path)
        return []
    return ocr_tables.extract_image(path, lang=lang)


def export_tables(tables: List[ExtractedTable], out_dir: str) -> dict:
    """Write tables to one XLSX (a sheet per table) + one CSV each.

    Returns {"xlsx": path, "csv_files": [...], "count": n}.
    """
    import pandas as pd

    os.makedirs(out_dir, exist_ok=True)
    uid = uuid.uuid4().hex[:8]
    xlsx_path = os.path.join(out_dir, f"tables_{uid}.xlsx")
    csv_files: List[str] = []

    writer = pd.ExcelWriter(xlsx_path, engine="openpyxl")
    written = 0
    for t in tables:
        df = _table_to_df(t)
        sheet = _safe_sheet_name(t.page, t.index)
        df.to_excel(writer, index=False, sheet_name=sheet)
        csv_name = f"table_{uid}_p{t.page}_t{t.index}.csv"
        df.to_csv(os.path.join(out_dir, csv_name), index=False)
        csv_files.append(csv_name)
        written += 1
    writer.close()
    return {"xlsx": xlsx_path, "csv_files": csv_files, "count": written}


def _table_to_df(t: ExtractedTable):
    import pandas as pd

    rows = t.rows or [[]]
    header = [str(c) if c is not None else f"col_{j}" for j, c in enumerate(rows[0])]
    df = pd.DataFrame(rows[1:], columns=header) if len(rows) > 1 else pd.DataFrame(columns=header)
    return df


def _safe_sheet_name(page: int, index: int) -> str:
    return f"p{page}_t{index}"[:31]
