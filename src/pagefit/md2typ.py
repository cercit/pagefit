"""
Markdown -> Typst markup.

Deliberately small. Covers what shows up in real documents: headings, emphasis,
code, links, lists, tables, quotes, rules, images. Anything exotic passes
through as escaped text rather than blowing up the compile.
"""

from __future__ import annotations

import re

# Characters that start Typst markup and must be neutralised in plain prose.
_ESCAPE = {"#": "\\#", "$": "\\$", "@": "\\@", "*": "\\*", "_": "\\_",
           "<": "\\<", ">": "\\>", "\\": "\\\\", "[": "\\[", "]": "\\]"}

# A table with this many body rows or fewer is kept on one page.
SHORT_TABLE_ROWS = 12

# Byline heuristic. A run of short lines with no sentence-ending punctuation is
# a title block or address, not prose, so its line breaks are meaningful.
#
# Applied ONLY to the document's opening block, which is where bylines live.
# Loose anywhere else it would mangle hard-wrapped prose: a paragraph wrapped at
# 72 columns also has short lines that mostly do not end in punctuation, and
# every one of those would gain a spurious break.
BYLINE_MAX_LEN = 72
BYLINE_MAX_LINES = 5


def _esc(s: str) -> str:
    return "".join(_ESCAPE.get(c, c) for c in s)


def _inline(s: str) -> str:
    """Convert inline markdown, protecting code spans from escaping."""
    out = []
    i = 0
    # Split on code spans first so their contents are never mangled.
    for part in re.split(r"(`[^`]+`)", s):
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(part)
            continue
        out.append(_inline_no_code(part))
    return "".join(out)


def _inline_no_code(s: str) -> str:
    tokens: list[str] = []

    def stash(rendered: str) -> str:
        tokens.append(rendered)
        return f"\x00{len(tokens) - 1}\x00"

    # images before links (they share bracket syntax)
    s = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)",
        lambda m: stash(f'#figure(image("{m.group(2)}", width: 88%), caption: [{_esc(m.group(1))}])'),
        s,
    )
    s = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)[^)]*\)",
        lambda m: stash(f'#link("{m.group(2)}")[{_esc(m.group(1))}]'),
        s,
    )
    # bare urls
    s = re.sub(r"(?<![\"(\w])(https?://[^\s<>\)]+)", lambda m: stash(f'#link("{m.group(1)}")'), s)
    # bold then italic
    s = re.sub(r"\*\*(.+?)\*\*", lambda m: stash(f"*{_inline_no_code(m.group(1))}*"), s)
    s = re.sub(r"__(.+?)__", lambda m: stash(f"*{_inline_no_code(m.group(1))}*"), s)
    s = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", lambda m: stash(f"_{_inline_no_code(m.group(1))}_"), s)
    s = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", lambda m: stash(f"_{_inline_no_code(m.group(1))}_"), s)
    s = re.sub(r"~~(.+?)~~", lambda m: stash(f"#strike[{_inline_no_code(m.group(1))}]"), s)

    s = _esc(s)
    # restore placeholders (escaping turned \x00N\x00 markers untouched)
    s = re.sub(r"\x00(\d+)\x00", lambda m: tokens[int(m.group(1))], s)
    return s


_BOLD_ONLY = re.compile(r"^\*\*((?:(?!\*\*).)+)\*\*$")


def _starts_block(st: str, raw: str) -> bool:
    """True if this line opens a construct the paragraph gatherer must not eat."""
    if st.startswith("```") or st.startswith(">"):
        return True
    if st.startswith("|") and "|" in st:
        return True
    if re.match(r"^#{1,6}\s+", st):
        return True
    if re.match(r"^(\*\s*){3,}$|^(-\s*){3,}$|^(_\s*){3,}$", st):
        return True
    if re.match(r"^(\s*)([-*+]|\d+[.)])\s+", raw):
        return True
    return False


