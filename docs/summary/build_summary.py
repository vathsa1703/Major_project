"""Build the short plain-English summary PDF from summary.md, with the same converter as the project book.

    python docs/summary/build_summary.py        # writes docs/summary/UAV-NOMA-Summary.pdf
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "book"))
import build_pdf as bp  # noqa: E402


class SummaryDoc(bp.BookDoc):
    @staticmethod
    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont("DV", 7.5)
        canvas.setFillColor(bp.colors.HexColor("#777777"))
        canvas.drawString(2 * bp.cm, 1.2 * bp.cm, "UAV-NOMA Disaster Network Planning Simulator: summary")
        canvas.drawRightString(bp.A4[0] - 2 * bp.cm, 1.2 * bp.cm, f"page {doc.page}")
        canvas.restoreState()


def build():
    out = HERE / "UAV-NOMA-Summary.pdf"
    SummaryDoc(out).multiBuild(bp.chapter_flowables(HERE / "summary.md"))
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
