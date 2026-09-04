CREATE TABLE IF NOT EXISTS snapshots (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    feed_updated_at TIMESTAMPTZ NOT NULL UNIQUE,
    feed_version INTEGER NOT NULL,
    connected_clients INTEGER NOT NULL,
    unique_users INTEGER NOT NULL,
    pilot_count INTEGER NOT NULL,
    controller_count INTEGER NOT NULL,
    atis_count INTEGER NOT NULL,
    server_count INTEGER NOT NULL,
    raw_payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS snapshots_captured_at_idx ON snapshots (captured_at DESC);

CREATE TABLE IF NOT EXISTS pilots (
    snapshot_id BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    captured_at TIMESTAMPTZ NOT NULL,
    cid BIGINT NOT NULL,
    callsign TEXT NOT NULL,
    name TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    altitude INTEGER,
    groundspeed INTEGER,
    heading INTEGER,
    aircraft_short TEXT,
    departure TEXT,
    arrival TEXT,
    server TEXT,
    logon_time TIMESTAMPTZ,
    data JSONB NOT NULL,
    PRIMARY KEY (snapshot_id, cid, callsign)
);

CREATE INDEX IF NOT EXISTS pilots_captured_at_idx ON pilots (captured_at DESC);
CREATE INDEX IF NOT EXISTS pilots_callsign_time_idx ON pilots (callsign, captured_at DESC);
CREATE INDEX IF NOT EXISTS pilots_route_idx ON pilots (departure, arrival, captured_at DESC);
CREATE INDEX IF NOT EXISTS pilots_position_idx ON pilots (captured_at DESC, latitude, longitude);

CREATE TABLE IF NOT EXISTS controllers (
    snapshot_id BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    captured_at TIMESTAMPTZ NOT NULL,
    cid BIGINT NOT NULL,
    callsign TEXT NOT NULL,
    name TEXT,
    frequency TEXT,
    facility INTEGER,
    rating INTEGER,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    server TEXT,
    logon_time TIMESTAMPTZ,
    data JSONB NOT NULL,
    PRIMARY KEY (snapshot_id, cid, callsign)
);

CREATE INDEX IF NOT EXISTS controllers_captured_at_idx ON controllers (captured_at DESC);
CREATE INDEX IF NOT EXISTS controllers_callsign_time_idx ON controllers (callsign, captured_at DESC);

CREATE TABLE IF NOT EXISTS atis (
    snapshot_id BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    captured_at TIMESTAMPTZ NOT NULL,
    cid BIGINT NOT NULL,
    callsign TEXT NOT NULL,
    name TEXT,
    frequency TEXT,
    atis_code TEXT,
    server TEXT,
    logon_time TIMESTAMPTZ,
    data JSONB NOT NULL,
    PRIMARY KEY (snapshot_id, cid, callsign)
);

CREATE INDEX IF NOT EXISTS atis_captured_at_idx ON atis (captured_at DESC);
CREATE INDEX IF NOT EXISTS atis_callsign_time_idx ON atis (callsign, captured_at DESC);

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

CREATE TABLE IF NOT EXISTS collector_events (
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSONB
);

CREATE INDEX IF NOT EXISTS collector_events_occurred_at_idx ON collector_events (occurred_at DESC);

CREATE OR REPLACE VIEW latest_snapshot AS
SELECT * FROM snapshots ORDER BY feed_updated_at DESC LIMIT 1;
