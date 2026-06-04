"""
QR Leaderboard Slide Generator
==============================

Generates a 16:9 (1920x1080) PNG slide of the QR Tracker leaderboard for
download / digital signage. Matches the visual language of the existing
Server Performance Snapshot slide:

  * Dark slate background with the Bubba Gump branding panel on the left
  * Color-coded rank badges (gold/silver/bronze for 1-2-3)
  * Per-platform columns (Yelp / Google / TripAdvisor / Total)
  * Heatmap-style value cells (red→yellow→green based on relative performance)
  * Footer with the quarter date
"""

from __future__ import annotations

import io
import os
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# --- Theme ----------------------------------------------------------------

BG = (15, 23, 42)           # slate-900
BG_PANEL = (30, 41, 59)     # slate-800
HEADER_BG = (51, 65, 85)    # slate-700
ROW_ALT = (22, 31, 49)
TEXT = (241, 245, 249)
TEXT_DIM = (148, 163, 184)
GRID = (51, 65, 85)
GOLD = (251, 191, 36)
SILVER = (203, 213, 225)
BRONZE = (180, 83, 9)
RED = (239, 68, 68)
YELLOW_500 = (234, 179, 8)
GREEN_500 = (34, 197, 94)
EMERALD = (16, 185, 129)
BLUE_500 = (59, 130, 246)
VIOLET = (139, 92, 246)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Load DejaVu (always present in the container)."""
    try:
        path = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold else
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        )
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, x: float, y: float,
                   font: ImageFont.ImageFont, fill: tuple) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((x - w / 2, y - h / 2), text, font=font, fill=fill)


def _heat_color(value: int, max_value: int) -> tuple:
    """Red (low) -> Yellow (mid) -> Green (high) heatmap."""
    if max_value <= 0:
        return TEXT_DIM
    ratio = max(0.0, min(1.0, value / max_value))
    if ratio <= 0.05:
        return RED
    if ratio < 0.4:
        return (220, 100, 60)
    if ratio < 0.7:
        return YELLOW_500
    return GREEN_500


def generate_qr_leaderboard_slide(
    employees: list[dict[str, Any]],
    quarter: str = "Q2",
    year: int = 2026,
    title: str | None = None,
) -> bytes:
    """
    Render the QR Click vs Review Mentions report to a 1920x1080 PNG.

    Each row shows:
      * Total QR Clicks (Yelp + Google + TripAdvisor combined)
      * Review Mentions (Review Tracker mentions, all platforms combined)

    Lists ALL employees, falling into a 2-column grid when there are more than
    14 rows so the slide never truncates.

    `employees` items may include:
        name, yelp_clicks, google_clicks, tripadvisor_clicks,
        rt_mentions or review_tracker_mentions
    """
    width, height = 1920, 1080
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    def total_clicks(e):
        return (e.get("yelp_clicks") or 0) + (e.get("google_clicks") or 0) + (e.get("tripadvisor_clicks") or 0)

    def total_mentions(e):
        # Combine ALL RT platforms into one number. Many shapes exist in the
        # codebase — try them all and sum.
        return int(
            (e.get("rt_mentions") or 0)
            + (e.get("review_tracker_mentions") or 0)
            + (e.get("rt_yelp_mentions") or 0)
            + (e.get("rt_google_mentions") or 0)
            + (e.get("rt_tripadvisor_mentions") or 0)
        )

    # Sort: total clicks desc -> mentions desc. Conversion ratio dropped
    # because it's easily skewed by self-scans and doesn't add value.
    employees = sorted(
        employees,
        key=lambda e: (total_clicks(e), total_mentions(e)),
        reverse=True,
    )

    # ----- Left brand panel ------------------------------------------------
    panel_w = 360
    draw.rectangle([(0, 0), (panel_w, height)], fill=BG_PANEL)

    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    logo_y = 50
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((220, 220))
            img.paste(logo, ((panel_w - logo.width) // 2, logo_y), logo)
            logo_y += logo.height + 20
        except Exception:
            logo_y = 60
    else:
        logo_y = 60

    title_text = title or "QR CLICKS\nvs\nREVIEWS"
    f_title = _font(40, bold=True)
    y = logo_y + 20
    for line in title_text.split("\n"):
        _draw_centered(draw, line, panel_w / 2, y, f_title, GOLD)
        y += 50

    f_period = _font(26, bold=True)
    _draw_centered(draw, f"{quarter} {year}", panel_w / 2, y + 25, f_period, TEXT)

    # Aggregate stats on left panel
    grand_clicks = sum(total_clicks(e) for e in employees)
    grand_mentions = sum(total_mentions(e) for e in employees)

    stats_y = y + 95
    f_stat_label = _font(16, bold=True)
    f_stat_value = _font(38, bold=True)

    def stat_block(label, value, color, top):
        _draw_centered(draw, label, panel_w / 2, top, f_stat_label, TEXT_DIM)
        _draw_centered(draw, value, panel_w / 2, top + 30, f_stat_value, color)

    stat_block("TOTAL CLICKS", str(grand_clicks), VIOLET, stats_y)
    stat_block("REVIEW MENTIONS", str(grand_mentions), EMERALD, stats_y + 90)

    # Legend at the bottom of the panel
    legend_y = height - 130
    f_legend = _font(15)
    draw.text((30, legend_y),
              "Clicks  = Yelp + Google + TripAdvisor",
              font=f_legend, fill=TEXT_DIM)
    draw.text((30, legend_y + 24),
              "Mentions = ReviewTracker mentions",
              font=f_legend, fill=TEXT_DIM)
    draw.text((30, legend_y + 48),
              "(combined across all platforms)",
              font=f_legend, fill=TEXT_DIM)

    # ----- Right side: title + table ---------------------------------------
    table_x = panel_w + 40
    table_y = 50
    table_w = width - table_x - 40

    f_header = _font(38, bold=True)
    draw.text((table_x, table_y), "QR Clicks vs Review Mentions", font=f_header, fill=TEXT)
    draw.text((table_x, table_y + 50),
              f"All staff — sorted by total clicks ({len(employees)} employees)",
              font=_font(18), fill=TEXT_DIM)

    # ----- Determine layout: 1 col vs 2 col --------------------------------
    head_y = table_y + 105
    available_h = height - head_y - 70
    use_two_col = len(employees) > 14
    cols = 2 if use_two_col else 1
    col_w = (table_w - (40 if use_two_col else 0)) / cols
    rows_per_col = -(-len(employees) // cols)  # ceil division
    row_h = max(34, min(48, int(available_h / max(rows_per_col, 1))))

    # ----- Per-column band positions (relative to col origin) --------------
    BAND_RANK = 0
    BAND_NAME = 1
    BAND_CLK = 2
    BAND_MEN = 3

    def band_x(col_origin: float, band: int) -> float:
        # Within each column: rank | name | clicks | mentions
        rank_w = 40
        name_w = col_w - rank_w - 110 - 110
        clk_w = 110
        men_w = 110
        if band == BAND_RANK:
            return col_origin + rank_w / 2
        if band == BAND_NAME:
            return col_origin + rank_w + 5
        if band == BAND_CLK:
            return col_origin + rank_w + name_w + clk_w / 2
        if band == BAND_MEN:
            return col_origin + rank_w + name_w + clk_w + men_w / 2
        return col_origin

    # ----- Header rows for each column ------------------------------------
    f_col_head = _font(16, bold=True)
    for c in range(cols):
        col_origin = table_x + c * (col_w + 40)
        draw.rectangle(
            [(col_origin, head_y - 6), (col_origin + col_w, head_y + 26)],
            fill=HEADER_BG,
        )
        draw.text((col_origin + 10, head_y), "#", font=f_col_head, fill=TEXT_DIM)
        draw.text((band_x(col_origin, BAND_NAME), head_y), "Employee",
                  font=f_col_head, fill=TEXT_DIM)
        _draw_centered(draw, "Clicks", band_x(col_origin, BAND_CLK), head_y + 12,
                       f_col_head, VIOLET)
        _draw_centered(draw, "Mentions", band_x(col_origin, BAND_MEN), head_y + 12,
                       f_col_head, EMERALD)

    # ----- Rows -----------------------------------------------------------
    if not employees:
        f_empty = _font(22)
        draw.text((table_x + 20, head_y + 80),
                  "No QR scan data yet — generate codes for your team to start tracking.",
                  font=f_empty, fill=TEXT_DIM)
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()

    f_row_name = _font(int(row_h * 0.5), bold=True)
    f_row_num = _font(int(row_h * 0.55), bold=True)
    f_row_rank = _font(int(row_h * 0.45), bold=True)

    name_truncate_chars = 22 if use_two_col else 36

    rows_start_y = head_y + 36

    for idx, emp in enumerate(employees):
        rank = idx + 1
        col_idx = idx // rows_per_col if use_two_col else 0
        within_col_idx = idx if not use_two_col else (idx % rows_per_col)

        col_origin = table_x + col_idx * (col_w + 40)
        cy = rows_start_y + within_col_idx * row_h

        # Alternating row background
        if within_col_idx % 2 == 0:
            draw.rectangle(
                [(col_origin, cy), (col_origin + col_w, cy + row_h - 4)],
                fill=ROW_ALT,
            )

        # Rank badge
        rank_color = (
            GOLD if rank == 1 else SILVER if rank == 2 else BRONZE if rank == 3 else
            GREEN_500 if rank <= 5 else TEXT_DIM
        )
        rank_label_color = (15, 23, 42) if rank in (1, 2, 4, 5) else TEXT
        if rank <= 5:
            badge_r = int(row_h * 0.32)
            bx = col_origin + 22
            by = cy + row_h / 2 - 2
            draw.ellipse(
                [bx - badge_r, by - badge_r, bx + badge_r, by + badge_r],
                fill=rank_color,
            )
            _draw_centered(draw, str(rank), bx, by, f_row_rank, rank_label_color)
        else:
            _draw_centered(draw, str(rank), col_origin + 22, cy + row_h / 2 - 2,
                           f_row_rank, TEXT_DIM)

        # Name
        name = (emp.get("name") or "—").strip()
        if len(name) > name_truncate_chars:
            name = name[: name_truncate_chars - 1] + "…"
        draw.text(
            (band_x(col_origin, BAND_NAME), cy + (row_h - int(row_h * 0.5)) / 2 - 2),
            name, font=f_row_name, fill=TEXT,
        )

        # Numbers
        clk = total_clicks(emp)
        men = total_mentions(emp)

        _draw_centered(draw, str(clk), band_x(col_origin, BAND_CLK), cy + row_h / 2 - 2,
                       f_row_num, VIOLET)
        _draw_centered(draw, str(men), band_x(col_origin, BAND_MEN), cy + row_h / 2 - 2,
                       f_row_num, EMERALD if men else TEXT_DIM)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
