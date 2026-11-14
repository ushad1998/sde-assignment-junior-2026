
import sqlite3
from pathlib import Path

def connect_database(database_path: str) -> sqlite3.Connection:
    """
    Open a SQLite database connection.

    If the database file does not exist, SQLite creates it.
    """
    # Create the parent directory if it does not exist.
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    # Open the database file.
    connection = sqlite3.connect(database_path)

    # Allow us to access query results using column names.
    connection.row_factory = sqlite3.Row

    # Enable foreign key enforcement in SQLite.
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    """
    Create the tables and indexes required by Assignment A.
    """

    # Table 1: Stores validated and normalized leads.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            workflow_id TEXT NOT NULL,

            -- HMAC fingerprint allows matching without plaintext phone storage.
            phone_fingerprint TEXT NOT NULL,

            -- Original customer name is stored encrypted.
            customer_name_encrypted TEXT,

            -- Original phone number is stored encrypted.
            phone_encrypted TEXT NOT NULL,

            -- policy_number or order_id, depending on the workflow.
            external_ref TEXT,

            -- The first batch in which this lead appeared.
            batch_id TEXT NOT NULL,

            -- Stores other non-PII fields as JSON.
            other_fields_json TEXT NOT NULL DEFAULT '{}',

            -- Prevents duplicate leads within the same workflow.
            UNIQUE (workflow_id, phone_fingerprint)
        )
    """)

    # Table 2: Stores interaction events.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Every event must have a globally unique event ID.
            event_id TEXT NOT NULL UNIQUE,

            event_type TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            call_id TEXT NOT NULL,

            -- Original timestamp is retained for later timezone processing.
            occurred_at TEXT NOT NULL,

            -- NULL is allowed for events such as disposition.override.
            phone_fingerprint TEXT,

            -- Event payload is stored as JSON.
            payload_json TEXT NOT NULL DEFAULT '{}'
        )
    """)

    # Table 3: Stores rejected CSV rows without storing their PII.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS rejections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            workflow_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            reason TEXT NOT NULL,

            -- Avoid recording the same rejection twice.
            UNIQUE (workflow_id, batch_id, row_number)
        )
    """)

        # Table 4: Remembers each input file that has been processed.
    # The file path is unique, so the same file cannot be ingested twice.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            source_file TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL
        )
    """)


    # Table 5: Stores ingestion metrics for data-quality reporting.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_metrics (
            source_file TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_key TEXT NOT NULL DEFAULT '',
            metric_value INTEGER NOT NULL DEFAULT 0,

            PRIMARY KEY (source_file, metric_name, metric_key)
        )
    """)


    # Indexes make common lookups faster.
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_leads_workflow_phone
        ON leads (workflow_id, phone_fingerprint)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_workflow_call
        ON events (workflow_id, call_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_phone
        ON events (workflow_id, phone_fingerprint)
    """)

    # Save the table and index definitions.
    connection.commit()
