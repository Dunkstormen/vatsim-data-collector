"""Execute the shipped Grafana SQL against a disposable PostgreSQL database.

Set TEST_PSQL_COMMAND to a JSON argument list, e.g.
["podman", "exec", "-i", "cph-dashboard-qa-postgres", "psql", "-U", "postgres", "-d", "vatsim"].
Fixtures live in transaction-local temporary tables; no persistent data is changed.
Run: python -m unittest discover -s tests -v
"""

import json
import os
from pathlib import Path
import subprocess
import unittest


DASHBOARD = json.loads((Path(__file__).resolve().parents[1] / "grafana/dashboards/copenhagen-live.json").read_text(encoding="utf-8"))
PANELS = {panel["id"]: panel for panel in DASHBOARD["panels"]}
PSQL = json.loads(os.environ.get("TEST_PSQL_COMMAND", "[]"))
FIXTURES = """
INSERT INTO flight_events VALUES
 ('2026-09-05 03:59Z', 'EKCH', 'departure', 'EKCH', 'BEFORE'),
 ('2026-09-05 04:00Z', 'EKCH', 'departure', 'EKCH', 'EGLL'),
 ('2026-09-05 04:01Z', 'EKCH', 'departure', 'EKCH', ' egll '),
 ('2026-09-05 04:03Z', 'EKCH', 'arrival', 'ENGM', 'EKCH'),
 ('2026-09-05 04:05Z', 'EKCH', 'departure', 'EKCH', NULL),
 ('2026-09-05 04:10Z', 'EKBI', 'arrival', 'ENGM', 'EKBI'),
 ('2026-09-05 04:15Z', 'EKCH', 'arrival', 'ENGM', 'EKCH'),
 ('2026-09-05 04:30Z', 'EKCH', 'arrival', 'EHAM', 'EKCH'),
 ('2026-09-05 04:50Z', 'EKCH', 'departure', 'EKCH', 'EHAM'),
 ('2026-09-05 05:00Z', 'EKCH', 'departure', 'EKCH', 'AFTER');
"""


def query(panel_id, start="2026-09-05T04:00:00Z", end="2026-09-05T05:00:00Z",
          now="2026-09-06T00:00:00Z", fixtures=FIXTURES):
    sql = PANELS[panel_id]["targets"][0]["rawSql"]
    sql = sql.replace("$__timeFrom()", f"'{start}'").replace("$__timeTo()", f"'{end}'")
    sql = sql.replace("now()", f"'{now}'::timestamptz")
    script = f"""
    BEGIN;
    SET LOCAL TIME ZONE 'UTC';
    CREATE TEMP TABLE flight_events (
        event_at timestamptz, airport text, event_type text, origin text, destination text
    ) ON COMMIT DROP;
    {fixtures}
    SELECT COALESCE(json_agg(q), '[]'::json) FROM ({sql}) q;
    ROLLBACK;
    """
    result = subprocess.run(PSQL + ["-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
                            input=script, text=True, encoding="utf-8", capture_output=True, check=True)
    return json.loads(result.stdout)


class DashboardConfigTests(unittest.TestCase):
    def test_layout_has_unique_ids_and_no_overlaps(self):
        self.assertEqual(len(PANELS), len(DASHBOARD["panels"]))
        positions = [p["gridPos"] for p in DASHBOARD["panels"]]
        for i, a in enumerate(positions):
            for b in positions[i + 1:]:
                self.assertFalse(a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
                                 and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])

    def test_fixed_color_values_are_not_mode_ids(self):
        for panel in PANELS.values():
            config = panel["fieldConfig"]
            self.assertNotEqual(config["defaults"]["color"]["mode"], "fixedColor")
            for override in config["overrides"]:
                for prop in override["properties"]:
                    if prop["id"] == "color":
                        self.assertNotEqual(prop["value"]["mode"], "fixedColor")


