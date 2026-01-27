"""
Snapshot Slide Generator
Generates bi-weekly team snapshot slides (1920x1080 PNG)
All employees on one page with conditional formatting
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
    """Create a fun background."""
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
                # First to second color
                r = ratio * 2
                c1, c2 = colors[0], colors[1] if len(colors) > 1 else colors[0]
            else:
                # Second to third color
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
                # Add wave effect
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
        
        # Add neon glow lines
        accent = colors[2] if len(colors) > 2 else colors[0]
        for i in range(0, width, 200):
            for y in range(height):
                alpha = int(50 * (1 - abs(y - height/2) / (height/2)))
                if alpha > 0:
                    glow_color = tuple(min(255, base_color[j] + accent[j] * alpha // 255) for j in range(3))
                    draw.point((i + int(30 * math.sin(y / 30)), y), fill=glow_color)
    
    # Add subtle pattern overlay
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            if (x + y) % 8 == 0:
                current = img.getpixel((x, y))
                darker = tuple(max(0, c - 5) for c in current)
                draw.point((x, y), fill=darker)
    
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
    
    Args:
        employees: List of employee data with metrics
        benchmarks: Dict of metric benchmarks {ppa: 55, lbw_per_guest: 6.5, ...}
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
    
    # Calculate layout
    num_employees = len(sorted_employees)
    
    # Dynamic font sizing based on employee count
    if num_employees <= 15:
        font_size_name = 22
        font_size_cell = 20
        row_height = 50
    elif num_employees <= 25:
        font_size_name = 18
        font_size_cell = 16
        row_height = 38
    elif num_employees <= 35:
        font_size_name = 15
        font_size_cell = 14
        row_height = 30
    else:
        font_size_name = 12
        font_size_cell = 11
        row_height = 24
    
    # Fonts
    font_title = get_font(42, bold=True)
    font_subtitle = get_font(22)
    font_header = get_font(font_size_cell + 4, bold=True)
    font_name = get_font(font_size_name, bold=True)
    font_cell = get_font(font_size_cell)
    font_tier = get_font(font_size_cell - 2, bold=True)
    font_subheader = get_font(12)
    
    # Header
    title_text = title or "TEAM SNAPSHOT"
    draw.text((SLIDE_WIDTH//2, 25), title_text, font=font_title, fill="#FFFFFF", anchor="mt")
    draw.text((SLIDE_WIDTH//2, 72), f"📊 {snapshot_date} • Bubba Gump Shrimp Co.", 
              font=font_subtitle, fill="#E0E0E0", anchor="mt")
    
    # Grid layout
    margin_left = 50
    margin_right = 50
    margin_top = 115
    
    # Column definitions with full names and short names
    columns = [
        {"name": "Employee", "short": "Name", "width": 200, "key": None, "desc": ""},
        {"name": "Tier", "short": "Tier", "width": 80, "key": None, "desc": ""},
        {"name": "PPA", "short": "$/Guest", "width": 85, "key": "ppa", "benchmark_key": "ppa_benchmark", "desc": "Per Person Avg"},
        {"name": "LBW", "short": "$/Guest", "width": 85, "key": "lbw_per_guest", "benchmark_key": "lbw_benchmark", "desc": "Liquor Beer Wine"},
        {"name": "Glass", "short": "$/Guest", "width": 85, "key": "glassware_per_guest", "benchmark_key": "glassware_benchmark", "desc": "Glassware Sales"},
        {"name": "LSC", "short": "Guests", "width": 85, "key": "guests_per_lsc", "benchmark_key": "lsc_benchmark", "inverse": True, "desc": "Landshark Calls"},
        {"name": "CV", "short": "Score", "width": 75, "key": "cv_score", "benchmark_key": "cv_benchmark", "desc": "Customer Voice"},
        {"name": "TOTAL", "short": "Score", "width": 85, "key": "total_score", "benchmark_key": "total_benchmark", "desc": "Overall"},
    ]
    
    # Calculate column positions
    total_width = sum(c["width"] for c in columns)
    start_x = (SLIDE_WIDTH - total_width) // 2
    
    col_positions = []
    x = start_x
    for col in columns:
        col_positions.append(x)
        x += col["width"]
    
    # Draw header row with two lines (name + description)
    header_y = margin_top
    header_height = row_height + 15
    
    # Header background - darker and more prominent
    draw.rounded_rectangle(
        [start_x - 10, header_y - 8, start_x + total_width + 10, header_y + header_height],
        radius=10,
        fill=(0, 0, 0, 120)
    )
    
    # Draw column headers
    for i, col in enumerate(columns):
        center_x = col_positions[i] + col["width"]//2
        # Main header name
        draw.text((center_x, header_y + 8), col["name"], font=font_header, fill="#FFFFFF", anchor="mt")
        # Sub-description if exists
        if col.get("short") and col["name"] not in ["Employee", "Tier"]:
            draw.text((center_x, header_y + 30), col["short"], font=font_subheader, fill="#AAAAAA", anchor="mt")
    
    # Draw legend - moved to top right
    legend_y = header_y + 5
    legend_x = SLIDE_WIDTH - 280
    draw.text((legend_x, legend_y), "Legend:", font=get_font(14, bold=True), fill="#FFFFFF")
    legend_y += 18
    legend_items = [("🟢 ≥80%", CELL_COLORS["green"]), ("🟡 70-79%", CELL_COLORS["yellow"]), ("🔴 <70%", CELL_COLORS["red"])]
    for text, color in legend_items:
        draw.text((legend_x, legend_y), text, font=get_font(13), fill=color)
        legend_y += 16
    
    # Draw employee rows
    data_start_y = header_y + header_height + 8
    current_tier = None
    
    for idx, emp in enumerate(sorted_employees):
        y = data_start_y + idx * row_height
        
        # Check if we've run out of space
        if y + row_height > SLIDE_HEIGHT - 40:
            # Draw overflow indicator
            draw.text((SLIDE_WIDTH//2, y + 10), f"... and {num_employees - idx} more", 
                      font=font_cell, fill="#FFFFFF", anchor="mt")
            break
        
        tier = emp.get("tier_label", "C-Server")
        
        # Tier separator line
        if tier != current_tier:
            current_tier = tier
            if idx > 0:
                draw.line([(start_x, y - 3), (start_x + total_width, y - 3)], 
                         fill=TIER_COLORS.get(tier, "#666666"), width=2)
        
        # Alternating row background
        if idx % 2 == 0:
            draw.rounded_rectangle(
                [start_x - 5, y - 2, start_x + total_width + 5, y + row_height - 4],
                radius=4,
                fill=(0, 0, 0, 60)
            )
        
        # Name column
        name = emp.get("name", "Unknown")
        if len(name) > 18:
            name = name[:16] + "..."
        draw.text((col_positions[0] + 5, y + row_height//2 - font_size_name//2 - 2),
                  name, font=font_name, fill="#FFFFFF")
        
        # Tier column (with color)
        tier_color = TIER_COLORS.get(tier, "#666666")
        tier_short = {"Trainer": "TRN", "Bartender": "BAR", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, tier)
        
        # Tier badge
        badge_x = col_positions[1] + 10
        badge_y = y + 3
        badge_w = 50
        badge_h = row_height - 8
        draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
                              radius=badge_h//2, fill=hex_to_rgb(tier_color))
        draw.text((badge_x + badge_w//2, badge_y + badge_h//2 - 2),
                  tier_short, font=font_tier, fill="#FFFFFF", anchor="mm")
        
        # Metric columns
        for i, col in enumerate(columns[2:], start=2):
            metric_key = col.get("key")
            benchmark_key = col.get("benchmark_key")
            is_inverse = col.get("inverse", False)
            
            if metric_key and benchmark_key:
                value = emp.get(metric_key, 0) or 0
                benchmark = benchmarks.get(benchmark_key, 0)
                
                if is_inverse and benchmark > 0:
                    # For LSC, lower is better (fewer guests per LSC = more LSCs)
                    percentage = (benchmark / value * 100) if value > 0 else 0
                else:
                    percentage = calculate_percentage(value, benchmark)
                
                # Get cell color
                cell_color = get_cell_color(percentage)
                
                # Draw colored cell background
                cell_x = col_positions[i]
                cell_y = y + 2
                cell_w = col["width"] - 4
                cell_h = row_height - 6
                
                draw.rounded_rectangle(
                    [cell_x + 2, cell_y, cell_x + cell_w, cell_y + cell_h],
                    radius=4,
                    fill=hex_to_rgb(cell_color)
                )
                
                # Draw percentage text
                pct_text = f"{percentage:.0f}%"
                draw.text((cell_x + cell_w//2, cell_y + cell_h//2 - 2),
                          pct_text, font=font_cell, fill="#FFFFFF", anchor="mm")
    
    # Footer
    font_footer = get_font(16)
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y %H:%M')} • Benchmarks: PPA ${benchmarks.get('ppa_benchmark', 0):.0f}, LBW ${benchmarks.get('lbw_benchmark', 0):.2f}/guest"
    draw.text((SLIDE_WIDTH//2, SLIDE_HEIGHT - 25), footer_text, 
              font=font_footer, fill="#AAAAAA", anchor="mt")
    
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
