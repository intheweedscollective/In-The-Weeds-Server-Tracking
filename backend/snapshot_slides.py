"""
Server Performance Snapshot Generator
Matches reference design exactly - Holiday themed, TV optimized
"""
import io
import os
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import math
import random

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

BACKGROUNDS = {"holiday": {"name": "Holiday"}, "standard": {"name": "Standard"}}

# Performance colors matching reference
PERF_COLORS = {
    "exceeding": (0, 100, 180),       # Blue
    "meeting": (34, 139, 34),          # Green
    "progress": (218, 165, 32),        # Yellow/Gold
    "improvement": (180, 30, 30),      # Red
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


def create_holiday_background(w: int, h: int) -> Image.Image:
    """Create festive holiday background with garlands and bokeh."""
    img = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(img)
    
    # Deep forest green base gradient
    for y in range(h):
        ratio = y / h
        r = int(15 + ratio * 10)
        g = int(45 + ratio * 25)
        b = int(25 + ratio * 15)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    
    # Bokeh lights effect
    random.seed(42)
    for _ in range(60):
        x = random.randint(0, w)
        y = random.randint(0, h)
        size = random.randint(15, 60)
        brightness = random.randint(40, 100)
        # Warm golden/white bokeh
        color = (brightness + 50, brightness + 30, brightness - 20)
        for r in range(size, 0, -2):
            alpha = int(brightness * (r / size) * 0.3)
            c = (min(255, color[0] + alpha), min(255, color[1] + alpha), min(255, color[2] + alpha // 2))
            draw.ellipse([x - r, y - r, x + r, y + r], outline=c)
    
    # Garland effect at top
    garland_color = (30, 70, 35)
    for i in range(0, w, 8):
        amplitude = 15 + random.randint(-5, 5)
        y_base = 25
        y = y_base + int(amplitude * math.sin(i * 0.05))
        draw.ellipse([i - 12, y - 12, i + 12, y + 12], fill=garland_color)
    
    # Red ornaments/berries on garland
    for i in range(50, w, 120):
        y = 25 + random.randint(-10, 10)
        draw.ellipse([i - 8, y - 8, i + 8, y + 8], fill=(180, 30, 30))
        draw.ellipse([i - 5, y - 8, i, y - 5], fill=(220, 80, 80))  # Highlight
    
    # Corner ribbons
    # Top-left bow
    draw.polygon([(0, 0), (80, 0), (0, 80)], fill=(160, 25, 25))
    draw.polygon([(0, 0), (60, 0), (0, 60)], fill=(190, 35, 35))
    
    # Bottom-right bow
    draw.polygon([(w, h), (w - 100, h), (w, h - 100)], fill=(160, 25, 25))
    draw.polygon([(w, h), (w - 70, h), (w, h - 70)], fill=(190, 35, 35))
    
    return img


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "holiday",
    title: str = None
) -> bytes:
    """Generate Server Performance Snapshot matching reference design."""
    
    # Create holiday background
    img = create_holiday_background(SLIDE_WIDTH, SLIDE_HEIGHT)
    draw = ImageDraw.Draw(img)
    
    # Sort employees
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_emps = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    num_emps = len(sorted_emps)
    
    # ===== LEFT PANEL =====
    left_width = 350
    
    # Semi-transparent overlay for left panel readability
    overlay = Image.new('RGBA', (left_width, SLIDE_HEIGHT), (0, 30, 15, 180))
    img.paste(Image.alpha_composite(
        img.crop((0, 0, left_width, SLIDE_HEIGHT)).convert('RGBA'),
        overlay
    ).convert('RGB'), (0, 0))
    draw = ImageDraw.Draw(img)
    
    # Logo
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((160, 160), Image.Resampling.LANCZOS)
            logo_x = (left_width - logo.width) // 2
            img.paste(logo, (logo_x, 30), logo)
        except:
            pass
    
    # Refresh draw after paste
    draw = ImageDraw.Draw(img)
    
    # Title - matching reference style
    title_y = 210
    
    # "SERVER" - white
    draw.text((left_width // 2, title_y), "SERVER", font=get_font(26, True), 
              fill=(255, 255, 255), anchor="mm")
    
    # "PERFORMANCE" - bright red
    draw.text((left_width // 2, title_y + 35), "PERFORMANCE", font=get_font(28, True),
              fill=(220, 50, 50), anchor="mm")
    
    # "SNAPSHOT" - white
    draw.text((left_width // 2, title_y + 70), "SNAPSHOT", font=get_font(26, True),
              fill=(255, 255, 255), anchor="mm")
    
    # Date - bright green like reference
    draw.text((left_width // 2, title_y + 110), snapshot_date, font=get_font(18, True),
              fill=(50, 220, 80), anchor="mm")
    
    # Legend - colored boxes with white text
    legend_y = 380
    legend_items = [
        (PERF_COLORS["exceeding"], "EXCEEDING ALL", "EXPECTATIONS"),
        (PERF_COLORS["meeting"], "MEETING", "EXPECTATIONS"),
        (PERF_COLORS["progress"], "WORK IN", "PROGRESS"),
        (PERF_COLORS["improvement"], "NEEDS IMMEDIATE", "IMPROVEMENT"),
    ]
    
    for i, (color, line1, line2) in enumerate(legend_items):
        y = legend_y + i * 65
        # Colored square
        draw.rectangle([25, y, 55, y + 30], fill=color)
        # White text
        draw.text((65, y + 2), line1, font=get_font(13, True), fill=(255, 255, 255))
        draw.text((65, y + 18), line2, font=get_font(13, True), fill=(255, 255, 255))
    
    # Footer text
    footer_y = SLIDE_HEIGHT - 90
    draw.text((left_width // 2, footer_y), "Don't wait to impact", font=get_font(11), 
              fill=(200, 200, 200), anchor="mm")
    draw.text((left_width // 2, footer_y + 15), "this number. If you have", font=get_font(11),
              fill=(200, 200, 200), anchor="mm")
    draw.text((left_width // 2, footer_y + 30), "questions, please see", font=get_font(11),
              fill=(200, 200, 200), anchor="mm")
    draw.text((left_width // 2, footer_y + 45), "a member of management.", font=get_font(11),
              fill=(200, 200, 200), anchor="mm")
    
    # ===== RIGHT PANEL - TABLE =====
    table_left = left_width + 15
    table_right = SLIDE_WIDTH - 15
    table_top = 50
    table_width = table_right - table_left
    
    header_h = 45
    avail_h = SLIDE_HEIGHT - table_top - 60
    row_h = (avail_h - header_h) // max(num_emps, 1)
    row_h = max(26, min(38, row_h))
    
    # Font sizes
    if row_h >= 34:
        name_sz, val_sz = 15, 14
    elif row_h >= 30:
        name_sz, val_sz = 13, 12
    else:
        name_sz, val_sz = 11, 10
    
    # Columns
    columns = [
        {"name": "Rank", "pct": 5},
        {"name": "Employee Name", "pct": 14},
        {"name": "PPA Score", "pct": 11, "key": "score_ppa"},
        {"name": "LBW Score", "pct": 11, "key": "score_lbw"},
        {"name": "Glass Score", "pct": 11, "key": "score_glass"},
        {"name": "LSC Score", "pct": 11, "key": "score_lsc"},
        {"name": "Review Bonus", "pct": 12, "key": "review_tracker_bonus", "is_bonus": True},
        {"name": "Metric Bonus", "pct": 12, "key": "total_metric_bonus", "is_bonus": True},
        {"name": "Total Score", "pct": 13, "key": "total_score"},
    ]
    
    col_widths = [int(c["pct"] / 100 * table_width) for c in columns]
    col_widths[-1] += table_width - sum(col_widths)
    
    col_x = []
    x = table_left
    for w in col_widths:
        col_x.append(x)
        x += w
    
    # Header row - dark blue like reference
    draw.rectangle([table_left, table_top, table_right, table_top + header_h],
                   fill=(20, 50, 90))
    
    header_font = get_font(12, True)
    for i, col in enumerate(columns):
        cx = col_x[i] + col_widths[i] // 2
        draw.text((cx, table_top + header_h // 2), col["name"],
                  font=header_font, fill=(255, 255, 255), anchor="mm")
    
    # Data rows - WHITE and LIGHT GRAY alternating (like reference)
    data_y = table_top + header_h
    name_font = get_font(name_sz, True)
    val_font = get_font(val_sz, True)
    
    tier_counts = {}
    
    for idx, emp in enumerate(sorted_emps):
        y = data_y + idx * row_h
        
        if y + row_h > SLIDE_HEIGHT - 40:
            break
        
        tier = emp.get("tier_label", "C-Server")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        # Row background - WHITE and LIGHT GRAY alternating
        row_bg = (255, 255, 255) if idx % 2 == 0 else (235, 240, 245)
        draw.rectangle([table_left, y, table_right, y + row_h], fill=row_bg)
        
        # Row border
        draw.line([(table_left, y + row_h), (table_right, y + row_h)], fill=(200, 205, 210), width=1)
        
        row_cy = y + row_h // 2
        
        # Rank
        prefix = {"Trainer": "T", "Bartender": "BAR", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "?")
        rank = f"{prefix}{tier_counts[tier]}"
        draw.text((col_x[0] + col_widths[0] // 2, row_cy), rank,
                  font=val_font, fill=(40, 40, 40), anchor="mm")
        
        # Name
        name = emp.get("name", "Unknown")
        max_ch = int(col_widths[1] / (name_sz * 0.55))
        if len(name) > max_ch:
            name = name[:max_ch - 1] + "…"
        draw.text((col_x[1] + 6, row_cy), name,
                  font=name_font, fill=(30, 30, 30), anchor="lm")
        
        # Column separators
        for i in range(len(columns)):
            draw.line([(col_x[i], y), (col_x[i], y + row_h)], fill=(200, 205, 210), width=1)
        draw.line([(table_right, y), (table_right, y + row_h)], fill=(200, 205, 210), width=1)
        
        # Score columns - colored cells
        for i, col in enumerate(columns[2:], start=2):
            key = col.get("key")
            if not key:
                continue
            
            val = emp.get(key, 0) or 0
            is_bonus = col.get("is_bonus", False)
            
            # Cell dimensions with padding
            cell_pad = 3
            cx = col_x[i] + cell_pad
            cw = col_widths[i] - cell_pad * 2
            ch = row_h - 6
            cy = y + 3
            
            # Determine color and text
            if is_bonus:
                if val > 2:
                    color = PERF_COLORS["meeting"]
                elif val > 0:
                    color = PERF_COLORS["progress"]
                elif val < 0:
                    color = PERF_COLORS["improvement"]
                else:
                    color = PERF_COLORS["progress"]
                txt = f"{val:.1f}" if val != 0 else "0"
            elif key == "total_score":
                color = get_perf_color(val)
                txt = f"{val:.1f}"
            else:
                color = get_perf_color(val)
                txt = f"{val:.0f}%"
            
            # Draw colored cell
            draw.rectangle([cx, cy, cx + cw, cy + ch], fill=color)
            
            # White text on colored cell
            draw.text((cx + cw // 2, row_cy), txt,
                      font=val_font, fill=(255, 255, 255), anchor="mm")
    
    # Table outer border
    final_y = data_y + min(num_emps, int((SLIDE_HEIGHT - 60 - data_y) / row_h)) * row_h
    draw.rectangle([table_left, table_top, table_right, final_y], outline=(100, 110, 120), width=2)
    
    # Employee count footer
    draw.text((table_right, SLIDE_HEIGHT - 25), f"{num_emps} employees",
              font=get_font(12), fill=(200, 200, 200), anchor="ra")
    
    # Save
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


def get_available_backgrounds():
    return [{"key": k, "name": v["name"]} for k, v in BACKGROUNDS.items()]
