
import argparse
from pathlib import Path

from solution.src.database import connect_database
from solution.src.security import PIISecurity
from solution.src.schema_loader import load_workflow_schemas
from solution.src.event_ingestion import load_dispositions
from solution.src.reporting import generate_reports


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_DIR = PROJECT_ROOT / "assignment-a-data" / "schemas"
DISPOSITIONS_PATH = SCHEMA_DIR / "dispositions.csv"
DATABASE_PATH = PROJECT_ROOT / "solution" / "interaction_ledger.db"


def main():

    parser = argparse.ArgumentParser(
        description="Generate Assignment A reports."
    )

    parser.add_argument(
        "--out",
        required=True,
        help="Directory where the five reports will be saved.",
    )

    args = parser.parse_args()

    output_dir = Path(args.out)

    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    security = PIISecurity.from_environment()

    schemas = load_workflow_schemas(SCHEMA_DIR)

    dispositions = load_dispositions(DISPOSITIONS_PATH)

    connection = connect_database(DATABASE_PATH)

    try:

        results = generate_reports(
            connection=connection,
            output_dir=output_dir,
            security=security,
            dispositions=dispositions,
            schemas=schemas,
        )

        print("\nREPORT GENERATION SUCCESSFUL")
        print("-" * 40)

        for name, value in results.items():
            print(f"{name}: {value}")

        print("\nGenerated files:")

        for filename in (
            "batch_summary.csv",
            "daily_overview.csv",
            "lead_report.csv",
            "rejections.csv",
            "data_quality.json",
        ):
            print(f"- {output_dir / filename}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
