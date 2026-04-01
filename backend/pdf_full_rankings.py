"""
Full Rankings PDF Generator
Generates a professional PDF with hierarchy-based rankings matching the app's dark theme aesthetic.
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


# App color scheme - Dark Navy Theme
COLORS = {
    "background": "#1a1f2e",      # Dark navy background
    "card": "#1E293B",            # Card/row background
    "card_alt": "#252d3d",        # Alternating row
    "primary": "#2563EB",         # Primary blue
    "accent": "#3B82F6",          # Accent blue
    "text": "#F8FAFC",            # White text
    "text_muted": "#94A3B8",      # Muted gray text
    "border": "#334155",          # Border color
    "success": "#22C55E",         # Green for bonuses
    "warning": "#EAB308",         # Yellow/gold
    "danger": "#EF4444",          # Red
}

# Tier colors matching the app
TIER_COLORS = {
    "Trainer": {"bg": "#8B5CF6", "text": "#FFFFFF"},      # Purple
    "Bartender": {"bg": "#3B82F6", "text": "#FFFFFF"},    # Blue
    "A-Server": {"bg": "#22C55E", "text": "#FFFFFF"},     # Green
    "B-Server": {"bg": "#EAB308", "text": "#1a1f2e"},     # Yellow/Gold
    "C-Server": {"bg": "#EF4444", "text": "#FFFFFF"},     # Red
}

# Performance tier badges
PERF_COLORS = {
    "Top 10%": {"bg": "#22C55E", "text": "#FFFFFF"},
    "Top 25%": {"bg": "#3B82F6", "text": "#FFFFFF"},
    "Top Performer": {"bg": "#22C55E", "text": "#FFFFFF"},
    "Above Average": {"bg": "#3B82F6", "text": "#FFFFFF"},
    "Satisfactory": {"bg": "#EAB308", "text": "#1a1f2e"},
    "Needs Improvement": {"bg": "#EF4444", "text": "#FFFFFF"},
}


def build_full_rankings_pdf(
    rankings: List[Dict[str, Any]],
    quarter: str,
    year: int,
    thresholds: Dict[str, float],
) -> bytes:
    """
    Build a comprehensive full rankings PDF matching the app's dark theme aesthetic.
    
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
        topMargin=0.3 * inch,
        bottomMargin=0.3 * inch,
        leftMargin=0.3 * inch,
        rightMargin=0.3 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles matching app aesthetic
    title_style = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=colors.HexColor(COLORS["text"]),
        alignment=TA_CENTER,
        spaceAfter=2,
    )

    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=colors.HexColor(COLORS["text_muted"]),
        alignment=TA_CENTER,
        spaceAfter=6,
    )

    section_style = ParagraphStyle(
        "section",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.HexColor(COLORS["text"]),
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=4,
    )

    footer_style = ParagraphStyle(
        "footer",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        textColor=colors.HexColor(COLORS["text_muted"]),
        alignment=TA_CENTER,
    )

    story: List[Any] = []

    # ==================== HEADER ====================
    # Create header table with dark background
    header_data = [[
        Paragraph("Performance Leaderboard", title_style),
    ]]
    header_table = Table(header_data, colWidths=[10.5 * inch])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(COLORS["background"])),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)

    # Subtitle with quarter info
    subtitle_data = [[
        Paragraph(f"{quarter} {year} Rankings  |  Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style),
    ]]
    subtitle_table = Table(subtitle_data, colWidths=[10.5 * inch])
    subtitle_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(COLORS["background"])),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(subtitle_table)

    # ==================== TIER LEGEND ====================
    a_min = thresholds.get("a_server_min", 90)
    b_min = thresholds.get("b_server_min", 75)
    
    legend_items = [
        ("Trainer", TIER_COLORS["Trainer"]["bg"]),
        ("Bartender", TIER_COLORS["Bartender"]["bg"]),
        (f"A-Server (≥{a_min})", TIER_COLORS["A-Server"]["bg"]),
        (f"B-Server (≥{b_min})", TIER_COLORS["B-Server"]["bg"]),
        (f"C-Server (<{b_min})", TIER_COLORS["C-Server"]["bg"]),
    ]
    
    legend_row = []
    for label, bg_color in legend_items:
        legend_row.append(Paragraph(
            f"<font color='white'><b>{label}</b></font>",
            ParagraphStyle("legend", fontSize=7, alignment=TA_CENTER)
        ))
    
    legend_table = Table([legend_row], colWidths=[2.1 * inch] * 5)
    legend_style = [
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, (_, bg_color) in enumerate(legend_items):
        legend_style.append(("BACKGROUND", (i, 0), (i, 0), colors.HexColor(bg_color)))
        legend_style.append(("ROUNDEDCORNERS", [4, 4, 4, 4]))
    
    legend_table.setStyle(TableStyle(legend_style))
    story.append(legend_table)
    story.append(Spacer(1, 8))

    # ==================== MAIN RANKINGS TABLE ====================
    header_row = [
        "#", "Label", "Employee", "Tier", "Score", "Bonus",
        "PPA", "LBW", "LSC", "Glass", "CV", "RT"
    ]
    
    data_rows = [header_row]
    
    for emp in rankings:
        # Calculate metrics
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
            emp.get("name", "")[:22],
            emp.get("tier_label", ""),
            f"{emp.get('total_score', 0):.1f}",
            f"+{bonus_pts:.1f}" if bonus_pts > 0 else "-",
            f"{ppa_pts:.1f}",
            f"{lbw_pts:.1f}",
            f"{lsc_pts:.1f}",
            f"{glass_pts:.1f}",
            f"{cv_score:.1f}",
            str(int(rt_mentions)),
        ]
        data_rows.append(row)

    # Column widths optimized for readability
    col_widths = [
        0.35 * inch,   # #
        0.5 * inch,    # Label
        1.8 * inch,    # Employee
        0.75 * inch,   # Tier
        0.6 * inch,    # Score
        0.55 * inch,   # Bonus
        0.6 * inch,    # PPA
        0.6 * inch,    # LBW
        0.6 * inch,    # LSC
        0.6 * inch,    # Glass
        0.55 * inch,   # CV
        0.45 * inch,   # RT
    ]

    table = Table(data_rows, colWidths=col_widths, repeatRows=1)
    
    # Dark theme table styling
    table_style = [
        # Header row - Dark navy with white text
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(COLORS["card"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(COLORS["text"])),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        
        # Data rows - Dark alternating backgrounds
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor(COLORS["text"])),
        ("ALIGN", (0, 1), (1, -1), "CENTER"),    # # and Label
        ("ALIGN", (2, 1), (2, -1), "LEFT"),      # Name
        ("ALIGN", (3, 1), (-1, -1), "CENTER"),   # Rest centered
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        
        # Grid lines - Subtle dark borders
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(COLORS["border"])),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(COLORS["border"])),
    ]
    
    # Alternating row backgrounds (dark theme)
    for idx in range(1, len(data_rows)):
        if idx % 2 == 0:
            table_style.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(COLORS["card_alt"])))
        else:
            table_style.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(COLORS["card"])))
    
    # Add tier-based coloring for the Tier column
    for idx, emp in enumerate(rankings, start=1):
        tier = emp.get("tier_label", "")
        tier_color = TIER_COLORS.get(tier, {"bg": "#6B7280", "text": "#FFFFFF"})
        table_style.append(("BACKGROUND", (3, idx), (3, idx), colors.HexColor(tier_color["bg"])))
        table_style.append(("TEXTCOLOR", (3, idx), (3, idx), colors.HexColor(tier_color["text"])))
        table_style.append(("FONTNAME", (3, idx), (3, idx), "Helvetica-Bold"))
        
        # Highlight score column based on value
        score = emp.get("total_score", 0) or 0
        if score >= 100:
            table_style.append(("TEXTCOLOR", (4, idx), (4, idx), colors.HexColor(COLORS["success"])))
            table_style.append(("FONTNAME", (4, idx), (4, idx), "Helvetica-Bold"))
        elif score >= 90:
            table_style.append(("TEXTCOLOR", (4, idx), (4, idx), colors.HexColor("#22C55E")))
        
        # Highlight bonus column in green if > 0
        if emp.get("bonus_points", 0) or emp.get("metric_bonus", 0):
            bonus = emp.get("bonus_points", 0) or emp.get("metric_bonus", 0) or 0
            if bonus > 0:
                table_style.append(("TEXTCOLOR", (5, idx), (5, idx), colors.HexColor(COLORS["success"])))
    
    table.setStyle(TableStyle(table_style))
    story.append(table)

    # ==================== FOOTER ====================
    story.append(Spacer(1, 12))
    
    # Scoring formula box
    formula_data = [[
        Paragraph(
            "<b>Scoring Formula:</b> PPA (25%) + LBW (20%) + LSC (25%) + Glassware (15%) + Customer Voice (15%) + Metric Bonuses",
            ParagraphStyle("formula", fontSize=7, textColor=colors.HexColor(COLORS["text_muted"]), alignment=TA_CENTER)
        )
    ]]
    formula_table = Table(formula_data, colWidths=[10.5 * inch])
    formula_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(COLORS["card"])),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(COLORS["border"])),
    ]))
    story.append(formula_table)
    
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Bubba Gump Shrimp Co.  •  Las Vegas  •  {quarter} {year} Performance Rankings  •  Confidential",
        footer_style
    ))

    # Build with dark page background
    def add_background(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor(COLORS["background"]))
        canvas.rect(0, 0, landscape(A4)[0], landscape(A4)[1], fill=True, stroke=False)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_background, onLaterPages=add_background)
    buffer.seek(0)
    return buffer.getvalue()
