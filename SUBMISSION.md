# Submission

## Candidate
- **Name:** Usha D
- **Assignment chosen:** A — Interaction Ledger & Reporting Pipeline
- **Time spent (honest estimate):** Approximately 8-10 hours

## How to run

The following commands assume a clean clone, Python 3.11 or newer, and Windows PowerShell. Run them from the repository root.

```powershell
# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
python -m pip install -r requirements.txt

# Generate fresh local PII keys and write them to .env
python -c "import secrets; from pathlib import Path; from cryptography.fernet import Fernet; Path('.env').write_text('PII_ENCRYPTION_KEY='+Fernet.generate_key().decode()+'\nPII_HMAC_KEY='+secrets.token_hex(32)+'\n', encoding='utf-8')"

# Generate the sample dataset
python assignment-a-data/tools/generate_data.py --seed 42 --scale small --out data

# Ingest leads and events into SQLite
python -m solution.run_ingestion

# Generate the five reports
python -m solution.run_report --out reports

# Run the automated test suite
python -m pytest -v
```

The ingestion command processes the available drop directories in sorted order. The report command expects ingestion to have completed and the SQLite database to exist.

Do not commit `.env`, generated data, the SQLite database, or generated reports.

## Design

The solution is implemented in Python and uses SQLite for persistent storage.

The main components are:

- **Normalization and schema loading:** Read workflow schemas, map incoming CSV headers, and normalize values such as phone numbers and timestamps.
- **Lead ingestion:** Validate CSV rows, reject invalid records with a reason, and merge duplicate leads.
- **Lead repository:** Identify a lead using a workflow-specific HMAC fingerprint of the normalized phone number. Store customer names and phone numbers encrypted with Fernet rather than storing them in plaintext.
- **Event ingestion:** Read JSONL event files, reject malformed events, discard duplicate event IDs, and retain valid events for later lead linking.
- **Reporting:** Join linked events to leads and generate batch, daily, lead-level, rejection, and data-quality reports.

The database contains these main tables:

- `leads`: One record per unique workflow and phone fingerprint.
- `events`: Append-only event records with a unique event ID.
- `rejections`: Rejected lead rows and their validation reasons.
- `processed_files`: Tracks processed input files for re-run protection.
- `ingestion_metrics`: Stores ingestion counters used by the data-quality report.

The unique constraint on `(workflow_id, phone_fingerprint)` prevents duplicate lead records within a workflow. The unique event ID prevents duplicate event insertion. Fernet encryption protects stored PII, while HMAC fingerprints allow matching without querying plaintext phone numbers.

## Decisions & assumptions

| Decision | Why | Alternative considered |
|---|---|---|
| Use SQLite | It is sufficient for this assignment and avoids requiring a separate database server | PostgreSQL |
| Use HMAC fingerprints for phone matching | Allows deterministic matching without storing plaintext phone numbers as lookup keys | Hashing without a secret |
| Encrypt customer names and phone numbers with Fernet | Protects PII at rest while allowing authorized report generation | Plaintext storage |
| Treat naive source timestamps as IST | The assignment specifies IST for naive timestamps | Treating them as UTC |
| Store normalized event timestamps in UTC and convert to IST for reporting | Gives consistent timestamp comparisons and IST reporting dates | Store all timestamps directly in IST |
| Keep events append-only and apply valid overrides during reporting | Preserves the original event history | Updating earlier disposition events |
| Count a call only when a linked `call.initiated` event exists | Prevents incomplete event sequences from being treated as calls | Count any event with a call ID |
| Ignore unknown disposition codes when determining effective disposition | Unknown codes should not override valid known dispositions | Treat unknown codes as terminal or valid outcomes |
| Resolve duplicate lead rows by merging non-empty fields | Preserves useful data from repeated rows | Reject every duplicate row |

## Failure modes considered

- **Invalid lead rows:** Validation failures are recorded in `rejections` with a reason, without including PII in the rejection report.
- **Duplicate leads:** Rows are merged using workflow ID and HMAC phone fingerprint.
- **Malformed event lines:** Invalid JSON or events missing an event ID are counted and skipped.
- **Duplicate events:** Duplicate event IDs are dropped.
- **Events arriving before their leads:** Events can be stored before their corresponding lead is available. Reports only include events that can be linked to a valid lead at report time.
- **Unknown dispositions:** Unknown disposition codes are counted and excluded from effective disposition selection.
- **Repeated ingestion:** Processed-file tracking prevents a successfully processed file from being ingested again.
- **Sensitive data:** Customer names and phone numbers are encrypted in the database. Phone fingerprints are HMAC-based.

Known limitations:

- The implementation was tested against the supplied small dataset, not the large dataset.
- PostgreSQL compatibility and concurrent ingestion were not tested.
- Crash recovery during a partially completed ingestion was not comprehensively fault-injected.
- Performance under substantially larger datasets has not been benchmarked.
- The implementation has not been independently validated against multiple newly generated seeds.

## Testing

The automated test suite currently reports **50 passing tests**.

Testing and manual verification included:

- Unit tests for normalization, schema loading, database operations, lead ingestion, event ingestion, security, and reporting.
- Encryption and decryption round-trip verification.
- Repeated ingestion checks to verify already-processed files are not inserted again.
- Manual inspection of generated CSV and JSON reports.
- Cross-checking the number of reported calls against linked `call.initiated` events in SQLite.
- Checking that connectivity rates are formatted to four decimal places.
- Checking that batch bucket counts add up to the total leads.

The tests do not establish production readiness or prove correctness for every possible input.

## Results

For the supplied small dataset:

- Lead rows processed: **2,057**
- Rejected lead rows: **108**
- Duplicate lead rows merged: **57**
- Unique leads stored: **1,892**
- Optional-field warnings: **122**
- Event lines processed: **8,745**
- Malformed events: **163**
- Duplicate events dropped: **234**
- Stored events: **8,348**
- Final orphan events: **310**
- Linked unknown disposition events: **18**
- Generated report rows:
  - `batch_summary.csv`: 6
  - `daily_overview.csv`: 33
  - `lead_report.csv`: 1,892
  - `rejections.csv`: 108
  - `data_quality.json`: generated

The daily report contains 2,536 calls, matching the count of linked `call.initiated` events.

## If I had another day

1. Run the complete pipeline against a different generated seed and compare the results.
2. Test the large dataset and profile ingestion and reporting performance.
3. Add more integration tests for event ordering, partial failures, and crash recovery.
4. Review database indexes and query performance with larger data volumes.
5. Improve command-line configuration and logging for easier operational use.