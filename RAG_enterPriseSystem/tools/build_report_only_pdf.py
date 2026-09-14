from pathlib import Path
import re
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "REPORT.md"
OUT = ROOT / "output" / "pdf" / "caredesk_ai_report_only.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

NAVY = colors.HexColor("#10233f")
BLUE = colors.HexColor("#1f5f9e")
MUTED = colors.HexColor("#5f6b7a")
INK = colors.HexColor("#1c2430")
PAGE_W, PAGE_H = letter
MARGIN = 0.58 * inch

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleR", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=NAVY, spaceAfter=10))
styles.add(ParagraphStyle(name="H1R", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=NAVY, spaceBefore=8, spaceAfter=7))
styles.add(ParagraphStyle(name="H2R", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=BLUE, spaceBefore=6, spaceAfter=4))
styles.add(ParagraphStyle(name="BodyR", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.7, leading=11.2, textColor=INK, spaceAfter=5))
styles.add(ParagraphStyle(name="BulletR", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.4, leading=10.7, leftIndent=12, firstLineIndent=-8, textColor=INK, spaceAfter=3))
styles.add(ParagraphStyle(name="SmallR", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.4, leading=9.2, textColor=MUTED, spaceAfter=3))
styles.add(ParagraphStyle(name="CodeR", parent=styles["Code"], fontName="Courier", fontSize=6.8, leading=8.2, textColor=INK, backColor=colors.HexColor("#f4f6f8"), borderColor=colors.HexColor("#d7dee7"), borderWidth=0.4, borderPadding=6, spaceBefore=4, spaceAfter=7))

def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def inline(text):
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r"<font name='Courier'>\1</font>", text)
    text = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r"\1", text)
    return text

def make_table(lines):
    rows = []
    for line in lines:
        if re.match(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append([Paragraph(inline(c), styles["SmallR"]) for c in cells])
    if not rows:
        return None
    cols = max(len(r) for r in rows)
    for r in rows:
        r.extend([Paragraph("", styles["SmallR"])] * (cols - len(r)))
    t = Table(rows, colWidths=[6.25 * inch / cols] * cols, repeatRows=1)
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd4df")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            commands.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f5f8fb")))
    t.setStyle(TableStyle(commands))
    return t

def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d8dee8"))
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, PAGE_H - 0.38 * inch, PAGE_W - MARGIN, PAGE_H - 0.38 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 0.27 * inch, "CareDesk AI | Report.md")
    canvas.drawRightString(PAGE_W - MARGIN, 0.27 * inch, f"Page {doc.page}")
    canvas.restoreState()

text = SOURCE.read_text(encoding="utf-8")
lines = text.splitlines()
story = []
i = 0
in_code = False
code = []
while i < len(lines):
    line = lines[i]
    if line.startswith("```"):
        if in_code:
            story.append(Preformatted("\n".join(code), styles["CodeR"]))
            code = []
            in_code = False
        else:
            in_code = True
        i += 1
        continue
    if in_code:
        code.append(line)
        i += 1
        continue
    if not line.strip():
        i += 1
        continue
    if line.startswith("# "):
        story.append(Paragraph(inline(line[2:]), styles["TitleR"]))
    elif line.startswith("## "):
        story.append(Paragraph(inline(line[3:]), styles["H1R"]))
    elif line.startswith("### "):
        story.append(Paragraph(inline(line[4:]), styles["H2R"]))
    elif line.startswith("| "):
        block = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            block.append(lines[i])
            i += 1
        t = make_table(block)
        if t:
            story.append(t)
            story.append(Spacer(1, 5))
        continue
    elif line.startswith("- ") or line.startswith("* "):
        story.append(Paragraph("- " + inline(line[2:]), styles["BulletR"]))
    elif re.match(r"^\d+\. ", line):
        story.append(Paragraph(inline(line), styles["BulletR"]))
    elif line.startswith("> "):
        story.append(Paragraph(inline(line[2:]), styles["BodyR"]))
    else:
        para = line
        while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|[-*] |\d+\. |\||>|```)", lines[i + 1]):
            i += 1
            para += " " + lines[i].strip()
        story.append(Paragraph(inline(para), styles["BodyR"]))
    i += 1

doc = SimpleDocTemplate(str(OUT), pagesize=letter, rightMargin=MARGIN, leftMargin=MARGIN, topMargin=0.5*inch, bottomMargin=0.48*inch, title="CareDesk AI Report", author="Syed Ahmed")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
