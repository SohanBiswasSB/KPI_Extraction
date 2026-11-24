"""Offline evaluation of the retrieval-and-answer pipeline.

Four metrics, chosen because each one catches a failure this project has
actually shipped at some point:

  retrieval hit@k  Did any retrieved chunk come from a page that prints the
                   answer? Catches the retrieval arm going blind - the state
                   the index was in when every vector for a document was zero.

  figure recall    Did the answer state the figures the document prints?
                   Catches a correct-sounding answer built from the wrong rows.

  citation valid   Does every "[Source: file, Page N]" in the answer point at a
                   page that was actually retrieved? Catches invented citations,
                   which read exactly like real ones.

  groundedness     Does every number in the answer appear in the retrieved
                   context? Catches rescaling and silent arithmetic.

  MRR before/after Where in the ranking does the first correct chunk sit, with
                   and without the reranker? hit@k only asks whether the answer
                   was somewhere in the top k, so a reranker that moves it from
                   fifth to first scores identically to one that does nothing.
                   The delta between the two is what says whether reranking
                   earns the LLM call it costs.

Run against a live backend with the golden document uploaded and processed:

    python eval/run_eval.py --org 2
    python eval/run_eval.py --org 2 --json results.json
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

CITATION = re.compile(r"\[Source:\s*([^,\]]+?)\s*,\s*Page\s*(\d+)\s*\]", re.I)
# Figures as a document prints them: grouped, decimal, or parenthesised negative.
NUMBER = re.compile(r"\(?\$?\s?\d[\d,]*(?:\.\d+)?\)?%?")


def post(base, path, token, payload):
    """POST JSON to the API and return the decoded reply."""
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)


def digits(text):
    """Strip everything but digits and dots, so 219,024 and (219024) compare equal."""
    return re.sub(r"[^\d.]", "", text)


def evaluate(case, answer, sources):
    """Score one case. Every metric is None when it does not apply."""
    pages = {s.get("chunk_metadata", {}).get("page_number") for s in sources}
    pages.discard(None)
    context = "\n".join(s.get("content_chunk", "") for s in sources)
    low = answer.lower()

    refused = any(p in low for p in (
        "not stated", "does not", "no relevant content", "not provided",
        "cannot", "not mentioned", "not available"))

    if case.get("expect_refusal"):
        return {"hit": None, "figures": None, "citations": None,
                "grounded": None, "refused": refused, "pass": refused}

    hit = bool(set(case["pages"]) & pages) if case["pages"] else None

    want = case.get("figures") or []
    found = [f for f in want if digits(f) in digits(answer)]
    figures = len(found) / len(want) if want else None

    cited = [(f, int(p)) for f, p in CITATION.findall(answer)]
    good = [c for c in cited if c[1] in pages]
    citations = len(good) / len(cited) if cited else None

    nums = {digits(n) for n in NUMBER.findall(answer) if len(digits(n)) >= 2}
    ctx = digits(context)
    grounded = (sum(1 for n in nums if n and n in ctx) / len(nums)) if nums else None

    banned = [b for b in case.get("must_not_contain", [])
              if digits(b) and digits(b) in digits(answer)]

    ok = (hit is not False and (figures is None or figures == 1.0)
          and (citations is None or citations == 1.0) and not banned
          and not refused)
    return {"hit": hit, "figures": figures, "citations": citations,
            "grounded": grounded, "refused": refused, "banned": banned,
            "pass": ok}


def reciprocal_rank(ranked_pages, gold_pages, depth):
    """1/rank of the first chunk from a gold page, within the top ``depth``.

    Returns None when the case has no gold pages, 0.0 when no gold page is
    ranked inside the depth. Truncating to a fixed depth is what makes the
    before/after comparison fair: the candidate pool is several times longer
    than the reranked list, and scoring the two at their natural lengths
    rewards the longer one for hits nobody would ever have seen.
    """
    if not gold_pages:
        return None
    gold = set(gold_pages)
    for position, page in enumerate(ranked_pages[:depth], start=1):
        if page in gold:
            return 1.0 / position
    return 0.0


def rank_case(base, token, case, org, top_k):
    """Score one case's ranking, before and after the reranker.

    ``reachable`` records whether a gold page was anywhere in the candidate
    pool. It separates the two failures that hit@k reports identically: a
    reranker cannot promote a chunk that retrieval never surfaced, so a case
    that is unreachable is a retrieval problem and a case that is reachable
    but ranked low is a ranking problem.
    """
    reply = post(base, "/files/retrieve", token, {
        "question": case["question"], "organization_id": org,
        "top_k": top_k})
    before = [c.get("page_number") for c in reply.get("before_rerank", [])]
    after = [c.get("page_number") for c in reply.get("after_rerank", [])]
    gold = set(case["pages"])
    return {
        "id": case["id"],
        "rr_before": reciprocal_rank(before, case["pages"], top_k),
        "rr_after": reciprocal_rank(after, case["pages"], top_k),
        "reachable": bool(gold & set(before)),
        "pool": len(before),
    }


def rank_report(base, token, golden, org, top_k):
    """Run the ranking pass over every case that has gold pages."""
    cases = [c for c in golden["cases"]
             if c.get("pages") and not c.get("expect_refusal")]
    if not cases:
        return []
    print()
    print(f"{'case':22} {'RR before':>10} {'RR after':>9} {'in pool':>8}")
    print("-" * 62)
    rows = []
    for case in cases:
        try:
            row = rank_case(base, token, case, org, top_k)
        except urllib.error.HTTPError as err:
            if err.code in (404, 405):
                print("  /files/retrieve not available - skipping ranking "
                      "metrics")
                return []
            print(f"{case['id']:22} {'':>10} {'':>9}  HTTP {err.code}")
            continue
        rows.append(row)
        print(f"{row['id']:22} {row['rr_before']:>10.2f} "
              f"{row['rr_after']:>9.2f} {'yes' if row['reachable'] else 'NO':>8}")

    def mrr(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return sum(vals) / len(vals) if vals else 0.0

    before, after = mrr("rr_before"), mrr("rr_after")
    unreachable = [r["id"] for r in rows if not r["reachable"]]
    print("-" * 62)
    print(f"MRR@{top_k} before rerank {before:.3f}   after {after:.3f}   "
          f"delta {after - before:+.3f}")
    if unreachable:
        # Worth calling out separately: these cap the achievable MRR, and no
        # amount of reranking moves them. They are retrieval work, not
        # ranking work.
        print(f"gold page never retrieved for: {', '.join(unreachable)}")
    if len(rows) < 8:
        print(f"({len(rows)} scorable cases - treat the delta as directional)")
    return rows


def pct(v):
    """Format a 0-1 score, or a dash when the metric does not apply."""
    return "  -  " if v is None else f"{v * 100:4.0f}%"


def main():
    """Run every golden case against a live backend and print a scorecard."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001/api/v1")
    ap.add_argument("--org", type=int, required=True)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--golden", default=os.path.join(HERE, "golden.json"))
    ap.add_argument("--json", dest="out")
    ap.add_argument("--email", default="sohanbiswas09@gmail.com")
    ap.add_argument("--user-id", type=int, default=1)
    ap.add_argument("--no-rank", action="store_true",
                    help="skip the MRR pass (one extra retrieval per case)")
    args = ap.parse_args()

    # Imported here rather than at module scope: this file is a standalone
    # script, and the sys.path insert above has to run before app.* resolves.
    # pylint: disable=import-outside-toplevel
    from app.core.security import create_access_token
    token = create_access_token(data={"sub": args.email, "user_id": args.user_id})

    with open(args.golden, encoding="utf-8") as fh:
        golden = json.load(fh)

    print(f"{'case':22} {'hit':>5} {'figs':>5} {'cite':>5} {'grnd':>5} "
          f"{'secs':>6}  result")
    print("-" * 62)

    rows, elapsed_total = [], 0.0
    for case in golden["cases"]:
        started = time.time()
        try:
            reply = post(args.base, "/files/ask", token, {
                "question": case["question"], "organization_id": args.org,
                "top_k": args.top_k})
        except urllib.error.HTTPError as err:
            print(f"{case['id']:22} {'':>5} {'':>5} {'':>5} {'':>5} "
                  f"{'':>6}  HTTP {err.code}")
            rows.append({"id": case["id"], "error": err.code})
            continue
        secs = time.time() - started
        elapsed_total += secs
        score = evaluate(case, reply.get("answer", ""), reply.get("sources", []))
        rows.append({"id": case["id"], "secs": round(secs, 1), **score,
                     "answer": reply.get("answer", "")})
        hit = score["hit"]
        print(f"{case['id']:22} {pct(None if hit is None else float(hit))} "
              f"{pct(score['figures'])} {pct(score['citations'])} "
              f"{pct(score['grounded'])} {secs:5.1f}s  "
              f"{'PASS' if score['pass'] else 'FAIL'}")

    scored = [r for r in rows if "pass" in r]
    passed = sum(1 for r in scored if r["pass"])
    print("-" * 62)
    print(f"{passed}/{len(scored)} passed   mean latency "
          f"{elapsed_total / max(len(scored), 1):.1f}s")

    def mean(key):
        vals = [r[key] for r in scored if r.get(key) is not None]
        vals = [float(v) for v in vals]
        return f"{sum(vals) / len(vals) * 100:.0f}%" if vals else "-"

    print(f"hit@{args.top_k} {mean('hit')}   figure recall {mean('figures')}   "
          f"citation validity {mean('citations')}   groundedness {mean('grounded')}")

    # Ranking is measured in a second pass rather than from the answers above:
    # /ask returns only the final reranked sources, so the ordering the
    # reranker started from is not observable from it.
    ranking = [] if args.no_rank else rank_report(
        args.base, token, golden, args.org, args.top_k)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"top_k": args.top_k, "results": rows,
                       "ranking": ranking}, fh, indent=2)
        print(f"wrote {args.out}")
    return 0 if passed == len(scored) else 1


if __name__ == "__main__":
    sys.exit(main())
