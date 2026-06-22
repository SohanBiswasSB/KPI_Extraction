"""Common structured-table data model shared by every extraction backend."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# A cell can be text, a number, or empty (None).
Cell = Optional[Any]
Row = List[Cell]


@dataclass
class ExtractedTable:
    """A single structured table, regardless of source format.

    rows[0] is treated as the header when `header` is None and headers were
    detected. `source` records which backend produced the table so the UI can
    show provenance and confidence ('pdfplumber' | 'ocr' | 'excel' | 'csv' | 'docx').
    """

    page: int                      # 1-based page/sheet number (1 for flat formats)
    index: int                     # 0-based index of the table within that page/sheet
    rows: List[Row]                # full grid, including the header row
    source: str                    # extraction backend that produced this table
    sheet_name: Optional[str] = None      # original sheet name for Excel, else None
    bbox: Optional[List[float]] = None     # [x0, y0, x1, y1] in page points, when known
    caption: Optional[str] = None
    confidence: float = 1.0        # 1.0 for ruled/native, lower for OCR/heuristic

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    @property
    def header(self) -> Row:
        return self.rows[0] if self.rows else []

    def is_meaningful(self) -> bool:
        """Drop degenerate 1x1 / single-line 'tables' that are usually noise."""
        return self.n_rows >= 2 and self.n_cols >= 2

    def preview(self, max_rows: int = 10) -> Dict[str, Any]:
        """JSON-serialisable preview honoring a row cap."""
        return {
            "page": self.page,
            "index": self.index,
            "source": self.source,
            "sheet_name": self.sheet_name,
            "caption": self.caption,
            "confidence": round(self.confidence, 3),
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
            "rows": self.rows[: max_rows + 1],  # +1 so header + max_rows of data show
        }

    def to_dict(self) -> Dict[str, Any]:
        """Full JSON-serialisable representation for persistence/export."""
        return {
            "page": self.page,
            "index": self.index,
            "source": self.source,
            "sheet_name": self.sheet_name,
            "bbox": self.bbox,
            "caption": self.caption,
            "confidence": round(self.confidence, 3),
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
            "rows": self.rows,
        }
