"""
pagefit — URL / HTML file -> PDF via headless Chromium.

Chromium's print path is a greedy single-pass fragmenter with no backtracking:
once it defers a block to the next page it cannot return and redistribute the
gap it just made. Two things are done about that here.

1. Pre-flight. Most "mystery" page-count drift is the renderer printing before
   fonts and images have settled, so the layout is computed against fallback
   metrics and then reflows. We wait on document.fonts.ready and on every
   image's decode() before printing.

2. Defensive CSS plus an outer measure-and-retune loop. Chromium will not fix a
   sparse page on its own, so we render, measure actual page fill, and re-render
   at a slightly tighter density if that sheds an almost-empty trailing page.

Usage:
    python web.py URL_OR_FILE -o OUT.pdf [--paper A4] [--margin 22]
                  [--selector CSS] [--wait MS] [--landscape]
                  [--no-loop] [--keep-nav] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fill as fillmod  # noqa: E402

HERE = Path(__file__).parent
PREFLIGHT = HERE / "preflight.css"

LADDER = [
    dict(body=10.5, lead=1.42, margin=22.0),
    dict(body=10.3, lead=1.38, margin=21.5),
    dict(body=10.1, lead=1.34, margin=21.0),
    dict(body=9.9,  lead=1.30, margin=20.5),
    dict(body=9.7,  lead=1.27, margin=20.0),
]

SPARSE_LAST = 0.30
FILL_TARGET = 0.85

# Resolved before printing so layout is computed against real metrics.
SETTLE_JS = """
async () => {
  // Walk the page so IntersectionObserver-driven reveal animations actually
  // fire. Without this, scroll-revealed sections are still at opacity 0 when
  // the print snapshot is taken and come out as blank pages. The CSS override
  // covers the same ground; doing both also lets JS commit its 'is-visible'
  // classes, which some layouts depend on for height.
  const h = document.body.scrollHeight;
  for (let y = 0; y < h; y += Math.max(200, window.innerHeight * 0.8)) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 40));
  }
  window.scrollTo(0, h);
  await new Promise(r => setTimeout(r, 120));
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 60));

  if (document.fonts && document.fonts.ready) { await document.fonts.ready; }
  const imgs = Array.from(document.images);
  await Promise.all(imgs.map(img => {
    if (img.complete && img.naturalHeight !== 0) return Promise.resolve();
    if (img.decode) return img.decode().catch(() => {});
    return new Promise(r => { img.onload = img.onerror = r; });
  }));
  // Force a layout flush, then give late reflows one frame to land.
  document.body.getBoundingClientRect();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
}
"""

# Decorative shells that carried a background, a gradient or an animation on
# screen become empty grey slabs once print styling strips them. Class names for
# these are unguessable across sites, so they are found structurally: block-level,
# occupies real height, contains no text, no media and no form control.
DESHELL_JS = """
() => {
  let removed = 0;
  for (let pass = 0; pass < 3; pass++) {
    document.querySelectorAll('body div, body section, body header, body footer, body aside')
      .forEach(el => {
        if (!el.isConnected) return;
        if (el.offsetHeight < 12) return;
        if (el.textContent.trim().length > 0) return;
        if (el.querySelector('img, svg, canvas, video, picture, input, textarea, select')) return;
        el.remove();
        removed++;
      });
  }
  return removed;
}
"""

ISOLATE_JS = """
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return false;
  const keep = new Set();
  for (let n = el; n; n = n.parentElement) keep.add(n);
  document.querySelectorAll('body *').forEach(n => {
    if (!keep.has(n) && !el.contains(n)) n.remove();
  });
  return true;
}
"""


def _render_once(page, out_pdf: Path, step: dict, paper: str,
                 landscape: bool, keep_nav: bool) -> None:
    css = PREFLIGHT.read_text(encoding="utf-8")
    if keep_nav:
        # Drop only the rule block that hides screen furniture.
        css = css.replace("display: none !important;", "/* kept */", 1)
    vars_css = (
        ":root{"
        f"--pk-paper:{paper};"
        f"--pk-margin:{step['margin']}mm;"
        f"--pk-body:{step['body']}pt;"
        f"--pk-lead:{step['lead']};"
        "}"
    )
    page.add_style_tag(content=vars_css + "\n" + css)
    page.emulate_media(media="print")
    page.evaluate(SETTLE_JS)
    page.evaluate(DESHELL_JS)
    m = f"{step['margin']}mm"
    page.pdf(
        path=str(out_pdf),
        format=paper,
        landscape=landscape,
        print_background=True,
        prefer_css_page_size=True,
        margin={"top": m, "bottom": m, "left": m, "right": m},
    )


def render(source: str, out_pdf: Path, paper: str = "A4", margin: float | None = None,
           selector: str | None = None, wait_ms: int = 0, landscape: bool = False,
           loop: bool = True, keep_nav: bool = False) -> dict:
    from playwright.sync_api import sync_playwright

    url = source
    if not source.startswith(("http://", "https://", "file://")):
        url = Path(source).resolve().as_uri()

    ladder = [dict(s) for s in LADDER]
    if margin is not None:
        for s in ladder:
            s["margin"] = margin

    trace = {"source": url, "attempts": [], "final": None, "reason": ""}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            if wait_ms:
                page.wait_for_timeout(wait_ms)
            if selector and not page.evaluate(ISOLATE_JS, selector):
                print(f"warning: selector {selector!r} matched nothing; printing whole page",
                      file=sys.stderr)

            def attempt(step, label):
                _render_once(page, out_pdf, step, paper, landscape, keep_nav)
                stats = fillmod.measure(str(out_pdf), margin_mm=step["margin"])
                rec = {"label": label, "density": step, "pages": stats["pages"],
                       "last_fill": round(stats["last_page"], 3),
                       "mean_fill": round(stats["mean"], 3), "_stats": stats}
                trace["attempts"].append({k: v for k, v in rec.items() if k != "_stats"})
                return rec

            base = attempt(ladder[0], "base")
            best = base

            # A sparse page anywhere is worth chasing, not just a sparse last
            # page: a mid-document block that Chromium deferred leaves the same
            # hole, and it cannot go back and close it.
            worst = base["_stats"]["worst"]
            needs_work = base["pages"] > 1 and (
                base["last_fill"] < 0.55 or worst < 0.60
            )

            if not loop:
                trace["reason"] = "loop disabled"
            elif not needs_work:
                trace["reason"] = "density already within house limits"
            else:
                def score(a):
                    # Fewer pages first; then the fullest layout for that count.
                    return (a["pages"], -a["mean_fill"])

                for idx in range(1, len(ladder)):
                    a = attempt(ladder[idx], f"compress-{idx}")
                    if score(a) < score(best):
                        best = a
                    # Once a page has been shed and nothing is starved, stop.
                    if a["pages"] < base["pages"] and a["_stats"]["worst"] >= 0.60:
                        break

                if best["label"] == "base":
                    trace["reason"] = (
                        f"sparse page detected (worst {worst:.0%}), but no safe "
                        f"density improved it; left at house density"
                    )
                elif best["pages"] < base["pages"]:
                    trace["reason"] = (
                        f"tightened to {best['density']['body']}pt and shed a page "
                        f"({base['pages']} -> {best['pages']}), "
                        f"fill {base['mean_fill']:.0%} -> {best['mean_fill']:.0%}"
                    )
                else:
                    trace["reason"] = (
                        f"tightened to {best['density']['body']}pt to close a gap; "
                        f"fill {base['mean_fill']:.0%} -> {best['mean_fill']:.0%}"
                    )

            if trace["attempts"] and best["label"] != trace["attempts"][-1]["label"]:
                _render_once(page, out_pdf, best["density"], paper, landscape, keep_nav)
                best["_stats"] = fillmod.measure(str(out_pdf),
                                                 margin_mm=best["density"]["margin"])

            trace["final"] = {k: v for k, v in best.items() if k != "_stats"}
            trace["stats"] = best["_stats"]
            return trace
        finally:
            browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="URL or HTML file -> clean PDF")
    ap.add_argument("source", help="http(s) URL or path to an .html file")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--paper", default="A4")
    ap.add_argument("--margin", type=float, default=None, help="mm, overrides the ladder")
    ap.add_argument("--selector", default=None,
                    help="CSS selector for the region to print, e.g. 'main' or 'article'")
    ap.add_argument("--wait", type=int, default=0, help="extra settle time in ms")
    ap.add_argument("--landscape", action="store_true")
    ap.add_argument("--keep-nav", action="store_true", help="do not strip nav/sidebar/buttons")
    ap.add_argument("--no-loop", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    trace = render(args.source, out, paper=args.paper, margin=args.margin,
                   selector=args.selector, wait_ms=args.wait, landscape=args.landscape,
                   loop=not args.no_loop, keep_nav=args.keep_nav)

    if args.json:
        print(json.dumps({k: v for k, v in trace.items() if k != "stats"}, indent=2))
    else:
        s = trace["stats"]
        print(f"-> {out}")
        print(fillmod.report(s, FILL_TARGET))
        print(f"density: {trace['final']['density']}")
        print(f"note: {trace['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
