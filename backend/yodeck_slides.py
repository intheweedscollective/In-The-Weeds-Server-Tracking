"""
Yodeck Slide Generator
Generates 16:9 (1920x1080) PNG slides for digital signage.
Vegas Strip professional - clean, branded, high-contrast.
Supports per-quarter theme customization and seasonal themes.
"""
import io
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, date
import base64
import math

# ============================================================================
# DESIGN CONSTANTS (Vegas Strip Professional)
# ============================================================================

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

# Pre-built themes
THEMES = {
    "dark_navy": {
        "background": "#0A1628",
        "background_gradient": "#132238",
        "primary": "#D12E2E",
        "secondary": "#005B96",
        "text_white": "#FFFFFF",
        "text_light": "#E5E7EB",
        "text_muted": "#9CA3AF",
        "gold": "#FFD700",
        "silver": "#C0C0C0",
        "bronze": "#CD7F32",
    },
    "light_corporate": {
        "background": "#F8FAFC",
        "background_gradient": "#E2E8F0",
        "primary": "#D12E2E",
        "secondary": "#005B96",
        "text_white": "#1E293B",
        "text_light": "#334155",
        "text_muted": "#64748B",
        "gold": "#D97706",
        "silver": "#6B7280",
        "bronze": "#92400E",
    },
    "bubba_red": {
        "background": "#7F1D1D",
        "background_gradient": "#450A0A",
        "primary": "#FEF2F2",
        "secondary": "#FCA5A5",
        "text_white": "#FFFFFF",
        "text_light": "#FEE2E2",
        "text_muted": "#FECACA",
        "gold": "#FFD700",
        "silver": "#E5E7EB",
        "bronze": "#F59E0B",
    },
    "ocean_blue": {
        "background": "#0C4A6E",
        "background_gradient": "#082F49",
        "primary": "#F0F9FF",
        "secondary": "#38BDF8",
        "text_white": "#FFFFFF",
        "text_light": "#E0F2FE",
        "text_muted": "#BAE6FD",
        "gold": "#FCD34D",
        "silver": "#E5E7EB",
        "bronze": "#FB923C",
    },
}

# ============================================================================
# SEASONAL/HOLIDAY THEMES
# ============================================================================

