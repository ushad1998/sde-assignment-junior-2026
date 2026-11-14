
import json
import sqlite3

from cryptography.fernet import Fernet

from solution.src.database import initialize_database
from solution.src.security import PIISecurity
from solution.src.schema_loader import load_workflow_schemas
from solution.src.lead_repository import insert_or_merge_lead


def setup_repository():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row

    initialize_database(connection)

    security = PIISecurity(
        Fernet.generate_key().decode("utf-8"),
        "a" * 64,
    )

    schemas = load_workflow_schemas("assignment-a-data/schemas")

    return connection, security, schemas


def test_insert_new_lead():
    connection, security, schemas = setup_repository()

    row = {
        "customer_name": "Rahul",
        "phone": "+919876543210",
        "policy_number": "POL123",
        "policy_expiry": "2026-12-15",
        "premium_amount": "25500.00",
        "preferred_language": "kn",
    }

    duplicate = insert_or_merge_lead(
        connection,
        "motor_renewal",
        "batch_001",
        row,
        schemas["motor_renewal"],
        security,
    )

    assert duplicate is False

    lead = connection.execute(
        "SELECT * FROM leads"
    ).fetchone()

    assert lead["workflow_id"] == "motor_renewal"
    assert lead["batch_id"] == "batch_001"
    assert lead["phone_fingerprint"] == security.phone_fingerprint(
        "+919876543210"
    )

    # PII must not be stored as plaintext.
    assert lead["customer_name_encrypted"] != "Rahul"
    assert lead["phone_encrypted"] != "+919876543210"

    # Other non-PII fields are stored as JSON.
    fields = json.loads(lead["other_fields_json"])
    assert fields["preferred_language"] == "kn"

    connection.close()


def test_duplicate_lead_is_merged():
    connection, security, schemas = setup_repository()

    first_row = {
        "customer_name": "Rahul",
        "phone": "+919876543210",
        "policy_number": "POL123",
        "policy_expiry": None,
        "premium_amount": None,
        "preferred_language": None,
    }

    second_row = {
        "customer_name": "Rahul Kumar",
        "phone": "+919876543210",
        "policy_number": "POL456",
        "policy_expiry": "2026-12-15",
        "premium_amount": "25500.00",
        "preferred_language": "kn",
    }

    first_result = insert_or_merge_lead(
        connection,
        "motor_renewal",
        "batch_001",
        first_row,
        schemas["motor_renewal"],
        security,
    )

    second_result = insert_or_merge_lead(
        connection,
        "motor_renewal",
        "batch_002",
        second_row,
        schemas["motor_renewal"],
        security,
    )

    assert first_result is False
    assert second_result is True

    leads = connection.execute(
        "SELECT * FROM leads"
    ).fetchall()

    assert len(leads) == 1

    lead = leads[0]

    # Original batch must be preserved.
    assert lead["batch_id"] == "batch_001"

    # Latest non-null customer name must win.
    assert security.decrypt(
        lead["customer_name_encrypted"]
    ) == "Rahul Kumar"

    # Latest non-null reference must win.
    assert lead["external_ref"] == "POL456"

    # Non-null fields from the duplicate must be merged.
    fields = json.loads(lead["other_fields_json"])

    assert fields["policy_expiry"] == "2026-12-15"
    assert fields["premium_amount"] == "25500.00"
    assert fields["preferred_language"] == "kn"

    connection.close()


def test_null_values_do_not_overwrite_existing_values():
    connection, security, schemas = setup_repository()

    first_row = {
        "customer_name": "Rahul",
        "phone": "+919876543210",
        "policy_number": "POL123",
        "policy_expiry": "2026-12-15",
        "premium_amount": "25500.00",
        "preferred_language": "kn",
    }

    second_row = {
        "customer_name": None,
        "phone": "+919876543210",
        "policy_number": None,
        "policy_expiry": None,
        "premium_amount": None,
        "preferred_language": None,
    }

    insert_or_merge_lead(
        connection,
        "motor_renewal",
        "batch_001",
        first_row,
        schemas["motor_renewal"],
        security,
    )

    insert_or_merge_lead(
        connection,
        "motor_renewal",
        "batch_002",
        second_row,
        schemas["motor_renewal"],
        security,
    )

    lead = connection.execute(
        "SELECT * FROM leads"
    ).fetchone()

    assert lead["batch_id"] == "batch_001"
    assert security.decrypt(
        lead["customer_name_encrypted"]
    ) == "Rahul"
    assert lead["external_ref"] == "POL123"

    fields = json.loads(lead["other_fields_json"])

    assert fields["preferred_language"] == "kn"
    assert fields["premium_amount"] == "25500.00"

    connection.close()


def test_same_phone_in_different_workflows_creates_separate_leads():
    connection, security, schemas = setup_repository()

    motor_row = {
        "customer_name": "Rahul",
        "phone": "+919876543210",
        "policy_number": "POL123",
        "policy_expiry": None,
        "premium_amount": None,
        "preferred_language": None,
    }

    feedback_row = {
        "customer_name": "Rahul",
        "phone": "+919876543210",
        "order_id": "ORD123",
        "product": "Phone",
        "order_date": None,
        "preferred_language": None,
    }

    insert_or_merge_lead(
        connection,
        "motor_renewal",
        "batch_001",
        motor_row,
        schemas["motor_renewal"],
        security,
    )

    insert_or_merge_lead(
        connection,
        "policy_feedback",
        "batch_001",
        feedback_row,
        schemas["policy_feedback"],
        security,
    )

    count = connection.execute(
        "SELECT COUNT(*) FROM leads"
    ).fetchone()[0]

    assert count == 2

    connection.close()
