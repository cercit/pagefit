# pagefit — PDF generation

Applies to any task that produces a PDF — from a markdown file, notes, a report,
a draft, a live URL, or an HTML file.

Use `pagefit`. Do not hand-roll a PDF script, and do not reach for pandoc,
LaTeX or `wkhtmltopdf`.

## Why

Chromium's print path, and most paginators, are greedy single-pass fragmenters.
When a block does not fit in the space left on a page the whole block moves to
the next page, and the algorithm cannot go back to close the hole it just made.
That is what produces a heading stranded at the foot of a page, a table sliced
mid-row, the bottom half of a sheet blank.

CSS alone cannot fix it, because CSS cannot see the outcome. pagefit renders,
measures how much of each page actually carries ink, and re-renders slightly
tighter if that absorbs a sparse page — capped at about 8% off base type size.

## Commands

Markdown or Typst source:

    python src/pagefit/render.py INPUT.md -o OUT.pdf --title "Title"

A live URL or a local HTML file:

    python src/pagefit/web.py URL -o OUT.pdf --selector main

Prefer the first whenever the source is text you control. It is deterministic,
needs no browser, and runs in about 200ms.

## Rules

- No cover page; the title block is inline on page 1.
- No forced page break per section.
- Margins 20-24mm.
- Body fill at or above 85%, measured, before you hand anything over.
- Block quotes keep their rule, tint and italics. A quote rendered as a bare
  indent is indistinguishable from the prose around it.
- Nothing that behaves like a heading ends a page.
- Tables under 12 rows stay whole.

## Never hand over an unmeasured PDF

Every run prints per-page fill and what the density loop decided. Read it. If a
page below 85% is not the last page, a block was deferred — usually a table or
an image too tall for the space left. If the run warns that the final page is
still sparse, the loop hit its safety cap: do not force more compression, say so
and offer to trim the content instead.

Report the path, the page count and the mean fill. If a page is still sparse,
say so rather than burying it.

## If `import typst` fails

You are probably running a different Python from the one pagefit was installed
into. AI agents and desktop apps often bundle their own. Install into the same
Python that runs the command, then retry:

    python -m pip install typst pymupdf

Tell the user you installed it. Do not switch to another converter instead.
