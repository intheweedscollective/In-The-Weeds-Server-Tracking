"""
Yodeck Slide Generator v3.0
Generates 16:9 (1920x1080) PNG slides for digital signage.
Bubba Gump Brand + Sports Leaderboard Style
- Vibrant red/blue colors with tropical accents
- ESPN-style rankings with dynamic energy
- Geometric patterns, glow effects, card-based layouts
"""
import io
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime, date
import base64
import math
import random

# ============================================================================
# DESIGN CONSTANTS
# ============================================================================

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

# Premium themes - Bubba Gump Brand + Sports Energy
THEMES = {
    "dark_navy": {
        "background": "#0A1628",
        "background_gradient": "#1A2744",
        "card_bg": "#1E3A5F",
        "primary": "#FF4757",
        "secondary": "#3742FA",
        "accent": "#FFA502",
        "text_white": "#FFFFFF",
        "text_light": "#E8EEF7",
        "text_muted": "#8899AA",
        "gold": "#FFD700",
        "silver": "#C0C0C0",
        "bronze": "#CD7F32",
        "glow": "#00D9FF",
    },
    "bubba_gump": {
        "background": "#0D1B2A",
        "background_gradient": "#1B263B",
        "card_bg": "#1B3A4B",
        "primary": "#E63946",      # Bubba Gump Red
        "secondary": "#1D8CC7",    # Ocean Blue
        "accent": "#F4A261",       # Tropical Orange
        "tropical": "#2A9D8F",     # Teal accent
        "text_white": "#FFFFFF",
        "text_light": "#E8EEF7",
        "text_muted": "#778DA9",
        "gold": "#FFD700",
        "silver": "#B8C5D6",
        "bronze": "#E76F51",
        "glow": "#00D4FF",
    },
    "light_corporate": {
        "background": "#F0F4F8",
        "background_gradient": "#E2E8F0",
        "card_bg": "#FFFFFF",
        "primary": "#E53E3E",
        "secondary": "#3182CE",
        "accent": "#DD6B20",
        "text_white": "#1A202C",
        "text_light": "#2D3748",
        "text_muted": "#718096",
        "gold": "#D69E2E",
        "silver": "#718096",
        "bronze": "#C05621",
        "glow": "#4299E1",
    },
    "bubba_red": {
        "background": "#450A0A",
        "background_gradient": "#7F1D1D",
        "card_bg": "#991B1B",
        "primary": "#FEF2F2",
        "secondary": "#FCA5A5",
        "accent": "#FCD34D",
        "text_white": "#FFFFFF",
        "text_light": "#FEE2E2",
        "text_muted": "#FECACA",
        "gold": "#FFD700",
        "silver": "#E5E7EB",
        "bronze": "#F59E0B",
        "glow": "#FF6B6B",
    },
    "ocean_blue": {
        "background": "#082F49",
        "background_gradient": "#0C4A6E",
        "card_bg": "#0369A1",
        "primary": "#F0F9FF",
        "secondary": "#38BDF8",
        "accent": "#FB923C",
        "text_white": "#FFFFFF",
        "text_light": "#E0F2FE",
        "text_muted": "#BAE6FD",
        "gold": "#FCD34D",
        "silver": "#E5E7EB",
        "bronze": "#FB923C",
        "glow": "#22D3EE",
    },
    "vegas_gold": {
        "background": "#1A1A2E",
        "background_gradient": "#16213E",
        "card_bg": "#0F3460",
        "primary": "#FFD700",
        "secondary": "#E94560",
        "accent": "#00FFF5",
        "text_white": "#FFFFFF",
        "text_light": "#F5F5F5",
        "text_muted": "#AAAAAA",
        "gold": "#FFD700",
        "silver": "#C0C0C0",
        "bronze": "#CD7F32",
        "glow": "#FFD700",
    },
}

