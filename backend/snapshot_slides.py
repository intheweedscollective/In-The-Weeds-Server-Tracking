"""
Snapshot Slide Generator - REDESIGNED
Based on successful Bubba Gump slide design
16:9 format (1920x1080) for TV display
Two-panel layout: Left info panel + Right data table
"""
import io
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import math

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

# Performance tier colors (matching reference design)
TIER_COLORS = {
    "exceeding": (0, 120, 215),      # Blue - Exceeding expectations (>=100%)
    "meeting": (34, 177, 76),         # Green - Meeting expectations (80-99%)
    "progress": (255, 192, 0),        # Yellow/Orange - Work in progress (70-79%)
    "improvement": (237, 28, 36),     # Red - Needs improvement (<70%)
}

# Row background colors (gradient from green to red based on performance)
ROW_COLORS = {
    "top": (200, 230, 200),           # Light green for top performers
    "good": (220, 240, 200),          # Pale green
    "mid": (255, 255, 200),           # Yellow
    "low": (255, 220, 180),           # Orange
    "bottom": (255, 200, 180),        # Light red for bottom performers
}

COLORS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "dark_red": (139, 0, 0),
    "header_red": (180, 30, 30),
    "light_gray": (220, 220, 220),
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


def get_performance_color(value: float) -> Tuple[int, int, int]:
    """Get performance tier color based on percentage."""
    if value >= 100:
        return TIER_COLORS["exceeding"]
    elif value >= 80:
        return TIER_COLORS["meeting"]
    elif value >= 70:
        return TIER_COLORS["progress"]
    else:
        return TIER_COLORS["improvement"]


def get_row_color(rank_position: int, total: int) -> Tuple[int, int, int]:
    """Get row background color based on position (gradient effect)."""
    if total <= 1:
        return ROW_COLORS["mid"]
    
    ratio = rank_position / (total - 1) if total > 1 else 0
    
    if ratio < 0.25:
        return ROW_COLORS["top"]
    elif ratio < 0.5:
        return ROW_COLORS["good"]
    elif ratio < 0.75:
        return ROW_COLORS["mid"]
    elif ratio < 0.9:
        return ROW_COLORS["low"]
    else:
        return ROW_COLORS["bottom"]


