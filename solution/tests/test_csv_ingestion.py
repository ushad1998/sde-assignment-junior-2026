
import sqlite3

from cryptography.fernet import Fernet

from solution.src.database import initialize_database
from solution.src.security import PIISecurity
from solution.src.schema_loader import load_workflow_schemas
from solution.src.csv_ingestion import (
    ingest_lead_csv,
    ingest_all_lead_files,
)


def setup_ingestion():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row

    initialize_database(connection)

    security = PIISecurity(
        Fernet.generate_key().decode("utf-8"),
        "a" * 64,
    )

    schemas = load_workflow_schemas("assignment-a-data/schemas")

    return connection, security, schemas


def test_ingest_one_csv_file(tmp_path):
    connection, security, schemas = setup_ingestion()

    data_root = tmp_path / "data"
    csv_path = (
        data_root
        / "drop_1"
        / "leads"
        / "motor_renewal"
        / "batch_001.csv"
    )

    csv_path.parent.mkdir(parents=True)

    csv_path.write_text(
        "Name,Mobile No,Policy No,Language\n"
        "Rahul,9876543210,POL123,kn\n"
        "Priya,9876543211,POL124,en\n",
        encoding="utf-8",
    )

    result = ingest_lead_csv(
        connection,
        csv_path,
        "motor_renewal",
        schemas["motor_renewal"],
        security,
        data_root,
    )

    assert result["status"] == "processed"
    assert result["total_rows"] == 2
    assert result["rejected_rows"] == 0

    count = connection.execute(
        "SELECT COUNT(*) FROM leads"
    ).fetchone()[0]

    assert count == 2

    connection.close()


def test_same_csv_file_is_not_ingested_twice(tmp_path):
    connection, security, schemas = setup_ingestion()

    data_root = tmp_path / "data"
    csv_path = (
        data_root
        / "drop_1"
        / "leads"
        / "motor_renewal"
        / "batch_001.csv"
    )

    csv_path.parent.mkdir(parents=True)

    csv_path.write_text(
        "Name,Mobile No,Policy No\n"
        "Rahul,9876543210,POL123\n",
        encoding="utf-8",
    )

    first_result = ingest_lead_csv(
        connection,
        csv_path,
        "motor_renewal",
        schemas["motor_renewal"],
        security,
        data_root,
    )

    second_result = ingest_lead_csv(
        connection,
        csv_path,
        "motor_renewal",
        schemas["motor_renewal"],
        security,
        data_root,
    )

    assert first_result["status"] == "processed"
    assert second_result["status"] == "already_processed"

    count = connection.execute(
        "SELECT COUNT(*) FROM leads"
    ).fetchone()[0]

    assert count == 1

    connection.close()


def test_ingest_all_drop_files(tmp_path):
    connection, security, schemas = setup_ingestion()

    data_root = tmp_path / "data"

    csv_path = (
        data_root
        / "drop_1"
        / "leads"
        / "motor_renewal"
        / "batch_001.csv"
    )

    csv_path.parent.mkdir(parents=True)

    csv_path.write_text(
        "Name,Mobile No,Policy No\n"
        "Rahul,9876543210,POL123\n",
        encoding="utf-8",
    )

    results = ingest_all_lead_files(
        connection,
        data_root,
        "assignment-a-data/schemas",
        security,
    )

    assert len(results) == 1
    assert results[0]["status"] == "processed"

    connection.close()


def test_rejected_rows_are_recorded_without_pii(tmp_path):
    connection, security, schemas = setup_ingestion()

    data_root = tmp_path / "data"
    csv_path = (
        data_root
        / "drop_1"
        / "leads"
        / "motor_renewal"
        / "batch_001.csv"
    )

    csv_path.parent.mkdir(parents=True)

    csv_path.write_text(
        "Name,Mobile No,Policy No\n"
        "Rahul,12345,POL123\n",
        encoding="utf-8",
    )

    result = ingest_lead_csv(
        connection,
        csv_path,
        "motor_renewal",
        schemas["motor_renewal"],
        security,
        data_root,
    )

    assert result["rejected_rows"] == 1

    rejection = connection.execute(
        "SELECT * FROM rejections"
    ).fetchone()

    assert rejection["reason"] == "invalid_phone"
    assert "Rahul" not in str(dict(rejection))
    assert "12345" not in str(dict(rejection))

    connection.close()
