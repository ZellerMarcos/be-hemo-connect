import argparse
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def inline(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return escape(text.replace("**", "").replace("`", ""))


DEFAULT_FOOTER = "Hemo Connect - DevSecOps avancado - evidencias locais e GitHub Actions"
DEFAULT_TITLE = "Hemo Connect - DevSecOps avancado"


def render(source: Path, destination: Path, footer_text: str = DEFAULT_FOOTER, title: str = DEFAULT_TITLE) -> None:
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 13
    styles["BodyText"].wordWrap = "CJK"
    for name in ("Title", "Heading1", "Heading2"):
        styles[name].keepWithNext = True
    story = []
    lines = source.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        image = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", line)
        if image:
            path = (source.parent / image[2]).resolve()
            if not path.is_relative_to(source.parent.resolve()):
                raise ValueError("Report images must stay inside the documentation directory.")
            picture = Image(str(path))
            scale = min((A4[0] - 80) / picture.imageWidth, 420 / picture.imageHeight)
            picture.drawWidth = picture.imageWidth * scale
            picture.drawHeight = picture.imageHeight * scale
            story.append(KeepTogether([
                picture, Paragraph(inline(image[1]), styles["BodyText"]), Spacer(1, 10),
            ]))
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [item.strip() for item in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[-: ]+", cell) for cell in cells):
                    rows.append([Paragraph(inline(cell), styles["BodyText"]) for cell in cells])
                index += 1
            table = Table(rows, colWidths=[(A4[0] - 80) / len(rows[0])] * len(rows[0]), repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeef4")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.extend([table, Spacer(1, 10)])
            continue
        if line:
            heading = re.match(r"^(#{1,3}) (.+)$", line)
            if heading:
                style = styles["Title" if len(heading[1]) == 1 else f"Heading{len(heading[1]) - 1}"]
                story.append(Paragraph(inline(heading[2]), style))
            else:
                if not re.match(r"^(- |\d+\. )", line):
                    while index + 1 < len(lines):
                        continuation = lines[index + 1].strip()
                        if not continuation or re.match(r"^(#|\||!\[|- |\d+\. )", continuation):
                            break
                        line += " " + continuation
                        index += 1
                story.append(Paragraph(inline(line), styles["BodyText"]))
                story.append(Spacer(1, 5))
        index += 1
    destination.parent.mkdir(parents=True, exist_ok=True)

    def footer(canvas, document):
        canvas.setFont("Helvetica", 8)
        canvas.drawString(40, 24, footer_text)
        canvas.drawRightString(A4[0] - 40, 24, str(document.page))

    document = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=40, rightMargin=40,
                                topMargin=40, bottomMargin=40, title=title)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"PDF generated: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--footer", default=DEFAULT_FOOTER)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    args = parser.parse_args()
    render(args.source, args.destination, args.footer, args.title)
