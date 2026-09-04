// Business Charts 6.6.0 Charts Function. Embedded by scripts/update_traffic_heatmap.py.
// All counts come from PostgreSQL; never invent observations for unselected/future cells.
const frame = context.panel.data.series.find(s => s.fields.some(f => f.name === 'Date'));
const theme = context.grafana.theme;
const dark = theme.isDark;
const text = theme.colors.text.primary;
const muted = theme.colors.text.secondary;
const pad = n => String(n).padStart(2, '0');
const clockLabel = minute => `${pad(Math.floor(minute / 60))}:${pad(minute % 60)}`;
const stamp = ms => new Date(ms).toISOString().slice(0, 19).replace('T', ' ').replace(/:00$/, '');

if (!frame || !frame.length) {
  return { series: [], graphic: [{ type: 'text', left: 'center', top: 'middle',
    style: { text: frame ? 'No intervals in the selected range' : 'Waiting for movement data', fill: muted, font: '13px sans-serif' } }] };
}
const fields = Object.fromEntries(frame.fields.map(f => [f.name, f.values]));
const dates = [...new Set(fields.Date)].sort();
const minutes = [...new Set(Array.from(fields.Minute, Number))].sort((a, b) => a - b);
const timeLabels = minutes.map(clockLabel);
const source = new Map(Array.from({ length: frame.length }, (_, i) => [`${fields.Date[i]}|${fields.Minute[i]}`, i]));
// Cross-date alignment gaps are grey; they are not counted as observations.
const rows = dates.flatMap((date, day) => minutes.map((minute, column) => {
  const i = source.get(`${date}|${minute}`);
  if (i === undefined) return [column, day, null, null, 0, 0, null, null, null];
  return [column, day,
    fields.Departures[i] == null ? null : Number(fields.Departures[i]),
    fields.Arrivals[i] == null ? null : Number(fields.Arrivals[i]),
    1, Number(fields.Elapsed[i]), Number(fields['Period start'][i]), Number(fields['Period end'][i]),
    fields['Observed until'][i] == null ? null : Number(fields['Observed until'][i])];
}));
const totals = rows.reduce((sum, r) => [sum[0] + (r[2] ?? 0), sum[1] + (r[3] ?? 0)], [0, 0]);
// One shared scale: equal counts get equal intensity in both halves.
const maximumCount = rows.reduce((max, r) => Math.max(max, r[2] ?? 0, r[3] ?? 0), 0);
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
  const [column, day, departures, arrivals, selected, elapsed, start, end, observed] = params.data;
  if (!selected) return `${dates[day]} ${timeLabels[column]} UTC\nOutside the selected time range`;
  const endText = stamp(end), heading = `${stamp(start)}–${endText.slice(0, 10) === dates[day] ? endText.slice(11) : endText} UTC`;
  if (!elapsed) return `${heading}\nNot yet elapsed — no counts reported`;
  const partial = observed < end ? `\nCounts through ${stamp(observed)} UTC` : '';
  return `${heading}\nDepartures (left): ${departures}\nArrivals (right): ${arrivals}\nTotal: ${departures + arrivals}\nWithin the selected time range${partial}`;
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
  grid: { left: compact ? 80 : 96, right: 30, top: 96, bottom: 98 },
  xAxis: { axisLabel: { interval: 'auto', hideOverlap: true, color: muted, fontSize: compact ? 9 : 11, margin: 13 } },
  yAxis: { axisLabel: { interval: 0, color: muted, fontSize: compact ? 9 : 11, margin: 12 } },
  graphic: { elements: [
    badge('Departures', totals[0], 0, compact ? 12 : 24, compact),
    badge('Arrivals', totals[1], 1, compact ? 166 : 202, compact),
    { id: 'subtitle', type: 'text', left: compact ? 12 : 24, top: 59,
      style: { text: compact ? 'Selected dates · 15-minute intervals · UTC' : 'Selected dates only · 15-minute intervals in UTC · drag the slider to zoom', fill: muted, font: `${compact ? 10 : 12}px sans-serif` } },
    { id: 'help', type: 'text', left: compact ? 12 : 24, bottom: 40,
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
  aria: { enabled: true, description: `Traffic heatmap in UTC. Selected dates ${dates.join(', ')} in 15-minute intervals. Departures left, arrivals right. ${totals[0]} departures and ${totals[1]} arrivals.` },
  ...layout(false),
  xAxis: { type: 'category', data: timeLabels, position: 'top',
    axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false }, ...layout(false).xAxis },
  yAxis: { type: 'category', data: dates, inverse: true,
    axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false }, ...layout(false).yAxis },
  tooltip: { trigger: 'item', confine: true, renderMode: 'richText', formatter: tooltip,
    backgroundColor: theme.colors.background.primary, borderColor: theme.colors.border.medium,
    textStyle: { color: text, fontSize: 12 } },
  series: [{ type: 'custom', name: 'Traffic', coordinateSystem: 'cartesian2d', clip: true,
    dimensions: ['Interval', 'Date', 'Departures', 'Arrivals', 'Selected', 'Elapsed', 'Start', 'End', 'Observed until'],
    encode: { x: 0, y: 1, tooltip: [2, 3] }, data: rows,
    renderItem: (params, api) => {
      const center = api.coord([api.value(0), api.value(1)]);
      const size = api.size([1, 1]);
      const cellWidth = Math.max(1, Math.abs(size[0]) * 0.85);
      const cellHeight = Math.max(2, Math.min(64, Math.abs(size[1]) - 6));
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
// Retain a user's zoom across 15-second refreshes when the selected axes are unchanged.
const previous = context.panel.chart.getOption?.() || {};
const sameAxes = JSON.stringify(previous.xAxis?.[0]?.data) === JSON.stringify(timeLabels) &&
  JSON.stringify(previous.yAxis?.[0]?.data) === JSON.stringify(dates);
const zoom = (index, fallbackEnd) => sameAxes && previous.dataZoom?.[index]
  ? { start: previous.dataZoom[index].start, end: previous.dataZoom[index].end }
  : { start: 0, end: fallbackEnd };
baseOption.dataZoom = [
  { id: 'time-zoom', type: 'slider', xAxisIndex: 0, filterMode: 'none', left: 96, right: 30,
    bottom: 66, height: 16, showDetail: false, showDataShadow: false, brushSelect: false,
    ...zoom(0, 100) },
  { id: 'date-zoom', type: 'slider', yAxisIndex: 0, orient: 'vertical', filterMode: 'none',
    right: 5, top: 96, bottom: 98, width: 12, show: dates.length > 3,
    showDetail: false, showDataShadow: false, brushSelect: false,
    ...zoom(1, dates.length > 3 ? 200 / (dates.length - 1) : 100) },
];
return { baseOption, media: [{ query: { maxWidth: 599 }, option: layout(true) }, { option: layout(false) }] };
