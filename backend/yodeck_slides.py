"""
Yodeck Slide Generator v3.0
Generates 16:9 (1920x1080) PNG slides for digital signage.
Bubba Gump Brand + Sports Leaderboard Style
- Vibrant red/blue colors with tropical accents
- ESPN-style rankings with dynamic energy
- Geometric patterns, glow effects, card-based layouts
"""
import io
import os
import requests
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from datetime import datetime, date
import base64
import math
import random

# Import backgrounds from snapshot_slides
from snapshot_slides import BACKGROUNDS as SNAPSHOT_BACKGROUNDS

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

def generate_top_10_by_metric_slide(
    employees: List[Dict[str, Any]],
    quarter: str,
    year: int,
    output_format: str = "16:9"
) -> bytes:
    """
    Generate Top 10 Performers By Metric slide matching the user's professional design.
    Shows 4 metric columns: PPA, Glass/Guest, Guests/LSC, LBW/Guest
    
    Args:
        employees: List of employee dicts with metrics
        quarter: Quarter string (e.g., "Q1")
        year: Year integer
        output_format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
    """
    # Set dimensions based on format
    if output_format == "letter":
        width, height = 2550, 3300
        scale = 1.33
    else:
        width, height = SLIDE_WIDTH, SLIDE_HEIGHT
        scale = 1.0
    
    # Colors matching the design
    header_dark = "#0D3B66"  # Dark blue header
    header_gradient = "#1A5276"  # Slightly lighter blue
    metric_header_bg = "#4A4A4A"  # Dark gray for metric titles
    col_header_bg = "#507EA9"  # Light blue for column headers
    row_light = "#F8F9FA"  # Light gray alternating row
    row_white = "#FFFFFF"  # White alternating row
    rank_badge_bg = "#C41E3A"  # Red for rank badges
    text_dark = "#333333"  # Dark text for data
    
    # Create image with gradient header
    img = Image.new('RGB', (width, height), row_white)
    draw = ImageDraw.Draw(img)
    
    # Header height (scaled)
    header_height = int(180 * scale)
    
    # Draw gradient header background
    for y in range(header_height):
        ratio = y / header_height
        r = int(13 + (26 - 13) * ratio)
        g = int(59 + (82 - 59) * ratio)
        b = int(102 + (118 - 102) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # Fonts (scaled)
    try:
        font_title_top = get_font(int(52 * scale), bold=True)
        font_title_main = get_font(int(72 * scale), bold=True)
        font_quarter = get_font(int(28 * scale), bold=True)
        font_year = get_font(int(56 * scale), bold=True)
        font_metric_header = get_font(int(22 * scale), bold=True)
        font_col_header = get_font(int(18 * scale), bold=True)
        font_rank = get_font(int(16 * scale), bold=True)
        font_name = get_font(int(18 * scale))
        font_value = get_font(int(18 * scale), bold=True)
    except:
        font_title_top = ImageFont.load_default()
        font_title_main = ImageFont.load_default()
        font_quarter = ImageFont.load_default()
        font_year = ImageFont.load_default()
        font_metric_header = ImageFont.load_default()
        font_col_header = ImageFont.load_default()
        font_rank = ImageFont.load_default()
        font_name = ImageFont.load_default()
        font_value = ImageFont.load_default()
    
    # === HEADER SECTION ===
    
    # Logo placeholder area (left side) - draw a circle with text as placeholder
    logo_x = int(90 * scale)
    logo_y = int(90 * scale)
    logo_radius = int(70 * scale)
    
    # Draw logo circle background
    draw.ellipse([logo_x - logo_radius, logo_y - logo_radius, 
                  logo_x + logo_radius, logo_y + logo_radius], 
                 fill="#1A5276", outline="#E63946", width=3)
    
    # Add "BUBBA GUMP" text in circle
    logo_font = get_font(int(14 * scale), bold=True)
    draw.text((logo_x, logo_y - int(15 * scale)), "BUBBA", font=logo_font, fill="#FFFFFF", anchor="mm")
    draw.text((logo_x, logo_y + int(5 * scale)), "GUMP", font=logo_font, fill="#E63946", anchor="mm")
    logo_font_small = get_font(int(10 * scale))
    draw.text((logo_x, logo_y + int(22 * scale)), "SHRIMP CO.", font=logo_font_small, fill="#FFFFFF", anchor="mm")
    
    # Title - "TOP 10 PERFORMERS" on first line
    title_x = int(220 * scale)
    draw.text((title_x, int(55 * scale)), "TOP 10 PERFORMERS", font=font_title_top, fill="#FFFFFF", anchor="lm")
    
    # "BY METRIC" on second line (larger, bolder)
    draw.text((title_x, int(120 * scale)), "BY METRIC", font=font_title_main, fill="#FFFFFF", anchor="lm")
    
    # Quarter and Year on right side
    quarter_x = width - int(150 * scale)
    quarter_num = quarter.replace("Q", "")
    draw.text((quarter_x, int(55 * scale)), f"QUARTER {quarter_num}", font=font_quarter, fill="#FFFFFF", anchor="mm")
    draw.text((quarter_x, int(110 * scale)), str(year), font=font_year, fill="#FFFFFF", anchor="mm")
    
    # === METRICS SECTION ===
    
    # Define the 4 metrics to display
    metrics = [
        {"key": "ppa", "label": "PPA - Top 10", "format": "currency", "higher_better": True},
        {"key": "glassware_per_guest", "label": "Glass/Guest - Top 10", "format": "currency", "higher_better": True},
        {"key": "guests_per_lsc", "label": "Guests/LSC - Top 10", "format": "number", "higher_better": False},
        {"key": "lbw_per_guest", "label": "LBW/Guest - Top 10", "format": "currency", "higher_better": True},
    ]
    
    # Calculate column widths
    margin = int(20 * scale)
    table_area_width = width - (margin * 2)
    col_width = table_area_width // 4
    table_start_y = header_height + int(10 * scale)
    
    # Process employee data for each metric
    for col_idx, metric in enumerate(metrics):
        col_x = margin + (col_idx * col_width)
        
        # Sort employees by this metric
        metric_key = metric["key"]
        valid_employees = [e for e in employees if e.get(metric_key) is not None]
        
        if metric["higher_better"]:
            sorted_emps = sorted(valid_employees, key=lambda e: float(e.get(metric_key, 0) or 0), reverse=True)
        else:
            sorted_emps = sorted(valid_employees, key=lambda e: float(e.get(metric_key, 999999) or 999999))
        
        top_10 = sorted_emps[:10]
        
        # Draw metric header (dark gray bar)
        metric_header_y = table_start_y
        metric_header_height = int(40 * scale)
        draw.rectangle([col_x, metric_header_y, col_x + col_width - int(5 * scale), metric_header_y + metric_header_height],
                       fill=metric_header_bg)
        draw.text((col_x + col_width // 2, metric_header_y + metric_header_height // 2), 
                  metric["label"], font=font_metric_header, fill="#FFFFFF", anchor="mm")
        
        # Draw column headers (light blue bar)
        col_header_y = metric_header_y + metric_header_height
        col_header_height = int(35 * scale)
        draw.rectangle([col_x, col_header_y, col_x + col_width - int(5 * scale), col_header_y + col_header_height],
                       fill=col_header_bg)
        
        # Column header text positions
        rank_col_w = int(60 * scale)
        name_col_w = int(150 * scale)
        value_col_w = col_width - rank_col_w - name_col_w - int(20 * scale)
        
        draw.text((col_x + rank_col_w // 2, col_header_y + col_header_height // 2), 
                  "Rank", font=font_col_header, fill="#FFFFFF", anchor="mm")
        draw.text((col_x + rank_col_w + int(10 * scale), col_header_y + col_header_height // 2), 
                  "Employee", font=font_col_header, fill="#FFFFFF", anchor="lm")
        draw.text((col_x + col_width - int(40 * scale), col_header_y + col_header_height // 2), 
                  "Value", font=font_col_header, fill="#FFFFFF", anchor="rm")
        
        # Draw data rows
        row_y = col_header_y + col_header_height
        row_height = int(70 * scale)  # Taller rows for letter format
        
        if output_format != "letter":
            row_height = int(76 * scale)  # Adjust for 16:9 to fill space
        
        for rank, emp in enumerate(top_10, 1):
            # Alternating row colors
            row_bg = row_light if rank % 2 == 0 else row_white
            draw.rectangle([col_x, row_y, col_x + col_width - int(5 * scale), row_y + row_height],
                           fill=row_bg)
            
            # Rank badge (red circle with white text)
            badge_x = col_x + rank_col_w // 2
            badge_y = row_y + row_height // 2
            badge_radius = int(14 * scale)
            draw.ellipse([badge_x - badge_radius, badge_y - badge_radius,
                         badge_x + badge_radius, badge_y + badge_radius],
                        fill=rank_badge_bg)
            draw.text((badge_x, badge_y), f"#{rank}", font=font_rank, fill="#FFFFFF", anchor="mm")
            
            # Employee name (truncate if needed)
            name = emp.get("name", "Unknown")
            if len(name) > 12:
                name = name[:11] + ".."
            draw.text((col_x + rank_col_w + int(15 * scale), badge_y), 
                      name, font=font_name, fill=text_dark, anchor="lm")
            
            # Value (formatted)
            value = emp.get(metric_key, 0)
            if metric["format"] == "currency":
                value_text = f"${float(value or 0):.2f}"
            else:
                value_text = f"{float(value or 0):.1f}"
            
            draw.text((col_x + col_width - int(15 * scale), badge_y), 
                      value_text, font=font_value, fill=text_dark, anchor="rm")
            
            row_y += row_height
        
        # Fill remaining rows if less than 10 employees
        while rank < 10:
            rank += 1
            row_bg = row_light if rank % 2 == 0 else row_white
            draw.rectangle([col_x, row_y, col_x + col_width - int(5 * scale), row_y + row_height],
                           fill=row_bg)
            row_y += row_height
    
    # Save to buffer
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def generate_top_10_slide(
    rankings: List[Dict[str, Any]], 
    quarter: str, 
    year: int,
    theme: str = "bubba_gump",
    custom_colors: Dict = None,
    custom_bg_image: str = None,
    seasonal_theme: str = None,
    output_format: str = "16:9"
) -> bytes:
    """
    Generate premium Top 10 Performers slide.
    Sports leaderboard style with Bubba Gump branding.
    Args:
        output_format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
    """
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    
    # Set dimensions based on format
    if output_format == "letter":
        width, height = 2550, 3300
        font_scale = 1.5
    else:
        width, height = SLIDE_WIDTH, SLIDE_HEIGHT
        font_scale = 1.0
    
    img = create_gradient_background(width, height, colors)
    
    # Add geometric decorations
    img = draw_geometric_decorations(img, colors)
    
    draw = ImageDraw.Draw(img)
    
    # Fonts - scaled for format
    font_title = get_font(int(72 * font_scale), bold=True)
    font_subtitle = get_font(int(24 * font_scale))
    font_rank = get_font(int(32 * font_scale), bold=True)
    font_name = get_font(int(30 * font_scale), bold=True)
    font_score = get_font(int(36 * font_scale), bold=True)
    font_tier = get_font(int(16 * font_scale), bold=True)
    font_footer = get_font(int(16 * font_scale))
    
    # === HEADER SECTION ===
    # Title with shadow effect
    title = "TOP 10 PERFORMERS"
    title_y = int(45 * font_scale)
    draw.text((width//2 + 3, title_y + 3), title, font=font_title, 
              fill=(0, 0, 0, 150), anchor="mt")
    draw.text((width//2, title_y), title, font=font_title, 
              fill=colors.get("primary", "#E63946"), anchor="mt")
    
    # Decorative underline
    line_y = int(115 * font_scale)
    primary_rgb = hex_to_rgb(colors.get("primary", "#E63946"))
    secondary_rgb = hex_to_rgb(colors.get("secondary", "#1D8CC7"))
    draw.rectangle([width//2 - int(250 * font_scale), line_y, width//2 + int(250 * font_scale), line_y + int(4 * font_scale)], 
                   fill=primary_rgb)
    draw.rectangle([width//2 - int(150 * font_scale), line_y + int(6 * font_scale), width//2 + int(150 * font_scale), line_y + int(8 * font_scale)], 
                   fill=secondary_rgb)
    
    # Subtitle
    subtitle = f"{quarter} {year}  •  BUBBA GUMP SHRIMP CO.  •  LAS VEGAS"
    draw.text((width//2, line_y + int(25 * font_scale)), subtitle, font=font_subtitle, 
              fill=colors.get("text_muted", "#778DA9"), anchor="mt")
    
    # === LEADERBOARD SECTION ===
    start_y = int(170 * font_scale)
    row_height = int(85 * font_scale)
    left_margin = int(80 * font_scale)
    right_margin = int(80 * font_scale)
    card_width = SLIDE_WIDTH - left_margin - right_margin
    
    for idx, emp in enumerate(rankings[:10]):
        rank = idx + 1
        y = start_y + idx * row_height
        
        # Draw card with shadow (glow for top 3)
        card_bbox = (left_margin, y, width - right_margin, y + row_height - int(8 * font_scale))
        img = draw_card_with_shadow(img, card_bbox, colors, glow=(rank <= 3))
        draw = ImageDraw.Draw(img)  # Refresh draw object
        
        # Medal for top 3
        if rank <= 3:
            img = draw_premium_medal(img, left_margin + int(50 * font_scale), y + row_height//2 - 4, rank, colors, size=int(60 * font_scale))
            draw = ImageDraw.Draw(img)
            name_x = left_margin + int(110 * font_scale)
        else:
            # Rank number for others
            rank_text = f"#{rank}"
            draw.text((left_margin + int(30 * font_scale), y + row_height//2 - 5), rank_text, 
                      font=font_rank, fill=colors.get("text_muted", "#888"), anchor="lm")
            name_x = left_margin + int(100 * font_scale)
        
        # Employee name
        name = emp.get("name", "Unknown")
        if len(name) > 18:
            name = name[:17] + ".."
        draw.text((name_x, y + row_height//2 - 5), name, font=font_name, 
                  fill=colors.get("text_white", "#FFFFFF"), anchor="lm")
        
        # Tier badge (glossy pill)
        tier = emp.get("tier_label", "A-Server")
        tier_config = TIER_CONFIG.get(tier, TIER_CONFIG["A-Server"])
        tier_x = int(500 * font_scale)
        draw_glossy_badge(draw, tier_x, y + row_height//2 - int(15 * font_scale), int(100 * font_scale), int(30 * font_scale), 
                         tier_config["color"], tier, "#FFFFFF")
        
        # Score visualization - Progress Ring
        score = emp.get("total_score", 0)
        max_score = 130
        ring_x = width - right_margin - int(180 * font_scale)
        ring_y = y + row_height//2 - 4
        img = draw_progress_ring(img, ring_x, ring_y, int(28 * font_scale), score, max_score, colors, thickness=int(8 * font_scale))
        draw = ImageDraw.Draw(img)
        
        # Score number
        score_text = f"{score:.1f}"
        score_color = colors.get("gold", "#FFD700") if rank <= 3 else colors.get("text_white", "#FFFFFF")
        draw.text((width - right_margin - int(40 * font_scale), y + row_height//2 - 5), 
                  score_text, font=font_score, fill=score_color, anchor="rm")
    
    # === FOOTER ===
    footer_y = height - int(40 * font_scale)
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y')}  •  Performance Rankings  •  Max Score: 130"
    draw.text((width//2, footer_y), footer_text, font=font_footer, 
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
    seasonal_theme: str = None,
    output_format: str = "16:9",
    background: str = "dark"
) -> bytes:
    """
    Generate complete rankings slide matching the snapshot layout.
    Left panel: Logo, title, legend. Right panel: Full employee table.
    """
    width = SLIDE_WIDTH  # 1920
    height = SLIDE_HEIGHT  # 1080
    
    # Colors
    COLORS = {
        "bg_navy": (15, 23, 42),
        "white": "#FFFFFF",
        "title_red": "#E63946",
        "header_blue": (13, 42, 77),
        "row_white": (255, 255, 255),
        "row_gray": (240, 240, 240),
        "blue": "#007BFF",
        "green": "#28A745",
        "yellow": "#FFC107",
        "red": "#DC3545",
        "divider": (100, 100, 100),
        "divider_bold": (50, 50, 50),
    }
    
    # Tier colors
    TIER_COLORS = {
        "Trainer": "#A855F7",
        "Bartender": "#3B82F6", 
        "A-Server": "#22C55E",
        "B-Server": "#EAB308",
        "C-Server": "#EF4444"
    }
    
    # Helper function to draw outlined text with thick black stroke
    def draw_outlined_text(draw, pos, text, font, fill_color, outline_color="#000000", outline_width=2):
        x, y = pos
        # Draw thick outline by drawing text in multiple positions
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, font=font, fill=outline_color, anchor="mm")
        # Draw main text on top
        draw.text((x, y), text, font=font, fill=fill_color, anchor="mm")
    
    # Get background configuration
    bg_config = SNAPSHOT_BACKGROUNDS.get(background, SNAPSHOT_BACKGROUNDS.get("dark", {"type": "solid", "color": COLORS["bg_navy"]}))
    
    # Create base image based on background type
    if bg_config.get("type") == "image" and bg_config.get("url"):
        try:
            response = requests.get(bg_config["url"], timeout=10)
            bg_img = Image.open(io.BytesIO(response.content))
            if bg_img.mode != 'RGB':
                bg_img = bg_img.convert('RGB')
            bg_img = bg_img.resize((width, height), Image.Resampling.LANCZOS)
            enhancer = ImageEnhance.Brightness(bg_img)
            bg_img = enhancer.enhance(0.3)
            sat_enhancer = ImageEnhance.Color(bg_img)
            bg_img = sat_enhancer.enhance(0.6)
            bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=3))
            overlay = Image.new('RGBA', (width, height), (10, 20, 40, 150))
            bg_img = bg_img.convert('RGBA')
            bg_img = Image.alpha_composite(bg_img, overlay)
            img = bg_img.convert('RGB')
        except Exception as e:
            print(f"Error loading background: {e}")
            img = Image.new('RGB', (width, height), COLORS["bg_navy"])
    else:
        color = bg_config.get("color", COLORS["bg_navy"])
        img = Image.new('RGB', (width, height), color)
    
    draw = ImageDraw.Draw(img)
    
    # Sort employees by tier hierarchy
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_emps = sorted(rankings, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    num_emps = len(sorted_emps)
    
    # ===== LEFT PANEL =====
    left_width = 380
    
    # Logo
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((220, 220), Image.Resampling.LANCZOS)
            logo_x = (left_width - logo.width) // 2
            img.paste(logo, (logo_x, 20), logo)
        except:
            pass
    
    draw = ImageDraw.Draw(img)
    
    # Title section
    title_y = 260
    center_x = left_width // 2
    
    draw.text((center_x, title_y), f"{quarter} TEAM", font=get_font(30, bold=True),
              fill=COLORS["white"], anchor="mm")
    draw.text((center_x, title_y + 40), "RANKINGS", font=get_font(38, bold=True),
              fill=COLORS["title_red"], anchor="mm")
    draw.text((center_x, title_y + 80), str(year), font=get_font(26, bold=True),
              fill=COLORS["white"], anchor="mm")
    
    # Legend
    legend_y = title_y + 130
    legend_items = [
        (TIER_COLORS["Trainer"], "TRAINER"),
        (TIER_COLORS["Bartender"], "BARTENDER"),
        (TIER_COLORS["A-Server"], "A-SERVER"),
        (TIER_COLORS["B-Server"], "B-SERVER"),
        (TIER_COLORS["C-Server"], "C-SERVER"),
    ]
    
    for i, (color, label) in enumerate(legend_items):
        y = legend_y + i * 50
        square_size = 35
        legend_start_x = (left_width - 180) // 2
        draw.rectangle([legend_start_x, y, legend_start_x + square_size, y + square_size], fill=color, outline="#000000", width=1)
        draw.text((legend_start_x + square_size + 10, y + 17), label, 
                  font=get_font(20, bold=True), fill=color, anchor="lm")
    
    # Footer
    footer_y = height - 90
    draw.text((center_x, footer_y), "BUBBA GUMP SHRIMP CO.", 
              font=get_font(16, bold=True), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 22), "LAS VEGAS",
              font=get_font(16, bold=True), fill=COLORS["title_red"], anchor="mm")
    draw.text((center_x, footer_y + 48), f"Generated {datetime.now().strftime('%m/%d/%Y')}",
              font=get_font(12), fill="#888888", anchor="mm")
    
    # ===== RIGHT PANEL (Table) =====
    table_left = left_width + 10
    table_right = width - 10
    table_top = 15
    table_width = table_right - table_left
    
    # Calculate row sizing - bolder font needs slightly more space
    header_h = 38
    available_height = height - table_top - 15 - header_h
    row_h = available_height // max(num_emps, 1)
    row_h = max(26, min(36, row_h))
    
    # Columns - EQUITABLE spacing (all equal width except Name which needs more)
    num_cols = 9
    base_col_width = table_width // num_cols
    
    columns = [
        {"name": "Rank", "width": base_col_width},
        {"name": "Name", "width": base_col_width + 40},  # Name gets extra
        {"name": "PPA", "width": base_col_width},
        {"name": "LBW", "width": base_col_width},
        {"name": "Glass", "width": base_col_width},
        {"name": "LSC", "width": base_col_width},
        {"name": "CV", "width": base_col_width - 10},
        {"name": "Bonus", "width": base_col_width - 10},
        {"name": "Score", "width": base_col_width - 20},
    ]
    
    # Adjust to fit exactly
    total_w = sum(c["width"] for c in columns)
    diff = table_width - total_w
    columns[-1]["width"] += diff
    
    col_x = []
    x = table_left
    for c in columns:
        col_x.append(x)
        x += c["width"]
    
    # Header row
    draw.rectangle([table_left, table_top, table_right, table_top + header_h], fill=COLORS["header_blue"])
    header_font = get_font(15, bold=True)
    for i, col in enumerate(columns):
        cx = col_x[i] + col["width"] // 2
        draw.text((cx, table_top + header_h // 2), col["name"],
                  font=header_font, fill=COLORS["white"], anchor="mm")
        # Vertical divider lines in header
        if i > 0:
            draw.line([(col_x[i], table_top), (col_x[i], table_top + header_h)], fill=(80, 100, 140), width=2)
    
    # Data rows
    data_y = table_top + header_h
    tier_counts = {}
    prev_tier = None
    
    # Fonts - BOLDER and slightly larger
    font_data = get_font(14, bold=True)
    font_rank = get_font(15, bold=True)
    font_score = get_font(15, bold=True)
    
    for row_idx, emp in enumerate(sorted_emps):
        tier = emp.get("tier_label", "C-Server")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        y = data_y + row_idx * row_h
        if y + row_h > height - 10:
            break
        
        # Row background
        row_bg = COLORS["row_white"] if row_idx % 2 == 0 else COLORS["row_gray"]
        draw.rectangle([table_left, y, table_right, y + row_h], fill=row_bg)
        
        # Horizontal divider - BOLD between tiers, regular otherwise
        is_tier_change = prev_tier is not None and tier != prev_tier
        line_width = 3 if is_tier_change else 1
        line_color = COLORS["divider_bold"] if is_tier_change else COLORS["divider"]
        draw.line([(table_left, y), (table_right, y)], fill=line_color, width=line_width)
        
        prev_tier = tier
        
        # Vertical divider lines in data rows
        for i in range(1, len(columns)):
            draw.line([(col_x[i], y), (col_x[i], y + row_h)], fill=(120, 120, 120), width=2)
        
        # Rank with tier prefix - OUTLINED
        prefix = {"Trainer": "T", "Bartender": "BAR", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "")
        rank_text = f"{prefix}{tier_counts[tier]}"
        tier_color = TIER_COLORS.get(tier, "#666666")
        
        row_cy = y + row_h // 2
        
        # Draw outlined rank text with thick black stroke
        draw_outlined_text(draw, (col_x[0] + columns[0]["width"] // 2, row_cy), 
                          rank_text, font_rank, tier_color, "#000000", 2)
        
        # Name (left aligned, no outline needed)
        name = emp.get("name", "Unknown")[:18]
        draw.text((col_x[1] + 8, row_cy), name, font=font_data, fill="#222222", anchor="lm")
        
        # PPA - 2 DECIMALS
        ppa = emp.get("ppa") or emp.get("score_ppa", 0) or 0
        ppa_text = f"${ppa:.2f}" if ppa else "-"
        draw.text((col_x[2] + columns[2]["width"] // 2, row_cy), ppa_text,
                  font=font_data, fill="#222222", anchor="mm")
        
        # LBW
        lbw = emp.get("lbw_per_guest") or emp.get("score_lbw", 0) or 0
        draw.text((col_x[3] + columns[3]["width"] // 2, row_cy), f"${lbw:.2f}" if lbw else "-",
                  font=font_data, fill="#222222", anchor="mm")
        
        # Glass
        glass = emp.get("glassware_per_guest") or emp.get("score_glass", 0) or 0
        draw.text((col_x[4] + columns[4]["width"] // 2, row_cy), f"${glass:.2f}" if glass else "-",
                  font=font_data, fill="#222222", anchor="mm")
        
        # LSC
        lsc = emp.get("guests_per_lsc") or emp.get("score_lsc", 0) or 0
        draw.text((col_x[5] + columns[5]["width"] // 2, row_cy), f"{lsc:.1f}" if lsc else "-",
                  font=font_data, fill="#222222", anchor="mm")
        
        # CV
        cv = emp.get("cv_score") or emp.get("score_cv", 0) or 0
        draw.text((col_x[6] + columns[6]["width"] // 2, row_cy), f"{cv:.0f}" if cv else "-",
                  font=font_data, fill="#222222", anchor="mm")
        
        # Bonus
        bonus = (emp.get("review_tracker_bonus", 0) or 0) + (emp.get("total_metric_bonus", 0) or 0)
        bonus_color = "#16A34A" if bonus > 0 else "#222222"
        draw.text((col_x[7] + columns[7]["width"] // 2, row_cy), f"+{bonus:.0f}" if bonus > 0 else "-",
                  font=font_data, fill=bonus_color, anchor="mm")
        
        # Total Score - OUTLINED with tier color
        total = emp.get("total_score", 0) or 0
        draw_outlined_text(draw, (col_x[8] + columns[8]["width"] // 2, row_cy),
                          f"{total:.1f}", font_score, tier_color, "#000000", 1)
    
    # Final bottom border
    final_y = data_y + len(sorted_emps) * row_h
    if final_y <= height - 10:
        draw.line([(table_left, final_y), (table_right, final_y)], fill=COLORS["divider_bold"], width=2)
    
    # Table border
    draw.rectangle([table_left, table_top, table_right, min(final_y, height - 10)], outline=COLORS["divider_bold"], width=2)
    
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
    seasonal_theme: str = None,
    output_format: str = "16:9"
) -> bytes:
    """Generate Most Improved slide with visual impact.
    Args:
        output_format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
    """
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    
    # Set dimensions based on format
    if output_format == "letter":
        width, height = 2550, 3300
        scale = 1.5
    else:
        width, height = SLIDE_WIDTH, SLIDE_HEIGHT
        scale = 1.0
    
    img = create_gradient_background(width, height, colors)
    
    active_seasonal = seasonal_theme if seasonal_theme and seasonal_theme != "none" else (get_current_seasonal_theme() if seasonal_theme == "auto" else None)
    if active_seasonal:
        img = add_decorations(img, active_seasonal, colors)
    
    # Add celebratory glow
    img = draw_glow_circle(img, width//2, int(200 * scale), int(150 * scale), hex_to_rgb("#22C55E"), 25)
    
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(int(64 * scale), bold=True)
    font_subtitle = get_font(int(24 * scale))
    font_rank = get_font(int(42 * scale), bold=True)
    font_name = get_font(int(36 * scale), bold=True)
    font_change = get_font(int(32 * scale), bold=True)
    font_score = get_font(int(30 * scale))
    
    # Header
    title = "🚀 MOST IMPROVED 🚀"
    draw.text((width//2 + 2, int(42 * scale)), title, font=font_title, fill=(0, 0, 0, 80), anchor="mt")
    draw.text((width//2, int(40 * scale)), title, font=font_title, fill="#22C55E", anchor="mt")
    
    subtitle = f"{quarter} {year} • Rising Stars"
    draw.text((width//2, int(115 * scale)), subtitle, font=font_subtitle, fill=colors["text_muted"], anchor="mt")
    
    draw.line([(int(100 * scale), int(155 * scale)), (width - int(100 * scale), int(155 * scale))], fill="#22C55E", width=int(3 * scale))
    
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
    
    start_y = int(185 * scale)
    row_height = int(100 * scale)
    
    for idx, emp in enumerate(improvements[:8]):
        y = start_y + idx * row_height
        
        # Card background
        draw_card(draw, (int(100 * scale), y - 5, width - int(100 * scale), y + row_height - 15), colors, highlight=(idx < 3))
        
        # Rank
        rank_color = colors["gold"] if idx == 0 else colors["silver"] if idx == 1 else colors["bronze"] if idx == 2 else colors["text_light"]
        draw.text((int(140 * scale), y + int(22 * scale)), f"#{idx + 1}", font=font_rank, fill=rank_color)
        
        # Name
        draw.text((int(230 * scale), y + int(25 * scale)), emp["name"][:18], font=font_name, fill=colors["text_white"])
        
        # Change with arrow
        change_text = f"↑ +{emp['change']:.1f}"
        draw.text((int(700 * scale), y + int(28 * scale)), change_text, font=font_change, fill="#22C55E")
        
        # Score progression
        progression = f"{emp['prev_score']:.1f} → {emp['current_score']:.1f}"
        draw.text((width - int(200 * scale), y + int(30 * scale)), progression, font=font_score, fill=colors["text_muted"], anchor="rt")
    
    if not improvements:
        font_no_data = get_font(int(28 * scale))
        draw.text((width//2, int(450 * scale)), "No improvement data available", font=font_no_data, fill=colors["text_muted"], anchor="mt")
        draw.text((width//2, int(490 * scale)), "(Requires previous quarter data)", font=font_subtitle, fill=colors["text_muted"], anchor="mt")
    
    font_footer = get_font(int(18 * scale))
    draw.text((width//2, height - int(40 * scale)), "Keep Up The Great Work! 💪", font=font_footer, fill=colors["text_muted"], anchor="mt")
    
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
    seasonal_theme: str = None,
    output_format: str = "16:9"
) -> bytes:
    """Generate Promotion Watchlist slide.
    Args:
        output_format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
    """
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    
    # Set dimensions based on format
    if output_format == "letter":
        width, height = 2550, 3300
        scale = 1.5
    else:
        width, height = SLIDE_WIDTH, SLIDE_HEIGHT
        scale = 1.0
    
    img = create_gradient_background(width, height, colors)
    
    active_seasonal = seasonal_theme if seasonal_theme and seasonal_theme != "none" else (get_current_seasonal_theme() if seasonal_theme == "auto" else None)
    if active_seasonal:
        img = add_decorations(img, active_seasonal, colors)
    
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(int(64 * scale), bold=True)
    font_subtitle = get_font(int(24 * scale))
    font_rank = get_font(int(38 * scale), bold=True)
    font_name = get_font(int(34 * scale), bold=True)
    font_gap = get_font(int(28 * scale), bold=True)
    font_score = get_font(int(28 * scale))
    
    # Header
    title = "⭐ PROMOTION WATCHLIST ⭐"
    draw.text((width//2 + 2, int(42 * scale)), title, font=font_title, fill=(0, 0, 0, 80), anchor="mt")
    draw.text((width//2, int(40 * scale)), title, font=font_title, fill=TIER_CONFIG["A-Server"]["color"], anchor="mt")
    
    subtitle = f"{quarter} {year} • Almost A-Server! (threshold: {a_server_threshold})"
    draw.text((width//2, int(115 * scale)), subtitle, font=font_subtitle, fill=colors["text_muted"], anchor="mt")
    
    draw.line([(int(100 * scale), int(155 * scale)), (width - int(100 * scale), int(155 * scale))], fill=TIER_CONFIG["A-Server"]["color"], width=int(3 * scale))
    
    # Find B-Servers close to A threshold
    watchlist = []
    for emp in rankings:
        if emp.get("tier_label") == "B-Server":
            score = emp.get("total_score", 0)
            gap = a_server_threshold - score
            if 0 < gap <= 10:
                watchlist.append({"name": emp.get("name"), "score": score, "gap": gap, "position_label": emp.get("position_label")})
    
    watchlist.sort(key=lambda x: x["gap"])
    
    start_y = int(185 * scale)
    row_height = int(100 * scale)
    
    for idx, emp in enumerate(watchlist[:8]):
        y = start_y + idx * row_height
        
        draw_card(draw, (int(100 * scale), y - 5, width - int(100 * scale), y + row_height - 15), colors, highlight=(idx < 3))
        
        draw.text((int(140 * scale), y + int(22 * scale)), emp["position_label"], font=font_rank, fill=TIER_CONFIG["B-Server"]["color"])
        draw.text((int(250 * scale), y + int(25 * scale)), emp["name"][:18], font=font_name, fill=colors["text_white"])
        
        # Gap indicator with progress bar
        gap_pct = 1 - (emp["gap"] / 10)
        bar_width = int(150 * scale)
        bar_x = int(680 * scale)
        bar_bg = hex_to_rgb(colors["text_muted"])
        draw.rounded_rectangle([bar_x, y + int(35 * scale), bar_x + bar_width, y + int(45 * scale)], radius=5, fill=bar_bg)
        draw.rounded_rectangle([bar_x, y + int(35 * scale), bar_x + int(bar_width * gap_pct), y + int(45 * scale)], radius=5, fill=hex_to_rgb(TIER_CONFIG["A-Server"]["color"]))
        
        draw.text((bar_x + bar_width + int(15 * scale), y + int(28 * scale)), f"{emp['gap']:.1f} pts to go", font=font_gap, fill=colors["gold"])
        draw.text((width - int(150 * scale), y + int(28 * scale)), f"{emp['score']:.1f}", font=font_score, fill=colors["text_white"], anchor="rt")
    
    if not watchlist:
        font_no_data = get_font(int(28 * scale))
        draw.text((width//2, int(450 * scale)), "No B-Servers within 10 points of A-Server", font=font_no_data, fill=colors["text_muted"], anchor="mt")
    
    font_footer = get_font(int(18 * scale))
    draw.text((width//2, height - int(40 * scale)), "Keep Pushing! You're Almost There! 🎯", font=font_footer, fill=colors["text_muted"], anchor="mt")
    
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
    seasonal_theme: str = None,
    output_format: str = "16:9"
) -> bytes:
    """Generate At Risk / Coaching Focus slide.
    Args:
        output_format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
    """
    colors = get_theme_colors(theme, custom_colors, seasonal_theme)
    
    # Set dimensions based on format
    if output_format == "letter":
        width, height = 2550, 3300
        scale = 1.5
    else:
        width, height = SLIDE_WIDTH, SLIDE_HEIGHT
        scale = 1.0
    
    img = create_gradient_background(width, height, colors)
    
    active_seasonal = seasonal_theme if seasonal_theme and seasonal_theme != "none" else (get_current_seasonal_theme() if seasonal_theme == "auto" else None)
    if active_seasonal:
        img = add_decorations(img, active_seasonal, colors)
    
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(int(60 * scale), bold=True)
    font_warning = get_font(int(22 * scale), bold=True)
    font_subtitle = get_font(int(24 * scale))
    font_rank = get_font(int(36 * scale), bold=True)
    font_name = get_font(int(32 * scale), bold=True)
    font_gap = get_font(int(26 * scale))
    font_score = get_font(int(28 * scale))
    
    # Header
    title = "📋 COACHING FOCUS GROUP 📋"
    draw.text((width//2 + 2, int(37 * scale)), title, font=font_title, fill=(0, 0, 0, 80), anchor="mt")
    draw.text((width//2, int(35 * scale)), title, font=font_title, fill=TIER_CONFIG["C-Server"]["color"], anchor="mt")
    
    subtitle = f"{quarter} {year} • Development Priority (B-Server: {b_server_threshold})"
    draw.text((width//2, int(100 * scale)), subtitle, font=font_subtitle, fill=colors["text_muted"], anchor="mt")
    
    # Warning banner
    warning = "⚠️ MANAGER ONLY - CONFIDENTIAL ⚠️"
    banner_half_width = int(220 * scale)
    draw.rounded_rectangle([width//2 - banner_half_width, int(130 * scale), width//2 + banner_half_width, int(160 * scale)], radius=8, fill=TIER_CONFIG["C-Server"]["bg"])
    draw.text((width//2, int(138 * scale)), warning, font=font_warning, fill=TIER_CONFIG["C-Server"]["color"], anchor="mt")
    
    draw.line([(int(100 * scale), int(175 * scale)), (width - int(100 * scale), int(175 * scale))], fill=TIER_CONFIG["C-Server"]["color"], width=int(3 * scale))
    
    # Find C-Servers
    at_risk = []
    for emp in rankings:
        if emp.get("tier_label") == "C-Server":
            score = emp.get("total_score", 0)
            gap = b_server_threshold - score
            at_risk.append({"name": emp.get("name"), "score": score, "gap": gap, "position_label": emp.get("position_label")})
    
    at_risk.sort(key=lambda x: x["score"], reverse=True)
    
    start_y = int(200 * scale)
    row_height = int(90 * scale)
    
    for idx, emp in enumerate(at_risk[:8]):
        y = start_y + idx * row_height
        
        draw_card(draw, (int(100 * scale), y - 5, width - int(100 * scale), y + row_height - 15), colors)
        
        draw.text((int(140 * scale), y + int(18 * scale)), emp["position_label"], font=font_rank, fill=TIER_CONFIG["C-Server"]["color"])
        draw.text((int(250 * scale), y + int(22 * scale)), emp["name"][:18], font=font_name, fill=colors["text_white"])
        draw.text((int(700 * scale), y + int(24 * scale)), f"{emp['gap']:.1f} pts needed", font=font_gap, fill=TIER_CONFIG["B-Server"]["color"])
        draw.text((width - int(150 * scale), y + int(22 * scale)), f"{emp['score']:.1f}", font=font_score, fill=colors["text_white"], anchor="rt")
    
    if not at_risk:
        font_no_data = get_font(int(28 * scale))
        draw.text((width//2, int(450 * scale)), "No C-Servers - Great job team! 🎉", font=font_no_data, fill=colors["text_muted"], anchor="mt")
    
    font_footer = get_font(int(18 * scale))
    draw.text((width//2, height - int(40 * scale)), "Confidential Management Document", font=font_footer, fill=colors["text_muted"], anchor="mt")
    
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
