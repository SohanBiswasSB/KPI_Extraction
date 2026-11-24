"""Derive the golden set from the extracted tables, rather than typing it in.

A golden file written by hand records what someone believed the document said
on the day they wrote it. It cannot be re-checked, it goes stale silently when
extraction changes, and a transcription slip in it looks exactly like a
regression in the pipeline. Everything here is instead located in the stored
tables at build time: each case names the statement and the row label to find,
and the figures and page numbers come out of the document.

What is declared by hand is only what cannot be derived - the question a reader
would ask, and which wrong answer is worth guarding against.

    python eval/build_golden.py --file-id 5
    python eval/build_golden.py --file-id 5 --check   # verify, write nothing

--check re-derives and compares against the stored file without writing, so
CI can fail when re-extraction moves a figure out from under the golden set.
"""

import argparse
import asyncio
import itertools
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

# pylint: disable=wrong-import-position
import asyncpg

from app.core.config import settings
from app.services.embedding_service import EmbeddingService

sys.path.insert(0, HERE)
from run_eval import digits  # noqa: E402  same normalisation the harness scores with

# A cell holding a figure as the filing prints it. Reused rather than
# redefined so the harness and the chunker agree on what a number is.
FIGURE = re.compile(r"^\(?\$?\s?\d[\d,]*(?:\.\d+)?\)?%?$")

# Rows whose label matches but which restate a figure in a different unit.
SHARE_COUNT = re.compile(r"shares used|weighted-average", re.I)

# A leading digit group that pdfplumber has separated from the rest of its own
# number by a column break: "118,254" arrives as the two cells "1" and
# "18,254". A fragment is short, has no separator of its own, and is followed
# by a grouped number.
FRAGMENT = re.compile(r"^\d{1,2}$")
GROUPED = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")


def cells_of(line):
    """Figure-bearing cells of a row, repaired.

    Two artefacts have to be undone first. Currency symbols ride along inside
    a cell ("112,010 $"), so cells are split on whitespace as well as tabs.
    And a figure can be broken across a column break, which leaves a one- or
    two-digit fragment sitting in front of the rest of its own number.
    """
    parts = [p for cell in line.split("\t")
             for p in cell.split() if p and p != "$"]
    merged, index = [], 0
    while index < len(parts):
        current = parts[index]
        following = parts[index + 1] if index + 1 < len(parts) else ""
        if FRAGMENT.match(current) and GROUPED.match(following):
            merged.append(current + following)
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged

CASES = [
    {
        "id": "total-net-sales-3y",
        "question": "What were total net sales for each of the last three years?",
        "section": "income statement",
        "label": r"^total\s*net\s*sales",
        "absent": ["3,253,431"],
        "why": "3,253,431 is the aggregate market value of stock held by "
               "non-affiliates on page 2. KPI extraction has labelled that "
               "figure as net sales before; it is the most plausible wrong "
               "answer in the document.",
    },
    {
        "id": "net-income-3y",
        "question": "What was net income for each year?",
        "section": "comprehensive income",
        "label": r"^net\s*income",
        "sibling": r"^total\s*compre",
        "why": "The distractor is total comprehensive income, printed a few "
               "lines below net income on the same page.",
    },
    {
        "id": "diluted-eps",
        "question": "What was diluted earnings per share?",
        "section": "income statement",
        "label": r"^diluted",
        "sibling": r"^basic",
        "why": "The distractor is basic EPS, printed directly above diluted.",
    },
    {
        "id": "gross-margin-3y",
        "question": "What was gross margin for each year?",
        "section": "income statement",
        "label": r"^gross\s*margin",
        "derived": "delta",
        "why": "The distractor is the year-over-year change, which the filing "
               "never prints. The extractor has invented that subtraction.",
    },
    {
        "id": "total-assets",
        "question": "What were total assets at the end of each of the last "
                    "two years?",
        "section": "balance sheet",
        "label": r"^total\s*assets",
        "why": "The hardest retrieval case: pdfplumber's table region for the "
               "balance sheet starts below the title, so the page never names "
               "the statement it belongs to.",
    },
    {
        "id": "operating-cash-flow",
        "question": "How much cash was generated by operating activities?",
        "section": "cash flow",
        "label": r"^cash\s*generated\s*by\s*operating",
        "why": "Single-page answer with no restatement elsewhere, so a hit "
               "means retrieval found the cash flow statement itself.",
    },
    {
        "id": "segment-vs-total",
        "question": "What were Services net sales?",
        "section": "income statement",
        "label": r"^services$",
        "sibling": r"^total\s*net\s*sales",
        "why": "Asks for a component while the total sits on the same rows. "
               "Answering with the total is the classic wrong-row failure.",
    },
]

