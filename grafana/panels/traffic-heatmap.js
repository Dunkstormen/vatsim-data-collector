// Business Charts 6.6.0 Charts Function. Embedded by scripts/update_traffic_heatmap.py.
// All counts come from PostgreSQL; never invent observations for unselected/future cells.
const frame = context.panel.data.series.find(s => s.fields.some(f => f.name === 'Weekday'));
const theme = context.grafana.theme;
const dark = theme.isDark;
const text = theme.colors.text.primary;
const muted = theme.colors.text.secondary;
const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const hourLabel = n => String(n).padStart(2, '0');

if (!frame) {
  return { series: [], graphic: [{ type: 'text', left: 'center', top: 'middle',
    style: { text: 'Waiting for movement data', fill: muted, font: '13px sans-serif' } }] };
}
const fields = Object.fromEntries(frame.fields.map(f => [f.name, f.values]));
const rows = Array.from({ length: frame.length }, (_, i) => [
  Number(fields.Hour[i]), Number(fields.Weekday[i]) - 1,
  fields.Departures[i] == null ? null : Number(fields.Departures[i]),
  fields.Arrivals[i] == null ? null : Number(fields.Arrivals[i]),
  Number(fields['Selected hours'][i]), Number(fields['Elapsed hours'][i]),
]);
const totals = rows.reduce((sum, r) => [sum[0] + (r[2] ?? 0), sum[1] + (r[3] ?? 0)], [0, 0]);
// One shared scale: equal counts get equal intensity in both halves.
const maximumCount = Math.max(0, ...rows.flatMap(r => [r[2] ?? 0, r[3] ?? 0]));
const peak = Math.max(1, maximumCount);
const emptyColor = dark ? '#202830' : '#edf2f0';
const zeroColor = dark ? '#35443e' : '#dce8e2';
const base = dark ? [36, 48, 46] : [228, 239, 233];
const endpoints = dark ? [[16, 185, 129], [245, 145, 66]] : [[5, 130, 91], [183, 83, 17]];
function color(count, direction) {
  if (count == null) return emptyColor;
  if (count === 0) return zeroColor;
  const weight = 0.2 + 0.8 * count / peak;
  return 'rgb(' + base.map((value, i) => Math.round(value + (endpoints[direction][i] - value) * weight)).join(',') + ')';
}
function tooltip(params) {
  const [hour, day, departures, arrivals, selected, elapsed] = params.data;
  const heading = `${days[day]} ${hourLabel(hour)}:00–${hourLabel(hour + 1)}:00 UTC`;
  if (!selected) return `${heading}\nOutside the selected time range`;
  if (!elapsed) return `${heading}\nNot yet elapsed — no counts reported`;
  const scope = elapsed > 1 ? `\nSummed across ${elapsed} selected hourly slots` : '\nWithin the selected time range';
  const future = selected > elapsed ? `\n${selected - elapsed} future slot(s) excluded` : '';
  return `${heading}\nDepartures (left): ${departures}\nArrivals (right): ${arrivals}\nTotal: ${departures + arrivals}${scope}${future}`;
}
const badge = (label, total, direction, x, compact) => ({ id: `badge-${direction}`, type: 'text', left: x, top: 15,
  style: { text: `${label}  ${total.toLocaleString()}`, fill: color(peak, direction),
    font: `${compact ? 12 : 14}px sans-serif`, backgroundColor: dark ? '#202c2a' : '#f0f7f3',
    borderColor: color(peak, direction), borderWidth: 1, borderRadius: 6, padding: [7, 10] } });
// ECharts mutates graphic options; each responsive layout needs fresh swatches.
const key = () => Array.from({ length: 5 }, (_, i) => ({ type: 'group', x: i * 15, children: [
  { type: 'rect', shape: { x: 0, y: 0, width: 6, height: 11, r: [2, 0, 0, 2] }, style: { fill: color(peak * i / 4, 0) } },
  { type: 'rect', shape: { x: 6, y: 0, width: 6, height: 11, r: [0, 2, 2, 0] }, style: { fill: color(peak * i / 4, 1) } },
] }));

