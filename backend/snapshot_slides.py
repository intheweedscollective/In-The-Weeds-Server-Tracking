"""
Snapshot Slide Generator
Generates bi-weekly team snapshot slides (1920x1080 PNG)
All employees on one page with conditional formatting - EDGE TO EDGE design
"""
import io
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import math

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

# Fun background themes
BACKGROUNDS = {
    "ocean_wave": {
        "name": "Ocean Wave",
        "colors": ["#0077B6", "#00B4D8", "#90E0EF"],
        "style": "wave"
    },
    "sunset_gradient": {
        "name": "Sunset Gradient",
        "colors": ["#FF6B6B", "#FFA07A", "#FFD93D"],
        "style": "gradient"
    },
    "forest_green": {
        "name": "Forest Green",
        "colors": ["#2D5A27", "#4A7C23", "#6B9B37"],
        "style": "gradient"
    },
    "purple_haze": {
        "name": "Purple Haze",
        "colors": ["#4A0E4E", "#7B2D8E", "#A855F7"],
        "style": "gradient"
    },
    "midnight_blue": {
        "name": "Midnight Blue",
        "colors": ["#0A1628", "#1E3A5F", "#2563EB"],
        "style": "gradient"
    },
    "coral_reef": {
        "name": "Coral Reef",
        "colors": ["#FF6F61", "#FF9A8B", "#FFECD2"],
        "style": "gradient"
    },
    "neon_nights": {
        "name": "Neon Nights",
        "colors": ["#0D0221", "#2D1B69", "#FF00FF"],
        "style": "neon"
    },
    "tropical_paradise": {
        "name": "Tropical Paradise",
        "colors": ["#00CED1", "#20B2AA", "#3CB371"],
        "style": "wave"
    },
    "golden_hour": {
        "name": "Golden Hour",
        "colors": ["#FF8C00", "#FFD700", "#FFF8DC"],
        "style": "gradient"
    },
    "cherry_blossom": {
        "name": "Cherry Blossom",
        "colors": ["#FFB7C5", "#FF69B4", "#FFC0CB"],
        "style": "gradient"
    },
    "slate_professional": {
        "name": "Slate Professional",
        "colors": ["#1E293B", "#334155", "#475569"],
        "style": "gradient"
    },
    "bubba_red": {
        "name": "Bubba Gump Red",
        "colors": ["#7F1D1D", "#B91C1C", "#DC2626"],
        "style": "gradient"
    },
}

# Tier configuration
TIER_ORDER = ["Trainer", "Bartender", "A-Server", "B-Server", "C-Server"]
TIER_COLORS = {
    "Trainer": "#A855F7",
    "Bartender": "#3B82F6",
    "A-Server": "#22C55E",
    "B-Server": "#EAB308",
    "C-Server": "#EF4444",
}

# Conditional formatting colors
CELL_COLORS = {
    "green": "#22C55E",   # ≥80%
    "yellow": "#EAB308",  # 70-79.99%
    "red": "#EF4444",     # <70%
}


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex to RGB."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get system font."""
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


def get_cell_color(percentage: float) -> str:
    """Get cell color based on percentage of benchmark."""
    if percentage >= 80:
        return CELL_COLORS["green"]
    elif percentage >= 70:
        return CELL_COLORS["yellow"]
    else:
        return CELL_COLORS["red"]