# Seasonal themes (keeping existing)
SEASONAL_THEMES = {
    "valentines": {
        "name": "Valentine's Day",
        "background": "#4A0D2A",
        "background_gradient": "#2D0519",
        "card_bg": "#6B1E4A",
        "primary": "#FF6B9D",
        "secondary": "#FF1493",
        "accent": "#FFB6C1",
        "text_white": "#FFFFFF",
        "text_light": "#FFE4EC",
        "text_muted": "#FFB6C1",
        "gold": "#FFD700",
        "silver": "#FFC0CB",
        "bronze": "#FF69B4",
        "glow": "#FF1493",
        "emoji": "💕",
        "decorations": ["heart"],
    },
    "st_patricks": {
        "name": "St. Patrick's Day",
        "background": "#0D3B0D",
        "background_gradient": "#1A5C1A",
        "card_bg": "#228B22",
        "primary": "#00FF7F",
        "secondary": "#32CD32",
        "accent": "#FFD700",
        "text_white": "#FFFFFF",
        "text_light": "#E8F5E9",
        "text_muted": "#A5D6A7",
        "gold": "#FFD700",
        "silver": "#98FB98",
        "bronze": "#228B22",
        "glow": "#00FF7F",
        "emoji": "🍀",
        "decorations": ["shamrock"],
    },
    "christmas": {
        "name": "Christmas",
        "background": "#0D2818",
        "background_gradient": "#1A4D2E",
        "card_bg": "#2D5A3D",
        "primary": "#FF0000",
        "secondary": "#228B22",
        "accent": "#FFD700",
        "text_white": "#FFFFFF",
        "text_light": "#E8F5E9",
        "text_muted": "#C8E6C9",
        "gold": "#FFD700",
        "silver": "#C0C0C0",
        "bronze": "#CD7F32",
        "glow": "#FF0000",
        "emoji": "🎄",
        "decorations": ["snowflake", "tree"],
    },
    "halloween": {
        "name": "Halloween",
        "background": "#1A0A00",
        "background_gradient": "#2D1500",
        "card_bg": "#4A2500",
        "primary": "#FF6600",
        "secondary": "#9C27B0",
        "accent": "#FFD700",
        "text_white": "#FFFFFF",
        "text_light": "#FFE0B2",
        "text_muted": "#FFCC80",
        "gold": "#FFD700",
        "silver": "#E0E0E0",
        "bronze": "#FF9800",
        "glow": "#FF6600",
        "emoji": "🎃",
        "decorations": ["pumpkin"],
    },
    "july_4th": {
        "name": "4th of July",
        "background": "#0A1628",
        "background_gradient": "#1A237E",
        "card_bg": "#283593",
        "primary": "#F44336",
        "secondary": "#2196F3",
        "accent": "#FFFFFF",
        "text_white": "#FFFFFF",
        "text_light": "#E3F2FD",
        "text_muted": "#BBDEFB",
        "gold": "#FFD700",
        "silver": "#E0E0E0",
        "bronze": "#FF5722",
        "glow": "#F44336",
        "emoji": "🇺🇸",
        "decorations": ["star", "firework"],
    },
    "new_year": {
        "name": "New Year",
        "background": "#0A0A1A",
        "background_gradient": "#1A1A3A",
        "card_bg": "#2A2A5A",
        "primary": "#FFD700",
        "secondary": "#C0C0C0",
        "accent": "#00FFFF",
        "text_white": "#FFFFFF",
        "text_light": "#FFF9C4",
        "text_muted": "#FFF59D",
        "gold": "#FFD700",
        "silver": "#E0E0E0",
        "bronze": "#FF8F00",
        "glow": "#FFD700",
        "emoji": "🎆",
        "decorations": ["firework", "confetti"],
    },
    "thanksgiving": {
        "name": "Thanksgiving",
        "background": "#3E2723",
        "background_gradient": "#5D4037",
        "card_bg": "#6D4C41",
        "primary": "#FF8F00",
        "secondary": "#8D6E63",
        "accent": "#FFD700",
        "text_white": "#FFFFFF",
        "text_light": "#FFF3E0",
        "text_muted": "#FFE0B2",
        "gold": "#FFD700",
        "silver": "#BCAAA4",
        "bronze": "#A1887F",
        "glow": "#FF8F00",
        "emoji": "🦃",
        "decorations": ["leaf"],
    },
    "easter": {
        "name": "Easter",
        "background": "#E8E4F0",
        "background_gradient": "#D4C8E8",
        "card_bg": "#C8B8E0",
        "primary": "#9C27B0",
        "secondary": "#FF9800",
        "accent": "#4CAF50",
        "text_white": "#4A148C",
        "text_light": "#6A1B9A",
        "text_muted": "#7B1FA2",
        "gold": "#FFD54F",
        "silver": "#CE93D8",
        "bronze": "#FF7043",
        "glow": "#9C27B0",
        "emoji": "🐣",
        "decorations": ["egg"],
    },
}

# Holiday dates
HOLIDAY_DATES = {
    "new_year": [(1, 1, 7)],
    "valentines": [(2, 7, 14)],
    "st_patricks": [(3, 10, 17)],
    "easter": [(3, 25, 31), (4, 1, 21)],
    "july_4th": [(6, 28, 30), (7, 1, 7)],
    "halloween": [(10, 24, 31)],
    "thanksgiving": [(11, 18, 28)],
    "christmas": [(12, 15, 31)],
}

# Tier colors
TIER_CONFIG = {
    "Trainer": {"color": "#A855F7", "bg": "#581C87", "short": "T", "icon": "👑"},
    "Bartender": {"color": "#3B82F6", "bg": "#1E3A8A", "short": "BAR", "icon": "🍸"},
    "A-Server": {"color": "#22C55E", "bg": "#14532D", "short": "A", "icon": "⭐"},
    "B-Server": {"color": "#EAB308", "bg": "#713F12", "short": "B", "icon": "📈"},
    "C-Server": {"color": "#EF4444", "bg": "#7F1D1D", "short": "C", "icon": "💪"},
}


def get_current_seasonal_theme() -> Optional[str]:
    """Auto-detect current seasonal theme based on date."""
    today = date.today()
    for theme_key, date_ranges in HOLIDAY_DATES.items():
        for (m, start_day, end_day) in date_ranges:
            if today.month == m and start_day <= today.day <= end_day:
                return theme_key
    return None


def get_theme_colors(theme_name: str = "dark_navy", custom_colors: Dict = None, seasonal_override: str = None) -> Dict:
    """Get colors for a theme."""
    if seasonal_override and seasonal_override not in ["auto", "none"] and seasonal_override in SEASONAL_THEMES:
        return SEASONAL_THEMES[seasonal_override].copy()
    
    if seasonal_override == "auto":
        auto_theme = get_current_seasonal_theme()
        if auto_theme:
            return SEASONAL_THEMES[auto_theme].copy()
    
    if theme_name == "custom" and custom_colors:
        base = THEMES["dark_navy"].copy()
        base.update(custom_colors)
        return base
    
    return THEMES.get(theme_name, THEMES["dark_navy"]).copy()


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


def create_gradient_background(width: int, height: int, colors: Dict) -> Image.Image:
    """Create a rich gradient background with subtle pattern."""
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    
    top_color = hex_to_rgb(colors.get("background", "#0A1628"))
    bottom_color = hex_to_rgb(colors.get("background_gradient", "#1A2744"))
    
    # Vertical gradient
    for y in range(height):
        ratio = y / height
        # Add slight curve to gradient
        ratio = ratio ** 0.8
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # Add subtle diagonal pattern
    pattern_color = hex_to_rgb(colors.get("card_bg", "#1E3A5F"))
    for i in range(-height, width + height, 80):
        draw.line([(i, 0), (i + height, height)], fill=pattern_color + (15,), width=1)
    
    return img


def draw_glow_circle(img: Image.Image, x: int, y: int, radius: int, color: tuple, intensity: int = 50):
    """Draw a glowing circle effect."""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Multiple layers for glow effect
    for i in range(5, 0, -1):
        r = radius + i * 10
        alpha = intensity // i
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color + (alpha,))
    
    img = img.convert('RGBA')
    return Image.alpha_composite(img, overlay).convert('RGB')