# Cases that need no row lookup.
LITERAL_CASES = [
    {
        "id": "exact-figure-lookup",
        "question": None,          # filled from total-net-sales-3y
        "borrow": "total-net-sales-3y",
        "why": "Exercises the lexical arm. An embedding blurs a bare figure "
               "into every other figure, so this fails outright if BM25 stops "
               "contributing to the fusion.",
    },
    {
        "id": "absent-fact",
        "question": "What was the chief executive officer's total compensation?",
        "expect_refusal": True,
        "probe": "total compensation",
        "why": "A 10-K incorporates executive compensation by reference to the "
               "proxy statement. Verified absent from every extracted table, "
               "so any figure here is invented.",
    },
]


async def load_blocks(file_id):
    """Every stored table for a file, as (page, cleaned text), and its name."""
    dsn = settings.DATABASE_URL.replace("+asyncpg", "")
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT page, rows FROM extracted_tables "
            "WHERE file_id = $1 ORDER BY page, table_index", file_id)
        name = await conn.fetchval(
            "SELECT original_filename FROM uploaded_files WHERE id = $1",
            file_id)
    finally:
        await conn.close()
    blocks = []
    for row in rows:
        data = row["rows"]
        if isinstance(data, str):
            data = json.loads(data)
        raw = "\n".join(
            "\t".join("" if c is None else str(c) for c in line)
            for line in data)
        blocks.append((row["page"], EmbeddingService.clean_text(raw)))
    return blocks, name


def row_figures(block, label):
    """Figures on the first line of ``block`` whose label matches."""
    pattern = re.compile(label, re.I)
    for line in block.split("\n"):
        cells = cells_of(line)
        if not cells:
            continue
        # Match against the row's label only - the words before its first
        # figure - so a pattern can be anchored at both ends. "^services$"
        # has to distinguish the Services row from "Total cost of services".
        words = list(itertools.takewhile(
            lambda c: not FIGURE.match(c), cells))
        row_label = " ".join(words)
        if not row_label or not pattern.match(row_label):
            continue
        if SHARE_COUNT.search(row_label):
            continue
        figures = [c for c in cells[len(words):] if FIGURE.match(c)]
        if figures:
            return figures
    return []


def pages_printing(blocks, figures):
    """Pages whose text prints every one of ``figures``.

    Compared on digits alone, and for the same reason the harness scores that
    way: extraction scatters separators and currency symbols through a figure
    - page 2 holds the aggregate market value as "$3,\t253,431,000,00\t0." -
    so a literal substring test reports figures missing that a reader, and the
    answer scorer, both consider present.
    """
    return sorted({page for page, text in blocks
                   if all(digits(f) in digits(text) for f in figures)})


