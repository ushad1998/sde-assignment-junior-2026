
import csv
from pathlib import Path

from solution.src.schema_loader import map_csv_headers

from solution.src.normalization import (
    normalize_phone,
    normalize_date,
    normalize_decimal,
)


def validate_lead_row(
    raw_row: dict,
    schema: dict,
) -> tuple[dict | None, str | None, list[str]]:
    """
    Validate and normalize one CSV row against its workflow schema.

    Returns:
        normalized_row: Validated field values, or None if rejected.
        rejection_reason: Rejection reason, or None if valid.
        warnings: Optional-field validation warnings.
    """

    normalized_row = {}
    warnings = []

    # Process fields in schema order.
    for field in schema["fields"]:

        field_name = field["name"]
        field_type = field["type"]
        required = field.get("required", False)

        raw_value = raw_row.get(field_name)
        value = str(raw_value).strip() if raw_value is not None else ""

        # Check required fields first.
        if not value:
            if required:
                return None, f"missing_required:{field_name}", warnings

            normalized_row[field_name] = None
            continue

        try:
            if field_type == "phone":
                normalized_value = normalize_phone(value)

            elif field_type == "date":
                normalized_value = normalize_date(value).isoformat()

            elif field_type == "decimal":
                normalized_value = str(normalize_decimal(value))

            elif field_type == "enum":
                normalized_value = value.lower()

                allowed_values = [
                    item.lower() for item in field.get("values", [])
                ]

                if normalized_value not in allowed_values:
                    raise ValueError("invalid_enum")

            elif field_type == "string":
                normalized_value = value

            else:
                raise ValueError(
                    f"unsupported_field_type:{field_type}"
                )

            normalized_row[field_name] = normalized_value

        except ValueError:
            # Invalid required phone numbers reject the entire row.
            if required and field_type == "phone":
                return None, "invalid_phone", warnings

            # Invalid optional values become NULL and create warnings.
            normalized_row[field_name] = None
            warnings.append(f"invalid_{field_type}:{field_name}")

    return normalized_row, None, warnings


def read_csv_rows(
    file_path: str | Path,
    schema: dict,
):
    """
    Read a lead CSV and yield canonical rows.

    Each item contains:
        row_number: Nonblank data-row number, starting at 1.
        raw_row: Dictionary using canonical schema field names.
    """

    file_path = Path(file_path)

    with file_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:

        reader = csv.reader(csv_file)

        # Read the CSV header.
        headers = next(reader, None)

        # Handle an empty file.
        if headers is None:
            return

        # Map CSV columns to canonical schema field names.
        column_mapping = map_csv_headers(headers, schema)

        row_number = 0

        for csv_row in reader:

            # Skip completely blank rows.
            if not any(
                value.strip()
                for value in csv_row
                if value is not None
            ):
                continue

            # Count only nonblank data rows.
            row_number += 1

            raw_row = {}

            # Extract recognized columns and ignore unknown columns.
            for field_name, column_index in column_mapping.items():

                if column_index < len(csv_row):
                    raw_row[field_name] = csv_row[column_index]
                else:
                    raw_row[field_name] = ""

            yield row_number, raw_row