SEASONAL_THEMES = {
    "valentines": {
        "name": "Valentine's Day",
        "background": "#4A0D2A",
        "background_gradient": "#2D0519",
        "primary": "#FF6B9D",
        "secondary": "#FF1493",
        "text_white": "#FFFFFF",
        "text_light": "#FFE4EC",
        "text_muted": "#FFB6C1",
        "gold": "#FFD700",
        "silver": "#FFC0CB",
        "bronze": "#FF69B4",
        "emoji": "💕",
        "decorations": ["heart"],
    },
    "st_patricks": {
        "name": "St. Patrick's Day",
        "background": "#0D3B0D",
        "background_gradient": "#051F05",
        "primary": "#00FF7F",
        "secondary": "#32CD32",
        "text_white": "#FFFFFF",
        "text_light": "#E8F5E9",
        "text_muted": "#A5D6A7",
        "gold": "#FFD700",
        "silver": "#98FB98",
        "bronze": "#228B22",
        "emoji": "🍀",
        "decorations": ["shamrock"],
    },
    "easter": {
        "name": "Easter",
        "background": "#E8E4F0",
        "background_gradient": "#D4C8E8",
        "primary": "#9C27B0",
        "secondary": "#FF9800",
        "text_white": "#4A148C",
        "text_light": "#6A1B9A",
        "text_muted": "#7B1FA2",
        "gold": "#FFD54F",
        "silver": "#CE93D8",
        "bronze": "#FF7043",
        "emoji": "🐣",
        "decorations": ["egg"],
    },
    "july_4th": {
        "name": "4th of July",
        "background": "#0A1628",
        "background_gradient": "#1A237E",
        "primary": "#F44336",
        "secondary": "#2196F3",
        "text_white": "#FFFFFF",
        "text_light": "#E3F2FD",
        "text_muted": "#BBDEFB",
        "gold": "#FFD700",
        "silver": "#E0E0E0",
        "bronze": "#FF5722",
        "emoji": "🇺🇸",
        "decorations": ["star", "firework"],
    },
    "halloween": {
        "name": "Halloween",
        "background": "#1A0A00",
        "background_gradient": "#0D0500",
        "primary": "#FF6600",
        "secondary": "#9C27B0",
        "text_white": "#FFFFFF",
        "text_light": "#FFE0B2",
        "text_muted": "#FFCC80",
        "gold": "#FFD700",
        "silver": "#E0E0E0",
        "bronze": "#FF9800",
        "emoji": "🎃",
        "decorations": ["pumpkin", "bat"],
    },
    "thanksgiving": {
        "name": "Thanksgiving",
        "background": "#3E2723",
        "background_gradient": "#1B0F0A",
        "primary": "#FF8F00",
        "secondary": "#8D6E63",
        "text_white": "#FFFFFF",
        "text_light": "#FFF3E0",
        "text_muted": "#FFE0B2",
        "gold": "#FFD700",
        "silver": "#BCAAA4",
        "bronze": "#A1887F",
        "emoji": "🦃",
        "decorations": ["leaf"],
    },
    "christmas": {
        "name": "Christmas",
        "background": "#0D2818",
        "background_gradient": "#051208",
        "primary": "#FF0000",
        "secondary": "#228B22",
        "text_white": "#FFFFFF",
        "text_light": "#E8F5E9",
        "text_muted": "#C8E6C9",
        "gold": "#FFD700",
        "silver": "#C0C0C0",
        "bronze": "#CD7F32",
        "emoji": "🎄",
        "decorations": ["snowflake", "tree"],
    },
    "new_year": {
        "name": "New Year",
        "background": "#0A0A1A",
        "background_gradient": "#000005",
        "primary": "#FFD700",
        "secondary": "#C0C0C0",
        "text_white": "#FFFFFF",
        "text_light": "#FFF9C4",
        "text_muted": "#FFF59D",
        "gold": "#FFD700",
        "silver": "#E0E0E0",
        "bronze": "#FF8F00",
        "emoji": "🎆",
        "decorations": ["firework", "confetti"],
    },
}

# Holiday date ranges (month, start_day, end_day)
HOLIDAY_DATES = {
    "new_year": [(1, 1, 7)],  # Jan 1-7
    "valentines": [(2, 7, 14)],  # Feb 7-14
    "st_patricks": [(3, 10, 17)],  # Mar 10-17
    "easter": [(3, 25, 31), (4, 1, 21)],  # Late March to mid-April (approximate)
    "july_4th": [(6, 28, 30), (7, 1, 7)],  # Jun 28 - Jul 7
    "halloween": [(10, 24, 31)],  # Oct 24-31
    "thanksgiving": [(11, 18, 28)],  # Nov 18-28 (4th Thursday varies)
    "christmas": [(12, 15, 31)],  # Dec 15-31
}


def get_current_seasonal_theme() -> Optional[str]:
    """
    Auto-detect current seasonal theme based on today's date.
    Returns the theme key or None if no holiday is active.
    """
    today = date.today()
    month = today.month
    day = today.day
    
    for theme_key, date_ranges in HOLIDAY_DATES.items():
        for (m, start_day, end_day) in date_ranges:
            if month == m and start_day <= day <= end_day:
                return theme_key
    
    return None


def get_seasonal_theme_colors(theme_key: str) -> Optional[Dict]:
    """Get colors for a seasonal theme."""
    if theme_key in SEASONAL_THEMES:
        return SEASONAL_THEMES[theme_key]
    return None

# Default colors (dark_navy)
COLORS = THEMES["dark_navy"]

# Tier configuration
TIER_CONFIG = {
    "Trainer": {"color": "#9333EA", "short": "T"},
    "Bartender": {"color": "#2563EB", "short": "BAR"},
    "A-Server": {"color": "#16A34A", "short": "A"},
    "B-Server": {"color": "#CA8A04", "short": "B"},
    "C-Server": {"color": "#DC2626", "short": "C"},
}


