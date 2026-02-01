"""
Snapshot Slide Generator - TV OPTIMIZED
Generates bi-weekly team snapshot slides (1920x1080 PNG)
Designed for readability on large TV displays from a distance
"""
import io
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import math

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

# Background themes
BACKGROUNDS = {
    "midnight_blue": {
        "name": "Midnight Blue",
        "bg_color": (10, 25, 50),
        "header_color": (20, 45, 80),
        "row_alt": (15, 35, 65),
        "accent": (59, 130, 246),
    },
    "slate_dark": {
        "name": "Slate Dark",
        "bg_color": (15, 23, 42),
        "header_color": (30, 41, 59),
        "row_alt": (20, 30, 50),
        "accent": (100, 116, 139),
    },
    "forest_green": {
        "name": "Forest Green",
        "bg_color": (10, 30, 20),
        "header_color": (20, 50, 35),
        "row_alt": (15, 40, 28),
        "accent": (34, 197, 94),
    },
    "bubba_red": {
        "name": "Bubba Gump Red",
        "bg_color": (40, 10, 10),
        "header_color": (60, 20, 20),
        "row_alt": (50, 15, 15),
        "accent": (220, 38, 38),
    },
}

# Tier colors - bright and visible
TIER_COLORS = {
    "Trainer": "#A855F7",
    "Bartender": "#3B82F6", 
    "A-Server": "#22C55E",
    "B-Server": "#EAB308",
    "C-Server": "#EF4444",
}

