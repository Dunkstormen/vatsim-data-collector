from __future__ import annotations

import json
import logging
import math
import os
import signal
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://vatsim:vatsim-local@localhost:5432/vatsim")
FEED_URL = os.environ.get("VATSIM_FEED_URL", "https://data.vatsim.net/v3/vatsim-data.json")
INTERVAL = max(1.0, float(os.environ.get("COLLECT_INTERVAL_SECONDS", "15")))
TIMEOUT = max(1.0, float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "10")))
HEALTH_FILE = Path(os.environ.get("HEALTH_FILE", "/tmp/collector-healthy"))

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("vatsim-collector")
stopping = False

EKCH_LATITUDE = 55.6181
EKCH_LONGITUDE = 12.6561
GROUND_RADIUS_NM = 4.0
AIRBORNE_RADIUS_NM = 12.0
GROUND_MAX_ALTITUDE_FT = 350
GROUND_MAX_SPEED_KT = 60
AIRBORNE_MIN_ALTITUDE_FT = 450
AIRBORNE_MIN_SPEED_KT = 80


def stop(_signum: int, _frame: Any) -> None:
    global stopping
    stopping = True


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def distance_nm(latitude: float, longitude: float) -> float:
    earth_radius_nm = 3440.065
    lat1 = math.radians(EKCH_LATITUDE)
    lat2 = math.radians(latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(longitude - EKCH_LONGITUDE)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return earth_radius_nm * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def movement_state(latitude: float | None, longitude: float | None, altitude: int | None, groundspeed: int | None) -> str:
    if latitude is None or longitude is None or altitude is None or groundspeed is None:
        return "other"
    radius = distance_nm(latitude, longitude)
    if radius <= GROUND_RADIUS_NM and altitude <= GROUND_MAX_ALTITUDE_FT and groundspeed <= GROUND_MAX_SPEED_KT:
        return "ground"
    if radius <= AIRBORNE_RADIUS_NM and (altitude >= AIRBORNE_MIN_ALTITUDE_FT or groundspeed >= AIRBORNE_MIN_SPEED_KT):
        return "airborne_near"
    return "other"


def ensure_schema(connection: psycopg.Connection[Any]) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS flight_events (
            id BIGSERIAL PRIMARY KEY,
            event_at TIMESTAMPTZ NOT NULL,
            snapshot_id BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
            airport TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('departure', 'arrival')),
            cid BIGINT NOT NULL,
            callsign TEXT NOT NULL,
            logon_time TIMESTAMPTZ NOT NULL,
            aircraft_short TEXT,
            origin TEXT,
            destination TEXT,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            altitude INTEGER NOT NULL,
            groundspeed INTEGER NOT NULL,
            detection JSONB NOT NULL,
            UNIQUE (airport, event_type, cid, callsign, logon_time)
        );
        CREATE INDEX IF NOT EXISTS flight_events_airport_time_idx
            ON flight_events (airport, event_type, event_at DESC);
        """
    )
    connection.commit()


def fetch_feed() -> dict[str, Any]:
    request = urllib.request.Request(
        FEED_URL,
        headers={"Accept": "application/json", "User-Agent": "vatsim-snapshot-collector/1.0"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        if response.status != 200:
            raise RuntimeError(f"feed returned HTTP {response.status}")
        return json.load(response)


def pilot_row(snapshot_id: int, captured_at: datetime, item: dict[str, Any]) -> tuple[Any, ...]:
    flight_plan = item.get("flight_plan") or {}
    return (
        snapshot_id, captured_at, item["cid"], item["callsign"], item.get("name"),
        item.get("latitude"), item.get("longitude"), item.get("altitude"),
        item.get("groundspeed"), item.get("heading"), flight_plan.get("aircraft_short"),
        flight_plan.get("departure"), flight_plan.get("arrival"), item.get("server"),
        parse_timestamp(item.get("logon_time")), Jsonb(item),
    )


def controller_row(snapshot_id: int, captured_at: datetime, item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot_id, captured_at, item["cid"], item["callsign"], item.get("name"),
        item.get("frequency"), item.get("facility"), item.get("rating"),
        item.get("latitude"), item.get("longitude"), item.get("server"),
        parse_timestamp(item.get("logon_time")), Jsonb(item),
    )


def atis_row(snapshot_id: int, captured_at: datetime, item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot_id, captured_at, item["cid"], item["callsign"], item.get("name"),
        item.get("frequency"), item.get("atis_code"), item.get("server"),
        parse_timestamp(item.get("logon_time")), Jsonb(item),
    )


def detect_movement_events(
    cursor: psycopg.Cursor[Any], previous_snapshot_id: int | None, snapshot_id: int,
    captured_at: datetime, current_pilots: list[dict[str, Any]],
) -> int:
    if previous_snapshot_id is None:
        return 0
    cursor.execute(
        """
        SELECT cid, callsign, logon_time, latitude, longitude, altitude, groundspeed
        FROM pilots
        WHERE snapshot_id = %s AND (departure = 'EKCH' OR arrival = 'EKCH')
        """,
        (previous_snapshot_id,),
    )
    previous = {(row[0], row[1], row[2]): row[3:] for row in cursor.fetchall()}
    detected = 0
    for item in current_pilots:
        flight_plan = item.get("flight_plan") or {}
        origin = flight_plan.get("departure")
        destination = flight_plan.get("arrival")
        if origin != "EKCH" and destination != "EKCH":
            continue
        logon_time = parse_timestamp(item.get("logon_time"))
        if logon_time is None:
            continue
        key = (item["cid"], item["callsign"], logon_time)
        prior = previous.get(key)
        if prior is None:
            continue
        prior_state = movement_state(prior[0], prior[1], prior[2], prior[3])
        current_state = movement_state(
            item.get("latitude"), item.get("longitude"), item.get("altitude"), item.get("groundspeed")
        )
        event_type = None
        if origin == "EKCH" and prior_state == "ground" and current_state == "airborne_near":
            event_type = "departure"
        elif destination == "EKCH" and prior_state == "airborne_near" and current_state == "ground":
            event_type = "arrival"
        if event_type is None:
            continue
        radius = distance_nm(item["latitude"], item["longitude"])
        cursor.execute(
            """
            INSERT INTO flight_events (
                event_at, snapshot_id, airport, event_type, cid, callsign, logon_time,
                aircraft_short, origin, destination, latitude, longitude, altitude,
                groundspeed, detection
            ) VALUES (%s, %s, 'EKCH', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (airport, event_type, cid, callsign, logon_time) DO NOTHING
            """,
            (
                captured_at, snapshot_id, event_type, item["cid"], item["callsign"], logon_time,
                flight_plan.get("aircraft_short"), origin, destination, item["latitude"],
                item["longitude"], item["altitude"], item["groundspeed"],
                Jsonb({
                    "method": "consecutive_snapshot_state_transition_v1",
                    "previous_state": prior_state,
                    "current_state": current_state,
                    "distance_nm": round(radius, 3),
                    "thresholds": {
                        "ground_radius_nm": GROUND_RADIUS_NM,
                        "airborne_radius_nm": AIRBORNE_RADIUS_NM,
                        "ground_max_altitude_ft": GROUND_MAX_ALTITUDE_FT,
                        "ground_max_speed_kt": GROUND_MAX_SPEED_KT,
                        "airborne_min_altitude_ft": AIRBORNE_MIN_ALTITUDE_FT,
                        "airborne_min_speed_kt": AIRBORNE_MIN_SPEED_KT,
                    },
                }),
            ),
        )
        detected += cursor.rowcount
    return detected


def save_snapshot(connection: psycopg.Connection[Any], feed: dict[str, Any]) -> bool:
    general = feed["general"]
    pilots = feed.get("pilots", [])
    controllers = feed.get("controllers", [])
    atis_entries = feed.get("atis", [])
    captured_at = datetime.now(timezone.utc)
    feed_updated_at = parse_timestamp(general["update_timestamp"])

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("SELECT id FROM snapshots ORDER BY feed_updated_at DESC LIMIT 1")
        previous_result = cursor.fetchone()
        previous_snapshot_id = previous_result[0] if previous_result else None
        cursor.execute(
            """
            INSERT INTO snapshots (
                captured_at, feed_updated_at, feed_version, connected_clients, unique_users,
                pilot_count, controller_count, atis_count, server_count, raw_payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (feed_updated_at) DO NOTHING
            RETURNING id
            """,
            (
                captured_at, feed_updated_at, general["version"], general["connected_clients"],
                general["unique_users"], len(pilots), len(controllers), len(atis_entries),
                len(feed.get("servers", [])), Jsonb(feed),
            ),
        )
        result = cursor.fetchone()
        if result is None:
            return False
        snapshot_id = result[0]

        cursor.executemany(
            """INSERT INTO pilots VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (pilot_row(snapshot_id, captured_at, item) for item in pilots),
        )
        cursor.executemany(
            """INSERT INTO controllers VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (controller_row(snapshot_id, captured_at, item) for item in controllers),
        )
        cursor.executemany(
            """INSERT INTO atis VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (atis_row(snapshot_id, captured_at, item) for item in atis_entries),
        )
        movement_count = detect_movement_events(
            cursor, previous_snapshot_id, snapshot_id, captured_at, pilots
        )
        if movement_count:
            log.info("detected %d EKCH movement event(s)", movement_count)
    return True


def record_error(connection: psycopg.Connection[Any] | None, error: Exception) -> None:
    if connection is None or connection.closed:
        return
    try:
        connection.execute(
            "INSERT INTO collector_events (level, message, details) VALUES ('ERROR', %s, %s)",
            (str(error), Jsonb({"type": type(error).__name__})),
        )
        connection.commit()
    except Exception:
        log.exception("could not record collector error")


def main() -> None:
    connection: psycopg.Connection[Any] | None = None
    next_run = time.monotonic()
    while not stopping:
        try:
            if connection is None or connection.closed:
                connection = psycopg.connect(DATABASE_URL, autocommit=False)
                ensure_schema(connection)
            feed = fetch_feed()
            inserted = save_snapshot(connection, feed)
            if inserted:
                HEALTH_FILE.touch()
                log.info(
                    "stored feed update=%s pilots=%d controllers=%d atis=%d",
                    feed["general"]["update_timestamp"], len(feed.get("pilots", [])),
                    len(feed.get("controllers", [])), len(feed.get("atis", [])),
                )
            else:
                log.info("feed update %s already stored", feed["general"]["update_timestamp"])
        except (KeyError, ValueError, RuntimeError, urllib.error.URLError, psycopg.Error) as error:
            log.exception("collection failed")
            if connection is not None:
                try:
                    connection.rollback()
                except psycopg.Error:
                    pass
            record_error(connection, error)
            if isinstance(error, psycopg.Error):
                connection = None

        next_run += INTERVAL
        delay = next_run - time.monotonic()
        if delay < 0:
            next_run = time.monotonic()
            delay = 0
        deadline = time.monotonic() + delay
        while not stopping and time.monotonic() < deadline:
            time.sleep(min(0.5, deadline - time.monotonic()))

    if connection is not None:
        connection.close()
    log.info("collector stopped")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    main()
