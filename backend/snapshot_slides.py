"""
Snapshot Slide Generator - TV OPTIMIZED, EDGE TO EDGE
Generates bi-weekly team snapshot slides (1920x1080 PNG)
Full width, all employees, optimized for TV displays
"""
import io
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

# Background themes
BACKGROUNDS = {
    "midnight_blue": {
        "name": "Midnight Blue",
        "bg_color": (10, 25, 50),
        "header_color": (20, 45, 80),
        "row_alt": (15, 35, 65),
    },
    "slate_dark": {
        "name": "Slate Dark",
        "bg_color": (15, 23, 42),
        "header_color": (30, 41, 59),
        "row_alt": (20, 30, 50),
    },
    "forest_green": {
        "name": "Forest Green",
        "bg_color": (10, 30, 20),
        "header_color": (20, 50, 35),
        "row_alt": (15, 40, 28),
    },
    "bubba_red": {
        "name": "Bubba Gump Red",
        "bg_color": (40, 10, 10),
        "header_color": (60, 20, 20),
        "row_alt": (50, 15, 15),
    },
}

# Tier colors
TIER_COLORS = {
    "Trainer": (168, 85, 247),
    "Bartender": (59, 130, 246), 
    "A-Server": (34, 197, 94),
    "B-Server": (234, 179, 8),
    "C-Server": (239, 68, 68),
}

# Performance colors
COLORS = {
    "green": (34, 197, 94),
    "yellow": (234, 179, 8),
    "red": (239, 68, 68),
    "white": (255, 255, 255),
    "light_gray": (180, 180, 180),
}


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()