# Performance colors - high contrast
COLORS = {
    "green": (34, 197, 94),      # Bright green
    "yellow": (234, 179, 8),     # Bright yellow
    "red": (239, 68, 68),        # Bright red
    "white": (255, 255, 255),
    "light_gray": (200, 200, 200),
}


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


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
    """Get performance color based on percentage."""
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
    Generate a TV-optimized snapshot slide.
    Large fonts, high contrast, clear layout for viewing from distance.
    """
    theme = BACKGROUNDS.get(background, BACKGROUNDS["midnight_blue"])
    
    # Create base image
    img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), theme["bg_color"])
    draw = ImageDraw.Draw(img)
    
    # Sort employees by tier then score
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_employees = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    
    num_employees = len(sorted_employees)
    
    # ===== HEADER AREA =====
    header_height = 80
    draw.rectangle([0, 0, SLIDE_WIDTH, header_height], fill=theme["header_color"])
    
    # Title
    title_font = get_font(42, bold=True)
    title_text = title or "TEAM SNAPSHOT"
    draw.text((40, 20), title_text, font=title_font, fill=COLORS["white"])
    
    # Date and company on right
    subtitle_font = get_font(24)
    date_text = f"{snapshot_date}"
    draw.text((SLIDE_WIDTH - 40, 20), date_text, font=subtitle_font, fill=COLORS["light_gray"], anchor="ra")
    draw.text((SLIDE_WIDTH - 40, 50), "Bubba Gump Shrimp Co.", font=get_font(18), fill=COLORS["light_gray"], anchor="ra")
    
    # Legend on header
    legend_font = get_font(18, bold=True)
    legend_x = 500
    draw.rectangle([legend_x, 25, legend_x + 25, 50], fill=COLORS["green"])
    draw.text((legend_x + 32, 30), "≥80%", font=legend_font, fill=COLORS["white"])
    draw.rectangle([legend_x + 100, 25, legend_x + 125, 50], fill=COLORS["yellow"])
    draw.text((legend_x + 132, 30), "70-79%", font=legend_font, fill=COLORS["white"])
    draw.rectangle([legend_x + 220, 25, legend_x + 245, 50], fill=COLORS["red"])
    draw.text((legend_x + 252, 30), "<70%", font=legend_font, fill=COLORS["white"])
    
    # ===== TABLE SETUP =====
    table_top = header_height + 10
    table_bottom = SLIDE_HEIGHT - 50
    available_height = table_bottom - table_top
    
    # Column headers row
    col_header_height = 50
    
    # Calculate row height - optimize for readability
    max_rows = 20  # Maximum rows for good readability
    rows_to_show = min(num_employees, max_rows)
    row_height = min(48, (available_height - col_header_height) // rows_to_show)
    row_height = max(36, row_height)  # Minimum row height
    
    # Define columns with fixed widths for TV readability
    # Name gets more space, metrics are equal width
    col_defs = [
        {"name": "EMPLOYEE", "width": 280},
        {"name": "TIER", "width": 100},
        {"name": "PPA", "width": 140, "key": "score_ppa"},
        {"name": "LBW", "width": 140, "key": "score_lbw"},
        {"name": "GLASS", "width": 140, "key": "score_glass"},
        {"name": "LSC", "width": 140, "key": "score_lsc"},
        {"name": "CV", "width": 100, "key": "cv_score", "is_binary": True},
        {"name": "TOTAL", "width": 160, "key": "total_score"},
    ]
    
    # Calculate starting x to center the table
    total_width = sum(c["width"] for c in col_defs)
    start_x = (SLIDE_WIDTH - total_width) // 2
    
    # Calculate column positions
    col_positions = []
    x = start_x
    for col in col_defs:
        col_positions.append(x)
        x += col["width"]
    
    # ===== COLUMN HEADERS =====
    header_y = table_top
    draw.rectangle([start_x - 5, header_y, start_x + total_width + 5, header_y + col_header_height], 
                   fill=theme["header_color"])
    
    header_font = get_font(22, bold=True)
    for i, col in enumerate(col_defs):
        center_x = col_positions[i] + col["width"] // 2
        draw.text((center_x, header_y + col_header_height // 2), 
                  col["name"], font=header_font, fill=COLORS["white"], anchor="mm")
    
    # ===== DATA ROWS =====
    data_start_y = header_y + col_header_height + 5
    
    name_font = get_font(22, bold=True)
    value_font = get_font(24, bold=True)
    tier_font = get_font(18, bold=True)
    
    for idx, emp in enumerate(sorted_employees[:rows_to_show]):
        y = data_start_y + idx * row_height
        
        # Alternating row background
        if idx % 2 == 0:
            draw.rectangle([start_x - 5, y, start_x + total_width + 5, y + row_height - 2],
                          fill=theme["row_alt"])
        
        tier = emp.get("tier_label", "C-Server")
        tier_color = hex_to_rgb(TIER_COLORS.get(tier, "#666666"))
        
        # Left color bar for tier
        draw.rectangle([start_x - 5, y, start_x, y + row_height - 2], fill=tier_color)
        
        row_center_y = y + row_height // 2
        
        # Employee name
        name = emp.get("name", "Unknown")
        if len(name) > 16:
            name = name[:15] + "…"
        draw.text((col_positions[0] + 15, row_center_y), name, 
                  font=name_font, fill=COLORS["white"], anchor="lm")
        
        # Tier badge
        tier_short = {"Trainer": "TRN", "Bartender": "BAR", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "?")
        badge_x = col_positions[1] + col_defs[1]["width"] // 2
        badge_w, badge_h = 60, 28
        draw.rounded_rectangle(
            [badge_x - badge_w//2, row_center_y - badge_h//2, 
             badge_x + badge_w//2, row_center_y + badge_h//2],
            radius=14, fill=tier_color
        )
        draw.text((badge_x, row_center_y), tier_short, font=tier_font, fill=COLORS["white"], anchor="mm")
        
        # Metric columns
        for i, col in enumerate(col_defs[2:], start=2):
            key = col.get("key")
            if not key:
                continue
                
            value = emp.get(key, 0) or 0
            is_binary = col.get("is_binary", False)
            
            cell_x = col_positions[i]
            cell_w = col["width"]
            cell_padding = 8
            
            # Cell background with performance color
            if is_binary:
                # CV: binary green/red
                cell_color = COLORS["green"] if value > 0 else COLORS["red"]
                display_text = f"+{int(value)}" if value > 0 else "0"
            else:
                cell_color = get_perf_color(value)
                display_text = f"{value:.0f}%"
            
            # Draw cell
            draw.rounded_rectangle(
                [cell_x + cell_padding, y + 4, 
                 cell_x + cell_w - cell_padding, y + row_height - 6],
                radius=6, fill=cell_color
            )
            
            # Draw value
            draw.text((cell_x + cell_w // 2, row_center_y), display_text,
                      font=value_font, fill=COLORS["white"], anchor="mm")
    
    # Show overflow indicator if needed
    if num_employees > rows_to_show:
        overflow_text = f"+ {num_employees - rows_to_show} more employees"
        overflow_font = get_font(20)
        draw.text((SLIDE_WIDTH // 2, table_bottom - 20), overflow_text,
                  font=overflow_font, fill=COLORS["light_gray"], anchor="mm")
    
    # ===== FOOTER =====
    footer_font = get_font(16)
    footer_y = SLIDE_HEIGHT - 35
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y')} • {num_employees} employees"
    draw.text((SLIDE_WIDTH // 2, footer_y), footer_text, 
              font=footer_font, fill=COLORS["light_gray"], anchor="mm")
    
    # Save
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def get_available_backgrounds() -> List[Dict[str, str]]:
    """Get list of available background options."""
    return [
        {"key": key, "name": config["name"]}
        for key, config in BACKGROUNDS.items()
    ]
