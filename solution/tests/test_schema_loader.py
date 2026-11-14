from pathlib import Path

from solution.src.schema_loader import (
    load_workflow_schemas,
    map_csv_headers,
)


# Locate the schema directory from the project root.
SCHEMA_DIR = Path("assignment-a-data/schemas")


def test_both_workflow_schemas_load():
    schemas = load_workflow_schemas(SCHEMA_DIR)

    assert "motor_renewal" in schemas
    assert "policy_feedback" in schemas


def test_motor_renewal_headers_are_mapped():
    schemas = load_workflow_schemas(SCHEMA_DIR)

    headers = [
        "Language",
        "Insured Name",
        "Policy No",
        "Mobile No",
        "Expiry Date",
        "Premium",
        "agent_notes",
    ]

    mapping = map_csv_headers(headers, schemas["motor_renewal"])

    assert mapping == {
        "preferred_language": 0,
        "customer_name": 1,
        "policy_number": 2,
        "phone": 3,
        "policy_expiry": 4,
        "premium_amount": 5,
    }


def test_policy_feedback_headers_are_mapped():
    schemas = load_workflow_schemas(SCHEMA_DIR)

    headers = [
        "Order ID",
        "Name",
        "Contact",
        "Product",
        "Order Date",
        "Language",
        "agent_notes",
    ]

    mapping = map_csv_headers(headers, schemas["policy_feedback"])

    assert mapping == {
        "order_id": 0,
        "customer_name": 1,
        "phone": 2,
        "product": 3,
        "order_date": 4,
        "preferred_language": 5,
    }


def test_unknown_columns_are_ignored():
    schemas = load_workflow_schemas(SCHEMA_DIR)

    headers = ["Name", "Mobile No", "extra_column"]

    mapping = map_csv_headers(headers, schemas["policy_feedback"])

    assert "extra_column" not in mapping
    assert mapping["customer_name"] == 0
    assert mapping["phone"] == 1