def build(blocks):
    """Turn the declarations above into golden cases, or explain what failed."""
    sectioned = {}
    for page, text in blocks:
        section = EmbeddingService._section_of(text)   # pylint: disable=protected-access
        if section and section not in sectioned:
            sectioned[section] = (page, text)

    cases, problems = [], []
    for spec in CASES:
        located = sectioned.get(spec["section"])
        if not located:
            problems.append(f"{spec['id']}: no page detected as "
                            f"{spec['section']!r}")
            continue
        _, text = located
        figures = row_figures(text, spec["label"])
        if not figures:
            problems.append(f"{spec['id']}: no row matching "
                            f"{spec['label']!r} on the {spec['section']}")
            continue

        distractors = []
        if spec.get("sibling"):
            sibling = row_figures(text, spec["sibling"])
            near = [f for f in sibling if f not in figures]
            if not near:
                problems.append(f"{spec['id']}: sibling row "
                                f"{spec['sibling']!r} yielded no distinct "
                                f"figure")
            distractors = near[:1]
        if spec.get("derived") == "delta":
            distractors = [derived_delta(figures, blocks, spec, problems)]
            distractors = [d for d in distractors if d]
        for literal in spec.get("absent", []):
            if pages_printing(blocks, [literal]):
                distractors.append(literal)
            else:
                problems.append(f"{spec['id']}: declared distractor "
                                f"{literal} is not in the document")

        pages = pages_printing(blocks, figures)
        if not pages:
            problems.append(f"{spec['id']}: no page prints all of {figures}")
            continue
        cases.append({
            "id": spec["id"], "question": spec["question"], "pages": pages,
            "figures": figures, "must_not_contain": distractors,
            "why": spec["why"],
        })
    return cases, problems


def derived_delta(figures, blocks, spec, problems):
    """The year-over-year change the filing does not print, as a distractor."""
    try:
        first, second = (int(f.replace(",", "")) for f in figures[:2])
    except ValueError:
        return None
    delta = f"{first - second:,}"
    if pages_printing(blocks, [delta]):
        problems.append(f"{spec['id']}: computed delta {delta} does appear "
                        f"in the document, so it is not a safe distractor")
        return None
    return delta


def add_literal_cases(cases, blocks):
    """Append the cases that need no row lookup."""
    by_id = {c["id"]: c for c in cases}
    problems = []
    for spec in LITERAL_CASES:
        if spec.get("borrow"):
            source = by_id.get(spec["borrow"])
            if not source:
                problems.append(f"{spec['id']}: {spec['borrow']} not built")
                continue
            figure = source["figures"][0]
            cases.append({
                "id": spec["id"], "question": f"What is {figure}?",
                "pages": source["pages"], "figures": [figure],
                "must_not_contain": [], "why": spec["why"],
            })
            continue
        if spec.get("probe"):
            hits = [p for p, t in blocks if spec["probe"] in t.lower()]
            if hits:
                problems.append(f"{spec['id']}: {spec['probe']!r} appears on "
                                f"pages {hits[:5]}, so a refusal is not the "
                                f"correct answer")
                continue
        cases.append({
            "id": spec["id"], "question": spec["question"], "pages": [],
            "figures": [], "expect_refusal": True, "must_not_contain": [],
            "why": spec["why"],
        })
    return problems


async def main():
    """Build the golden set, or check the stored one still matches."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--file-id", type=int, required=True)
    parser.add_argument("--out", default=os.path.join(HERE, "golden.json"))
    parser.add_argument("--check", action="store_true",
                        help="compare against the stored file, write nothing")
    args = parser.parse_args()

    blocks, document = await load_blocks(args.file_id)
    if not blocks:
        print(f"no extracted tables for file {args.file_id}")
        return 1
    cases, problems = build(blocks)
    problems += add_literal_cases(cases, blocks)

    for case in cases:
        print(f"  {case['id']:22} pages {str(case['pages']):<26} "
              f"{', '.join(case['figures']) or '(refusal)'}"
              + (f"   not: {case['must_not_contain']}"
                 if case["must_not_contain"] else ""))
    for problem in problems:
        print(f"  PROBLEM  {problem}")

    payload = {
        "document": document,
        "note": "Generated by eval/build_golden.py from the stored extracted "
                "tables. Do not edit by hand: add a case to CASES in that "
                "script and rebuild, so every figure and page stays traceable "
                "to the document.",
        "cases": cases,
    }
    if args.check:
        with open(args.out, encoding="utf-8") as handle:
            stored = json.load(handle)
        drift = [c["id"] for c in cases
                 if c != next((s for s in stored["cases"]
                               if s["id"] == c["id"]), None)]
        if drift or problems:
            print(f"drifted: {drift or 'none'}")
            return 1
        print(f"{len(cases)} cases match the stored golden set")
        return 0

    if problems:
        print("refusing to write a golden set with unresolved problems")
        return 1
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"wrote {len(cases)} cases to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