def create_background(width: int, height: int, bg_key: str = "midnight_blue") -> Image.Image:
    """Create a full-bleed background (edge-to-edge)."""
    bg_config = BACKGROUNDS.get(bg_key, BACKGROUNDS["midnight_blue"])
    colors = [hex_to_rgb(c) for c in bg_config["colors"]]
    style = bg_config["style"]
    
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    
    if style == "gradient":
        # Vertical gradient with multiple color stops
        for y in range(height):
            ratio = y / height
            if ratio < 0.5:
                r = ratio * 2
                c1, c2 = colors[0], colors[1] if len(colors) > 1 else colors[0]
            else:
                r = (ratio - 0.5) * 2
                c1 = colors[1] if len(colors) > 1 else colors[0]
                c2 = colors[2] if len(colors) > 2 else c1
            
            color = tuple(int(c1[i] + (c2[i] - c1[i]) * r) for i in range(3))
            draw.line([(0, y), (width, y)], fill=color)
    
    elif style == "wave":
        # Wave pattern background
        for y in range(height):
            base_ratio = y / height
            for x in range(width):
                wave = math.sin(x / 100 + y / 50) * 0.1
                ratio = max(0, min(1, base_ratio + wave))
                
                if ratio < 0.5:
                    r = ratio * 2
                    c1, c2 = colors[0], colors[1] if len(colors) > 1 else colors[0]
                else:
                    r = (ratio - 0.5) * 2
                    c1 = colors[1] if len(colors) > 1 else colors[0]
                    c2 = colors[2] if len(colors) > 2 else c1
                
                color = tuple(int(c1[i] + (c2[i] - c1[i]) * r) for i in range(3))
                draw.point((x, y), fill=color)
    
    elif style == "neon":
        # Dark base with neon accents
        base_color = colors[0]
        for y in range(height):
            for x in range(width):
                draw.point((x, y), fill=base_color)
        
        accent = colors[2] if len(colors) > 2 else colors[0]
        for i in range(0, width, 200):
            for y in range(height):
                alpha = int(50 * (1 - abs(y - height/2) / (height/2)))
                if alpha > 0:
                    glow_color = tuple(min(255, base_color[j] + accent[j] * alpha // 255) for j in range(3))
                    draw.point((i + int(30 * math.sin(y / 30)), y), fill=glow_color)
    
    return img


def calculate_percentage(value: float, benchmark: float) -> float:
    """Calculate percentage of benchmark."""
    if benchmark <= 0:
        return 0
    return (value / benchmark) * 100


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "midnight_blue",
    title: str = None
) -> bytes:
    """
    Generate a bi-weekly snapshot slide showing all employees in a grid.
    EDGE-TO-EDGE design that fills the entire 1920x1080 canvas.
    
    Args:
        employees: List of employee data with metrics
        benchmarks: Dict of metric benchmarks {ppa_benchmark: 55, lbw_benchmark: 6.5, ...}
        snapshot_date: Date string (e.g., "Jan 15, 2026")
        background: Background theme key
        title: Optional custom title
    
    Returns:
        PNG image bytes
    """
    img = create_background(SLIDE_WIDTH, SLIDE_HEIGHT, background)
    draw = ImageDraw.Draw(img)
    
    # Sort employees by tier hierarchy, then by score within tier
    def sort_key(emp):
        tier = emp.get("tier_label", "C-Server")
        tier_idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else 4
        score = emp.get("total_score", 0)
        return (tier_idx, -score)
    
    sorted_employees = sorted(employees, key=sort_key)
    num_employees = len(sorted_employees)
    
    # Edge-to-edge margins (minimal)
    MARGIN_H = 15  # Horizontal margin from edges
    MARGIN_TOP = 70  # Space for header
    MARGIN_BOTTOM = 35  # Space for footer
    
    # Calculate available space for table
    table_width = SLIDE_WIDTH - (2 * MARGIN_H)
    table_height = SLIDE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    
    # Dynamic font sizing based on employee count
    if num_employees <= 15:
        font_size_name = 20
        font_size_cell = 18
        header_height = 55
    elif num_employees <= 25:
        font_size_name = 17
        font_size_cell = 15
        header_height = 48
    elif num_employees <= 35:
        font_size_name = 14
        font_size_cell = 13
        header_height = 42
    else:
        font_size_name = 12
        font_size_cell = 11
        header_height = 38
    
    # Calculate row height based on available space
    data_area_height = table_height - header_height - 10
    row_height = max(24, min(45, data_area_height // max(num_employees, 1)))
    
    # Fonts
    font_title = get_font(32, bold=True)
    font_subtitle = get_font(16)
    font_header = get_font(font_size_cell + 2, bold=True)
    font_name = get_font(font_size_name, bold=True)
    font_cell = get_font(font_size_cell)
    font_tier = get_font(font_size_cell - 2, bold=True)
    font_subheader = get_font(11)
    
    # Column definitions - use pre-calculated normalized scores from employee data
    # These were calculated during upload/recalculate with the correct quarter settings
    columns = [
        {"name": "Employee", "short": "", "flex": 2.5, "key": None},
        {"name": "Tier", "short": "", "flex": 1.0, "key": None},
        {"name": "PPA", "short": "$/Guest", "flex": 1.2, "key": "score_ppa", "is_normalized": True},
        {"name": "LBW", "short": "$/Guest", "flex": 1.2, "key": "score_lbw", "is_normalized": True},
        {"name": "Glass", "short": "$/Guest", "flex": 1.2, "key": "score_glass", "is_normalized": True},
        {"name": "LSC", "short": "Guests/#", "flex": 1.2, "key": "score_lsc", "is_normalized": True},
        {"name": "CV", "short": "+/-", "flex": 1.0, "key": "cv_score", "is_binary": True},  # Binary: green if >0, red if <=0
        {"name": "TOTAL", "short": "Score", "flex": 1.2, "key": "total_score", "is_normalized": True},
    ]
    
    # Calculate column widths based on flex values
    total_flex = sum(c["flex"] for c in columns)
    col_widths = [int((c["flex"] / total_flex) * table_width) for c in columns]
    
    # Adjust last column to fill remaining space
    remaining = table_width - sum(col_widths)
    col_widths[-1] += remaining
    
    # Calculate column positions (edge-to-edge)
    col_positions = []
    x = MARGIN_H
    for width in col_widths:
        col_positions.append(x)
        x += width
    
    # Header area
    title_text = title or "TEAM SNAPSHOT"
    draw.text((SLIDE_WIDTH // 2, 12), title_text, font=font_title, fill="#FFFFFF", anchor="mt")
    draw.text((SLIDE_WIDTH // 2, 45), f"{snapshot_date} • Bubba Gump Shrimp Co.", 
              font=font_subtitle, fill="#E0E0E0", anchor="mt")
    
    # Table starts here
    table_start_y = MARGIN_TOP
    
    # Draw header background (full width)
    header_bg_color = (0, 0, 0, 100)
    draw.rectangle(
        [0, table_start_y, SLIDE_WIDTH, table_start_y + header_height],
        fill=(20, 30, 50)  # Dark semi-transparent
    )
    
    # Draw column headers
    for i, col in enumerate(columns):
        center_x = col_positions[i] + col_widths[i] // 2
        # Main header name
        draw.text((center_x, table_start_y + 10), col["name"], font=font_header, fill="#FFFFFF", anchor="mt")
        # Sub-description
        if col.get("short"):
            draw.text((center_x, table_start_y + 30), col["short"], font=font_subheader, fill="#AAAAAA", anchor="mt")
    
    # Legend in top-right corner (inside header area)
    legend_x = SLIDE_WIDTH - 200
    legend_y = table_start_y + 8
    legend_font = get_font(11, bold=True)
    draw.text((legend_x, legend_y), "≥80%", font=legend_font, fill=CELL_COLORS["green"])
    draw.text((legend_x + 50, legend_y), "70-79%", font=legend_font, fill=CELL_COLORS["yellow"])
    draw.text((legend_x + 115, legend_y), "<70%", font=legend_font, fill=CELL_COLORS["red"])
    
    # Draw employee rows
    data_start_y = table_start_y + header_height + 5
    current_tier = None
    
    for idx, emp in enumerate(sorted_employees):
        y = data_start_y + idx * row_height
        
        # Check if we've run out of space
        if y + row_height > SLIDE_HEIGHT - MARGIN_BOTTOM:
            draw.text((SLIDE_WIDTH // 2, y + 5), f"... and {num_employees - idx} more", 
                      font=font_cell, fill="#FFFFFF", anchor="mt")
            break
        
        tier = emp.get("tier_label", "C-Server")
        
        # Tier separator line (full width)
        if tier != current_tier:
            current_tier = tier
            if idx > 0:
                tier_line_color = TIER_COLORS.get(tier, "#666666")
                draw.line([(0, y - 2), (SLIDE_WIDTH, y - 2)], 
                         fill=hex_to_rgb(tier_line_color), width=2)
        
        # Alternating row background (full width)
        if idx % 2 == 0:
            draw.rectangle(
                [0, y - 1, SLIDE_WIDTH, y + row_height - 2],
                fill=(0, 0, 0, 40)
            )
        
        # Name column
        name = emp.get("name", "Unknown")
        max_name_len = int(col_widths[0] / (font_size_name * 0.6))
        if len(name) > max_name_len:
            name = name[:max_name_len - 2] + ".."
        draw.text((col_positions[0] + 8, y + row_height // 2),
                  name, font=font_name, fill="#FFFFFF", anchor="lm")
        
        # Tier column (badge)
        tier_color = TIER_COLORS.get(tier, "#666666")
        tier_short = {"Trainer": "TRN", "Bartender": "BAR", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, tier)
        
        badge_center_x = col_positions[1] + col_widths[1] // 2
        badge_y = y + 3
        badge_w = min(50, col_widths[1] - 10)
        badge_h = row_height - 8
        
        draw.rounded_rectangle(
            [badge_center_x - badge_w // 2, badge_y, badge_center_x + badge_w // 2, badge_y + badge_h],
            radius=badge_h // 2, 
            fill=hex_to_rgb(tier_color)
        )
        draw.text((badge_center_x, badge_y + badge_h // 2),
                  tier_short, font=font_tier, fill="#FFFFFF", anchor="mm")
        
        # Metric columns - all use pre-calculated normalized scores (0-100+ scale)
        for i, col in enumerate(columns[2:], start=2):
            metric_key = col.get("key")
            
            if metric_key:
                # Get pre-calculated score (already a percentage)
                percentage = emp.get(metric_key, 0) or 0
                
                # Get cell color based on percentage
                cell_color = get_cell_color(percentage)
                
                # Draw colored cell background (edge-to-edge within column)
                cell_x = col_positions[i] + 2
                cell_y = y + 2
                cell_w = col_widths[i] - 4
                cell_h = row_height - 6
                
                draw.rounded_rectangle(
                    [cell_x, cell_y, cell_x + cell_w, cell_y + cell_h],
                    radius=3,
                    fill=hex_to_rgb(cell_color)
                )
                
                # Draw percentage text
                pct_text = f"{percentage:.0f}%"
                draw.text((cell_x + cell_w // 2, cell_y + cell_h // 2),
                          pct_text, font=font_cell, fill="#FFFFFF", anchor="mm")
    
    # Footer (edge-to-edge)
    font_footer = get_font(13)
    footer_y = SLIDE_HEIGHT - 25
    
    # Footer background
    draw.rectangle([0, footer_y - 8, SLIDE_WIDTH, SLIDE_HEIGHT], fill=(10, 20, 40))
    
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y %H:%M')} • Benchmarks: PPA ${benchmarks.get('ppa_benchmark', 0):.0f}, LBW ${benchmarks.get('lbw_benchmark', 0):.2f}/guest, Glass ${benchmarks.get('glassware_benchmark', 0):.2f}/guest, LSC {benchmarks.get('lsc_benchmark', 0):.0f} guests"
    draw.text((SLIDE_WIDTH // 2, footer_y + 5), footer_text, 
              font=font_footer, fill="#AAAAAA", anchor="mm")
    
    # Save to bytes
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
