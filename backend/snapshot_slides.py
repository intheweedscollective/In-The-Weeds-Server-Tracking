"""
Server Performance Leaderboard - Yodeck Ready
EXACT SPECIFICATION - NO DEVIATIONS
Resolution: 1920x1080, Poppins font only
"""
import io
import os
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

BACKGROUNDS = {"dark": {"name": "Dark"}}

# Font paths - Poppins ONLY
FONT_PATH_SEMIBOLD = "/app/backend/assets/fonts/Poppins-SemiBold.ttf"
FONT_PATH_MEDIUM = "/app/backend/assets/fonts/Poppins-Medium.ttf"
FONT_PATH_REGULAR = "/app/backend/assets/fonts/Poppins-Regular.ttf"

# Colors (STRICT - no gradients, no transparency)
COLORS = {
    "bg_dark": (18, 24, 38),           # Dark background
    "header_navy": (25, 35, 60),       # Dark Navy header
    "white": (255, 255, 255),
    "top_performer": (34, 197, 94),    # Green
    "above_average": (59, 130, 246),   # Blue
    "below_average": (249, 115, 22),   # Orange
    "needs_improvement": (239, 68, 68), # Red
}


def get_poppins(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    """Get Poppins font - ONLY font allowed."""
    if weight == "semibold":
        path = FONT_PATH_SEMIBOLD
    elif weight == "medium":
        path = FONT_PATH_MEDIUM
    else:
        path = FONT_PATH_REGULAR
    
    try:
        return ImageFont.truetype(path, size)
    except:
        # Fallback if Poppins not found
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)


def get_row_color(total_score: float) -> Tuple[int, int, int]:
    """Get row color based on performance tier."""
    if total_score >= 90:
        return COLORS["top_performer"]      # Green
    elif total_score >= 80:
        return COLORS["above_average"]      # Blue
    elif total_score >= 70:
        return COLORS["below_average"]      # Orange
    return COLORS["needs_improvement"]       # Red


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "dark",
    title: str = None
) -> bytes:
    """
    Generate Yodeck-ready leaderboard slide.
    EXACT SPECIFICATION - NO DEVIATIONS.
    """
    # Dark solid background
    img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), COLORS["bg_dark"])
    draw = ImageDraw.Draw(img)
    
    # Sort employees by tier then score
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_emps = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    num_emps = len(sorted_emps)
    
    # === LOGO: Top-Left, 120px width, 32px padding ===
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            # Scale to 120px width
            aspect = logo.height / logo.width
            logo = logo.resize((120, int(120 * aspect)), Image.Resampling.LANCZOS)
            img.paste(logo, (32, 32), logo)
        except:
            pass
    
    draw = ImageDraw.Draw(img)
    
    # === TITLE: Centered, 48px from top, Poppins SemiBold 52pt ===
    title_font = get_poppins(52, "semibold")
    title_text = "SERVER PERFORMANCE LEADERBOARD"
    draw.text((SLIDE_WIDTH // 2, 48), title_text, font=title_font, 
              fill=COLORS["white"], anchor="mt")
    
    # === TABLE: 70% width, aligned right ===
    table_width = int(SLIDE_WIDTH * 0.70)
    table_left = SLIDE_WIDTH - table_width - 32  # 32px right padding
    table_right = SLIDE_WIDTH - 32
    table_top = 140
    
    # Row height: 48px (LOCKED)
    row_height = 48
    header_height = 48
    bottom_margin = 48
    
    # Calculate how many rows fit
    available_height = SLIDE_HEIGHT - table_top - bottom_margin - header_height
    max_rows = available_height // row_height
    rows_to_show = min(num_emps, max_rows)
    
    # === COLUMNS (EXACT ORDER) ===
    columns = [
        {"name": "Rank", "width": 80},
        {"name": "Employee Name", "width": 220},
        {"name": "PPA", "width": 100, "key": "score_ppa"},
        {"name": "LBW", "width": 100, "key": "score_lbw"},
        {"name": "Glassware", "width": 110, "key": "score_glass"},
        {"name": "LSC", "width": 100, "key": "score_lsc"},
        {"name": "Review Bonus", "width": 130, "key": "review_tracker_bonus", "is_bonus": True},
        {"name": "Metric Bonus", "width": 130, "key": "total_metric_bonus", "is_bonus": True},
        {"name": "Total Score", "width": 130, "key": "total_score"},
    ]
    
    # Scale columns to fit table width
    total_col_width = sum(c["width"] for c in columns)
    scale = table_width / total_col_width
    for c in columns:
        c["width"] = int(c["width"] * scale)
    
    # Adjust last column for rounding
    actual_width = sum(c["width"] for c in columns)
    columns[-1]["width"] += table_width - actual_width
    
    # Calculate column positions
    col_x = []
    x = table_left
    for c in columns:
        col_x.append(x)
        x += c["width"]
    
    # === HEADER ROW: Dark Navy background, white text ===
    draw.rectangle([table_left, table_top, table_right, table_top + header_height],
                   fill=COLORS["header_navy"])
    
    # Header text: Poppins Medium 24pt, left-aligned with 16px padding
    header_font = get_poppins(24, "medium")
    cell_padding = 16
    
    for i, col in enumerate(columns):
        text_x = col_x[i] + cell_padding
        text_y = table_top + header_height // 2
        draw.text((text_x, text_y), col["name"], font=header_font,
                  fill=COLORS["white"], anchor="lm")
    
    # === DATA ROWS ===
    data_y = table_top + header_height
    
    # Fonts: Employee Names 22pt, Numeric Data 20pt
    name_font = get_poppins(22, "regular")
    data_font = get_poppins(20, "regular")
    
    tier_counts = {}
    
    for idx, emp in enumerate(sorted_emps[:rows_to_show]):
        y = data_y + idx * row_height
        
        tier = emp.get("tier_label", "C-Server")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        total_score = emp.get("total_score", 0) or 0
        
        # Row color based on performance tier
        row_color = get_row_color(total_score)
        draw.rectangle([table_left, y, table_right, y + row_height], fill=row_color)
        
        row_cy = y + row_height // 2
        
        # Column 1: Rank
        rank = idx + 1
        draw.text((col_x[0] + cell_padding, row_cy), str(rank),
                  font=data_font, fill=COLORS["white"], anchor="lm")
        
        # Column 2: Employee Name (22pt)
        name = emp.get("name", "Unknown")
        # Truncate if needed
        max_chars = (columns[1]["width"] - cell_padding * 2) // 12
        if len(name) > max_chars:
            name = name[:max_chars - 1] + "…"
        draw.text((col_x[1] + cell_padding, row_cy), name,
                  font=name_font, fill=COLORS["white"], anchor="lm")
        
        # Columns 3-9: Metric data (20pt)
        for i, col in enumerate(columns[2:], start=2):
            key = col.get("key")
            if not key:
                continue
            
            val = emp.get(key, 0) or 0
            is_bonus = col.get("is_bonus", False)
            
            if is_bonus:
                text = f"{val:.2f}"
            elif key == "total_score":
                text = f"{val:.2f}"
            else:
                text = f"{val:.1f}%"
            
            draw.text((col_x[i] + cell_padding, row_cy), text,
                      font=data_font, fill=COLORS["white"], anchor="lm")
    
    # Save
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


def get_available_backgrounds():
    return [{"key": k, "name": v["name"]} for k, v in BACKGROUNDS.items()]
