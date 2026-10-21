"""Build the project book PDF from the Markdown chapters in this folder.

    python docs/book/build_pdf.py            # writes docs/book/UAV-NOMA-Project-Book.pdf

Run it after every change to the book (CLAUDE.md rule). Needs reportlab and Pillow (Pillow comes with matplotlib).
It understands the Markdown used in the book: headings, paragraphs, bullet and numbered lists, tables, code blocks,
quotes, **bold**, *italic*, `code` and links. A link to a picture in figures/ also embeds the picture (once); a GIF is
shown as its last frame, with a note that the animation is in the repository.
"""
import datetime
import re
from pathlib import Path

import matplotlib
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
)
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.doctemplate import BaseDocTemplate, PageTemplate
from reportlab.platypus.frames import Frame
from reportlab.platypus.tableofcontents import TableOfContents

HERE = Path(__file__).parent
OUT = HERE / "UAV-NOMA-Project-Book.pdf"
BUILD = HERE / "build"
CHAPTERS = ["README.md"] + sorted(p.name for p in HERE.glob("[0-9][0-9]-*.md"))
PAGE_W = A4[0] - 4 * cm                     # usable text width

# ---------------------------------------------------------------- fonts (DejaVu ships with matplotlib: full Unicode)
FONT_DIR = Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf"
for name, file in [("DV", "DejaVuSans.ttf"), ("DV-B", "DejaVuSans-Bold.ttf"), ("DV-I", "DejaVuSans-Oblique.ttf"),
                   ("DV-BI", "DejaVuSans-BoldOblique.ttf"), ("DVM", "DejaVuSansMono.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-BI")

base = getSampleStyleSheet()
S = {
    "body": ParagraphStyle("body", parent=base["BodyText"], fontName="DV", fontSize=9.5, leading=13, spaceAfter=5),
    "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="DV-B", fontSize=18, leading=22, spaceBefore=6,
                         spaceAfter=10, textColor=colors.HexColor("#1f3a5f")),
    "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="DV-B", fontSize=13, leading=16, spaceBefore=10,
                         spaceAfter=6, textColor=colors.HexColor("#1f3a5f")),
    "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName="DV-B", fontSize=11, leading=14, spaceBefore=8,
                         spaceAfter=4),
    "h4": ParagraphStyle("h4", parent=base["Heading4"], fontName="DV-B", fontSize=10, leading=13, spaceBefore=6,
                         spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName="DV", fontSize=7.5, leading=9.5),
    "cellh": ParagraphStyle("cellh", fontName="DV-B", fontSize=7.5, leading=9.5),
    "code": ParagraphStyle("code", fontName="DVM", fontSize=7.5, leading=9.5, leftIndent=8,
                           backColor=colors.HexColor("#f3f3f3"), borderPadding=4, spaceBefore=3, spaceAfter=6),
    "quote": ParagraphStyle("quote", parent=base["BodyText"], fontName="DV-I", fontSize=9.5, leading=13, leftIndent=14,
                            textColor=colors.HexColor("#444444")),
    "caption": ParagraphStyle("caption", fontName="DV-I", fontSize=8, leading=10, alignment=TA_CENTER,
                              textColor=colors.HexColor("#555555"), spaceAfter=8),
    "title": ParagraphStyle("title", fontName="DV-B", fontSize=26, leading=32, alignment=TA_CENTER, spaceAfter=14,
                            textColor=colors.HexColor("#1f3a5f")),
    "subtitle": ParagraphStyle("subtitle", fontName="DV", fontSize=12, leading=16, alignment=TA_CENTER),
    "toc1": ParagraphStyle("toc1", fontName="DV-B", fontSize=10, leading=14, leftIndent=0),
    "toc2": ParagraphStyle("toc2", fontName="DV", fontSize=8.5, leading=11, leftIndent=14),
}


