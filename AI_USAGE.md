# AI Usage Disclosure

## Tools used

- ChatGPT

## What I used them for

I used ChatGPT throughout the assignment as a coding assistant and learning resource.

 ## Examples of assistance included:

- Breaking down the assignment requirements into implementation steps.
- Explaining Python, SQLite, CSV and JSONL processing, and database design.
- Helping develop the lead ingestion, event ingestion, PII security, and reporting components.
- Explaining HMAC fingerprints and Fernet encryption.
- Suggesting unit tests and edge cases for the implementation.
- Helping debug errors and interpret PowerShell and pytest output.
- Reviewing report logic, including call counting, disposition overrides, IST date handling, and bucket classification.
- Preparing setup instructions and submission documentation.

Some implementation code and test code were drafted with AI assistance and then integrated, run, and checked during development. I am not claiming that every line was independently written without AI assistance.

## What I wrote or decided myself

I made the implementation decisions while working through the assignment requirements, including:

- Choosing Assignment A.
- Using SQLite for the database.
- Following the supplied workflow schemas and input data.
- Deciding to work through the implementation in separate ingestion, security, database, and reporting components.
- Running the commands, reviewing outputs, and investigating failures.
- Checking ingestion counts, report totals, duplicate handling, and encryption behaviour.
- Deciding which remaining limitations to disclose.

I also worked through the code and tests step by step so I could understand the implementation rather than treating generated code as a black box.

## Where the AI was wrong or unhelpful

AI-generated suggestions were not always correct or complete.

For example, during reporting development, an initial batch-summary implementation did not explicitly include every bucket when its count was zero. I checked the output against the required report columns, identified the missing-zero-count issue, and corrected the implementation.

I also verified the encryption function directly with an encryption/decryption round-trip instead of relying only on the appearance of a source-code listing or on the test count.

## How I verified AI-generated code

- Ran the automated test suite; the latest run completed with **50 passing tests**.
- Ran Python compilation checks on the reporting and report-runner modules.
- Executed the ingestion pipeline against the supplied small dataset.
- Ran ingestion again and checked that previously processed files were skipped.
- Tested encryption and decryption using a round-trip check.
- Inspected generated reports and checked their row counts.
- Compared the daily report's call total against linked `call.initiated` events in SQLite.
- Checked that connectivity rates use four decimal places.
- Reviewed the implementation and its output while working through the assignment.

I understand that passing tests does not guarantee that the implementation is free of defects. I have listed the areas I did not test in `SUBMISSION.md`.