// Media options are evaluated by ECharts on resize, not only on the next data refresh.
const layout = compact => ({
  grid: { left: compact ? 42 : 62, right: compact ? 10 : 24, top: 100, bottom: compact ? 70 : 62 },
  xAxis: { axisLabel: { interval: compact ? 5 : 2, color: muted, fontSize: compact ? 9 : 11, margin: 13 } },
  yAxis: { axisLabel: { color: muted, fontSize: compact ? 10 : 12, margin: 12 } },
  graphic: { elements: [
    badge('Departures', totals[0], 0, compact ? 12 : 24, compact),
    badge('Arrivals', totals[1], 1, compact ? 166 : 202, compact),
    { id: 'subtitle', type: 'text', left: compact ? 12 : 24, top: 59,
      style: { text: compact ? 'Weekday × hour · UTC · selected range' : 'Weekday and hour of detection in UTC · selected range · repeated weekdays are summed', fill: muted, font: `${compact ? 10 : 12}px sans-serif` } },
    { id: 'help', type: 'text', left: compact ? 12 : 24, bottom: compact ? 40 : 20,
      style: { text: compact ? 'Departures left · arrivals right · hover for counts' : 'Split cells: departures left, arrivals right. Hover for exact counts. Grey = outside range; outline = future.', fill: muted, font: `${compact ? 9 : 11}px sans-serif` } },
    { id: 'scale', type: 'group', right: 24, bottom: 18, children: maximumCount ? [
      { type: 'text', x: -36, y: 0, style: { text: 'Quiet', fill: muted, font: '10px sans-serif' } },
      ...key(),
      { type: 'text', x: 80, y: 0, style: { text: `Busy (${peak})`, fill: muted, font: '10px sans-serif' } },
    ] : [{ type: 'text', style: { text: 'No recorded movements', fill: muted, font: '10px sans-serif' } }] },
  ].map(element => ({ ...element, $action: 'replace' })) },
});
const baseOption = {
  backgroundColor: 'transparent',
  animation: false,
  aria: { enabled: true, description: `Traffic heatmap in UTC. Monday through Sunday, hours 00 to 23. Departures left, arrivals right. ${totals[0]} departures and ${totals[1]} arrivals.` },
  ...layout(false),
  xAxis: { type: 'category', data: Array.from({ length: 24 }, (_, i) => hourLabel(i)), position: 'top',
    axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false }, ...layout(false).xAxis },
  yAxis: { type: 'category', data: days, inverse: true,
    axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false }, ...layout(false).yAxis },
  tooltip: { trigger: 'item', confine: true, renderMode: 'richText', formatter: tooltip,
    backgroundColor: theme.colors.background.primary, borderColor: theme.colors.border.medium,
    textStyle: { color: text, fontSize: 12 } },
  series: [{ type: 'custom', name: 'Traffic', coordinateSystem: 'cartesian2d',
    dimensions: ['Hour', 'Weekday', 'Departures', 'Arrivals', 'Selected hours', 'Elapsed hours'],
    encode: { x: 0, y: 1, tooltip: [2, 3] }, data: rows,
    renderItem: (params, api) => {
      const compact = api.getWidth() < 600;
      const center = api.coord([api.value(0), api.value(1)]);
      const size = api.size([1, 1]);
      const cellWidth = Math.max(2, Math.abs(size[0]) - (compact ? 2 : 6));
      const cellHeight = Math.max(2, Math.min(32, Math.abs(size[1]) - 6));
      const x = center[0] - cellWidth / 2, y = center[1] - cellHeight / 2;
      const row = rows[params.dataIndex];
      const future = row[4] > 0 && row[5] === 0;
      return { type: 'group', children: [0, 1].map(direction => ({
        type: 'rect', shape: { x: x + direction * cellWidth / 2, y, width: cellWidth / 2,
          height: cellHeight, r: direction ? [0, 3, 3, 0] : [3, 0, 0, 3] },
        style: { fill: color(row[direction + 2], direction), stroke: future ? muted : undefined,
          lineWidth: future ? 0.6 : 0, lineDash: future ? [2, 2] : undefined },
        emphasis: { style: { stroke: text, lineWidth: 1 } },
      })) };
    },
  }],
};
return { baseOption, media: [{ query: { maxWidth: 599 }, option: layout(true) }, { option: layout(false) }] };
