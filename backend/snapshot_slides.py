"""
Snapshot Slide Generator - PREMIUM VISUAL DESIGN
Striking, modern, TV-optimized display
Ocean-inspired theme matching Bubba Gump brand
"""
import io
import os
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from datetime import datetime
import math
import random

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

BACKGROUNDS = {
    "ocean": {"name": "Ocean Blue"},
    "sunset": {"name": "Sunset"},
    "midnight": {"name": "Midnight"},
}

# Premium color palette
COLORS = {
    "bg_dark": (8, 32, 50),
    "bg_mid": (12, 45, 72),
    "accent_coral": (255, 107, 107),
    "accent_teal": (64, 224, 208),
    "accent_gold": (255, 215, 0),
    "white": (255, 255, 255),
    "glass_bg": (255, 255, 255, 25),
    "text_primary": (255, 255, 255),
    "text_secondary": (180, 200, 220),
}

# Performance colors - vibrant and distinct
PERF = {
    "excellent": (0, 200, 150),      # Teal green
    "good": (100, 220, 100),          # Bright green
    "warning": (255, 190, 50),        # Golden amber
    "danger": (255, 85, 85),          # Coral red
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


def create_ocean_background(w: int, h: int) -> Image.Image:
    """Create a rich, ocean-inspired gradient with wave patterns."""
    img = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(img)
    
    # Deep ocean gradient
    for y in range(h):
        progress = y / h
        r = int(5 + progress * 20)
        g = int(25 + progress * 45)
        b = int(55 + progress * 50)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    
    # Add wave-like curves
    random.seed(42)
    for wave in range(8):
        opacity = random.randint(15, 35)
        wave_y = random.randint(100, h - 100)
        amplitude = random.randint(30, 80)
        frequency = random.uniform(0.005, 0.015)
        
        points = []
        for x in range(0, w, 3):
            y = wave_y + int(amplitude * math.sin(x * frequency + wave))
            points.append((x, y))
        
        if len(points) > 1:
            wave_color = (80 + opacity, 150 + opacity, 180 + opacity)
            draw.line(points, fill=wave_color, width=2)
    
    # Soft light spots (like sun through water)
    for _ in range(15):
        cx = random.randint(0, w)
        cy = random.randint(0, h // 2)
        radius = random.randint(50, 200)
        for r in range(radius, 0, -3):
            alpha = int(8 * (r / radius))
            color = (100 + alpha * 3, 180 + alpha * 2, 220 + alpha)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color)
    
    return img


def draw_glass_panel(draw, x1, y1, x2, y2, radius=15):
    """Draw a frosted glass effect panel."""
    # Dark translucent background
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=(15, 35, 55))
    # Subtle border glow
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, outline=(80, 140, 180), width=1)


