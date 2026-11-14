
import csv
import json
import sqlite3

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from solution.src.event_ingestion import count_orphan_events


IST = ZoneInfo("Asia/Kolkata")


def to_ist(value):
    """Convert a stored UTC timestamp to an IST datetime."""

    timestamp = datetime.fromisoformat(value)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo("UTC"))

    return timestamp.astimezone(IST)


def sum_metric(connection, metric_name):
    """Sum one ingestion metric across all processed files."""

    result = connection.execute(
        """
        SELECT COALESCE(SUM(metric_value), 0)
        FROM ingestion_metrics
        WHERE metric_name = ?
        """,
        (metric_name,),
    ).fetchone()

    return int(result[0])


def write_csv(output_path, fieldnames, rows):
    """Write a CSV file with a header and no index column."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(rows)


def get_effective_disposition(events, workflow_id, dispositions):
    """
    Determine the effective disposition for one call.

    Rule:
    1. Use the latest valid override if one exists.
    2. Otherwise use the latest valid disposition.set.
    3. Ignore unknown disposition codes.
    """

    valid_codes = dispositions.get(workflow_id, {})

    overrides = []
    disposition_sets = []

    for event in events:

        if event["event_type"] not in {
            "disposition.set",
            "disposition.override",
        }:
            continue

        payload = json.loads(event["payload_json"])
        code = payload.get("disposition_code")

        if not isinstance(code, str):
            continue

        code = code.strip().lower()

        # Unknown codes must not affect reports.
        if code not in valid_codes:
            continue

        if event["event_type"] == "disposition.override":
            overrides.append((event["occurred_at"], code))

        else:
            disposition_sets.append((event["occurred_at"], code))

    if overrides:
        return max(overrides, key=lambda item: item[0])[1]

    if disposition_sets:
        return max(
            disposition_sets,
            key=lambda item: item[0],
        )[1]

    return None


def get_linked_events(connection):
    """
    Retrieve only events linked to valid leads.

    Orphan events must not appear in any report.
    """

    rows = connection.execute(
        """
        SELECT
            e.event_id,
            e.event_type,
            e.workflow_id,
            e.call_id,
            e.occurred_at,
            e.phone_fingerprint,
            e.payload_json
        FROM events AS e
        INNER JOIN leads AS l
            ON l.workflow_id = e.workflow_id
           AND l.phone_fingerprint = e.phone_fingerprint
        ORDER BY e.workflow_id, e.call_id, e.occurred_at
        """
    ).fetchall()

    return [dict(row) for row in rows]


def get_call_data(connection, security, dispositions):
    """
    Build call-level information for every lead.

    Only calls with a linked call.initiated event are counted.
    """

    leads = connection.execute(
        """
        SELECT
            id,
            workflow_id,
            phone_fingerprint,
            phone_encrypted,
            external_ref,
            batch_id
        FROM leads
        ORDER BY workflow_id, external_ref
        """
    ).fetchall()

    linked_events = get_linked_events(connection)

    # Group events by workflow, phone fingerprint, and call ID.
    events_by_call = defaultdict(list)

    for event in linked_events:

        key = (
            event["workflow_id"],
            event["phone_fingerprint"],
            event["call_id"],
        )

        events_by_call[key].append(event)

    calls_by_lead = defaultdict(list)

    for lead in leads:

        lead_key = (
            lead["workflow_id"],
            lead["phone_fingerprint"],
        )

        for (workflow_id, fingerprint, call_id), events in (
            events_by_call.items()
        ):

            if (
                workflow_id != lead["workflow_id"]
                or fingerprint != lead["phone_fingerprint"]
            ):
                continue

            initiated_events = [
                event
                for event in events
                if event["event_type"] == "call.initiated"
            ]

            # A call exists only when call.initiated is present.
            if not initiated_events:
                continue

            initiated_at = min(
                event["occurred_at"]
                for event in initiated_events
            )

            connected = any(
                event["event_type"] == "call.connected"
                for event in events
            )

            telephony_failed = any(
                event["event_type"] == "call.telephony_failed"
                for event in events
            )

            disposition = get_effective_disposition(
                events,
                workflow_id,
                dispositions,
            )

            calls_by_lead[lead_key].append({
                "call_id": call_id,
                "initiated_at": initiated_at,
                "connected": connected,
                "telephony_failed": telephony_failed,
                "disposition": disposition,
            })

    return leads, calls_by_lead


def get_bucket(calls, workflow_id, dispositions):
    """Determine a lead's bucket using the assignment priority."""

    if not calls:
        return "yet_to_reach_out"

    for call in calls:

        code = call["disposition"]

        if code is not None:
            disposition_info = dispositions[workflow_id][code]

            if disposition_info["is_terminal"]:
                return "completed"

    if all(call["telephony_failed"] for call in calls):
        return "in_progress_telephony_failed"

    return "in_progress_dialed"


