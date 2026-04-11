"""
Server Performance Snapshot - EXACT REPLICATION
Matching the Q1 Final Performance Slide reference image precisely
"""
import io
import os
import requests
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from datetime import datetime

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

# Background options
BACKGROUNDS = {
    "dark": {
        "name": "Dark Navy",
        "type": "solid",
        "color": (15, 23, 42),
        "preview": None
    },
    "rainbow_bubbles": {
        "name": "Rainbow Bubbles",
        "type": "image",
        "path": "/app/backend/assets/backgrounds/rainbow_bubbles.jpg",
        "preview": None
    },
}

# Exact colors from reference
COLORS = {
    "bg_navy": (15, 23, 42),           # Dark navy background
    "header_blue": (30, 58, 95),       # Table header dark blue
    "white": (255, 255, 255),
    "row_white": (255, 255, 255),
    "row_gray": (240, 242, 245),
    
    # Performance colors - EXACT from reference
    "blue": (12, 118, 158),            # #0c769e - Exceeding (>=100%)
    "green": (51, 204, 51),            # #33cc33 - Meeting (80-99%)
    "yellow": (255, 255, 0),           # #ffff00 - Work in Progress (70-79%)
    "red": (255, 0, 0),                # #ff0000 - Needs Improvement (<70%)
    
    # Title colors
    "title_red": (255, 50, 50),
    "title_green": (50, 205, 50),
}

# Font paths
FONT_REGULAR = "/app/backend/assets/fonts/Poppins-Regular.ttf"
FONT_MEDIUM = "/app/backend/assets/fonts/Poppins-Medium.ttf"
FONT_SEMIBOLD = "/app/backend/assets/fonts/Poppins-SemiBold.ttf"
FONT_APTOS_NARROW_BOLD = "/app/backend/assets/fonts/Aptos-Narrow-Bold.ttf"


def get_font(size: int, weight: str = "regular"):
    if weight == "aptos":
        path = FONT_APTOS_NARROW_BOLD
    elif weight == "semibold":
        path = FONT_SEMIBOLD
    elif weight == "medium":
        path = FONT_MEDIUM
    else:
        path = FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except:
        if weight in ["bold", "semibold", "aptos"]:
            fallback = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        else:
            fallback = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        try:
            return ImageFont.truetype(fallback, size)
        except:
            return ImageFont.load_default()


def get_metric_color(value: float) -> Tuple[int, int, int]:
    """Get cell color based on percentage value."""
    if value >= 100:
        return COLORS["blue"]
    elif value >= 80:
        return COLORS["green"]
    elif value >= 70:
        return COLORS["yellow"]
    return COLORS["red"]


def get_cv_color(value: float) -> Tuple[int, int, int]:
    """Get CV score color. Higher is better."""
    if value >= 15:
        return COLORS["blue"]
    elif value >= 10:
        return COLORS["green"]
    elif value >= 5:
        return COLORS["yellow"]
    return COLORS["red"]


def get_rt_color(value: float) -> Tuple[int, int, int]:
    """Get RT bonus color. Higher is better."""
    if value >= 10:
        return COLORS["blue"]
    elif value >= 5:
        return COLORS["green"]
    elif value >= 1:
        return COLORS["yellow"]
    return COLORS["red"]


def get_bonus_color(value: float) -> Tuple[int, int, int]:
    """Get metric bonus color."""
    if value >= 8:
        return COLORS["blue"]
    elif value >= 4:
        return COLORS["green"]
    elif value >= 1:
        return COLORS["yellow"]
    return COLORS["red"]


