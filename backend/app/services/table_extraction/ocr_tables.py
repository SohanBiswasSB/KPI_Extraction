"""Scanned-PDF / image table reconstruction via PyMuPDF render + Tesseract OCR.

Extends the legacy `text_bbox.py` word-box logic: instead of only drawing boxes,
we cluster OCR word boxes into rows (by vertical position) and columns (by shared
x-bands across rows) to rebuild an approximate grid. This is the fallback path when
pdfplumber finds no native tables (i.e. the PDF is scanned/image-only).

Requires the system Tesseract binary plus `pymupdf` and `pytesseract`.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Set, Tuple

from .models import ExtractedTable

logger = logging.getLogger(__name__)

try:  # optional heavy deps — engine degrades gracefully if missing
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None

try:
    import pytesseract
    from PIL import Image
except ImportError:  # pragma: no cover
    pytesseract = None
    Image = None


class OCRUnavailable(RuntimeError):
    """Raised when OCR is requested but its dependencies are missing."""


def is_available() -> bool:
    """True if the OCR dependencies (PyMuPDF, pytesseract, Pillow) are importable."""
    return fitz is not None and pytesseract is not None and Image is not None


# ----------------------------------------------------------------------------- #
# Low-level OCR: render a page to an image and pull word boxes from Tesseract.
# ----------------------------------------------------------------------------- #

def _render_page(page, dpi: int):
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    mode = "RGB" if pix.n < 4 else "RGBA"
    return Image.frombytes(mode, [pix.width, pix.height], pix.samples)


def _ocr_words(img, lang: str) -> List[Tuple[float, float, float, float, str]]:
    """Return [(x0, y0, x1, y1, text), ...] for non-empty OCR tokens."""
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    out = []
    for i in range(len(data["text"])):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        conf = float(data.get("conf", ["-1"])[i]) if data.get("conf") else -1.0
        if conf != -1.0 and conf < 30:  # drop very low-confidence noise
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        out.append((float(x), float(y), float(x + w), float(y + h), txt))
    return out


# ----------------------------------------------------------------------------- #
# Grid reconstruction from word boxes.
# ----------------------------------------------------------------------------- #

def _group_rows(words, y_thresh: float):
    """Cluster words into rows by vertical center proximity."""
    rows: List[list] = []
    for w in sorted(words, key=lambda b: (b[1], b[0])):
        cy = 0.5 * (w[1] + w[3])
        placed = False
        for row in rows:
            ry = sum(0.5 * (b[1] + b[3]) for b in row) / len(row)
            if abs(cy - ry) <= y_thresh:
                row.append(w)
                placed = True
                break
        if not placed:
            rows.append([w])
    for row in rows:
        row.sort(key=lambda b: b[0])  # left-to-right within the row
    rows.sort(key=lambda r: min(b[1] for b in r))  # top-to-bottom
    return rows


def _column_edges(rows, page_w: float, x_thresh: float) -> List[float]:
    """Derive column boundaries by clustering word left-edges across all rows."""
    starts = sorted(b[0] for row in rows for b in row)
    if not starts:
        return [0.0, page_w]
    clusters = [[starts[0]]]
    for x in starts[1:]:
        if x - clusters[-1][-1] <= x_thresh:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    centers = [sum(c) / len(c) for c in clusters]
    # edges are midpoints between consecutive column centers
    edges = [0.0]
    for a, b in zip(centers, centers[1:]):
        edges.append((a + b) / 2.0)
    edges.append(page_w)
    return edges


def _assign_to_grid(rows, edges) -> List[List[Optional[str]]]:
    n_cols = max(1, len(edges) - 1)
    grid: List[List[Optional[str]]] = []
    for row in rows:
        cells: List[List[str]] = [[] for _ in range(n_cols)]
        for (x0, _y0, _x1, _y1, txt) in row:
            col = 0
            for ci in range(n_cols):
                if edges[ci] <= x0 < edges[ci + 1]:
                    col = ci
                    break
            else:
                col = n_cols - 1
            cells[col].append(txt)
        grid.append([" ".join(c).strip() or None for c in cells])
    return grid


def _reconstruct(words, page_w: float, page_h: float) -> Optional[List[List[Optional[str]]]]:
    if len(words) < 4:
        return None
    y_thresh = max(6.0, 0.012 * page_h)
    x_thresh = max(10.0, 0.04 * page_w)
    rows = _group_rows(words, y_thresh)
    rows = [r for r in rows if r]
    if len(rows) < 2:
        return None
    edges = _column_edges(rows, page_w, x_thresh)
    if len(edges) - 1 < 2:  # need at least 2 columns to call it a table
        return None
    return _assign_to_grid(rows, edges)


# ----------------------------------------------------------------------------- #
# Public entry points.
# ----------------------------------------------------------------------------- #

def extract_pdf(pdf_path: str, dpi: int = 200, lang: str = "eng",
                page_filter: Set[int] | None = None) -> List[ExtractedTable]:
    """Render each PDF page, OCR it, and reconstruct one table per page.

    Raises OCRUnavailable if the OCR dependencies are not installed.
    """
    if not is_available():
        raise OCRUnavailable(
            "OCR requires pymupdf, pytesseract, Pillow and the Tesseract binary."
        )
    tables: List[ExtractedTable] = []
    doc = fitz.open(pdf_path)
    for i in range(doc.page_count):
        pidx = i + 1
        if page_filter is not None and pidx not in page_filter:
            continue
        page = doc.load_page(i)
        img = _render_page(page, dpi)
        words = _ocr_words(img, lang)
        scale = 72.0 / dpi  # report bbox back in PDF points
        grid = _reconstruct(words, img.size[0], img.size[1])
        if grid:
            tables.append(ExtractedTable(
                page=pidx, index=0, rows=grid, source="ocr",
                confidence=0.55,  # OCR reconstruction is best-effort
                bbox=[0.0, 0.0, img.size[0] * scale, img.size[1] * scale],
            ))
    doc.close()
    return tables


def extract_image(image_path: str, lang: str = "eng") -> List[ExtractedTable]:
    """OCR a single image file and reconstruct one table from it.

    Raises OCRUnavailable if the OCR dependencies are not installed.
    """
    if not is_available():
        raise OCRUnavailable(
            "OCR requires pytesseract, Pillow and the Tesseract binary."
        )
    img = Image.open(image_path).convert("RGB")
    words = _ocr_words(img, lang)
    grid = _reconstruct(words, img.size[0], img.size[1])
    if not grid:
        return []
    return [ExtractedTable(page=1, index=0, rows=grid, source="ocr", confidence=0.55)]