def create_gradient_background(width: int, height: int) -> Image.Image:
    """Create a professional dark gradient background."""
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    
    # Dark blue-green gradient
    for y in range(height):
        ratio = y / height
        r = int(15 + ratio * 10)
        g = int(40 + ratio * 20)
        b = int(30 + ratio * 15)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # Add subtle bokeh-like circles for visual interest
    import random
    random.seed(42)  # Consistent pattern
    for _ in range(50):
        x = random.randint(0, width)
        y = random.randint(0, height)
        size = random.randint(20, 80)
        alpha = random.randint(10, 30)
        color = (255, 255, 255, alpha)
        # Draw semi-transparent circle
        for i in range(size):
            opacity = int(alpha * (1 - i/size))
            if opacity > 0:
                circle_color = (50 + opacity, 70 + opacity, 60 + opacity)
                draw.ellipse([x-i, y-i, x+i, y+i], outline=circle_color)
    
    return img


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "midnight_blue",
    title: str = None
) -> bytes:
    """
    Generate a professional two-panel snapshot slide.
    Left panel: Branding, title, legend
    Right panel: Full employee data table
    """
    # Create background
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT)
    draw = ImageDraw.Draw(img)
    
    # Sort employees by tier then score
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_employees = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    
    num_employees = len(sorted_employees)
    
    # ===== LAYOUT =====
    left_panel_width = 380
    right_panel_start = left_panel_width + 20
    table_width = SLIDE_WIDTH - right_panel_start - 20
    
    # ===== LEFT PANEL =====
    # Semi-transparent overlay for left panel
    overlay = Image.new('RGBA', (left_panel_width, SLIDE_HEIGHT), (0, 0, 0, 120))
    img.paste(Image.blend(img.crop((0, 0, left_panel_width, SLIDE_HEIGHT)).convert('RGBA'), 
                          overlay, 0.4).convert('RGB'), (0, 0))
    
    # Company name/logo area
    logo_font = get_font(36, bold=True)
    draw.text((20, 30), "BUBBA GUMP", font=logo_font, fill=(255, 100, 100))
    draw.text((20, 70), "SHRIMP CO.", font=get_font(28, bold=True), fill=COLORS["white"])
    
    # Title
    title_y = 150
    quarter_font = get_font(32, bold=True)
    draw.text((20, title_y), "TEAM", font=quarter_font, fill=COLORS["white"])
    
    perf_font = get_font(38, bold=True)
    draw.text((20, title_y + 40), "PERFORMANCE", font=perf_font, fill=(255, 80, 80))
    draw.text((20, title_y + 85), "SNAPSHOT", font=perf_font, fill=(255, 180, 80))
    
    # Date
    date_font = get_font(22, bold=True)
    draw.text((20, title_y + 140), snapshot_date, font=date_font, fill=(100, 200, 100))
    
    # Legend
    legend_y = 380
    legend_font = get_font(18, bold=True)
    legend_desc_font = get_font(14)
    
    legend_items = [
        (TIER_COLORS["exceeding"], "EXCEEDING", "EXPECTATIONS", ">=100%"),
        (TIER_COLORS["meeting"], "MEETING", "EXPECTATIONS", "80-99%"),
        (TIER_COLORS["progress"], "WORK IN", "PROGRESS", "70-79%"),
        (TIER_COLORS["improvement"], "NEEDS", "IMPROVEMENT", "<70%"),
    ]
    
    for i, (color, line1, line2, pct) in enumerate(legend_items):
        y = legend_y + i * 80
        # Color square
        draw.rectangle([20, y, 50, y + 30], fill=color)
        # Text
        draw.text((60, y), line1, font=legend_font, fill=color)
        draw.text((60, y + 22), line2, font=legend_font, fill=color)
        draw.text((60, y + 44), pct, font=legend_desc_font, fill=COLORS["light_gray"])
    
    # CV Legend (binary)
    cv_y = legend_y + 340
    draw.text((20, cv_y), "CV Score:", font=legend_font, fill=COLORS["white"])
    draw.rectangle([20, cv_y + 25, 50, cv_y + 50], fill=TIER_COLORS["meeting"])
    draw.text((60, cv_y + 28), "Positive", font=legend_desc_font, fill=COLORS["white"])
    draw.rectangle([140, cv_y + 25, 170, cv_y + 50], fill=TIER_COLORS["improvement"])
    draw.text((180, cv_y + 28), "Zero/Neg", font=legend_desc_font, fill=COLORS["white"])
    
    # Footer note
    footer_font = get_font(11)
    draw.text((20, SLIDE_HEIGHT - 80), "Performance metrics shown as", font=footer_font, fill=COLORS["light_gray"])
    draw.text((20, SLIDE_HEIGHT - 65), "percentage of benchmark targets.", font=footer_font, fill=COLORS["light_gray"])
    draw.text((20, SLIDE_HEIGHT - 40), f"Generated {datetime.now().strftime('%m/%d/%Y')}", font=footer_font, fill=COLORS["light_gray"])
    draw.text((20, SLIDE_HEIGHT - 25), f"{num_employees} employees", font=footer_font, fill=COLORS["light_gray"])
    
    # ===== RIGHT PANEL - DATA TABLE =====
    table_top = 20
    header_height = 45
    
    # Calculate row height to fit all employees
    available_height = SLIDE_HEIGHT - table_top - header_height - 30
    row_height = available_height // max(num_employees, 1)
    row_height = max(24, min(38, row_height))
    
    # Dynamic font sizes
    if row_height >= 34:
        name_size, value_size, rank_size = 16, 15, 14
    elif row_height >= 28:
        name_size, value_size, rank_size = 14, 13, 12
    else:
        name_size, value_size, rank_size = 12, 11, 10
    
    # Column definitions
    columns = [
        {"name": "Rank", "width": 70},
        {"name": "Employee", "width": 160},
        {"name": "PPA", "width": 90, "key": "score_ppa"},
        {"name": "LBW", "width": 90, "key": "score_lbw"},
        {"name": "Glass", "width": 90, "key": "score_glass"},
        {"name": "LSC", "width": 90, "key": "score_lsc"},
        {"name": "CV", "width": 70, "key": "cv_score", "is_binary": True},
        {"name": "TOTAL", "width": 100, "key": "total_score"},
    ]
    
    # Calculate column positions
    total_col_width = sum(c["width"] for c in columns)
    scale = table_width / total_col_width
    col_widths = [int(c["width"] * scale) for c in columns]
    col_widths[-1] += table_width - sum(col_widths)  # Adjust rounding
    
    col_positions = []
    x = right_panel_start
    for w in col_widths:
        col_positions.append(x)
        x += w
    
    # Draw header row
    draw.rectangle([right_panel_start, table_top, SLIDE_WIDTH - 20, table_top + header_height], 
                   fill=COLORS["header_red"])
    
    header_font = get_font(16, bold=True)
    for i, col in enumerate(columns):
        cx = col_positions[i] + col_widths[i] // 2
        draw.text((cx, table_top + header_height // 2), col["name"], 
                  font=header_font, fill=COLORS["white"], anchor="mm")
    
    # Track tier counts for ranking
    tier_counts = {"Trainer": 0, "Bartender": 0, "A-Server": 0, "B-Server": 0, "C-Server": 0}
    
    # Draw data rows
    data_start_y = table_top + header_height
    name_font = get_font(name_size, bold=True)
    value_font = get_font(value_size, bold=True)
    rank_font = get_font(rank_size, bold=True)
    
    for idx, emp in enumerate(sorted_employees):
        y = data_start_y + idx * row_height
        
        if y + row_height > SLIDE_HEIGHT - 20:
            break
        
        tier = emp.get("tier_label", "C-Server")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        # Row background color based on position
        row_bg = get_row_color(idx, num_employees)
        draw.rectangle([right_panel_start, y, SLIDE_WIDTH - 20, y + row_height - 1], fill=row_bg)
        
        row_cy = y + row_height // 2
        
        # Rank column (T1, Bar1, A1, B1, C1 format)
        tier_prefix = {"Trainer": "T", "Bartender": "Bar", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "?")
        rank_text = f"{tier_prefix}{tier_counts[tier]}"
        draw.text((col_positions[0] + col_widths[0] // 2, row_cy), rank_text,
                  font=rank_font, fill=COLORS["black"], anchor="mm")
        
        # Employee name
        name = emp.get("name", "Unknown")
        max_chars = col_widths[1] // (name_size * 0.55)
        if len(name) > max_chars:
            name = name[:int(max_chars)-1] + "…"
        draw.text((col_positions[1] + 8, row_cy), name, 
                  font=name_font, fill=COLORS["black"], anchor="lm")
        
        # Metric columns
        for i, col in enumerate(columns[2:], start=2):
            key = col.get("key")
            if not key:
                continue
            
            value = emp.get(key, 0) or 0
            is_binary = col.get("is_binary", False)
            
            cell_x = col_positions[i] + 4
            cell_w = col_widths[i] - 8
            cell_h = row_height - 6
            cell_y = y + 3
            
            if is_binary:
                # CV: green if positive, red if 0 or negative
                cell_color = TIER_COLORS["meeting"] if value > 0 else TIER_COLORS["improvement"]
                text = f"+{int(value)}" if value > 0 else str(int(value))
            else:
                cell_color = get_performance_color(value)
                text = f"{value:.0f}%"
            
            # Draw colored cell
            draw.rounded_rectangle(
                [cell_x, cell_y, cell_x + cell_w, cell_y + cell_h],
                radius=3, fill=cell_color
            )
            
            # Draw text
            draw.text((cell_x + cell_w // 2, row_cy), text,
                      font=value_font, fill=COLORS["white"], anchor="mm")
    
    # Save
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def get_available_backgrounds() -> List[Dict[str, str]]:
    return [
        {"key": "midnight_blue", "name": "Midnight Blue"},
        {"key": "forest_green", "name": "Forest Green"},
        {"key": "slate_dark", "name": "Slate Dark"},
    ]
