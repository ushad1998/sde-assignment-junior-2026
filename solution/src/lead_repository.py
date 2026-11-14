
import json
import sqlite3

from solution.src.security import PIISecurity


def insert_or_merge_lead(
    connection: sqlite3.Connection,
    workflow_id: str,
    batch_id: str,
    normalized_row: dict,
    schema: dict,
    security: PIISecurity,
) -> bool:
    """
    Insert a new lead or merge it with an existing lead.

    A lead is identified by workflow_id + phone fingerprint.

    Returns:
        False: A new lead was inserted.
        True: An existing lead was merged.

    This function does not commit. The caller controls the
    transaction so lead changes and processed-file tracking
    can be committed together.
    """

    # Identify PII and reference fields using the workflow schema.
    pii_fields = [
        field["name"]
        for field in schema["fields"]
        if field.get("pii", False)
    ]

    reference_fields = [
        field["name"]
        for field in schema["fields"]
        if field.get("reference", False)
    ]

    # Our current database structure has dedicated encrypted
    # columns for customer_name and phone.
    supported_pii_fields = {"customer_name", "phone"}

    unsupported_pii_fields = set(pii_fields) - supported_pii_fields

    if unsupported_pii_fields:
        raise ValueError(
            f"Unsupported PII fields: {sorted(unsupported_pii_fields)}"
        )

    if "phone" not in pii_fields:
        raise ValueError("The workflow schema must mark phone as PII")

    # Get the canonical phone number and create its HMAC fingerprint.
    canonical_phone = normalized_row.get("phone")

    if not canonical_phone:
        raise ValueError("A normalized phone number is required")

    phone_fingerprint = security.phone_fingerprint(canonical_phone)

    # Encrypt the phone number before storing it.
    encrypted_phone = security.encrypt(canonical_phone)

    # Encrypt the customer name if it is available.
    customer_name = normalized_row.get("customer_name")

    encrypted_customer_name = (
        security.encrypt(customer_name)
        if customer_name is not None
        else None
    )

    # Extract the workflow's reference field.
    external_ref = None

    if reference_fields:
        external_ref = normalized_row.get(reference_fields[0])

    # Collect only non-PII, non-reference fields.
    other_fields = {}

    for field in schema["fields"]:
        field_name = field["name"]

        if field_name in pii_fields or field_name in reference_fields:
            continue

        value = normalized_row.get(field_name)

        if value is not None:
            other_fields[field_name] = value

    # Look for an existing lead with the same workflow and phone.
    existing_lead = connection.execute(
        """
        SELECT *
        FROM leads
        WHERE workflow_id = ?
          AND phone_fingerprint = ?
        """,
        (workflow_id, phone_fingerprint),
    ).fetchone()

    # Case 1: This is a new lead.
    if existing_lead is None:
        connection.execute(
            """
            INSERT INTO leads (
                workflow_id,
                phone_fingerprint,
                customer_name_encrypted,
                phone_encrypted,
                external_ref,
                batch_id,
                other_fields_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                phone_fingerprint,
                encrypted_customer_name,
                encrypted_phone,
                external_ref,
                batch_id,
                json.dumps(other_fields),
            ),
        )

        return False

    # Case 2: This lead already exists.
    # Keep its original batch_id.

    merged_customer_name = existing_lead["customer_name_encrypted"]
    if encrypted_customer_name is not None:
        merged_customer_name = encrypted_customer_name

    merged_external_ref = existing_lead["external_ref"]
    if external_ref is not None:
        merged_external_ref = external_ref

    # Merge other fields. Incoming non-null values take priority.
    merged_other_fields = json.loads(
        existing_lead["other_fields_json"]
    )
    merged_other_fields.update(other_fields)

    connection.execute(
        """
        UPDATE leads
        SET
            customer_name_encrypted = ?,
            phone_encrypted = ?,
            external_ref = ?,
            other_fields_json = ?
        WHERE id = ?
        """,
        (
            merged_customer_name,
            encrypted_phone,
            merged_external_ref,
            json.dumps(merged_other_fields),
            existing_lead["id"],
        ),
    )

    return True
