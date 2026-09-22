// ============================================================
//  pagefit — house document template
//
//  Density is driven from outside via sys.inputs so the render
//  loop can retune it without rewriting the document.
//
//  House rules baked in:
//    - no forced page break per section
//    - no cover page
//    - margins 20-24mm
//    - headings stay with their content (Typst default + explicit)
//    - tables repeat their header row across pages
//    - blocks never split mid-unit
// ============================================================

#let num(key, fallback) = {
  let v = sys.inputs.at(key, default: none)
  if v == none { fallback } else { float(v) }
}
#let str-in(key, fallback) = {
  let v = sys.inputs.at(key, default: none)
  if v == none { fallback } else { v }
}

// ---- density knobs (the render loop varies these) ----
#let BODY     = num("body", 10.5) * 1pt      // body font size
#let LEAD     = num("lead", 0.72)            // leading multiplier
#let MARGIN   = num("margin", 22.0) * 1mm    // page margin
#let SPACING  = num("spacing", 1.0)          // block-spacing scale

#let TITLE  = str-in("title", "")
#let SUB    = str-in("subtitle", "")
#let PAPER  = str-in("paper", "a4")
#let ACCENT = rgb(str-in("accent", "#1f2933"))
#let FOOT   = str-in("footer", "")

#set document(title: TITLE)

#set page(
  paper: PAPER,
  margin: MARGIN,
  footer: context {
    let n = counter(page).get().first()
    let total = counter(page).final().first()
    // Single-page documents get no footer furniture.
    if total > 1 {
      set text(size: 7.5pt, fill: luma(110))
      grid(
        columns: (1fr, auto),
        align(left)[#FOOT],
        align(right)[#n / #total],
      )
    }
  },
)

#set text(
  font: ("Charter", "Georgia", "Cambria", "Times New Roman"),
  size: BODY,
  lang: "en",
)

#set par(
  leading: LEAD * 1em,
  justify: true,
  spacing: SPACING * 1.1em,
)

// Never strand a single line at a page boundary.
#set par(first-line-indent: 0pt)
#show par: set block(spacing: SPACING * 1.05em)

// ---- headings ----
// Typst keeps headings with the block that follows by default; these
// only tune the rhythm, they do not need break-avoidance bolted on.
#show heading: set block(sticky: true)

// Level 1 carries a hairline rule. In a reference document that gets scanned
// rather than read straight through, the rule is what makes a section boundary
// findable at arm's length; size alone is not enough.
#show heading.where(level: 1): it => block(
  above: SPACING * 1.6em,
  below: SPACING * 0.7em,
  sticky: true,
)[
  #set text(size: BODY * 1.45, weight: "bold", fill: ACCENT)
  #it.body
  #v(0.22em)
  #line(length: 100%, stroke: 0.9pt + ACCENT)
]

#show heading.where(level: 2): it => block(
  above: SPACING * 1.25em,
  below: SPACING * 0.55em,
  sticky: true,
)[
  #set text(size: BODY * 1.15, weight: "bold", fill: ACCENT)
  #it.body
]

#show heading.where(level: 3): it => block(
  above: SPACING * 1.45em,
  below: SPACING * 0.3em,
  sticky: true,
)[
  #set text(size: BODY * 1.0, weight: "bold", style: "italic")
  #it.body
]

// ---- tables: header repeats, rows never split ----
#set table(
  stroke: (x, y) => (
    top: if y == 0 { 0.8pt + ACCENT } else if y == 1 { 0.5pt + luma(150) } else { 0pt },
    bottom: 0.4pt + luma(210),
  ),
  inset: (x: 0.6em, y: 0.42em),
)
#show table.cell.where(y: 0): set text(weight: "bold", size: BODY * 0.92)
#show table: set text(size: BODY * 0.94)
#show table: set block(breakable: true)

// ---- self-contained units never split across a page ----
#show figure: set block(breakable: false)

// ---- block quotes ----
// Quotes carry meaning in a lot of documents: the line you say out loud, the
// passage being cited. Typst's default renders them as a bare indent, which
// makes them indistinguishable from the prose around them. They get a rule, a
// tint and italics so the distinction survives printing.
//
// They are deliberately breakable. A non-breakable quote that does not fit is
// deferred whole to the next page, which is the single biggest source of
// half-empty pages in a quote-heavy document. Typst continues the fill and the
// left rule across the break, so a split quote still reads as one unit.
#let QUOTE_TINT = ACCENT.lighten(93%)

#show quote.where(block: true): it => block(
  width: 100%,
  breakable: true,
  above: SPACING * 0.95em,
  below: SPACING * 0.95em,
  fill: QUOTE_TINT,
  stroke: (left: 2pt + ACCENT),
  inset: (left: 0.95em, rest: 0.7em),
)[
  #set text(style: "italic", size: BODY * 0.98)
  #set par(justify: true)
  #it.body
]

// ---- lead-in paragraphs ----
// A fully-bold paragraph introducing the block beneath it behaves like a
// heading but is not one, so the heading sticky rule above never caught it.
// Left alone it strands at the foot of a page while the block it introduces
// moves on without it.
//
// md2typ emits these as a self-contained `#block(sticky: true)`. It cannot call
// a helper defined here: `#include` compiles body.typ in its own scope, so
// nothing bound in this file is visible inside it.

#show raw.where(block: true): it => block(
  width: 100%,
  fill: luma(247),
  inset: (x: 0.8em, y: 0.65em),
  radius: 2pt,
  breakable: false,
)[#set text(size: BODY * 0.85, font: ("Cascadia Code", "Consolas", "Menlo")); #it]

#set list(indent: 0.7em, spacing: SPACING * 0.75em)
#set enum(indent: 0.7em, spacing: SPACING * 0.75em)

#show link: set text(fill: ACCENT)

// ---- title block: inline, never a cover page ----
#if TITLE != "" {
  block(below: SPACING * 1.3em, sticky: true)[
    #set text(size: BODY * 1.75, weight: "bold", fill: ACCENT)
    #TITLE
    #if SUB != "" {
      linebreak()
      set text(size: BODY * 0.95, weight: "regular", fill: luma(95), style: "italic")
      SUB
    }
    #v(0.35em)
    #line(length: 100%, stroke: 1.2pt + ACCENT)
  ]
}

#include "body.typ"
