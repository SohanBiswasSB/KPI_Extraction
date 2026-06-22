#!/usr/bin/env python3
"""Standalone CLI for the unified table-extraction engine — no DB, no server.

Useful for verifying extraction on a document before wiring it into the platform.

Usage:
    python scripts/extract_tables_cli.py <file> [--export OUT_DIR] [--json] [--no-ocr]

Examples:
    python scripts/extract_tables_cli.py sample.pdf
    python scripts/extract_tables_cli.py report.xlsx --json
    python scripts/extract_tables_cli.py scanned.pdf --export ./out
"""
import argparse
import json
import os
import sys

# allow running from the backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.table_extraction import extract_tables, export_tables  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract structured tables from a document.")
    ap.add_argument("file", help="Path to a PDF / XLSX / XLS / CSV / DOCX / image")
    ap.add_argument("--export", metavar="DIR", help="Also write XLSX + per-table CSV to DIR")
    ap.add_argument("--json", action="store_true", help="Print full tables as JSON")
    ap.add_argument("--no-ocr", action="store_true", help="Disable the scanned-PDF OCR fallback")
    ap.add_argument("--dpi", type=int, default=200, help="OCR/VLM render DPI (default 200)")
    ap.add_argument("--lang", default="eng", help="Tesseract language(s), e.g. eng+hin")
    ap.add_argument("--vlm", action="store_true",
                    help="Use a vision-LLM (Qwen2.5-VL via Ollama) for scanned pages")
    ap.add_argument("--vlm-model", default="qwen2.5vl:7b", help="Vision model name")
    ap.add_argument("--vlm-base-url", default="http://localhost:11434/v1",
                    help="OpenAI-compatible base URL for the vision model")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    tables = extract_tables(
        args.file, ocr_dpi=args.dpi, ocr_lang=args.lang, allow_ocr=not args.no_ocr,
        allow_vlm=args.vlm, vlm_model=args.vlm_model, vlm_base_url=args.vlm_base_url,
    )
    print(f"Found {len(tables)} table(s) in {args.file}\n")

    for t in tables:
        loc = f"page {t.page}" + (f" / sheet '{t.sheet_name}'" if t.sheet_name else "")
        print(f"- [{loc}] table #{t.index}  {t.n_rows}x{t.n_cols}  "
              f"via {t.source} (conf {t.confidence:.2f})")
        if args.json:
            print(json.dumps(t.to_dict(), indent=2, ensure_ascii=False, default=str))
        else:
            for row in t.rows[:6]:
                print("    " + " | ".join("" if c is None else str(c) for c in row))
            if t.n_rows > 6:
                print(f"    ... ({t.n_rows - 6} more rows)")
        print()

    if args.export:
        out = export_tables(tables, args.export)
        print(f"Exported {out['count']} table(s):")
        print(f"  XLSX: {out['xlsx']}")
        for c in out["csv_files"]:
            print(f"  CSV:  {os.path.join(args.export, c)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
