# pagefit

**Markdown to PDF that measures its own output and stops producing half-empty pages.**

Most markdown-to-PDF tools render once and hand you the result. If a section lands badly and leaves the bottom third of a sheet blank, that is what you get. pagefit rasterises every page it produces, measures how much of the live text area actually carries ink, and re-renders slightly tighter if that absorbs a sparse page.

A real example. A 26-page study document, hand-tuned, averaged 72% page fill with twelve pages under 88% — one was 8% full. Run through pagefit it came out at 17 pages and 96% mean fill, at full base type size.

**Works with most AI coding agents.** It is a plain command-line tool, so any agent that can run a shell command can use it. Tested end to end with **Claude Code**, **Codex** and **Hermes Agent**. All three produced the identical PDF from the same test document. Instruction files for other agents are in [`adapters/`](#using-it-from-an-ai-coding-agent).

---

## The problem it solves

Chromium's print path, and Typst's, and almost every other paginator you will meet, are greedy single-pass fragmenters. When a block does not fit in the space left on a page, the whole block moves to the next page and the algorithm cannot go back to close the hole it just opened.

That is the cause of most ugly generated PDFs: a heading stranded at the foot of a page, a short table sliced across a break, the bottom half of a sheet blank. You cannot fix it from CSS alone, because CSS cannot see the outcome.

The fix is an outer loop. Render, look at what came out, adjust, render again — and keep the result only if it actually helped.

## What it does not claim

TeX solved the harder version of this in 1981. Knuth-Plass considers all break points together and optimises globally, which is strictly better than re-rendering at a different size and hoping. `\looseness` and `\enlargethispage` are the manual escape hatches.

pagefit is cruder than that on purpose. It cannot reflow globally, because it sits on top of a greedy paginator chosen for being fast and installable without admin rights. If you already have a working LaTeX toolchain, you do not need this.

---

## Install

```bash
pip install typst pymupdf
python -m playwright install chromium   # only if you need the web path
```

If `import typst` fails later, the thing running pagefit is using a different Python from the one you installed into. This happens a lot with AI agents and desktop apps that bundle their own. Install with that same Python:

```bash
python -m pip install typst pymupdf
```

`typst` ships as a self-contained binary inside the wheel. No system libraries, no GTK, no admin rights. That is the reason it is used here instead of WeasyPrint, which needs Pango installed system-wide and will not work on a locked-down machine.

## Use

Markdown or Typst source:

```bash
python src/pagefit/render.py notes.md -o notes.pdf --title "Session 07"
```

A live URL or a local HTML file:

```bash
python src/pagefit/web.py https://example.com -o out.pdf --selector main
```

Both print a fill report per page and say what the density loop decided.

```
17 page(s), mean fill 96%
  p1: 89%
  p2: 99%
  ...
density: {'body': 10.5, 'lead': 0.72, 'spacing': 1.0, 'margin': 22.0}
note: density already within house limits
```

### Options

`render.py` — `--title`, `--subtitle`, `--paper a4|a5|us-letter`, `--accent "#1f2933"`, `--footer`, `--fit` (expand an airy one-pager rather than shrink it), `--no-loop`, `--json`

`web.py` — `--selector 'main'`, `--paper`, `--margin MM`, `--wait MS`, `--landscape`, `--keep-nav`, `--no-loop`, `--json`

Prefer the Typst path whenever the source is text you control. It is deterministic, needs no browser, and runs in about 200ms.

---

## The loop

1. Render at house density — 10.5pt type, 22mm margins.
2. Rasterise each page, project it to a column of row-darkness, measure how far down the live area content reaches.
3. If a page is sparse, step one notch tighter and re-render. Keep the result only if it sheds a page or meaningfully raises fill.
4. Stop at 9.7pt and 20mm. That is roughly 8% off base type, about where a reader starts to notice. If a page cannot be absorbed inside that budget, the page stays and nothing gets squashed.

Step 4 is the part that matters. Compression nobody notices is free. Past that you are just shipping a smaller document pretending to be a tidier one.

### Measuring fill honestly

Exclude the running header and footer bands before you measure. Include them and every page reads as 100% full, because a header and a page number touch the top and bottom of every sheet. The measurement becomes worthless and you will not notice.

`ROW_INK_THRESHOLD` in `fill.py` sets how much ink a row needs before it counts as used. It sits deliberately above the width of a decorative vertical rule — a full-height ornamental line would otherwise mark every row as inked and report a nearly empty page as completely full.

---

## House rules

Baked into `template.typ` and `preflight.css`:

- No cover page. The title block sits inline at the top of page 1.
- No forced page break per section. Sections flow.
- Margins 20–24mm.
- Body fill at or above 85%, measured before handover.
- Block quotes get a rule, a tint and italics — never a bare indent. In most documents a quote is the line being cited or spoken; rendered as a plain indent it becomes indistinguishable from the prose around it and the document loses meaning.
- Nothing that behaves like a heading ends a page. That includes real headings and fully-bold lead-in paragraphs.
- Tables under 12 rows stay whole. Longer ones flow and repeat their header.

Quotes are the one self-contained unit allowed to split. A non-breakable quote that does not fit gets deferred whole to the next page, which is the single biggest source of half-empty pages in a quote-heavy document. The tint and the left rule carry across the break, so a split quote still reads as one unit.

---

## Using it from an AI coding agent

pagefit is a plain Python CLI, so anything that can run a shell command can drive it. The `adapters/` directory has ready-made instruction files:

| Platform | File | Status |
|---|---|---|
| Claude Code | `adapters/claude-code/print.md` → `.claude/agents/` | Tested |
| Codex | `adapters/agents/AGENTS.md` → repo root | Tested |
| Hermes Agent (desktop app) | `adapters/agents/AGENTS.md` → repo root | Tested |
| Cursor | `adapters/cursor/pagefit.mdc` → `.cursor/rules/` | Untested |
| GitHub Copilot | `adapters/copilot/copilot-instructions.md` → `.github/` | Untested |
| OpenCode, Amp | `adapters/agents/AGENTS.md` → repo root | Untested |
| Gemini CLI | `adapters/gemini/GEMINI.md` | Untested |

**How "tested" was checked.** Each agent got the same short test document and the same instruction: read the adapter file, make the PDF with pagefit, report the fill. I did not take their word for it. For each one I checked that the PDF actually existed, that Typst produced it (so the agent had not written its own converter), and I re-measured the fill myself. All three came out at 2 pages and 87% fill, with the text identical page for page.

**On "untested".** Those files follow each platform's published instruction-file format, which I am confident is right, but I have not run them myself. If you try one, an issue saying whether it worked is genuinely useful.

**One thing that tripped an agent up.** The Hermes desktop app runs its own copy of Python, not the one pagefit was installed into, so its first try failed with `No module named 'typst'`. It fixed that itself. A weaker agent might not, so the adapter files now say how to fix it.

Nothing about the tool is platform-specific. If your agent is not listed, point it at the CLI and the README.

---

## Tuning

Density ladders are `LADDER` and `EXPAND` at the top of `render.py` and `web.py`. The 20mm margin floor and the 8% type floor are deliberate; raise them only with a reason.

`SHORT_TABLE_ROWS` in `md2typ.py` is the cutoff below which a table is kept on one page.

`BYLINE_MAX_LEN` and `BYLINE_MAX_LINES` govern the byline heuristic. Markdown folds single newlines into a running paragraph, which is right for prose and wrong for a title block where the author meant the breaks. The heuristic fires only on the document's opening block — applied everywhere it would put a spurious break on every line of hard-wrapped prose. Explicit CommonMark hard breaks, two trailing spaces or a trailing backslash, are honoured anywhere.

## Files

| File | What it does |
|---|---|
| `render.py` | Markdown/Typst → PDF, with the density loop |
| `web.py` | URL/HTML → PDF via headless Chromium, same loop |
| `md2typ.py` | Markdown → Typst markup |
| `template.typ` | Document template; house rules live here |
| `preflight.css` | Defensive print CSS injected into web pages |
| `fill.py` | Page-fill measurement |

## Web path failure modes

If a URL produces blank or near-empty pages it is almost always one of these. All are already handled, listed so you know what to look for when something new breaks.

1. **Scroll-reveal animations.** Content sits at `opacity: 0` until an IntersectionObserver fires, which never happens in a headless print. The toolkit scrolls the page and forces the settled state.
2. **Printing before assets settle.** Fonts and images resolve after layout is computed, everything reflows, pages drift. Handled via `document.fonts.ready` and `img.decode()`.
3. **Viewport-height hero sections.** `100vh` becomes a page-height void. Reset to `min-height: 0`.
4. **Screen furniture.** Nav bars, sidebars, cookie banners. Stripped unless you pass `--keep-nav`.
5. **Decorative rails.** Full-height ornamental lines add noise and defeat fill measurement. Stripped structurally.

Reach for `--selector` to print one content region before you start adding CSS hacks.

## Licence

MIT. See [LICENSE](LICENSE).
