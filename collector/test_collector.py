from datetime import timezone

from collector import atis_row, controller_row, movement_state, parse_timestamp, pilot_row


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


def test_ekch_movement_states():
    assert movement_state("EKCH", 55.6181, 12.6561, 25, 12) == "ground"
    assert movement_state("EKCH", 55.63, 12.70, 1200, 160) == "airborne_near"
    assert movement_state("EKCH", 56.0, 13.0, 1200, 160) == "other"
    assert movement_state("EKBI", 55.7403, 9.1518, 250, 5) == "ground"
