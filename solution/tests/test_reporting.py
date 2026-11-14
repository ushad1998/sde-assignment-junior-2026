from datetime import datetime
from zoneinfo import ZoneInfo

from solution.src.reporting import (
    to_ist,
    get_effective_disposition,
    get_bucket,
    build_daily_overview,
    build_daily_rows,
)


DISPOSITIONS = {
    "motor_renewal": {
        "renewed": {
            "label": "Policy renewed",
            "is_terminal": True,
            "is_success": True,
        },
        "not_interested": {
            "label": "Not interested",
            "is_terminal": True,
            "is_success": False,
        },
        "callback_requested": {
            "label": "Callback requested",
            "is_terminal": False,
            "is_success": False,
        },
    }
}


def make_disposition_event(event_type, code, timestamp):
    return {
        "event_type": event_type,
        "occurred_at": timestamp,
        "payload_json": f'{{"disposition_code": "{code}"}}',
    }


def make_call(
    initiated_at,
    connected=False,
    disposition=None,
):
    return {
        "initiated_at": initiated_at,
        "connected": connected,
        "disposition": disposition,
    }


def test_to_ist_converts_utc_to_indian_time():
    result = to_ist("2026-10-01T20:00:00+00:00")

    assert result.isoformat() == "2026-10-02T01:30:00+05:30"


def test_to_ist_treats_naive_timestamp_as_utc():
    result = to_ist("2026-10-01T20:00:00")

    assert result.isoformat() == "2026-10-02T01:30:00+05:30"


def test_latest_valid_override_wins_over_disposition_set():
    events = [
        make_disposition_event(
            "disposition.set",
            "renewed",
            "2026-10-01T12:00:00+00:00",
        ),
        make_disposition_event(
            "disposition.override",
            "not_interested",
            "2026-10-01T10:00:00+00:00",
        ),
    ]

    result = get_effective_disposition(
        events,
        "motor_renewal",
        DISPOSITIONS,
    )

    assert result == "not_interested"


def test_latest_override_wins_when_multiple_overrides_exist():
    events = [
        make_disposition_event(
            "disposition.override",
            "renewed",
            "2026-10-01T10:00:00+00:00",
        ),
        make_disposition_event(
            "disposition.override",
            "not_interested",
            "2026-10-01T12:00:00+00:00",
        ),
    ]

    result = get_effective_disposition(
        events,
        "motor_renewal",
        DISPOSITIONS,
    )

    assert result == "not_interested"


def test_unknown_override_is_ignored():
    events = [
        make_disposition_event(
            "disposition.set",
            "renewed",
            "2026-10-01T10:00:00+00:00",
        ),
        make_disposition_event(
            "disposition.override",
            "unknown_code",
            "2026-10-01T12:00:00+00:00",
        ),
    ]

    result = get_effective_disposition(
        events,
        "motor_renewal",
        DISPOSITIONS,
    )

    assert result == "renewed"


def test_bucket_without_calls_is_yet_to_reach_out():
    result = get_bucket(
        [],
        "motor_renewal",
        DISPOSITIONS,
    )

    assert result == "yet_to_reach_out"


def test_terminal_disposition_has_completed_priority():
    calls = [
        {
            "telephony_failed": True,
            "disposition": "renewed",
        }
    ]

    result = get_bucket(
        calls,
        "motor_renewal",
        DISPOSITIONS,
    )

    assert result == "completed"


def test_bucket_detects_all_telephony_failures():
    calls = [
        {
            "telephony_failed": True,
            "disposition": None,
        },
        {
            "telephony_failed": True,
            "disposition": None,
        },
    ]

    result = get_bucket(
        calls,
        "motor_renewal",
        DISPOSITIONS,
    )

    assert result == "in_progress_telephony_failed"


def test_daily_overview_counts_calls_and_distinct_successful_leads():
    calls_by_lead = {
        ("motor_renewal", "fingerprint_1"): [
            make_call(
                "2026-10-01T20:00:00+00:00",
                connected=True,
                disposition="renewed",
            ),
            make_call(
                "2026-10-01T21:00:00+00:00",
                connected=False,
                disposition="callback_requested",
            ),
        ],
        ("motor_renewal", "fingerprint_2"): [
            make_call(
                "2026-10-01T22:00:00+00:00",
                connected=True,
                disposition="renewed",
            ),
        ],
    }

    daily = build_daily_overview(calls_by_lead)

    rows = build_daily_rows(daily, DISPOSITIONS)

    assert len(rows) == 1

    row = rows[0]

    assert row["workflow_id"] == "motor_renewal"
    assert row["date"] == "2026-10-02"
    assert row["total_calls"] == 3
    assert row["connected_calls"] == 2
    assert row["connectivity_rate"] == "0.6667"
    assert row["success_leads"] == 2
