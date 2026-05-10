"""Currency parsing — turn raw matches like '$1,234.56' or 'EUR 200' into
a structured dict with an amount (float) and ISO 4217 currency code.
"""

from __future__ import annotations

import re
from typing import Optional, TypedDict


class NormalizedMoney(TypedDict, total=False):
    raw: str
    amount: float
    currency: str  # ISO 4217 (USD, EUR, GBP, ...)


# Symbol → ISO 4217
_SYMBOL_TO_CODE = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "₽": "RUB",
    "₩": "KRW",
    "₺": "TRY",
    "₪": "ILS",
    "R$": "BRL",
}

# Recognized 3-letter codes
_KNOWN_CODES = {
    "USD", "EUR", "GBP", "JPY", "INR", "EGP", "AED", "SAR", "CAD", "AUD",
    "CHF", "CNY", "HKD", "SGD", "NZD", "ZAR", "BRL", "MXN", "RUB", "KRW",
    "TRY", "ILS", "PLN", "SEK", "NOK", "DKK",
}

_AMOUNT_RE = re.compile(r"-?\d{1,3}(?:[,\s]\d{3})*(?:\.\d{1,2})?|-?\d+(?:\.\d{1,2})?")


def normalize_money(raw: str) -> Optional[NormalizedMoney]:
    """Best-effort parse. Returns None if no usable amount is found."""
    if not raw:
        return None

    text = raw.strip()
    currency: Optional[str] = None

    # 1. ISO code in the string?
    upper = text.upper()
    for code in _KNOWN_CODES:
        if re.search(rf"\b{code}\b", upper):
            currency = code
            break

    # 2. Symbol prefix?
    if currency is None:
        for symbol, code in _SYMBOL_TO_CODE.items():
            if symbol in text:
                currency = code
                break

    # 3. Amount
    amount_match = _AMOUNT_RE.search(text)
    if amount_match is None:
        return None

    amount_str = amount_match.group(0).replace(",", "").replace(" ", "")
    try:
        amount = float(amount_str)
    except ValueError:
        return None

    out: NormalizedMoney = {"raw": raw, "amount": amount}
    if currency:
        out["currency"] = currency
    return out
