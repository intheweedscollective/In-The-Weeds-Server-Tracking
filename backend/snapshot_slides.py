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
FONT_QUICKSAND_BOLD = "/app/backend/assets/fonts/Quicksand-Bold.ttf"
FONT_QUICKSAND_SEMIBOLD = "/app/backend/assets/fonts/Quicksand-SemiBold.ttf"
FONT_QUICKSAND_MEDIUM = "/app/backend/assets/fonts/Quicksand-Medium.ttf"


def get_font(size: int, weight: str = "regular"):
    if weight == "aptos":
        path = FONT_APTOS_NARROW_BOLD
    elif weight == "semibold":
        path = FONT_SEMIBOLD
    elif weight == "medium":
        path = FONT_MEDIUM
    elif weight == "quicksand_bold":
        path = FONT_QUICKSAND_BOLD
    elif weight == "quicksand_semibold":
        path = FONT_QUICKSAND_SEMIBOLD
    elif weight == "quicksand":
        path = FONT_QUICKSAND_MEDIUM
    else:
        path = FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except:
        if weight in ["bold", "semibold", "aptos", "quicksand_bold"]:
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
    Shows ONLY: Tier sections with First Name and Rank (T1, BAR1, A1, B1, C1 format).
    Uses colorful background image with content-fitted column backgrounds.
    Uses Quicksand font for a fun, stylish look.
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
    
    # Tier configuration with colors and rank prefixes
    TIER_CONFIG = {
        "Trainer": {"label": "TRAINERS", "prefix": "T", "color": (220, 38, 38), "text": (255, 255, 255)},
        "Bartender": {"label": "BARTENDERS", "prefix": "BAR", "color": (168, 85, 247), "text": (255, 255, 255)},
        "A-Server": {"label": "A-SERVERS", "prefix": "A", "color": (34, 197, 94), "text": (255, 255, 255)},
        "B-Server": {"label": "B-SERVERS", "prefix": "B", "color": (234, 179, 8), "text": (0, 0, 0)},
        "C-Server": {"label": "C-SERVERS", "prefix": "C", "color": (239, 68, 68), "text": (255, 255, 255)},
    }
    
    tier_order_list = ["Trainer", "Bartender", "A-Server", "B-Server", "C-Server"]
    active_tiers = [t for t in tier_order_list if t in tier_groups and len(tier_groups[t]) > 0]
    
    num_tiers = len(active_tiers)
    if num_tiers == 0:
        # No employees, return blank slide
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        buf.seek(0)
        return buf.getvalue()
    
    # Title at top - using Quicksand Bold for fun style
    title_text = f"{quarter} SERVER RANKINGS"
    draw.text((SLIDE_WIDTH // 2, 55), title_text, 
              font=get_font(60, "quicksand_bold"), fill=(255, 255, 255), anchor="mm",
              stroke_width=4, stroke_fill=(0, 0, 0))
    
    # Layout parameters
    margin = 50
    top_margin = 130
    col_gap = 25  # Gap between columns
    
    # Calculate column width based on number of active tiers
    available_width = SLIDE_WIDTH - (2 * margin) - ((num_tiers - 1) * col_gap)
    col_width = available_width // num_tiers
    
    tier_header_height = 55
    row_height = 62  # Increased for even bigger text
    padding_bottom = 15  # Padding inside column after last employee
    
    # Calculate max employees per column for vertical centering
    max_employees = max(len(tier_groups[t]) for t in active_tiers)
    
    for tier_idx, tier in enumerate(active_tiers):
        tier_config = TIER_CONFIG.get(tier, {"label": tier.upper(), "prefix": "", "color": (100, 100, 100), "text": (255, 255, 255)})
        employees_in_tier = tier_groups[tier]
        num_employees = len(employees_in_tier)
        
        # Column position
        col_x = margin + tier_idx * (col_width + col_gap)
        col_right = col_x + col_width
        
        # Calculate column height based on CONTENT (not full height)
        content_height = tier_header_height + (num_employees * row_height) + padding_bottom
        
        # Center the column vertically in the available space
        available_height = SLIDE_HEIGHT - top_margin - 60  # Leave space for footer
        column_top = top_margin + (available_height - content_height) // 2
        column_top = max(top_margin, column_top)  # Don't go above top_margin
        
        # Draw semi-transparent rounded background for column (content-fitted)
        bg_radius = 15
        overlay = Image.new('RGBA', (col_width + 2, content_height + 2), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(
            [0, 0, col_width, content_height],
            radius=bg_radius,
            fill=(0, 0, 0, 200)
        )
        img.paste(overlay, (col_x, column_top), overlay)
        draw = ImageDraw.Draw(img)
        
        # Tier header with rounded top corners
        header_y = column_top
        # Draw header background
        draw.rounded_rectangle(
            [col_x, header_y, col_right, header_y + tier_header_height],
            radius=bg_radius,
            fill=tier_config["color"],
            corners=(True, True, False, False)  # Only top corners rounded
        )
        # Header text - Quicksand Bold
        draw.text((col_x + col_width // 2, header_y + tier_header_height // 2), 
                 tier_config["label"], font=get_font(26, "quicksand_bold"), 
                 fill=tier_config["text"], anchor="mm")
        
        # Draw employees
        data_y = header_y + tier_header_height + 8
        
        for emp_idx, emp in enumerate(employees_in_tier):
            tier_count = emp_idx + 1
            
            y = data_y + emp_idx * row_height
            row_cy = y + row_height // 2
            
            # Rank label (T1, BAR1, A1, B1, C1 format)
            prefix = tier_config["prefix"]
            rank_text = f"{prefix}{tier_count}"
            
            # First name only (max 12 chars for readability)
            full_name = emp.get("name") or emp.get("display_name") or "Unknown"
            first_name = full_name.split()[0][:12] if full_name else "Unknown"
            
            # Draw rank - prominent, bold, white
            rank_x = col_x + 12
            draw.text((rank_x, row_cy), rank_text, font=get_font(24, "quicksand_bold"), 
                      fill=(255, 255, 255), anchor="lm")
            
            # Draw name - EVEN BIGGER and BOLDER, pure white
            # Fixed position for consistent alignment
            name_x = col_x + 85  # Fixed position for all names
            draw.text((name_x, row_cy), first_name, font=get_font(36, "quicksand_bold"), 
                      fill=(255, 255, 255), anchor="lm")
    
    # Footer - quarter and location info with Quicksand
    footer_text = f"{quarter} 2026 • Las Vegas"
    draw.text((SLIDE_WIDTH // 2, SLIDE_HEIGHT - 30), footer_text,
              font=get_font(22, "quicksand"), fill=(255, 255, 255), anchor="mm",
              stroke_width=2, stroke_fill=(0, 0, 0))
    
    # Save
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


def get_available_backgrounds():
    return [{"key": k, "name": v["name"], "preview": v.get("preview")} for k, v in BACKGROUNDS.items()]
