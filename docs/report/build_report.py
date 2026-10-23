"""Build the major-project report PDF from report.md, with the same Markdown converter as the project book.

    python docs/report/build_report.py        # writes docs/report/UAV-NOMA-Report.pdf (needs requirements-docs.txt)

What it adds on top of docs/book/build_pdf.py:
- a title page from the block between <!-- titlepage --> and <!-- /titlepage -->;
- page breaks at <!-- pagebreak --> and the table of contents at <!-- toc -->;
- every other HTML comment (the source notes next to the numbers) is removed from the PDF;
- ```mermaid blocks (simple flowcharts: A["label"] --> B["label"]) are drawn with matplotlib, so the PDF shows a diagram
  rather than the Mermaid source. GitHub renders the same blocks natively.
"""
import re
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "book"))
import build_pdf as bp  # noqa: E402

SRC = HERE / "report.md"
OUT = HERE / "UAV-NOMA-Report.pdf"
BUILD = HERE / "build"

MERMAID = re.compile(r"```mermaid\s*\n(.*?)```", re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)
TITLE = re.compile(r"<!--\s*titlepage\s*-->(.*?)<!--\s*/titlepage\s*-->", re.S)
DIAGRAM_TAG = "DIAGRAM-PLACEHOLDER-{}"


# ---------------------------------------------------------------- Mermaid flowcharts -> PNG
NODE = re.compile(r'^([A-Za-z0-9_]+)\s*(?:\[\s*"?(.*?)"?\s*\])?$')
ARROW = re.compile(r"\s*(?:-->|-\.->|==>)\s*(?:\|([^|]*)\|\s*)?")


def parse_flowchart(src):
    """Nodes (ordered dict id -> label) and edges [(a, b, label)] of a simple Mermaid flowchart."""
    lines = [s.strip() for s in src.strip().splitlines() if s.strip() and not s.strip().startswith("%%")]
    direction = lines[0].split()[1] if len(lines[0].split()) > 1 else "TD"
    nodes, edges = {}, []
    for line in lines[1:]:
        parts = ARROW.split(line)                         # node, label, node, label, node ...
        ids = []
        for tok in parts[0::2]:
            m = NODE.match(tok.strip())
            if not m:
                raise ValueError(f"cannot parse Mermaid node: {tok!r}")
            nid, label = m.group(1), m.group(2)
            if label or nid not in nodes:
                nodes[nid] = label or nodes.get(nid, nid)
            ids.append(nid)
        for a, b, lab in zip(ids[:-1], ids[1:], parts[1::2], strict=True):
            edges.append((a, b, (lab or "").strip()))
    return direction, nodes, edges


