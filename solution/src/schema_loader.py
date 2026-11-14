import json
from pathlib import Path

from solution.src.normalization import normalize_header


def load_workflow_schemas(schema_dir: str | Path) -> dict:
    """
    Load every workflow JSON schema from the given directory.

    Returns a dictionary:
    {
        "motor_renewal": {...},
        "policy_feedback": {...}
    }
    """
    schema_dir = Path(schema_dir)

    schemas = {}

    # Find every JSON schema in the directory.
    for schema_path in schema_dir.glob("*.json"):

        # Read the JSON file and convert it into a Python dictionary.
        with schema_path.open("r", encoding="utf-8") as file:
            schema = json.load(file)

        # Check that the schema has the required top-level information.
        if "workflow_id" not in schema or "fields" not in schema:
            raise ValueError(f"Invalid workflow schema: {schema_path.name}")

        workflow_id = schema["workflow_id"]

        # Store the schema using its workflow ID as the dictionary key.
        schemas[workflow_id] = schema

    return schemas


def build_header_mapping(schema: dict) -> dict:
    """
    Build a mapping from normalized CSV headers to schema field names.

    Example:
        "insured name" -> "customer_name"
        "mobile no"    -> "phone"
        "policy no"    -> "policy_number"
    """
    header_mapping = {}

    # Process every field defined in the workflow schema.
    for field in schema["fields"]:

        field_name = field["name"]

        # The actual schema field name is also a valid CSV header.
        possible_headers = [field_name]

        # Add all aliases defined in the schema.
        possible_headers.extend(field.get("aliases", []))

        for header in possible_headers:

            # Normalize the header before storing it.
            normalized = normalize_header(header)

            header_mapping[normalized] = field_name

    return header_mapping


def map_csv_headers(csv_headers: list[str], schema: dict) -> dict:
    """
    Match CSV column positions to canonical schema field names.

    Unknown columns are ignored.

    Returns:
        {
            "customer_name": 1,
            "phone": 2,
            "policy_number": 0
        }
    """
    known_headers = build_header_mapping(schema)

    column_mapping = {}

    # Enumerate gives us both the column position and its header.
    for index, csv_header in enumerate(csv_headers):

        normalized = normalize_header(csv_header)

        # Ignore columns that do not exist in the schema or its aliases.
        if normalized not in known_headers:
            continue

        field_name = known_headers[normalized]

        # Keep the first occurrence if a CSV contains duplicate aliases
        # for the same schema field.
        if field_name not in column_mapping:
            column_mapping[field_name] = index

    return column_mapping