def draw_card(draw: ImageDraw.Draw, bbox: Tuple[int, int, int, int], colors: Dict, highlight: bool = False):
    """Draw a modern card with optional highlight."""
    x1, y1, x2, y2 = bbox
    card_color = hex_to_rgb(colors.get("card_bg", "#1E3A5F"))
    
    if highlight:
        # Highlighted card has brighter background
        card_color = tuple(min(c + 30, 255) for c in card_color)
    
    # Draw rounded rectangle
    draw.rounded_rectangle(bbox, radius=16, fill=card_color)
    
    # Add subtle border
    border_color = hex_to_rgb(colors.get("secondary", "#3742FA"))
    if highlight:
        draw.rounded_rectangle(bbox, radius=16, outline=border_color + (100,), width=2)


def draw_medal(draw: ImageDraw.Draw, x: int, y: int, rank: int, colors: Dict, size: int = 60):
    """Draw a stylish medal for top 3."""
    if rank == 1:
        medal_color = colors["gold"]
        inner_color = "#FFE55C"
        icon = "🥇"
    elif rank == 2:
        medal_color = colors["silver"]
        inner_color = "#E8E8E8"
        icon = "🥈"
    elif rank == 3:
        medal_color = colors["bronze"]
        inner_color = "#E8A45C"
        icon = "🥉"
    else:
        return
    
    # Outer circle
    draw.ellipse([x - size//2, y - size//2, x + size//2, y + size//2], 
                 fill=hex_to_rgb(medal_color))
    # Inner circle
    draw.ellipse([x - size//3, y - size//3, x + size//3, y + size//3], 
                 fill=hex_to_rgb(inner_color))
    
    # Rank number
    font = get_font(size//2, bold=True)
    draw.text((x - size//6, y - size//4), str(rank), font=font, fill="#1A1A2E", anchor="lt")


def draw_tier_badge(draw: ImageDraw.Draw, x: int, y: int, tier: str, size: str = "normal"):
    """Draw a stylish tier badge."""
    config = TIER_CONFIG.get(tier, TIER_CONFIG["A-Server"])
    
    font_size = 24 if size == "normal" else 20
    font = get_font(font_size, bold=True)
    
    # Badge dimensions
    padding = 16 if size == "normal" else 12
    text_bbox = draw.textbbox((0, 0), tier, font=font)
    badge_width = text_bbox[2] - text_bbox[0] + padding * 2
    badge_height = text_bbox[3] - text_bbox[1] + padding
    
    # Draw badge with gradient effect
    bg_color = hex_to_rgb(config["bg"])
    border_color = hex_to_rgb(config["color"])
    
    draw.rounded_rectangle(
        [x, y, x + badge_width, y + badge_height],
        radius=badge_height // 2,
        fill=bg_color,
        outline=border_color,
        width=2
    )
    
    # Text
    draw.text((x + padding, y + padding//2 - 2), tier, font=font, fill=config["color"])
    
    return badge_width


def draw_score_bar(draw: ImageDraw.Draw, x: int, y: int, width: int, score: float, max_score: float, colors: Dict):
    """Draw a visual score bar."""
    bar_height = 8
    fill_width = int((score / max_score) * width) if max_score > 0 else 0
    
    # Background bar
    draw.rounded_rectangle([x, y, x + width, y + bar_height], radius=4, 
                          fill=hex_to_rgb(colors["text_muted"]) + (50,))
    
    # Fill bar with gradient effect
    if fill_width > 0:
        # Color based on score percentage
        pct = score / max_score if max_score > 0 else 0
        if pct >= 0.85:
            fill_color = hex_to_rgb(TIER_CONFIG["A-Server"]["color"])
        elif pct >= 0.70:
            fill_color = hex_to_rgb(TIER_CONFIG["B-Server"]["color"])
        else:
            fill_color = hex_to_rgb(TIER_CONFIG["C-Server"]["color"])
        
        draw.rounded_rectangle([x, y, x + fill_width, y + bar_height], radius=4, fill=fill_color)


def add_decorations(img: Image.Image, seasonal_theme: str, colors: Dict) -> Image.Image:
    """Add seasonal decorations."""
    if not seasonal_theme or seasonal_theme not in SEASONAL_THEMES:
        return img
    
    theme_info = SEASONAL_THEMES[seasonal_theme]
    decorations = theme_info.get("decorations", [])
    if not decorations:
        return img
    
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    random.seed(42)
    primary_rgb = hex_to_rgb(colors.get("primary", "#FF6B9D"))
    
    if "heart" in decorations:
        for _ in range(15):
            px, py = random.randint(50, 1870), random.choice([random.randint(50, 150), random.randint(930, 1030)])
            size = random.randint(15, 35)
            alpha = random.randint(30, 70)
            r = size // 3
            draw.ellipse([px - r, py - r, px + r, py + r], fill=primary_rgb + (alpha,))
            draw.ellipse([px + r - 2, py - r, px + 3*r - 2, py + r], fill=primary_rgb + (alpha,))
            draw.polygon([(px - r, py), (px + 3*r - 2, py), (px + r - 1, py + int(size * 0.9))], fill=primary_rgb + (alpha,))
    
    if "snowflake" in decorations:
        for _ in range(20):
            px, py = random.randint(50, 1870), random.choice([random.randint(50, 200), random.randint(880, 1030)])
            size = random.randint(12, 25)
            alpha = random.randint(40, 80)
            for angle in range(0, 360, 60):
                rad = math.radians(angle)
                x2, y2 = px + int(size * math.cos(rad)), py + int(size * math.sin(rad))
                draw.line([(px, py), (x2, y2)], fill=(255, 255, 255, alpha), width=2)
    
    if "star" in decorations:
        for _ in range(12):
            px, py = random.randint(50, 1870), random.choice([random.randint(50, 150), random.randint(930, 1030)])
            size = random.randint(10, 22)
            alpha = random.randint(50, 100)
            c = (255, 215, 0) if random.random() > 0.3 else (255, 255, 255)
            points = []
            for i in range(10):
                angle = math.radians(i * 36 - 90)
                r = size if i % 2 == 0 else size // 2
                points.append((px + int(r * math.cos(angle)), py + int(r * math.sin(angle))))
            draw.polygon(points, fill=c + (alpha,))
    
    if "firework" in decorations or "confetti" in decorations:
        for _ in range(40):
            px = random.randint(50, 1870)
            py = random.randint(50, 200) if random.random() > 0.5 else random.randint(880, 1030)
            size = random.randint(2, 8)
            alpha = random.randint(40, 100)
            c = random.choice([primary_rgb, hex_to_rgb(colors.get("secondary", "#C0C0C0")), (255, 215, 0), (255, 255, 255)])
            draw.ellipse([px - size, py - size, px + size, py + size], fill=c + (alpha,))
    
    img = img.convert('RGBA')
    return Image.alpha_composite(img, overlay).convert('RGB')


def generate_top_10_slide(
    rankings: List[Dict[str, Any]], 
    quarter: str, 
    year: int,
    theme: str = "dark_navy",
    custom_colors: Dict = None,
    custom_bg_image: str = None,
    seasonal_theme: str = None
) -> bytes:
    """Generate clean, professional Top 10 Performers slide without emoji dependencies."""
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors)
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_title = get_font(64, bold=True)
    font_subtitle = get_font(26)
    font_rank = get_font(36, bold=True)
    font_name = get_font(32, bold=True)
    font_score = get_font(38, bold=True)
    font_tier = get_font(18, bold=True)
    font_footer = get_font(18)
    
    # Header - clean text without emojis
    title = "TOP 10 PERFORMERS"
    draw.text((SLIDE_WIDTH//2 + 3, 38), title, font=font_title, fill=(0, 0, 0, 100), anchor="mt")
    draw.text((SLIDE_WIDTH//2, 35), title, font=font_title, fill=colors["primary"], anchor="mt")
    
    # Subtitle
    subtitle = f"{quarter} {year}  |  Bubba Gump Shrimp Co.  |  Las Vegas"
    draw.text((SLIDE_WIDTH//2, 110), subtitle, font=font_subtitle, fill=colors["text_muted"], anchor="mt")
    
    # Decorative line
    draw.line([(200, 150), (SLIDE_WIDTH - 200, 150)], fill=colors["secondary"], width=3)
    
    # Top 10 list
    start_y = 175
    row_height = 85
    left_margin = 100
    
    for idx, emp in enumerate(rankings[:10]):
        rank = idx + 1
        y = start_y + idx * row_height
        
        # Row background for top 3
        if rank <= 3:
            medal_colors = {1: colors["gold"], 2: colors["silver"], 3: colors["bronze"]}
            bg = hex_to_rgb(medal_colors[rank]) + (30,)
            draw.rounded_rectangle(
                [left_margin - 20, y - 5, SLIDE_WIDTH - left_margin + 20, y + row_height - 15],
                radius=8, fill=bg
            )
        
        # Rank medal/number
        if rank <= 3:
            # Draw medal circle
            medal_colors_map = {1: colors["gold"], 2: colors["silver"], 3: colors["bronze"]}
            medal_color = medal_colors_map[rank]
            cx, cy = left_margin + 30, y + 32
            draw.ellipse([cx - 25, cy - 25, cx + 25, cy + 25], fill=medal_color)
            draw.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=hex_to_rgb(medal_color))
            draw.text((cx, cy), str(rank), font=font_rank, fill="#1A1A2E", anchor="mm")
            name_x = left_margin + 80
        else:
            draw.text((left_margin + 10, y + 15), f"#{rank}", font=font_rank, fill=colors["text_muted"])
            name_x = left_margin + 80
        
        # Name - allow longer names since we have space
        name = emp.get("name", "Unknown")
        if len(name) > 24:
            name = name[:23] + ".."
        draw.text((name_x, y + 18), name, font=font_name, fill=colors["text_white"])
        
        # Tier badge
        tier = emp.get("tier_label", "A-Server")
        tier_colors = {"Trainer": "#A855F7", "Bartender": "#3B82F6", "A-Server": "#22C55E", "B-Server": "#EAB308", "C-Server": "#EF4444"}
        tier_color = tier_colors.get(tier, "#888888")
        
        tier_x = 620
        draw.rounded_rectangle([tier_x, y + 15, tier_x + 90, y + 50], radius=15, fill=tier_color)
        draw.text((tier_x + 45, y + 32), tier, font=font_tier, fill="#FFFFFF", anchor="mm")
        
        # Score
        score = emp.get("total_score", 0)
        score_text = f"{score:.1f}"
        score_color = colors["gold"] if rank <= 3 else colors["text_white"]
        
        # Score bar background
        bar_x = SLIDE_WIDTH - 380
        bar_y = y + 42
        bar_width = 180
        bar_height = 10
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], radius=5, 
                              fill=hex_to_rgb(colors["text_muted"]) + (50,))
        
        # Score bar fill
        max_score = 150
        fill_width = int((score / max_score) * bar_width)
        if fill_width > 0:
            bar_color = colors["gold"] if rank <= 3 else colors["secondary"]
            draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_width, bar_y + bar_height], radius=5, 
                                  fill=bar_color)
        
        # Score number
        draw.text((SLIDE_WIDTH - left_margin - 20, y + 15), score_text, font=font_score, fill=score_color, anchor="rt")
    
    # Footer
    footer = f"Generated {datetime.now().strftime('%m/%d/%Y')}  |  Performance Rankings"
    draw.text((SLIDE_WIDTH//2, SLIDE_HEIGHT - 35), footer, font=font_footer, fill=colors["text_muted"], anchor="mt")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def generate_complete_rankings_slide(
    rankings: List[Dict[str, Any]], 
    quarter: str, 
    year: int,
    theme: str = "dark_navy",
    custom_colors: Dict = None,
    custom_bg_image: str = None,
    seasonal_theme: str = None
) -> bytes:
    """
    Generate a complete rankings slide showing ALL employees from top to bottom.
    Clean, professional design with proper spacing and no emoji dependencies.
    """
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors)
    draw = ImageDraw.Draw(img)
    
    total_employees = len(rankings)
    
    # Dynamic layout based on employee count
    if total_employees <= 15:
        columns = 2
        row_height = 52
        font_name_size = 24
        font_score_size = 22
        font_rank_size = 20
    elif total_employees <= 24:
        columns = 3
        row_height = 44
        font_name_size = 20
        font_score_size = 18
        font_rank_size = 18
    elif total_employees <= 36:
        columns = 3
        row_height = 36
        font_name_size = 18
        font_score_size = 16
        font_rank_size = 16
    else:
        columns = 4
        row_height = 30
        font_name_size = 15
        font_score_size = 14
        font_rank_size = 14
    
    font_title = get_font(56, bold=True)
    font_subtitle = get_font(24)
    font_name = get_font(font_name_size, bold=True)
    font_score = get_font(font_score_size, bold=True)
    font_rank = get_font(font_rank_size, bold=True)
    font_tier = get_font(max(11, font_rank_size - 3), bold=True)
    font_legend = get_font(14)
    
    # Header - clean text without emojis
    title = "COMPLETE RANKINGS"
    draw.text((SLIDE_WIDTH//2 + 3, 33), title, font=font_title, fill=(0, 0, 0, 100), anchor="mt")
    draw.text((SLIDE_WIDTH//2, 30), title, font=font_title, fill=colors["primary"], anchor="mt")
    
    # Subtitle
    subtitle = f"{quarter} {year}  |  All {total_employees} Team Members  |  Top to Bottom"
    draw.text((SLIDE_WIDTH//2, 95), subtitle, font=font_subtitle, fill=colors["text_muted"], anchor="mt")
    
    # Decorative line
    line_y = 130
    draw.line([(120, line_y), (SLIDE_WIDTH - 120, line_y)], fill=colors["secondary"], width=3)
    
    # Calculate layout
    header_height = 150
    footer_height = 55
    content_height = SLIDE_HEIGHT - header_height - footer_height
    rows_per_col = math.ceil(total_employees / columns)
    
    # Ensure rows fit
    actual_row_height = min(row_height, content_height // rows_per_col)
    
    col_width = (SLIDE_WIDTH - 80) // columns
    col_padding = 20
    
    # Tier colors
    tier_colors = {
        "Trainer": "#A855F7",
        "Bartender": "#3B82F6",
        "A-Server": "#22C55E",
        "B-Server": "#EAB308",
        "C-Server": "#EF4444",
    }
    tier_abbrev = {"Trainer": "T", "Bartender": "BAR", "A-Server": "A", "B-Server": "B", "C-Server": "C"}
    
    # Draw employees
    for idx, emp in enumerate(rankings):
        col = idx // rows_per_col
        row = idx % rows_per_col
        
        x_base = 40 + col * col_width
        y = header_height + row * actual_row_height
        
        rank = idx + 1
        name = emp.get("name", "Unknown")
        score = emp.get("total_score", 0)
        tier = emp.get("tier_label", "A-Server")
        
        # Truncate name - increase limits for better readability
        max_name_len = 14 if columns >= 4 else (16 if columns >= 3 else 20)
        display_name = name[:max_name_len] + ".." if len(name) > max_name_len else name
        
        # Row background for top 3
        if rank <= 3:
            medal_colors = {1: colors["gold"], 2: colors["silver"], 3: colors["bronze"]}
            bg = hex_to_rgb(medal_colors[rank]) + (35,)
            draw.rounded_rectangle(
                [x_base, y, x_base + col_width - col_padding, y + actual_row_height - 4],
                radius=6, fill=bg
            )
        
        # Position tracking
        x_pos = x_base + 8
        
        # Rank number with medal indicator for top 3
        rank_text = f"#{rank}"
        if rank == 1:
            rank_color = colors["gold"]
        elif rank == 2:
            rank_color = colors["silver"]
        elif rank == 3:
            rank_color = colors["bronze"]
        else:
            rank_color = colors["text_muted"]
        
        draw.text((x_pos, y + 4), rank_text, font=font_rank, fill=rank_color)
        x_pos += 50 if columns <= 2 else 40
        
        # Tier badge (colored rectangle with letter)
        tier_color = tier_colors.get(tier, "#888888")
        tier_letter = tier_abbrev.get(tier, "?")
        badge_w = 28 if columns <= 2 else 24
        badge_h = actual_row_height - 12
        
        draw.rounded_rectangle(
            [x_pos, y + 4, x_pos + badge_w, y + badge_h + 4],
            radius=4, fill=tier_color
        )
        draw.text((x_pos + badge_w//2, y + badge_h//2 + 2), tier_letter, 
                  font=font_tier, fill="#FFFFFF", anchor="mm")
        x_pos += badge_w + 10
        
        # Name
        draw.text((x_pos, y + 5), display_name, font=font_name, fill=colors["text_white"])
        
        # Score (right-aligned)
        score_text = f"{score:.1f}"
        score_x = x_base + col_width - col_padding - 10
        score_color = colors["gold"] if rank <= 3 else colors["text_light"]
        draw.text((score_x, y + 5), score_text, font=font_score, fill=score_color, anchor="rt")
    
    # Footer legend
    footer_y = SLIDE_HEIGHT - 45
    legend_font = get_font(13)
    
    # Legend items
    legend_items = [
        ("T", "Trainer", "#A855F7"),
        ("BAR", "Bartender", "#3B82F6"),
        ("A", "A-Server", "#22C55E"),
        ("B", "B-Server", "#EAB308"),
        ("C", "C-Server", "#EF4444"),
    ]
    
    legend_x = 80
    for abbr, label, color in legend_items:
        # Small badge
        draw.rounded_rectangle([legend_x, footer_y, legend_x + 22, footer_y + 18], radius=4, fill=color)
        draw.text((legend_x + 11, footer_y + 9), abbr, font=get_font(11, bold=True), fill="#FFFFFF", anchor="mm")
        legend_x += 28
        draw.text((legend_x, footer_y + 2), f"= {label}", font=legend_font, fill=colors["text_muted"])
        legend_x += 90
    
    # Generation date
    date_text = f"Generated {datetime.now().strftime('%m/%d/%Y')}"
    draw.text((SLIDE_WIDTH - 80, footer_y + 2), date_text, font=legend_font, fill=colors["text_muted"], anchor="rt")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def generate_tier_slide(
    tier_name: str,
    employees: List[Dict[str, Any]], 
    quarter: str, 
    year: int,
    page: int = 1,
    total_pages: int = 1,
    theme: str = "dark_navy",
    custom_colors: Dict = None,
    custom_bg_image: str = None,
    seasonal_theme: str = None
) -> bytes:
    """Generate premium tier-specific slide."""
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors)
    
    active_seasonal = seasonal_theme if seasonal_theme and seasonal_theme != "none" else (get_current_seasonal_theme() if seasonal_theme == "auto" else None)
    if active_seasonal:
        img = add_decorations(img, active_seasonal, colors)
    
    draw = ImageDraw.Draw(img)
    
    tier_config = TIER_CONFIG.get(tier_name, TIER_CONFIG["A-Server"])
    tier_color = tier_config["color"]
    
    # Fonts
    font_title = get_font(64, bold=True)
    font_subtitle = get_font(24)
    font_header = get_font(18, bold=True)
    font_rank = get_font(36, bold=True)
    font_name = get_font(32, bold=True)
    font_score = get_font(36, bold=True)
    font_metric = get_font(20)
    
    # Header - clean without emojis
    title = f"{tier_name.upper()} RANKINGS"
    draw.text((SLIDE_WIDTH//2 + 2, 37), title, font=font_title, fill=(0, 0, 0, 80), anchor="mt")
    draw.text((SLIDE_WIDTH//2, 35), title, font=font_title, fill=tier_color, anchor="mt")
    
    # Subtitle
    page_info = f" • Page {page}/{total_pages}" if total_pages > 1 else ""
    subtitle = f"{quarter} {year} • Bubba Gump Shrimp Co.{page_info}"
    draw.text((SLIDE_WIDTH//2, 105), subtitle, font=font_subtitle, fill=colors["text_muted"], anchor="mt")
    
    # Decorative line
    draw.line([(100, 145), (SLIDE_WIDTH - 100, 145)], fill=tier_color, width=3)
    
    # Column headers
    header_y = 165
    headers = [("RANK", 120), ("NAME", 220), ("PPA", 650), ("LBW", 750), ("LSC", 850), ("GLASS", 950), ("SCORE", SLIDE_WIDTH - 180)]
    for text, x in headers:
        draw.text((x, header_y), text, font=font_header, fill=colors["text_muted"])
    
    # Employee rows
    start_y = 200
    row_height = 75
    max_per_page = 10
    
    for idx, emp in enumerate(employees[:max_per_page]):
        y = start_y + idx * row_height
        
        # Alternating row backgrounds
        if idx % 2 == 0:
            draw.rounded_rectangle(
                [90, y - 5, SLIDE_WIDTH - 90, y + row_height - 15],
                radius=8,
                fill=hex_to_rgb(colors["card_bg"]) + (40,)
            )
        
        # Position label
        position = emp.get("position_label", f"{idx + 1}")
        draw.text((120, y + 12), position, font=font_rank, fill=tier_color)
        
        # Name
        name = emp.get("name", "Unknown")[:20]
        draw.text((220, y + 14), name, font=font_name, fill=colors["text_white"])
        
        # Metric values with color coding
        metrics = [
            ("ppa", 650, 25),
            ("lbw_per_guest", 750, 20),
            ("guests_per_lsc", 850, 15),  # Lower is better
            ("glassware_per_guest", 950, 15),
        ]
        
        for metric_key, x_pos, threshold in metrics:
            value = emp.get(metric_key, 0) or 0
            
            # Color based on performance
            if metric_key == "guests_per_lsc":
                # Lower is better for guests per LSC
                if value <= threshold * 0.8:
                    color = TIER_CONFIG["A-Server"]["color"]
                elif value <= threshold * 1.2:
                    color = TIER_CONFIG["B-Server"]["color"]
                else:
                    color = TIER_CONFIG["C-Server"]["color"]
            else:
                if value >= threshold * 1.1:
                    color = TIER_CONFIG["A-Server"]["color"]
                elif value >= threshold * 0.9:
                    color = TIER_CONFIG["B-Server"]["color"]
                else:
                    color = TIER_CONFIG["C-Server"]["color"]
            
            if metric_key == "ppa":
                text = f"${value:.0f}"
            elif metric_key in ["lbw_per_guest", "glassware_per_guest"]:
                text = f"${value:.2f}"
            else:
                text = f"{value:.0f}"
            
            draw.text((x_pos, y + 18), text, font=font_metric, fill=color)
        
        # Total Score with emphasis
        score = emp.get("total_score", 0)
        draw.text((SLIDE_WIDTH - 130, y + 10), f"{score:.1f}", font=font_score, fill=colors["text_white"], anchor="rt")
    
    # Footer with legend
    font_footer = get_font(18)
    legend = "🟢 Above Target  🟡 On Target  🔴 Below Target"
    draw.text((SLIDE_WIDTH//2, SLIDE_HEIGHT - 45), legend, font=font_footer, fill=colors["text_muted"], anchor="mt")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def generate_most_improved_slide(
    current_rankings: List[Dict[str, Any]],
    previous_rankings: List[Dict[str, Any]],
    quarter: str,
    year: int,
    theme: str = "dark_navy",
    custom_colors: Dict = None,
    custom_bg_image: str = None,
    seasonal_theme: str = None
) -> bytes:
    """Generate Most Improved slide with visual impact."""
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors)
    
    active_seasonal = seasonal_theme if seasonal_theme and seasonal_theme != "none" else (get_current_seasonal_theme() if seasonal_theme == "auto" else None)
    if active_seasonal:
        img = add_decorations(img, active_seasonal, colors)
    
    # Add celebratory glow
    img = draw_glow_circle(img, SLIDE_WIDTH//2, 200, 150, hex_to_rgb("#22C55E"), 25)
    
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(64, bold=True)
    font_subtitle = get_font(24)
    font_rank = get_font(42, bold=True)
    font_name = get_font(36, bold=True)
    font_change = get_font(32, bold=True)
    font_score = get_font(30)
    
    # Header
    title = "🚀 MOST IMPROVED 🚀"
    draw.text((SLIDE_WIDTH//2 + 2, 42), title, font=font_title, fill=(0, 0, 0, 80), anchor="mt")
    draw.text((SLIDE_WIDTH//2, 40), title, font=font_title, fill="#22C55E", anchor="mt")
    
    subtitle = f"{quarter} {year} • Rising Stars"
    draw.text((SLIDE_WIDTH//2, 115), subtitle, font=font_subtitle, fill=colors["text_muted"], anchor="mt")
    
    draw.line([(100, 155), (SLIDE_WIDTH - 100, 155)], fill="#22C55E", width=3)
    
    # Calculate improvements
    prev_scores = {r.get("name"): r.get("total_score", 0) for r in previous_rankings}
    improvements = []
    
    for emp in current_rankings:
        name = emp.get("name")
        current_score = emp.get("total_score", 0)
        prev_score = prev_scores.get(name, current_score)
        change = current_score - prev_score
        if change > 0:
            improvements.append({
                "name": name,
                "current_score": current_score,
                "prev_score": prev_score,
                "change": change,
                "tier_label": emp.get("tier_label", "Server")
            })
    
    improvements.sort(key=lambda x: x["change"], reverse=True)
    
    start_y = 185
    row_height = 100
    
    for idx, emp in enumerate(improvements[:8]):
        y = start_y + idx * row_height
        
        # Card background
        draw_card(draw, (100, y - 5, SLIDE_WIDTH - 100, y + row_height - 15), colors, highlight=(idx < 3))
        
        # Rank
        rank_color = colors["gold"] if idx == 0 else colors["silver"] if idx == 1 else colors["bronze"] if idx == 2 else colors["text_light"]
        draw.text((140, y + 22), f"#{idx + 1}", font=font_rank, fill=rank_color)
        
        # Name
        draw.text((230, y + 25), emp["name"][:18], font=font_name, fill=colors["text_white"])
        
        # Change with arrow
        change_text = f"↑ +{emp['change']:.1f}"
        draw.text((700, y + 28), change_text, font=font_change, fill="#22C55E")
        
        # Score progression
        progression = f"{emp['prev_score']:.1f} → {emp['current_score']:.1f}"
        draw.text((SLIDE_WIDTH - 200, y + 30), progression, font=font_score, fill=colors["text_muted"], anchor="rt")
    
    if not improvements:
        font_no_data = get_font(28)
        draw.text((SLIDE_WIDTH//2, 450), "No improvement data available", font=font_no_data, fill=colors["text_muted"], anchor="mt")
        draw.text((SLIDE_WIDTH//2, 490), "(Requires previous quarter data)", font=font_subtitle, fill=colors["text_muted"], anchor="mt")
    
    font_footer = get_font(18)
    draw.text((SLIDE_WIDTH//2, SLIDE_HEIGHT - 40), "Keep Up The Great Work! 💪", font=font_footer, fill=colors["text_muted"], anchor="mt")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def generate_promotion_watchlist_slide(
    rankings: List[Dict[str, Any]],
    a_server_threshold: float,
    quarter: str,
    year: int,
    theme: str = "dark_navy",
    custom_colors: Dict = None,
    custom_bg_image: str = None,
    seasonal_theme: str = None
) -> bytes:
    """Generate Promotion Watchlist slide."""
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors)
    
    active_seasonal = seasonal_theme if seasonal_theme and seasonal_theme != "none" else (get_current_seasonal_theme() if seasonal_theme == "auto" else None)
    if active_seasonal:
        img = add_decorations(img, active_seasonal, colors)
    
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(64, bold=True)
    font_subtitle = get_font(24)
    font_rank = get_font(38, bold=True)
    font_name = get_font(34, bold=True)
    font_gap = get_font(28, bold=True)
    font_score = get_font(28)
    
    # Header
    title = "⭐ PROMOTION WATCHLIST ⭐"
    draw.text((SLIDE_WIDTH//2 + 2, 42), title, font=font_title, fill=(0, 0, 0, 80), anchor="mt")
    draw.text((SLIDE_WIDTH//2, 40), title, font=font_title, fill=TIER_CONFIG["A-Server"]["color"], anchor="mt")
    
    subtitle = f"{quarter} {year} • Almost A-Server! (threshold: {a_server_threshold})"
    draw.text((SLIDE_WIDTH//2, 115), subtitle, font=font_subtitle, fill=colors["text_muted"], anchor="mt")
    
    draw.line([(100, 155), (SLIDE_WIDTH - 100, 155)], fill=TIER_CONFIG["A-Server"]["color"], width=3)
    
    # Find B-Servers close to A threshold
    watchlist = []
    for emp in rankings:
        if emp.get("tier_label") == "B-Server":
            score = emp.get("total_score", 0)
            gap = a_server_threshold - score
            if 0 < gap <= 10:
                watchlist.append({"name": emp.get("name"), "score": score, "gap": gap, "position_label": emp.get("position_label")})
    
    watchlist.sort(key=lambda x: x["gap"])
    
    start_y = 185
    row_height = 100
    
    for idx, emp in enumerate(watchlist[:8]):
        y = start_y + idx * row_height
        
        draw_card(draw, (100, y - 5, SLIDE_WIDTH - 100, y + row_height - 15), colors, highlight=(idx < 3))
        
        draw.text((140, y + 22), emp["position_label"], font=font_rank, fill=TIER_CONFIG["B-Server"]["color"])
        draw.text((250, y + 25), emp["name"][:18], font=font_name, fill=colors["text_white"])
        
        # Gap indicator with progress bar
        gap_pct = 1 - (emp["gap"] / 10)
        bar_width = 150
        bar_x = 680
        bar_bg = hex_to_rgb(colors["text_muted"])
        draw.rounded_rectangle([bar_x, y + 35, bar_x + bar_width, y + 45], radius=5, fill=bar_bg)
        draw.rounded_rectangle([bar_x, y + 35, bar_x + int(bar_width * gap_pct), y + 45], radius=5, fill=hex_to_rgb(TIER_CONFIG["A-Server"]["color"]))
        
        draw.text((bar_x + bar_width + 15, y + 28), f"{emp['gap']:.1f} pts to go", font=font_gap, fill=colors["gold"])
        draw.text((SLIDE_WIDTH - 150, y + 28), f"{emp['score']:.1f}", font=font_score, fill=colors["text_white"], anchor="rt")
    
    if not watchlist:
        font_no_data = get_font(28)
        draw.text((SLIDE_WIDTH//2, 450), "No B-Servers within 10 points of A-Server", font=font_no_data, fill=colors["text_muted"], anchor="mt")
    
    font_footer = get_font(18)
    draw.text((SLIDE_WIDTH//2, SLIDE_HEIGHT - 40), "Keep Pushing! You're Almost There! 🎯", font=font_footer, fill=colors["text_muted"], anchor="mt")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def generate_at_risk_slide(
    rankings: List[Dict[str, Any]],
    b_server_threshold: float,
    quarter: str,
    year: int,
    theme: str = "dark_navy",
    custom_colors: Dict = None,
    custom_bg_image: str = None,
    seasonal_theme: str = None
) -> bytes:
    """Generate At Risk / Coaching Focus slide."""
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors)
    
    active_seasonal = seasonal_theme if seasonal_theme and seasonal_theme != "none" else (get_current_seasonal_theme() if seasonal_theme == "auto" else None)
    if active_seasonal:
        img = add_decorations(img, active_seasonal, colors)
    
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(60, bold=True)
    font_warning = get_font(22, bold=True)
    font_subtitle = get_font(24)
    font_rank = get_font(36, bold=True)
    font_name = get_font(32, bold=True)
    font_gap = get_font(26)
    font_score = get_font(28)
    
    # Header
    title = "📋 COACHING FOCUS GROUP 📋"
    draw.text((SLIDE_WIDTH//2 + 2, 37), title, font=font_title, fill=(0, 0, 0, 80), anchor="mt")
    draw.text((SLIDE_WIDTH//2, 35), title, font=font_title, fill=TIER_CONFIG["C-Server"]["color"], anchor="mt")
    
    subtitle = f"{quarter} {year} • Development Priority (B-Server: {b_server_threshold})"
    draw.text((SLIDE_WIDTH//2, 100), subtitle, font=font_subtitle, fill=colors["text_muted"], anchor="mt")
    
    # Warning banner
    warning = "⚠️ MANAGER ONLY - CONFIDENTIAL ⚠️"
    draw.rounded_rectangle([SLIDE_WIDTH//2 - 220, 130, SLIDE_WIDTH//2 + 220, 160], radius=8, fill=TIER_CONFIG["C-Server"]["bg"])
    draw.text((SLIDE_WIDTH//2, 138), warning, font=font_warning, fill=TIER_CONFIG["C-Server"]["color"], anchor="mt")
    
    draw.line([(100, 175), (SLIDE_WIDTH - 100, 175)], fill=TIER_CONFIG["C-Server"]["color"], width=3)
    
    # Find C-Servers
    at_risk = []
    for emp in rankings:
        if emp.get("tier_label") == "C-Server":
            score = emp.get("total_score", 0)
            gap = b_server_threshold - score
            at_risk.append({"name": emp.get("name"), "score": score, "gap": gap, "position_label": emp.get("position_label")})
    
    at_risk.sort(key=lambda x: x["score"], reverse=True)
    
    start_y = 200
    row_height = 90
    
    for idx, emp in enumerate(at_risk[:8]):
        y = start_y + idx * row_height
        
        draw_card(draw, (100, y - 5, SLIDE_WIDTH - 100, y + row_height - 15), colors)
        
        draw.text((140, y + 18), emp["position_label"], font=font_rank, fill=TIER_CONFIG["C-Server"]["color"])
        draw.text((250, y + 22), emp["name"][:18], font=font_name, fill=colors["text_white"])
        draw.text((700, y + 24), f"{emp['gap']:.1f} pts needed", font=font_gap, fill=TIER_CONFIG["B-Server"]["color"])
        draw.text((SLIDE_WIDTH - 150, y + 22), f"{emp['score']:.1f}", font=font_score, fill=colors["text_white"], anchor="rt")
    
    if not at_risk:
        font_no_data = get_font(28)
        draw.text((SLIDE_WIDTH//2, 450), "No C-Servers - Great job team! 🎉", font=font_no_data, fill=colors["text_muted"], anchor="mt")
    
    font_footer = get_font(18)
    draw.text((SLIDE_WIDTH//2, SLIDE_HEIGHT - 40), "Confidential Management Document", font=font_footer, fill=colors["text_muted"], anchor="mt")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def generate_all_slides(rankings: List[Dict[str, Any]], quarter: str, year: int, theme: str = "dark_navy", custom_colors: Dict = None, seasonal_theme: str = None) -> Dict[str, List[bytes]]:
    """Generate all Yodeck slides for a quarter."""
    slides = {"top_10": [], "trainers": [], "bartenders": [], "a_servers": [], "b_servers": [], "c_servers": []}
    
    slides["top_10"].append(generate_top_10_slide(rankings, quarter, year, theme, custom_colors, None, seasonal_theme))
    
    tier_groups = {"Trainer": [], "Bartender": [], "A-Server": [], "B-Server": [], "C-Server": []}
    for emp in rankings:
        tier = emp.get("tier_label", "A-Server")
        if tier in tier_groups:
            tier_groups[tier].append(emp)
    
    max_per_slide = 10
    for tier_name, tier_key in [("Trainer", "trainers"), ("Bartender", "bartenders"), ("A-Server", "a_servers"), ("B-Server", "b_servers"), ("C-Server", "c_servers")]:
        employees = tier_groups[tier_name]
        if not employees:
            continue
        total_pages = (len(employees) + max_per_slide - 1) // max_per_slide
        for page in range(total_pages):
            start_idx = page * max_per_slide
            page_employees = employees[start_idx:start_idx + max_per_slide]
            slides[tier_key].append(generate_tier_slide(tier_name, page_employees, quarter, year, page + 1, total_pages, theme, custom_colors, None, seasonal_theme))
    
    return slides
