# VATSIM Data Collector

A Docker Compose stack that reads the public VATSIM Data API v3 feed every 15 seconds, stores each distinct feed update in PostgreSQL, and presents the data in a provisioned Grafana dashboard.

## Services

- `collector`: a small Python process with retry-safe, transactional ingestion.
- `postgres`: durable snapshot, pilot, controller, ATIS, and collector-event storage.
- `grafana`: a preconfigured PostgreSQL datasource plus **VATSIM Network Overview**, **Copenhagen Live**, and **CPH Live Competition Tracker** dashboards.

Every distinct feed update is stored in both forms:

- The complete, unmodified feed document is retained in `snapshots.raw_payload` as JSONB.
- Frequently queried data is divided into typed `snapshots`, `pilots`, `controllers`, and `atis` columns and tables.
- Each pilot/controller/ATIS row also retains its complete source object in its own `data` JSONB column.

This supports exact replay/export of a historical feed while keeping Grafana and SQL queries efficient. A unique feed timestamp prevents duplicate snapshots if the feed has not refreshed or the collector retries.

The collector also derives EKCH movement events from consecutive pilot observations. A departure is recorded when a filed EKCH departure changes from a conservative ground state at the airport to airborne nearby; an arrival is the inverse transition for a filed EKCH arrival. Events and the thresholds/evidence used to detect them are stored in `flight_events`. VATSIM does not publish an authoritative takeoff/landing flag, so these are auditable position-based inferences.

## Start

1. Copy `.env.example` to `.env` and change both passwords.
2. Start the stack:

   ```powershell
   docker compose up --build -d
   ```

3. Check service health:

   ```powershell
   docker compose ps
   docker compose logs -f collector
   ```

4. Open [Grafana](http://localhost:3000), sign in with the credentials from `.env`, and open the provisioned **VATSIM Network Overview** or **Copenhagen Live** dashboard under **Dashboards → VATSIM**.

PostgreSQL is available on `localhost:5432` by default. Override `POSTGRES_PORT` or `GRAFANA_PORT` in `.env` if those ports are occupied.

## GitHub Container Registry and Portainer

Every push to `main` builds the collector for AMD64 and ARM64 and publishes these public GHCR tags:

- `ghcr.io/dunkstormen/vatsim-data-collector:latest`
- `ghcr.io/dunkstormen/vatsim-data-collector:sha-<commit>`
- Version tags such as `1.0.0` when a Git tag such as `v1.0.0` is pushed.

To deploy in Portainer:

1. Create a Git-based stack from `https://github.com/Dunkstormen/vatsim-data-collector.git` using `docker-compose.portainer.yml` as the compose path.
2. Configure at least `POSTGRES_PASSWORD` and `GRAFANA_ADMIN_PASSWORD` in the stack environment. Use long, distinct values.
3. Deploy after the GitHub Actions **Publish collector image** workflow has completed.

The repository and image are public, so Portainer does not need GitHub or GHCR credentials.

The production compose file does not expose PostgreSQL publicly. Pin `COLLECTOR_TAG` to a version or `sha-...` tag when deterministic deployments are preferred over `latest`.

## Deploy with Podman

Podman Compose delegates to an installed Compose provider. Confirm both Podman and a provider are available:

```bash
podman --version
podman compose version
```

Clone and configure the stack as the unprivileged user that will own it:

```bash
git clone https://github.com/Dunkstormen/vatsim-data-collector.git
cd vatsim-data-collector
cp .env.example .env
chmod 600 .env
```

Edit `.env` and set long, distinct values for `POSTGRES_PASSWORD` and `GRAFANA_ADMIN_PASSWORD`. Then pull and start the public images:

```bash
podman compose -f docker-compose.portainer.yml pull
podman compose -f docker-compose.portainer.yml up -d
podman compose -f docker-compose.portainer.yml ps
podman compose -f docker-compose.portainer.yml logs -f collector
```

Grafana is available at `http://<server-address>:3000`. The compose bind mounts include private SELinux relabeling (`:Z`) for Fedora, RHEL, and other SELinux-enabled hosts. Named volumes preserve PostgreSQL and Grafana data across container replacement.

To update later:

```bash
git pull --ff-only
podman compose -f docker-compose.portainer.yml pull
podman compose -f docker-compose.portainer.yml up -d
```

To stop without deleting stored data:

```bash
podman compose -f docker-compose.portainer.yml down
```

Do not add `--volumes` unless you deliberately want to delete the database and Grafana volumes. For a rootless deployment that must start before login and survive logout, enable lingering for the service account and manage the workload with user systemd/Quadlet according to your distribution's Podman version.

## Useful queries

Latest snapshot:

```sql
SELECT * FROM latest_snapshot;
```

Export the latest complete feed document:

```sql
SELECT raw_payload
FROM snapshots
ORDER BY feed_updated_at DESC
LIMIT 1;
```

Current pilots:

```sql
SELECT callsign, departure, arrival, aircraft_short, altitude, groundspeed
FROM pilots
WHERE snapshot_id = (SELECT id FROM latest_snapshot)
ORDER BY callsign;
```

Collector errors:

```sql
SELECT * FROM collector_events ORDER BY occurred_at DESC LIMIT 100;
```

## Operations

Stop without deleting data:

```powershell
docker compose down
```

Delete the stack and all stored PostgreSQL/Grafana data only when deliberately starting over:

```powershell
docker compose down --volumes
```

Schema scripts in `db/init` run only when PostgreSQL creates a new data volume. For later schema changes, use versioned migrations rather than editing an already-applied initialization script.

## Storage planning

At a 15-second interval, the stack can produce 5,760 snapshots per day and millions of entity rows. Keeping both the full feed and normalized records deliberately trades disk space for replayability. PostgreSQL will normally TOAST-compress large JSONB values, but storage usage still depends heavily on network activity. Monitor disk growth before long-term unattended operation; a retention or archival policy should be chosen based on the history you need.

## Feed

The collector uses the public `https://data.vatsim.net/v3/vatsim-data.json` endpoint. The interval and request timeout can be changed in `.env`, though polling more frequently than the feed's 15-second refresh provides no additional data.
