
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from solution.src.normalization import normalize_phone
from solution.src.csv_ingestion import record_metric


IST = ZoneInfo("Asia/Kolkata")


VALID_EVENT_TYPES = {
    "call.initiated",
    "call.telephony_failed",
    "call.connected",
    "call.ended",
    "disposition.set",
    "disposition.override",
}


def load_dispositions(dispositions_path):
    """
    Load valid disposition codes for each workflow.

    Returns:
        {
            "motor_renewal": {
                "renewed": {
                    "label": "...",
                    "is_terminal": True,
                    "is_success": True
                }
            }
        }
    """

    import csv

    dispositions = {}

    with open(
        dispositions_path,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:
            workflow_id = row["workflow_id"].strip()
            code = row["code"].strip().lower()

            dispositions.setdefault(workflow_id, {})[code] = {
                "label": row["label"].strip(),
                "is_terminal": (
                    row["is_terminal"].strip().lower() == "true"
                ),
                "is_success": (
                    row["is_success"].strip().lower() == "true"
                ),
            }

    return dispositions


def normalize_event_timestamp(value):
    """
    Convert event timestamps to UTC ISO-8601.

    Supported:
    - UTC timestamps ending in Z
    - Offset-aware timestamps
    - Naive timestamps, interpreted as IST
    """

    value = value.strip()

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    timestamp = datetime.fromisoformat(value)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=IST)

    return timestamp.astimezone(timezone.utc).isoformat()


def count_orphan_events(connection):
    """
    Count events that cannot currently be linked to a valid lead.

    An event is orphaned when:
    - Its phone fingerprint is NULL, or
    - No lead exists with the same workflow and fingerprint.

    This is calculated from the current database state, not
    accumulated as a permanent ingestion metric.
    """

    result = connection.execute(
        """
        SELECT COUNT(*)
        FROM events AS e
        WHERE e.phone_fingerprint IS NULL
           OR NOT EXISTS (
                SELECT 1
                FROM leads AS l
                WHERE l.workflow_id = e.workflow_id
                  AND l.phone_fingerprint = e.phone_fingerprint
           )
        """
    ).fetchone()

    return result[0]


def link_override_events(connection):
    """
    Link disposition.override events through their call_id.

    Overrides do not contain phone numbers. Their fingerprint
    is obtained from another event belonging to the same call.

    The original event is never modified or deleted except
    for filling its previously NULL phone fingerprint.
    """

    connection.execute(
        """
        UPDATE events
        SET phone_fingerprint = (
            SELECT source.phone_fingerprint
            FROM events AS source
            WHERE source.workflow_id = events.workflow_id
              AND source.call_id = events.call_id
              AND source.phone_fingerprint IS NOT NULL
              AND source.event_type != 'disposition.override'
            ORDER BY source.occurred_at
            LIMIT 1
        )
        WHERE event_type = 'disposition.override'
          AND phone_fingerprint IS NULL
          AND EXISTS (
              SELECT 1
              FROM events AS source
              WHERE source.workflow_id = events.workflow_id
                AND source.call_id = events.call_id
                AND source.phone_fingerprint IS NOT NULL
                AND source.event_type != 'disposition.override'
          )
        """
    )


