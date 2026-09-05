from datetime import datetime, timezone

from collector import (
    AIRBORNE_MIN_ALTITUDE_FT,
    AIRBORNE_MIN_SPEED_KT,
    AIRPORTS,
    GROUND_MAX_SPEED_KT,
    MOVEMENT_LOOKBACK_SECONDS,
    atis_row,
    controller_row,
    detect_movement_events,
    movement_state,
    parse_timestamp,
    pilot_row,
)


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


def test_movement_thresholds_are_configured_for_recent_history():
    assert MOVEMENT_LOOKBACK_SECONDS == 120
    assert GROUND_MAX_SPEED_KT == 60
    assert AIRBORNE_MIN_ALTITUDE_FT == 450
    assert AIRBORNE_MIN_SPEED_KT == 80
    assert set(AIRPORTS) == {"EKCH", "EKYT", "EKBI", "EKAH"}


def test_arrival_uses_recent_airborne_observation_after_intervening_snapshot():
    logon_time = parse_timestamp("2026-09-04T12:00:00Z")
    cursor = FakeCursor([
        (42, "TEST1", logon_time, 56.0, 13.0, 1200, 160),
        (42, "TEST1", logon_time, 55.63, 12.70, 1200, 160),
    ])
    current = [{
        "cid": 42,
        "callsign": "TEST1",
        "logon_time": "2026-09-04T12:00:00Z",
        "latitude": 55.6181,
        "longitude": 12.6561,
        "altitude": 25,
        "groundspeed": 12,
        "flight_plan": {"arrival": "EKCH"},
    }]

    detected = detect_movement_events(
        cursor, 10, 12, datetime(2026, 9, 4, 12, 0, 30, tzinfo=timezone.utc), current
    )

    assert detected == 1
    assert cursor.inserted_event[3] == "arrival"


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.inserted_event = None
        self.rowcount = 0

    def execute(self, query, params):
        if query.lstrip().startswith("SELECT"):
            self.rowcount = -1
        else:
            self.inserted_event = params
            self.rowcount = 1

    def fetchall(self):
        return self.rows
