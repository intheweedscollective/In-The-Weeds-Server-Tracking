"""
Server Performance Snapshot - EXACT REPLICATION
Matching the reference image precisely
"""
import io
import os
import requests
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from datetime import datetime

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

# Background options with descriptive names and preview URLs
BACKGROUNDS = {
    "dark": {
        "name": "Dark Navy",
        "type": "solid",
        "color": (15, 23, 42),
        "preview": None
    },
    "rainbow_bokeh": {
        "name": "Rainbow Bokeh",
        "type": "image",
        "url": "https://customer-assets.emergentagent.com/job_staffscore-1/artifacts/0dpcbmve_IMG_2080.jpeg",
        "preview": "https://customer-assets.emergentagent.com/job_staffscore-1/artifacts/0dpcbmve_IMG_2080.jpeg"
    },
    "cosmic_lights": {
        "name": "Cosmic Lights",
        "type": "image",
        "url": "https://customer-assets.emergentagent.com/job_staffscore-1/artifacts/kj7dry1p_IMG_2081.jpeg",
        "preview": "https://customer-assets.emergentagent.com/job_staffscore-1/artifacts/kj7dry1p_IMG_2081.jpeg"
    },
    "neon_grid": {
        "name": "Neon Grid",
        "type": "image",
        "url": "https://customer-assets.emergentagent.com/job_staffscore-1/artifacts/7ejr8e4h_IMG_2078.jpeg",
        "preview": "https://customer-assets.emergentagent.com/job_staffscore-1/artifacts/7ejr8e4h_IMG_2078.jpeg"
    },
    "synthwave_sunset": {
        "name": "Synthwave Sunset",
        "type": "image",
        "url": "https://customer-assets.emergentagent.com/job_staffscore-1/artifacts/2uyjx6bg_IMG_2076.jpeg",
        "preview": "https://customer-assets.emergentagent.com/job_staffscore-1/artifacts/2uyjx6bg_IMG_2076.jpeg"
    },
    "electric_mesh": {
        "name": "Electric Mesh",
        "type": "image",
        "url": "https://customer-assets.emergentagent.com/job_staffscore-1/artifacts/zlo7kss4_IMG_2077.jpeg",
        "preview": "https://customer-assets.emergentagent.com/job_staffscore-1/artifacts/zlo7kss4_IMG_2077.jpeg"
    }
}

