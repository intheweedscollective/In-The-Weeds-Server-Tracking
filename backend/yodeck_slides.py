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
    output_format: str = "16:9",
    background: str = "dark",
    data_date: str = None
) -> bytes:
    """
    Generate Top 10 Performers By Metric slide matching the user's professional design.
    Shows 4 metric columns: PPA, Glass/Guest, Guests/LSC, LBW/Guest
    
    Args:
        employees: List of employee dicts with metrics
        quarter: Quarter string (e.g., "Q1")
        year: Year integer
        output_format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
        background: Background key from BACKGROUNDS dict
        data_date: Date string of most recent data (e.g., "2026-01-15")
    """
    from snapshot_slides import BACKGROUNDS
    import requests
    
    # Set dimensions based on format
    if output_format == "letter":
        width, height = 2550, 3300
        scale = 1.33
    else:
        width, height = SLIDE_WIDTH, SLIDE_HEIGHT
        scale = 1.0
    
    # Colors matching the design - WHITE background with alternating rows
    metric_header_bg = "#4A4A4A"  # Dark gray for metric titles
    col_header_bg = "#507EA9"  # Light blue for column headers
    row_light = (235, 235, 235)  # Light gray alternating row
    row_white = (255, 255, 255)  # White alternating row
    rank_badge_bg = "#1E5FA8"  # BLUE for rank badges (was red)
    text_dark = "#222222"  # Dark text for data
    
    # Create WHITE background image (ignore background parameter for cleaner look)
    img = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Header height (scaled) - LARGER for more impact
    header_height = int(145 * scale)
    
    # Draw solid header bar
    draw.rectangle([0, 0, width, header_height], fill=(13, 59, 102))
    
    # Fonts (scaled) - LARGER TITLES for TV impact
    try:
        font_title_top = get_font(int(52 * scale), bold=True)  # Larger
        font_title_main = get_font(int(72 * scale), bold=True)  # Much larger
        font_quarter = get_font(int(28 * scale), bold=True)
        font_year = get_font(int(44 * scale), bold=True)
        font_metric_header = get_font(int(24 * scale), bold=True)  # Increased
        font_col_header = get_font(int(20 * scale), bold=True)     # Increased
        font_rank = get_font(int(18 * scale), bold=True)           # Increased
        font_name = get_font(int(22 * scale), bold=True)           # Increased & bold
        font_value = get_font(int(22 * scale), bold=True)          # Increased
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
    
    # Load classic Bubba Gump logo from local file
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    logo_height = int(125 * scale)  # Larger logo for bigger header
    logo_x = int(10 * scale)
    logo_y = int(10 * scale)
    
    try:
        logo_img = Image.open(logo_path)
        logo_img = logo_img.convert('RGBA')
        # Calculate width maintaining aspect ratio
        aspect_ratio = logo_img.width / logo_img.height
        logo_width = int(logo_height * aspect_ratio)
        logo_img = logo_img.resize((logo_width, logo_height), Image.LANCZOS)
        # Paste logo onto header
        img.paste(logo_img, (logo_x, logo_y), logo_img)
        title_x = logo_x + logo_width + int(25 * scale)
    except Exception as e:
        print(f"Error loading logo: {e}")
        # Fallback - draw placeholder text
        logo_font = get_font(int(14 * scale), bold=True)
        draw.text((int(80 * scale), int(70 * scale)), "BUBBA GUMP", font=logo_font, fill="#FFFFFF", anchor="mm")
        title_x = int(180 * scale)
    
    # Title - "TOP 10 PERFORMERS" on first line - positioned for larger header
    draw.text((title_x, int(45 * scale)), "TOP 10 PERFORMERS", font=font_title_top, fill="#FFFFFF", anchor="lm")
    
    # "BY METRIC" on second line (larger, bolder) - more spacing
    draw.text((title_x, int(100 * scale)), "BY METRIC", font=font_title_main, fill="#FFFFFF", anchor="lm")
    
    # Quarter and Year on right side - adjusted for larger header
    quarter_x = width - int(130 * scale)
    quarter_num = quarter.replace("Q", "")
    draw.text((quarter_x, int(35 * scale)), f"QUARTER {quarter_num}", font=font_quarter, fill="#FFFFFF", anchor="mm")
    draw.text((quarter_x, int(80 * scale)), str(year), font=font_year, fill="#FFFFFF", anchor="mm")
    
    # Data date below year (if provided)
    if data_date:
        font_date = get_font(int(16 * scale), bold=False)
        # Format date nicely (e.g., "2026-01-15" -> "Data as of Jan 15")
        try:
            from datetime import datetime
            if isinstance(data_date, str):
                dt = datetime.fromisoformat(data_date.replace('Z', '+00:00'))
            else:
                dt = data_date
            date_str = f"Data as of {dt.strftime('%b %d')}"
        except:
            date_str = f"Data as of {data_date}"
        draw.text((quarter_x, int(115 * scale)), date_str, font=font_date, fill="#AACCFF", anchor="mm")
    
    # === METRICS SECTION - FULL WIDTH ===
    
    # Define the 4 metrics to display
    metrics = [
        {"key": "ppa", "label": "PPA - Top 10", "format": "currency", "higher_better": True},
        {"key": "glassware_per_guest", "label": "Glass/Guest - Top 10", "format": "currency", "higher_better": True},
        {"key": "guests_per_lsc", "label": "Guests/LSC - Top 10", "format": "number", "higher_better": False},
        {"key": "lbw_per_guest", "label": "LBW/Guest - Top 10", "format": "currency", "higher_better": True},
    ]
    
    # Calculate column widths - TRUE FULL WIDTH
    num_cols = 4
    col_gap = int(4 * scale)  # Tiny gap between columns
    total_gap = col_gap * (num_cols - 1)
    col_width = (width - total_gap) // num_cols
    table_start_y = header_height + int(5 * scale)
    
    # Calculate available height for rows
    available_height = height - table_start_y - int(5 * scale)
    metric_header_height = int(40 * scale)
    col_header_height = int(35 * scale)
    row_area_height = available_height - metric_header_height - col_header_height
    row_height = row_area_height // 10  # Exactly 10 rows
    
    # Column internal layout - proportional widths
    rank_col_pct = 0.18  # 18% for rank
    value_col_pct = 0.25  # 25% for value
    name_col_pct = 1.0 - rank_col_pct - value_col_pct  # Rest for name
    
    # Process employee data for each metric
    for col_idx, metric in enumerate(metrics):
        col_x = col_idx * (col_width + col_gap)
        col_right = col_x + col_width
        
        # Internal column positions
        rank_col_w = int(col_width * rank_col_pct)
        value_col_w = int(col_width * value_col_pct)
        name_col_w = col_width - rank_col_w - value_col_w
        
        rank_divider_x = col_x + rank_col_w
        value_divider_x = col_right - value_col_w
        
        # Sort employees by this metric
        metric_key = metric["key"]
        valid_employees = [e for e in employees if e.get(metric_key) is not None]
        
        if metric["higher_better"]:
            sorted_emps = sorted(valid_employees, key=lambda e: float(e.get(metric_key, 0) or 0), reverse=True)
        else:
            sorted_emps = sorted(valid_employees, key=lambda e: float(e.get(metric_key, 999999) or 999999))
        
        top_10 = sorted_emps[:10]
        
        # === DRAW METRIC HEADER (dark gray bar) ===
        metric_header_y = table_start_y
        draw.rectangle([col_x, metric_header_y, col_right, metric_header_y + metric_header_height],
                       fill=metric_header_bg)
        draw.text((col_x + col_width // 2, metric_header_y + metric_header_height // 2), 
                  metric["label"], font=font_metric_header, fill="#FFFFFF", anchor="mm")
        
        # === DRAW COLUMN SUB-HEADERS (light blue bar) ===
        col_header_y = metric_header_y + metric_header_height
        draw.rectangle([col_x, col_header_y, col_right, col_header_y + col_header_height],
                       fill=col_header_bg)
        
        # Column header text - centered in each sub-column
        draw.text((col_x + rank_col_w // 2, col_header_y + col_header_height // 2), 
                  "Rank", font=font_col_header, fill="#FFFFFF", anchor="mm")
        draw.text((rank_divider_x + name_col_w // 2, col_header_y + col_header_height // 2), 
                  "Employee", font=font_col_header, fill="#FFFFFF", anchor="mm")
        draw.text((value_divider_x + value_col_w // 2, col_header_y + col_header_height // 2), 
                  "Value", font=font_col_header, fill="#FFFFFF", anchor="mm")
        
        # Draw vertical dividers in header
        draw.line([(rank_divider_x, col_header_y), (rank_divider_x, col_header_y + col_header_height)], 
                 fill="#3A6A8A", width=2)
        draw.line([(value_divider_x, col_header_y), (value_divider_x, col_header_y + col_header_height)], 
                 fill="#3A6A8A", width=2)
        
        # === DRAW DATA ROWS ===
        row_y = col_header_y + col_header_height
        
        for rank, emp in enumerate(top_10, 1):
            # Solid alternating row colors (white and light grey)
            row_color = row_light if rank % 2 == 0 else row_white
            draw.rectangle([col_x, row_y, col_right, row_y + row_height], fill=row_color)
            
            # Horizontal divider line after each row
            draw.line([(col_x, row_y + row_height), (col_right, row_y + row_height)], 
                     fill="#CCCCCC", width=1)
            
            # Vertical dividers in data rows
            draw.line([(rank_divider_x, row_y), (rank_divider_x, row_y + row_height)], 
                     fill="#CCCCCC", width=1)
            draw.line([(value_divider_x, row_y), (value_divider_x, row_y + row_height)], 
                     fill="#CCCCCC", width=1)
            
            # Rank badge (blue circle with white text) - consistent size for all ranks
            badge_x = col_x + rank_col_w // 2
            badge_y = row_y + row_height // 2
            badge_radius = int(22 * scale)  # Optimized size for readable "#10"
            draw.ellipse([badge_x - badge_radius, badge_y - badge_radius,
                         badge_x + badge_radius, badge_y + badge_radius],
                        fill=rank_badge_bg)
            # Font sized to fit #10 comfortably - larger font for better readability
            font_badge = get_font(int(14 * scale), bold=True)
            rank_text = f"#{rank}"
            draw.text((badge_x, badge_y), rank_text, font=font_badge, fill="#FFFFFF", anchor="mm")
            
            # Employee name - First name only, centered in name column
            full_name = emp.get("name", "Unknown")
            name = full_name.split()[0] if full_name else "Unknown"  # First name only
            if len(name) > 10:
                name = name[:9] + ".."
            draw.text((rank_divider_x + name_col_w // 2, badge_y), 
                      name, font=font_name, fill=text_dark, anchor="mm")
            
            # Value (formatted) - centered in value column
            value = emp.get(metric_key, 0)
            if metric["format"] == "currency":
                value_text = f"${float(value or 0):.2f}"
            else:
                value_text = f"{float(value or 0):.1f}"
            
            draw.text((value_divider_x + value_col_w // 2, badge_y), 
                      value_text, font=font_value, fill=text_dark, anchor="mm")
            
            row_y += row_height
        
        # Fill remaining rows if less than 10 employees
        remaining_rank = len(top_10)
        while remaining_rank < 10:
            remaining_rank += 1
            # Solid alternating row colors
            row_color = row_light if remaining_rank % 2 == 0 else row_white
            draw.rectangle([col_x, row_y, col_right, row_y + row_height], fill=row_color)
            # Horizontal divider line
            draw.line([(col_x, row_y + row_height), (col_right, row_y + row_height)], 
                     fill="#CCCCCC", width=1)
            # Vertical dividers
            draw.line([(rank_divider_x, row_y), (rank_divider_x, row_y + row_height)], 
                     fill="#CCCCCC", width=1)
            draw.line([(value_divider_x, row_y), (value_divider_x, row_y + row_height)], 
                     fill="#CCCCCC", width=1)
            row_y += row_height
        
        # Store column boundaries
        col_table_top = metric_header_y
        col_table_bottom = row_y
        
        # Draw thick outer border for this column (BLACK, 3px width)
        draw.rectangle([col_x, col_table_top, col_right, col_table_bottom],
                      outline="#000000", width=3)
    
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
        
        # Employee name - First name only
        full_name = emp.get("name", "Unknown")
        name = full_name.split()[0] if full_name else "Unknown"  # First name only
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
    title_y = 240
    center_x = left_width // 2
    
    draw.text((center_x, title_y), f"{quarter} SERVER", font=get_font(28, bold=True),
              fill=COLORS["white"], anchor="mm")
    draw.text((center_x, title_y + 45), "PERFORMANCE", font=get_font(34, bold=True),
              fill=COLORS["title_red"], anchor="mm")
    draw.text((center_x, title_y + 90), "SNAPSHOT", font=get_font(32, bold=True),
              fill=COLORS["title_red"], anchor="mm")
    draw.text((center_x, title_y + 130), f"March 01, {year}", font=get_font(22, bold=True),
              fill=COLORS["title_red"], anchor="mm")
    
    # Performance Legend (like in the prior version)
    legend_y = title_y + 180
    legend_items = [
        ((34, 197, 94), "EXCEEDING ALL", "EXPECTATIONS"),      # Green
        ((6, 182, 212), "MEETING", "EXPECTATIONS"),            # Cyan
        ((234, 179, 8), "WORK IN", "PROGRESS"),                # Yellow
        ((239, 68, 68), "NEEDS IMMEDIATE", "IMPROVEMENT"),     # Red
    ]
    
    for i, (color, line1, line2) in enumerate(legend_items):
        y = legend_y + i * 70
        bar_width = 8
        legend_start_x = 30
        # Draw vertical color bar
        draw.rectangle([legend_start_x, y, legend_start_x + bar_width, y + 50], fill=color)
        # Draw text
        draw.text((legend_start_x + bar_width + 15, y + 10), line1, 
                  font=get_font(18, bold=True), fill=color, anchor="lm")
        draw.text((legend_start_x + bar_width + 15, y + 32), line2, 
                  font=get_font(18, bold=True), fill=color, anchor="lm")
    
    # Footer message
    footer_y = height - 130
    draw.text((center_x, footer_y), "DON'T WAIT TO IMPACT", 
              font=get_font(16, bold=True), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 22), "THIS NUMBER.",
              font=get_font(16, bold=True), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 50), "IF YOU HAVE QUESTIONS",
              font=get_font(14, bold=True), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 70), "PLEASE SEE MANAGEMENT.",
              font=get_font(14, bold=True), fill=COLORS["white"], anchor="mm")
    
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
        {"name": "Rank", "width": base_col_width - 10},
        {"name": "Employee Name", "width": base_col_width + 60},  # Name gets extra
        {"name": "PPA", "width": base_col_width},
        {"name": "LBW", "width": base_col_width},
        {"name": "GLASS", "width": base_col_width},
        {"name": "LSC", "width": base_col_width},
        {"name": "Review Bonus", "width": base_col_width + 10},
        {"name": "Metric Bonus", "width": base_col_width + 10},
        {"name": "Total Score", "width": base_col_width - 10},
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
    
    # Fonts - BOLDER with subtle outline visibility
    font_data = get_font(14, bold=True)
    font_rank = get_font(16, bold=True)  # Slightly larger for readability
    font_score = get_font(16, bold=True)  # Slightly larger for readability
    
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
        rank_x = col_x[0] + columns[0]["width"] // 2
        
        # Draw outlined rank text with subtle black stroke - 1px for cleaner look
        outline_width = 1
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((rank_x + dx, row_cy + dy), rank_text, font=font_rank, fill="#000000", anchor="mm")
        draw.text((rank_x, row_cy), rank_text, font=font_rank, fill=tier_color, anchor="mm")
        
        # Name - First name only (left aligned, no outline needed)
        full_name = emp.get("name", "Unknown")
        name = full_name.split()[0][:18] if full_name else "Unknown"  # First name only
        draw.text((col_x[1] + 8, row_cy), name, font=font_data, fill="#222222", anchor="lm")
        
        # Helper function to get performance color based on score percentage
        def get_metric_color(score_pct):
            """
            Returns background color based on performance level:
            - Green (#22C55E): >= 110% (Exceeding)
            - Cyan (#06B6D4): 100-109% (Meeting)
            - Yellow (#EAB308): 80-99% (Work in Progress)
            - Red (#EF4444): < 80% (Needs Improvement)
            """
            if score_pct is None or score_pct == 0:
                return None  # No color for missing data
            if score_pct >= 110:
                return (34, 197, 94)  # Green
            elif score_pct >= 100:
                return (6, 182, 212)  # Cyan
            elif score_pct >= 80:
                return (234, 179, 8)  # Yellow
            else:
                return (239, 68, 68)  # Red
        
        # Helper to draw colored cell background
        def draw_metric_cell(col_idx, value, format_str, score_pct=None):
            cell_x = col_x[col_idx]
            cell_w = columns[col_idx]["width"]
            cell_color = get_metric_color(score_pct) if score_pct else None
            
            # Draw colored background if applicable
            if cell_color:
                draw.rectangle([cell_x + 1, y + 1, cell_x + cell_w - 1, y + row_h - 1], fill=cell_color)
            
            # Draw text
            text = format_str.format(value) if value else "-"
            text_color = "#FFFFFF" if cell_color else "#222222"
            draw.text((cell_x + cell_w // 2, row_cy), text, font=font_data, fill=text_color, anchor="mm")
        
        # PPA - use percentage score for display and color coding
        ppa_score = emp.get("score_ppa", 0) or 0
        draw_metric_cell(2, ppa_score, "{:.2f}", ppa_score)
        
        # LBW - use percentage score for display and color coding
        lbw_score = emp.get("score_lbw", 0) or 0
        draw_metric_cell(3, lbw_score, "{:.2f}", lbw_score)
        
        # Glass - use percentage score for display and color coding
        glass_score = emp.get("score_glass", 0) or 0
        draw_metric_cell(4, glass_score, "{:.2f}", glass_score)
        
        # LSC - use percentage score for display and color coding
        lsc_score = emp.get("score_lsc", 0) or 0
        draw_metric_cell(5, lsc_score, "{:.2f}", lsc_score)
        
        # Review Bonus = CV Score + RT Bonus (combined customer feedback bonus)
        cv_score = emp.get("cv_score", 0) or 0
        rt_bonus = emp.get("review_tracker_bonus", 0) or 0
        review_combined = cv_score + rt_bonus
        review_color = (34, 197, 94) if review_combined > 0 else None
        if review_color:
            draw.rectangle([col_x[6] + 1, y + 1, col_x[6] + columns[6]["width"] - 1, y + row_h - 1], fill=review_color)
        review_text = f"+{review_combined:.1f}" if review_combined > 0 else "-"
        draw.text((col_x[6] + columns[6]["width"] // 2, row_cy), review_text,
                  font=font_data, fill="#FFFFFF" if review_color else "#222222", anchor="mm")
        
        # Metric Bonus - green if positive
        metric_bonus = emp.get("total_metric_bonus", 0) or 0
        metric_color = (34, 197, 94) if metric_bonus > 0 else None
        if metric_color:
            draw.rectangle([col_x[7] + 1, y + 1, col_x[7] + columns[7]["width"] - 1, y + row_h - 1], fill=metric_color)
        metric_text = f"{metric_bonus:.2f}" if metric_bonus > 0 else "0.00"
        draw.text((col_x[7] + columns[7]["width"] // 2, row_cy), metric_text,
                  font=font_data, fill="#FFFFFF" if metric_color else "#222222", anchor="mm")
        
        # Total Score - colored background based on tier
        total = emp.get("total_score", 0) or emp.get("pre_dar_score", 0) or 0
        score_text = f"{total:.2f}"
        score_x = col_x[8] + columns[8]["width"] // 2
        
        # Color the Total Score cell based on tier
        tier_bg_colors = {
            "Trainer": (34, 197, 94),    # Green
            "Bartender": (59, 130, 246), # Blue
            "A-Server": (34, 197, 94),   # Green
            "B-Server": (234, 179, 8),   # Yellow
            "C-Server": (239, 68, 68)    # Red
        }
        score_bg = tier_bg_colors.get(tier, (240, 240, 240))
        draw.rectangle([col_x[8] + 1, y + 1, col_x[8] + columns[8]["width"] - 1, y + row_h - 1], fill=score_bg)
        
        # Draw score text in white
        draw.text((score_x, row_cy), score_text, font=font_score, fill="#FFFFFF", anchor="mm")
    
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
        
        # Name - First name only
        full_name = emp.get("name", "Unknown")
        name = full_name.split()[0][:20] if full_name else "Unknown"  # First name only
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
    """Generate Most Improved slide - consistent with Top 10 design."""
    # Set dimensions based on format
    if output_format == "letter":
        width, height = 2550, 3300
        scale = 1.5
    else:
        width, height = SLIDE_WIDTH, SLIDE_HEIGHT
        scale = 1.0
    
    # White background like Top 10
    img = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Header - consistent with Top 10
    header_height = int(145 * scale)
    draw.rectangle([0, 0, width, header_height], fill=(13, 59, 102))
    
    # Load logo
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    try:
        logo_img = Image.open(logo_path).convert('RGBA')
        logo_h = int(125 * scale)
        aspect = logo_img.width / logo_img.height
        logo_w = int(logo_h * aspect)
        logo_img = logo_img.resize((logo_w, logo_h), Image.LANCZOS)
        img.paste(logo_img, (int(10 * scale), int(10 * scale)), logo_img)
        title_x = int(10 * scale) + logo_w + int(25 * scale)
    except:
        title_x = int(30 * scale)
    
    # Bold title fonts - matching Top 10 style
    font_title_top = get_font(int(52 * scale), bold=True)
    font_title_main = get_font(int(72 * scale), bold=True)
    font_quarter = get_font(int(28 * scale), bold=True)
    font_year = get_font(int(48 * scale), bold=True)
    font_explanation = get_font(int(16 * scale), bold=False)
    
    # Title - "MOST IMPROVED" with bold styling
    draw.text((title_x, int(45 * scale)), "MOST IMPROVED", font=font_title_top, fill="#FFFFFF", anchor="lm")
    draw.text((title_x, int(100 * scale)), "PERFORMERS", font=font_title_main, fill="#FFFFFF", anchor="lm")
    
    # Quarter and Year on RIGHT side
    quarter_x = width - int(130 * scale)
    quarter_num = quarter.replace("Q", "")
    draw.text((quarter_x, int(35 * scale)), f"QUARTER {quarter_num}", font=font_quarter, fill="#FFFFFF", anchor="mm")
    draw.text((quarter_x, int(80 * scale)), str(year), font=font_year, fill="#FFFFFF", anchor="mm")
    
    # Explanation text - compared to previous quarter
    prev_quarter = f"Q{int(quarter_num) - 1}" if int(quarter_num) > 1 else "Q4"
    prev_year = year if int(quarter_num) > 1 else year - 1
    draw.text((quarter_x, int(115 * scale)), f"vs {prev_quarter} {prev_year} Final", font=font_explanation, fill="#AACCFF", anchor="mm")
    
    font_rank = get_font(int(42 * scale), bold=True)
    font_name = get_font(int(36 * scale), bold=True)
    font_change = get_font(int(32 * scale), bold=True)
    font_score = get_font(int(30 * scale))
    
    # Content starts below header
    content_y = header_height + int(20 * scale)
    
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
    
    start_y = content_y + int(20 * scale)
    row_height = int(80 * scale)
    
    # Draw improvements list
    for idx, emp in enumerate(improvements[:8]):
        y = start_y + idx * row_height
        row_color = (235, 235, 235) if idx % 2 == 0 else (255, 255, 255)
        draw.rectangle([int(50 * scale), y, width - int(50 * scale), y + row_height - 5], fill=row_color)
        
        # Rank badge
        badge_x = int(100 * scale)
        badge_y = y + row_height // 2
        badge_color = "#FFD700" if idx == 0 else "#C0C0C0" if idx == 1 else "#CD7F32" if idx == 2 else "#1E5FA8"
        draw.ellipse([badge_x - 25, badge_y - 25, badge_x + 25, badge_y + 25], fill=badge_color)
        draw.text((badge_x, badge_y), f"#{idx + 1}", font=get_font(int(14 * scale), bold=True), fill="#FFFFFF", anchor="mm")
        
        # Name - First name only
        first_name = emp["name"].split()[0][:18] if emp.get("name") else "Unknown"
        draw.text((int(180 * scale), badge_y), first_name, font=font_name, fill="#222222", anchor="lm")
        
        # Change with arrow
        change_text = f"+{emp['change']:.1f}"
        draw.text((int(600 * scale), badge_y), change_text, font=font_change, fill="#22C55E", anchor="mm")
        
        # Score progression
        progression = f"{emp['prev_score']:.1f} → {emp['current_score']:.1f}"
        draw.text((width - int(100 * scale), badge_y), progression, font=font_score, fill="#666666", anchor="rm")
    
    if not improvements:
        font_no_data = get_font(int(28 * scale))
        draw.text((width//2, int(450 * scale)), "No improvement data available", font=font_no_data, fill="#666666", anchor="mm")
    
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
    """Generate Promotion Watchlist slide - consistent with Top 10 design."""
    # Set dimensions based on format
    if output_format == "letter":
        width, height = 2550, 3300
        scale = 1.5
    else:
        width, height = SLIDE_WIDTH, SLIDE_HEIGHT
        scale = 1.0
    
    # White background like Top 10
    img = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Header - consistent with Top 10
    header_height = int(120 * scale)
    draw.rectangle([0, 0, width, header_height], fill=(13, 59, 102))
    
    # Load logo
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    try:
        logo_img = Image.open(logo_path).convert('RGBA')
        logo_h = int(100 * scale)
        aspect = logo_img.width / logo_img.height
        logo_w = int(logo_h * aspect)
        logo_img = logo_img.resize((logo_w, logo_h), Image.LANCZOS)
        img.paste(logo_img, (int(10 * scale), int(10 * scale)), logo_img)
        title_x = int(10 * scale) + logo_w + int(20 * scale)
    except:
        title_x = int(30 * scale)
    
    font_title = get_font(int(48 * scale), bold=True)
    font_subtitle = get_font(int(28 * scale))
    draw.text((title_x, int(35 * scale)), "PROMOTION WATCHLIST", font=font_title, fill="#FFFFFF", anchor="lm")
    draw.text((title_x, int(85 * scale)), f"{quarter} {year} • Almost A-Server! (threshold: {a_server_threshold})", font=font_subtitle, fill="#AACCFF", anchor="lm")
    
    font_rank = get_font(int(38 * scale), bold=True)
    font_name = get_font(int(34 * scale), bold=True)
    font_gap = get_font(int(28 * scale), bold=True)
    font_score = get_font(int(28 * scale))
    
    # Find B-Servers close to A threshold
    watchlist = []
    for emp in rankings:
        if emp.get("tier_label") == "B-Server":
            score = emp.get("total_score", 0)
            gap = a_server_threshold - score
            if 0 < gap <= 10:
                watchlist.append({"name": emp.get("name"), "score": score, "gap": gap, "position_label": emp.get("position_label")})
    
    watchlist.sort(key=lambda x: x["gap"])
    
    # Content area starts after header
    start_y = int(150 * scale)
    row_height = int(90 * scale)
    
    for idx, emp in enumerate(watchlist[:8]):
        y = start_y + idx * row_height
        row_color = (235, 235, 235) if idx % 2 == 0 else (255, 255, 255)
        draw.rectangle([int(50 * scale), y, width - int(50 * scale), y + row_height - 5], fill=row_color)
        
        draw.text((int(140 * scale), y + int(35 * scale)), emp["position_label"], font=font_rank, fill=TIER_CONFIG["B-Server"]["color"])
        draw.text((int(280 * scale), y + int(38 * scale)), emp["name"][:18], font=font_name, fill="#222222")
        
        # Gap indicator with progress bar
        gap_pct = 1 - (emp["gap"] / 10)
        bar_width = int(150 * scale)
        bar_x = int(680 * scale)
        draw.rounded_rectangle([bar_x, y + int(35 * scale), bar_x + bar_width, y + int(45 * scale)], radius=5, fill="#CCCCCC")
        draw.rounded_rectangle([bar_x, y + int(35 * scale), bar_x + int(bar_width * gap_pct), y + int(45 * scale)], radius=5, fill=TIER_CONFIG["A-Server"]["color"])
        
        draw.text((bar_x + bar_width + int(15 * scale), y + int(38 * scale)), f"{emp['gap']:.1f} pts to go", font=font_gap, fill="#D4A017")
        draw.text((width - int(150 * scale), y + int(38 * scale)), f"{emp['score']:.1f}", font=font_score, fill="#666666", anchor="rt")
    
    if not watchlist:
        font_no_data = get_font(int(28 * scale))
        draw.text((width//2, int(450 * scale)), "No B-Servers within 10 points of A-Server", font=font_no_data, fill="#22C55E", anchor="mm")
    
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
    """Generate At Risk / Coaching Focus slide - consistent with Top 10 design."""
    # Set dimensions based on format
    if output_format == "letter":
        width, height = 2550, 3300
        scale = 1.5
    else:
        width, height = SLIDE_WIDTH, SLIDE_HEIGHT
        scale = 1.0
    
    # White background like Top 10
    img = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Header - consistent with Top 10
    header_height = int(120 * scale)
    draw.rectangle([0, 0, width, header_height], fill=(13, 59, 102))
    
    # Load logo
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    try:
        logo_img = Image.open(logo_path).convert('RGBA')
        logo_h = int(100 * scale)
        aspect = logo_img.width / logo_img.height
        logo_w = int(logo_h * aspect)
        logo_img = logo_img.resize((logo_w, logo_h), Image.LANCZOS)
        img.paste(logo_img, (int(10 * scale), int(10 * scale)), logo_img)
        title_x = int(10 * scale) + logo_w + int(20 * scale)
    except:
        title_x = int(30 * scale)
    
    font_title = get_font(int(48 * scale), bold=True)
    font_subtitle = get_font(int(28 * scale))
    draw.text((title_x, int(35 * scale)), "COACHING FOCUS", font=font_title, fill="#FFFFFF", anchor="lm")
    draw.text((title_x, int(85 * scale)), f"{quarter} {year}", font=font_subtitle, fill="#AACCFF", anchor="lm")
    
    font_warning = get_font(int(22 * scale), bold=True)
    font_rank = get_font(int(36 * scale), bold=True)
    font_name = get_font(int(32 * scale), bold=True)
    font_gap = get_font(int(26 * scale))
    font_score = get_font(int(28 * scale))
    
    # Content area starts after header
    content_y = header_height + int(20 * scale)
    
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
        row_color = (235, 235, 235) if idx % 2 == 0 else (255, 255, 255)
        draw.rectangle([int(50 * scale), y, width - int(50 * scale), y + row_height - 5], fill=row_color)
        
        draw.text((int(140 * scale), y + int(35 * scale)), emp.get("position_label", "C"), font=font_rank, fill="#DC2626")
        draw.text((int(250 * scale), y + int(38 * scale)), emp["name"][:18], font=font_name, fill="#222222")
        draw.text((int(700 * scale), y + int(40 * scale)), f"{emp['gap']:.1f} pts needed", font=font_gap, fill="#F59E0B")
        draw.text((width - int(150 * scale), y + int(38 * scale)), f"{emp['score']:.1f}", font=font_score, fill="#666666", anchor="rt")
    
    if not at_risk:
        font_no_data = get_font(int(28 * scale))
        draw.text((width//2, int(450 * scale)), "No C-Servers - Great job team!", font=font_no_data, fill="#22C55E", anchor="mm")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def generate_printable_rankings_slide(
    rankings: List[Dict[str, Any]], 
    quarter: str, 
    year: int,
    output_format: str = "16:9"
) -> bytes:
    """
    Generate a stylized printable rankings slide with word art headers.
    Groups employees by tier with decorative elements - no metrics, just rank and name.
    
    Tiers: RED HATS (Trainers), A, B, C, BAR (Bartenders), UNRANKED
    """
    # Set dimensions based on format
    if output_format == "letter":
        width, height = 2550, 3300
        scale = 1.5
    else:
        width, height = SLIDE_WIDTH, SLIDE_HEIGHT
        scale = 1.0
    
    # Create dark background
    img = Image.new('RGB', (width, height), (15, 20, 30))
    draw = ImageDraw.Draw(img)
    
    # Add subtle gradient
    for y in range(height):
        ratio = y / height
        darkness = int(15 + ratio * 10)
        draw.line([(0, y), (width, y)], fill=(darkness, darkness + 5, darkness + 15))
    
    # Add sparkle/confetti effects
    random.seed(42)  # Consistent random
    gold_color = (255, 215, 0)
    
    # Draw confetti ribbons
    for _ in range(30):
        x = random.randint(0, width)
        y = random.randint(0, height)
        ribbon_len = random.randint(20, 60)
        angle = random.randint(-45, 45)
        alpha = random.randint(40, 120)
        ribbon_color = random.choice([gold_color, (200, 180, 100), (255, 230, 150)])
        # Draw diagonal ribbon
        end_x = x + int(ribbon_len * math.cos(math.radians(angle)))
        end_y = y + int(ribbon_len * math.sin(math.radians(angle)))
        draw.line([(x, y), (end_x, end_y)], fill=ribbon_color, width=random.randint(2, 4))
    
    # Draw sparkle dots
    for _ in range(50):
        x = random.randint(0, width)
        y = random.randint(0, height)
        size = random.randint(2, 6)
        alpha = random.randint(80, 200)
        draw.ellipse([x-size, y-size, x+size, y+size], fill=(255, 255, 200))
    
    # 40% ZOOM increase (more zoomed in)
    zoom = 1.4
    
    # Helper function for word art text (text with outline) - CENTERED with anchor
    def draw_word_art(draw, pos, text, font, fill_color, outline_color, outline_width=3):
        x, y = pos
        # Draw outline
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, font=font, fill=outline_color, anchor="mt")
        # Draw fill - anchor="mt" means middle-top (horizontally centered)
        draw.text((x, y), text, font=font, fill=fill_color, anchor="mt")
    
    # Helper function to draw a tier table - with zoom factor
    def draw_tier_table(draw, x, y, employees, rank_prefix="", table_width=None, row_height=None):
        if not employees:
            return 0
        
        tw = table_width or int(200 * scale * zoom)
        rh = row_height or int(38 * scale * zoom)
        rank_col_w = int(tw * 0.35)
        name_col_w = int(tw * 0.65)
        
        font_rank = get_font(int(18 * scale * zoom), bold=True)
        font_name = get_font(int(18 * scale * zoom), bold=True)
        
        border_color = (255, 255, 255)
        
        for idx, emp in enumerate(employees):
            row_y = y + idx * rh
            
            # Draw cell borders
            # Rank cell
            draw.rectangle([x, row_y, x + rank_col_w, row_y + rh], outline=border_color, width=2)
            # Name cell
            draw.rectangle([x + rank_col_w, row_y, x + tw, row_y + rh], outline=border_color, width=2)
            
            # Draw rank text
            rank_text = f"{rank_prefix}{idx + 1}" if rank_prefix else str(idx + 1)
            draw.text((x + rank_col_w // 2, row_y + rh // 2), rank_text, 
                     font=font_rank, fill=(255, 255, 255), anchor="mm")
            
            # Draw name text
            name = emp.get("name", "Unknown")
            if len(name) > 12:
                name = name[:11] + "."
            draw.text((x + rank_col_w + name_col_w // 2, row_y + rh // 2), name.upper(), 
                     font=font_name, fill=(255, 255, 255), anchor="mm")
        
        return len(employees) * rh
    
    # Sort employees into tiers
    tier_groups = {
        "trainers": [],
        "a_servers": [],
        "b_servers": [],
        "c_servers": [],
        "bartenders": [],
        "unranked": []
    }
    
    tier_counters = {"Trainer": 0, "A-Server": 0, "B-Server": 0, "C-Server": 0, "Bartender": 0}
    
    for emp in rankings:
        tier = emp.get("tier_label", "")
        if tier == "Trainer":
            tier_counters["Trainer"] += 1
            tier_groups["trainers"].append(emp)
        elif tier == "A-Server":
            tier_counters["A-Server"] += 1
            tier_groups["a_servers"].append(emp)
        elif tier == "B-Server":
            tier_counters["B-Server"] += 1
            tier_groups["b_servers"].append(emp)
        elif tier == "C-Server":
            tier_counters["C-Server"] += 1
            tier_groups["c_servers"].append(emp)
        elif tier == "Bartender":
            tier_counters["Bartender"] += 1
            tier_groups["bartenders"].append(emp)
        else:
            tier_groups["unranked"].append(emp)
    
    # Fonts for word art headers (zoom already defined above)
    font_header_large = get_font(int(80 * scale * zoom), bold=True)
    font_header_medium = get_font(int(60 * scale * zoom), bold=True)
    font_header_small = get_font(int(45 * scale * zoom), bold=True)
    
    # Colors
    red_color = (200, 50, 50)
    gold_outline = (200, 170, 50)
    white_color = (255, 255, 255)
    black_outline = (30, 30, 30)
    
    # Layout - FULL WIDTH with 20% zoom and alternating vertical offsets
    table_width = int(220 * scale * zoom)
    row_height = int(40 * scale * zoom)
    
    # Collect active tiers in order: Red Hats, Bar, A, B, C, Unranked
    active_tiers = []
    if tier_groups["trainers"]:
        active_tiers.append(("trainers", "RED\nHATS", "T", red_color, white_color))
    if tier_groups["bartenders"]:
        active_tiers.append(("bartenders", "BAR", "Bar ", red_color, None))
    if tier_groups["a_servers"]:
        active_tiers.append(("a_servers", "A", "A", gold_outline, None))
    if tier_groups["b_servers"]:
        active_tiers.append(("b_servers", "B", "B", white_color, None))
    if tier_groups["c_servers"]:
        active_tiers.append(("c_servers", "C", "C", (180, 140, 100), None))
    if tier_groups["unranked"]:
        active_tiers.append(("unranked", "UNRANKED", "NR", gold_outline, None))
    
    num_tiers = len(active_tiers)
    if num_tiers == 0:
        # No data - just return empty slide
        buffer = io.BytesIO()
        img.save(buffer, format='PNG', optimize=True)
        buffer.seek(0)
        return buffer.getvalue()
    
    # Calculate column positions - spread full width
    margin = int(40 * scale)
    usable_width = width - (margin * 2)
    col_width = usable_width // num_tiers
    
    # Vertical positioning - alternating up/down from center
    center_y = height // 2
    vertical_offset = int(height * 0.10)  # 10% alternating offset
    
    # Draw each tier column
    for col_idx, (tier_key, header_text, rank_prefix, header_color, header_color2) in enumerate(active_tiers):
        employees = tier_groups[tier_key]
        
        # Column X position (centered in column)
        col_center_x = margin + (col_idx * col_width) + (col_width // 2)
        table_x = col_center_x - (table_width // 2)
        
        # Calculate header height for positioning table
        if "\n" in header_text:
            header_height = int(160 * scale * zoom)  # Two-line header
        elif header_text == "UNRANKED":
            header_height = int(70 * scale * zoom)
        else:
            header_height = int(100 * scale * zoom)
        
        # Calculate total content height
        table_height = len(employees[:15]) * row_height
        total_content_height = header_height + table_height
        
        # Alternating vertical offset: even columns (0,2,4) UP, odd columns (1,3,5) DOWN
        if col_idx % 2 == 0:
            # Even index columns go UP (10% above center)
            content_start_y = center_y - (total_content_height // 2) - vertical_offset
        else:
            # Odd index columns go DOWN (10% below center)
            content_start_y = center_y - (total_content_height // 2) + vertical_offset
        
        # Draw header
        if header_text == "RED\nHATS":
            # Two-line header for RED HATS
            draw_word_art(draw, (col_center_x, content_start_y), "RED", font_header_large, 
                         header_color, gold_outline, int(4 * scale * zoom))
            draw_word_art(draw, (col_center_x, content_start_y + int(70 * scale * zoom)), "HATS", font_header_large, 
                         header_color2 or white_color, gold_outline, int(4 * scale * zoom))
            table_y = content_start_y + header_height
        elif header_text == "UNRANKED":
            draw_word_art(draw, (col_center_x, content_start_y), header_text, font_header_small, 
                         header_color, black_outline, int(3 * scale * zoom))
            table_y = content_start_y + header_height
        elif header_text == "BAR":
            draw_word_art(draw, (col_center_x, content_start_y), header_text, font_header_medium, 
                         header_color, gold_outline, int(3 * scale * zoom))
            table_y = content_start_y + header_height
        else:
            # Single letter headers (A, B, C)
            draw_word_art(draw, (col_center_x, content_start_y), header_text, font_header_large, 
                         header_color, gold_outline if header_text != "A" else black_outline, int(4 * scale * zoom))
            table_y = content_start_y + header_height
        
        # Draw table
        if tier_key == "unranked":
            # Special handling for unranked (NR prefix)
            font_table = get_font(int(18 * scale * zoom), bold=True)
            for idx, emp in enumerate(employees[:10]):
                row_y = table_y + idx * row_height
                rank_col_w = int(table_width * 0.35)
                draw.rectangle([table_x, row_y, table_x + rank_col_w, row_y + row_height], 
                              outline=white_color, width=2)
                draw.rectangle([table_x + rank_col_w, row_y, table_x + table_width, row_y + row_height], 
                              outline=white_color, width=2)
                draw.text((table_x + rank_col_w // 2, row_y + row_height // 2), "NR", 
                         font=font_table, fill=white_color, anchor="mm")
                name = emp.get("name", "Unknown")[:12].upper()
                draw.text((table_x + rank_col_w + (table_width - rank_col_w) // 2, row_y + row_height // 2), 
                         name, font=font_table, fill=white_color, anchor="mm")
        else:
            draw_tier_table(draw, table_x, table_y, employees[:15], rank_prefix, table_width, row_height)
    
    # Add decorative stars scattered around
    def draw_star(draw, cx, cy, size, color):
        points = []
        for i in range(10):
            angle = math.radians(i * 36 - 90)
            r = size if i % 2 == 0 else size * 0.4
            points.append((cx + int(r * math.cos(angle)), cy + int(r * math.sin(angle))))
        draw.polygon(points, fill=color)
    
    # Draw gold stars in gaps between columns
    random.seed(123)
    for col_idx in range(num_tiers - 1):
        col_center_x = margin + (col_idx * col_width) + col_width
        # Add a few stars near column boundaries
        for _ in range(2):
            sx = col_center_x + random.randint(-30, 30)
            sy = random.randint(int(height * 0.7), int(height * 0.9))
            draw_star(draw, sx, sy, int(25 * scale * zoom), (200, 180, 100))
    
    # Store Name and Quarter/Year Header - TOP CENTER
    store_name = "BUBBA GUMP SHRIMP CO."
    font_store = get_font(int(36 * scale * zoom), bold=True)
    font_quarter = get_font(int(28 * scale * zoom), bold=True)
    
    # Draw store name with gold outline at top center
    store_y = int(25 * scale)
    draw_word_art(draw, (width // 2, store_y), store_name, font_store, 
                 (255, 255, 255), gold_outline, int(3 * scale * zoom))
    
    # Draw Quarter/Year below store name
    quarter_y = store_y + int(45 * scale * zoom)
    draw_word_art(draw, (width // 2, quarter_y), f"{quarter} {year} RANKINGS", font_quarter, 
                 gold_outline, black_outline, int(2 * scale * zoom))
    
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
