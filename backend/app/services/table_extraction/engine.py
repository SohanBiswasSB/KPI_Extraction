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

import pandas as pd

from .models import ExtractedTable
from . import pdf_tables, office_tables, ocr_tables, vlm_tables

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
    allow_vlm: bool = False,
    vlm_model: Optional[str] = None,
    vlm_base_url: Optional[str] = None,
    vlm_api_key: Optional[str] = None,
    vlm_max_pages: int = 10,
) -> List[ExtractedTable]:
    """Extract structured tables from any supported document.

    For scanned PDFs/images the fallback order is: vision-LLM (if allow_vlm) →
    Tesseract OCR (if allow_ocr). For born-digital PDFs, pdfplumber runs first
    and the fallbacks only fire when it finds nothing.
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
        return _scanned_image(
            path, ocr_lang, allow_ocr, allow_vlm, vlm_model, vlm_base_url, vlm_api_key
        )

    # PDF: born-digital first, then VLM, then OCR.
    tables = pdf_tables.extract(path, page_filter=page_filter)
    if tables:
        return tables

    if allow_vlm and vlm_model and vlm_base_url:
        logger.info("No native tables in %s; trying vision-LLM.", path)
        vlm_tabs = vlm_tables.extract_pdf(
            path, model=vlm_model, base_url=vlm_base_url, api_key=vlm_api_key,
            dpi=ocr_dpi, page_filter=page_filter, max_pages=vlm_max_pages,
        )
        if vlm_tabs:
            return vlm_tabs
        logger.info("Vision-LLM found no tables in %s; trying OCR.", path)

    if allow_ocr and ocr_tables.is_available():
        logger.info("Falling back to OCR for %s.", path)
        try:
            return ocr_tables.extract_pdf(
                path, dpi=ocr_dpi, lang=ocr_lang, page_filter=page_filter
            )
        except ocr_tables.OCRUnavailable as exc:
            logger.warning("OCR fallback unavailable: %s", exc)
    elif allow_ocr:
        logger.warning("Scanned PDF %s but OCR deps not installed.", path)
    return tables


def _scanned_image(path: str, lang: str, allow_ocr: bool, allow_vlm: bool,
                   vlm_model: Optional[str], vlm_base_url: Optional[str],
                   vlm_api_key: Optional[str]) -> List[ExtractedTable]:
    if allow_vlm and vlm_model and vlm_base_url:
        vlm_tabs = vlm_tables.extract_image(
            path, model=vlm_model, base_url=vlm_base_url, api_key=vlm_api_key
        )
        if vlm_tabs:
            return vlm_tabs
    if allow_ocr and ocr_tables.is_available():
        return ocr_tables.extract_image(path, lang=lang)
    if not allow_ocr and not allow_vlm:
        return []
    logger.warning("Image input %s: no usable OCR/VLM backend available.", path)
    return []


def export_tables(tables: List[ExtractedTable], out_dir: str) -> dict:
    """Write tables to one XLSX (a sheet per table) + one CSV each.

    Returns {"xlsx": path, "csv_files": [...], "count": n}.
    """
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
    rows = t.rows or [[]]
    header = [str(c) if c is not None else f"col_{j}" for j, c in enumerate(rows[0])]
    df = pd.DataFrame(rows[1:], columns=header) if len(rows) > 1 else pd.DataFrame(columns=header)
    return df


def _safe_sheet_name(page: int, index: int) -> str:
    return f"p{page}_t{index}"[:31]
