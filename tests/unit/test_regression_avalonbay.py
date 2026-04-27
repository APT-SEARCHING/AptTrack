"""Regression tests for the AvalonBay adapter using saved HTML snapshots.

Each fixture is a real page captured at a known-good moment. Expected output is
stored in tests/fixtures/scraper_regression/expected/apt_<id>.json and verified
by hand at capture time. Prices are compared with ±10% tolerance because sites
update prices daily — the fixture is testing plan detection, not price liveness.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "scraper_regression"
AVALONBAY_DIR = FIXTURE_DIR / "avalonbay"
EXPECTED_DIR = FIXTURE_DIR / "expected"

CASES = [
    ("apt_158_avalon_fremont.html", "apt_158.json"),
    ("apt_167_ava_nob_hill.html",   "apt_167.json"),
    ("apt_179_eaves_san_jose.html", "apt_179.json"),
    ("apt_181_cahill_park.html",    "apt_181.json"),
]


def _load_avalonbay_parser():
    import sys
    integration_path = Path(__file__).parent.parent / "integration" / "agentic_scraper"
    if str(integration_path) not in sys.path:
        sys.path.insert(0, str(integration_path))
    from platforms.avalonbay import _parse_avalon_global_content
    return _parse_avalon_global_content


@pytest.mark.parametrize("html_file,expected_file", CASES, ids=[c[1] for c in CASES])
def test_avalonbay_adapter_plans(html_file, expected_file):
    parse = _load_avalonbay_parser()

    html = (AVALONBAY_DIR / html_file).read_text()
    expected = json.loads((EXPECTED_DIR / expected_file).read_text())

    actual_plans = parse(html)
    expected_plans = expected["plans"]

    # Plan count must match exactly — adapter must not drop or hallucinate plans.
    assert len(actual_plans) == len(expected_plans), (
        f"{expected_file}: expected {len(expected_plans)} plans, "
        f"got {len(actual_plans)}: {[p['plan_name'] for p in actual_plans]}"
    )

    actual_by_name = {p["plan_name"]: p for p in actual_plans}

    for exp in expected_plans:
        name = exp["plan_name"]
        assert name in actual_by_name, (
            f"{expected_file}: plan '{name}' missing from adapter output. "
            f"Got: {list(actual_by_name)}"
        )
        act = actual_by_name[name]

        assert int(act["bedrooms"]) == exp["bedrooms"], (
            f"{name}: bedrooms {act['bedrooms']} != {exp['bedrooms']}"
        )
        assert int(act["bathrooms"]) == exp["bathrooms"], (
            f"{name}: bathrooms {act['bathrooms']} != {exp['bathrooms']}"
        )
        assert act["size_sqft"] == exp["size_sqft"], (
            f"{name}: size_sqft {act['size_sqft']} != {exp['size_sqft']}"
        )

        exp_price = exp["price"]
        act_price = act["price"]
        if exp_price is None:
            assert act_price is None, (
                f"{name}: expected no price (unavailable), got {act_price}"
            )
        else:
            assert act_price is not None, (
                f"{name}: expected price ~{exp_price}, got None"
            )
            tolerance = exp_price * 0.10
            assert abs(act_price - exp_price) <= tolerance, (
                f"{name}: price {act_price} deviates >10% from baseline {exp_price}"
            )
