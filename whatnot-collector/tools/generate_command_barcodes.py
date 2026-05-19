from pathlib import Path

from reportlab.graphics.barcode import code128
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "exports" / "barcodes"
PAGE_WIDTH, PAGE_HEIGHT = letter

CARDS = [
    {
        "title": "Release Bucket",
        "command": "RELEASE_BUCKET",
        "subtitle": "Scan this card to release the current lot and move on.",
        "accent": "#C92A2A",
    },
    {
        "title": "Undo Release",
        "command": "UNDO_RELEASE",
        "subtitle": "Scan this card to restore the last released lot.",
        "accent": "#2B8A3E",
    },
]


def draw_card(c, card):
    accent = HexColor(card["accent"])
    margin = 42

    c.setFillColor(white)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)

    c.setFillColor(accent)
    c.roundRect(margin, PAGE_HEIGHT - 115, PAGE_WIDTH - (margin * 2), 70, 18, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 28)
    c.drawString(margin + 24, PAGE_HEIGHT - 72, card["title"])

    c.setFillColor(black)
    c.setFont("Helvetica", 14)
    c.drawString(margin, PAGE_HEIGHT - 145, card["subtitle"])

    barcode_value = card["command"]
    barcode = code128.Code128(
        barcode_value,
        barHeight=100,
        barWidth=1.1,
        humanReadable=False,
    )
    barcode_x = (PAGE_WIDTH - barcode.width) / 2
    barcode_y = PAGE_HEIGHT / 2 - 40
    barcode.drawOn(c, barcode_x, barcode_y)

    c.setFont("Helvetica-Bold", 30)
    text_width = stringWidth(barcode_value, "Helvetica-Bold", 30)
    c.drawString((PAGE_WIDTH - text_width) / 2, barcode_y - 42, barcode_value)

    c.setFont("Helvetica", 12)
    helper = "Print on plain white paper or laminate as a command card."
    helper_width = stringWidth(helper, "Helvetica", 12)
    c.drawString((PAGE_WIDTH - helper_width) / 2, 74, helper)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    combined_path = OUTPUT_DIR / "command_barcodes.pdf"
    combined = canvas.Canvas(str(combined_path), pagesize=letter)
    for card in CARDS:
        draw_card(combined, card)
        combined.showPage()
    combined.save()

    for card in CARDS:
        filename = card["command"].lower() + ".pdf"
        path = OUTPUT_DIR / filename
        pdf = canvas.Canvas(str(path), pagesize=letter)
        draw_card(pdf, card)
        pdf.save()
        print(path)

    print(combined_path)


if __name__ == "__main__":
    main()