def get_perf_color(value: float) -> Tuple[int, int, int]:
    if value >= 80:
        return COLORS["green"]
    elif value >= 70:
        return COLORS["yellow"]
    else:
        return COLORS["red"]


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "midnight_blue",
    title: str = None
) -> bytes:
    """
    Generate edge-to-edge snapshot slide showing ALL employees.
    Dynamic sizing based on employee count.
    """
    theme = BACKGROUNDS.get(background, BACKGROUNDS["midnight_blue"])
    
    img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), theme["bg_color"])
    draw = ImageDraw.Draw(img)
    
    # Sort employees
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_employees = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    
    num_employees = len(sorted_employees)
    
    # ===== LAYOUT CALCULATIONS =====
    header_height = 65
    footer_height = 30
    col_header_height = 40
    
    # Available height for data rows
    data_area_height = SLIDE_HEIGHT - header_height - footer_height - col_header_height
    
    # Calculate row height to fit ALL employees
    row_height = data_area_height // max(num_employees, 1)
    row_height = max(22, min(40, row_height))  # Clamp between 22-40px
    
    # Dynamic font sizes based on row height
    if row_height >= 36:
        name_size, value_size, tier_size = 18, 18, 14
    elif row_height >= 30:
        name_size, value_size, tier_size = 15, 16, 12
    elif row_height >= 26:
        name_size, value_size, tier_size = 13, 14, 10
    else:
        name_size, value_size, tier_size = 11, 12, 9
    
    # ===== HEADER - EDGE TO EDGE =====
    draw.rectangle([0, 0, SLIDE_WIDTH, header_height], fill=theme["header_color"])
    
    title_font = get_font(32, bold=True)
    title_text = title or "TEAM SNAPSHOT"
    draw.text((20, 15), title_text, font=title_font, fill=COLORS["white"])
    
    # Date on right
    date_font = get_font(20)
    draw.text((SLIDE_WIDTH - 20, 18), snapshot_date, font=date_font, fill=COLORS["light_gray"], anchor="ra")
    draw.text((SLIDE_WIDTH - 20, 42), "Bubba Gump Shrimp Co.", font=get_font(14), fill=COLORS["light_gray"], anchor="ra")
    
    # Legend in header
    legend_font = get_font(14, bold=True)
    lx = 400
    draw.rectangle([lx, 22, lx+20, 42], fill=COLORS["green"])
    draw.text((lx+26, 25), "≥80%", font=legend_font, fill=COLORS["white"])
    draw.rectangle([lx+85, 22, lx+105, 42], fill=COLORS["yellow"])
    draw.text((lx+111, 25), "70-79%", font=legend_font, fill=COLORS["white"])
    draw.rectangle([lx+185, 22, lx+205, 42], fill=COLORS["red"])
    draw.text((lx+211, 25), "<70%", font=legend_font, fill=COLORS["white"])
    
    # ===== COLUMN SETUP - EDGE TO EDGE =====
    margin = 10
    table_width = SLIDE_WIDTH - (2 * margin)
    
    # Column proportions (total = 100)
    col_props = [
        {"name": "EMPLOYEE", "prop": 18},
        {"name": "TIER", "prop": 8},
        {"name": "PPA", "prop": 12, "key": "score_ppa"},
        {"name": "LBW", "prop": 12, "key": "score_lbw"},
        {"name": "GLASS", "prop": 12, "key": "score_glass"},
        {"name": "LSC", "prop": 12, "key": "score_lsc"},
        {"name": "CV", "prop": 10, "key": "cv_score", "is_binary": True},
        {"name": "TOTAL", "prop": 16, "key": "total_score"},
    ]
    
    total_prop = sum(c["prop"] for c in col_props)
    col_widths = [int((c["prop"] / total_prop) * table_width) for c in col_props]
    col_widths[-1] += table_width - sum(col_widths)  # Adjust for rounding
    
    col_positions = []
    x = margin
    for w in col_widths:
        col_positions.append(x)
        x += w
    
    # ===== COLUMN HEADERS =====
    col_header_y = header_height
    draw.rectangle([0, col_header_y, SLIDE_WIDTH, col_header_y + col_header_height], fill=theme["header_color"])
    
    header_font = get_font(16, bold=True)
    for i, col in enumerate(col_props):
        cx = col_positions[i] + col_widths[i] // 2
        draw.text((cx, col_header_y + col_header_height // 2), col["name"], 
                  font=header_font, fill=COLORS["white"], anchor="mm")
    
    # ===== DATA ROWS - ALL EMPLOYEES =====
    data_start_y = col_header_y + col_header_height
    
    name_font = get_font(name_size, bold=True)
    value_font = get_font(value_size, bold=True)
    tier_font = get_font(tier_size, bold=True)
    
    for idx, emp in enumerate(sorted_employees):
        y = data_start_y + idx * row_height
        
        # Stop if we run out of space
        if y + row_height > SLIDE_HEIGHT - footer_height:
            break
        
        # Alternating background - edge to edge
        if idx % 2 == 0:
            draw.rectangle([0, y, SLIDE_WIDTH, y + row_height], fill=theme["row_alt"])
        
        tier = emp.get("tier_label", "C-Server")
        tier_color = TIER_COLORS.get(tier, (100, 100, 100))
        
        # Tier color bar on left edge
        draw.rectangle([0, y, 5, y + row_height], fill=tier_color)
        
        row_cy = y + row_height // 2
        
        # Employee name
        name = emp.get("name", "Unknown")
        max_chars = col_widths[0] // (name_size * 0.6)
        if len(name) > max_chars:
            name = name[:int(max_chars)-1] + "…"
        draw.text((col_positions[0] + 10, row_cy), name, font=name_font, fill=COLORS["white"], anchor="lm")
        
        # Tier badge
        tier_short = {"Trainer": "TRN", "Bartender": "BAR", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "?")
        badge_cx = col_positions[1] + col_widths[1] // 2
        badge_w = min(50, col_widths[1] - 10)
        badge_h = min(22, row_height - 6)
        draw.rounded_rectangle(
            [badge_cx - badge_w//2, row_cy - badge_h//2, badge_cx + badge_w//2, row_cy + badge_h//2],
            radius=badge_h//2, fill=tier_color
        )
        draw.text((badge_cx, row_cy), tier_short, font=tier_font, fill=COLORS["white"], anchor="mm")
        
        # Metric columns
        for i, col in enumerate(col_props[2:], start=2):
            key = col.get("key")
            if not key:
                continue
            
            value = emp.get(key, 0) or 0
            is_binary = col.get("is_binary", False)
            
            cell_x = col_positions[i] + 3
            cell_w = col_widths[i] - 6
            cell_h = row_height - 4
            cell_y = y + 2
            
            if is_binary:
                cell_color = COLORS["green"] if value > 0 else COLORS["red"]
                text = f"+{int(value)}" if value > 0 else "0"
            else:
                cell_color = get_perf_color(value)
                text = f"{value:.0f}%"
            
            draw.rounded_rectangle(
                [cell_x, cell_y, cell_x + cell_w, cell_y + cell_h],
                radius=4, fill=cell_color
            )
            draw.text((cell_x + cell_w // 2, row_cy), text, font=value_font, fill=COLORS["white"], anchor="mm")
    
    # ===== FOOTER - EDGE TO EDGE =====
    footer_y = SLIDE_HEIGHT - footer_height
    draw.rectangle([0, footer_y, SLIDE_WIDTH, SLIDE_HEIGHT], fill=theme["header_color"])
    
    footer_font = get_font(14)
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y')} • {num_employees} employees"
    draw.text((SLIDE_WIDTH // 2, footer_y + footer_height // 2), footer_text,
              font=footer_font, fill=COLORS["light_gray"], anchor="mm")
    
    # Save
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def get_available_backgrounds() -> List[Dict[str, str]]:
    return [{"key": key, "name": config["name"]} for key, config in BACKGROUNDS.items()]