def ingest_event_file(
    connection,
    file_path,
    data_root,
    security,
    dispositions,
):
    """
    Ingest one JSONL file idempotently.

    Processing order:
    1. Malformed event validation
    2. Duplicate event ID detection
    3. Event insertion
    4. Override linking

    Unknown disposition events are retained in the append-only
    ledger and counted. Reporting must ignore their codes when
    calculating effective dispositions.
    """

    file_path = Path(file_path)
    data_root = Path(data_root)

    source_file = (
        file_path.resolve()
        .relative_to(data_root.resolve())
        .as_posix()
    )

    # Check whether the file was already processed.
    already_processed = connection.execute(
        """
        SELECT 1
        FROM processed_files
        WHERE source_file = ?
        """,
        (source_file,),
    ).fetchone()

    if already_processed:
        return {
            "source_file": source_file,
            "status": "already_processed",
            "events_total": 0,
            "malformed_events": 0,
            "duplicate_events_dropped": 0,
            "unknown_disposition_events": 0,
        }

    result = {
        "source_file": source_file,
        "status": "processed",
        "events_total": 0,
        "malformed_events": 0,
        "duplicate_events_dropped": 0,
        "unknown_disposition_events": 0,
    }

    with connection:

        with file_path.open(
            "r",
            encoding="utf-8-sig",
        ) as file:

            for line in file:

                # Ignore empty lines.
                if not line.strip():
                    continue

                # Every non-empty line counts, even if malformed
                # or a duplicate.
                result["events_total"] += 1

                try:
                    event = json.loads(line)

                    if not isinstance(event, dict):
                        raise ValueError(
                            "Event must be a JSON object"
                        )

                    event_id = event.get("event_id")
                    event_type = event.get("event_type")
                    workflow_id = event.get("workflow_id")
                    call_id = event.get("call_id")
                    occurred_at = event.get("occurred_at")
                    payload = event.get("payload", {})

                    # Validate required fields.
                    required_values = (
                        event_id,
                        event_type,
                        workflow_id,
                        call_id,
                        occurred_at,
                    )

                    if not all(
                        isinstance(value, str) and value.strip()
                        for value in required_values
                    ):
                        raise ValueError(
                            "Missing required event fields"
                        )

                    if event_type not in VALID_EVENT_TYPES:
                        raise ValueError(
                            "Unknown event type"
                        )

                    if workflow_id not in dispositions:
                        raise ValueError(
                            "Unknown workflow"
                        )

                    if not isinstance(payload, dict):
                        raise ValueError(
                            "Payload must be a JSON object"
                        )

                    # Normalize timestamp.
                    normalized_timestamp = (
                        normalize_event_timestamp(occurred_at)
                    )

                    # Normalize phone and create HMAC fingerprint.
                    phone = event.get("phone")
                    phone_fingerprint = None

                    if phone is not None:
                        canonical_phone = normalize_phone(
                            str(phone)
                        )

                        if not canonical_phone:
                            raise ValueError(
                                "Invalid phone number"
                            )

                        phone_fingerprint = (
                            security.phone_fingerprint(
                                canonical_phone
                            )
                        )

                    elif event_type != "disposition.override":
                        raise ValueError(
                            "Missing phone number"
                        )

                    # Validate disposition payload.
                    disposition_code = None

                    if event_type in {
                        "disposition.set",
                        "disposition.override",
                    }:

                        disposition_code = payload.get(
                            "disposition_code"
                        )

                        if (
                            not isinstance(disposition_code, str)
                            or not disposition_code.strip()
                        ):
                            raise ValueError(
                                "Missing disposition code"
                            )

                        disposition_code = (
                            disposition_code.strip().lower()
                        )

                    # Check duplicate IDs before counting unknown
                    # disposition events.
                    existing = connection.execute(
                        """
                        SELECT 1
                        FROM events
                        WHERE event_id = ?
                        """,
                        (event_id,),
                    ).fetchone()

                    if existing:
                        result["duplicate_events_dropped"] += 1
                        continue

                    # Count unknown disposition codes.
                    # Keep their events in the append-only ledger;
                    # the reporting layer must ignore these codes.
                    if (
                        event_type in {
                            "disposition.set",
                            "disposition.override",
                        }
                        and disposition_code
                        not in dispositions[workflow_id]
                    ):
                        result[
                            "unknown_disposition_events"
                        ] += 1

                    # Store payload only. Never store raw phone data.
                    payload_json = json.dumps(
                        payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )

                    connection.execute(
                        """
                        INSERT INTO events (
                            event_id,
                            event_type,
                            workflow_id,
                            call_id,
                            occurred_at,
                            phone_fingerprint,
                            payload_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            event_type,
                            workflow_id,
                            call_id,
                            normalized_timestamp,
                            phone_fingerprint,
                            payload_json,
                        ),
                    )

                except (
                    json.JSONDecodeError,
                    ValueError,
                    TypeError,
                    KeyError,
                ):
                    result["malformed_events"] += 1

        # Link overrides after inserting all events in this file.
        link_override_events(connection)

        # Save ingestion metrics.
        for metric_name in (
            "events_total",
            "malformed_events",
            "duplicate_events_dropped",
            "unknown_disposition_events",
        ):
            record_metric(
                connection,
                source_file,
                metric_name,
                amount=result[metric_name],
            )

        # Mark file processed only after successful ingestion.
        connection.execute(
            """
            INSERT INTO processed_files (
                source_file,
                processed_at
            )
            VALUES (?, ?)
            """,
            (
                source_file,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    return result


def ingest_all_event_files(
    connection,
    data_root,
    dispositions_path,
    security,
):
    """
    Discover and ingest every event JSONL file across all drops.
    """

    data_root = Path(data_root)

    dispositions = load_dispositions(dispositions_path)

    event_files = sorted(
        data_root.glob("drop_*/events/*.jsonl")
    )

    results = []

    for file_path in event_files:

        result = ingest_event_file(
            connection=connection,
            file_path=file_path,
            data_root=data_root,
            security=security,
            dispositions=dispositions,
        )

        results.append(result)

    # Resolve overrides again after all files have been processed.
    with connection:
        link_override_events(connection)

    return results
