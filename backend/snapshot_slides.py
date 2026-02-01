"""
Snapshot Slide Generator - MARKETING STYLE
Vibrant, designer marketing aesthetic
16:9 format (1920x1080) for TV display
Features: Logo integration, modern fonts, bold colors
"""
import io
import os
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

# Background themes (exported for API)
BACKGROUNDS = {
    "midnight_blue": {"name": "Midnight Blue"},
    "ocean_blue": {"name": "Ocean Blue"},
    "bubba_red": {"name": "Bubba Red"},
}

# Vibrant performance colors
PERF_COLORS = {
    "exceeding": (0, 150, 255),       # Bright blue
    "meeting": (0, 200, 100),          # Vibrant green
    "progress": (255, 180, 0),         # Golden yellow
    "improvement": (255, 60, 60),      # Bright red
}

COLORS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "dark_bg": (12, 25, 47),
    "accent_red": (220, 50, 50),
    "accent_blue": (30, 144, 255),
    "light_text": (230, 230, 240),
    "gold": (255, 200, 50),
}


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get best available font - prefer bold/impact styles for marketing look."""
    if bold:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()


def get_perf_color(value: float) -> Tuple[int, int, int]:
    """Get vibrant performance color."""
    if value >= 100:
        return PERF_COLORS["exceeding"]
    elif value >= 80:
        return PERF_COLORS["meeting"]
    elif value >= 70:
        return PERF_COLORS["progress"]
    else:
        return PERF_COLORS["improvement"]


def create_gradient_bg(width: int, height: int) -> Image.Image:
    """Create vibrant gradient background."""
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    
    # Rich navy to deep blue gradient
    for y in range(height):
        ratio = y / height
        r = int(8 + ratio * 15)
        g = int(20 + ratio * 30)
        b = int(45 + ratio * 35)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    return img


def add_decorative_elements(img: Image.Image, draw: ImageDraw.Draw):
    """Add subtle decorative elements for visual interest."""
    width, height = img.size
    
    # Subtle diagonal lines
    for i in range(-height, width, 150):
        color = (255, 255, 255, 8)
        draw.line([(i, height), (i + height, 0)], fill=(30, 50, 70), width=1)
    
    # Corner accent
    draw.polygon([(0, 0), (200, 0), (0, 200)], fill=(220, 50, 50, 30))
    draw.polygon([(width, height), (width-150, height), (width, height-150)], fill=(30, 100, 200, 30))


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "midnight_blue",
    title: str = None
) -> bytes:
    """
    Generate a marketing-style snapshot slide.
    Vibrant colors, logo integration, modern design.
    """
    # Create gradient background
    img = create_gradient_bg(SLIDE_WIDTH, SLIDE_HEIGHT)
    draw = ImageDraw.Draw(img)
    
    # Add decorative elements
    add_decorative_elements(img, draw)
    
    # Try to load and place logo
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    logo_size = 180
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            # Resize maintaining aspect ratio
            logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
            # Place logo in top-left
            img.paste(logo, (25, 20), logo)
        except Exception as e:
            print(f"Could not load logo: {e}")
    
    # Sort employees
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_employees = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    num_employees = len(sorted_employees)
    
    # ===== HEADER AREA =====
    # Title - bold marketing style
    title_x = 230
    title_font_large = get_font(48, bold=True)
    title_font_med = get_font(36, bold=True)
    
    draw.text((title_x, 35), "TEAM PERFORMANCE", font=title_font_large, fill=COLORS["white"])
    draw.text((title_x, 90), "SNAPSHOT", font=title_font_large, fill=COLORS["gold"])
    
    # Date with style
    date_font = get_font(24, bold=True)
    draw.text((title_x, 145), snapshot_date, font=date_font, fill=COLORS["accent_blue"])
    
    # Legend - horizontal, top right
    legend_x = SLIDE_WIDTH - 650
    legend_y = 50
    legend_font = get_font(14, bold=True)
    
    legend_items = [
        (PERF_COLORS["exceeding"], "≥100%"),
        (PERF_COLORS["meeting"], "80-99%"),
        (PERF_COLORS["progress"], "70-79%"),
        (PERF_COLORS["improvement"], "<70%"),
    ]
    
    for i, (color, label) in enumerate(legend_items):
        x = legend_x + i * 150
        draw.rounded_rectangle([x, legend_y, x + 30, legend_y + 25], radius=4, fill=color)
        draw.text((x + 38, legend_y + 3), label, font=legend_font, fill=COLORS["white"])
    
    # CV legend
    cv_y = legend_y + 40
    draw.text((legend_x, cv_y), "CV:", font=legend_font, fill=COLORS["light_text"])
    draw.rounded_rectangle([legend_x + 35, cv_y - 2, legend_x + 60, cv_y + 20], radius=3, fill=PERF_COLORS["meeting"])
    draw.text((legend_x + 68, cv_y), "+", font=legend_font, fill=COLORS["white"])
    draw.rounded_rectangle([legend_x + 100, cv_y - 2, legend_x + 125, cv_y + 20], radius=3, fill=PERF_COLORS["improvement"])
    draw.text((legend_x + 133, cv_y), "0/-", font=legend_font, fill=COLORS["white"])
    
    # ===== DATA TABLE =====
    table_top = 190
    table_left = 30
    table_right = SLIDE_WIDTH - 30
    table_width = table_right - table_left
    
    # Calculate row height
    header_height = 45
    available_height = SLIDE_HEIGHT - table_top - 50
    row_height = (available_height - header_height) // max(num_employees, 1)
    row_height = max(26, min(38, row_height))
    
    # Font sizes based on row height
    if row_height >= 34:
        name_size, val_size, rank_size = 17, 16, 15
    elif row_height >= 30:
        name_size, val_size, rank_size = 15, 14, 13
    else:
        name_size, val_size, rank_size = 13, 12, 11
    
    # Columns
    columns = [
        {"name": "RANK", "pct": 5},
        {"name": "EMPLOYEE", "pct": 14},
        {"name": "PPA", "pct": 13, "key": "score_ppa"},
        {"name": "LBW", "pct": 13, "key": "score_lbw"},
        {"name": "GLASS", "pct": 13, "key": "score_glass"},
        {"name": "LSC", "pct": 13, "key": "score_lsc"},
        {"name": "CV", "pct": 10, "key": "cv_score", "is_binary": True},
        {"name": "TOTAL", "pct": 19, "key": "total_score"},
    ]
    
    col_widths = [int(c["pct"] / 100 * table_width) for c in columns]
    col_widths[-1] += table_width - sum(col_widths)
    
    col_positions = []
    x = table_left
    for w in col_widths:
        col_positions.append(x)
        x += w
    
    # Header row - vibrant red
    draw.rounded_rectangle(
        [table_left, table_top, table_right, table_top + header_height],
        radius=8, fill=COLORS["accent_red"]
    )
    
    header_font = get_font(18, bold=True)
    for i, col in enumerate(columns):
        cx = col_positions[i] + col_widths[i] // 2
        draw.text((cx, table_top + header_height // 2), col["name"],
                  font=header_font, fill=COLORS["white"], anchor="mm")
    
    # Data rows
    data_start = table_top + header_height + 3
    name_font = get_font(name_size, bold=True)
    val_font = get_font(val_size, bold=True)
    rank_font = get_font(rank_size, bold=True)
    
    tier_counts = {}
    
    for idx, emp in enumerate(sorted_employees):
        y = data_start + idx * row_height
        
        if y + row_height > SLIDE_HEIGHT - 40:
            # Show overflow
            overflow_font = get_font(16, bold=True)
            draw.text((SLIDE_WIDTH // 2, SLIDE_HEIGHT - 25),
                      f"+ {num_employees - idx} more", font=overflow_font,
                      fill=COLORS["gold"], anchor="mm")
            break
        
        tier = emp.get("tier_label", "C-Server")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        # Row background - alternating with subtle gradient effect
        if idx % 2 == 0:
            row_color = (20, 40, 65)
        else:
            row_color = (15, 30, 55)
        
        draw.rounded_rectangle(
            [table_left, y, table_right, y + row_height - 2],
            radius=4, fill=row_color
        )
        
        # Tier color accent on left
        tier_colors = {
            "Trainer": (168, 85, 247),
            "Bartender": (59, 130, 246),
            "A-Server": (34, 197, 94),
            "B-Server": (234, 179, 8),
            "C-Server": (239, 68, 68),
        }
        tier_color = tier_colors.get(tier, (100, 100, 100))
        draw.rectangle([table_left, y, table_left + 5, y + row_height - 2], fill=tier_color)
        
        row_cy = y + row_height // 2
        
        # Rank
        tier_prefix = {"Trainer": "T", "Bartender": "Bar", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "?")
        rank_text = f"{tier_prefix}{tier_counts[tier]}"
        draw.text((col_positions[0] + col_widths[0] // 2, row_cy), rank_text,
                  font=rank_font, fill=tier_color, anchor="mm")
        
        # Name
        name = emp.get("name", "Unknown")
        max_chars = col_widths[1] // (name_size * 0.55)
        if len(name) > max_chars:
            name = name[:int(max_chars) - 1] + "…"
        draw.text((col_positions[1] + 10, row_cy), name,
                  font=name_font, fill=COLORS["white"], anchor="lm")
        
        # Metrics
        for i, col in enumerate(columns[2:], start=2):
            key = col.get("key")
            if not key:
                continue
            
            value = emp.get(key, 0) or 0
            is_binary = col.get("is_binary", False)
            
            cell_x = col_positions[i] + 4
            cell_w = col_widths[i] - 8
            cell_h = row_height - 8
            cell_y = y + 4
            
            if is_binary:
                cell_color = PERF_COLORS["meeting"] if value > 0 else PERF_COLORS["improvement"]
                text = f"+{int(value)}" if value > 0 else str(int(value))
            else:
                cell_color = get_perf_color(value)
                text = f"{value:.0f}%"
            
            draw.rounded_rectangle(
                [cell_x, cell_y, cell_x + cell_w, cell_y + cell_h],
                radius=5, fill=cell_color
            )
            draw.text((cell_x + cell_w // 2, row_cy), text,
                      font=val_font, fill=COLORS["white"], anchor="mm")
    
    # Footer
    footer_font = get_font(14, bold=True)
    draw.text((table_left, SLIDE_HEIGHT - 30), f"{num_employees} employees",
              font=footer_font, fill=COLORS["light_text"])
    draw.text((table_right, SLIDE_HEIGHT - 30), f"Generated {datetime.now().strftime('%m/%d/%Y')}",
              font=footer_font, fill=COLORS["light_text"], anchor="ra")
    
    # Save
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def get_available_backgrounds() -> List[Dict[str, str]]:
    return [{"key": k, "name": v["name"]} for k, v in BACKGROUNDS.items()]
