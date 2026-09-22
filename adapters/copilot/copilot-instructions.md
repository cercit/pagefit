# PDF generation

When a task produces a PDF — from markdown, notes, a report, a draft, a URL or
an HTML file — use `pagefit`. Do not hand-roll a PDF script and do not reach for
pandoc, LaTeX or `wkhtmltopdf`.

```bash
python src/pagefit/render.py INPUT.md -o OUT.pdf --title "Title"   # markdown/typst
python src/pagefit/web.py URL -o OUT.pdf --selector main           # url/html
```

Prefer the first whenever the source is text you control.

Chromium's print path is a greedy single-pass fragmenter: a block that does not
fit moves whole to the next page and the algorithm cannot go back to close the
gap. pagefit renders, measures the ink on each page, and re-renders tighter if
that absorbs a sparse page — capped at roughly 8% off base type.

Constraints: no cover page, no forced page break per section, margins 20-24mm,
body fill at or above 85%, block quotes keep their rule and tint, nothing that
behaves like a heading ends a page, tables under 12 rows stay whole.

Every run prints a per-page fill report. Read it before saying the PDF is done,
and report page count and mean fill. Never hand over a PDF you have not measured.
