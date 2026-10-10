"""Identifier validators: IBAN (ISO 13616 mod-97) and EU VAT IDs for FI / SE / DE."""

import re

_IBAN_LENGTHS: dict[str, int] = {
    "AT": 20, "BE": 16, "CH": 21, "DE": 22, "DK": 18, "EE": 20, "ES": 24, "FI": 18,
    "FR": 27, "GB": 22, "IE": 22, "IT": 27, "LT": 20, "LU": 20, "LV": 21, "NL": 18,
    "NO": 15, "PL": 28, "PT": 25, "SE": 24,
}  # fmt: skip

ISO_4217 = frozenset({"EUR", "SEK", "USD", "GBP", "NOK", "DKK", "CHF", "PLN", "JPY", "CAD", "AUD"})


def normalize_iban(iban: str) -> str:
    return re.sub(r"\s+", "", iban).upper()


def iban_checksum(country: str, bban: str) -> str:
    """Compute the two check digits for ``country`` + ``bban``."""
    rearranged = f"{bban}{country}00"
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return f"{98 - int(numeric) % 97:02d}"


def is_valid_iban(iban: str) -> bool:
    value = normalize_iban(iban)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{8,30}", value):
        return False
    expected_len = _IBAN_LENGTHS.get(value[:2])
    if expected_len is not None and len(value) != expected_len:
        return False
    rearranged = value[4:] + value[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1


def normalize_vat_id(vat_id: str) -> str:
    return re.sub(r"[\s.\-]", "", vat_id).upper()


def fi_vat_check_digit(base7: str) -> int | None:
    """Finnish business ID (Y-tunnus) check digit; ``None`` means the base is invalid."""
    weights = (7, 9, 10, 5, 8, 4, 2)
    remainder = sum(int(d) * w for d, w in zip(base7, weights, strict=True)) % 11
    if remainder == 0:
        return 0
    if remainder == 1:
        return None
    return 11 - remainder


def luhn_check_digit(digits: str) -> int:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def de_vat_check_digit(base8: str) -> int:
    """ISO 7064 MOD 11,10 as used by the German USt-IdNr."""
    product = 10
    for ch in base8:
        total = (int(ch) + product) % 10 or 10
        product = (2 * total) % 11
    return (11 - product) % 10


def is_valid_vat_id(vat_id: str) -> bool:
    """Format + checksum validation for FI, SE and DE; other countries get a format check."""
    value = normalize_vat_id(vat_id)
    country, body = value[:2], value[2:]
    if country == "FI":
        if not re.fullmatch(r"\d{8}", body):
            return False
        check = fi_vat_check_digit(body[:7])
        return check is not None and check == int(body[7])
    if country == "SE":
        if not re.fullmatch(r"\d{10}01", body):
            return False
        return luhn_check_digit(body[:9]) == int(body[9])
    if country == "DE":
        if not re.fullmatch(r"[1-9]\d{8}", body):
            return False
        return de_vat_check_digit(body[:8]) == int(body[8])
    return bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{2,13}", value))


def is_valid_currency(code: str) -> bool:
    return code.upper() in ISO_4217
