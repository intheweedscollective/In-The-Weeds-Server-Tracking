"""
Full Rankings PDF Generator
Generates a professional PDF with hierarchy-based rankings and complete scoring breakdown.
"""
import io
from datetime import datetime
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, 
    PageBreak, KeepTogether
)


# Tier colors for badges
TIER_COLORS = {
    "Trainer": {"bg": "#9333EA", "text": "#FFFFFF"},      # Purple
    "Bartender": {"bg": "#2563EB", "text": "#FFFFFF"},    # Blue
    "A-Server": {"bg": "#16A34A", "text": "#FFFFFF"},     # Green
    "B-Server": {"bg": "#CA8A04", "text": "#FFFFFF"},     # Yellow/Gold
    "C-Server": {"bg": "#DC2626", "text": "#FFFFFF"},     # Red
}


def build_full_rankings_pdf(
    rankings: List[Dict[str, Any]],
    quarter: str,
    year: int,
    thresholds: Dict[str, float],
) -> bytes:
    """
    Build a comprehensive full rankings PDF with all scoring breakdown columns.
    
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
        fontSize=18,
        textColor=colors.HexColor("#D12E2E"),
        alignment=TA_CENTER,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#374151"),
        alignment=TA_CENTER,
        spaceAfter=8,
    )

    footer_style = ParagraphStyle(
        "footer",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        textColor=colors.HexColor("#6B7280"),
        alignment=TA_CENTER,
    )

    story: List[Any] = []

    # Header
    story.append(Paragraph("🦐 BUBBA GUMP SHRIMP CO. 🦐", title_style))
    story.append(Paragraph(
        f"Full Team Rankings - {quarter} {year} | Generated {datetime.now().strftime('%m/%d/%Y %H:%M')}",
        subtitle_style
    ))

    # Thresholds Legend
    a_min = thresholds.get("a_server_min", 85.1)
    b_min = thresholds.get("b_server_min", 70.1)
    legend_text = (
        f"<b>Hierarchy:</b> Trainers → Bartenders → A-Servers (≥{a_min}) → "
        f"B-Servers (≥{b_min}) → C-Servers (<{b_min}) | "
        f"<b>Rank is final.</b> Within each tier, sorted by Total Score."
    )
    story.append(Paragraph(legend_text, footer_style))
    story.append(Spacer(1, 8))

    # Build main rankings table
    # Columns: Position, Label, Name, Job Title, Tier, Total Score, Bonus,
    #          PPA (Base), PPA (Bonus), LBW (Base), LBW (Bonus), 
    #          LSC (Base), LSC (Bonus), Glass (Base), Glass (Bonus), CV Score
    
    header_row = [
        "Pos", "Label", "Employee Name", "Tier", "Total\nScore", "Total\nBonus",
        "PPA\nBase", "PPA\nBonus", "LBW\nBase", "LBW\nBonus",
        "LSC\nBase", "LSC\nBonus", "Glass\nBase", "Glass\nBonus", "CV\nScore"
    ]
    
    data_rows = [header_row]
    
    for emp in rankings:
        # Get bonus values
        ppa_bonus = emp.get("bonus_ppa", 0) or 0
        lbw_bonus = emp.get("bonus_lbw", 0) or 0
        lsc_bonus = emp.get("bonus_lsc", 0) or 0
        glass_bonus = emp.get("bonus_glass", 0) or 0
        
        # CV score (15% weight, no bonus)
        cv_score = emp.get("cv_score", 0) or 0
        
        # Get base earned (subtract bonus from total earned)
        ppa_earned = emp.get("ppa_points", {}).get("earned", 0)
        ppa_base = round(ppa_earned - ppa_bonus, 1)
        
        lbw_earned = emp.get("lbw_points", {}).get("earned", 0)
        lbw_base = round(lbw_earned - lbw_bonus, 1)
        
        lsc_earned = emp.get("lsc_points", {}).get("earned", 0)
        lsc_base = round(lsc_earned - lsc_bonus, 1)
        
        glass_earned = emp.get("glassware_points", {}).get("earned", 0)
        glass_base = round(glass_earned - glass_bonus, 1)
        
        row = [
            str(emp.get("position", "")),
            emp.get("position_label", ""),
            emp.get("name", "")[:20],  # Truncate long names
            emp.get("tier_label", ""),
            f"{emp.get('total_score', 0):.1f}",
            f"+{emp.get('bonus_points', 0):.1f}",
            f"{ppa_base:.1f}",
            f"+{ppa_bonus:.1f}" if ppa_bonus > 0 else "-",
            f"{lbw_base:.1f}",
            f"+{lbw_bonus:.1f}" if lbw_bonus > 0 else "-",
            f"{lsc_base:.1f}",
            f"+{lsc_bonus:.1f}" if lsc_bonus > 0 else "-",
            f"{glass_base:.1f}",
            f"+{glass_bonus:.1f}" if glass_bonus > 0 else "-",
            f"{cv_score:.1f}",
        ]
        data_rows.append(row)

    # Column widths for landscape A4 (11.69 x 8.27 inches usable ~10.89 x 7.47)
    col_widths = [
        0.35 * inch,   # Pos
        0.45 * inch,   # Label
        1.4 * inch,    # Name
        0.65 * inch,   # Tier
        0.55 * inch,   # Total Score
        0.55 * inch,   # Total Bonus
        0.5 * inch,    # PPA Base
        0.5 * inch,    # PPA Bonus
        0.5 * inch,    # LBW Base
        0.5 * inch,    # LBW Bonus
        0.5 * inch,    # LSC Base
        0.5 * inch,    # LSC Bonus
        0.5 * inch,    # Glass Base
        0.5 * inch,    # Glass Bonus
        0.5 * inch,    # CV Score
    ]

    table = Table(data_rows, colWidths=col_widths, repeatRows=1)
    
    # Table styling
    table_style = [
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#005B96")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        
        # Data rows
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),   # Position
        ("ALIGN", (1, 1), (1, -1), "CENTER"),   # Label
        ("ALIGN", (2, 1), (2, -1), "LEFT"),     # Name
        ("ALIGN", (3, 1), (3, -1), "CENTER"),   # Tier
        ("ALIGN", (4, 1), (-1, -1), "CENTER"),  # All numbers
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        
        # Alternating row colors
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
    ]
    
    # Add tier-based coloring for the Tier column
    for idx, emp in enumerate(rankings, start=1):
        tier = emp.get("tier_label", "")
        tier_color = TIER_COLORS.get(tier, {"bg": "#9CA3AF"})
        table_style.append(("BACKGROUND", (3, idx), (3, idx), colors.HexColor(tier_color["bg"])))
        table_style.append(("TEXTCOLOR", (3, idx), (3, idx), colors.white))
        table_style.append(("FONTNAME", (3, idx), (3, idx), "Helvetica-Bold"))
        
        # Highlight bonus columns in green if > 0
        if emp.get("bonus_points", 0) > 0:
            table_style.append(("TEXTCOLOR", (5, idx), (5, idx), colors.HexColor("#16A34A")))
    
    table.setStyle(TableStyle(table_style))
    story.append(table)

    # Footer with scoring explanation
    story.append(Spacer(1, 12))
    scoring_legend = (
        "<b>Scoring Formula:</b> "
        "PPA (25% max 30pts) | LBW (20% max 25pts) | LSC (25% max 30pts) | Glass (15% max 20pts) | CV (15% max 20pts) | "
        "Base = weight × min(score%, 100). Bonus = (score% - 100) × 0.2, capped at 5 per metric."
    )
    story.append(Paragraph(scoring_legend, footer_style))
    
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "🦐 Bubba Gump Shrimp Co. • Las Vegas • Confidential HR Document 🦐",
        footer_style
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