def build_batch_summary(leads, calls_by_lead, dispositions):
    """Build batch_summary.csv rows."""

    batches = defaultdict(
        lambda: {
            "total_leads": 0,
            "yet_to_reach_out": 0,
            "in_progress_telephony_failed": 0,
            "in_progress_dialed": 0,
            "completed": 0,
        }
    )

    for lead in leads:

        workflow_id = lead["workflow_id"]
        lead_key = (
            workflow_id,
            lead["phone_fingerprint"],
        )

        calls = calls_by_lead[lead_key]

        bucket = get_bucket(
            calls,
            workflow_id,
            dispositions,
        )

        batch_key = (
            workflow_id,
            lead["batch_id"],
        )

        batches[batch_key]["total_leads"] += 1
        batches[batch_key][bucket] += 1

    rows = []

    for (workflow_id, batch_id), counts in sorted(batches.items()):

        rows.append({
            "workflow_id": workflow_id,
            "batch_id": batch_id,
            "total_leads": counts["total_leads"],
            "yet_to_reach_out": counts["yet_to_reach_out"],
            "in_progress_telephony_failed": counts["in_progress_telephony_failed"],
            "in_progress_dialed": counts["in_progress_dialed"],
            "completed": counts["completed"],
     })

    return rows


def build_daily_overview(calls_by_lead):
    """
    Build daily_overview.csv.

    Counts:
    - Calls initiated on each IST date.
    - Calls connected on that date.
    - Distinct leads with a successful effective disposition
      on at least one call on that date.
    """

    daily = defaultdict(
        lambda: {
            "total_calls": 0,
            "connected_calls": 0,
            "success_leads": set(),
        }
    )

    for (workflow_id, fingerprint), calls in calls_by_lead.items():

        for call in calls:

            local_time = to_ist(call["initiated_at"])
            date = local_time.date().isoformat()

            key = (workflow_id, date)

            daily[key]["total_calls"] += 1

            if call["connected"]:
                daily[key]["connected_calls"] += 1

            code = call["disposition"]

            # Successful status is checked in generate_reports
            # using the workflow's disposition definitions.
            if code is not None:
                daily[key]["success_leads"].add(
                    (fingerprint, code)
                )

    return daily


def build_lead_report(
    leads,
    calls_by_lead,
    security,
    dispositions,
):
    """Build lead_report.csv rows."""

    rows = []

    for lead in leads:

        workflow_id = lead["workflow_id"]

        lead_key = (
            workflow_id,
            lead["phone_fingerprint"],
        )

        calls = calls_by_lead[lead_key]

        bucket = get_bucket(
            calls,
            workflow_id,
            dispositions,
        )

        # Decrypt only when preparing the masked report value.
        canonical_phone = security.decrypt(
            lead["phone_encrypted"]
        )

        phone_masked = security.mask_phone(canonical_phone)

        # Most recent initiated call.
        last_call = (
            max(calls, key=lambda call: call["initiated_at"])
            if calls
            else None
        )

        last_call_at = ""

        if last_call is not None:
            last_call_at = to_ist(
                last_call["initiated_at"]
            ).isoformat()

        # Current disposition belongs to the most recent call
        # that has an effective disposition.
        calls_with_disposition = [
            call
            for call in calls
            if call["disposition"] is not None
        ]

        current_disposition = ""

        if calls_with_disposition:
            latest_disposition_call = max(
                calls_with_disposition,
                key=lambda call: call["initiated_at"],
            )

            current_disposition = (
                latest_disposition_call["disposition"]
            )

        ever_success = any(
            call["disposition"] is not None
            and dispositions[workflow_id][
                call["disposition"]
            ]["is_success"]
            for call in calls
        )

        connected_calls = sum(
            1 for call in calls if call["connected"]
        )

        rows.append({
            "workflow_id": workflow_id,
            "external_ref": lead["external_ref"] or "",
            "batch_id": lead["batch_id"],
            "phone_masked": phone_masked,
            "bucket": bucket,
            "total_calls": len(calls),
            "connected_calls": connected_calls,
            "last_call_at": last_call_at,
            "current_disposition": current_disposition,
            "ever_success": str(ever_success).lower(),
        })

    rows.sort(
        key=lambda row: (
            row["workflow_id"],
            row["external_ref"],
        )
    )

    return rows


def build_daily_rows(daily, dispositions):
    """Convert daily aggregation into CSV rows."""

    rows = []

    for (workflow_id, date), values in sorted(daily.items()):

        total_calls = values["total_calls"]
        connected_calls = values["connected_calls"]

        rate = (
            Decimal(connected_calls) / Decimal(total_calls)
        ).quantize(Decimal("0.0001"))

        success_leads = {
            fingerprint
            for fingerprint, code in values["success_leads"]
            if dispositions[workflow_id][code]["is_success"]
        }

        rows.append({
            "workflow_id": workflow_id,
            "date": date,
            "total_calls": total_calls,
            "connected_calls": connected_calls,
            "connectivity_rate": f"{rate:.4f}",
            "success_leads": len(success_leads),
        })

    return rows


