from datetime import timezone

from collector import atis_row, controller_row, parse_timestamp, pilot_row


def test_parse_timestamp_handles_zulu():
    parsed = parse_timestamp("2026-09-04T12:34:56.000000Z")
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc


def test_pilot_row_handles_missing_flight_plan():
    now = parse_timestamp("2026-09-04T12:34:56Z")
    row = pilot_row(1, now, {"cid": 42, "callsign": "TEST1", "flight_plan": None})
    assert row[2:5] == (42, "TEST1", None)
    assert row[10:13] == (None, None, None)


def test_controller_and_atis_rows_accept_minimum_fields():
    now = parse_timestamp("2026-09-04T12:34:56Z")
    assert controller_row(1, now, {"cid": 42, "callsign": "TEST_CTR"})[3] == "TEST_CTR"
    assert atis_row(1, now, {"cid": 42, "callsign": "TEST_ATIS"})[3] == "TEST_ATIS"
