"""
Server Performance Snapshot - Matching 1.15.26 snap.png style exactly
Dark textured background, oversized logo, bold black text on colored cells
"""
import io
import os
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import random
import math

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

BACKGROUNDS = {"fire": {"name": "Fire Texture"}, "dark": {"name": "Dark"}}

# Vibrant performance colors matching reference
PERF_COLORS = {
    "exceeding": (65, 145, 255),      # Bright Blue
    "meeting": (50, 205, 50),          # Lime Green
    "progress": (255, 215, 0),         # Gold/Yellow
    "improvement": (255, 70, 70),      # Bright Red
}


def get_font(size: int, bold: bool = False):
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except:
            pass
    return ImageFont.load_default()


def get_perf_color(val: float) -> Tuple[int, int, int]:
    if val >= 100:
        return PERF_COLORS["exceeding"]
    elif val >= 80:
        return PERF_COLORS["meeting"]
    elif val >= 70:
        return PERF_COLORS["progress"]
    return PERF_COLORS["improvement"]


def create_fire_texture_background(w: int, h: int) -> Image.Image:
    """Create dark textured background like reference - red/orange/black fire texture."""
    img = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(img)
    
    # Base dark gradient
    for y in range(h):
        for x in range(w):
            # Create organic fire-like texture
            noise1 = math.sin(x * 0.02 + y * 0.01) * 0.5 + 0.5
            noise2 = math.sin(x * 0.015 - y * 0.02) * 0.5 + 0.5
            noise3 = math.sin((x + y) * 0.01) * 0.5 + 0.5
            
            combined = (noise1 + noise2 + noise3) / 3
            
            # Dark red/orange/black palette
            r = int(30 + combined * 80)
            g = int(10 + combined * 30)
            b = int(5 + combined * 15)
            
            draw.point((x, y), fill=(r, g, b))
    
    # Add some brighter spots for texture
    random.seed(42)
    for _ in range(200):
        x = random.randint(0, w)
        y = random.randint(0, h)
        brightness = random.randint(60, 120)
        size = random.randint(20, 60)
        for r in range(size, 0, -5):
            alpha = int(brightness * (r / size) * 0.15)
            color = (80 + alpha, 30 + alpha // 2, 10 + alpha // 4)
            draw.ellipse([x - r, y - r, x + r, y + r], outline=color)
    
    return img


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "fire",
    title: str = None
) -> bytes:
    """Generate snapshot matching 1.15.26 snap.png style exactly."""
    
    # Create fire texture background
    img = create_fire_texture_background(SLIDE_WIDTH, SLIDE_HEIGHT)
    draw = ImageDraw.Draw(img)
    
    # Sort employees
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_emps = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    num_emps = len(sorted_emps)
    
    # ===== LEFT PANEL =====
    left_width = 320
    
    # OVERSIZED LOGO - much bigger
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((240, 240), Image.Resampling.LANCZOS)  # OVERSIZED
            logo_x = (left_width - logo.width) // 2
            img.paste(logo, (logo_x, 15), logo)
        except:
            pass
    
    draw = ImageDraw.Draw(img)
    
    # Title - LARGE FONTS matching reference
    title_y = 280
    
    # Quarter identifier
    draw.text((left_width // 2, title_y), "Q1 SERVER", font=get_font(32, True),
              fill=(255, 255, 255), anchor="mm")
    
    # "PERFORMANCE" in RED - large
    draw.text((left_width // 2, title_y + 45), "PERFORMANCE", font=get_font(34, True),
              fill=(255, 50, 50), anchor="mm")
    
    # "SNAPSHOT" in YELLOW
    draw.text((left_width // 2, title_y + 90), "SNAPSHOT", font=get_font(32, True),
              fill=(255, 220, 0), anchor="mm")
    
    # Date
    draw.text((left_width // 2, title_y + 135), snapshot_date, font=get_font(22, True),
              fill=(255, 255, 255), anchor="mm")
    
    # Legend - LARGER colored squares with BIGGER text
    legend_y = 460
    legend_items = [
        (PERF_COLORS["exceeding"], "EXCEEDING ALL", "EXPECTATIONS"),
        (PERF_COLORS["meeting"], "MEETING", "EXPECTATIONS"),
        (PERF_COLORS["progress"], "WORK IN", "PROGRESS"),
        (PERF_COLORS["improvement"], "NEEDS IMMEDIATE", "IMPROVEMENT"),
    ]
    
    for i, (color, line1, line2) in enumerate(legend_items):
        y = legend_y + i * 95
        # Larger colored square
        draw.rectangle([12, y, 58, y + 48], fill=color)
        # EVEN LARGER text in matching color - 24pt bold
        draw.text((68, y + 2), line1, font=get_font(24, True), fill=color)
        draw.text((68, y + 30), line2, font=get_font(24, True), fill=color)
    
    # Footer
    footer_y = SLIDE_HEIGHT - 100
    draw.text((left_width // 2, footer_y), "DON'T WAIT TO IMPACT THIS NUMBER.", 
              font=get_font(11, True), fill=(200, 200, 200), anchor="mm")
    draw.text((left_width // 2, footer_y + 18), "IF YOU HAVE ANY QUESTIONS PLEASE SEE",
              font=get_font(11, True), fill=(200, 200, 200), anchor="mm")
    draw.text((left_width // 2, footer_y + 36), "A MEMBER OF MANAGEMENT.",
              font=get_font(11, True), fill=(200, 200, 200), anchor="mm")
    
    # ===== TABLE - RIGHT SIDE =====
    table_left = left_width + 10
    table_right = SLIDE_WIDTH - 10
    table_top = 25
    table_width = table_right - table_left
    
    # Calculate row height for ALL employees - LARGER rows
    header_h = 55
    avail_h = SLIDE_HEIGHT - table_top - 30
    row_h = (avail_h - header_h) // max(num_emps, 1)
    row_h = max(32, min(42, row_h))  # Larger minimum
    
    # LARGER fonts
    name_sz = 16
    val_sz = 15
    
    # Columns matching reference
    columns = [
        {"name": "Rank", "pct": 5},
        {"name": "Employee Name", "pct": 13},
        {"name": "PPA", "pct": 9, "key": "score_ppa"},
        {"name": "LBW", "pct": 9, "key": "score_lbw"},
        {"name": "GLASS", "pct": 9, "key": "score_glass"},
        {"name": "LSC", "pct": 9, "key": "score_lsc"},
        {"name": "Review\nBonus", "pct": 10, "key": "review_tracker_bonus", "is_bonus": True},
        {"name": "Metric\nBonus", "pct": 10, "key": "total_metric_bonus", "is_bonus": True},
        {"name": "Total Score", "pct": 12, "key": "total_score"},
    ]
    
    col_widths = [int(c["pct"] / 100 * table_width) for c in columns]
    col_widths[-1] += table_width - sum(col_widths)
    
    col_x = []
    x = table_left
    for w in col_widths:
        col_x.append(x)
        x += w
    
    # Header row - dark blue with BLACK border
    draw.rectangle([table_left, table_top, table_right, table_top + header_h],
                   fill=(30, 60, 100))
    draw.rectangle([table_left, table_top, table_right, table_top + header_h],
                   outline=(0, 0, 0), width=2)
    
    # Header column separators - BLACK
    for i in range(len(columns)):
        draw.line([(col_x[i], table_top), (col_x[i], table_top + header_h)], fill=(0, 0, 0), width=1)
    draw.line([(table_right, table_top), (table_right, table_top + header_h)], fill=(0, 0, 0), width=1)
    
    # Header text - WHITE, LARGE
    header_font = get_font(14, True)
    for i, col in enumerate(columns):
        cx = col_x[i] + col_widths[i] // 2
        name = col["name"]
        if "\n" in name:
            lines = name.split("\n")
            draw.text((cx, table_top + 18), lines[0], font=header_font, fill=(255, 255, 255), anchor="mm")
            draw.text((cx, table_top + 38), lines[1], font=header_font, fill=(255, 255, 255), anchor="mm")
        else:
            draw.text((cx, table_top + header_h // 2), name, font=header_font, fill=(255, 255, 255), anchor="mm")
    
    # Data rows
    data_y = table_top + header_h
    name_font = get_font(name_sz, True)
    val_font = get_font(val_sz, True)
    
    tier_counts = {}
    
    for idx, emp in enumerate(sorted_emps):
        y = data_y + idx * row_h
        
        if y + row_h > SLIDE_HEIGHT - 20:
            break
        
        tier = emp.get("tier_label", "C-Server")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        # WHITE and LIGHT GRAY alternating rows
        row_bg = (255, 255, 255) if idx % 2 == 0 else (230, 235, 240)
        draw.rectangle([table_left, y, table_right, y + row_h], fill=row_bg)
        
        # Row border - BLACK
        draw.line([(table_left, y + row_h), (table_right, y + row_h)], fill=(0, 0, 0), width=1)
        
        row_cy = y + row_h // 2
        
        # Rank - plain black text
        prefix = {"Trainer": "", "Bartender": "BAR", "A-Server": "", "B-Server": "", "C-Server": ""}.get(tier, "")
        if prefix:
            rank = f"{prefix}{tier_counts[tier]}"
        else:
            rank = str(sum(tier_counts.values()))
        draw.text((col_x[0] + col_widths[0] // 2, row_cy), rank,
                  font=val_font, fill=(30, 30, 30), anchor="mm")
        
        # Name - BOLD BLACK
        name = emp.get("name", "Unknown")
        max_ch = int(col_widths[1] / (name_sz * 0.5))
        if len(name) > max_ch:
            name = name[:max_ch - 1] + "…"
        draw.text((col_x[1] + 8, row_cy), name,
                  font=name_font, fill=(20, 20, 20), anchor="lm")
        
        # Column borders - BLACK
        for i in range(len(columns)):
            draw.line([(col_x[i], y), (col_x[i], y + row_h)], fill=(0, 0, 0), width=1)
        draw.line([(table_right, y), (table_right, y + row_h)], fill=(0, 0, 0), width=1)
        
        # Score columns - COLORED CELLS with BOLD BLACK TEXT
        for i, col in enumerate(columns[2:], start=2):
            key = col.get("key")
            if not key:
                continue
            
            val = emp.get(key, 0) or 0
            is_bonus = col.get("is_bonus", False)
            
            # Cell with padding
            pad = 3
            cx = col_x[i] + pad
            cw = col_widths[i] - pad * 2
            ch = row_h - 6
            cy = y + 3
            
            # Determine color
            if is_bonus:
                if val > 2:
                    color = PERF_COLORS["meeting"]
                elif val >= 0:
                    color = PERF_COLORS["progress"]
                else:
                    color = PERF_COLORS["improvement"]
                txt = f"{val:.2f}"
            elif key == "total_score":
                color = get_perf_color(val)
                txt = f"{val:.2f}"
            else:
                color = get_perf_color(val)
                txt = f"{val:.2f}"
            
            # Draw colored cell
            draw.rectangle([cx, cy, cx + cw, cy + ch], fill=color)
            
            # BOLD BLACK TEXT on colored cell
            draw.text((cx + cw // 2, row_cy), txt,
                      font=val_font, fill=(0, 0, 0), anchor="mm")
    
    # Outer border - BLACK
    final_y = data_y + min(num_emps, int((SLIDE_HEIGHT - 30 - data_y) / row_h)) * row_h
    draw.rectangle([table_left, table_top, table_right, final_y], outline=(0, 0, 0), width=2)
    
    # Save
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


def get_available_backgrounds():
    return [{"key": k, "name": v["name"]} for k, v in BACKGROUNDS.items()]
