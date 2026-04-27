"""Tests for _extract_price_from_card_text — BUG-01 deposit/fee filtering."""
from __future__ import annotations

import pytest
from app.services.scraper_agent.platforms.universal_dom import _extract_price_from_card_text


def test_deposit_then_rent():
    """Camden Village layout: deposit appears before rent in DOM."""
    text = "1 Bed 720 sqft Deposit: $1,000 $2,055/mo Available now"
    assert _extract_price_from_card_text(text) == 2055.0


def test_deposit_starting_at_then_rent():
    """Hazelwood layout: 'Deposit Starting at $500' with no rent → None."""
    text = "Studio 310 sqft Rent Call for details Deposit Starting at $500"
    assert _extract_price_from_card_text(text) is None


def test_admin_fee_then_rent():
    """Admin fee appears before rent — should not be picked up."""
    text = "Studio $300 admin fee $2,500/mo"
    assert _extract_price_from_card_text(text) == 2500.0


def test_only_deposit_returns_none():
    """Only a deposit amount present — should return None."""
    text = "Studio Deposit Starting at $500"
    assert _extract_price_from_card_text(text) is None


def test_rent_with_decimal():
    """Decimal rent price parses correctly."""
    text = "$2,055.50 per month"
    assert _extract_price_from_card_text(text) == 2055.50


def test_plain_price_above_floor():
    """No /mo suffix but price is above $1,000 floor — Pass B catches it."""
    text = "1BR · 720 sqft · $2,055"
    assert _extract_price_from_card_text(text) == 2055.0


def test_plain_price_below_floor():
    """Price below $1,000 floor is rejected (application fee, not rent)."""
    text = "Application fee $50"
    assert _extract_price_from_card_text(text) is None


def test_rent_first_then_deposit():
    """Pass A finds /mo price first; deposit is ignored."""
    text = "$2,055/mo + $1,000 deposit"
    assert _extract_price_from_card_text(text) == 2055.0


def test_existing_canonical_miro():
    """Regression: Miro-style card text extracts price unchanged."""
    text = "A17 + Den 1 bed 1 bath 1002 sqft $4,023 / mo Available Now"
    assert _extract_price_from_card_text(text) == 4023.0


def test_existing_canonical_ryden():
    """Regression: The Ryden style — bare price above $1,000."""
    text = "1 Bedroom 1 Bath 750 sqft $2,865"
    assert _extract_price_from_card_text(text) == 2865.0


def test_pet_fee_then_rent():
    """Pet fee stripped; rent extracted via Pass B."""
    text = "2 Bed 2 Bath pet fee $75 $3,500"
    assert _extract_price_from_card_text(text) == 3500.0


def test_empty_text_returns_none():
    assert _extract_price_from_card_text("") is None


def test_none_text_returns_none():
    assert _extract_price_from_card_text(None) is None
