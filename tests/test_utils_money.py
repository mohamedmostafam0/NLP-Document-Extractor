"""Tests for the currency-normalization helper."""

from __future__ import annotations

from utils.money import normalize_money


def test_normalize_money_symbol_prefix():
    out = normalize_money("$1,234.56")
    assert out is not None
    assert out["amount"] == 1234.56
    assert out["currency"] == "USD"


def test_normalize_money_euro_symbol():
    out = normalize_money("€999")
    assert out is not None
    assert out["amount"] == 999.0
    assert out["currency"] == "EUR"


def test_normalize_money_iso_code():
    out = normalize_money("EUR 200")
    assert out is not None
    assert out["amount"] == 200.0
    assert out["currency"] == "EUR"


def test_normalize_money_iso_code_egp():
    out = normalize_money("EGP 250.75")
    assert out is not None
    assert out["amount"] == 250.75
    assert out["currency"] == "EGP"


def test_normalize_money_keeps_raw_string():
    out = normalize_money("$50")
    assert out is not None
    assert out["raw"] == "$50"


def test_normalize_money_no_amount_returns_none():
    assert normalize_money("abc") is None


def test_normalize_money_empty_returns_none():
    assert normalize_money("") is None


def test_normalize_money_no_currency_still_parses_amount():
    out = normalize_money("250.00")
    assert out is not None
    assert out["amount"] == 250.0
    assert "currency" not in out


def test_normalize_money_thousands_separator():
    out = normalize_money("$1,000,000")
    assert out is not None
    assert out["amount"] == 1_000_000.0
    assert out["currency"] == "USD"
