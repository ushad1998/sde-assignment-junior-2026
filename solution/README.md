# Assignment A — Interaction Ledger & Reporting Pipeline

## Overview

This solution implements a Python-based interaction ledger and reporting pipeline using SQLite.

It ingests lead CSV files and call-event JSONL files, validates and normalizes input data, protects personally identifiable information (PII), handles duplicate records, and generates the required reports.

## Project Structure

- `run_ingestion.py` — runs lead and event ingestion.
- `run_report.py` — generates the five required reports.
- `src/` — contains database, normalization, schema loading, ingestion, security, and reporting modules.
- `tests/` — automated tests for the implementation.

## Requirements

- Python 3.11 or later
- Dependencies listed in the root `requirements.txt`
- Dataset and workflow schemas provided with the assignment
- Environment variables configured using `.env`

## Screenshots

### Screenshot 1
<img src="../Screenshots/Screenshot%20(462).png" width="700">

### Screenshot 2
<img src="../Screenshots/Screenshot%20(463).png" width="700">

### Screenshot 3
<img src="../Screenshots/Screenshot%20(464).png" width="700">

### Screenshot 4
<img src="../Screenshots/Screenshot%20(465).png" width="700">

### Screenshot 5
<img src="../Screenshots/Screenshot%20(466).png" width="700">

### Screenshot 6
<img src="../Screenshots/Screenshot%20(467).png" width="700">

## Setup

Run these commands from the repository root.

```powershell
python -m venv .venv

.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
```

Configure the environment variables shown in the root `.env.example` file. Create a local `.env` file with fresh secrets before running ingestion.

Generate the assignment dataset using the provided data-generation instructions.

## Running the Pipeline

Run lead and event ingestion:

```powershell
python -m solution.run_ingestion
```

Generate all reports:

```powershell
python -m solution.run_report --out reports
```

Run the automated test suite:

```powershell
python -m pytest -v
```

## Database and Reports

The SQLite database is created at:

`solution/interaction_ledger.db`

The report command generates five outputs in the directory supplied through `--out`:

- `batch_summary.csv`
- `daily_overview.csv`
- `lead_report.csv`
- `rejections.csv`
- `data_quality.json`

## Security

- Customer names and phone numbers are encrypted before storage.
- Phone numbers are matched using keyed HMAC fingerprints.
- Phone numbers are masked in the lead report.
- Environment secrets and generated database files must not be committed to version control.

## Idempotency

Processed input files are tracked so that running ingestion again does not process the same files twice.

Duplicate lead records are merged, and duplicate event IDs are prevented from being inserted again.

## Testing

The automated test suite covers database operations, normalization, schema loading, lead ingestion, event ingestion, PII security, and report generation.
