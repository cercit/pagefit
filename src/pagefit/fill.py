"""
Page-fill measurement.

Implements the raster-projection idea from the pagination research: rasterise
each page, project it to a 1-D column of row-darkness, and report how much of
the live text block each page actually uses.

This is the check behind the house rule "body fill >= 85%". It is measured, not
eyeballed.
"""

from __future__ import annotations

import pymupdf as fitz

# A row counts as "inked" if at least this fraction of its pixels are non-white.
# Set above the width of a decorative vertical rule: a 1-3px rail running the
# full height of the sheet would otherwise mark every row as inked and report a
# nearly empty page as 100% full. Real text lines clear this easily.
ROW_INK_THRESHOLD = 0.012
# Pixel is non-white below this grey value (0 = black, 255 = white).
WHITE_CUTOFF = 245


def _page_rows(page, margin_mm: float, dpi: int = 72):
    """Return (inked_rows, total_rows) for the live area of one page."""
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    w, h = pix.width, pix.height
    buf = pix.samples

    # Crop the physical margin out so we measure the text block, not the sheet.
    inset = int(round(margin_mm / 25.4 * dpi))
    top, bot = inset, max(inset + 1, h - inset)
    left, right = inset, max(inset + 1, w - inset)
    band = max(1, right - left)

    inked = []
    for y in range(top, bot):
        base = y * w
        dark = 0
        for x in range(left, right):
            if buf[base + x] < WHITE_CUTOFF:
                dark += 1
        inked.append(dark / band >= ROW_INK_THRESHOLD)
    return inked


def measure(pdf_path: str, margin_mm: float = 20.0) -> dict:
    """
    Measure fill for every page of a PDF.

    Returns:
        {
          "pages": int,
          "per_page": [fill_ratio, ...],   # 0..1, share of live height used
          "last_page": float,              # fill of the final page
          "worst": float,                  # lowest fill on any page
          "mean": float,
        }

    "Fill" is the distance from the first inked row to the last inked row,
    divided by the live height. That measures where the content *ends*, which is
    what causes a page to look empty, rather than ink density, which would
    penalise a page for having whitespace between paragraphs.
    """
    doc = fitz.open(pdf_path)
    per_page = []
    try:
        for page in doc:
            rows = _page_rows(page, margin_mm)
            total = len(rows)
            if total == 0:
                per_page.append(0.0)
                continue
            first = next((i for i, v in enumerate(rows) if v), None)
            if first is None:
                per_page.append(0.0)
                continue
            last = total - 1 - next(i for i, v in enumerate(reversed(rows)) if v)
            per_page.append((last + 1) / total)
    finally:
        doc.close()

    if not per_page:
        return {"pages": 0, "per_page": [], "last_page": 0.0, "worst": 0.0, "mean": 0.0}

    return {
        "pages": len(per_page),
        "per_page": per_page,
        "last_page": per_page[-1],
        "worst": min(per_page),
        "mean": sum(per_page) / len(per_page),
    }


def report(stats: dict, target: float = 0.85) -> str:
    """Human-readable fill report."""
    if stats["pages"] == 0:
        return "empty document"
    lines = [f"{stats['pages']} page(s), mean fill {stats['mean']:.0%}"]
    for i, f in enumerate(stats["per_page"], 1):
        flag = "" if f >= target or i == stats["pages"] else "  <- sparse"
        lines.append(f"  p{i}: {f:.0%}{flag}")
    last = stats["last_page"]
    if stats["pages"] > 1 and last < 0.25:
        lines.append(f"  final page only {last:.0%} full - candidate for compression")
    return "\n".join(lines)
