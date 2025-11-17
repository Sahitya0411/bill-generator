from flask import Flask, request, send_file, render_template_string
import io
import re
import csv as csv_module
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage

app = Flask(__name__)

# === Register Arial Font (same logic as bill.py) ===
try:
    arial_paths = [
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Arial.ttf",
        Path.home() / "Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]

    arial_registered = False
    for path in arial_paths:
        path = Path(path)
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("Arial", str(path)))
                arial_registered = True
                break
            except Exception:
                continue

    if not arial_registered:
        arial_font = "Helvetica"
    else:
        arial_font = "Arial"

except Exception:
    arial_font = "Helvetica"


def get_font_size_pt(area_cm2):
    if area_cm2 is None:
        return 8
    if area_cm2 <= 50:
        return 8
    if area_cm2 <= 100:
        return 9
    if area_cm2 <= 500:
        return 10
    if area_cm2 <= 2500:
        return 16
    return 24


def clean_text(text):
    text = str(text).strip()
    text = re.sub(r"[\x00-\x1F\x7F-\x9F\u2000-\u206F■□●◾◻▪▫\u25A1]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


@app.route("/", methods=["GET"])
def index():
    html = """<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>Bill Generator</title>
    <style>
        body { font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#f4f4f5; margin:0; padding:0; }
        .container { max-width: 640px; margin: 40px auto; background:#fff; padding:24px 28px 28px; border-radius:12px; box-shadow:0 10px 30px rgba(15,23,42,0.08); }
        h1 { margin-top:0; font-size:1.5rem; color:#111827; }
        p.desc { margin-top:4px; margin-bottom:20px; color:#4b5563; font-size:0.95rem; }
        label { display:block; font-weight:500; margin-bottom:6px; color:#111827; }
        input[type="file"], input[type="number"] { width:100%; padding:8px 10px; border-radius:8px; border:1px solid #d1d5db; box-sizing:border-box; font-size:0.95rem; }
        input[type="number"] { -moz-appearance:textfield; }
        input[type="number"]::-webkit-outer-spin-button,
        input[type="number"]::-webkit-inner-spin-button { -webkit-appearance:none; margin:0; }
        .field { margin-bottom:14px; }
        .hint { font-size:0.8rem; color:#6b7280; margin-top:3px; }
        .row { display:flex; gap:12px; }
        .row .field { flex:1; }
        button { margin-top:10px; width:100%; padding:10px 12px; border-radius:999px; border:none; cursor:pointer; font-weight:600; font-size:0.95rem; background:linear-gradient(135deg,#4f46e5,#6366f1); color:white; box-shadow:0 8px 20px rgba(79,70,229,0.35); }
        button:hover { filter:brightness(1.05); }
        button:active { transform:translateY(1px); box-shadow:0 4px 12px rgba(79,70,229,0.35); }
        .optional { font-weight:400; color:#6b7280; font-size:0.85rem; }
        .footer { margin-top:18px; text-align:center; color:#9ca3af; font-size:0.8rem; }
    </style>
</head>
<body>
    <div class=\"container\">
        <h1>Bill PDF Generator</h1>
        <p class=\"desc\">Upload your product CSV and optional barcode image, enter label dimensions in cm, and download the generated bill as PDF.</p>
        <form action=\"/generate\" method=\"post\" enctype=\"multipart/form-data\">
            <div class=\"field\">
                <label for=\"csv_file\">CSV file (required)</label>
                <input type=\"file\" id=\"csv_file\" name=\"csv_file\" accept=\".csv\" required />
                <div class=\"hint\">Uses the same format as your current <code>product_data.csv</code>.</div>
            </div>
            <div class=\"field\">
                <label for=\"barcode_file\">Barcode image <span class=\"optional\">(optional)</span></label>
                <input type=\"file\" id=\"barcode_file\" name=\"barcode_file\" accept=\"image/*\" />
                <div class=\"hint\">PNG/JPEG recommended. If omitted, the bill is generated without a barcode.</div>
            </div>
            <div class=\"row\">
                <div class=\"field\">
                    <label for=\"side1\">Label side 1 (cm)</label>
                    <input type=\"number\" step=\"0.1\" min=\"0.1\" id=\"side1\" name=\"side1\" required />
                </div>
                <div class=\"field\">
                    <label for=\"side2\">Label side 2 (cm)</label>
                    <input type=\"number\" step=\"0.1\" min=\"0.1\" id=\"side2\" name=\"side2\" required />
                </div>
            </div>
            <button type=\"submit\">Generate Bill PDF</button>
        </form>
        <div class=\"footer\">CSV required · Barcode optional · Output: bill.pdf</div>
    </div>
</body>
</html>"""
    return render_template_string(html)


@app.route("/generate", methods=["POST"])
def generate():
    # Get files
    csv_file = request.files.get("csv_file")
    if not csv_file or csv_file.filename == "":
        return "CSV file is required", 400

    barcode_file = request.files.get("barcode_file")

    # Get dimensions
    try:
        side1 = float(request.form.get("side1", "0"))
        side2 = float(request.form.get("side2", "0"))
        if side1 <= 0 or side2 <= 0:
            raise ValueError
    except ValueError:
        return "Invalid label dimensions. Please provide positive numbers.", 400

    sides = sorted([side1, side2])
    smallest_side = sides[0]
    second_smallest_side = sides[1]

    # Calculate font size
    pdp_area = smallest_side * second_smallest_side
    font_size_pt = get_font_size_pt(pdp_area)

    # Read CSV from uploaded file
    data = {}
    try:
        csv_bytes = csv_file.read()
        text_stream = io.StringIO(csv_bytes.decode("utf-8-sig"))
        reader = csv_module.reader(text_stream)
        for row in reader:
            if not row:
                continue
            if len(row) > 1:
                key = row[0]
                value = ",".join(row[1:])
                data[key.strip()] = value.strip()
            elif len(row) == 1:
                data[row[0].strip()] = ""
    except Exception as e:
        return f"Error reading CSV: {e}", 400

    # Prepare styles
    styles = getSampleStyleSheet()
    style = ParagraphStyle(
        "CustomText",
        parent=styles["Normal"],
        fontSize=font_size_pt,
        fontName=arial_font,
        leading=font_size_pt * 1.1,
        wordWrap="CJK",
        spaceAfter=0,
        spaceBefore=0,
    )

    table_data = []
    for col_name, val in data.items():
        col_name = clean_text(col_name)
        val = clean_text(val)
        col_para = Paragraph(col_name, style)
        val_para = Paragraph(val, style)
        table_data.append([col_para, val_para])

    # header helper
    g = {"width_cm": 0.0, "height_points": 0.0}

    def add_page_header(canvas, doc):
        canvas.saveState()
        width_cm = g["width_cm"]
        height_points = g["height_points"]
        width_in = width_cm / 2.54
        height_in = (height_points / cm) / 2.54
        dim_str = f"W: {width_in:.2f} in  |  H: {height_in:.2f} in"
        page_width, page_height = A4
        bold_font = arial_font + "-Bold" if "Arial" in arial_font else "Helvetica-Bold"
        canvas.setFont(bold_font, font_size_pt)
        canvas.setFillColor(colors.black)
        canvas.drawRightString(page_width - 1 * cm, page_height - 1 * cm, dim_str)
        canvas.restoreState()

    # Create PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0 * cm,
        leftMargin=0 * cm,
        topMargin=0 * cm,
        bottomMargin=0 * cm,
        onFirstPage=add_page_header,
    )

    story = []
    page_width_points, page_height_points = A4

    # Width logic
    a4_page_width_cm = A4[0] / cm
    if smallest_side > a4_page_width_cm:
        total_table_width_cm = 20.0
    else:
        total_table_width_cm = smallest_side - 1.0
    if total_table_width_cm <= 0:
        total_table_width_cm = 1.0

    g["width_cm"] = total_table_width_cm

    col_width_cm = total_table_width_cm / 3.0
    col_value_width_cm = total_table_width_cm * (2.0 / 3.0)

    col_width = col_width_cm * cm
    col_value_width = col_value_width_cm * cm
    total_table_width = total_table_width_cm * cm

    # Temporary table (without barcode) to get height
    temp_table = Table(table_data, colWidths=[col_width, col_value_width])
    temp_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), arial_font),
                ("FONTSIZE", (0, 0), (-1, -1), font_size_pt),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    _, main_table_height_points = temp_table.wrap(total_table_width, page_height_points)

    max_allowed_height_points = second_smallest_side * cm
    TOP_SPACER_HEIGHT = 0.2 * cm
    BOTTOM_PADDING_HEIGHT = 3 * (cm / 72.0)
    TOTAL_ROW_PADDING = TOP_SPACER_HEIGHT + BOTTOM_PADDING_HEIGHT
    MIN_BARCODE_IMAGE_HEIGHT = 0.5 * cm

    target_barcode_height = 0

    # Determine barcode height (if barcode provided later)
    if main_table_height_points >= max_allowed_height_points:
        target_barcode_height = main_table_height_points / 7.0
    else:
        barcode_height_1_7th = main_table_height_points / 7.0
        total_height_with_1_7th = (
            main_table_height_points + barcode_height_1_7th + TOTAL_ROW_PADDING
        )
        if total_height_with_1_7th <= max_allowed_height_points:
            target_barcode_height = barcode_height_1_7th
        else:
            remaining_space_for_image = (
                max_allowed_height_points
                - main_table_height_points
                - TOTAL_ROW_PADDING
            )
            if remaining_space_for_image < MIN_BARCODE_IMAGE_HEIGHT:
                target_barcode_height = MIN_BARCODE_IMAGE_HEIGHT
            else:
                target_barcode_height = remaining_space_for_image

    # Barcode handling (optional)
    barcode_exists = False
    if barcode_file and barcode_file.filename:
        try:
            barcode_bytes = barcode_file.read()
            image_stream_for_pil = io.BytesIO(barcode_bytes)
            pil_img = PILImage.open(image_stream_for_pil)
            img_width_px, img_height_px = pil_img.size
            if img_height_px > 0:
                aspect_ratio = img_width_px / img_height_px
                final_barcode_height = target_barcode_height
                final_barcode_width = aspect_ratio * final_barcode_height
                max_width = total_table_width
                if final_barcode_width > max_width:
                    final_barcode_width = max_width * 0.98
                    final_barcode_height = final_barcode_width / aspect_ratio

                image_stream_for_rl = io.BytesIO(barcode_bytes)
                img = Image(image_stream_for_rl, width=final_barcode_width, height=final_barcode_height)
                table_data.append([img, ""])  # new row for barcode
                barcode_exists = True
        except Exception:
            barcode_exists = False

    # Base style commands
    style_commands = [
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), arial_font),
        ("FONTSIZE", (0, 0), (-1, -1), font_size_pt),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    grid_end_row = -1
    if barcode_exists:
        grid_end_row = -2
        style_commands.extend(
            [
                ("SPAN", (0, -1), (1, -1)),
                ("BOX", (0, -1), (1, -1), 1, colors.black),
                ("ALIGN", (0, -1), (1, -1), "CENTER"),
                ("VALIGN", (0, -1), (1, -1), "MIDDLE"),
                ("TOPPADDING", (0, -1), (1, -1), TOP_SPACER_HEIGHT),
                ("BOTTOMPADDING", (0, -1), (1, -1), 3),
            ]
        )

    style_commands.append(("GRID", (0, 0), (-1, grid_end_row), 1, colors.black))

    table = Table(table_data, colWidths=[col_width, col_value_width])
    table.setStyle(TableStyle(style_commands))

    _, main_table_height_points = table.wrap(total_table_width, page_height_points * 10)
    g["height_points"] = main_table_height_points

    story.append(table)

    doc.build(story)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="bill.pdf",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
