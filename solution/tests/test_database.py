
import sqlite3

from solution.src.database import (
    connect_database,
    initialize_database,
)


def test_database_tables_are_created(tmp_path):
    # pytest provides a temporary directory for this test.
    database_path = tmp_path / "test.db"

    connection = connect_database(str(database_path))
    initialize_database(connection)

    # Read all table names from SQLite's internal schema.
    tables = connection.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
    """).fetchall()

    table_names = {row["name"] for row in tables}

    assert "leads" in table_names
    assert "events" in table_names
    assert "rejections" in table_names

    connection.close()


def test_duplicate_lead_is_rejected(tmp_path):
    connection = connect_database(str(tmp_path / "test.db"))
    initialize_database(connection)

    # Insert the first lead.
    connection.execute("""
        INSERT INTO leads (
            workflow_id,
            phone_fingerprint,
            phone_encrypted,
            batch_id
        )
        VALUES (?, ?, ?, ?)
    """, ("motor_renewal", "hash123", "encrypted_phone", "batch_001"))

    connection.commit()

    # A second lead with the same workflow and fingerprint must fail.
    try:
        connection.execute("""
            INSERT INTO leads (
                workflow_id,
                phone_fingerprint,
                phone_encrypted,
                batch_id
            )
            VALUES (?, ?, ?, ?)
        """, ("motor_renewal", "hash123", "another_encrypted_phone", "batch_002"))

        assert False, "Duplicate lead should not be inserted"

    except sqlite3.IntegrityError:
        pass

    connection.close()


def test_duplicate_event_id_is_rejected(tmp_path):
    connection = connect_database(str(tmp_path / "test.db"))
    initialize_database(connection)

    # Insert an event.
    connection.execute("""
        INSERT INTO events (
            event_id,
            event_type,
            workflow_id,
            call_id,
            occurred_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        "evt_001",
        "call.initiated",
        "motor_renewal",
        "call_001",
        "2026-10-01T10:00:00Z",
    ))

    connection.commit()



    # The same event ID cannot be inserted twice.
    try:
        connection.execute("""
            INSERT INTO events (
                event_id,
                event_type,
                workflow_id,
                call_id,
                occurred_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            "evt_001",
            "call.connected",
            "motor_renewal",
            "call_001",
            "2026-10-01T10:01:00Z",
        ))

        assert False, "Duplicate event ID should not be inserted"

    except sqlite3.IntegrityError:
        pass

    connection.close()

def test_processed_files_table_is_created(tmp_path):
    database_path = tmp_path / "test.db"

    connection = connect_database(str(database_path))
    initialize_database(connection)

    result = connection.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'processed_files'
    """).fetchone()

    assert result is not None

    connection.close()
