"""
Server Performance Snapshot - Clean Web Style with Gridlines
Matches the Full Rankings page design exactly
"""
import io
import os
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

BACKGROUNDS = {"clean": {"name": "Clean White"}}

# Tier colors matching web design
TIER_COLORS = {
    "Trainer": (216, 180, 254),       # Light purple
    "Bartender": (147, 197, 253),     # Light blue
    "A-Server": (134, 239, 172),      # Light green
    "B-Server": (253, 186, 116),      # Light orange
    "C-Server": (252, 165, 165),      # Light red
}

TIER_TEXT_COLORS = {
    "Trainer": (126, 34, 206),        # Purple text
    "Bartender": (37, 99, 235),       # Blue text
    "A-Server": (22, 163, 74),        # Green text
    "B-Server": (234, 88, 12),        # Orange text
    "C-Server": (220, 38, 38),        # Red text
}

# Progress bar colors
PROGRESS_COLORS = {
    "green": (34, 197, 94),
    "yellow": (234, 179, 8),
    "red": (239, 68, 68),
}


def get_font(size: int, bold: bool = False):
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except:
            pass
    return ImageFont.load_default()


def get_progress_color(percentage: float) -> Tuple[int, int, int]:
    if percentage >= 80:
        return PROGRESS_COLORS["green"]
    elif percentage >= 70:
        return PROGRESS_COLORS["yellow"]
    return PROGRESS_COLORS["red"]


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "clean",
    title: str = None
) -> bytes:
    """Generate snapshot matching the clean web design with gridlines."""
    
    # White/light gray background
    img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), (248, 250, 252))
    draw = ImageDraw.Draw(img)
    
    # Sort employees
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_emps = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    num_emps = len(sorted_emps)
    
    # Logo in top left
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((100, 100), Image.Resampling.LANCZOS)
            img.paste(logo, (20, 15), logo)
        except:
            pass
    
    draw = ImageDraw.Draw(img)
    
    # Title next to logo
    draw.text((140, 30), "SERVER PERFORMANCE SNAPSHOT", font=get_font(28, True), fill=(30, 41, 59))
    draw.text((140, 65), snapshot_date, font=get_font(18), fill=(100, 116, 139))
    
    # Table dimensions
    table_left = 20
    table_right = SLIDE_WIDTH - 20
    table_top = 120
    table_width = table_right - table_left
    
    # Header height and row calculations
    header_h = 50
    avail_h = SLIDE_HEIGHT - table_top - 30
    row_h = (avail_h - header_h) // max(num_emps, 1)
    row_h = max(38, min(50, row_h))
    
    # Columns - equal width
    columns = [
        {"name": "POSITION", "width": 100},
        {"name": "EMPLOYEE", "width": 200},
        {"name": "TIER", "width": 120},
        {"name": "TOTAL SCORE", "width": 140},
        {"name": "BONUS", "width": 100},
        {"name": "PPA (25%)", "width": 180, "key": "score_ppa", "max": 30},
        {"name": "LBW (20%)", "width": 180, "key": "score_lbw", "max": 25},
        {"name": "LSC (25%)", "width": 180, "key": "score_lsc", "max": 30},
        {"name": "GLASS (15%)", "width": 180, "key": "score_glass", "max": 20},
    ]
    
    # Adjust widths to fit
    total_w = sum(c["width"] for c in columns)
    scale = table_width / total_w
    for c in columns:
        c["width"] = int(c["width"] * scale)
    
    # Calculate positions
    col_x = []
    x = table_left
    for c in columns:
        col_x.append(x)
        x += c["width"]
    
    # Red accent line at top
    draw.rectangle([table_left, table_top - 4, table_right, table_top], fill=(239, 68, 68))
    
    # Header row - dark navy
    draw.rectangle([table_left, table_top, table_right, table_top + header_h], fill=(30, 41, 59))
    
    # Yellow accent under header for metric columns
    metric_start = col_x[5]  # PPA column
    draw.rectangle([metric_start, table_top + header_h, table_right, table_top + header_h + 4], fill=(250, 204, 21))
    
    # Header text
    header_font = get_font(13, True)
    for i, col in enumerate(columns):
        cx = col_x[i] + col["width"] // 2
        draw.text((cx, table_top + header_h // 2), col["name"],
                  font=header_font, fill=(255, 255, 255), anchor="mm")
    
    # Data rows
    data_y = table_top + header_h + 6
    tier_counts = {}
    
    for idx, emp in enumerate(sorted_emps):
        y = data_y + idx * row_h
        
        if y + row_h > SLIDE_HEIGHT - 20:
            break
        
        tier = emp.get("tier_label", "C-Server")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        # Alternating row backgrounds
        row_bg = (255, 255, 255) if idx % 2 == 0 else (241, 245, 249)
        draw.rectangle([table_left, y, table_right, y + row_h], fill=row_bg)
        
        # GRIDLINE between rows - black line
        draw.line([(table_left, y + row_h), (table_right, y + row_h)], fill=(0, 0, 0), width=1)
        
        row_cy = y + row_h // 2
        tier_color = TIER_COLORS.get(tier, (200, 200, 200))
        tier_text_color = TIER_TEXT_COLORS.get(tier, (50, 50, 50))
        
        # Column 1: Position with rank badge
        pos_x = col_x[0] + 15
        # Position number
        draw.text((pos_x, row_cy), str(idx + 1), font=get_font(20, True), fill=(100, 116, 139), anchor="lm")
        
        # Tier badge (T1, Bar1, A1, etc.)
        prefix = {"Trainer": "T", "Bartender": "Bar", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "?")
        badge_text = f"{prefix}{tier_counts[tier]}"
        badge_x = pos_x + 35
        badge_w, badge_h = 45, 28
        draw.rounded_rectangle([badge_x, row_cy - badge_h//2, badge_x + badge_w, row_cy + badge_h//2],
                               radius=6, fill=tier_color)
        draw.text((badge_x + badge_w//2, row_cy), badge_text, font=get_font(12, True), 
                  fill=tier_text_color, anchor="mm")
        
        # Column 2: Employee name
        name = emp.get("name", "Unknown")
        job = emp.get("job_title", "server").lower()
        draw.text((col_x[1] + 10, row_cy - 8), name, font=get_font(15, True), fill=(30, 41, 59), anchor="lm")
        draw.text((col_x[1] + 10, row_cy + 10), job, font=get_font(11), fill=(148, 163, 184), anchor="lm")
        
        # Column 3: Tier badge
        tier_label = tier
        tier_badge_w = 90
        tier_badge_x = col_x[2] + (columns[2]["width"] - tier_badge_w) // 2
        draw.rounded_rectangle([tier_badge_x, row_cy - 14, tier_badge_x + tier_badge_w, row_cy + 14],
                               radius=14, fill=tier_color)
        draw.text((tier_badge_x + tier_badge_w//2, row_cy), tier_label, font=get_font(12, True),
                  fill=tier_text_color, anchor="mm")
        
        # Column 4: Total Score - RED bold text
        total = emp.get("total_score", 0) or 0
        draw.text((col_x[3] + columns[3]["width"]//2, row_cy), f"{total:.2f}",
                  font=get_font(22, True), fill=(220, 38, 38), anchor="mm")
        
        # Column 5: Bonus
        bonus = (emp.get("total_metric_bonus", 0) or 0) + (emp.get("review_tracker_bonus", 0) or 0)
        bonus_color = (22, 163, 74) if bonus > 0 else (148, 163, 184)
        bonus_text = f"+{bonus:.2f}" if bonus > 0 else f"{bonus:.2f}"
        draw.text((col_x[4] + columns[4]["width"]//2, row_cy), bonus_text,
                  font=get_font(14, True), fill=bonus_color, anchor="mm")
        
        # Metric columns with progress bars
        metrics = [
            ("score_ppa", 5, 30),
            ("score_lbw", 6, 25),
            ("score_lsc", 7, 30),
            ("score_glass", 8, 20),
        ]
        
        for key, col_idx, max_val in metrics:
            val = emp.get(key, 0) or 0
            # Calculate actual score (val is percentage, convert to points)
            actual = (val / 100) * max_val
            percentage = val
            
            col_center = col_x[col_idx] + columns[col_idx]["width"] // 2
            
            # Score text
            score_text = f"{actual:.2f} / {max_val}"
            draw.text((col_center, row_cy - 8), score_text, font=get_font(13, True), fill=(51, 65, 85), anchor="mm")
            
            # Progress bar
            bar_w = columns[col_idx]["width"] - 30
            bar_h = 8
            bar_x = col_x[col_idx] + 15
            bar_y = row_cy + 8
            
            # Background bar
            draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                                   radius=4, fill=(226, 232, 240))
            
            # Filled bar
            fill_w = int((percentage / 100) * bar_w)
            fill_w = min(fill_w, bar_w)
            if fill_w > 0:
                bar_color = get_progress_color(percentage)
                draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h],
                                       radius=4, fill=bar_color)
    
    # Outer border
    final_y = data_y + min(num_emps, int((SLIDE_HEIGHT - 30 - data_y) / row_h)) * row_h
    draw.rectangle([table_left, table_top, table_right, final_y], outline=(0, 0, 0), width=2)
    
    # Vertical gridlines
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
