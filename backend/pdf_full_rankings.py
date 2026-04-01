"""
Full Rankings PDF Generator - Snapshot Style
Matches the dark navy aesthetic with color-coded performance cells.
"""
import io
from datetime import datetime
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    Image, Frame, PageTemplate, BaseDocTemplate
)
from reportlab.pdfgen import canvas


# Colors from the design
COLORS = {
    "background": "#0D1E31",      # Dark navy background
    "header_bg": "#1a2d47",       # Slightly lighter header
    "text_white": "#FFFFFF",
    "text_red": "#FF0000",
    "blue": "#00AEEF",            # Exceeding expectations
    "green": "#00B050",           # Meeting expectations  
    "yellow": "#F6EA0C",          # Work in progress
    "red": "#E52D27",             # Needs improvement
    "row_dark": "#0D1E31",
    "row_light": "#142638",
    "border": "#2a4060",
}


def get_cell_color(value: float, metric_type: str = "percentage") -> str:
    """Determine cell color based on value and metric type."""
    if metric_type == "percentage":
        if value >= 100:
            return COLORS["blue"]
        elif value >= 90:
            return COLORS["green"]
        elif value >= 75:
            return COLORS["yellow"]
        else:
            return COLORS["red"]
    elif metric_type == "cv":
        if value >= 16:
            return COLORS["blue"]
        elif value >= 11:
            return COLORS["green"]
        elif value >= 6:
            return COLORS["yellow"]
        else:
            return COLORS["red"]
    elif metric_type == "rt":
        if value >= 15:
            return COLORS["blue"]
        elif value >= 8:
            return COLORS["green"]
        elif value >= 3:
            return COLORS["yellow"]
        else:
            return COLORS["red"]
    elif metric_type == "bonus":
        if value >= 10:
            return COLORS["blue"]
        elif value >= 5:
            return COLORS["green"]
        elif value >= 1:
            return COLORS["yellow"]
        else:
            return COLORS["red"]
    return COLORS["green"]


def get_text_color_for_bg(bg_color: str) -> str:
    """Get appropriate text color for background."""
    if bg_color == COLORS["yellow"]:
        return "#000000"  # Black text on yellow
    return "#FFFFFF"  # White text on other colors


