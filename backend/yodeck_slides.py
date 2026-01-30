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


# ============================================================================
# PREMIUM VISUAL EFFECTS (v3.0)
# ============================================================================

def draw_progress_ring(img: Image.Image, x: int, y: int, radius: int, 
                       score: float, max_score: float, colors: Dict, 
                       thickness: int = 12) -> Image.Image:
    """Draw a circular progress ring with score."""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Background ring
    bg_color = hex_to_rgb(colors.get("text_muted", "#888888")) + (60,)
    draw.ellipse([x - radius, y - radius, x + radius, y + radius], outline=bg_color, width=thickness)
    
    # Progress arc
    pct = min(score / max_score, 1.0) if max_score > 0 else 0
    if pct > 0:
        end_angle = -90 + (360 * pct)
        
        # Determine color based on score
        if pct >= 0.85:
            ring_color = hex_to_rgb(colors.get("gold", "#FFD700"))
        elif pct >= 0.70:
            ring_color = hex_to_rgb(colors.get("secondary", "#3742FA"))
        else:
            ring_color = hex_to_rgb(colors.get("accent", "#FFA502"))
        
        draw.arc([x - radius, y - radius, x + radius, y + radius], 
                 start=-90, end=end_angle, fill=ring_color + (255,), width=thickness)
    
    img = img.convert('RGBA')
    return Image.alpha_composite(img, overlay).convert('RGB')


