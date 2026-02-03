"""
Server Performance Snapshot - EXACT REPLICATION
Matching the reference image precisely
"""
import io
import os
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

BACKGROUNDS = {"dark": {"name": "Dark Navy"}}

# Exact colors from reference
COLORS = {
    "bg_navy": (15, 23, 42),           # Dark navy background
    "header_blue": (30, 58, 95),       # Table header dark blue
    "white": (255, 255, 255),
    "row_white": (255, 255, 255),
    "row_gray": (240, 242, 245),
    "bar_row": (25, 40, 65),           # BAR1/BAR2 row background
    
    # Performance colors - EXACT hex values
    "blue": (12, 118, 158),            # #0c769e - Exceeding
    "green": (51, 204, 51),            # #33cc33 - Meeting
    "yellow": (255, 255, 0),           # #ffff00 - Work in Progress
    "red": (255, 0, 0),                # #ff0000 - Needs Improvement
    
    # Title colors
    "title_red": (255, 50, 50),
    "title_green": (50, 205, 50),
}

# Font paths
FONT_REGULAR = "/app/backend/assets/fonts/Poppins-Regular.ttf"
FONT_MEDIUM = "/app/backend/assets/fonts/Poppins-Medium.ttf"
FONT_SEMIBOLD = "/app/backend/assets/fonts/Poppins-SemiBold.ttf"
FONT_APTOS_NARROW_BOLD = "/app/backend/assets/fonts/Aptos-Narrow-Bold.ttf"


def get_font(size: int, weight: str = "regular"):
    if weight == "aptos":
        path = FONT_APTOS_NARROW_BOLD
    elif weight == "semibold":
        path = FONT_SEMIBOLD
    elif weight == "medium":
        path = FONT_MEDIUM
    else:
        path = FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except:
        fallback = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if weight != "regular" else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        return ImageFont.truetype(fallback, size)


