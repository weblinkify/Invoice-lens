import pytest

from app.domain.validators import (
    de_vat_check_digit,
    fi_vat_check_digit,
    iban_checksum,
    is_valid_currency,
    is_valid_iban,
    is_valid_vat_id,
    luhn_check_digit,
    normalize_iban,
)


@pytest.mark.parametrize(
    "iban",
    [
        "FI2112345600000785",
        "FI21 1234 5600 0007 85",
        "SE4550000000058398257466",
        "DE89370400440532013000",
        "de89 3704 0044 0532 0130 00",
        "GB82WEST12345698765432",
    ],
)
def test_valid_ibans(iban: str) -> None:
    assert is_valid_iban(iban)


@pytest.mark.parametrize(
    "iban",
    [
        "FI2112345600000786",  # bad checksum
        "DE8937040044053201300",  # wrong length for DE
        "XX00",  # too short
        "1234567890123456",  # no country
        "",
    ],
)
def test_invalid_ibans(iban: str) -> None:
    assert not is_valid_iban(iban)


def test_iban_checksum_roundtrip() -> None:
    bban = "12345600000785"
    assert iban_checksum("FI", bban) == "21"
    assert is_valid_iban(f"FI{iban_checksum('FI', bban)}{bban}")


def test_normalize_iban() -> None:
    assert normalize_iban(" fi21 1234\t56 ") == "FI21123456"


@pytest.mark.parametrize(
    ("vat_id", "valid"),
    [
        ("FI12345671", True),
        ("FI 1234567-1", True),
        ("FI12345672", False),  # wrong check digit
        ("FI1234567", False),  # too short
        ("SE556036079301", True),
        ("SE556036079401", False),  # Luhn fails
        ("SE556036079302", False),  # must end in 01
        ("DE136695976", True),
        ("DE136695977", False),
        ("DE036695976", False),  # leading zero not allowed
        ("NL123456789B01", True),  # other countries: format only
        ("N1", False),
    ],
)
def test_vat_ids(vat_id: str, valid: bool) -> None:
    assert is_valid_vat_id(vat_id) is valid


def test_fi_check_digit_remainder_one_is_invalid() -> None:
    # Weighted sum 1*7 ... chosen so remainder is 1 → base is unusable.
    bases = [f"{i:07d}" for i in range(0, 200)]
    assert any(fi_vat_check_digit(b) is None for b in bases)
    assert fi_vat_check_digit("0000000") == 0


def test_luhn_and_de_digits() -> None:
    assert luhn_check_digit("556036079") == 3
    assert de_vat_check_digit("13669597") == 6


@pytest.mark.parametrize(("code", "ok"), [("EUR", True), ("sek", True), ("XYZ", False)])
def test_currency(code: str, ok: bool) -> None:
    assert is_valid_currency(code) is ok
