"""
pagefit — Markdown/Typst -> PDF with an adaptive density loop.

The loop is the point. A single render is a guess; this renders, measures how
much of each page the content actually occupies, and retunes type size, leading
and margins to kill a sparse trailing page or an airy one-pager.

Compression is capped at roughly 8% of base type size, which the pagination
literature treats as the limit of what a reader notices. If shedding a page
would need more than that, the page stays and nothing is squashed.

Usage:
    python render.py INPUT.md -o OUT.pdf [--title T] [--subtitle S]
                     [--paper a4|a5|us-letter] [--accent "#1f2933"]
                     [--footer TEXT] [--fit] [--no-loop] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import typst  # noqa: E402

import fill as fillmod  # noqa: E402
from md2typ import convert  # noqa: E402

HERE = Path(__file__).parent
TEMPLATE = HERE / "template.typ"

# Density ladder. Index 0 is the house default; higher indices are tighter.
# Margin never drops below 20mm and type never loses more than ~8%.
LADDER = [
    dict(body=10.5, lead=0.72, spacing=1.00, margin=22.0),
    dict(body=10.3, lead=0.70, spacing=0.95, margin=21.5),
    dict(body=10.1, lead=0.68, spacing=0.90, margin=21.0),
    dict(body=9.9,  lead=0.66, spacing=0.86, margin=20.5),
    dict(body=9.7,  lead=0.65, spacing=0.82, margin=20.0),
]

# Looser settings, used only with --fit when a document is too airy.
EXPAND = [
    dict(body=10.8, lead=0.75, spacing=1.08, margin=22.5),
    dict(body=11.2, lead=0.78, spacing=1.15, margin=23.0),
    dict(body=11.6, lead=0.82, spacing=1.22, margin=24.0),
]

# A final page emptier than this is worth trying to absorb.
SPARSE_LAST = 0.30
# A one-pager emptier than this is worth expanding, with --fit.
AIRY = 0.70
FILL_TARGET = 0.85


def _compile(body_typ: str, workdir: Path, out_pdf: Path, inputs: dict) -> None:
    (workdir / "body.typ").write_text(body_typ, encoding="utf-8")
    shutil.copy(TEMPLATE, workdir / "template.typ")
    typst.compile(
        str(workdir / "template.typ"),
        output=str(out_pdf),
        root=str(workdir),
        sys_inputs={k: str(v) for k, v in inputs.items()},
    )


def render(
    body_typ: str,
    out_pdf: Path,
    meta: dict,
    loop: bool = True,
    fit: bool = False,
) -> dict:
    """Render with the density loop. Returns a trace of what it decided."""
    workdir = Path(tempfile.mkdtemp(prefix="pagefit_"))
    trace = {"attempts": [], "final": None, "reason": ""}
    try:
        def attempt(step: dict, label: str) -> dict:
            inputs = {**meta, **step}
            _compile(body_typ, workdir, out_pdf, inputs)
            stats = fillmod.measure(str(out_pdf), margin_mm=step["margin"])
            rec = {
                "label": label,
                "density": step,
                "pages": stats["pages"],
                "last_fill": round(stats["last_page"], 3),
                "mean_fill": round(stats["mean"], 3),
                "_stats": stats,
            }
            trace["attempts"].append({k: v for k, v in rec.items() if k != "_stats"})
            return rec

        base = attempt(LADDER[0], "base")
        best = base

        if not loop:
            trace["reason"] = "loop disabled"
            trace["final"] = {k: v for k, v in best.items() if k != "_stats"}
            trace["stats"] = best["_stats"]
            return trace

        # --- case 1: trailing page barely used -> try to absorb it ---
        if base["pages"] > 1 and base["last_fill"] < SPARSE_LAST:
            target_pages = base["pages"] - 1
            got = None
            for idx in range(1, len(LADDER)):
                a = attempt(LADDER[idx], f"compress-{idx}")
                if a["pages"] <= target_pages:
                    got = a
                    break
            if got:
                best = got
                trace["reason"] = (
                    f"final page was {base['last_fill']:.0%} full; "
                    f"tightened to {got['density']['body']}pt and shed a page "
                    f"({base['pages']} -> {got['pages']})"
                )
            else:
                best = base
                trace["reason"] = (
                    f"final page is {base['last_fill']:.0%} full but shedding it would "
                    f"need more compression than is safe; left at house density"
                )

        # --- case 2: content overflows onto a nearly empty page by a hair ---
        elif base["pages"] > 1 and base["last_fill"] < 0.5:
            target_pages = base["pages"] - 1
            for idx in range(1, 3):  # only the gentlest two notches
                a = attempt(LADDER[idx], f"nudge-{idx}")
                if a["pages"] <= target_pages:
                    best = a
                    trace["reason"] = (
                        f"small spill onto a {base['last_fill']:.0%}-full page; "
                        f"absorbed with a {idx}-notch nudge"
                    )
                    break
            else:
                trace["reason"] = "page count is genuine; no compression applied"

        # --- case 3: airy one-pager, only with --fit ---
        elif fit and base["pages"] == 1 and base["last_fill"] < AIRY:
            for idx, step in enumerate(EXPAND):
                a = attempt(step, f"expand-{idx}")
                if a["pages"] > 1:
                    break
                best = a
                if a["last_fill"] >= FILL_TARGET:
                    break
            trace["reason"] = (
                f"single page was {base['last_fill']:.0%} full; expanded type to "
                f"{best['density']['body']}pt ({best['last_fill']:.0%} fill)"
            )
        else:
            trace["reason"] = "density already within house limits"

        # The file on disk is whatever compiled last. If that is not the winner,
        # compile the winner again so output and decision agree.
        if trace["attempts"] and best["label"] != trace["attempts"][-1]["label"]:
            _compile(body_typ, workdir, out_pdf, {**meta, **best["density"]})
            best["_stats"] = fillmod.measure(str(out_pdf), margin_mm=best["density"]["margin"])

        trace["final"] = {k: v for k, v in best.items() if k != "_stats"}
        trace["stats"] = best["_stats"]
        return trace
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown -> clean PDF")
    ap.add_argument("input", help="input .md or .typ file")
    ap.add_argument("-o", "--output", help="output .pdf (default: alongside input)")
    ap.add_argument("--title", default="")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--paper", default="a4")
    ap.add_argument("--accent", default="#1f2933")
    ap.add_argument("--footer", default="")
    ap.add_argument("--fit", action="store_true",
                    help="also expand an airy one-pager to fill the sheet")
    ap.add_argument("--no-loop", action="store_true", help="single render, no retune")
    ap.add_argument("--json", action="store_true", help="emit the trace as JSON")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"error: {src} not found", file=sys.stderr)
        return 1

    raw = src.read_text(encoding="utf-8")
    title = args.title

    if src.suffix == ".typ":
        body = raw
    else:
        lines = raw.splitlines()
        # Lift a leading H1 into the template's title block so it is not
        # printed twice, and so the title can never be orphaned from its text.
        for idx, line in enumerate(lines[:10]):
            if line.startswith("# "):
                if not title:
                    title = line[2:].strip()
                del lines[idx]
                break
        body = convert("\n".join(lines))

    out = Path(args.output) if args.output else src.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    meta = {
        "title": title,
        "subtitle": args.subtitle,
        "paper": args.paper,
        "accent": args.accent,
        "footer": args.footer or title,
    }

    trace = render(body, out, meta, loop=not args.no_loop, fit=args.fit)

    if args.json:
        print(json.dumps({k: v for k, v in trace.items() if k != "stats"}, indent=2))
    else:
        s = trace["stats"]
        print(f"-> {out}")
        print(fillmod.report(s, FILL_TARGET))
        print(f"density: {trace['final']['density']}")
        print(f"note: {trace['reason']}")
        if s["pages"] > 1 and s["last_page"] < SPARSE_LAST:
            print("WARNING: final page still sparse - consider trimming content")
        if s["pages"] == 1 and s["last_page"] < 0.55:
            # Type scaling cannot fill a sheet from a third of a page. The
            # honest fix is a smaller sheet, not 14pt body text.
            smaller = {"a4": "a5", "us-letter": "a5", "a5": "a6"}.get(args.paper.lower())
            if smaller:
                print(f"note: only {s['last_page']:.0%} of the sheet is used - "
                      f"this content suits --paper {smaller} better than stretched type")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
