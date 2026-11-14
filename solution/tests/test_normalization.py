
# Import the functions we want to test from our normalization module.
from decimal import Decimal
from solution.src.normalization import (
    normalize_header,
    normalize_phone,
    normalize_date,
    normalize_decimal,
)


def test_normalize_header():
    # Different spaces and underscores should become one space.
    assert normalize_header(" Customer_Name ") == "customer name"


def test_normalize_phone():
    # All these formats should produce the same canonical phone number.
    assert normalize_phone("+91 98765 43210") == "+919876543210"
    assert normalize_phone("09876543210") == "+919876543210"
    assert normalize_phone("919876543210") == "+919876543210"


def test_invalid_phone():
    # An invalid phone number must raise a ValueError.
    try:
        normalize_phone("12345")
        assert False, "Expected an invalid phone number to raise ValueError"
    except ValueError as error:
        assert str(error) == "invalid_phone"


def test_normalize_date():
    # The supported input formats should produce the same date.
    assert str(normalize_date("2026-11-21")) == "2026-11-21"
    assert str(normalize_date("21/11/2026")) == "2026-11-21"
    assert str(normalize_date("21-Nov-2026")) == "2026-11-21"


def test_invalid_date():
    # November cannot have a 31st day.
    try:
        normalize_date("31-11-2026")
        assert False, "Expected an invalid date to raise ValueError"
    except ValueError as error:
        assert str(error) == "invalid_date"



def test_normalize_decimal():
    # Currency symbols and prefixes should be removed.
    # Decimal values are compared with Decimal values, not floats.
    assert normalize_decimal("₹27,554") == Decimal("27554.00")
    assert normalize_decimal("Rs. 26505") == Decimal("26505.00")
    assert normalize_decimal("INR 33473.7") == Decimal("33473.70")
