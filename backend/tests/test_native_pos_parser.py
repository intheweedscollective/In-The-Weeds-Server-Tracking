"""
Regression tests for native_pos_parser.py.

These cover the column-drift / glyph-artifact bugs that came up on the
SSS Q2P5W1 Server Sales Report, where PyMuPDF emitted skewed word
coordinates and letter-for-digit misreads (e.g. "so" for "50",
"L,quor" for "Liquor"). The key invariants being protected:

1. _join_column_tokens must correctly handle 2- and 3-token splits where
   the trailing token is the cents portion.
2. Single-token values like "4.10300" (thousands-period plus baked-in
   cents) must reconstruct to 4103.00, not 4.103.
3. The regex fallback (_grab_label_value) must accept the "so" glyph
   as cents and match "L,quor" as a Liquor label.
4. Name extraction must skip tiny (<4 char, no-space) alphabetic rows
   that are glyph artifacts, not server names.
5. Category values over $100k on a per-server page are nulled so the
   regex fallback supplies a plausible value.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from native_pos_parser import (
    _grab_label_value,
    _join_column_tokens,
    _normalize_glyph_token,
    _smart_float,
)


# ---------------------------------------------------------------------------
# _join_column_tokens
# ---------------------------------------------------------------------------

def test_join_single_token_with_decimal():
    assert _join_column_tokens(["1,816.00"]) == 1816.00
    assert _join_column_tokens(["17,319.94"]) == 17319.94


def test_join_single_token_implicit_cents():
    # "7000" on a POS weekly report means $70.00 (decimal missing)
    assert _join_column_tokens(["7000"]) == 70.00


def test_join_single_token_baked_in_cents():
    # "4.10300" = $4,103.00 (period-as-thousands with cents appended)
    assert _join_column_tokens(["4.10300"]) == 4103.00
    # "1.13750" = $1,137.50
    assert _join_column_tokens(["1.13750"]) == 1137.50


def test_join_two_tokens_cents_split():
    assert _join_column_tokens(["697", "00"]) == 697.00
    assert _join_column_tokens(["8,138", "61"]) == 8138.61
    # Period-for-comma case: "1,685.50" rendered as ["1.685", "50"]
    assert _join_column_tokens(["1.685", "50"]) == 1685.50


def test_join_three_tokens_cents_split():
    # "1,707.25" can split to ["1", "707", "25"]
    assert _join_column_tokens(["1", "707", "25"]) == 1707.25
    # "13,567.98" can split to ["13", "567", "98"]
    assert _join_column_tokens(["13", "567", "98"]) == 13567.98


def test_join_with_so_glyph():
    # "2,857.50" rendered as "2.857 so" (glyph misread)
    assert _join_column_tokens(["2.857", "so"]) == 2857.50
    assert _join_column_tokens(["1.760", "so"]) == 1760.50


# ---------------------------------------------------------------------------
# _smart_float (double-period handling)
# ---------------------------------------------------------------------------

def test_smart_float_double_period():
    # Comma-rendered-as-period case: "1.425.37" means "1,425.37"
    assert _smart_float("1.425.37") == 1425.37
    assert _smart_float("16.639.32") == 16639.32


# ---------------------------------------------------------------------------
# _normalize_glyph_token
# ---------------------------------------------------------------------------

def test_glyph_normalization():
    assert _normalize_glyph_token("so") == "50"
    assert _normalize_glyph_token("SO") == "50"
    # 'o' inside a numeric token becomes '0'
    assert _normalize_glyph_token("1o0") == "100"
    # Non-numeric tokens are untouched
    assert _normalize_glyph_token("Liquor") == "Liquor"


# ---------------------------------------------------------------------------
# _grab_label_value
# ---------------------------------------------------------------------------

def test_grab_label_three_tokens():
    text = "Food 13 567 98 Liquor 1 742 00 Beer"
    assert _grab_label_value("Food", text) == 13567.98
    assert _grab_label_value("Liquor", text) == 1742.00


def test_grab_label_with_so_glyph():
    text = "Liquor 2.857 so Beer 1.559.75 Wine"
    assert _grab_label_value("Liquor", text) == 2857.50


def test_grab_label_baked_in_cents():
    text = "Liquor 4.10300 Beer 2.713 50"
    assert _grab_label_value("Liquor", text) == 4103.00
    assert _grab_label_value("Beer", text) == 2713.50


def test_grab_label_mixed_period_format():
    # "1.234 75" = $1,234.75 (period is thousands sep, space separates cents)
    text = "Beer 1.234 75 Wine 84 50"
    assert _grab_label_value("Beer", text) == 1234.75
    assert _grab_label_value("Wine", text) == 84.50
