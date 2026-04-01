"""
Server Performance Snapshot - EXACT REPLICATION
Matching the Q1 Final Performance Slide reference image precisely
"""
import io
import os
import requests
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from datetime import datetime

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

# Background options
BACKGROUNDS = {
    "dark": {
        "name": "Dark Navy",
        "type": "solid",
        "color": (15, 23, 42),
        "preview": None
    },
}

# Exact colors from reference
COLORS = {
    "bg_navy": (15, 23, 42),           # Dark navy background
    "header_blue": (30, 58, 95),       # Table header dark blue
    "white": (255, 255, 255),
    "row_white": (255, 255, 255),
    "row_gray": (240, 242, 245),
    
    # Performance colors - EXACT from reference
    "blue": (12, 118, 158),            # #0c769e - Exceeding (>=100%)
    "green": (51, 204, 51),            # #33cc33 - Meeting (80-99%)
    "yellow": (255, 255, 0),           # #ffff00 - Work in Progress (70-79%)
    "red": (255, 0, 0),                # #ff0000 - Needs Improvement (<70%)
    
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
        if weight in ["bold", "semibold", "aptos"]:
            fallback = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        else:
            fallback = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        try:
            return ImageFont.truetype(fallback, size)
        except:
            return ImageFont.load_default()


def get_metric_color(value: float) -> Tuple[int, int, int]:
    """Get cell color based on percentage value."""
    if value >= 100:
        return COLORS["blue"]
    elif value >= 80:
        return COLORS["green"]
    elif value >= 70:
        return COLORS["yellow"]
    return COLORS["red"]


def get_cv_color(value: float) -> Tuple[int, int, int]:
    """Get CV score color. Higher is better."""
    if value >= 15:
        return COLORS["blue"]
    elif value >= 10:
        return COLORS["green"]
    elif value >= 5:
        return COLORS["yellow"]
    return COLORS["red"]


def get_rt_color(value: float) -> Tuple[int, int, int]:
    """Get RT bonus color. Higher is better."""
    if value >= 10:
        return COLORS["blue"]
    elif value >= 5:
        return COLORS["green"]
    elif value >= 1:
        return COLORS["yellow"]
    return COLORS["red"]


def get_bonus_color(value: float) -> Tuple[int, int, int]:
    """Get metric bonus color."""
    if value >= 8:
        return COLORS["blue"]
    elif value >= 4:
        return COLORS["green"]
    elif value >= 1:
        return COLORS["yellow"]
    return COLORS["red"]


def get_score_color(value: float, a_min: float = 85, b_min: float = 70) -> Tuple[int, int, int]:
    """Get total score color based on tier thresholds."""
    if value >= a_min:
        return COLORS["green"]   # A-Server: Green
    elif value >= b_min:
        return COLORS["yellow"]  # B-Server: Yellow
    return COLORS["red"]         # C-Server: Red


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "dark",
    title: str = None,
    quarter: str = "Q1",
    a_min: float = 85,
    b_min: float = 70
) -> bytes:
    """Generate snapshot matching Q1 Final reference image exactly."""
    
    # Create base image with dark navy background
    img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), COLORS["bg_navy"])
    draw = ImageDraw.Draw(img)
    
    # Sort employees by tier, then by score within tier
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_emps = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score") or 0)
    ))
    num_emps = len(sorted_emps)
    
    # ===== LEFT PANEL =====
    left_width = 480
    
    # Logo
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
    draw.text((center_x, title_y), f"{quarter} SERVER", font=get_font(36, "semibold"),
              fill=COLORS["white"], anchor="mm")
    
    # "PERFORMANCE" - red, large
    draw.text((center_x, title_y + 50), "PERFORMANCE", font=get_font(42, "semibold"),
              fill=COLORS["title_red"], anchor="mm")
    
    # "SNAPSHOT" - white
    draw.text((center_x, title_y + 100), "SNAPSHOT", font=get_font(36, "semibold"),
              fill=COLORS["white"], anchor="mm")
    
    # Date - red
    draw.text((center_x, title_y + 145), snapshot_date, font=get_font(24, "medium"),
              fill=COLORS["title_red"], anchor="mm")
    
    # Legend
    legend_y = title_y + 200
    legend_items = [
        (COLORS["blue"], "EXCEEDING ALL", "EXPECTATIONS"),
        (COLORS["green"], "MEETING", "EXPECTATIONS"),
        (COLORS["yellow"], "WORK IN", "PROGRESS"),
        (COLORS["red"], "NEEDS IMMEDIATE", "IMPROVEMENT"),
    ]
    
    for i, (color, line1, line2) in enumerate(legend_items):
        y = legend_y + i * 70
        square_size = 50
        legend_start_x = 50
        
        draw.rectangle([legend_start_x, y, legend_start_x + square_size, y + square_size], fill=color)
        draw.text((legend_start_x + square_size + 12, y + 8), line1, 
                  font=get_font(28, "semibold"), fill=color, anchor="lm")
        draw.text((legend_start_x + square_size + 12, y + 36), line2, 
                  font=get_font(28, "semibold"), fill=color, anchor="lm")
    
    # Footer text
    footer_y = SLIDE_HEIGHT - 130
    draw.text((center_x, footer_y), "DON'T WAIT TO IMPACT", 
              font=get_font(24, "semibold"), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 30), "THIS NUMBER.",
              font=get_font(24, "semibold"), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 65), "IF YOU HAVE QUESTIONS",
              font=get_font(24, "semibold"), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 95), "PLEASE SEE MANAGEMENT.",
              font=get_font(24, "semibold"), fill=COLORS["white"], anchor="mm")
    
    # ===== RIGHT PANEL (Table) =====
    table_left = left_width + 20
    table_right = SLIDE_WIDTH - 20
    table_top = 30
    table_width = table_right - table_left
    
    # Row sizing
    header_h = 45
    available_height = SLIDE_HEIGHT - table_top - 20 - header_h
    row_h = available_height // max(num_emps, 1)
    row_h = max(28, min(42, row_h))
    
    # Columns - EXACT match to reference: Rank, Name, Trend, PPA, LBW, GLASS, LSC, CV, RT, Bonus, Score
    columns = [
        {"name": "Rank", "width": 55},
        {"name": "Name", "width": 140},
        {"name": "Trend", "width": 50},
        {"name": "PPA", "width": 80},
        {"name": "LBW", "width": 80},
        {"name": "GLASS", "width": 80},
        {"name": "LSC", "width": 80},
        {"name": "CV", "width": 75},
        {"name": "RT", "width": 75},
        {"name": "Bonus", "width": 75},
        {"name": "Score", "width": 90},
    ]
    
    # Scale columns to fit
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
    
    # Header border
    draw.line([(table_left, table_top), (table_right, table_top)], fill=(0, 0, 0), width=1)
    draw.line([(table_left, table_top + header_h), (table_right, table_top + header_h)], fill=(0, 0, 0), width=1)
    
    # Header text
    header_font = get_font(16, "semibold")
    for i, col in enumerate(columns):
        cx = col_x[i] + col["width"] // 2
        draw.text((cx, table_top + header_h // 2), col["name"],
                  font=header_font, fill=COLORS["white"], anchor="mm")
    
    # Data rows
    data_y = table_top + header_h
    tier_counts = {}
    row_idx = 0
    
    for emp in sorted_emps:
        tier = emp.get("tier_label", "C-Server")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        y = data_y + row_idx * row_h
        if y + row_h > SLIDE_HEIGHT - 20:
            break
        
        # Alternating row colors (white / light gray)
        row_bg = COLORS["row_white"] if row_idx % 2 == 0 else COLORS["row_gray"]
        draw.rectangle([table_left, y, table_right, y + row_h], fill=row_bg)
        
        # Grid lines
        draw.line([(table_left, y), (table_right, y)], fill=(0, 0, 0), width=1)
        draw.line([(table_left, y + row_h), (table_right, y + row_h)], fill=(0, 0, 0), width=1)
        
        row_cy = y + row_h // 2
        
        # Rank label (T1, T2, BAR1, A1, B1, C1, etc.)
        if tier == "Bartender":
            rank_text = f"BAR{tier_counts[tier]}"
        else:
            prefix = {"Trainer": "T", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "")
            rank_text = f"{prefix}{tier_counts[tier]}"
        
        draw.text((col_x[0] + columns[0]["width"] // 2, row_cy), rank_text,
                  font=get_font(16, "aptos"), fill=(0, 0, 0), anchor="mm")
        
        # Name - first name only
        full_name = emp.get("name") or emp.get("display_name") or "Unknown"
        name = full_name.split()[0] if full_name else "Unknown"
        draw.text((col_x[1] + 10, row_cy), name,
                  font=get_font(16, "aptos"), fill=(0, 0, 0), anchor="lm")
        
        # Trend - horizontal dash (=)
        trend_cx = col_x[2] + columns[2]["width"] // 2
        dash_width = 16
        dash_height = 4
        draw.rectangle(
            [trend_cx - dash_width//2, row_cy - dash_height//2, 
             trend_cx + dash_width//2, row_cy + dash_height//2],
            fill=(128, 128, 128)
        )
        
        # Get metric values - use pre-calculated from snapshot
        score_ppa = emp.get("score_ppa", 0) or 0
        score_lbw = emp.get("score_lbw", 0) or 0
        score_glass = emp.get("score_glass", 0) or 0
        score_lsc = emp.get("score_lsc", 0) or 0
        cv_score = emp.get("cv_score", 0) or 0
        rt_bonus = emp.get("rt_bonus", 0) or min((emp.get("rt_mentions", 0) or 0) * 0.5, 15)
        
        # Use pre-calculated metric bonus from snapshot
        metric_bonus = emp.get("total_metric_bonus", 0) or 0
        total_score = emp.get("total_score", 0) or 0
        
        # Draw metric cells with colors
        cell_pad = 4
        
        # PPA (column 3)
        col_idx = 3
        color = get_metric_color(score_ppa)
        text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
        cx = col_x[col_idx] + cell_pad
        cw = columns[col_idx]["width"] - cell_pad * 2
        ch = row_h - 8
        cy_cell = y + 4
        draw.rectangle([cx, cy_cell, cx + cw, cy_cell + ch], fill=color)
        draw.text((cx + cw // 2, row_cy), f"{score_ppa:.0f}%",
                  font=get_font(14, "aptos"), fill=text_color, anchor="mm")
        
        # LBW (column 4)
        col_idx = 4
        color = get_metric_color(score_lbw)
        text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
        cx = col_x[col_idx] + cell_pad
        cw = columns[col_idx]["width"] - cell_pad * 2
        draw.rectangle([cx, cy_cell, cx + cw, cy_cell + ch], fill=color)
        draw.text((cx + cw // 2, row_cy), f"{score_lbw:.0f}%",
                  font=get_font(14, "aptos"), fill=text_color, anchor="mm")
        
        # GLASS (column 5)
        col_idx = 5
        color = get_metric_color(score_glass)
        text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
        cx = col_x[col_idx] + cell_pad
        cw = columns[col_idx]["width"] - cell_pad * 2
        draw.rectangle([cx, cy_cell, cx + cw, cy_cell + ch], fill=color)
        draw.text((cx + cw // 2, row_cy), f"{score_glass:.0f}%",
                  font=get_font(14, "aptos"), fill=text_color, anchor="mm")
        
        # LSC (column 6)
        col_idx = 6
        color = get_metric_color(score_lsc)
        text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
        cx = col_x[col_idx] + cell_pad
        cw = columns[col_idx]["width"] - cell_pad * 2
        draw.rectangle([cx, cy_cell, cx + cw, cy_cell + ch], fill=color)
        draw.text((cx + cw // 2, row_cy), f"{score_lsc:.0f}%",
                  font=get_font(14, "aptos"), fill=text_color, anchor="mm")
        
        # CV (column 7)
        col_idx = 7
        color = get_cv_color(cv_score)
        text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
        cx = col_x[col_idx] + cell_pad
        cw = columns[col_idx]["width"] - cell_pad * 2
        draw.rectangle([cx, cy_cell, cx + cw, cy_cell + ch], fill=color)
        draw.text((cx + cw // 2, row_cy), f"+{cv_score:.1f}",
                  font=get_font(14, "aptos"), fill=text_color, anchor="mm")
        
        # RT (column 8)
        col_idx = 8
        color = get_rt_color(rt_bonus)
        text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
        cx = col_x[col_idx] + cell_pad
        cw = columns[col_idx]["width"] - cell_pad * 2
        draw.rectangle([cx, cy_cell, cx + cw, cy_cell + ch], fill=color)
        draw.text((cx + cw // 2, row_cy), f"+{rt_bonus:.1f}",
                  font=get_font(14, "aptos"), fill=text_color, anchor="mm")
        
        # Bonus (column 9)
        col_idx = 9
        color = get_bonus_color(metric_bonus)
        text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
        cx = col_x[col_idx] + cell_pad
        cw = columns[col_idx]["width"] - cell_pad * 2
        draw.rectangle([cx, cy_cell, cx + cw, cy_cell + ch], fill=color)
        draw.text((cx + cw // 2, row_cy), f"+{metric_bonus:.1f}",
                  font=get_font(14, "aptos"), fill=text_color, anchor="mm")
        
        # Score (column 10) - color based on tier thresholds
        col_idx = 10
        color = get_score_color(total_score, a_min, b_min)
        text_color = (0, 0, 0) if color == COLORS["yellow"] else COLORS["white"]
        cx = col_x[col_idx] + cell_pad
        cw = columns[col_idx]["width"] - cell_pad * 2
        draw.rectangle([cx, cy_cell, cx + cw, cy_cell + ch], fill=color)
        draw.text((cx + cw // 2, row_cy), f"{total_score:.1f}",
                  font=get_font(14, "aptos"), fill=text_color, anchor="mm")
        
        row_idx += 1
    
    # Outer border
    final_y = data_y + row_idx * row_h
    draw.rectangle([table_left, table_top, table_right, final_y], outline=(0, 0, 0), width=1)
    
    # Vertical column lines
    for i in range(len(columns)):
        draw.line([(col_x[i], table_top), (col_x[i], final_y)], fill=(0, 0, 0), width=1)
    draw.line([(table_right, table_top), (table_right, final_y)], fill=(0, 0, 0), width=1)
    
    # Save
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


def get_available_backgrounds():
    return [{"key": k, "name": v["name"], "preview": v.get("preview")} for k, v in BACKGROUNDS.items()]