def get_cell_color(value: float, is_total: bool = False) -> Tuple[int, int, int]:
    """Get cell color based on performance."""
    if value >= 100:
        return COLORS["blue"]
    elif value >= 80:
        return COLORS["green"]
    elif value >= 70:
        return COLORS["yellow"]
    return COLORS["red"]


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "dark",
    title: str = None
) -> bytes:
    """Generate snapshot matching reference image exactly."""
    
    # Dark navy background
    img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), COLORS["bg_navy"])
    draw = ImageDraw.Draw(img)
    
    # Sort employees
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_emps = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    num_emps = len(sorted_emps)
    
    # ===== LEFT PANEL (30% width) =====
    left_width = 400
    
    # Logo - large, top of left panel
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((280, 280), Image.Resampling.LANCZOS)
            logo_x = (left_width - logo.width) // 2
            img.paste(logo, (logo_x, 30), logo)
        except:
            pass
    
    draw = ImageDraw.Draw(img)
    
    # Title section
    title_y = 330
    center_x = left_width // 2
    
    # "Q1 SERVER" - white
    draw.text((center_x, title_y), "Q1 SERVER", font=get_font(36, "semibold"),
              fill=COLORS["white"], anchor="mm")
    
    # "PERFORMANCE" - red, large
    draw.text((center_x, title_y + 50), "PERFORMANCE", font=get_font(42, "semibold"),
              fill=COLORS["title_red"], anchor="mm")
    
    # "SNAPSHOT" - white
    draw.text((center_x, title_y + 100), "SNAPSHOT", font=get_font(36, "semibold"),
              fill=COLORS["white"], anchor="mm")
    
    # Date - green
    draw.text((center_x, title_y + 145), snapshot_date, font=get_font(24, "medium"),
              fill=COLORS["title_green"], anchor="mm")
    
    # Legend
    legend_y = 540
    legend_items = [
        (COLORS["blue"], "EXCEEDING ALL", "EXPECTATIONS"),
        (COLORS["green"], "MEETING", "EXPECTATIONS"),
        (COLORS["yellow"], "WORK IN", "PROGRESS"),
        (COLORS["red"], "NEEDS IMMEDIATE", "IMPROVEMENT"),
    ]
    
    for i, (color, line1, line2) in enumerate(legend_items):
        y = legend_y + i * 70
        # Colored square
        draw.rectangle([30, y, 65, y + 35], fill=color)
        # Text in matching color
        draw.text((80, y + 3), line1, font=get_font(18, "semibold"), fill=color)
        draw.text((80, y + 23), line2, font=get_font(18, "semibold"), fill=color)
    
    # Footer text
    footer_y = SLIDE_HEIGHT - 80
    draw.text((center_x, footer_y), "DON'T WAIT TO IMPACT THIS NUMBER.", 
              font=get_font(11, "medium"), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 16), "IF YOU HAVE ANY QUESTIONS PLEASE SEE",
              font=get_font(11, "medium"), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 32), "A MEMBER OF MANAGEMENT.",
              font=get_font(11, "medium"), fill=COLORS["white"], anchor="mm")
    
    # ===== RIGHT PANEL (Table) =====
    table_left = left_width + 20
    table_right = SLIDE_WIDTH - 20
    table_top = 30
    table_width = table_right - table_left
    
    # Calculate row sizing to fit ALL employees
    header_h = 45
    available_height = SLIDE_HEIGHT - table_top - 20 - header_h
    row_h = available_height // max(num_emps, 1)
    row_h = max(28, min(42, row_h))  # Between 28-42px
    
    # Columns
    columns = [
        {"name": "Rank", "width": 70},
        {"name": "Employee Name", "width": 180},
        {"name": "PPA", "width": 100, "key": "score_ppa"},
        {"name": "LBW", "width": 100, "key": "score_lbw"},
        {"name": "GLASS", "width": 100, "key": "score_glass"},
        {"name": "LSC", "width": 100, "key": "score_lsc"},
        {"name": "Review Bonus", "width": 120, "key": "review_tracker_bonus", "is_bonus": True},
        {"name": "Metric Bonus", "width": 120, "key": "total_metric_bonus", "is_bonus": True},
        {"name": "Total Score", "width": 120, "key": "total_score"},
    ]
    
    # Scale columns
    total_col_w = sum(c["width"] for c in columns)
    scale = table_width / total_col_w
    for c in columns:
        c["width"] = int(c["width"] * scale)
    columns[-1]["width"] += table_width - sum(c["width"] for c in columns)
    
    # Column positions
    col_x = []
    x = table_left
    for c in columns:
        col_x.append(x)
        x += c["width"]
    
    # Header row - dark blue
    draw.rectangle([table_left, table_top, table_right, table_top + header_h],
                   fill=COLORS["header_blue"])
    
    # Header text
    header_font = get_font(16, "semibold")
    for i, col in enumerate(columns):
        cx = col_x[i] + col["width"] // 2
        draw.text((cx, table_top + header_h // 2), col["name"],
                  font=header_font, fill=COLORS["white"], anchor="mm")
    
    # Data rows
    data_y = table_top + header_h
    current_tier = None
    tier_counts = {}
    row_idx = 0
    
    for emp in sorted_emps:
        tier = emp.get("tier_label", "C-Server")
        
        # Insert BAR separator rows for Bartenders
        if tier == "Bartender" and current_tier != "Bartender":
            # Check if we have bartenders
            pass
        
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        current_tier = tier
        
        y = data_y + row_idx * row_h
        if y + row_h > SLIDE_HEIGHT - 20:
            break
        
        # Alternating row colors (white / light gray)
        row_bg = COLORS["row_white"] if row_idx % 2 == 0 else COLORS["row_gray"]
        
        # Special row for BAR entries
        if tier == "Bartender":
            prefix = "BAR"
            rank_text = f"{prefix}{tier_counts[tier]}"
        else:
            prefix = {"Trainer": "T", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "")
            if prefix:
                rank_text = f"{prefix}{tier_counts[tier]}"
            else:
                rank_text = str(row_idx + 1)
        
        # Draw row background
        draw.rectangle([table_left, y, table_right, y + row_h], fill=row_bg)
        
        # Row border - BLACK
        draw.line([(table_left, y + row_h), (table_right, y + row_h)], fill=(0, 0, 0), width=1)
        
        row_cy = y + row_h // 2
        
        # Rank column - Aptos Narrow Bold, black text
        draw.text((col_x[0] + columns[0]["width"] // 2, row_cy), rank_text,
                  font=get_font(16, "aptos"), fill=(0, 0, 0), anchor="mm")
        
        # Employee name - Aptos Narrow Bold, black text
        name = emp.get("name", "Unknown")
        max_ch = columns[1]["width"] // 10
        if len(name) > max_ch:
            name = name[:max_ch-1] + "…"
        draw.text((col_x[1] + 10, row_cy), name,
                  font=get_font(16, "aptos"), fill=(0, 0, 0), anchor="lm")
        
        # Metric columns - colored cells
        for i, col in enumerate(columns[2:], start=2):
            key = col.get("key")
            if not key:
                continue
            
            # Calculate Review Bonus using correct formula
            if key == "review_tracker_bonus":
                review_mentions = emp.get("review_mentions", 0) or 0
                cv_promoters = emp.get("cv_promoters", 0) or 0
                cv_detractors = emp.get("cv_detractors", 0) or 0
                val = (review_mentions * 0.2) + cv_promoters - (cv_detractors * 2)
            else:
                val = emp.get(key, 0) or 0
            
            is_bonus = col.get("is_bonus", False)
            
            # Cell dimensions
            cell_pad = 4
            cx = col_x[i] + cell_pad
            cw = columns[i]["width"] - cell_pad * 2
            ch = row_h - 8
            cy = y + 4
            
            # Determine color and format
            if key == "review_tracker_bonus":
                # Review Bonus: 0=Red, 1-5=Yellow, 5-10=Green, +10=Blue
                if val >= 10:
                    color = COLORS["blue"]
                    text_color = COLORS["white"]  # White text on blue
                elif val >= 5:
                    color = COLORS["green"]
                    text_color = (0, 0, 0)  # Black text
                elif val >= 1:
                    color = COLORS["yellow"]
                    text_color = (0, 0, 0)  # Black text
                else:
                    color = COLORS["red"]
                    text_color = (0, 0, 0)  # Black text
                text = f"{val:.2f}"
            elif key == "total_metric_bonus":
                # Metric Bonus: 0=Red, +1=Green, +10=Blue
                if val >= 10:
                    color = COLORS["blue"]
                    text_color = COLORS["white"]  # White text on blue
                elif val >= 1:
                    color = COLORS["green"]
                    text_color = (0, 0, 0)  # Black text
                else:
                    color = COLORS["red"]
                    text_color = (0, 0, 0)  # Black text
                text = f"{val:.2f}"
            elif key == "total_score":
                # Total score - colored based on value
                color = get_cell_color(val)
                text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
                text = f"{val:.2f}"
            else:
                # Metric scores - colored cells
                color = get_cell_color(val)
                text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
                text = f"{val:.2f}"
            
            # Draw colored cell
            draw.rectangle([cx, cy, cx + cw, cy + ch], fill=color)
            
            # Draw text - Aptos Narrow Bold
            draw.text((cx + cw // 2, row_cy), text,
                      font=get_font(14, "aptos"), fill=text_color, anchor="mm")
        
        row_idx += 1
    
    # Outer border - BLACK
    final_y = data_y + row_idx * row_h
    draw.rectangle([table_left, table_top, table_right, final_y], outline=(0, 0, 0), width=1)
    
    # Vertical column lines - BLACK
    for i in range(len(columns)):
        draw.line([(col_x[i], table_top), (col_x[i], final_y)], fill=(0, 0, 0), width=1)
    draw.line([(table_right, table_top), (table_right, final_y)], fill=(0, 0, 0), width=1)
    
    # Save
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


def get_available_backgrounds():
    return [{"key": k, "name": v["name"]} for k, v in BACKGROUNDS.items()]
