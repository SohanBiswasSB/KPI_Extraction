"""Vision-LLM table extraction for scanned pages (Qwen2.5-VL via Ollama).

Used as a higher-quality fallback for scanned/image documents: instead of
OCR -> text -> reconstruct, we send the rendered page image straight to a
vision model and ask it to return the tables as JSON. This sees layout the way
OCR can't, but it makes scanned-doc extraction depend on the LLM — so the engine
only uses it when ENABLE_VLM is set, keeping plain OCR as the offline fallback.

Requires `openai` (client) + `PyMuPDF`/`Pillow` (page rendering). Degrades to an
empty result if those or the model server are unavailable.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
from typing import List, Optional, Set

from .models import ExtractedTable

logger = logging.getLogger(__name__)

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None


_PROMPT = (
    "You are a precise table-extraction engine. Look at this document page and "
    "extract every data table you can see. Return ONLY a JSON object, no prose, "
    "with this exact shape:\n"
    '{"tables": [{"rows": [["header1","header2"],["cell","cell"]]}]}\n'
    "Rules: include the header row as the first row of each table; preserve the "
    "reading order of columns; use null for empty cells; if the page has no "
    'tables, return {"tables": []}.'
)


def is_available() -> bool:
    """True if the VLM dependencies (openai, PyMuPDF, Pillow) are importable."""
    return fitz is not None and Image is not None and openai is not None


def _client(base_url: str, api_key: Optional[str]):
    return openai.OpenAI(base_url=base_url, api_key=api_key or "ollama")


def _png_data_uri(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _render_page(page, dpi: int):
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    mode = "RGB" if pix.n < 4 else "RGBA"
    return Image.frombytes(mode, [pix.width, pix.height], pix.samples)


def _parse_tables(content: str) -> List[List[list]]:
    """Pull the JSON `tables` array out of a model response, tolerating fences."""
    if not content:
        return []
    text = content.strip()
    # strip ```json ... ``` fences if present
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # else try to locate the first {...} block
    if not text.startswith("{"):
        brace = text.find("{")
        if brace != -1:
            text = text[brace:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.debug("VLM returned non-JSON content: %.200s", content)
        return []
    tables = data.get("tables", []) if isinstance(data, dict) else []
    out: List[List[list]] = []
    for t in tables:
        rows = t.get("rows") if isinstance(t, dict) else None
        if isinstance(rows, list) and rows:
            out.append([[(c if c not in ("", []) else None) for c in (row or [])] for row in rows])
    return out


def _extract_from_image(img, page: int, model: str, base_url: str,
                        api_key: Optional[str]) -> List[ExtractedTable]:
    client = _client(base_url, api_key)
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": _PROMPT},
                {"type": "image_url", "image_url": {"url": _png_data_uri(img)}},
            ],
        }],
    )
    grids = _parse_tables(resp.choices[0].message.content)
    tables: List[ExtractedTable] = []
    for idx, grid in enumerate(grids):
        tbl = ExtractedTable(page=page, index=idx, rows=grid, source="vlm", confidence=0.7)
        if tbl.is_meaningful():
            tables.append(tbl)
    return tables


def extract_pdf(pdf_path: str, model: str, base_url: str, api_key: Optional[str] = None,
                dpi: int = 200, page_filter: Set[int] | None = None,
                max_pages: int = 10) -> List[ExtractedTable]:
    """Render up to `max_pages` PDF pages and extract their tables with the vision model.

    Returns an empty list (logged) if the dependencies or model server are unavailable.
    """
    if not is_available():
        logger.warning("VLM extraction unavailable (need openai + PyMuPDF + Pillow).")
        return []
    tables: List[ExtractedTable] = []
    doc = fitz.open(pdf_path)
    processed = 0
    for i in range(doc.page_count):
        pidx = i + 1
        if page_filter is not None and pidx not in page_filter:
            continue
        if processed >= max_pages:
            logger.info("VLM page cap (%d) reached for %s; remaining pages skipped.",
                        max_pages, pdf_path)
            break
        try:
            img = _render_page(doc.load_page(i), dpi)
            tables.extend(_extract_from_image(img, pidx, model, base_url, api_key))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("VLM extraction failed on page %s: %s", pidx, exc)
        processed += 1
    doc.close()
    return tables


def extract_image(image_path: str, model: str, base_url: str,
                  api_key: Optional[str] = None) -> List[ExtractedTable]:
    """Extract tables from a single image file using the vision model.

    Returns an empty list (logged) if the dependencies or model server are unavailable.
    """
    if not is_available():
        logger.warning("VLM extraction unavailable (need openai + Pillow).")
        return []
    try:
        img = Image.open(image_path).convert("RGB")
        return _extract_from_image(img, 1, model, base_url, api_key)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("VLM extraction failed for image %s: %s", image_path, exc)
        return []
