from __future__ import annotations

import json
import logging
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


def stop(_signum: int, _frame: Any) -> None:
    global stopping
    stopping = True


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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


def save_snapshot(connection: psycopg.Connection[Any], feed: dict[str, Any]) -> bool:
    general = feed["general"]
    pilots = feed.get("pilots", [])
    controllers = feed.get("controllers", [])
    atis_entries = feed.get("atis", [])
    captured_at = datetime.now(timezone.utc)
    feed_updated_at = parse_timestamp(general["update_timestamp"])

    with connection.transaction(), connection.cursor() as cursor:
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
