
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def normalize_header(header: str) -> str:
    """Normalize a CSV header before matching it to a schema field."""
    value = header.strip().lower()
    return re.sub(r"[_\s]+", " ", value)


def normalize_phone(value: str) -> str:
    """
    Normalize an Indian mobile number to +91XXXXXXXXXX.

    Raises ValueError if the number is invalid.
    """
    digits = re.sub(r"\D", "", value)

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError("invalid_phone")

    return "+91" + digits


def normalize_date(value: str) -> date:
    """Parse supported date formats. Invalid dates raise ValueError."""
    value = value.strip()

    formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d-%b-%Y",
    )

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise ValueError("invalid_date")


def normalize_decimal(value: str) -> Decimal:
    """Parse a non-negative rupee amount and round it to two decimals."""
    cleaned = value.strip()

    cleaned = re.sub(
        r"^(?:₹|rs\.?|inr)\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = cleaned.replace(",", "")

    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError("invalid_decimal")

    if not amount.is_finite() or amount < 0:
        raise ValueError("invalid_decimal")

    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