def get_theme_colors(theme_name: str = "dark_navy", custom_colors: Dict = None) -> Dict:
    """Get colors for a theme, with optional custom overrides."""
    if theme_name == "custom" and custom_colors:
        base = THEMES["dark_navy"].copy()
        base.update(custom_colors)
        return base
    return THEMES.get(theme_name, THEMES["dark_navy"])


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def create_gradient_background(width: int, height: int, colors: Dict = None, custom_bg_image: str = None) -> Image.Image:
    """Create a gradient background or use custom image."""
    if colors is None:
        colors = COLORS
    
    # If custom background image provided
    if custom_bg_image:
        try:
            if custom_bg_image.startswith('data:'):
                # Base64 encoded image
                img_data = base64.b64decode(custom_bg_image.split(',')[1])
                img = Image.open(io.BytesIO(img_data))
            else:
                # URL - would need to fetch, for now skip
                img = None
            
            if img:
                img = img.convert('RGB')
                img = img.resize((width, height), Image.Resampling.LANCZOS)
                return img
        except Exception:
            pass  # Fall back to gradient
    
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    
    top_color = hex_to_rgb(colors.get("background", "#0A1628"))
    bottom_color = hex_to_rgb(colors.get("background_gradient", "#132238"))
    
    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    return img


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get font - uses system fonts with fallback."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    
    # Fallback to default
    return ImageFont.load_default()


def draw_rounded_rect(draw: ImageDraw.Draw, bbox: Tuple[int, int, int, int], 
                      radius: int, fill: str, outline: str = None):
    """Draw a rounded rectangle."""
    x1, y1, x2, y2 = bbox
    draw.rounded_rectangle(bbox, radius=radius, fill=fill, outline=outline)