@unittest.skipUnless(PSQL, "Set TEST_PSQL_COMMAND to execute PostgreSQL integration tests")
class DashboardSQLTests(unittest.TestCase):
    def test_airport_rankings_use_correct_direction_and_normalize_codes(self):
        self.assertEqual(query(6), [
            {"Destination": "EGLL", "Departures": 2},
            {"Destination": "EHAM", "Departures": 1},
            {"Destination": "Unknown", "Departures": 1},
        ])
        self.assertEqual(query(9), [
            {"Origin": "ENGM", "Arrivals": 2}, {"Origin": "EHAM", "Arrivals": 1},
        ])

    def test_timeline_and_cumulative_reconcile_with_stats(self):
        departures, arrivals = query(1)[0]["Departures"], query(2)[0]["Arrivals"]
        self.assertEqual((departures, arrivals), (4, 3))
        timeline = query(5)
        self.assertEqual(len(timeline), 4)
        self.assertEqual(sum(r["Departures"] for r in timeline), departures)
        self.assertEqual(sum(r["Arrivals"] for r in timeline), arrivals)
        self.assertEqual([(r["Departures"], r["Arrivals"]) for r in timeline], [(3, 1), (0, 1), (0, 1), (1, 0)])
        cumulative = query(10)
        self.assertEqual((cumulative[-1]["Departures"], cumulative[-1]["Arrivals"]), (departures, arrivals))
        for label in ("Departures", "Arrivals"):
            values = [r[label] for r in cumulative]
            self.assertEqual(values, sorted(values))
        # Steps use actual movement times, not the start of their quarter-hour bin.
        self.assertEqual(cumulative[1]["time"], "2026-09-05T04:01:00+00:00")
        self.assertEqual(cumulative[1]["Departures"], 2)

    def test_empty_periods_are_zero_and_cumulative_stays_flat(self):
        timeline = query(5, fixtures="")
        self.assertEqual(len(timeline), 4)
        self.assertTrue(all(r["Departures"] == r["Arrivals"] == 0 for r in timeline))
        cumulative = query(10, fixtures="")
        self.assertEqual(len(cumulative), 2)
        self.assertTrue(all(r["Departures"] == r["Arrivals"] == 0 for r in cumulative))
        self.assertEqual(query(11, fixtures=""), [])

    def test_busiest_periods_sort_by_total_then_time(self):
        periods = query(11)
        self.assertEqual([r["Total"] for r in periods], [4, 1, 1, 1])
        self.assertEqual(periods[0]["Period (UTC)"], "05 Sep 04:00–04:15")
        self.assertEqual(periods[-1]["Period (UTC)"], "05 Sep 04:45–05:00")

    def test_partial_range_does_not_include_events_outside_selection(self):
        args = {"start": "2026-09-05T04:02:00Z", "end": "2026-09-05T04:32:00Z"}
        timeline = query(5, **args)
        self.assertEqual(len(timeline), 3)
        self.assertEqual(timeline[0]["time"], "2026-09-05T04:02:00+00:00")
        self.assertEqual(query(1, **args)[0]["Departures"], 1)
        self.assertEqual(query(10, **args)[-1]["Departures"], 1)
        self.assertEqual(query(10, **args)[-1]["Arrivals"], 3)

    def test_future_intervals_are_not_reported_as_zero(self):
        args = {"now": "2026-09-05T04:20:00Z"}
        self.assertEqual(len(query(5, **args)), 2)
        self.assertEqual(query(10, **args)[-1]["time"], "2026-09-05T04:20:00+00:00")
        self.assertEqual(query(2, **args)[0]["Arrivals"], 2)
        self.assertEqual(query(5, now="2026-09-05T03:00:00Z"), [])
        self.assertEqual(query(10, now="2026-09-05T03:00:00Z"), [])

    def test_single_direction_and_simultaneous_events(self):
        fixtures = """INSERT INTO flight_events VALUES
          ('2026-09-05 04:10Z', 'EKCH', 'arrival', 'EDDF', 'EKCH'),
          ('2026-09-05 04:10Z', 'EKCH', 'arrival', 'EDDF', 'EKCH');"""
        timeline, cumulative = query(5, fixtures=fixtures), query(10, fixtures=fixtures)
        self.assertTrue(all(r["Departures"] == 0 for r in timeline))
        self.assertEqual([r["Arrivals"] for r in timeline], [2, 0, 0, 0])
        self.assertEqual([r["Arrivals"] for r in cumulative], [0, 2, 2])


if __name__ == "__main__":
    unittest.main()