def get_score_color(value: float, a_min: float = 85, b_min: float = 70) -> Tuple[int, int, int]:
    """Get total score color based on tier thresholds."""
    if value >= 100:
        return COLORS["blue"]     # Exceeding expectations: Blue (100+)
    elif value >= a_min:
        return COLORS["green"]    # A-Server: Green
    elif value >= b_min:
        return COLORS["yellow"]   # B-Server: Yellow
    return COLORS["red"]          # C-Server: Red


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "rainbow_bubbles",
    title: str = None,
    quarter: str = "Q1",
    a_min: float = 85,
    b_min: float = 70
) -> bytes:
    """
    Generate a simplified Complete Rankings slide.
    Shows ONLY: Tier sections with First Name and Rank, sorted highest to lowest.
    Uses colorful background image.
    """
    
    # Load background image or use solid color
    bg_config = BACKGROUNDS.get(background, BACKGROUNDS.get("rainbow_bubbles", BACKGROUNDS["dark"]))
    
    if bg_config.get("type") == "image" and os.path.exists(bg_config.get("path", "")):
        try:
            img = Image.open(bg_config["path"]).convert("RGB")
            img = img.resize((SLIDE_WIDTH, SLIDE_HEIGHT), Image.Resampling.LANCZOS)
        except:
            img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), COLORS["bg_navy"])
    else:
        img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), bg_config.get("color", COLORS["bg_navy"]))
    
    draw = ImageDraw.Draw(img)
    
    # Sort employees by tier, then by score within tier (highest to lowest)
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_emps = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score") or 0)
    ))
    
    # Group employees by tier
    tier_groups = {}
    for emp in sorted_emps:
        tier = emp.get("tier_label", "C-Server")
        if tier not in tier_groups:
            tier_groups[tier] = []
        tier_groups[tier].append(emp)
    
    # Tier configuration with colors
    TIER_CONFIG = {
        "Trainer": {"label": "TRAINERS", "color": (220, 38, 38), "text": (255, 255, 255)},
        "Bartender": {"label": "BARTENDERS", "color": (168, 85, 247), "text": (255, 255, 255)},
        "A-Server": {"label": "A-SERVERS", "color": (34, 197, 94), "text": (255, 255, 255)},
        "B-Server": {"label": "B-SERVERS", "color": (234, 179, 8), "text": (0, 0, 0)},
        "C-Server": {"label": "C-SERVERS", "color": (239, 68, 68), "text": (255, 255, 255)},
    }
    
    tier_order_list = ["Trainer", "Bartender", "A-Server", "B-Server", "C-Server"]
    active_tiers = [t for t in tier_order_list if t in tier_groups and len(tier_groups[t]) > 0]
    
    # Calculate layout - arrange tiers in columns
    num_tiers = len(active_tiers)
    if num_tiers == 0:
        # No employees, return blank slide
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        buf.seek(0)
        return buf.getvalue()
    
    # Title at top
    title_text = f"{quarter} SERVER RANKINGS"
    draw.text((SLIDE_WIDTH // 2, 50), title_text, 
              font=get_font(56, "semibold"), fill=(255, 255, 255), anchor="mm",
              stroke_width=3, stroke_fill=(0, 0, 0))
    
    # Layout tiers in columns (max 5 columns for 5 tiers)
    margin = 40
    top_margin = 120
    bottom_margin = 40
    
    # Calculate column width based on number of active tiers
    available_width = SLIDE_WIDTH - (2 * margin) - ((num_tiers - 1) * 20)  # 20px gap between columns
    col_width = available_width // num_tiers
    
    tier_header_height = 50
    row_height = 36
    available_height = SLIDE_HEIGHT - top_margin - bottom_margin - tier_header_height
    
    for tier_idx, tier in enumerate(active_tiers):
        tier_config = TIER_CONFIG.get(tier, {"label": tier.upper(), "color": (100, 100, 100), "text": (255, 255, 255)})
        employees_in_tier = tier_groups[tier]
        
        # Column position
        col_x = margin + tier_idx * (col_width + 20)
        col_right = col_x + col_width
        
        # Semi-transparent background for column
        overlay = Image.new('RGBA', (col_width, SLIDE_HEIGHT - top_margin - bottom_margin + 10), (0, 0, 0, 180))
        img.paste(Image.alpha_composite(Image.new('RGBA', overlay.size, (0, 0, 0, 0)), overlay).convert('RGB'), 
                  (col_x, top_margin - 5), 
                  overlay.split()[3])
        draw = ImageDraw.Draw(img)
        
        # Tier header
        header_y = top_margin
        draw.rectangle([col_x, header_y, col_right, header_y + tier_header_height], 
                      fill=tier_config["color"])
        draw.text((col_x + col_width // 2, header_y + tier_header_height // 2), 
                 tier_config["label"], font=get_font(28, "semibold"), 
                 fill=tier_config["text"], anchor="mm")
        
        # Draw employees
        data_y = header_y + tier_header_height
        tier_count = 0
        
        for emp in employees_in_tier:
            tier_count += 1
            
            y = data_y + (tier_count - 1) * row_height
            if y + row_height > SLIDE_HEIGHT - bottom_margin:
                break
            
            row_cy = y + row_height // 2
            
            # Rank label
            if tier == "Bartender":
                rank_text = f"{tier_count}."
            else:
                rank_text = f"{tier_count}."
            
            # First name only
            full_name = emp.get("name") or emp.get("display_name") or "Unknown"
            first_name = full_name.split()[0][:15] if full_name else "Unknown"  # Max 15 chars
            
            # Draw rank and name
            rank_x = col_x + 15
            name_x = col_x + 50
            
            draw.text((rank_x, row_cy), rank_text, font=get_font(22, "semibold"), 
                      fill=(255, 255, 255), anchor="lm")
            draw.text((name_x, row_cy), first_name, font=get_font(22, "medium"), 
                      fill=(255, 255, 255), anchor="lm")
    
    # Footer - quarter info
    footer_text = f"Q1 2026 • Las Vegas"
    draw.text((SLIDE_WIDTH // 2, SLIDE_HEIGHT - 25), footer_text,
              font=get_font(20, "medium"), fill=(255, 255, 255), anchor="mm",
              stroke_width=1, stroke_fill=(0, 0, 0))
    
    # Save
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


def get_available_backgrounds():
    return [{"key": k, "name": v["name"], "preview": v.get("preview")} for k, v in BACKGROUNDS.items()]
