"""
Server Performance Snapshot Generator
Corporate/Professional Style - Bi-weekly Report
PNG 1920x1080 Landscape
"""
import io
import os
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

BACKGROUNDS = {
    "corporate": {"name": "Corporate"},
    "dark": {"name": "Dark"},
}

# Corporate color scheme
COLORS = {
    "bg_dark": (20, 35, 55),
    "panel_left": (15, 28, 45),
    "table_header": (140, 25, 25),
    "row_light": (240, 245, 250),
    "row_dark": (225, 232, 240),
    "border": (180, 185, 195),
    "text_dark": (30, 35, 45),
    "text_white": (255, 255, 255),
    "text_muted": (150, 160, 175),
}

# Performance tier colors per spec
PERF_COLORS = {
    "exceeding": (0, 120, 215),      # Blue - >=100%
    "meeting": (34, 139, 34),         # Green - 80-99%
    "progress": (218, 165, 32),       # Yellow - 70-79.99%
    "improvement": (200, 40, 40),     # Red - <70%
}


def get_font(size: int, bold: bool = False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except:
            pass
    return ImageFont.load_default()


def get_perf_color(val: float) -> Tuple[int, int, int]:
    """Get performance color based on benchmark percentage."""
    if val >= 100:
        return PERF_COLORS["exceeding"]
    elif val >= 80:
        return PERF_COLORS["meeting"]
    elif val >= 70:
        return PERF_COLORS["progress"]
    return PERF_COLORS["improvement"]


def get_bonus_color(val: float) -> Tuple[int, int, int]:
    """Get bonus column color."""
    if val > 2:
        return PERF_COLORS["meeting"]  # Green - strong positive
    elif val > 0:
        return PERF_COLORS["progress"]  # Yellow - small bonus
    elif val < 0:
        return PERF_COLORS["improvement"]  # Red - penalty
    return PERF_COLORS["progress"]  # Yellow - neutral/zero


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "corporate",
    title: str = None
) -> bytes:
    """
    Generate Server Performance Snapshot.
    Corporate/professional style per specification.
    """
    img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), COLORS["bg_dark"])
    draw = ImageDraw.Draw(img)
    
    # Sort by hierarchy then total score descending
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_emps = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    num_emps = len(sorted_emps)
    
    # ===== LEFT PANEL =====
    left_panel_width = 380
    draw.rectangle([0, 0, left_panel_width, SLIDE_HEIGHT], fill=COLORS["panel_left"])
    
    # Logo
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((180, 180), Image.Resampling.LANCZOS)
            img.paste(logo, (100, 25), logo)
        except:
            pass
    
    # Title
    title_font = get_font(28, bold=True)
    title_small = get_font(24, bold=True)
    
    draw.text((left_panel_width // 2, 220), "SERVER", font=title_font, 
              fill=COLORS["text_white"], anchor="mm")
    draw.text((left_panel_width // 2, 255), "PERFORMANCE", font=title_font, 
              fill=COLORS["text_white"], anchor="mm")
    draw.text((left_panel_width // 2, 290), "SNAPSHOT", font=title_font, 
              fill=COLORS["text_white"], anchor="mm")
    
    # Date
    date_font = get_font(20, bold=True)
    draw.text((left_panel_width // 2, 340), snapshot_date, font=date_font,
              fill=(100, 180, 255), anchor="mm")
    
    # Legend
    legend_y = 420
    legend_font = get_font(14, bold=True)
    legend_desc = get_font(12)
    
    legend_items = [
        (PERF_COLORS["exceeding"], "EXCEEDING ALL", "EXPECTATIONS"),
        (PERF_COLORS["meeting"], "MEETING", "EXPECTATIONS"),
        (PERF_COLORS["progress"], "WORK IN", "PROGRESS"),
        (PERF_COLORS["improvement"], "NEEDS IMMEDIATE", "IMPROVEMENT"),
    ]
    
    for i, (color, line1, line2) in enumerate(legend_items):
        y = legend_y + i * 70
        # Color square
        draw.rectangle([30, y, 60, y + 30], fill=color)
        # Label text
        draw.text((75, y + 2), line1, font=legend_font, fill=COLORS["text_white"])
        draw.text((75, y + 20), line2, font=legend_font, fill=COLORS["text_white"])
    
    # Footer note
    footer_font = get_font(11)
    footer_y = SLIDE_HEIGHT - 100
    draw.text((20, footer_y), "Don't wait to impact this number.", 
              font=footer_font, fill=COLORS["text_muted"])
    draw.text((20, footer_y + 18), "If you have questions, please see",
              font=footer_font, fill=COLORS["text_muted"])
    draw.text((20, footer_y + 36), "a member of management.",
              font=footer_font, fill=COLORS["text_muted"])
    
    # Employee count
    draw.text((20, SLIDE_HEIGHT - 30), f"{num_emps} employees",
              font=get_font(12), fill=COLORS["text_muted"])
    
    # ===== RIGHT PANEL - PERFORMANCE TABLE =====
    table_left = left_panel_width + 20
    table_right = SLIDE_WIDTH - 20
    table_top = 30
    table_width = table_right - table_left
    
    # Header height
    header_h = 50
    
    # Calculate row height to fit all employees
    avail_h = SLIDE_HEIGHT - table_top - 50
    row_h = (avail_h - header_h) // max(num_emps, 1)
    row_h = max(28, min(40, row_h))
    
    # Font sizes
    if row_h >= 36:
        name_sz, val_sz = 16, 15
    elif row_h >= 32:
        name_sz, val_sz = 14, 13
    else:
        name_sz, val_sz = 12, 11
    
    # Columns per spec (exact order)
    columns = [
        {"name": "Rank", "pct": 6},
        {"name": "Employee Name", "pct": 16},
        {"name": "PPA", "pct": 10, "key": "score_ppa"},
        {"name": "LBW", "pct": 10, "key": "score_lbw"},
        {"name": "Glass", "pct": 10, "key": "score_glass"},
        {"name": "LSC", "pct": 10, "key": "score_lsc"},
        {"name": "Review Bonus", "pct": 12, "key": "review_tracker_bonus", "is_bonus": True},
        {"name": "Metric Bonus", "pct": 12, "key": "total_metric_bonus", "is_bonus": True},
        {"name": "Total Score", "pct": 14, "key": "total_score"},
    ]
    
    col_widths = [int(c["pct"] / 100 * table_width) for c in columns]
    col_widths[-1] += table_width - sum(col_widths)
    
    col_x = []
    x = table_left
    for w in col_widths:
        col_x.append(x)
        x += w
    
    # Draw header row
    draw.rectangle([table_left, table_top, table_right, table_top + header_h],
                   fill=COLORS["table_header"])
    
    header_font = get_font(14, bold=True)
    for i, col in enumerate(columns):
        cx = col_x[i] + col_widths[i] // 2
        draw.text((cx, table_top + header_h // 2), col["name"],
                  font=header_font, fill=COLORS["text_white"], anchor="mm")
    
    # Draw gridlines for header
    for i in range(len(columns) + 1):
        x_pos = col_x[i] if i < len(col_x) else table_right
        draw.line([(x_pos, table_top), (x_pos, table_top + header_h)], 
                  fill=(100, 30, 30), width=1)
    
    # Data rows
    data_y = table_top + header_h
    name_font = get_font(name_sz, bold=True)
    val_font = get_font(val_sz, bold=True)
    rank_font = get_font(val_sz, bold=True)
    
    tier_counts = {}
    
    for idx, emp in enumerate(sorted_emps):
        y = data_y + idx * row_h
        
        if y + row_h > SLIDE_HEIGHT - 30:
            break
        
        tier = emp.get("tier_label", "C-Server")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        # Row background - alternating
        row_bg = COLORS["row_light"] if idx % 2 == 0 else COLORS["row_dark"]
        draw.rectangle([table_left, y, table_right, y + row_h], fill=row_bg)
        
        # Gridlines
        draw.line([(table_left, y + row_h), (table_right, y + row_h)], 
                  fill=COLORS["border"], width=1)
        
        row_cy = y + row_h // 2
        
        # Column 1: Rank
        prefix = {"Trainer": "T", "Bartender": "BAR", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "?")
        rank = f"{prefix}{tier_counts[tier]}"
        draw.text((col_x[0] + col_widths[0] // 2, row_cy), rank,
                  font=rank_font, fill=COLORS["text_dark"], anchor="mm")
        
        # Column 2: Employee Name
        name = emp.get("name", "Unknown")
        max_ch = int(col_widths[1] / (name_sz * 0.55))
        if len(name) > max_ch:
            name = name[:max_ch - 1] + "…"
        draw.text((col_x[1] + 8, row_cy), name,
                  font=name_font, fill=COLORS["text_dark"], anchor="lm")
        
        # Metric columns (3-9)
        for i, col in enumerate(columns[2:], start=2):
            key = col.get("key")
            if not key:
                continue
            
            val = emp.get(key, 0) or 0
            is_bonus = col.get("is_bonus", False)
            
            cx = col_x[i] + 3
            cw = col_widths[i] - 6
            ch = row_h - 6
            cy_cell = y + 3
            
            # Determine color
            if is_bonus:
                color = get_bonus_color(val)
                txt = f"{val:.1f}" if val != 0 else "0"
            elif key == "total_score":
                # Total score reflects overall tier
                color = get_perf_color(val)
                txt = f"{val:.1f}"
            else:
                color = get_perf_color(val)
                txt = f"{val:.0f}%"
            
            # Draw colored cell
            draw.rectangle([cx, cy_cell, cx + cw, cy_cell + ch], fill=color)
            
            # Draw text
            draw.text((cx + cw // 2, row_cy), txt,
                      font=val_font, fill=COLORS["text_white"], anchor="mm")
        
        # Vertical gridlines
        for i in range(len(columns) + 1):
            x_pos = col_x[i] if i < len(col_x) else table_right
            draw.line([(x_pos, y), (x_pos, y + row_h)], fill=COLORS["border"], width=1)
    
    # Final border around table
    final_y = data_y + min(num_emps, int((SLIDE_HEIGHT - 60 - data_y) / row_h)) * row_h
    draw.rectangle([table_left, table_top, table_right, final_y], outline=COLORS["border"], width=2)
    
    # Save
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


def get_available_backgrounds():
    return [{"key": k, "name": v["name"]} for k, v in BACKGROUNDS.items()]