# ---------------------------------------------------------------- inline Markdown -> ReportLab mini-HTML
def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def inline(text, images):
    """Convert inline Markdown. Picture links are collected into `images` (to embed after the block)."""
    codes = []

    def keep_code(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", keep_code, text)

    def link(m):
        label, url = m.group(1), m.group(2)
        if re.search(r"\.(png|gif|jpg)$", url, re.I) and "figures/" in url:
            images.append(url)
            return f"\x01{label}\x01"
        if url.startswith("http"):
            return f"\x02{label}\x03{url}\x02"
        return f"\x01{label}\x01"                           # links to other chapters: keep the words

    text = LINK.sub(link, text)
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?![\s*])([^*\n]+?)(?<![\s*])\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"\x01(.+?)\x01", r'<font color="#1f5fa8">\1</font>', text)
    text = re.sub(r"\x02(.+?)\x03(.+?)\x02", r'<link href="\2" color="#1f5fa8">\1</link>', text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: f'<font face="DVM" size="8">{esc(codes[int(m.group(1))])}</font>', text)
    return text


# ---------------------------------------------------------------- pictures
_embedded = set()


def picture(url, chapter_dir):
    """Flowables for a referenced picture (each picture only once in the whole book)."""
    path = (chapter_dir / url).resolve()
    if path in _embedded or not path.exists():
        return []
    _embedded.add(path)
    note = ""
    if path.suffix.lower() == ".gif":                      # PDFs cannot animate: show the last frame
        BUILD.mkdir(exist_ok=True)
        with Image.open(path) as im:
            im.seek(getattr(im, "n_frames", 1) - 1)
            still = BUILD / (path.stem + "_last.png")
            im.convert("RGB").save(still)
        note = " (last frame of the animation; the GIF is in docs/book/figures/gifs/)"
        path = still
    with Image.open(path) as im:
        w, h = im.size
    width = min(PAGE_W, 16 * cm)
    height = width * h / w
    if height > 18 * cm:
        height = 18 * cm
        width = height * w / h
    return [KeepTogether([RLImage(str(path), width=width, height=height),
                          Paragraph(f"Figure: {esc(path.name if not note else Path(url).name)}{note}", S["caption"])])]


# ---------------------------------------------------------------- block Markdown -> flowables
def table(rows, chapter_dir, story_after):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [c for i, c in enumerate(cells) if not (i == 1 and all(re.fullmatch(r":?-{2,}:?", x) for x in c if x))]
    n = max(len(r) for r in cells)
    data = []
    for i, r in enumerate(cells):
        r = r + [""] * (n - len(r))
        imgs = []
        data.append([Paragraph(inline(c, imgs), S["cellh" if i == 0 else "cell"]) for c in r])
        for u in imgs:
            story_after.extend(picture(u, chapter_dir))
    lengths = [max(len(r[j]) if j < len(r) else 0 for r in cells) + 4 for j in range(n)]
    total = sum(lengths)
    widths = [max(PAGE_W * L / total, 1.2 * cm) for L in lengths]
    scale = PAGE_W / sum(widths)
    widths = [w * scale for w in widths]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6edf5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


