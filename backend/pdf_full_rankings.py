"""
Full Rankings PDF Generator
Generates a professional PDF with hierarchy-based rankings.
Clean, print-friendly design with color-coded tiers.
"""
import io
from datetime import datetime
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, 
    PageBreak, KeepTogether
)


# Tier colors for badges (print-friendly)
TIER_COLORS = {
    "Trainer": {"bg": "#7C3AED", "text": "#FFFFFF"},      # Purple
    "Bartender": {"bg": "#2563EB", "text": "#FFFFFF"},    # Blue
    "A-Server": {"bg": "#16A34A", "text": "#FFFFFF"},     # Green
    "B-Server": {"bg": "#CA8A04", "text": "#FFFFFF"},     # Gold
    "C-Server": {"bg": "#DC2626", "text": "#FFFFFF"},     # Red
}


def build_full_rankings_pdf(
    rankings: List[Dict[str, Any]],
    quarter: str,
    year: int,
    thresholds: Dict[str, float],
) -> bytes:
    """
    Build a comprehensive full rankings PDF with clean, print-friendly design.
    
    Args:
        rankings: List of ranked employees with scoring data
        quarter: Quarter string (Q1, Q2, etc.)
        year: Year
        thresholds: Dict with a_server_min and b_server_min
    
    Returns:
        PDF bytes
    """
    buffer = io.BytesIO()
    
    # Use landscape for more columns
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=colors.HexColor("#1E293B"),
        alignment=TA_CENTER,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#64748B"),
        alignment=TA_CENTER,
        spaceAfter=12,
    )

    footer_style = ParagraphStyle(
        "footer",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        textColor=colors.HexColor("#64748B"),
        alignment=TA_CENTER,
    )

    story: List[Any] = []

    # Header
    story.append(Paragraph("Performance Leaderboard", title_style))
    story.append(Paragraph(
        f"{quarter} {year} Final Rankings  •  Generated {datetime.now().strftime('%B %d, %Y')}",
        subtitle_style
    ))

    # Tier Legend
    a_min = thresholds.get("a_server_min", 90)
    b_min = thresholds.get("b_server_min", 75)
    
    legend_data = [[
        Paragraph(f"<font color='white'><b>Trainer</b></font>", 
                  ParagraphStyle("l", fontSize=7, alignment=TA_CENTER)),
        Paragraph(f"<font color='white'><b>Bartender</b></font>", 
                  ParagraphStyle("l", fontSize=7, alignment=TA_CENTER)),
        Paragraph(f"<font color='white'><b>A-Server ≥{int(a_min)}</b></font>", 
                  ParagraphStyle("l", fontSize=7, alignment=TA_CENTER)),
        Paragraph(f"<font color='white'><b>B-Server ≥{int(b_min)}</b></font>", 
                  ParagraphStyle("l", fontSize=7, alignment=TA_CENTER)),
        Paragraph(f"<font color='white'><b>C-Server &lt;{int(b_min)}</b></font>", 
                  ParagraphStyle("l", fontSize=7, alignment=TA_CENTER)),
    ]]
    
    legend_table = Table(legend_data, colWidths=[1.8 * inch] * 5)
    legend_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(TIER_COLORS["Trainer"]["bg"])),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(TIER_COLORS["Bartender"]["bg"])),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor(TIER_COLORS["A-Server"]["bg"])),
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor(TIER_COLORS["B-Server"]["bg"])),
        ("BACKGROUND", (4, 0), (4, 0), colors.HexColor(TIER_COLORS["C-Server"]["bg"])),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(legend_table)
    story.append(Spacer(1, 12))

    # Main Rankings Table
    header_row = [
        "#", "Pos", "Employee", "Tier", "Score", 
        "PPA\n/30", "LBW\n/25", "LSC\n/30", "Glass\n/20",
        "CV", "RT", "Bonus"
    ]
    
    data_rows = [header_row]
    
    for emp in rankings:
        # Get metrics
        ppa_pts = emp.get("ppa_points", {}).get("earned", 0) or 0
        lbw_pts = emp.get("lbw_points", {}).get("earned", 0) or 0
        lsc_pts = emp.get("lsc_points", {}).get("earned", 0) or 0
        glass_pts = emp.get("glassware_points", {}).get("earned", 0) or 0
        cv_score = emp.get("cv_score", 0) or 0
        rt_mentions = emp.get("review_mentions", 0) or emp.get("rt_mentions", 0) or 0
        bonus_pts = emp.get("bonus_points", 0) or emp.get("metric_bonus", 0) or 0
        
        row = [
            str(emp.get("position", "")),
            emp.get("position_label", ""),
            emp.get("name", "")[:24],
            emp.get("tier_label", ""),
            f"{emp.get('total_score', 0):.1f}",
            f"{ppa_pts:.1f}",
            f"{lbw_pts:.1f}",
            f"{lsc_pts:.1f}",
            f"{glass_pts:.1f}",
            f"{cv_score:.1f}",
            str(int(rt_mentions)),
            f"+{bonus_pts:.1f}" if bonus_pts > 0 else "-",
        ]
        data_rows.append(row)

    # Column widths
    col_widths = [
        0.3 * inch,    # #
        0.45 * inch,   # Pos
        1.9 * inch,    # Employee
        0.7 * inch,    # Tier
        0.55 * inch,   # Score
        0.5 * inch,    # PPA
        0.5 * inch,    # LBW
        0.5 * inch,    # LSC
        0.5 * inch,    # Glass
        0.5 * inch,    # CV
        0.4 * inch,    # RT
        0.5 * inch,    # Bonus
    ]

    table = Table(data_rows, colWidths=col_widths, repeatRows=1)
    
    # Clean table styling
    table_style = [
        # Header row - Dark navy
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        
        # Data rows
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#1E293B")),
        ("ALIGN", (0, 1), (1, -1), "CENTER"),    # # and Pos
        ("ALIGN", (2, 1), (2, -1), "LEFT"),      # Name
        ("ALIGN", (3, 1), (-1, -1), "CENTER"),   # Rest centered
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#94A3B8")),
        
        # Alternating rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]
    
    # Add tier-based coloring
    for idx, emp in enumerate(rankings, start=1):
        tier = emp.get("tier_label", "")
        tier_color = TIER_COLORS.get(tier, {"bg": "#94A3B8", "text": "#FFFFFF"})
        table_style.append(("BACKGROUND", (3, idx), (3, idx), colors.HexColor(tier_color["bg"])))
        table_style.append(("TEXTCOLOR", (3, idx), (3, idx), colors.white))
        table_style.append(("FONTNAME", (3, idx), (3, idx), "Helvetica-Bold"))
        
        # Highlight high scores in green
        score = emp.get("total_score", 0) or 0
        if score >= 100:
            table_style.append(("TEXTCOLOR", (4, idx), (4, idx), colors.HexColor("#16A34A")))
            table_style.append(("FONTNAME", (4, idx), (4, idx), "Helvetica-Bold"))
        
        # Highlight bonuses in green
        bonus = emp.get("bonus_points", 0) or emp.get("metric_bonus", 0) or 0
        if bonus > 0:
            table_style.append(("TEXTCOLOR", (11, idx), (11, idx), colors.HexColor("#16A34A")))
    
    table.setStyle(TableStyle(table_style))
    story.append(table)

    # Footer
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "<b>Scoring:</b> PPA (25%) + LBW (20%) + LSC (25%) + Glassware (15%) + Customer Voice (15%) + Metric Bonuses (up to +20)",
        footer_style
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Bubba Gump Shrimp Co.  •  Las Vegas  •  {quarter} {year}  •  Confidential",
        footer_style
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
