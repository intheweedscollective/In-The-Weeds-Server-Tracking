"""
Regression tests for the POS upload pipeline.

Covers:
  - `extract_pos_pdf_native_first` prefers the native parser and falls
    through to AI OCR only when native parsing fails / returns nothing.
  - `_validate_sales_reconciliation` flags rows where category sales
    don't approximately sum to net sales.
  - `_filter_reconcilable_employees` splits an extraction batch into
    kept and rejected lists.

⚠️ These tests stub external functions (the AI OCR endpoint and the
native parser) so no PDF actually has to be parsed.
"""

import asyncio
import sys


def test_validate_sales_reconciliation_passes_clean_row():
    from routes.pos_upload import _validate_sales_reconciliation
    emp = {
        "name": "Alice",
        "net_sales": 1000.0,
        "food_sales": 600.0,
        "liquor_sales": 200.0,
        "beer_sales": 100.0,
        "wine_sales": 100.0,
    }
    assert _validate_sales_reconciliation(emp) is None


def test_validate_sales_reconciliation_tolerates_comps_and_discounts():
    """POS reports often have a 10-12% gap from comps / discounts /
    dessert / NA bev that don't appear in the 4 category columns."""
    from routes.pos_upload import _validate_sales_reconciliation
    emp = {
        "name": "Bob",
        "net_sales": 1000.0,
        "food_sales": 540.0,
        "liquor_sales": 180.0,
        "beer_sales": 90.0,
        "wine_sales": 90.0,  # sum = 900, 10% gap → still ok
    }
    assert _validate_sales_reconciliation(emp) is None


def test_validate_sales_reconciliation_flags_obvious_extraction_errors():
    """Categories that drift > 15% from net are very likely an OCR
    miss-column or lost decimal point."""
    from routes.pos_upload import _validate_sales_reconciliation
    emp = {
        "name": "Carol",
        "net_sales": 1000.0,
        "food_sales": 60.0,   # missing zero — extraction error
        "liquor_sales": 20.0,
        "beer_sales": 10.0,
        "wine_sales": 10.0,   # sum = 100, off by 90%
    }
    reason = _validate_sales_reconciliation(emp)
    assert reason is not None
    assert "drift" in reason.lower() or "reconcile" in reason.lower() or "extraction" in reason.lower()


def test_validate_skips_when_no_category_breakdown():
    """Some POS summary pages only have net_sales — we can't judge
    those, must let them through."""
    from routes.pos_upload import _validate_sales_reconciliation
    emp = {"name": "D", "net_sales": 500.0, "food_sales": 0,
           "liquor_sales": 0, "beer_sales": 0, "wine_sales": 0}
    assert _validate_sales_reconciliation(emp) is None


def test_validate_skips_tiny_rows():
    """Rounding noise dominates below $50 net; don't flag."""
    from routes.pos_upload import _validate_sales_reconciliation
    emp = {"name": "E", "net_sales": 30.0,
           "food_sales": 10, "liquor_sales": 5,
           "beer_sales": 0, "wine_sales": 0}
    assert _validate_sales_reconciliation(emp) is None


def test_filter_reconcilable_splits_kept_and_rejected():
    from routes.pos_upload import _filter_reconcilable_employees
    employees = [
        {"name": "Good", "net_sales": 1000, "food_sales": 600,
         "liquor_sales": 200, "beer_sales": 100, "wine_sales": 100},
        {"name": "Bad",  "net_sales": 1000, "food_sales": 60,
         "liquor_sales": 20, "beer_sales": 10, "wine_sales": 10},
        {"name": "NoBreakdown", "net_sales": 500},  # passes (no category data)
    ]
    out = _filter_reconcilable_employees(employees)
    assert {e["name"] for e in out["kept"]} == {"Good", "NoBreakdown"}
    assert len(out["rejected"]) == 1
    assert out["rejected"][0]["name"] == "Bad"


def test_extract_pos_pdf_native_first_prefers_native(monkeypatch=None):
    """Native parser succeeds → AI OCR is NOT called."""
    import routes.pos_upload as pu

    async def fake_ocr(*a, **kw):
        raise AssertionError("AI OCR should not have been called")

    # Patch the AI OCR import target. The route function imports at runtime.
    import pos_ocr
    original_pos_ocr = pos_ocr.extract_pos_data_from_pdf
    pos_ocr.extract_pos_data_from_pdf = fake_ocr

    # Stub native parser to return one good row.
    import native_pos_parser
    original_native = native_pos_parser.extract_pos_data_from_pdf_bytes_native
    original_check  = native_pos_parser.is_pdf_native_extractable
    native_pos_parser.is_pdf_native_extractable = lambda b: True
    def fake_native(_):
        return {
            "success": True,
            "employees": [{
                "name": "Alice",
                "guest_count": 10,
                "net_sales": 1000,
                "ppa": 100,
                "food_sales": 600,
                "liquor_sales": 200,
                "beer_sales": 100,
                "wine_sales": 100,
                "bar_glassware_sales": 50,
                "loyalty_sales": 30,
            }],
            "extraction_notes": "native parsed 1 employee",
        }
    native_pos_parser.extract_pos_data_from_pdf_bytes_native = fake_native

    try:
        result = asyncio.get_event_loop().run_until_complete(
            pu.extract_pos_pdf_native_first(b"%PDF-1.4\nfake-bytes")
        )
        assert result["extraction_method"] == "native_pdf"
        assert len(result["employees"]) == 1
        assert result["employees"][0]["name"] == "Alice"
    finally:
        pos_ocr.extract_pos_data_from_pdf = original_pos_ocr
        native_pos_parser.extract_pos_data_from_pdf_bytes_native = original_native
        native_pos_parser.is_pdf_native_extractable = original_check


def test_extract_pos_pdf_native_first_falls_back_to_ocr():
    """Native parser returns nothing → AI OCR is called."""
    import routes.pos_upload as pu

    async def fake_ocr(b, job_id=None):
        return {
            "employees": [{
                "name": "Bob",
                "guest_count": 5,
                "net_sales": 500,
                "food_sales": 300,
                "liquor_sales": 100,
                "beer_sales": 50,
                "wine_sales": 50,
            }],
            "extraction_notes": "ai ocr",
            "pages_processed": 1,
        }

    import pos_ocr
    import native_pos_parser
    original_ocr    = pos_ocr.extract_pos_data_from_pdf
    original_native = native_pos_parser.extract_pos_data_from_pdf_bytes_native
    original_check  = native_pos_parser.is_pdf_native_extractable
    pos_ocr.extract_pos_data_from_pdf = fake_ocr
    native_pos_parser.is_pdf_native_extractable = lambda b: True
    native_pos_parser.extract_pos_data_from_pdf_bytes_native = (
        lambda b: {"success": False, "employees": []}
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(
            pu.extract_pos_pdf_native_first(b"%PDF-1.4\nfake-bytes")
        )
        assert result["extraction_method"] == "ai_ocr"
        assert result["employees"][0]["name"] == "Bob"
    finally:
        pos_ocr.extract_pos_data_from_pdf = original_ocr
        native_pos_parser.extract_pos_data_from_pdf_bytes_native = original_native
        native_pos_parser.is_pdf_native_extractable = original_check
