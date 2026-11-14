
import json
from pathlib import Path

from cryptography.fernet import Fernet

from solution.src.database import connect_database, initialize_database
from solution.src.security import PIISecurity
from solution.src.event_ingestion import (
    ingest_event_file,
    normalize_event_timestamp,
)


def setup_event_test(tmp_path):
    """Create an isolated database and test security instance."""

    database_path = tmp_path / "test.db"
    connection = connect_database(database_path)
    initialize_database(connection)

    security = PIISecurity(
        encryption_key=Fernet.generate_key().decode("utf-8"),
        hmac_key="11" * 32,
    )

    dispositions = {
        "motor_renewal": {
            "renewed": {
                "label": "Policy renewed",
                "is_terminal": True,
                "is_success": True,
            },
            "not_interested": {
                "label": "Not interested",
                "is_terminal": True,
                "is_success": False,
            },
        },
        "policy_feedback": {
            "feedback_captured": {
                "label": "Feedback captured",
                "is_terminal": True,
                "is_success": True,
            },
        },
    }

    data_root = tmp_path / "data"
    data_root.mkdir()

    return connection, security, dispositions, data_root


def write_events(file_path, events):
    """Write event dictionaries as JSONL."""

    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event) + "\n")


def make_event(
    event_id="evt_001",
    event_type="call.initiated",
    phone="+919876543210",
    payload=None,
):
    return {
        "event_id": event_id,
        "event_type": event_type,
        "workflow_id": "motor_renewal",
        "call_id": "call_001",
        "occurred_at": "2026-10-05T10:30:00Z",
        "phone": phone,
        "payload": payload or {},
    }


def test_normalize_utc_timestamp():
    result = normalize_event_timestamp("2026-10-05T10:30:00Z")

    assert result == "2026-10-05T10:30:00+00:00"


def test_normalize_naive_timestamp_as_ist():
    result = normalize_event_timestamp("2026-10-05 10:30:00")

    assert result == "2026-10-05T05:00:00+00:00"


def test_ingest_event_and_fingerprint_phone(tmp_path):
    connection, security, dispositions, data_root = setup_event_test(
        tmp_path
    )

    try:
        file_path = data_root / "drop_1" / "events" / "events_0001.jsonl"

        write_events(file_path, [make_event()])

        result = ingest_event_file(
            connection,
            file_path,
            data_root,
            security,
            dispositions,
        )

        assert result["status"] == "processed"
        assert result["events_total"] == 1
        assert result["malformed_events"] == 0

        stored = connection.execute(
            "SELECT * FROM events WHERE event_id = ?",
            ("evt_001",),
        ).fetchone()

        assert stored is not None
        assert stored["phone_fingerprint"] == security.phone_fingerprint(
            "+919876543210"
        )

        # The raw phone number must not be stored in the event row.
        assert "+919876543210" not in str(dict(stored))

    finally:
        connection.close()


def test_duplicate_event_id_is_dropped_across_files(tmp_path):
    connection, security, dispositions, data_root = setup_event_test(
        tmp_path
    )

    try:
        first_file = data_root / "drop_1" / "events" / "events_0001.jsonl"
        second_file = data_root / "drop_2" / "events" / "events_1001.jsonl"

        event = make_event()

        write_events(first_file, [event])
        write_events(second_file, [event])

        first_result = ingest_event_file(
            connection,
            first_file,
            data_root,
            security,
            dispositions,
        )

        second_result = ingest_event_file(
            connection,
            second_file,
            data_root,
            security,
            dispositions,
        )

        assert first_result["events_total"] == 1
        assert second_result["duplicate_events_dropped"] == 1

        count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_id = ?",
            ("evt_001",),
        ).fetchone()[0]

        assert count == 1

    finally:
        connection.close()


def test_malformed_events_are_skipped(tmp_path):
    connection, security, dispositions, data_root = setup_event_test(
        tmp_path
    )

    try:
        file_path = data_root / "drop_1" / "events" / "events_0001.jsonl"
        file_path.parent.mkdir(parents=True)

        with file_path.open("w", encoding="utf-8") as file:
            file.write("{invalid json}\n")
            file.write(json.dumps(make_event(phone="12345")) + "\n")

        result = ingest_event_file(
            connection,
            file_path,
            data_root,
            security,
            dispositions,
        )

        assert result["events_total"] == 2
        assert result["malformed_events"] == 2

        count = connection.execute(
            "SELECT COUNT(*) FROM events"
        ).fetchone()[0]

        assert count == 0

    finally:
        connection.close()


def test_override_event_links_when_call_event_arrives_later(tmp_path):
    connection, security, dispositions, data_root = setup_event_test(
        tmp_path
    )

    try:
        override = make_event(
            event_id="evt_override",
            event_type="disposition.override",
            phone=None,
            payload={"disposition_code": "not_interested"},
        )

        override_file = (
            data_root / "drop_1" / "events" / "events_0001.jsonl"
        )

        write_events(override_file, [override])

        first_result = ingest_event_file(
            connection,
            override_file,
            data_root,
            security,
            dispositions,
        )

        assert first_result["malformed_events"] == 0

        # The override initially has no phone fingerprint.
        stored_override = connection.execute(
            "SELECT phone_fingerprint FROM events WHERE event_id = ?",
            ("evt_override",),
        ).fetchone()

        assert stored_override["phone_fingerprint"] is None

        # The original call event arrives in a later drop.
        call_event = make_event(
            event_id="evt_call",
            event_type="call.initiated",
        )

        call_file = (
            data_root / "drop_2" / "events" / "events_1001.jsonl"
        )

        write_events(call_file, [call_event])

        second_result = ingest_event_file(
            connection,
            call_file,
            data_root,
            security,
            dispositions,
        )

        assert second_result["malformed_events"] == 0

        stored_override = connection.execute(
            "SELECT phone_fingerprint FROM events WHERE event_id = ?",
            ("evt_override",),
        ).fetchone()

        expected_fingerprint = security.phone_fingerprint(
            "+919876543210"
        )

        assert stored_override["phone_fingerprint"] == expected_fingerprint

    finally:
        connection.close()


def test_unknown_disposition_is_counted(tmp_path):
    connection, security, dispositions, data_root = setup_event_test(
        tmp_path
    )

    try:
        event = make_event(
            event_id="evt_unknown",
            event_type="disposition.set",
            payload={"disposition_code": "unknown_code"},
        )

        file_path = data_root / "drop_1" / "events" / "events_0001.jsonl"

        write_events(file_path, [event])

        result = ingest_event_file(
            connection,
            file_path,
            data_root,
            security,
            dispositions,
        )

        assert result["unknown_disposition_events"] == 1
        assert result["malformed_events"] == 0

    finally:
        connection.close()