def layers(nodes, edges):
    """Longest-path layering; nodes with successors are then pulled down next to their nearest successor."""
    layer = {n: 0 for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for a, b, _ in edges:
            if layer[b] < layer[a] + 1:
                layer[b], changed = layer[a] + 1, True
        if not changed:
            break
    succ = defaultdict(list)
    for a, b, _ in edges:
        succ[a].append(b)
    for n in sorted(nodes, key=lambda k: -layer[k]):
        if succ[n]:
            layer[n] = max(layer[n], min(layer[s] for s in succ[n]) - 1)
    return layer


def layout(nodes, edges, direction):
    """Positions in axes fractions, label wrap width per node, and the figure size in inches."""
    layer = layers(nodes, edges)
    rows = defaultdict(list)
    for n in nodes:
        rows[layer[n]].append(n)
    n_layers = max(rows) + 1
    widest = max(len(r) for r in rows.values())
    pos, wrap = {}, {}
    if widest == 1 and n_layers > 4:                      # a long chain: snake it left-right in rows of 3
        cols = 3
        n_rows = -(-n_layers // cols)
        for li, (n,) in sorted(rows.items()):
            r, c = divmod(li, cols)
            c = c if r % 2 == 0 else cols - 1 - c
            pos[n] = ((c + 0.5) / cols, 1 - (r + 0.5) / n_rows)
            wrap[n] = 26
        return pos, wrap, (6.6, 1.0 * n_rows + 0.2)
    horizontal = direction in ("LR", "RL")
    for li, row in rows.items():
        k = len(row)
        for i, n in enumerate(row):
            a = (li + 0.5) / n_layers                     # position along the flow
            b = (i + 1) / (k + 1)                         # position across the flow
            pos[n] = (a, 1 - b) if horizontal else (b, 1 - a)
            wrap[n] = 22 if horizontal else max(14, int(80 / k))
    size = (1.9 * n_layers + 0.4, 0.75 * widest + 0.4) if horizontal else (6.6, 0.72 * n_layers + 0.25)
    return pos, wrap, size


def render_mermaid(src, out_png):
    direction, nodes, edges = parse_flowchart(src)
    pos, wrap, size = layout(nodes, edges, direction)
    fig = plt.figure(figsize=size, dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    texts = {}
    for n, xy in pos.items():
        label = "\n".join(textwrap.wrap(nodes[n].replace("<br/>", " "), wrap[n])) or n
        texts[n] = ax.text(*xy, label, ha="center", va="center", fontsize=7.5, color="#1a1a1a",
                           transform=ax.transAxes, zorder=3,
                           bbox=dict(boxstyle="round,pad=0.45", fc="#e6edf5", ec="#1f3a5f", lw=0.8))
    fig.canvas.draw()                                     # place the boxes first, so the arrows can be clipped to them
    for a, b, lab in edges:
        ax.annotate("", xy=pos[b], xytext=pos[a], xycoords="axes fraction", zorder=2,
                    arrowprops=dict(arrowstyle="-|>", color="#555555", lw=0.9, shrinkA=1, shrinkB=1,
                                    patchA=texts[a].get_bbox_patch(), patchB=texts[b].get_bbox_patch()))
        if lab:
            mx, my = (pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2
            ax.text(mx, my, lab, fontsize=6.5, style="italic", ha="center", va="center", transform=ax.transAxes,
                    bbox=dict(fc="white", ec="none", pad=0.5), zorder=4)
    fig.savefig(out_png, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- Markdown pre-processing
class MdText:
    """A stand-in Path for build_pdf.chapter_flowables: text in memory, pictures resolved relative to docs/report."""

    def __init__(self, text):
        self._text, self.parent = text, HERE

    def read_text(self, encoding=None):
        return self._text


def title_page(block):
    story = [bp.Spacer(1, 3 * bp.cm)]
    for para in re.split(r"\n\s*\n", COMMENT.sub("", block).strip()):
        line = " ".join(s.strip() for s in para.splitlines())
        if line.startswith("# "):
            story += [bp.Paragraph(bp.inline(line[2:], []), bp.S["title"]), bp.Spacer(1, 0.4 * bp.cm)]
        else:
            story += [bp.Paragraph(bp.inline(line, []), bp.S["subtitle"]), bp.Spacer(1, 0.25 * bp.cm)]
    return story


def build():
    BUILD.mkdir(exist_ok=True)
    text = SRC.read_text(encoding="utf-8")
    m = TITLE.search(text)
    story = title_page(m.group(1)) if m else []
    text = text[m.end():] if m else text

    diagrams = {}

    def diagram(mm):
        i = len(diagrams) + 1
        png = BUILD / f"diagram_{i}.png"
        render_mermaid(mm.group(1), png)
        diagrams[DIAGRAM_TAG.format(i)] = png
        return DIAGRAM_TAG.format(i)

    text = MERMAID.sub(diagram, text)
    text = re.sub(r"<!--\s*pagebreak\s*-->", "\n@@PAGEBREAK@@\n", text)
    text = re.sub(r"<!--\s*toc\s*-->", "\n@@TOC@@\n", text)
    text = COMMENT.sub("", text)

    toc = bp.TableOfContents()
    toc.levelStyles = [bp.S["toc1"], bp.S["toc2"]]
    for part in re.split(r"\n(@@PAGEBREAK@@|@@TOC@@)\n", text):
        if part == "@@PAGEBREAK@@":
            story.append(bp.PageBreak())
            continue
        if part == "@@TOC@@":
            story += [bp.PageBreak(), bp.Paragraph("Contents", bp.S["h1"]), toc, bp.PageBreak()]
            continue
        if not part.strip():
            continue
        for f in bp.chapter_flowables(MdText(part)):
            tag = f.getPlainText().strip() if isinstance(f, bp.Paragraph) else None
            if tag in diagrams:                           # swap the placeholder paragraph for the drawn diagram
                with bp.Image.open(diagrams[tag]) as im:
                    w, h = im.size
                width = min(bp.PAGE_W, 16 * bp.cm)
                height = width * h / w
                if height > 20 * bp.cm:
                    height = 20 * bp.cm
                    width = height * w / h
                keep = [bp.RLImage(str(diagrams[tag]), width=width, height=height), bp.Spacer(1, 8)]
                if story and isinstance(story[-1], bp.Paragraph) and story[-1].getPlainText().startswith("Figure"):
                    keep.insert(0, story.pop())           # keep the caption on the same page as its diagram
                story.append(bp.KeepTogether(keep))
            elif (isinstance(f, bp.Table) and story and isinstance(story[-1], bp.Paragraph)
                  and story[-1].getPlainText().startswith("Table")):
                story.append(bp.KeepTogether([story.pop(), f]))   # keep a table caption with its table
            else:
                story.append(f)
    ReportDoc(OUT).multiBuild(story)
    return OUT


class ReportDoc(bp.BookDoc):
    def __init__(self, path):
        super().__init__(path)
        self.title = "UAV-NOMA Disaster Network Planning Simulator: Major Project Report"

    @staticmethod
    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont("DV", 7.5)
        canvas.setFillColor(bp.colors.HexColor("#777777"))
        canvas.drawString(2 * bp.cm, 1.2 * bp.cm, "UAV-NOMA Disaster Network Planning Simulator: Major Project Report")
        canvas.drawRightString(bp.A4[0] - 2 * bp.cm, 1.2 * bp.cm, f"page {doc.page}")
        canvas.restoreState()


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB), {len(bp._embedded)} pictures embedded")