LIST_ITEM = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def chapter_flowables(md_path):
    lines = md_path.read_text(encoding="utf-8").splitlines()
    story, i = [], 0
    chapter_dir = md_path.parent

    def para(text, style="body"):
        imgs = []
        story.append(Paragraph(inline(text, imgs), S[style]))
        for u in imgs:
            story.extend(picture(u, chapter_dir))

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):                              # code block (indented fences allowed)
            block, i = [], i + 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            indent = min((len(b) - len(b.lstrip()) for b in block if b.strip()), default=0)
            story.append(Preformatted("\n".join(b[indent:] for b in block), S["code"]))
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            level = len(m.group(1))
            p = Paragraph(inline(m.group(2), []), S[f"h{level}"])
            p._toc_level = level                             # picked up by the table of contents
            story.append(p)
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            after = []
            story.append(table(rows, chapter_dir, after))
            story.append(Spacer(1, 6))
            story.extend(after)
            continue
        if s == "---":
            story.append(Spacer(1, 8))
            i += 1
            continue
        if s.startswith(">"):
            block = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                block.append(lines[i].strip().lstrip(">").strip())
                i += 1
            para(" ".join(block), "quote")
            continue
        if LIST_ITEM.match(line):                            # a list item plus its wrapped continuation lines
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("```", "|", "#")):
                m = LIST_ITEM.match(lines[i])
                if not m:
                    break
                depth = len(m.group(1)) // 2
                bullet = m.group(2) if m.group(2)[0].isdigit() else "•"
                text = [m.group(3)]
                i += 1
                while (i < len(lines) and lines[i].strip() and not LIST_ITEM.match(lines[i])
                       and not lines[i].strip().startswith(("```", "|", "#", ">"))):
                    text.append(lines[i].strip())
                    i += 1
                imgs = []
                style = ParagraphStyle("li", parent=S["body"], leftIndent=14 + 14 * depth, bulletIndent=3 + 14 * depth,
                                       spaceAfter=2)
                story.append(Paragraph(inline(" ".join(text), imgs), style, bulletText=bullet))
                for u in imgs:
                    story.extend(picture(u, chapter_dir))
            story.append(Spacer(1, 3))
            continue
        block = [lines[i].strip()]                           # an ordinary paragraph (always takes its first line,
        i += 1                                               # e.g. "#2, #3 merged" is text, not a heading)
        while (i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("```", "|", "#", ">"))
               and not LIST_ITEM.match(lines[i]) and lines[i].strip() != "---"):
            block.append(lines[i].strip())
            i += 1
        para(" ".join(block))
    return story


# ---------------------------------------------------------------- document with page numbers and a table of contents
class BookDoc(BaseDocTemplate):
    def __init__(self, path):
        super().__init__(str(path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm,
                         bottomMargin=2 * cm, title="UAV-NOMA Project Book", author="UAV-NOMA project team")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=self.decorate)])

    @staticmethod
    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont("DV", 7.5)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(2 * cm, 1.2 * cm, "UAV-NOMA Disaster Network Planning Simulator: Project Book")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"page {doc.page}")
        canvas.restoreState()

    def afterFlowable(self, flowable):
        level = getattr(flowable, "_toc_level", None)
        if level in (1, 2):
            self.notify("TOCEntry", (level - 1, flowable.getPlainText(), self.page))


def build():
    story = [Spacer(1, 6 * cm), Paragraph("UAV-NOMA Disaster Network Planning Simulator", S["title"]),
             Paragraph("Project Book", S["title"]),
             Spacer(1, 1 * cm),
             Paragraph("A simulation-based planning tool for drone base stations using NOMA in disaster areas",
                       S["subtitle"]),
             Spacer(1, 0.5 * cm),
             Paragraph(f"Generated {datetime.date.today():%d %B %Y} from docs/book/ "
                       "(the Markdown chapters are the source; this PDF is rebuilt after every change)", S["subtitle"]),
             PageBreak()]
    toc = TableOfContents()
    toc.levelStyles = [S["toc1"], S["toc2"]]
    story += [Paragraph("Contents", S["h1"]), toc, PageBreak()]
    for name in CHAPTERS:
        story += chapter_flowables(HERE / name)
        story.append(PageBreak())
    rest = [p for p in sorted((HERE / "figures").rglob("*")) if p.suffix.lower() in (".png", ".gif")
            and p.resolve() not in _embedded]
    if rest:                                                 # every figure appears somewhere in the PDF
        h = Paragraph("Appendix. Figure gallery", S["h1"])
        h._toc_level = 1
        story += [h, Paragraph("Figures and animations from docs/book/figures/ that are not shown inside a chapter.",
                               S["body"])]
        for p in rest:
            story += picture(str(p.relative_to(HERE)).replace("\\", "/"), HERE)
    BookDoc(OUT).multiBuild(story)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB), {len(_embedded)} pictures embedded")