# Exact colors from reference
COLORS = {
    "bg_navy": (15, 23, 42),           # Dark navy background
    "header_blue": (30, 58, 95),       # Table header dark blue
    "white": (255, 255, 255),
    "row_white": (255, 255, 255),
    "row_gray": (240, 242, 245),
    "bar_row": (25, 40, 65),           # BAR1/BAR2 row background
    
    # Performance colors - EXACT hex values
    "blue": (12, 118, 158),            # #0c769e - Exceeding
    "green": (51, 204, 51),            # #33cc33 - Meeting
    "yellow": (255, 255, 0),           # #ffff00 - Work in Progress
    "red": (255, 0, 0),                # #ff0000 - Needs Improvement
    
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
        # Use Liberation fonts as fallback (available in container)
        if weight in ["bold", "semibold"]:
            fallback = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        else:
            fallback = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        try:
            return ImageFont.truetype(fallback, size)
        except:
            # Last resort: use default PIL font
            return ImageFont.load_default()


def get_cell_color(value: float, is_total: bool = False) -> Tuple[int, int, int]:
    """Get cell color based on performance."""
    if value >= 100:
        return COLORS["blue"]
    elif value >= 80:
        return COLORS["green"]
    elif value >= 70:
        return COLORS["yellow"]
    return COLORS["red"]


def get_rt_color(value: float) -> Tuple[int, int, int]:
    """Get Review Tracker bonus color.
    0.5 pts per mention, capped at 15 pts
    0 = red
    0.5-2.5 = yellow (1-5 mentions)
    3.0-5.0 = green (6-10 mentions)
    5.5-15 = blue (11-30 mentions, capped)
    """
    if value >= 5.5:
        return COLORS["blue"]
    elif value >= 3.0:
        return COLORS["green"]
    elif value >= 0.5:
        return COLORS["yellow"]
    return COLORS["red"]


def get_cv_color(value: float) -> Tuple[int, int, int]:
    """Get Customer Voice score color.
    CV Score = NPS points (0-10) + promoter/detractor points (+0.5/-1 each)
    0-5 = red
    5.1-10 = yellow
    10.1-15 = green
    15.1+ = blue
    """
    if value >= 15.1:
        return COLORS["blue"]
    elif value >= 10.1:
        return COLORS["green"]
    elif value >= 5.1:
        return COLORS["yellow"]
    return COLORS["red"]


def generate_snapshot_slide(
    employees: List[Dict[str, Any]],
    benchmarks: Dict[str, float],
    snapshot_date: str,
    background: str = "dark",
    title: str = None
) -> bytes:
    """Generate snapshot matching reference image exactly."""
    
    # Get background configuration
    bg_config = BACKGROUNDS.get(background, BACKGROUNDS["dark"])
    
    # Create base image based on background type
    if bg_config.get("type") == "image" and bg_config.get("url"):
        try:
            # Download and load image background
            response = requests.get(bg_config["url"], timeout=10)
            bg_img = Image.open(io.BytesIO(response.content))
            
            # Convert to RGB if necessary
            if bg_img.mode != 'RGB':
                bg_img = bg_img.convert('RGB')
            
            # Resize to fit slide dimensions
            bg_img = bg_img.resize((SLIDE_WIDTH, SLIDE_HEIGHT), Image.Resampling.LANCZOS)
            
            # Darken the image significantly for text readability
            enhancer = ImageEnhance.Brightness(bg_img)
            bg_img = enhancer.enhance(0.3)  # Darken to 30% brightness
            
            # Reduce saturation for more subtle look
            sat_enhancer = ImageEnhance.Color(bg_img)
            bg_img = sat_enhancer.enhance(0.6)  # Reduce saturation
            
            # Add slight blur for a softer look
            bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=3))
            
            # Create a dark overlay for even better readability
            overlay = Image.new('RGBA', (SLIDE_WIDTH, SLIDE_HEIGHT), (10, 20, 40, 150))
            bg_img = bg_img.convert('RGBA')
            bg_img = Image.alpha_composite(bg_img, overlay)
            bg_img = bg_img.convert('RGB')
            
            img = bg_img
        except Exception as e:
            print(f"Error loading background image: {e}")
            # Fallback to solid color
            img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), COLORS["bg_navy"])
    else:
        # Solid color background
        color = bg_config.get("color", COLORS["bg_navy"])
        img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), color)
    
    draw = ImageDraw.Draw(img)
    
    # Sort employees
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    sorted_emps = sorted(employees, key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 4),
        -(x.get("total_score", 0) or 0)
    ))
    num_emps = len(sorted_emps)
    
    # ===== LEFT PANEL - WIDER to give more space for legend =====
    left_width = 480
    
    # Logo - large, top of left panel
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((280, 280), Image.Resampling.LANCZOS)
            logo_x = (left_width - logo.width) // 2
            img.paste(logo, (logo_x, 30), logo)
        except:
            pass
    
    draw = ImageDraw.Draw(img)
    
    # Title section
    title_y = 330
    center_x = left_width // 2
    
    # "Q1 SERVER" - white
    draw.text((center_x, title_y), "Q1 SERVER", font=get_font(36, "semibold"),
              fill=COLORS["white"], anchor="mm")
    
    # "PERFORMANCE" - red, large
    draw.text((center_x, title_y + 50), "PERFORMANCE", font=get_font(42, "semibold"),
              fill=COLORS["title_red"], anchor="mm")
    
    # "SNAPSHOT" - white
    draw.text((center_x, title_y + 100), "SNAPSHOT", font=get_font(36, "semibold"),
              fill=COLORS["white"], anchor="mm")
    
    # Date - red
    date_y = title_y + 145
    draw.text((center_x, date_y), snapshot_date, font=get_font(24, "medium"),
              fill=COLORS["title_red"], anchor="mm")
    date_bottom_y = date_y + 20  # Add padding below date
    
    # Footer text - positioned at bottom
    footer_y = SLIDE_HEIGHT - 130
    
    # Calculate legend position - EQUALLY CENTERED between date and footer statement
    legend_height = 4 * 70  # 4 items × 70px spacing (280px total)
    # Available space from date bottom to footer top
    available_space = footer_y - date_bottom_y
    # Position legend so space above and below is equal
    space_above = (available_space - legend_height) // 2
    legend_y = date_bottom_y + space_above
    
    legend_items = [
        (COLORS["blue"], "EXCEEDING ALL", "EXPECTATIONS"),
        (COLORS["green"], "MEETING", "EXPECTATIONS"),
        (COLORS["yellow"], "WORK IN", "PROGRESS"),
        (COLORS["red"], "NEEDS IMMEDIATE", "IMPROVEMENT"),
    ]
    
    for i, (color, line1, line2) in enumerate(legend_items):
        y = legend_y + i * 70
        # Colored square - centered with logo
        square_size = 50
        # Calculate total legend width (square + gap + text)
        legend_content_width = square_size + 12 + 250  # approximate text width
        legend_start_x = (left_width - legend_content_width) // 2
        
        draw.rectangle([legend_start_x, y, legend_start_x + square_size, y + square_size], fill=color)
        # Text in matching color - 28pt (split into 2 lines)
        draw.text((legend_start_x + square_size + 12, y + 8), line1, 
                  font=get_font(28, "semibold"), fill=color, anchor="lm")
        draw.text((legend_start_x + square_size + 12, y + 36), line2, 
                  font=get_font(28, "semibold"), fill=color, anchor="lm")
    
    # Footer text
    draw.text((center_x, footer_y), "DON'T WAIT TO IMPACT", 
              font=get_font(24, "semibold"), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 30), "THIS NUMBER.",
              font=get_font(24, "semibold"), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 65), "IF YOU HAVE QUESTIONS",
              font=get_font(24, "semibold"), fill=COLORS["white"], anchor="mm")
    draw.text((center_x, footer_y + 95), "PLEASE SEE MANAGEMENT.",
              font=get_font(24, "semibold"), fill=COLORS["white"], anchor="mm")
    
    # ===== RIGHT PANEL (Table) =====
    table_left = left_width + 20
    table_right = SLIDE_WIDTH - 20
    table_top = 30
    table_width = table_right - table_left
    
    # Calculate row sizing to fit ALL employees
    header_h = 45
    available_height = SLIDE_HEIGHT - table_top - 20 - header_h
    row_h = available_height // max(num_emps, 1)
    row_h = max(28, min(42, row_h))  # Between 28-42px
    
    # Columns - Added Trend column, split Review into CV and RT
    columns = [
        {"name": "Rank", "width": 55},
        {"name": "Name", "width": 140},
        {"name": "Trend", "width": 45, "key": "trend"},
        {"name": "PPA", "width": 80, "key": "score_ppa"},
        {"name": "LBW", "width": 80, "key": "score_lbw"},
        {"name": "GLASS", "width": 80, "key": "score_glass"},
        {"name": "LSC", "width": 80, "key": "score_lsc"},
        {"name": "CV", "width": 70, "key": "cv_score", "is_bonus": True},
        {"name": "RT", "width": 70, "key": "rt_bonus", "is_bonus": True},
        {"name": "Bonus", "width": 80, "key": "total_metric_bonus", "is_bonus": True},
        {"name": "Score", "width": 100, "key": "total_score"},
    ]
    
    # Calculate CV score and RT bonus separately for each employee
    for emp in sorted_emps:
        # CV Score: NPS%/10 + promoters × 0.5 - detractors × 1 (stored as cv_score)
        cv_score = float(emp.get("cv_score", 0) or 0)
        emp["cv_score"] = cv_score
        
        # RT Bonus: mentions × 0.5, capped at 15 (stored as review_tracker_bonus or review_bonus)
        rt_bonus = float(emp.get("review_tracker_bonus", 0) or emp.get("review_bonus", 0) or 0)
        rt_bonus = min(rt_bonus, 15)  # Ensure cap
        emp["rt_bonus"] = rt_bonus
        
        # Calculate trend from previous snapshot data if available
        prev_score = emp.get("previous_score")
        current_score = emp.get("total_score", 0) or 0
        if prev_score is not None:
            diff = current_score - prev_score
            if diff > 1:
                emp["trend"] = "↑"
                emp["trend_color"] = "green"
            elif diff < -1:
                emp["trend"] = "↓"
                emp["trend_color"] = "red"
            else:
                emp["trend"] = "→"
                emp["trend_color"] = "gray"
        else:
            emp["trend"] = "•"
            emp["trend_color"] = "gray"
    
    # Scale columns
    total_col_w = sum(c["width"] for c in columns)
    scale = table_width / total_col_w
    for c in columns:
        c["width"] = int(c["width"] * scale)
    columns[-1]["width"] += table_width - sum(c["width"] for c in columns)
    
    # Column positions
    col_x = []
    x = table_left
    for c in columns:
        col_x.append(x)
        x += c["width"]
    
    # Header row - dark blue
    draw.rectangle([table_left, table_top, table_right, table_top + header_h],
                   fill=COLORS["header_blue"])
    
    # Header border - BLACK lines
    draw.line([(table_left, table_top), (table_right, table_top)], fill=(0, 0, 0), width=1)
    draw.line([(table_left, table_top + header_h), (table_right, table_top + header_h)], fill=(0, 0, 0), width=1)
    
    # Header text
    header_font = get_font(16, "semibold")
    for i, col in enumerate(columns):
        cx = col_x[i] + col["width"] // 2
        draw.text((cx, table_top + header_h // 2), col["name"],
                  font=header_font, fill=COLORS["white"], anchor="mm")
    
    # Data rows
    data_y = table_top + header_h
    current_tier = None
    tier_counts = {}
    row_idx = 0
    
    for emp in sorted_emps:
        tier = emp.get("tier_label", "C-Server")
        
        # Insert BAR separator rows for Bartenders
        if tier == "Bartender" and current_tier != "Bartender":
            # Check if we have bartenders
            pass
        
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        current_tier = tier
        
        y = data_y + row_idx * row_h
        if y + row_h > SLIDE_HEIGHT - 20:
            break
        
        # Alternating row colors (white / light gray)
        row_bg = COLORS["row_white"] if row_idx % 2 == 0 else COLORS["row_gray"]
        
        # Special row for BAR entries
        if tier == "Bartender":
            prefix = "BAR"
            rank_text = f"{prefix}{tier_counts[tier]}"
        else:
            prefix = {"Trainer": "T", "A-Server": "A", "B-Server": "B", "C-Server": "C"}.get(tier, "")
            if prefix:
                rank_text = f"{prefix}{tier_counts[tier]}"
            else:
                rank_text = str(row_idx + 1)
        
        # Draw row background
        draw.rectangle([table_left, y, table_right, y + row_h], fill=row_bg)
        
        # Horizontal grid lines - BLACK (top and bottom of each row)
        draw.line([(table_left, y), (table_right, y)], fill=(0, 0, 0), width=1)
        draw.line([(table_left, y + row_h), (table_right, y + row_h)], fill=(0, 0, 0), width=1)
        
        row_cy = y + row_h // 2
        
        # Rank column - Aptos Narrow Bold, black text
        draw.text((col_x[0] + columns[0]["width"] // 2, row_cy), rank_text,
                  font=get_font(16, "aptos"), fill=(0, 0, 0), anchor="mm")
        
        # Employee name - First name only, Aptos Narrow Bold, black text
        full_name = emp.get("name", "Unknown")
        name = full_name.split()[0] if full_name else "Unknown"  # First name only
        max_ch = columns[1]["width"] // 10
        if len(name) > max_ch:
            name = name[:max_ch-1] + "…"
        draw.text((col_x[1] + 10, row_cy), name,
                  font=get_font(16, "aptos"), fill=(0, 0, 0), anchor="lm")
        
        # Metric columns - colored cells
        for i, col in enumerate(columns[2:], start=2):
            key = col.get("key")
            if not key:
                continue
            
            # Special handling for trend column - draw arrows manually
            if key == "trend":
                trend_color_name = emp.get("trend_color", "gray")
                if trend_color_name == "green":
                    arrow_color = (34, 197, 94)  # Bright green
                elif trend_color_name == "red":
                    arrow_color = (239, 68, 68)  # Bright red
                else:
                    arrow_color = (156, 163, 175)  # Gray
                
                # Center point for the arrow
                center_x = col_x[i] + columns[i]["width"] // 2
                center_y = row_cy
                arrow_size = 8  # Half the arrow size
                
                trend_type = emp.get("trend", "•")
                
                if trend_type == "↑":
                    # Draw UP arrow (triangle pointing up)
                    points = [
                        (center_x, center_y - arrow_size),      # Top point
                        (center_x - arrow_size, center_y + arrow_size),  # Bottom left
                        (center_x + arrow_size, center_y + arrow_size),  # Bottom right
                    ]
                    draw.polygon(points, fill=arrow_color)
                elif trend_type == "↓":
                    # Draw DOWN arrow (triangle pointing down)
                    points = [
                        (center_x, center_y + arrow_size),      # Bottom point
                        (center_x - arrow_size, center_y - arrow_size),  # Top left
                        (center_x + arrow_size, center_y - arrow_size),  # Top right
                    ]
                    draw.polygon(points, fill=arrow_color)
                elif trend_type == "→":
                    # Draw horizontal line/dash for no change
                    draw.rectangle(
                        [center_x - arrow_size, center_y - 2, center_x + arrow_size, center_y + 2],
                        fill=arrow_color
                    )
                else:
                    # Draw a horizontal dash for no data (same as no change)
                    draw.rectangle(
                        [center_x - arrow_size, center_y - 2, center_x + arrow_size, center_y + 2],
                        fill=arrow_color
                    )
                continue
            
            # Get value - combined_review_bonus is already calculated above
            val = emp.get(key, 0) or 0
            
            is_bonus = col.get("is_bonus", False)
            
            # Cell dimensions
            cell_pad = 4
            cx = col_x[i] + cell_pad
            cw = columns[i]["width"] - cell_pad * 2
            ch = row_h - 8
            cy = y + 4
            
            # Determine color and format
            if key == "cv_score":
                # Customer Voice: 0-5=Red, 5.1-10=Yellow, 10.1-15=Green, 15.1+=Blue
                color = get_cv_color(val)
                text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
                text = f"+{val:.1f}" if val > 0 else f"{val:.1f}"
            elif key == "rt_bonus":
                # Review Tracker: 0=Red, 0.1-2.5=Yellow, 2.6-5=Green, 5.1+=Blue
                color = get_rt_color(val)
                text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
                text = f"+{val:.1f}" if val > 0 else f"{val:.1f}"
            elif key == "total_metric_bonus":
                # Metric Bonus: 0=Red, +1=Green, +10=Blue
                if val >= 10:
                    color = COLORS["blue"]
                    text_color = COLORS["white"]  # White text on blue
                elif val >= 1:
                    color = COLORS["green"]
                    text_color = (0, 0, 0)  # Black text
                else:
                    color = COLORS["red"]
                    text_color = (0, 0, 0)  # Black text
                text = f"+{val:.1f}"
            elif key == "total_score":
                # Total score - colored based on value
                color = get_cell_color(val)
                text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
                text = f"{val:.1f}"
            else:
                # Metric scores - colored cells
                color = get_cell_color(val)
                text_color = COLORS["white"] if color == COLORS["blue"] else (0, 0, 0)
                text = f"{val:.0f}%"
            
            # Draw colored cell
            draw.rectangle([cx, cy, cx + cw, cy + ch], fill=color)
            
            # Draw text - Aptos Narrow Bold
            draw.text((cx + cw // 2, row_cy), text,
                      font=get_font(14, "aptos"), fill=text_color, anchor="mm")
        
        row_idx += 1
    
    # Outer border - BLACK
    final_y = data_y + row_idx * row_h
    draw.rectangle([table_left, table_top, table_right, final_y], outline=(0, 0, 0), width=1)
    
    # Vertical column lines - BLACK
    for i in range(len(columns)):
        draw.line([(col_x[i], table_top), (col_x[i], final_y)], fill=(0, 0, 0), width=1)
    draw.line([(table_right, table_top), (table_right, final_y)], fill=(0, 0, 0), width=1)
    
    # Save
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.getvalue()


def get_available_backgrounds():
    return [{"key": k, "name": v["name"], "preview": v.get("preview")} for k, v in BACKGROUNDS.items()]