def get_perf_color(val: float) -> Tuple[int, int, int]:
    if val >= 100:
        return PERF["excellent"]
    elif val >= 80:
        return PERF["good"]
    elif val >= 70:
        return PERF["warning"]
    return PERF["danger"]


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "ocean",
    title: str = None
) -> bytes:
    """Generate premium visual snapshot slide."""
    
    # Create ocean background
    img = create_ocean_background(SLIDE_WIDTH, SLIDE_HEIGHT)
    draw = ImageDraw.Draw(img)
    
    # Load and place logo
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((160, 160), Image.Resampling.LANCZOS)
            img.paste(logo, (30, 20), logo)
        except:
            pass
    
    # Sort employees
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_emps = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    num_emps = len(sorted_emps)
    
    # ===== HEADER =====
    # Title - large, impactful
    title_font = get_font(52, bold=True)
    sub_font = get_font(28, bold=True)
    
    draw.text((210, 40), "TEAM PERFORMANCE", font=title_font, fill=COLORS["white"])
    draw.text((210, 100), "SNAPSHOT", font=title_font, fill=COLORS["accent_gold"])
    
    # Date badge
    date_font = get_font(22, bold=True)
    draw.rounded_rectangle([210, 160, 420, 195], radius=15, fill=COLORS["accent_teal"])
    draw.text((315, 177), snapshot_date, font=date_font, fill=COLORS["bg_dark"], anchor="mm")
    
    # Legend - top right, in a glass panel
    legend_x = SLIDE_WIDTH - 520
    draw_glass_panel(draw, legend_x - 20, 25, SLIDE_WIDTH - 30, 120, radius=12)
    
    leg_font = get_font(15, bold=True)
    leg_items = [
        (PERF["excellent"], "≥100%", "Exceeding"),
        (PERF["good"], "80-99%", "Meeting"),
        (PERF["warning"], "70-79%", "Progress"),
        (PERF["danger"], "<70%", "Improve"),
    ]
    
    for i, (color, pct, label) in enumerate(leg_items):
        x = legend_x + i * 120
        draw.rounded_rectangle([x, 40, x + 35, 65], radius=5, fill=color)
        draw.text((x + 17, 80), pct, font=get_font(12, bold=True), fill=COLORS["white"], anchor="mm")
        draw.text((x + 17, 100), label, font=get_font(10), fill=COLORS["text_secondary"], anchor="mm")
    
    # ===== MAIN TABLE =====
    table_top = 210
    table_left = 30
    table_right = SLIDE_WIDTH - 30
    table_width = table_right - table_left
    
    # Glass panel for table
    draw_glass_panel(draw, table_left - 10, table_top - 10, table_right + 10, SLIDE_HEIGHT - 40, radius=20)
    
    # Calculate sizing
    header_h = 50
    avail_h = SLIDE_HEIGHT - table_top - 80
    row_h = (avail_h - header_h) // max(num_emps, 1)
    row_h = max(28, min(38, row_h))
    
    # Dynamic fonts
    if row_h >= 34:
        name_sz, val_sz = 17, 16
    elif row_h >= 30:
        name_sz, val_sz = 15, 14
    else:
        name_sz, val_sz = 13, 12
    
    # Columns - optimized widths
    cols = [
        {"name": "RANK", "pct": 6},
        {"name": "EMPLOYEE", "pct": 15},
        {"name": "PPA", "pct": 12, "key": "score_ppa"},
        {"name": "LBW", "pct": 12, "key": "score_lbw"},
        {"name": "GLASS", "pct": 12, "key": "score_glass"},
        {"name": "LSC", "pct": 12, "key": "score_lsc"},
        {"name": "CV", "pct": 10, "key": "cv_score", "binary": True},
        {"name": "TOTAL", "pct": 21, "key": "total_score"},
    ]
    
    col_w = [int(c["pct"] / 100 * table_width) for c in cols]
    col_w[-1] += table_width - sum(col_w)
    
    col_x = []
    x = table_left
    for w in col_w:
        col_x.append(x)
        x += w
    
    # Header row - coral accent
    draw.rounded_rectangle(
        [table_left, table_top, table_right, table_top + header_h],
        radius=10, fill=COLORS["accent_coral"]
    )
    
    hdr_font = get_font(18, bold=True)
    for i, c in enumerate(cols):
        cx = col_x[i] + col_w[i] // 2
        draw.text((cx, table_top + header_h // 2), c["name"],
                  font=hdr_font, fill=COLORS["white"], anchor="mm")
    
    # Data rows
    data_y = table_top + header_h + 5
    name_font = get_font(name_sz, bold=True)
    val_font = get_font(val_sz, bold=True)
    rank_font = get_font(val_sz, bold=True)
    
    tier_colors = {
        "Trainer": (168, 85, 247),
        "Bartender": (59, 130, 246),
        "A-Server": (34, 197, 94),
        "B-Server": (234, 179, 8),
        "C-Server": (239, 68, 68),
    }
    tier_counts = {}
    
    for idx, emp in enumerate(sorted_emps):
        y = data_y + idx * row_h
        
        if y + row_h > SLIDE_HEIGHT - 60:
            more_font = get_font(16, bold=True)
            draw.text((SLIDE_WIDTH // 2, SLIDE_HEIGHT - 55),
                      f"+ {num_emps - idx} more employees",
                      font=more_font, fill=COLORS["accent_gold"], anchor="mm")
            break
        
        tier = emp.get("tier_label", "C-Server")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        t_color = tier_colors.get(tier, (100, 100, 100))
        
        # Row background - alternating
        row_bg = (20, 50, 75) if idx % 2 == 0 else (15, 40, 65)
        draw.rounded_rectangle([table_left + 5, y, table_right - 5, y + row_h - 3],
                               radius=6, fill=row_bg)
        
        # Tier indicator bar
        draw.rectangle([table_left + 5, y, table_left + 10, y + row_h - 3], fill=t_color)
        
        row_cy = y + row_h // 2
        
        # Rank
        prefix = {"Trainer": "T", "Bartender": "Bar", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "?")
        rank = f"{prefix}{tier_counts[tier]}"
        draw.text((col_x[0] + col_w[0] // 2, row_cy), rank,
                  font=rank_font, fill=t_color, anchor="mm")
        
        # Name
        name = emp.get("name", "")
        max_ch = int(col_w[1] / (name_sz * 0.55))
        if len(name) > max_ch:
            name = name[:max_ch - 1] + "…"
        draw.text((col_x[1] + 12, row_cy), name,
                  font=name_font, fill=COLORS["white"], anchor="lm")
        
        # Metrics
        for i, c in enumerate(cols[2:], start=2):
            key = c.get("key")
            if not key:
                continue
            
            val = emp.get(key, 0) or 0
            is_bin = c.get("binary", False)
            
            cx = col_x[i] + 5
            cw = col_w[i] - 10
            ch = row_h - 10
            cy_cell = y + 5
            
            if is_bin:
                color = PERF["good"] if val > 0 else PERF["danger"]
                txt = f"+{int(val)}" if val > 0 else str(int(val))
            else:
                color = get_perf_color(val)
                txt = f"{val:.0f}%"
            
            draw.rounded_rectangle([cx, cy_cell, cx + cw, cy_cell + ch],
                                   radius=6, fill=color)
            draw.text((cx + cw // 2, row_cy), txt,
                      font=val_font, fill=COLORS["white"], anchor="mm")
    
    # Footer
    foot_font = get_font(14, bold=True)
    draw.text((table_left + 20, SLIDE_HEIGHT - 30),
              f"{num_emps} Team Members", font=foot_font, fill=COLORS["text_secondary"])
    draw.text((table_right - 20, SLIDE_HEIGHT - 30),
              datetime.now().strftime("%B %d, %Y"), font=foot_font,
              fill=COLORS["text_secondary"], anchor="ra")
    
    # Save
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


def get_available_backgrounds():
    return [{"key": k, "name": v["name"]} for k, v in BACKGROUNDS.items()]
