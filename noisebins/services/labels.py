import io
from urllib.parse import urljoin

import segno
from noisebins.config import get_settings
from reportlab.lib.pagesizes import inch, letter
from reportlab.pdfgen import canvas


def build_bin_label_pdf(*, noisecode: str, title: str) -> bytes:
    settings = get_settings()
    public_url = urljoin(settings.public_base_url + "/", f"b/{noisecode}")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    qr = segno.make(public_url, error="m")
    qr_png = io.BytesIO()
    qr.save(qr_png, kind="png", scale=4)
    qr_png.seek(0)

    from reportlab.lib.utils import ImageReader

    img = ImageReader(qr_png)
    qr_size = 2 * inch
    x = (width - qr_size) / 2
    y = height / 2
    c.drawImage(img, x, y, width=qr_size, height=qr_size)

    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, y - 0.4 * inch, noisecode)
    c.setFont("Helvetica", 11)
    c.drawCentredString(width / 2, y - 0.65 * inch, title[:80])

    c.showPage()
    c.save()
    return buf.getvalue()
