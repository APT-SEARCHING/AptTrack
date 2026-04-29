"""Unit tests for the Equity Residential platform adapter."""
from __future__ import annotations

import json
import pytest

from app.services.scraper_agent.platforms.equity import (
    EquityAdapter,
    _parse_equity_unit_availability,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_html(unit_availability: dict) -> str:
    blob = json.dumps(unit_availability)
    return f"<html><head></head><body><script>var ea5=ea5||{{}};ea5.unitAvailability = {blob};\n</script></body></html>"


def _make_ua(bedroom_types: list) -> dict:
    return {"BedroomTypes": bedroom_types}


def _make_bt(display_name: str, bedroom_count: int, units: list) -> dict:
    return {"Id": 1, "DisplayName": display_name, "BedroomCount": bedroom_count, "AvailableUnits": units}


def _make_unit(
    fp_id="FP1", fp_name="1 Bedroom A", sqft=750, bed=1, bath=1, price=3000, avail="5/1/2026"
) -> dict:
    return {
        "LedgerId": "001",
        "UnitId": "101",
        "FloorplanId": fp_id,
        "FloorplanName": fp_name,
        "SqFt": sqft,
        "Bed": bed,
        "Bath": bath,
        "BestTerm": {"Length": 12, "Price": price},
        "AvailableDate": avail,
    }


ARCHSTONE_URL = "http://www.equityapartments.com/san-francisco-bay/fremont/archstone-fremont-center-apartments"
OTHER_URL = "https://www.example.com/apartments"


# ---------------------------------------------------------------------------
# detect()
# ---------------------------------------------------------------------------

class TestEquityDetect:
    def test_detects_equity_page_with_signal(self):
        html = _make_html(_make_ua([]))
        assert EquityAdapter().detect(html, ARCHSTONE_URL) is True

    def test_rejects_non_equity_domain(self):
        html = _make_html(_make_ua([]))
        assert EquityAdapter().detect(html, OTHER_URL) is False

    def test_rejects_missing_signal(self):
        assert EquityAdapter().detect("<html>no signal here</html>", ARCHSTONE_URL) is False

    def test_rejects_empty_html(self):
        assert EquityAdapter().detect("", ARCHSTONE_URL) is False


# ---------------------------------------------------------------------------
# _parse_equity_unit_availability()
# ---------------------------------------------------------------------------

class TestParseEquityUnitAvailability:
    def test_single_unit_extracted(self):
        html = _make_html(_make_ua([
            _make_bt("1 Bed", 1, [_make_unit(price=3015)])
        ]))
        plans = _parse_equity_unit_availability(html)
        assert len(plans) == 1
        assert plans[0]["plan_name"] == "1 Bedroom A"
        assert plans[0]["price"] == 3015
        assert plans[0]["bedrooms"] == 1.0
        assert plans[0]["bathrooms"] == 1.0
        assert plans[0]["size_sqft"] == 750.0

    def test_multiple_units_same_plan_takes_min_price(self):
        html = _make_html(_make_ua([
            _make_bt("1 Bed", 1, [
                _make_unit(fp_id="FP1", fp_name="1 Bedroom A", price=3200),
                _make_unit(fp_id="FP1", fp_name="1 Bedroom A", price=3015),
                _make_unit(fp_id="FP1", fp_name="1 Bedroom A", price=3116),
            ])
        ]))
        plans = _parse_equity_unit_availability(html)
        assert len(plans) == 1
        assert plans[0]["price"] == 3015

    def test_different_floor_plans_produce_separate_rows(self):
        html = _make_html(_make_ua([
            _make_bt("1 Bed", 1, [
                _make_unit(fp_id="FP1", fp_name="1 Bedroom A", sqft=723, price=3015),
                _make_unit(fp_id="FP2", fp_name="1 Bedroom F", sqft=925, price=3243),
            ])
        ]))
        plans = _parse_equity_unit_availability(html)
        assert len(plans) == 2
        names = {p["plan_name"] for p in plans}
        assert names == {"1 Bedroom A", "1 Bedroom F"}

    def test_multiple_bedroom_types(self):
        html = _make_html(_make_ua([
            _make_bt("1 Bed", 1, [_make_unit(fp_id="FP1", fp_name="1 Bedroom A", bed=1, price=3015)]),
            _make_bt("2 Bed", 2, [_make_unit(fp_id="FP2", fp_name="2 Bedrooms A", bed=2, sqft=982, price=3433)]),
            _make_bt("3 Bed", 3, [_make_unit(fp_id="FP3", fp_name="3+ Bedrooms B", bed=3, sqft=1421, bath=2, price=4469)]),
        ]))
        plans = _parse_equity_unit_availability(html)
        assert len(plans) == 3
        by_name = {p["plan_name"]: p for p in plans}
        assert by_name["1 Bedroom A"]["bedrooms"] == 1.0
        assert by_name["2 Bedrooms A"]["bedrooms"] == 2.0
        assert by_name["3+ Bedrooms B"]["bedrooms"] == 3.0
        assert by_name["3+ Bedrooms B"]["bathrooms"] == 2.0

    def test_available_date_converted_to_iso(self):
        html = _make_html(_make_ua([
            _make_bt("1 Bed", 1, [_make_unit(avail="6/12/2026")])
        ]))
        plans = _parse_equity_unit_availability(html)
        assert plans[0]["available_from"] == "2026-06-12"

    def test_missing_available_date_is_none(self):
        unit = _make_unit()
        unit.pop("AvailableDate", None)
        html = _make_html(_make_ua([_make_bt("1 Bed", 1, [unit])]))
        plans = _parse_equity_unit_availability(html)
        assert plans[0]["available_from"] is None

    def test_no_signal_returns_empty(self):
        plans = _parse_equity_unit_availability("<html>no data here</html>")
        assert plans == []

    def test_empty_bedroom_types_returns_empty(self):
        html = _make_html(_make_ua([]))
        plans = _parse_equity_unit_availability(html)
        assert plans == []

    def test_all_plans_have_available_status(self):
        html = _make_html(_make_ua([
            _make_bt("1 Bed", 1, [_make_unit()])
        ]))
        plans = _parse_equity_unit_availability(html)
        assert plans[0]["availability"] == "available"
