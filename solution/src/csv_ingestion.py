
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from solution.src.schema_loader import load_workflow_schemas
from solution.src.lead_ingestion import (
    validate_lead_row,
    read_csv_rows,
)
from solution.src.security import PIISecurity
from solution.src.lead_repository import insert_or_merge_lead


def record_metric(
    connection: sqlite3.Connection,
    source_file: str,
    metric_name: str,
    metric_key: str = "",
    amount: int = 1,
) -> None:
    """Insert or increment a metric for one source file."""

    connection.execute(
        """
        INSERT INTO ingestion_metrics (
            source_file,
            metric_name,
            metric_key,
            metric_value
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(source_file, metric_name, metric_key)
        DO UPDATE SET metric_value =
            metric_value + excluded.metric_value
        """,
        (source_file, metric_name, metric_key, amount),
    )


def ingest_lead_csv(
    connection: sqlite3.Connection,
    file_path: str | Path,
    workflow_id: str,
    schema: dict,
    security: PIISecurity,
    source_root: str | Path,
) -> dict:
    """
    Ingest one CSV file into the lead database.

    The lead changes, rejections, metrics, and processed-file
    marker are committed together in one transaction.
    """

    file_path = Path(file_path)
    source_root = Path(source_root)

    # Use a stable relative path to identify the input file.
    source_file = file_path.resolve().relative_to(
        source_root.resolve()
    ).as_posix()

    # Derive the batch ID from the CSV filename.
    batch_id = file_path.stem

    # Check whether this file was already processed.
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
            "total_rows": 0,
            "rejected_rows": 0,
            "duplicates_merged": 0,
            "field_warnings": 0,
        }

    result = {
        "source_file": source_file,
        "status": "processed",
        "total_rows": 0,
        "rejected_rows": 0,
        "duplicates_merged": 0,
        "field_warnings": 0,
    }

    try:
        # Process the entire file inside one transaction.
        with connection:

            for row_number, raw_row in read_csv_rows(
                file_path,
                schema,
            ):
                result["total_rows"] += 1

                # Validate and normalize the current row.
                normalized_row, rejection_reason, warnings = (
                    validate_lead_row(raw_row, schema)
                )

                if rejection_reason is not None:
                    connection.execute(
                        """
                        INSERT INTO rejections (
                            workflow_id,
                            batch_id,
                            row_number,
                            reason
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            workflow_id,
                            batch_id,
                            row_number,
                            rejection_reason,
                        ),
                    )

                    result["rejected_rows"] += 1

                    record_metric(
                        connection,
                        source_file,
                        "lead_rows_rejected",
                    )

                    record_metric(
                        connection,
                        source_file,
                        "rejection_reason",
                        rejection_reason,
                    )

                    continue

                # Count optional-field warnings.
                for warning in warnings:
                    result["field_warnings"] += 1

                    record_metric(
                        connection,
                        source_file,
                        "field_warning",
                        warning,
                    )

                # Insert a new lead or merge an existing lead.
                was_duplicate = insert_or_merge_lead(
                    connection,
                    workflow_id,
                    batch_id,
                    normalized_row,
                    schema,
                    security,
                )

                if was_duplicate:
                    result["duplicates_merged"] += 1

                    record_metric(
                        connection,
                        source_file,
                        "duplicate_lead_rows_merged",
                    )

                # Count valid rows.
                record_metric(
                    connection,
                    source_file,
                    "lead_rows_accepted",
                )

            # Record total nonblank input rows.
            record_metric(
                connection,
                source_file,
                "lead_rows_total",
                amount=result["total_rows"],
            )

            # Mark the file as processed only after all rows succeed.
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

    except Exception:
        # The transaction rolls back if any operation fails.
        raise

    return result


def ingest_all_lead_files(
    connection: sqlite3.Connection,
    data_root: str | Path,
    schema_dir: str | Path,
    security: PIISecurity,
) -> list[dict]:
    """
    Discover and ingest all lead CSV files from every drop.
    """

    data_root = Path(data_root)
    schemas = load_workflow_schemas(schema_dir)

    results = []

    # Search every drop for CSV files under leads/workflow folders.
    csv_files = sorted(
        data_root.glob("drop_*/leads/*/*.csv")
    )

    for file_path in csv_files:

        # Workflow ID is the directory directly under leads.
        workflow_id = file_path.parent.name

        if workflow_id not in schemas:
            raise ValueError(
                f"No schema found for workflow: {workflow_id}"
            )

        result = ingest_lead_csv(
            connection=connection,
            file_path=file_path,
            workflow_id=workflow_id,
            schema=schemas[workflow_id],
            security=security,
            source_root=data_root,
        )

        results.append(result)

    return results