def draw_tier_badge(draw: ImageDraw.Draw, x: int, y: int, tier: str, font: ImageFont.FreeTypeFont):
    """Draw a tier badge with color coding."""
    config = TIER_CONFIG.get(tier, TIER_CONFIG["A-Server"])
    badge_color = config["color"]
    badge_text = tier
    
    # Calculate badge size
    text_bbox = draw.textbbox((0, 0), badge_text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    padding_x = 16
    padding_y = 8
    badge_width = text_width + padding_x * 2
    badge_height = text_height + padding_y * 2
    
    # Draw badge background
    draw_rounded_rect(
        draw, 
        (x, y, x + badge_width, y + badge_height),
        radius=6,
        fill=badge_color
    )
    
    # Draw badge text
    draw.text(
        (x + padding_x, y + padding_y - 2),
        badge_text,
        font=font,
        fill=COLORS["text_white"]
    )
    
    return badge_width


def generate_top_10_slide(
    rankings: List[Dict[str, Any]], 
    quarter: str, 
    year: int,
    theme: str = "dark_navy",
    custom_colors: Dict = None,
    custom_bg_image: str = None
) -> bytes:
    """
    Generate Top 10 Performers slide.
    Simple: Rank, Name, Tier Badge, Total Score
    Readable from 15 feet away.
    """
    colors = get_theme_colors(theme, custom_colors)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors, custom_bg_image)
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_title = get_font(64, bold=True)
    font_subtitle = get_font(28)
    font_rank = get_font(48, bold=True)
    font_name = get_font(40, bold=True)
    font_score = get_font(44, bold=True)
    font_tier = get_font(22, bold=True)
    font_footer = get_font(20)
    
    # Header - Bubba Gump branding
    title_text = "🦐 TOP 10 PERFORMERS 🦐"
    title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(
        ((SLIDE_WIDTH - title_width) // 2, 40),
        title_text,
        font=font_title,
        fill=colors["primary"]
    )
    
    # Subtitle
    subtitle = f"{quarter} {year} • Bubba Gump Shrimp Co. • Las Vegas"
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=font_subtitle)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    draw.text(
        ((SLIDE_WIDTH - subtitle_width) // 2, 115),
        subtitle,
        font=font_subtitle,
        fill=colors["text_muted"]
    )
    
    # Divider line
    draw.line([(100, 160), (SLIDE_WIDTH - 100, 160)], fill=colors["secondary"], width=3)
    
    # Top 10 list
    start_y = 190
    row_height = 80
    
    for idx, emp in enumerate(rankings[:10]):
        rank = idx + 1
        y = start_y + idx * row_height
        
        # Rank medal color
        if rank == 1:
            rank_color = colors["gold"]
        elif rank == 2:
            rank_color = colors["silver"]
        elif rank == 3:
            rank_color = colors["bronze"]
        else:
            rank_color = colors["text_light"]
        
        # Rank number
        rank_text = f"#{rank}"
        draw.text((100, y + 15), rank_text, font=font_rank, fill=rank_color)
        
        # Name
        name = emp.get("name", "Unknown")[:25]  # Truncate long names
        draw.text((220, y + 18), name, font=font_name, fill=colors["text_white"])
        
        # Tier badge
        tier = emp.get("tier_label", "A-Server")
        draw_tier_badge(draw, 750, y + 18, tier, font_tier)
        
        # Score - right aligned
        score = emp.get("total_score", 0)
        score_text = f"{score:.1f}"
        score_bbox = draw.textbbox((0, 0), score_text, font=font_score)
        score_width = score_bbox[2] - score_bbox[0]
        draw.text(
            (SLIDE_WIDTH - 150 - score_width, y + 12),
            score_text,
            font=font_score,
            fill=colors["gold"] if rank <= 3 else colors["text_white"]
        )
        
        # Subtle row divider
        if idx < 9:
            draw.line(
                [(100, y + row_height - 5), (SLIDE_WIDTH - 100, y + row_height - 5)],
                fill=hex_to_rgb(colors["background_gradient"]),
                width=1
            )
    
    # Footer
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y')} • Confidential"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
    footer_width = footer_bbox[2] - footer_bbox[0]
    draw.text(
        ((SLIDE_WIDTH - footer_width) // 2, SLIDE_HEIGHT - 50),
        footer_text,
        font=font_footer,
        fill=colors["text_muted"]
    )
    
    # Save to bytes
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
    custom_bg_image: str = None
) -> bytes:
    """
    Generate a tier-specific slide (Trainers, Bartenders, A/B/C-Servers).
    Shows: Name, Total Score, optional metric indicators.
    """
    colors = get_theme_colors(theme, custom_colors)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors, custom_bg_image)
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_title = get_font(56, bold=True)
    font_subtitle = get_font(24)
    font_rank = get_font(36, bold=True)
    font_name = get_font(34, bold=True)
    font_score = get_font(38, bold=True)
    font_footer = get_font(18)
    font_indicator = get_font(20)
    
    # Get tier config
    tier_config = TIER_CONFIG.get(tier_name, TIER_CONFIG["A-Server"])
    tier_color = tier_config["color"]
    
    # Header
    title_text = f"🦐 {tier_name.upper()} RANKINGS 🦐"
    title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(
        ((SLIDE_WIDTH - title_width) // 2, 35),
        title_text,
        font=font_title,
        fill=tier_color
    )
    
    # Subtitle with page info
    page_info = f" • Page {page}/{total_pages}" if total_pages > 1 else ""
    subtitle = f"{quarter} {year} • Bubba Gump Shrimp Co.{page_info}"
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=font_subtitle)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    draw.text(
        ((SLIDE_WIDTH - subtitle_width) // 2, 100),
        subtitle,
        font=font_subtitle,
        fill=colors["text_muted"]
    )
    
    # Divider
    draw.line([(100, 140), (SLIDE_WIDTH - 100, 140)], fill=tier_color, width=3)
    
    # Column headers
    header_y = 160
    draw.text((100, header_y), "RANK", font=font_indicator, fill=colors["text_muted"])
    draw.text((200, header_y), "NAME", font=font_indicator, fill=colors["text_muted"])
    draw.text((SLIDE_WIDTH - 450, header_y), "PPA  LBW  LSC  GLS", font=font_indicator, fill=colors["text_muted"])
    draw.text((SLIDE_WIDTH - 180, header_y), "SCORE", font=font_indicator, fill=colors["text_muted"])
    
    # Employee rows
    start_y = 200
    row_height = 70
    max_per_page = 10
    
    for idx, emp in enumerate(employees[:max_per_page]):
        y = start_y + idx * row_height
        
        # Position label (e.g., A1, B2, Bar3)
        position_label = emp.get("position_label", f"{idx + 1}")
        draw.text((100, y + 12), position_label, font=font_rank, fill=tier_color)
        
        # Name
        name = emp.get("name", "Unknown")[:22]
        draw.text((200, y + 14), name, font=font_name, fill=colors["text_white"])
        
        # Metric indicators (visual dots/bars, not numbers)
        indicator_x = SLIDE_WIDTH - 450
        indicator_y = y + 18
        indicator_spacing = 55
        
        # PPA indicator
        ppa_earned = emp.get("ppa_points", {}).get("earned", 0)
        ppa_color = TIER_CONFIG["A-Server"]["color"] if ppa_earned >= 22 else TIER_CONFIG["B-Server"]["color"] if ppa_earned >= 18 else TIER_CONFIG["C-Server"]["color"]
        draw.ellipse((indicator_x, indicator_y, indicator_x + 20, indicator_y + 20), fill=ppa_color)
        
        # LBW indicator
        lbw_earned = emp.get("lbw_points", {}).get("earned", 0)
        lbw_color = TIER_CONFIG["A-Server"]["color"] if lbw_earned >= 18 else TIER_CONFIG["B-Server"]["color"] if lbw_earned >= 14 else TIER_CONFIG["C-Server"]["color"]
        draw.ellipse((indicator_x + indicator_spacing, indicator_y, indicator_x + indicator_spacing + 20, indicator_y + 20), fill=lbw_color)
        
        # LSC indicator
        lsc_earned = emp.get("lsc_points", {}).get("earned", 0)
        lsc_color = TIER_CONFIG["A-Server"]["color"] if lsc_earned >= 20 else TIER_CONFIG["B-Server"]["color"] if lsc_earned >= 15 else TIER_CONFIG["C-Server"]["color"]
        draw.ellipse((indicator_x + indicator_spacing * 2, indicator_y, indicator_x + indicator_spacing * 2 + 20, indicator_y + 20), fill=lsc_color)
        
        # Glass indicator
        glass_earned = emp.get("glassware_points", {}).get("earned", 0)
        glass_color = TIER_CONFIG["A-Server"]["color"] if glass_earned >= 14 else TIER_CONFIG["B-Server"]["color"] if glass_earned >= 10 else TIER_CONFIG["C-Server"]["color"]
        draw.ellipse((indicator_x + indicator_spacing * 3, indicator_y, indicator_x + indicator_spacing * 3 + 20, indicator_y + 20), fill=glass_color)
        
        # Total Score
        score = emp.get("total_score", 0)
        score_text = f"{score:.1f}"
        score_bbox = draw.textbbox((0, 0), score_text, font=font_score)
        score_width = score_bbox[2] - score_bbox[0]
        draw.text(
            (SLIDE_WIDTH - 120 - score_width, y + 10),
            score_text,
            font=font_score,
            fill=colors["text_white"]
        )
        
        # Row divider
        if idx < len(employees) - 1 and idx < max_per_page - 1:
            draw.line(
                [(100, y + row_height - 5), (SLIDE_WIDTH - 100, y + row_height - 5)],
                fill=hex_to_rgb(colors["background_gradient"]),
                width=1
            )
    
    # Footer
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y')} • 🟢 Strong  🟡 Average  🔴 Needs Focus"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
    footer_width = footer_bbox[2] - footer_bbox[0]
    draw.text(
        ((SLIDE_WIDTH - footer_width) // 2, SLIDE_HEIGHT - 45),
        footer_text,
        font=font_footer,
        fill=colors["text_muted"]
    )
    
    # Save to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================================
# SPECIAL SLIDES (Most Improved, Promotion Watchlist, At Risk)
# ============================================================================

def generate_most_improved_slide(
    current_rankings: List[Dict[str, Any]],
    previous_rankings: List[Dict[str, Any]],
    quarter: str,
    year: int,
    theme: str = "dark_navy",
    custom_colors: Dict = None,
    custom_bg_image: str = None
) -> bytes:
    """
    Generate "Most Improved" slide showing employees with biggest score increase.
    """
    colors = get_theme_colors(theme, custom_colors)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors, custom_bg_image)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(56, bold=True)
    font_subtitle = get_font(24)
    font_rank = get_font(42, bold=True)
    font_name = get_font(36, bold=True)
    font_score = get_font(32, bold=True)
    font_change = get_font(28, bold=True)
    font_footer = get_font(18)
    
    # Header
    title_text = "🚀 MOST IMPROVED 🚀"
    title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(((SLIDE_WIDTH - title_width) // 2, 40), title_text, font=font_title, fill=colors["gold"])
    
    subtitle = f"{quarter} {year} • Rising Stars"
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=font_subtitle)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    draw.text(((SLIDE_WIDTH - subtitle_width) // 2, 105), subtitle, font=font_subtitle, fill=colors["text_muted"])
    
    draw.line([(100, 150), (SLIDE_WIDTH - 100, 150)], fill=colors["gold"], width=3)
    
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
    
    # Sort by biggest improvement
    improvements.sort(key=lambda x: x["change"], reverse=True)
    
    # Show top 8 most improved
    start_y = 180
    row_height = 95
    
    for idx, emp in enumerate(improvements[:8]):
        y = start_y + idx * row_height
        
        # Rank
        draw.text((100, y + 20), f"#{idx + 1}", font=font_rank, fill=colors["gold"])
        
        # Name
        draw.text((200, y + 22), emp["name"][:20], font=font_name, fill=colors["text_white"])
        
        # Score change (green arrow up)
        change_text = f"+{emp['change']:.1f}"
        draw.text((750, y + 25), change_text, font=font_change, fill="#22C55E")
        
        # Current score
        score_text = f"{emp['current_score']:.1f}"
        score_bbox = draw.textbbox((0, 0), score_text, font=font_score)
        score_width = score_bbox[2] - score_bbox[0]
        draw.text((SLIDE_WIDTH - 150 - score_width, y + 25), score_text, font=font_score, fill=colors["text_white"])
    
    if not improvements:
        no_data_text = "No improvement data available (requires previous quarter data)"
        no_data_bbox = draw.textbbox((0, 0), no_data_text, font=font_subtitle)
        no_data_width = no_data_bbox[2] - no_data_bbox[0]
        draw.text(((SLIDE_WIDTH - no_data_width) // 2, 400), no_data_text, font=font_subtitle, fill=colors["text_muted"])
    
    # Footer
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y')} • Keep Up The Great Work!"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
    footer_width = footer_bbox[2] - footer_bbox[0]
    draw.text(((SLIDE_WIDTH - footer_width) // 2, SLIDE_HEIGHT - 45), footer_text, font=font_footer, fill=colors["text_muted"])
    
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
    custom_bg_image: str = None
) -> bytes:
    """
    Generate "Promotion Watchlist" slide - B-Servers close to A-Server threshold.
    """
    colors = get_theme_colors(theme, custom_colors)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors, custom_bg_image)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(56, bold=True)
    font_subtitle = get_font(24)
    font_rank = get_font(40, bold=True)
    font_name = get_font(36, bold=True)
    font_score = get_font(32, bold=True)
    font_gap = get_font(26)
    font_footer = get_font(18)
    
    # Header
    title_text = "⭐ PROMOTION WATCHLIST ⭐"
    title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(((SLIDE_WIDTH - title_width) // 2, 40), title_text, font=font_title, fill=TIER_CONFIG["A-Server"]["color"])
    
    subtitle = f"{quarter} {year} • Almost A-Server (threshold: {a_server_threshold})"
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=font_subtitle)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    draw.text(((SLIDE_WIDTH - subtitle_width) // 2, 105), subtitle, font=font_subtitle, fill=colors["text_muted"])
    
    draw.line([(100, 150), (SLIDE_WIDTH - 100, 150)], fill=TIER_CONFIG["A-Server"]["color"], width=3)
    
    # Find B-Servers close to A threshold (within 10 points)
    watchlist = []
    for emp in rankings:
        if emp.get("tier_label") == "B-Server":
            score = emp.get("total_score", 0)
            gap = a_server_threshold - score
            if gap <= 10 and gap > 0:
                watchlist.append({
                    "name": emp.get("name"),
                    "score": score,
                    "gap": gap,
                    "position_label": emp.get("position_label")
                })
    
    watchlist.sort(key=lambda x: x["gap"])  # Closest first
    
    start_y = 180
    row_height = 95
    
    for idx, emp in enumerate(watchlist[:8]):
        y = start_y + idx * row_height
        
        # Position label
        draw.text((100, y + 20), emp["position_label"], font=font_rank, fill=TIER_CONFIG["B-Server"]["color"])
        
        # Name
        draw.text((220, y + 22), emp["name"][:20], font=font_name, fill=colors["text_white"])
        
        # Gap to A-Server
        gap_text = f"{emp['gap']:.1f} pts to go"
        draw.text((700, y + 26), gap_text, font=font_gap, fill=colors["gold"])
        
        # Current score
        score_text = f"{emp['score']:.1f}"
        score_bbox = draw.textbbox((0, 0), score_text, font=font_score)
        score_width = score_bbox[2] - score_bbox[0]
        draw.text((SLIDE_WIDTH - 150 - score_width, y + 25), score_text, font=font_score, fill=colors["text_white"])
    
    if not watchlist:
        no_data_text = "No B-Servers within 10 points of A-Server threshold"
        no_data_bbox = draw.textbbox((0, 0), no_data_text, font=font_subtitle)
        no_data_width = no_data_bbox[2] - no_data_bbox[0]
        draw.text(((SLIDE_WIDTH - no_data_width) // 2, 400), no_data_text, font=font_subtitle, fill=colors["text_muted"])
    
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y')} • Keep Pushing!"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
    footer_width = footer_bbox[2] - footer_bbox[0]
    draw.text(((SLIDE_WIDTH - footer_width) // 2, SLIDE_HEIGHT - 45), footer_text, font=font_footer, fill=colors["text_muted"])
    
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
    custom_bg_image: str = None
) -> bytes:
    """
    Generate "At Risk / Coaching Group" slide - C-Servers needing attention.
    Manager-only slide.
    """
    colors = get_theme_colors(theme, custom_colors)
    img = create_gradient_background(SLIDE_WIDTH, SLIDE_HEIGHT, colors, custom_bg_image)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(56, bold=True)
    font_subtitle = get_font(24)
    font_rank = get_font(40, bold=True)
    font_name = get_font(36, bold=True)
    font_score = get_font(32, bold=True)
    font_gap = get_font(26)
    font_footer = get_font(18)
    font_warning = get_font(20, bold=True)
    
    # Header
    title_text = "📋 COACHING FOCUS GROUP 📋"
    title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(((SLIDE_WIDTH - title_width) // 2, 40), title_text, font=font_title, fill=TIER_CONFIG["C-Server"]["color"])
    
    subtitle = f"{quarter} {year} • Development Priority (B-Server threshold: {b_server_threshold})"
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=font_subtitle)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    draw.text(((SLIDE_WIDTH - subtitle_width) // 2, 105), subtitle, font=font_subtitle, fill=colors["text_muted"])
    
    # Manager only warning
    warning_text = "⚠️ MANAGER ONLY - NOT FOR PUBLIC DISPLAY ⚠️"
    warning_bbox = draw.textbbox((0, 0), warning_text, font=font_warning)
    warning_width = warning_bbox[2] - warning_bbox[0]
    draw.text(((SLIDE_WIDTH - warning_width) // 2, 135), warning_text, font=font_warning, fill=TIER_CONFIG["C-Server"]["color"])
    
    draw.line([(100, 170), (SLIDE_WIDTH - 100, 170)], fill=TIER_CONFIG["C-Server"]["color"], width=3)
    
    # Find C-Servers
    at_risk = []
    for emp in rankings:
        if emp.get("tier_label") == "C-Server":
            score = emp.get("total_score", 0)
            gap = b_server_threshold - score
            at_risk.append({
                "name": emp.get("name"),
                "score": score,
                "gap": gap,
                "position_label": emp.get("position_label")
            })
    
    at_risk.sort(key=lambda x: x["score"], reverse=True)  # Highest C-Server first
    
    start_y = 200
    row_height = 85
    
    for idx, emp in enumerate(at_risk[:8]):
        y = start_y + idx * row_height
        
        # Position label
        draw.text((100, y + 18), emp["position_label"], font=font_rank, fill=TIER_CONFIG["C-Server"]["color"])
        
        # Name
        draw.text((220, y + 20), emp["name"][:20], font=font_name, fill=colors["text_white"])
        
        # Gap to B-Server
        gap_text = f"{emp['gap']:.1f} pts needed"
        draw.text((700, y + 24), gap_text, font=font_gap, fill=TIER_CONFIG["B-Server"]["color"])
        
        # Current score
        score_text = f"{emp['score']:.1f}"
        score_bbox = draw.textbbox((0, 0), score_text, font=font_score)
        score_width = score_bbox[2] - score_bbox[0]
        draw.text((SLIDE_WIDTH - 150 - score_width, y + 22), score_text, font=font_score, fill=colors["text_white"])
    
    if not at_risk:
        no_data_text = "No C-Servers - Great job team!"
        no_data_bbox = draw.textbbox((0, 0), no_data_text, font=font_subtitle)
        no_data_width = no_data_bbox[2] - no_data_bbox[0]
        draw.text(((SLIDE_WIDTH - no_data_width) // 2, 400), no_data_text, font=font_subtitle, fill=colors["text_muted"])
    
    footer_text = f"Generated {datetime.now().strftime('%m/%d/%Y')} • Confidential Management Document"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
    footer_width = footer_bbox[2] - footer_bbox[0]
    draw.text(((SLIDE_WIDTH - footer_width) // 2, SLIDE_HEIGHT - 45), footer_text, font=font_footer, fill=colors["text_muted"])
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def generate_all_slides(rankings: List[Dict[str, Any]], quarter: str, year: int) -> Dict[str, List[bytes]]:
    """
    Generate all Yodeck slides for a quarter.
    
    Returns dict with:
    - "top_10": [slide_bytes]
    - "trainers": [slide_bytes, ...]
    - "bartenders": [slide_bytes, ...]
    - "a_servers": [slide_bytes, ...]
    - "b_servers": [slide_bytes, ...]
    - "c_servers": [slide_bytes, ...]
    """
    slides = {
        "top_10": [],
        "trainers": [],
        "bartenders": [],
        "a_servers": [],
        "b_servers": [],
        "c_servers": [],
    }
    
    # Top 10 slide
    slides["top_10"].append(generate_top_10_slide(rankings, quarter, year))
    
    # Group by tier
    tier_groups = {
        "Trainer": [],
        "Bartender": [],
        "A-Server": [],
        "B-Server": [],
        "C-Server": [],
    }
    
    for emp in rankings:
        tier = emp.get("tier_label", "A-Server")
        if tier in tier_groups:
            tier_groups[tier].append(emp)
    
    # Generate tier slides (paginated if needed)
    max_per_slide = 10
    
    for tier_name, tier_key in [
        ("Trainer", "trainers"),
        ("Bartender", "bartenders"),
        ("A-Server", "a_servers"),
        ("B-Server", "b_servers"),
        ("C-Server", "c_servers"),
    ]:
        employees = tier_groups[tier_name]
        if not employees:
            continue
            
        total_pages = (len(employees) + max_per_slide - 1) // max_per_slide
        
        for page in range(total_pages):
            start_idx = page * max_per_slide
            end_idx = start_idx + max_per_slide
            page_employees = employees[start_idx:end_idx]
            
            slide = generate_tier_slide(
                tier_name,
                page_employees,
                quarter,
                year,
                page=page + 1,
                total_pages=total_pages
            )
            slides[tier_key].append(slide)
    
    return slides