def build_full_rankings_pdf(
    rankings: List[Dict[str, Any]],
    quarter: str,
    year: int,
    thresholds: Dict[str, float],
) -> bytes:
    """Build the snapshot-style full rankings PDF."""
    buffer = io.BytesIO()
    
    # Custom page size (wider for this design)
    page_width = 14 * inch
    page_height = 10 * inch
    
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    
    # Draw background
    c.setFillColor(colors.HexColor(COLORS["background"]))
    c.rect(0, 0, page_width, page_height, fill=True, stroke=False)
    
    # ==================== LEFT SIDEBAR ====================
    sidebar_width = 2.8 * inch
    
    # Draw Bubba Gump Logo placeholder (circle with text)
    logo_center_x = sidebar_width / 2
    logo_center_y = page_height - 1.2 * inch
    
    # Logo circle background
    c.setFillColor(colors.HexColor("#1a3050"))
    c.circle(logo_center_x, logo_center_y, 0.9 * inch, fill=True, stroke=False)
    
    # Logo text
    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(logo_center_x, logo_center_y + 0.15 * inch, "BUBBA")
    c.setFillColor(colors.HexColor(COLORS["red"]))
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(logo_center_x, logo_center_y - 0.1 * inch, "GUMP")
    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica", 8)
    c.drawCentredString(logo_center_x, logo_center_y - 0.35 * inch, "SHRIMP CO.")
    
    # Title section
    title_y = logo_center_y - 1.1 * inch
    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(logo_center_x, title_y, f"{quarter} SERVER")
    
    c.setFillColor(colors.HexColor(COLORS["red"]))
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(logo_center_x, title_y - 0.35 * inch, "PERFORMANCE")
    
    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(logo_center_x, title_y - 0.7 * inch, "SNAPSHOT")
    
    c.setFont("Helvetica", 12)
    c.drawCentredString(logo_center_x, title_y - 1.0 * inch, datetime.now().strftime("%Y-%m-%d"))
    
    # Legend
    legend_y = title_y - 1.6 * inch
    legend_items = [
        ("EXCEEDING ALL", "EXPECTATIONS", COLORS["blue"]),
        ("MEETING", "EXPECTATIONS", COLORS["green"]),
        ("WORK IN", "PROGRESS", COLORS["yellow"]),
        ("NEEDS IMMEDIATE", "IMPROVEMENT", COLORS["red"]),
    ]
    
    for i, (line1, line2, color) in enumerate(legend_items):
        y_pos = legend_y - (i * 0.65 * inch)
        # Color box
        c.setFillColor(colors.HexColor(color))
        c.rect(0.3 * inch, y_pos - 0.1 * inch, 0.25 * inch, 0.35 * inch, fill=True, stroke=False)
        # Text
        text_color = "#000000" if color == COLORS["yellow"] else COLORS["text_white"]
        c.setFillColor(colors.HexColor(text_color if color != COLORS["yellow"] else COLORS["blue"]))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(0.65 * inch, y_pos + 0.08 * inch, line1)
        c.drawString(0.65 * inch, y_pos - 0.1 * inch, line2)
    
    # Footer text
    footer_y = 0.8 * inch
    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(logo_center_x, footer_y + 0.35 * inch, "DON'T WAIT TO IMPACT")
    c.drawCentredString(logo_center_x, footer_y + 0.15 * inch, "THIS NUMBER.")
    c.drawCentredString(logo_center_x, footer_y - 0.1 * inch, "IF YOU HAVE QUESTIONS")
    c.drawCentredString(logo_center_x, footer_y - 0.3 * inch, "PLEASE SEE MANAGEMENT.")
    
    # ==================== MAIN TABLE ====================
    table_x = sidebar_width + 0.15 * inch
    table_width = page_width - sidebar_width - 0.3 * inch
    table_y = page_height - 0.3 * inch
    
    # Column headers
    headers = ["Rank", "Name", "Trend", "PPA", "LBW", "GLASS", "LSC", "CV", "RT", "Bonus", "Score"]
    col_widths = [0.55, 1.1, 0.5, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7]  # in inches
    
    # Draw header row
    header_height = 0.35 * inch
    c.setFillColor(colors.HexColor(COLORS["header_bg"]))
    c.rect(table_x, table_y - header_height, table_width, header_height, fill=True, stroke=False)
    
    # Draw header text
    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 9)
    x_pos = table_x
    for i, (header, width) in enumerate(zip(headers, col_widths)):
        cell_width = width * inch
        c.drawCentredString(x_pos + cell_width / 2, table_y - 0.22 * inch, header)
        x_pos += cell_width
    
    # Draw data rows
    row_height = 0.32 * inch
    current_y = table_y - header_height
    
    for idx, emp in enumerate(rankings):
        current_y -= row_height
        
        if current_y < 0.3 * inch:
            break  # Stop if we run out of space
        
        # Alternating row background
        bg_color = COLORS["row_light"] if idx % 2 == 0 else COLORS["row_dark"]
        c.setFillColor(colors.HexColor(bg_color))
        c.rect(table_x, current_y, table_width, row_height, fill=True, stroke=False)
        
        # Get employee data
        pos_label = emp.get("position_label", "")
        name = emp.get("name", "")[:12]
        score = emp.get("total_score", 0) or 0
        
        # Calculate percentages (relative to max possible)
        ppa_pct = ((emp.get("ppa_points", {}).get("earned", 0) or 0) / 30) * 100 if 30 > 0 else 0
        lbw_pct = ((emp.get("lbw_points", {}).get("earned", 0) or 0) / 25) * 100 if 25 > 0 else 0
        glass_pct = ((emp.get("glassware_points", {}).get("earned", 0) or 0) / 20) * 100 if 20 > 0 else 0
        lsc_pct = ((emp.get("lsc_points", {}).get("earned", 0) or 0) / 30) * 100 if 30 > 0 else 0
        
        cv_score = emp.get("cv_score", 0) or 0
        rt_mentions = emp.get("review_mentions", 0) or emp.get("rt_mentions", 0) or 0
        bonus = emp.get("bonus_points", 0) or emp.get("metric_bonus", 0) or 0
        
        # Row data with colors
        row_data = [
            (pos_label, None, "center"),
            (name, None, "left"),
            ("=", None, "center"),
            (f"{ppa_pct:.0f}%", get_cell_color(ppa_pct, "percentage"), "center"),
            (f"{lbw_pct:.0f}%", get_cell_color(lbw_pct, "percentage"), "center"),
            (f"{glass_pct:.0f}%", get_cell_color(glass_pct, "percentage"), "center"),
            (f"{lsc_pct:.0f}%", get_cell_color(lsc_pct, "percentage"), "center"),
            (f"+{cv_score:.1f}", get_cell_color(cv_score, "cv"), "center"),
            (f"+{rt_mentions:.1f}", get_cell_color(rt_mentions, "rt"), "center"),
            (f"+{bonus:.1f}", get_cell_color(bonus, "bonus"), "center"),
            (f"{score:.1f}", None, "right"),
        ]
        
        # Draw cells
        x_pos = table_x
        for i, (text, cell_color, align) in enumerate(row_data):
            cell_width = col_widths[i] * inch
            
            # Draw colored background for metric cells
            if cell_color:
                c.setFillColor(colors.HexColor(cell_color))
                c.rect(x_pos + 0.02 * inch, current_y + 0.02 * inch, 
                       cell_width - 0.04 * inch, row_height - 0.04 * inch, 
                       fill=True, stroke=False)
                text_color = get_text_color_for_bg(cell_color)
            else:
                text_color = COLORS["text_white"]
            
            # Draw text
            c.setFillColor(colors.HexColor(text_color))
            c.setFont("Helvetica", 9)
            
            text_y = current_y + 0.1 * inch
            if align == "center":
                c.drawCentredString(x_pos + cell_width / 2, text_y, str(text))
            elif align == "left":
                c.drawString(x_pos + 0.05 * inch, text_y, str(text))
            else:  # right
                c.drawRightString(x_pos + cell_width - 0.05 * inch, text_y, str(text))
            
            x_pos += cell_width
    
    # Draw grid lines
    c.setStrokeColor(colors.HexColor(COLORS["border"]))
    c.setLineWidth(0.5)
    
    # Horizontal lines
    y = table_y
    while y > current_y:
        c.line(table_x, y, table_x + table_width, y)
        y -= row_height if y < table_y else header_height
    c.line(table_x, current_y, table_x + table_width, current_y)
    
    # Vertical lines
    x_pos = table_x
    for width in col_widths:
        c.line(x_pos, table_y, x_pos, current_y)
        x_pos += width * inch
    c.line(x_pos, table_y, x_pos, current_y)
    
    c.save()
    buffer.seek(0)
    return buffer.getvalue()