def build_rejections(connection):
    """Build rejections.csv without exposing customer PII."""

    rows = connection.execute(
        """
        SELECT
            workflow_id,
            batch_id,
            row_number,
            reason
        FROM rejections
        ORDER BY workflow_id, batch_id, row_number
        """
    ).fetchall()

    return [dict(row) for row in rows]


def build_data_quality(connection, dispositions):
    """Build data_quality.json from stored metrics and final DB state."""

    rejection_rows = connection.execute(
        """
        SELECT reason, COUNT(*) AS total
        FROM rejections
        GROUP BY reason
        ORDER BY reason
        """
    ).fetchall()

    rejections_by_reason = {
        row["reason"]: row["total"]
        for row in rejection_rows
    }

    # Count unknown disposition events only when linked to a lead.
    # Orphan events are excluded from reports.
    linked_events = get_linked_events(connection)

    unknown_disposition_events = 0

    for event in linked_events:

        if event["event_type"] not in {
            "disposition.set",
            "disposition.override",
        }:
            continue

        payload = json.loads(event["payload_json"])
        code = payload.get("disposition_code")

        if not isinstance(code, str):
            continue

        code = code.strip().lower()

        if code not in dispositions.get(
            event["workflow_id"],
            {},
        ):
            unknown_disposition_events += 1

    return {
        "lead_rows_total": sum_metric(
            connection,
            "lead_rows_total",
        ),
        "lead_rows_rejected": sum_metric(
            connection,
            "lead_rows_rejected",
        ),
        "rejections_by_reason": rejections_by_reason,
        "duplicate_lead_rows_merged": sum_metric(
            connection,
            "duplicate_lead_rows_merged",
        ),
        "field_warnings": sum_metric(
            connection,
            "field_warning",
        ),
        "events_total": sum_metric(
            connection,
            "events_total",
        ),
        "malformed_events": sum_metric(
            connection,
            "malformed_events",
        ),
        "duplicate_events_dropped": sum_metric(
            connection,
            "duplicate_events_dropped",
        ),
        "orphan_events": count_orphan_events(connection),
        "unknown_disposition_events": (
            unknown_disposition_events
        ),
    }


def generate_reports(
    connection,
    output_dir,
    security,
    dispositions,
    schemas,
):
    """
    Generate all five required Assignment A report files.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Verify that each workflow schema identifies a reference field.
    for workflow_id, schema in schemas.items():

        reference_fields = [
            field["name"]
            for field in schema["fields"]
            if field.get("reference", False)
        ]

        if len(reference_fields) != 1:
            raise ValueError(
                f"Expected exactly one reference field for "
                f"{workflow_id}; found {reference_fields}"
            )

    # Load linked call information once.
    leads, calls_by_lead = get_call_data(
        connection,
        security,
        dispositions,
    )

    # 1. batch_summary.csv
    batch_rows = build_batch_summary(
        leads,
        calls_by_lead,
        dispositions,
    )

    write_csv(
        output_dir / "batch_summary.csv",
        [
            "workflow_id",
            "batch_id",
            "total_leads",
            "yet_to_reach_out",
            "in_progress_telephony_failed",
            "in_progress_dialed",
            "completed",
        ],
        batch_rows,
    )

    # 2. daily_overview.csv
    daily = build_daily_overview(calls_by_lead)

    daily_rows = build_daily_rows(
        daily,
        dispositions,
    )

    write_csv(
        output_dir / "daily_overview.csv",
        [
            "workflow_id",
            "date",
            "total_calls",
            "connected_calls",
            "connectivity_rate",
            "success_leads",
        ],
        daily_rows,
    )

    # 3. lead_report.csv
    lead_rows = build_lead_report(
        leads,
        calls_by_lead,
        security,
        dispositions,
    )

    write_csv(
        output_dir / "lead_report.csv",
        [
            "workflow_id",
            "external_ref",
            "batch_id",
            "phone_masked",
            "bucket",
            "total_calls",
            "connected_calls",
            "last_call_at",
            "current_disposition",
            "ever_success",
        ],
        lead_rows,
    )

    # 4. rejections.csv
    rejection_rows = build_rejections(connection)

    write_csv(
        output_dir / "rejections.csv",
        [
            "workflow_id",
            "batch_id",
            "row_number",
            "reason",
        ],
        rejection_rows,
    )

    # 5. data_quality.json
    data_quality = build_data_quality(
        connection,
        dispositions,
    )

    with (output_dir / "data_quality.json").open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data_quality,
            file,
            indent=2,
            ensure_ascii=False,
        )

    return {
        "batch_summary_rows": len(batch_rows),
        "daily_overview_rows": len(daily_rows),
        "lead_report_rows": len(lead_rows),
        "rejection_rows": len(rejection_rows),
        "output_directory": str(output_dir.resolve()),
    }
