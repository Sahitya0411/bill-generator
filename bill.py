import re
import csv
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Image, Paragraph
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage

# === Register Arial Font ===
try:
    arial_paths = [
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Arial.ttf",
        Path.home() / "Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Linux fallback
        "C:\\Windows\\Fonts\\arial.ttf",  # Windows
    ]
    
    arial_registered = False
    for path in arial_paths:
        path = Path(path)
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("Arial", str(path)))
                arial_registered = True
                print(f"✓ Arial font registered from: {path}")
                break
            except Exception as font_err:
                print(f"  Could not register from {path}: {font_err}")
                continue
    
    if not arial_registered:
        print("⚠ Arial font not found on system")
        print("  Falling back to Helvetica")
        arial_font = "Helvetica"
    else:
        arial_font = "Arial"
        
except Exception as e:
    print(f"⚠ Error during font registration: {e}")
    print("  Falling back to Helvetica")
    arial_font = "Helvetica"

# === Input files ===
csv_path = Path("product_data.csv")
full_barcode_image_path = Path("barcode.png")

# === 1. Get PDP Dimensions from User ===
smallest_side = None
second_smallest_side = None

while True:
    try:
        side1_str = input("Enter the 1st dimension of the label (PDP) in cm: ")
        side1 = float(side1_str)
        
        side2_str = input("Enter the 2nd dimension of the label (PDP) in cm: ")
        side2 = float(side2_str)
        
        if side1 <= 0 or side2 <= 0:
            print("  Error: Dimensions must be positive numbers.")
            continue
            
        sides = sorted([side1, side2])
        smallest_side = sides[0]
        second_smallest_side = sides[1] # This is the max height
        break
    except ValueError:
        print("  Error: Please enter valid numbers (e.g., 10.5, 15)")

# === 2. Calculate PDP Area and Font Size ===
pdp_area = smallest_side * second_smallest_side

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

font_size_pt = get_font_size_pt(pdp_area)

# === 3. Read CSV ===
data = {}
try:
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            if len(row) > 1:
                key = row[0]
                value = ','.join(row[1:])
                data[key.strip()] = value.strip()
            elif len(row) == 1:
                data[row[0].strip()] = ""
                
except FileNotFoundError:
    print(f"Error: CSV file not found at {csv_path}")
    data = {}
except Exception as e:
    print(f"Error reading CSV: {e}")
    data = {}