def _paragraph(raw_lines: list[str], opening: bool = False) -> list[str]:
    """
    Render one paragraph.

    Markdown folds single newlines into a running paragraph, which is right for
    prose and wrong for a byline or address block, where the author wrote the
    breaks on purpose. Explicit CommonMark hard breaks (two trailing spaces or a
    trailing backslash) are honoured anywhere; the byline heuristic applies only
    when `opening` is set, i.e. the first block of the document.
    """
    stripped = [l.strip() for l in raw_lines]
    hard = [bool(re.search(r"(\s{2,}|\\)$", l)) for l in raw_lines]

    # A fully-bold single line introduces the block beneath it. It reads as a
    # heading, so it must not strand at the foot of a page without it.
    # Emitted self-contained: Typst's #include compiles body.typ in its own
    # scope, so a helper defined in the template is not visible here. Spacing is
    # in em so it still tracks the density loop's font size.
    if len(stripped) == 1 and _BOLD_ONLY.match(stripped[0]):
        return ["#block(sticky: true, above: 1.05em, below: 0.4em)["
                + _inline(stripped[0]) + "]"]

    byline = (
        opening
        and 1 < len(stripped) <= BYLINE_MAX_LINES
        and all(len(l) <= BYLINE_MAX_LEN for l in stripped)
        and not any(l.endswith((".", "!", "?", ":", ";")) for l in stripped)
    )

    if byline or any(hard):
        rendered = []
        for k, l in enumerate(stripped):
            txt = _inline(re.sub(r"[\s\\]+$", "", l))
            if k != len(stripped) - 1 and (byline or hard[k]):
                txt += " \\"
            rendered.append(txt)
        return rendered

    return [_inline(l) for l in stripped]


def _table(rows: list[str]) -> str:
    """Convert a pipe table. Row 0 is the header; the divider row is dropped."""
    def cells(line: str) -> list[str]:
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        return [c.strip() for c in line.split("|")]

    body = [r for r in rows if not re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", r)]
    if not body:
        return ""
    header = cells(body[0])
    n = len(header)

    out = [f"#table(", f"  columns: {n},", "  align: (left,) * %d," % n,
           "  table.header(" + ", ".join(f"[{_inline(c)}]" for c in header) + "),"]
    for line in body[1:]:
        cs = cells(line)
        cs = (cs + [""] * n)[:n]
        out.append("  " + ", ".join(f"[{_inline(c)}]" for c in cs) + ",")
    out.append(")")
    table = "\n".join(out)

    # A short table split across a page break looks like a mistake and leaves a
    # hole above it. Keep small ones whole; let genuinely long ones flow and
    # repeat their header.
    if len(body) - 1 <= SHORT_TABLE_ROWS:
        return "#block(breakable: false)[\n" + table + "\n]"
    return table


def convert(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    # strip a YAML front-matter block
    if lines and lines[0].strip() == "---":
        for j in range(1, n):
            if lines[j].strip() == "---":
                i = j + 1
                break

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # fenced code
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            buf = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("```" + lang)
            out.extend(buf)
            out.append("```")
            out.append("")
            continue

        # table
        if "|" in stripped and stripped.startswith("|"):
            buf = []
            while i < n and "|" in lines[i] and lines[i].strip().startswith("|"):
                buf.append(lines[i])
                i += 1
            out.append(_table(buf))
            out.append("")
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            out.append("=" * len(m.group(1)) + " " + _inline(m.group(2).strip("# ")))
            out.append("")
            i += 1
            continue

        # horizontal rule
        if re.match(r"^(\*\s*){3,}$|^(-\s*){3,}$|^(_\s*){3,}$", stripped):
            out.append("#line(length: 100%, stroke: 0.4pt + luma(190))")
            out.append("")
            i += 1
            continue

        # blockquote
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = " ".join(x.strip() for x in buf if x.strip())
            out.append(f"#quote(block: true)[{_inline(inner)}]")
            out.append("")
            continue

        # lists (indent-aware)
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if m:
            while i < n:
                mm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
                if not mm:
                    if lines[i].strip() == "":
                        break
                    # continuation line of the previous item
                    out[-1] = out[-1] + " " + _inline(lines[i].strip())
                    i += 1
                    continue
                depth = len(mm.group(1)) // 2
                marker = "+" if re.match(r"\d", mm.group(2)) else "-"
                out.append("  " * depth + marker + " " + _inline(mm.group(3)))
                i += 1
            out.append("")
            continue

        if stripped == "":
            out.append("")
            i += 1
            continue

        # paragraph — gather the whole block so line breaks can be judged in
        # context rather than one line at a time
        para: list[str] = []
        while i < n:
            nxt = lines[i]
            nst = nxt.strip()
            if nst == "" or (para and _starts_block(nst, nxt)):
                break
            para.append(nxt)
            i += 1

        # "Opening" means nothing but the document title has been emitted yet.
        body_so_far = [x for x in out if x.strip()]
        out.extend(_paragraph(para, opening=len(body_so_far) <= 1))
        out.append("")

    # collapse runs of blank lines
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
