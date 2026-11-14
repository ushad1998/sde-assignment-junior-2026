
from pathlib import Path

from solution.src.database import connect_database, initialize_database
from solution.src.security import PIISecurity
from solution.src.csv_ingestion import ingest_all_lead_files
from solution.src.event_ingestion import ingest_all_event_files


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
SCHEMA_DIR = PROJECT_ROOT / "assignment-a-data" / "schemas"
DISPOSITIONS_PATH = SCHEMA_DIR / "dispositions.csv"
DATABASE_PATH = PROJECT_ROOT / "solution" / "interaction_ledger.db"


def main():
    security = PIISecurity.from_environment()

    connection = connect_database(DATABASE_PATH)
    initialize_database(connection)

    try:
        # Step 1: Ingest lead CSV files.
        # Previously processed files will be skipped automatically.
        results = ingest_all_lead_files(
            connection=connection,
            data_root=DATA_DIR,
            schema_dir=SCHEMA_DIR,
            security=security,
        )

        print("\nCSV INGESTION RESULTS")
        print("-" * 40)

        for result in results:
            print(result)

        # Step 2: Ingest event JSONL files.
        event_results = ingest_all_event_files(
            connection=connection,
            data_root=DATA_DIR,
            dispositions_path=DISPOSITIONS_PATH,
            security=security,
        )

        print("\nEVENT INGESTION RESULTS")
        print("-" * 40)

        for result in event_results:
            print(result)

        # Step 3: Display database counts.
        lead_count = connection.execute(
            "SELECT COUNT(*) FROM leads"
        ).fetchone()[0]

        rejection_count = connection.execute(
            "SELECT COUNT(*) FROM rejections"
        ).fetchone()[0]

        event_count = connection.execute(
            "SELECT COUNT(*) FROM events"
        ).fetchone()[0]

        print("\nDATABASE SUMMARY")
        print("-" * 40)
        print(f"Total leads: {lead_count}")
        print(f"Total rejected rows: {rejection_count}")
        print(f"Total events: {event_count}")

        # Step 4: Verify PII storage.
        print("\nPII STORAGE CHECK")
        print("-" * 40)

        sample = connection.execute("""
            SELECT
                customer_name_encrypted,
                phone_encrypted,
                phone_fingerprint
            FROM leads
            LIMIT 1
        """).fetchone()

        if sample is None:
            print("No lead records found.")
        else:
            print(
                "Encrypted customer name:",
                sample["customer_name_encrypted"][:25] + "..."
            )
            print(
                "Encrypted phone:",
                sample["phone_encrypted"][:25] + "..."
            )
            print(
                "Phone fingerprint:",
                sample["phone_fingerprint"][:25] + "..."
            )

            print("\nPII fields are stored as encrypted values.")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