def draw_glossy_badge(draw: ImageDraw.Draw, x: int, y: int, width: int, height: int,
                      bg_color: str, text: str, text_color: str = "#FFFFFF"):
    """Draw a glossy pill-shaped badge with ribbon effect."""
    bg = hex_to_rgb(bg_color)
    
    # Main badge
    draw.rounded_rectangle([x, y, x + width, y + height], radius=height//2, fill=bg)
    
    # Glossy highlight
    highlight = tuple(min(c + 60, 255) for c in bg) + (80,)
    draw.rounded_rectangle([x + 2, y + 2, x + width - 2, y + height//2], 
                          radius=height//4, fill=highlight)
    
    # Text
    font = get_font(height - 10, bold=True)
    draw.text((x + width//2, y + height//2), text, font=font, 
              fill=text_color, anchor="mm")


def draw_card_with_shadow(img: Image.Image, bbox: Tuple[int, int, int, int], 
                          colors: Dict, glow: bool = False) -> Image.Image:
    """Draw a card with shadow and optional glow effect."""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    x1, y1, x2, y2 = bbox
    
    # Shadow layers
    shadow_color = (0, 0, 0)
    for i in range(4, 0, -1):
        shadow_bbox = [x1 + i*2, y1 + i*2, x2 + i*2, y2 + i*2]
        draw.rounded_rectangle(shadow_bbox, radius=16, fill=shadow_color + (20,))
    
    # Glow effect for top performers
    if glow:
        glow_color = hex_to_rgb(colors.get("glow", "#00D9FF"))
        for i in range(3, 0, -1):
            glow_bbox = [x1 - i*3, y1 - i*3, x2 + i*3, y2 + i*3]
            draw.rounded_rectangle(glow_bbox, radius=18, fill=glow_color + (15 * i,))
    
    # Main card
    card_color = hex_to_rgb(colors.get("card_bg", "#1E3A5F"))
    draw.rounded_rectangle(bbox, radius=16, fill=card_color + (240,))
    
    # Subtle border
    border_color = hex_to_rgb(colors.get("secondary", "#3742FA"))
    draw.rounded_rectangle(bbox, radius=16, outline=border_color + (100,), width=2)
    
    img = img.convert('RGBA')
    return Image.alpha_composite(img, overlay).convert('RGB')


def draw_geometric_decorations(img: Image.Image, colors: Dict) -> Image.Image:
    """Add geometric decorative elements to background."""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    primary = hex_to_rgb(colors.get("primary", "#E63946"))
    secondary = hex_to_rgb(colors.get("secondary", "#1D8CC7"))
    accent = hex_to_rgb(colors.get("accent", "#F4A261"))
    
    # Top right corner geometric shape
    draw.polygon([(SLIDE_WIDTH - 200, 0), (SLIDE_WIDTH, 0), (SLIDE_WIDTH, 200)], 
                 fill=primary + (25,))
    draw.polygon([(SLIDE_WIDTH - 300, 0), (SLIDE_WIDTH, 0), (SLIDE_WIDTH, 300)], 
                 fill=secondary + (15,))
    
    # Bottom left corner geometric shape
    draw.polygon([(0, SLIDE_HEIGHT - 150), (0, SLIDE_HEIGHT), (150, SLIDE_HEIGHT)], 
                 fill=accent + (25,))
    draw.polygon([(0, SLIDE_HEIGHT - 250), (0, SLIDE_HEIGHT), (250, SLIDE_HEIGHT)], 
                 fill=secondary + (15,))
    
    # Diagonal accent lines
    for i in range(3):
        y_offset = 120 + i * 25
        draw.line([(0, y_offset), (400 - i*80, 0)], 
                  fill=primary + (40 - i*10,), width=3)
    
    # Subtle grid pattern in corners
    for x in range(SLIDE_WIDTH - 150, SLIDE_WIDTH, 30):
        for y in range(0, 150, 30):
            draw.ellipse([x-2, y-2, x+2, y+2], fill=(255, 255, 255, 20))
    
    for x in range(0, 150, 30):
        for y in range(SLIDE_HEIGHT - 150, SLIDE_HEIGHT, 30):
            draw.ellipse([x-2, y-2, x+2, y+2], fill=(255, 255, 255, 20))
    
    img = img.convert('RGBA')
    return Image.alpha_composite(img, overlay).convert('RGB')


def draw_premium_medal(img: Image.Image, x: int, y: int, rank: int, 
                       colors: Dict, size: int = 70) -> Image.Image:
    """Draw a premium 3D-style medal with glow effect."""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    if rank == 1:
        outer_color = hex_to_rgb(colors.get("gold", "#FFD700"))
        inner_color = (255, 240, 150)
        glow_color = (255, 215, 0)
    elif rank == 2:
        outer_color = hex_to_rgb(colors.get("silver", "#C0C0C0"))
        inner_color = (220, 220, 230)
        glow_color = (200, 200, 210)
    elif rank == 3:
        outer_color = hex_to_rgb(colors.get("bronze", "#CD7F32"))
        inner_color = (230, 160, 100)
        glow_color = (205, 127, 50)
    else:
        return img
    
    # Glow effect
    for i in range(5, 0, -1):
        glow_size = size + i * 8
        draw.ellipse([x - glow_size//2, y - glow_size//2, 
                      x + glow_size//2, y + glow_size//2], 
                     fill=glow_color + (15 * i,))
    
    # Outer medal ring
    draw.ellipse([x - size//2, y - size//2, x + size//2, y + size//2], 
                 fill=outer_color + (255,))
    
    # Inner medal
    inner_size = int(size * 0.75)
    draw.ellipse([x - inner_size//2, y - inner_size//2, 
                  x + inner_size//2, y + inner_size//2], 
                 fill=inner_color + (255,))
    
    # 3D highlight
    highlight_size = int(size * 0.5)
    draw.ellipse([x - highlight_size//2 - 5, y - highlight_size//2 - 5, 
                  x + highlight_size//2 - 10, y + highlight_size//2 - 10], 
                 fill=(255, 255, 255, 80))
    
    # Rank number
    font = get_font(size//2, bold=True)
    draw.text((x, y + 3), str(rank), font=font, fill=(30, 30, 30, 255), anchor="mm")
    
    img = img.convert('RGBA')
    return Image.alpha_composite(img, overlay).convert('RGB')


# ============================================================================
# SLIDE GENERATORS (v3.0 - Premium Styling)
# ============================================================================

def generate_top_10_slide(
    rankings: List[Dict[str, Any]], 
    quarter: str, 
    year: int,
    theme: str = "bubba_gump",
    custom_colors: Dict = None,
    custom_bg_image: str = None,
    seasonal_theme: str = None
) -> bytes:
    """
    Generate premium Top 10 Performers slide.
    Sports leaderboard style with Bubba Gump branding.
    """
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors)
    
    # Add geometric decorations
    img = draw_geometric_decorations(img, colors)
    
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_title = get_font(72, bold=True)
    font_subtitle = get_font(24)
    font_rank = get_font(32, bold=True)
    font_name = get_font(30, bold=True)
    font_score = get_font(36, bold=True)
    font_tier = get_font(16, bold=True)
    font_footer = get_font(16)
    
    # === HEADER SECTION ===
    # Title with shadow effect
    title = "TOP 10 PERFORMERS"
    title_y = 45
    draw.text((SLIDE_WIDTH//2 + 3, title_y + 3), title, font=font_title, 
              fill=(0, 0, 0, 150), anchor="mt")
    draw.text((SLIDE_WIDTH//2, title_y), title, font=font_title, 
              fill=colors.get("primary", "#E63946"), anchor="mt")
    
    # Decorative underline
    line_y = 115
    primary_rgb = hex_to_rgb(colors.get("primary", "#E63946"))
    secondary_rgb = hex_to_rgb(colors.get("secondary", "#1D8CC7"))
    draw.rectangle([SLIDE_WIDTH//2 - 250, line_y, SLIDE_WIDTH//2 + 250, line_y + 4], 
                   fill=primary_rgb)
    draw.rectangle([SLIDE_WIDTH//2 - 150, line_y + 6, SLIDE_WIDTH//2 + 150, line_y + 8], 
                   fill=secondary_rgb)
    
    # Subtitle
    subtitle = f"{quarter} {year}  •  BUBBA GUMP SHRIMP CO.  •  LAS VEGAS"
    draw.text((SLIDE_WIDTH//2, line_y + 25), subtitle, font=font_subtitle, 
              fill=colors.get("text_muted", "#778DA9"), anchor="mt")
    
    # === LEADERBOARD SECTION ===
    start_y = 170
    row_height = 85
    left_margin = 80
    right_margin = 80
    card_width = SLIDE_WIDTH - left_margin - right_margin
    
    for idx, emp in enumerate(rankings[:10]):
        rank = idx + 1
        y = start_y + idx * row_height
        
        # Draw card with shadow (glow for top 3)
        card_bbox = (left_margin, y, SLIDE_WIDTH - right_margin, y + row_height - 8)
        img = draw_card_with_shadow(img, card_bbox, colors, glow=(rank <= 3))
        draw = ImageDraw.Draw(img)  # Refresh draw object
        
        # Medal for top 3
        if rank <= 3:
            img = draw_premium_medal(img, left_margin + 50, y + row_height//2 - 4, rank, colors, size=60)
            draw = ImageDraw.Draw(img)
            name_x = left_margin + 110
        else:
            # Rank number for others
            rank_text = f"#{rank}"
            draw.text((left_margin + 30, y + row_height//2 - 5), rank_text, 
                      font=font_rank, fill=colors.get("text_muted", "#888"), anchor="lm")
            name_x = left_margin + 100
        
        # Employee name
        name = emp.get("name", "Unknown")
        if len(name) > 18:
            name = name[:17] + ".."
        draw.text((name_x, y + row_height//2 - 5), name, font=font_name, 
                  fill=colors.get("text_white", "#FFFFFF"), anchor="lm")
        
        # Tier badge (glossy pill)
        tier = emp.get("tier_label", "A-Server")
        tier_config = TIER_CONFIG.get(tier, TIER_CONFIG["A-Server"])
        tier_x = 500
        draw_glossy_badge(draw, tier_x, y + row_height//2 - 15, 100, 30, 
                         tier_config["color"], tier, "#FFFFFF")
        
        # Score visualization - Progress Ring
        score = emp.get("total_score", 0)
        max_score = 130
        ring_x = SLIDE_WIDTH - right_margin - 180
        ring_y = y + row_height//2 - 4
        img = draw_progress_ring(img, ring_x, ring_y, 28, score, max_score, colors, thickness=8)
        draw = ImageDraw.Draw(img)
        
        # Score number
        score_text = f"{score:.1f}"
        score_color = colors.get("gold", "#FFD700") if rank <= 3 else colors.get("text_white", "#FFFFFF")
        draw.text((SLIDE_WIDTH - right_margin - 40, y + row_height//2 - 5), 
                  score_text, font=font_score, fill=score_color, anchor="rm")
    
    # === FOOTER ===
    footer_y = SLIDE_HEIGHT - 40
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y')}  •  Performance Rankings  •  Max Score: 130"
    draw.text((SLIDE_WIDTH//2, footer_y), footer_text, font=font_footer, 
              fill=colors.get("text_muted", "#778DA9"), anchor="mm")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def generate_complete_rankings_slide(
    rankings: List[Dict[str, Any]], 
    quarter: str, 
    year: int,
    theme: str = "bubba_gump",
    custom_colors: Dict = None,
    custom_bg_image: str = None,
    seasonal_theme: str = None
) -> bytes:
    """
    Generate two side-by-side tables matching the Rankings tab design.
    14 employees on left, 14 on right, with vertical red divider.
    Uses circular progress indicators for metrics.
    Proper A-Server/B-Server/C-Server tier labels.
    """
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors)
    draw = ImageDraw.Draw(img)
    
    total_employees = len(rankings)
    
    # Data is already sorted by hierarchy from the API
    left_employees = rankings[:14]
    right_employees = rankings[14:28]
    
    # Tier badge colors (matching the app exactly)
    tier_badge_colors = {
        "Trainer": "#A855F7",      # Purple
        "Bartender": "#3B82F6",    # Blue
        "A-Server": "#22C55E",     # Green
        "B-Server": "#EAB308",     # Yellow
        "C-Server": "#EF4444",     # Red
    }
    
    # Position badge colors
    position_badge_colors = {
        "T": "#A855F7",   # Purple for trainers
        "Bar": "#3B82F6", # Blue for bartenders
        "A": "#22C55E",   # Green for A-servers
        "B": "#EAB308",   # Yellow for B-servers
        "C": "#EF4444",   # Red for C-servers
    }
    
    # Colors
    text_dark = "#1F2937"
    text_gray = "#6B7280"
    text_light_gray = "#9CA3AF"
    header_red = "#DC2626"
    score_red = "#DC2626"
    bonus_green = "#16A34A"
    
    # Progress colors
    progress_green = "#22C55E"
    progress_yellow = "#F59E0B"
    progress_red = "#EF4444"
    progress_bg = "#E5E7EB"
    
    # Fonts
    font_title = get_font(24, bold=True)
    font_subtitle = get_font(10)
    font_header = get_font(8, bold=True)
    font_position = get_font(16, bold=True)
    font_badge = get_font(7, bold=True)
    font_name = get_font(10, bold=True)
    font_job = get_font(7)
    font_tier = get_font(7, bold=True)
    font_score = get_font(11, bold=True)
    font_metric_val = get_font(8)
    font_metric_max = get_font(6)
    font_bonus = get_font(9, bold=True)
    font_footer = get_font(8)
    
    # Layout
    margin_x = 10
    margin_y = 5
    divider_width = 4
    table_width = (SLIDE_WIDTH - (margin_x * 2) - divider_width) // 2
    
    title_height = 32
    header_height = 22
    footer_height = 16
    
    # Calculate row height for 14 rows
    available_height = SLIDE_HEIGHT - margin_y - title_height - header_height - footer_height - margin_y
    row_height = available_height // 14
    
    # === TITLE ===
    title = f"COMPLETE TEAM RANKINGS  •  {quarter} {year}"
    draw.text((SLIDE_WIDTH//2, margin_y + 3), title, font=font_title,
              fill=colors.get("primary", "#E63946"), anchor="mt")
    
    subtitle = f"{total_employees} Team Members  •  Trainers → Bartenders → A/B/C Servers"
    draw.text((SLIDE_WIDTH//2, margin_y + 22), subtitle, font=font_subtitle, 
              fill=colors.get("text_muted", "#778DA9"), anchor="mt")
    
    # Column positions
    left_x = margin_x
    right_x = margin_x + table_width + divider_width
    table_top = margin_y + title_height
    
    def draw_circle_progress(cx, cy, radius, percentage, color):
        """Draw a smooth circular progress indicator using filled shapes."""
        # Create a separate image for the circle at higher resolution
        scale = 3
        img_size = (radius * 2 + 12) * scale
        circle_img = Image.new('RGBA', (img_size, img_size), (0, 0, 0, 0))
        circle_draw = ImageDraw.Draw(circle_img)
        
        center = img_size // 2
        outer_r = radius * scale
        inner_r = int(outer_r * 0.65)  # Inner radius for donut hole
        
        # Draw background ring (full gray donut)
        circle_draw.ellipse([center - outer_r, center - outer_r, 
                            center + outer_r, center + outer_r],
                           fill=progress_bg)
        
        # Draw progress arc as pie slice
        if percentage > 0:
            start_angle = -90
            end_angle = -90 + (percentage * 360 / 100)
            circle_draw.pieslice([center - outer_r, center - outer_r,
                                 center + outer_r, center + outer_r],
                                start=start_angle, end=end_angle, fill=color)
        
        # Cut out center to make donut (white/transparent center)
        # Use the row background color for center
        circle_draw.ellipse([center - inner_r, center - inner_r,
                            center + inner_r, center + inner_r],
                           fill=(255, 255, 255, 255))
        
        # Scale down with high-quality resampling
        final_size = radius * 2 + 12
        circle_img = circle_img.resize((final_size, final_size), Image.LANCZOS)
        
        # Paste onto main image
        paste_x = cx - final_size // 2
        paste_y = cy - final_size // 2
        img.paste(circle_img, (paste_x, paste_y), circle_img)
    
    def get_position_badge_color(pos_label):
        """Get badge color based on position label prefix."""
        if pos_label.startswith("T"):
            return position_badge_colors["T"]
        elif pos_label.startswith("Bar"):
            return position_badge_colors["Bar"]
        elif pos_label.startswith("A"):
            return position_badge_colors["A"]
        elif pos_label.startswith("B"):
            return position_badge_colors["B"]
        elif pos_label.startswith("C"):
            return position_badge_colors["C"]
        return "#6B7280"
    
    def draw_table(employees, start_x, t_width):
        """Draw a complete table matching the Rankings tab exactly."""
        
        # Column widths (proportional) - adjusted for circles
        # POSITION(50) | EMPLOYEE(85) | TIER(55) | SCORE(45) | BONUS(40) | PPA(55) | LBW(55) | LSC(55) | GLASS(55)
        col_widths_raw = [50, 85, 55, 45, 40, 55, 55, 55, 55]
        total_raw = sum(col_widths_raw)
        scale = t_width / total_raw
        col_widths = [int(w * scale) for w in col_widths_raw]
        
        # Calculate column x positions
        col_x = []
        x = 0
        for w in col_widths:
            col_x.append(x)
            x += w
        
        # === HEADER ROW ===
        header_y = table_top
        draw.rectangle([start_x, header_y, start_x + t_width, header_y + header_height],
                       fill=header_red)
        
        # Header labels
        headers = ["#", "EMPLOYEE", "TIER", "SCORE", "BONUS", "PPA", "LBW", "LSC", "GLASS"]
        header_subs = ["", "", "", "", "", "(25%)", "(20%)", "(25%)", "(15%)"]
        
        for i, (label, sub) in enumerate(zip(headers, header_subs)):
            cx = start_x + col_x[i] + col_widths[i] // 2
            if sub:
                draw.text((cx, header_y + 6), label, font=font_header, fill="#FFFFFF", anchor="mt")
                draw.text((cx, header_y + 14), sub, font=get_font(5), fill=(255,255,255,180), anchor="mt")
            else:
                draw.text((cx, header_y + header_height // 2), label, font=font_header, fill="#FFFFFF", anchor="mm")
        
        # === DATA ROWS ===
        y = header_y + header_height
        
        for idx, emp in enumerate(employees):
            if idx >= 14:
                break
            
            job_title = str(emp.get("job_title", "server")).lower()
            tier_label = emp.get("tier_label", "Server")
            position_label = emp.get("position_label", str(idx + 1))
            
            # Alternating row background (white/light gray like the app)
            if idx % 2 == 0:
                row_bg = (255, 255, 255, 240)  # White
            else:
                row_bg = (248, 250, 252, 240)  # Very light gray
            
            draw.rectangle([start_x, y, start_x + t_width, y + row_height - 1], fill=row_bg)
            
            # Thin separator line
            draw.line([start_x, y + row_height - 1, start_x + t_width, y + row_height - 1],
                      fill=(229, 231, 235), width=1)
            
            # --- POSITION column ---
            col_idx = 0
            
            # Large gray position number
            draw.text((start_x + col_x[col_idx] + 12, y + row_height // 2),
                      str(idx + 1), font=font_position, fill=text_light_gray, anchor="mm")
            
            # Position badge (T1, Bar1, A1, B1, C1)
            badge_color = get_position_badge_color(position_label)
            badge_w = 26
            badge_h = 14
            badge_x = start_x + col_x[col_idx] + 24
            badge_y = y + (row_height - badge_h) // 2
            draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
                                   radius=3, fill=badge_color)
            draw.text((badge_x + badge_w // 2, badge_y + badge_h // 2), position_label,
                      font=font_badge, fill="#FFFFFF", anchor="mm")
            
            # --- EMPLOYEE column ---
            col_idx = 1
            name = str(emp.get("name", "Unknown"))
            if len(name) > 10:
                name = name[:9] + ".."
            job_display = job_title.title()
            
            draw.text((start_x + col_x[col_idx] + 4, y + row_height // 2 - 5),
                      name, font=font_name, fill=text_dark, anchor="lm")
            draw.text((start_x + col_x[col_idx] + 4, y + row_height // 2 + 5),
                      job_display, font=font_job, fill=text_gray, anchor="lm")
            
            # --- TIER column (A-Server, B-Server, C-Server badges) ---
            col_idx = 2
            tier_color = tier_badge_colors.get(tier_label, "#6B7280")
            tier_w = col_widths[col_idx] - 4
            tier_h = 14
            tier_x = start_x + col_x[col_idx] + 2
            tier_y = y + (row_height - tier_h) // 2
            draw.rounded_rectangle([tier_x, tier_y, tier_x + tier_w, tier_y + tier_h],
                                   radius=3, fill=tier_color)
            # Shorten label for space
            tier_short = {"Trainer": "Train", "Bartender": "Bar", "A-Server": "A-Srv", 
                          "B-Server": "B-Srv", "C-Server": "C-Srv"}.get(tier_label, tier_label[:5])
            draw.text((tier_x + tier_w // 2, tier_y + tier_h // 2), tier_short,
                      font=font_tier, fill="#FFFFFF", anchor="mm")
            
            # --- SCORE column ---
            col_idx = 3
            total_score = float(emp.get("total_score", 0) or 0)
            draw.text((start_x + col_x[col_idx] + col_widths[col_idx] // 2, y + row_height // 2),
                      f"{total_score:.1f}", font=font_score, fill=score_red, anchor="mm")
            
            # --- BONUS column ---
            col_idx = 4
            bonus = float(emp.get("bonus_total", 0) or 0)
            bonus_text = f"+{bonus:.1f}" if bonus >= 0 else f"{bonus:.1f}"
            draw.text((start_x + col_x[col_idx] + col_widths[col_idx] // 2, y + row_height // 2),
                      bonus_text, font=font_bonus, fill=bonus_green, anchor="mm")
            
            # --- METRIC columns with CIRCULAR progress indicators ---
            metrics = [
                (5, "ppa_points", 30),
                (6, "lbw_points", 25),
                (7, "lsc_points", 30),
                (8, "glassware_points", 20),
            ]
            
            for col_idx, key, default_max in metrics:
                points = emp.get(key, {})
                if isinstance(points, dict):
                    earned = float(points.get("earned", 0) or 0)
                    possible = float(points.get("possible", default_max) or default_max)
                else:
                    # Fallback for old format
                    earned = float(points or 0)
                    possible = default_max
                
                percentage = (earned / possible * 100) if possible > 0 else 0
                
                # Determine color based on percentage
                if percentage >= 80:
                    prog_color = progress_green
                elif percentage >= 50:
                    prog_color = progress_yellow
                else:
                    prog_color = progress_red
                
                cx = start_x + col_x[col_idx] + col_widths[col_idx] // 2
                cy = y + row_height // 2
                
                # Draw circular progress (radius 12)
                radius = 11
                draw_circle_progress(cx, cy, radius, percentage, prog_color)
                
                # Score text inside circle
                draw.text((cx, cy - 3), f"{earned:.0f}", font=font_metric_val, fill=text_dark, anchor="mm")
                draw.text((cx, cy + 6), f"/{int(possible)}", font=font_metric_max, fill=text_gray, anchor="mm")
            
            y += row_height
    
    # Draw left table
    draw_table(left_employees, left_x, table_width)
    
    # Draw right table
    draw_table(right_employees, right_x, table_width)
    
    # === VERTICAL RED DIVIDER LINE ===
    divider_x = margin_x + table_width + (divider_width // 2)
    draw.rectangle([divider_x - 2, table_top, divider_x + 2, SLIDE_HEIGHT - footer_height - margin_y],
                   fill="#DC2626")
    
    # === FOOTER ===
    footer_y = SLIDE_HEIGHT - footer_height + 2
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y')}  •  Bubba Gump Shrimp Co. Las Vegas"
    draw.text((SLIDE_WIDTH//2, footer_y), footer_text, font=font_footer, 
              fill=colors.get("text_muted", "#778DA9"), anchor="mt")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()
    
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
