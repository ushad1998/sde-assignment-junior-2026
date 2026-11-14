
import csv
from pathlib import Path

from solution.src.schema_loader import load_workflow_schemas
from solution.src.lead_ingestion import (
    validate_lead_row,
    read_csv_rows,
)


SCHEMA_DIR = Path("assignment-a-data/schemas")


def test_valid_motor_renewal_row():
    schemas = load_workflow_schemas(SCHEMA_DIR)

    row = {
        "customer_name": " Rahul ",
        "phone": "9876543210",
        "policy_number": "POL123",
        "policy_expiry": "15/12/2026",
        "premium_amount": "₹25,500",
        "preferred_language": "KN",
    }

    result, reason, warnings = validate_lead_row(
        row, schemas["motor_renewal"]
    )

    assert reason is None
    assert warnings == []
    assert result["customer_name"] == "Rahul"
    assert result["phone"] == "+919876543210"
    assert result["policy_expiry"] == "2026-12-15"
    assert result["premium_amount"] == "25500.00"
    assert result["preferred_language"] == "kn"


def test_missing_required_field_rejects_row():
    schemas = load_workflow_schemas(SCHEMA_DIR)

    row = {
        "customer_name": "",
        "phone": "9876543210",
        "policy_number": "POL123",
    }

    result, reason, warnings = validate_lead_row(
        row, schemas["motor_renewal"]
    )

    assert result is None
    assert reason == "missing_required:customer_name"


def test_invalid_required_phone_rejects_row():
    schemas = load_workflow_schemas(SCHEMA_DIR)

    row = {
        "customer_name": "Rahul",
        "phone": "12345",
        "policy_number": "POL123",
    }

    result, reason, warnings = validate_lead_row(
        row, schemas["motor_renewal"]
    )

    assert result is None
    assert reason == "invalid_phone"


def test_invalid_optional_date_generates_warning():
    schemas = load_workflow_schemas(SCHEMA_DIR)

    row = {
        "customer_name": "Rahul",
        "phone": "9876543210",
        "policy_number": "POL123",
        "policy_expiry": "2026-13-01",
    }

    result, reason, warnings = validate_lead_row(
        row, schemas["motor_renewal"]
    )

    assert reason is None
    assert result["policy_expiry"] is None
    assert warnings == ["invalid_date:policy_expiry"]


def test_invalid_optional_enum_generates_warning():
    schemas = load_workflow_schemas(SCHEMA_DIR)

    row = {
        "customer_name": "Rahul",
        "phone": "9876543210",
        "policy_number": "POL123",
        "preferred_language": "xyz",
    }

    result, reason, warnings = validate_lead_row(
        row, schemas["motor_renewal"]
    )

    assert reason is None
    assert result["preferred_language"] is None
    assert warnings == ["invalid_enum:preferred_language"]


def test_csv_reader_maps_reordered_headers_and_ignores_extra_columns(tmp_path):
    schemas = load_workflow_schemas(SCHEMA_DIR)
    schema = schemas["motor_renewal"]

    csv_path = tmp_path / "leads.csv"

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "Language",
            "Insured Name",
            "Policy No",
            "Mobile No",
            "agent_notes",
        ])

        writer.writerow([
            "kn",
            "Rahul",
            "POL123",
            "9876543210",
            "Extra information",
        ])

    rows = list(read_csv_rows(csv_path, schema))

    assert len(rows) == 1
    assert rows[0][0] == 1
    assert rows[0][1]["customer_name"] == "Rahul"
    assert rows[0][1]["phone"] == "9876543210"
    assert rows[0][1]["policy_number"] == "POL123"
    assert "agent_notes" not in rows[0][1]


def test_csv_reader_skips_blank_rows_without_incrementing_row_number(tmp_path):
    schemas = load_workflow_schemas(SCHEMA_DIR)
    schema = schemas["motor_renewal"]

    csv_path = tmp_path / "leads_with_blank.csv"

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)

        writer.writerow(["Name", "Mobile No", "Policy No"])
        writer.writerow(["Rahul", "9876543210", "POL123"])
        writer.writerow(["", "", ""])
        writer.writerow(["Priya", "9876543211", "POL124"])

    rows = list(read_csv_rows(csv_path, schema))

    assert len(rows) == 2
    assert rows[0][0] == 1
    assert rows[1][0] == 2
    assert rows[1][1]["customer_name"] == "Priya"
