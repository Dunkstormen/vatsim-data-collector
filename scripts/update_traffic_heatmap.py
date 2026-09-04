"""Embed the heatmap SQL and Charts Function into the provisioned dashboard."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "grafana/dashboards/copenhagen-live.json"
dashboard = json.loads(path.read_text(encoding="utf-8"))
panels = {panel["id"]: panel for panel in dashboard["panels"]}
panel = panels[11]
panel.update(
    title="Traffic heatmap · weekday and hour (UTC)",
    type="volkovlabs-echarts-panel",
    pluginVersion="6.6.0",
    description="Detected EKCH movements in the selected range. Monday–Sunday rows and UTC hour columns; departures left (green), arrivals right (orange). Repeated weekday/hour slots are summed. One shared intensity scale for both directions. Elapsed hours without recorded events show zero; grey cells are outside the range, outlined cells are future. Zero does not prove collector coverage. Partial hours include only events inside the selection.",
    gridPos={"h": 11, "w": 24, "x": 0, "y": 4},
    fieldConfig={"defaults": {"color": {"mode": "palette-classic"}}, "overrides": []},
    options={
        "renderer": "svg", "map": "none", "editorMode": "code",
        "editor": {"format": "auto"}, "themeEditor": {"name": "default", "config": "{}"},
        "getOption": (ROOT / "grafana/panels/traffic-heatmap.js").read_text(encoding="utf-8").strip(),
    },
)
panel["targets"][0]["rawSql"] = (ROOT / "grafana/queries/traffic-heatmap.sql").read_text(encoding="utf-8").strip()
panels[5]["gridPos"] = {"h": 8, "w": 24, "x": 0, "y": 15}
for panel_id, y in [(10, 23), (6, 31), (9, 31), (7, 39), (8, 39)]:
    panels[panel_id]["gridPos"]["y"] = y
dashboard["panels"] = [panels[n] for n in [1, 2, 3, 4, 11, 5, 10, 6, 9, 7, 8]]
dashboard["version"] = 3
path.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
