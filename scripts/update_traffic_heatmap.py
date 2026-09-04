"""Embed the heatmap SQL and Charts Function into the provisioned dashboard."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "grafana/dashboards/copenhagen-live.json"
dashboard = json.loads(path.read_text(encoding="utf-8"))
panels = {panel["id"]: panel for panel in dashboard["panels"]}
panel = panels[11]
panel.update(
    title="Traffic heatmap · 15-minute intervals (UTC)",
    type="volkovlabs-echarts-panel",
    pluginVersion="6.6.0",
    description="Detected EKCH movements in the selected range, in UTC 15-minute intervals. Only dates and clock intervals overlapping the selection are shown; each date stays separate. Departures left (green), arrivals right (orange), with one shared intensity scale. Use the bottom slider to zoom into intervals; long date ranges have a vertical slider. Quiet elapsed intervals show zero; grey cross-date gaps are outside the range, outlines are future. Zero does not prove collector coverage. Boundary intervals are clipped to the selection.",
    gridPos={"h": 9, "w": 24, "x": 0, "y": 4},
    fieldConfig={"defaults": {"color": {"mode": "palette-classic"}}, "overrides": []},
    options={
        "renderer": "svg", "map": "none", "editorMode": "code",
        "editor": {"format": "auto"}, "themeEditor": {"name": "default", "config": "{}"},
        "getOption": (ROOT / "grafana/panels/traffic-heatmap.js").read_text(encoding="utf-8").strip(),
    },
)
panel["targets"][0]["rawSql"] = (ROOT / "grafana/queries/traffic-heatmap.sql").read_text(encoding="utf-8").strip()
panels[5]["gridPos"] = {"h": 8, "w": 24, "x": 0, "y": 13}
for panel_id, y in [(10, 21), (6, 29), (9, 29), (7, 37), (8, 37)]:
    panels[panel_id]["gridPos"]["y"] = y
dashboard["panels"] = [panels[n] for n in [1, 2, 3, 4, 11, 5, 10, 6, 9, 7, 8]]
dashboard["version"] = 4
path.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