# === 4. Clean data and setup styles ===
def clean_text(text):
    text = str(text).strip()
    text = re.sub(r'[\x00-\x1F\x7F-\x9F\u2000-\u206F■□●◾◻▪▫\u25A1]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text

styles = getSampleStyleSheet()
style = ParagraphStyle(
    'CustomText',
    parent=styles['Normal'],
    fontSize=font_size_pt,
    fontName=arial_font,
    leading=font_size_pt * 1.1,
    wordWrap='CJK',
    spaceAfter=0,
    spaceBefore=0
)

# === 5. Build Table Data ===
table_data = []
for col_name, val in data.items():
    col_name = clean_text(col_name)
    val = clean_text(val)
    col_para = Paragraph(col_name, style)
    val_para = Paragraph(val, style)
    table_data.append([col_para, val_para])

# --- Global dictionary for header ---
g = {"width_cm": 0.0, "height_points": 0.0}

# === 6. Header Function (Final width/height display) ===
def add_page_header(canvas, doc):
    """
    Adds the FINAL GENERATED table dimensions to the top-right corner
    in bold, using the same font and font size as the table text.
    """
    canvas.saveState()
    
    width_cm = g["width_cm"]
    height_points = g["height_points"]
    
    width_in = width_cm / 2.54
    height_in = (height_points / cm) / 2.54  # points → cm → inches
    
    dim_str = f"W: {width_in:.2f} in  |  H: {height_in:.2f} in"
    
    page_width, page_height = A4
    
    bold_font = arial_font + "-Bold" if "Arial" in arial_font else "Helvetica-Bold"
    canvas.setFont(bold_font, font_size_pt)
    canvas.setFillColor(colors.black)
    
    canvas.drawRightString(
        page_width - 1 * cm,
        page_height - 1 * cm,
        dim_str
    )
    
    canvas.restoreState()

# === 7. Create PDF Document ===
out_path = Path("bill.pdf")
doc = SimpleDocTemplate(
    str(out_path),
    pagesize=A4,
    rightMargin=0*cm,
    leftMargin=0*cm,
    topMargin=0*cm,
    bottomMargin=0*cm,
    onFirstPage=add_page_header
)

story = []
page_width_points, page_height_points = A4
total_generated_height_points = 0

# === 8. Main Info Table (and Barcode) ===
if smallest_side is None:
    print("Error: Smallest side not set. Defaulting to 10cm.")
    smallest_side = 10.0

# --- START: UPDATED WIDTH LOGIC ---
a4_page_width_cm = A4[0] / cm  # A4 width is 21.0 cm

if smallest_side > a4_page_width_cm:
    # If smallest side is > 21cm, clamp width to 20cm
    total_table_width_cm = 20.0
    print(f"Info: Smallest side ({smallest_side}cm) > A4 width ({a4_page_width_cm}cm). Clamping table width to 20cm.")
else:
    # Otherwise, use smallest side minus 1cm
    total_table_width_cm = smallest_side - 1.0

# Safety check: Ensure width is not zero or negative
if total_table_width_cm <= 0:
    print(f"Warning: Calculated table width ({total_table_width_cm}cm) is too small. Setting to 1cm.")
    total_table_width_cm = 1.0
# --- END: UPDATED WIDTH LOGIC ---

g["width_cm"] = total_table_width_cm

col_width_cm = total_table_width_cm / 3.0
col_value_width_cm = total_table_width_cm * (2.0 / 3.0)

col_width = col_width_cm * cm
col_value_width = col_value_width_cm * cm
total_table_width = total_table_width_cm * cm

# --- START: NEW BARCODE HEIGHT LOGIC (RESPECTING LABEL SIZE) ---

# 1. Create a TEMPORARY table *without* barcode to get its height
temp_table = Table(table_data, colWidths=[col_width, col_value_width])
temp_table.setStyle(TableStyle([
    ('FONTNAME', (0, 0), (-1, -1), arial_font),
    ('FONTSIZE', (0, 0), (-1, -1), font_size_pt),
    ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ('TOPPADDING', (0, 0), (-1, -1), 3),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
]))
_, main_table_height_points = temp_table.wrap(total_table_width, page_height_points)
main_table_height_cm = main_table_height_points / cm

# 2. Define height constraints
max_allowed_height_points = second_smallest_side * cm
TOP_SPACER_HEIGHT = 0.2 * cm
BOTTOM_PADDING_HEIGHT = 3 * (cm / 72.0) # 3 points
TOTAL_ROW_PADDING = TOP_SPACER_HEIGHT + BOTTOM_PADDING_HEIGHT
MIN_BARCODE_IMAGE_HEIGHT = 0.5 * cm

target_barcode_height = 0 # Initialize

# 3. Check if main table data is ALREADY too tall
if main_table_height_points >= max_allowed_height_points:
    print(f"Warning: Main table data ({main_table_height_cm:.2f}cm) is already taller than label side ({second_smallest_side:.2f}cm).")
    print("         Using default 1/7th logic for barcode.")
    target_barcode_height = main_table_height_points / 7.0
else:
    # 4. Try 1/7th logic first
    barcode_height_1_7th = main_table_height_points / 7.0
    total_height_with_1_7th = main_table_height_points + barcode_height_1_7th + TOTAL_ROW_PADDING
    
    if total_height_with_1_7th <= max_allowed_height_points:
        # It fits! Use 1/7th logic.
        print(f"Info: Using 1/7th logic. Total height ({total_height_with_1_7th/cm:.2f}cm) fits within label ({second_smallest_side:.2f}cm).")
        target_barcode_height = barcode_height_1_7th
    else:
        # It fails. Use "remaining space" logic.
        remaining_space_for_image = max_allowed_height_points - main_table_height_points - TOTAL_ROW_PADDING
        
        if remaining_space_for_image < MIN_BARCODE_IMAGE_HEIGHT:
            print(f"Warning: Remaining space ({remaining_space_for_image/cm:.2f}cm) is too small. Using min barcode height ({MIN_BARCODE_IMAGE_HEIGHT/cm:.2f}cm).")
            target_barcode_height = MIN_BARCODE_IMAGE_HEIGHT
        else:
            print(f"Info: 1/7th logic failed. Shrinking barcode to remaining space ({remaining_space_for_image/cm:.2f}cm).")
            target_barcode_height = remaining_space_for_image

# 5. Now, load barcode and add it to the *real* table_data
barcode_exists = False
if full_barcode_image_path.exists():
    try:
        pil_img = PILImage.open(full_barcode_image_path)
        img_width_px, img_height_px = pil_img.size
        if img_height_px == 0:
            raise Exception("Invalid barcode image height (0px)")
        
        aspect_ratio = img_width_px / img_height_px
        
        # Use the height we just calculated
        final_barcode_height = target_barcode_height
        final_barcode_width = aspect_ratio * final_barcode_height
        max_width = total_table_width
        
        if final_barcode_width > max_width:
            final_barcode_width = max_width * 0.98 # Use 98% to avoid padding issues
            final_barcode_height = final_barcode_width / aspect_ratio
        
        img = Image(str(full_barcode_image_path), width=final_barcode_width, height=final_barcode_height)
        
        # Add the image as a new row (to be spanned)
        table_data.append([img, '']) 
        barcode_exists = True
        
    except Exception as e:
        print(f"Warning: Could not add barcode image: {e}")
else:
    print(f"Warning: Barcode image not found at {full_barcode_image_path}")

# --- 6. Define Base Style ---
style_commands = [
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('FONTNAME', (0, 0), (-1, -1), arial_font),
    ('FONTSIZE', (0, 0), (-1, -1), font_size_pt),
    ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ('TOPPADDING', (0, 0), (-1, -1), 3),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
]

# --- 7. Add Conditional Barcode Styling ---
grid_end_row = -1 # Default: grid to bottom
if barcode_exists:
    grid_end_row = -2 # Grid stops *before* the barcode row
    style_commands.extend([
        ('SPAN', (0, -1), (1, -1)),       # Span the last row
        ('BOX', (0, -1), (1, -1), 1, colors.black), # Draw a box around the spanned row
        ('ALIGN', (0, -1), (1, -1), 'CENTER'),
        ('VALIGN', (0, -1), (1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, -1), (1, -1), TOP_SPACER_HEIGHT), # This acts as the spacer
        ('BOTTOMPADDING', (0, -1), (1, -1), 3),
    ])

# Add the main grid
style_commands.append(('GRID', (0, 0), (-1, grid_end_row), 1, colors.black))

# --- 8. Create and wrap the FINAL single table ---
table = Table(table_data, colWidths=[col_width, col_value_width])
table.setStyle(TableStyle(style_commands))

# Wrap with a large height to allow splitting across pages if necessary
# (e.g., if main data > A4 page)
main_table_width_points, main_table_height_points = table.wrap(total_table_width, page_height_points * 10)
total_generated_height_points = main_table_height_points
main_table_height_cm = main_table_height_points / cm

story.append(table)
g["height_points"] = main_table_height_points
# --- END: COMBINED TABLE LOGIC ---


# === 9. Barcode Section ===
# --- THIS SECTION IS NOW REMOVED AND COMBINED INTO SECTION 8 ---


# === 10. Build PDF ===
doc.build(story)

# === 11. Summary ===
width_in = smallest_side / 2.54
height_in = second_smallest_side / 2.54
label_dim_in_str = f"{width_in:.1f} * {height_in:.1f} in"
table_width_in = total_table_width_cm / 2.54
total_generated_height_cm = total_generated_height_points / cm
total_generated_height_in = total_generated_height_cm / 2.54

print("--- PDP Rule Calculation ---")
print(f"  PDP Area: {pdp_area:.2f} cm²")
print(f"  Label Dimensions (Input): {smallest_side:.2f} cm * {second_smallest_side:.2f} cm ({label_dim_in_str})")
print(f"  Generated Table Width: {total_table_width_cm:.2f} cm ({table_width_in:.2f} in)")
print(f"  Generated Table Height: {total_generated_height_cm:.2f} cm ({total_generated_height_in:.2f} in)")
print(f"  Font Size: {font_size_pt} pt")
print(f"  Font Used: {arial_font}")
print("--------------------------------------------------")
print(f"✅ PDF Bill generated: {out_path.resolve()}")