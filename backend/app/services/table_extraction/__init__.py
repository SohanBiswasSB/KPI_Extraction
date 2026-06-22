"""Unified table-extraction engine.

Consolidates the structured-table logic from the legacy projects into one place:
  - pdfplumber dual-strategy extraction for born-digital PDFs   (pdf_tables.py)
  - PyMuPDF render + Tesseract OCR reconstruction for scanned PDFs/images (ocr_tables.py)
  - pandas (Excel/CSV) and python-docx (DOCX) for office formats (office_tables.py)

Everything returns the common `ExtractedTable` shape so downstream code
(persistence, KPI extraction, XLSX/CSV export) is format-agnostic.
"""
from .models import ExtractedTable
from .engine import extract_tables, export_tables, SUPPORTED_EXTENSIONS

__all__ = [
    "ExtractedTable",
    "extract_tables",
    "export_tables",
    "SUPPORTED_EXTENSIONS",
]
