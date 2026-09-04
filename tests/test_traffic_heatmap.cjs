// Exercise the exact Charts Function shipped to Grafana, without browser dependencies.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const dashboard = JSON.parse(fs.readFileSync(path.join(__dirname, '../grafana/dashboards/copenhagen-live.json'), 'utf8'));
const render = new Function('context', dashboard.panels.find(p => p.id === 11).options.getOption);
function row(date, minute, departures, arrivals, elapsed = 1) {
  const start = Date.parse(date + 'T00:00:00Z') + minute * 60000;
  return [date, minute, departures, arrivals, elapsed, start, start + 900000, elapsed ? start + 900000 : null];
}
const fixture = [row('2026-09-05', 240, 4, 3), row('2026-09-05', 255, 0, 0),
  row('2026-09-05', 270, null, null, 0), row('2026-09-05', 285, null, null, 0)];
function chart(rows = fixture, width = 1200, dark = false, previous = {}) {
  const names = ['Date', 'Minute', 'Departures', 'Arrivals', 'Elapsed', 'Period start', 'Period end', 'Observed until'];
  const frame = { length: rows.length, fields: names.map((name, i) => ({ name, values: rows.map(r => r[i]) })) };
  const result = render({ panel: { data: { series: [frame] }, chart: { getWidth: () => width, getOption: () => previous } },
    grafana: { theme: { isDark: dark, colors: { text: { primary: '#111', secondary: '#777' }, background: { primary: '#fff' }, border: { medium: '#ccc' } } } } });
  return { ...(result.baseOption || result), media: result.media, testWidth: width };
}
function shapes(option, index, cellSize = [45, 80]) {
  const series = option.series[0], item = series.data[index];
  return series.renderItem({ dataIndex: index }, { value: i => item[i], coord: () => [100, 150], size: () => cellSize, getWidth: () => option.testWidth }).children;
}
test('only selected dates and 15-minute columns are rendered', () => {
  const option = chart();
  assert.deepEqual(option.yAxis.data, ['2026-09-05']);
  assert.deepEqual(option.xAxis.data, ['04:00', '04:15', '04:30', '04:45']);
  assert.equal(option.yAxis.inverse, true);
  assert.equal(option.backgroundColor, 'transparent');
  assert.equal(option.series[0].data.length, 4);
  assert.deepEqual(option.series[0].data[0].slice(0, 6), [0, 0, 4, 3, 1, 1]);
  assert.match(option.aria.description, /4 departures and 3 arrivals/);
});
test('full event has one date row and 72 cells', () => {
  const option = chart(Array.from({ length: 72 }, (_, i) => row('2026-09-05', 240 + i * 15, 1, 0)));
  assert.equal(option.yAxis.data.length, 1);
  assert.equal(option.xAxis.data.length, 72);
  assert.equal(option.xAxis.data[0], '04:00');
  assert.equal(option.xAxis.data.at(-1), '21:45');
});
test('hover shows both counts, total, and exact clipped interval', () => {
  const clipped = row('2026-09-05', 240, 4, 3);
  clipped[5] += 120000;
  clipped[6] -= 180000;
  clipped[7] = clipped[6];
  const option = chart([clipped]);
  const tooltip = option.tooltip.formatter({ data: option.series[0].data[0] });
  assert.match(tooltip, /2026-09-05 04:02–04:12 UTC/);
  assert.match(tooltip, /Departures \(left\): 4/);
  assert.match(tooltip, /Arrivals \(right\): 3/);
  assert.match(tooltip, /Total: 7/);
  assert.equal(option.tooltip.renderMode, 'richText');
});
test('future cells differ from elapsed zero cells', () => {
  const option = chart();
  assert.match(option.tooltip.formatter({ data: option.series[0].data[2] }), /Not yet elapsed/);
  assert.match(option.tooltip.formatter({ data: option.series[0].data[1] }), /Total: 0/);
  assert.equal(shapes(option, 2)[0].style.lineWidth, 0.6);
  assert.notEqual(shapes(option, 1)[0].style.fill, shapes(option, 2)[0].style.fill);
});
test('two adjacent half cells use different direction colors', () => {
  const halves = shapes(chart(), 0);
  assert.equal(halves.length, 2);
  assert.equal(halves[0].shape.x + halves[0].shape.width, halves[1].shape.x);
  assert.equal(halves[0].shape.width, halves[1].shape.width);
  assert.notEqual(halves[0].style.fill, halves[1].style.fill);
});
test('compact and dark-theme cells keep positive sizes and independent graphics', () => {
  for (const width of [375, 1200]) for (const dark of [false, true]) {
    for (const cell of shapes(chart(fixture, width, dark), 0, [3, 20])) {
      assert.ok(cell.shape.width > 0);
      assert.ok(cell.shape.height > 0);
    }
  }
  const option = chart();
  assert.equal(option.media[0].query.maxWidth, 599);
  assert.notEqual(option.graphic.elements[4].children[1], option.media[0].option.graphic.elements[4].children[1]);
});
test('empty elapsed range and empty selection are handled', () => {
  const option = chart([row('2026-09-05', 240, 0, 0)]);
  assert.match(option.aria.description, /0 departures and 0 arrivals/);
  assert.ok(!JSON.stringify(option).includes('NaN'));
  assert.match(JSON.stringify(option.graphic), /No recorded movements/);
  assert.match(JSON.stringify(chart([]).graphic), /No intervals in the selected range/);
});
test('different dates remain separate and cross-midnight gaps stay unselected', () => {
  const option = chart([row('2026-09-05', 1425, 4, 0), row('2026-09-06', 0, 0, 3)]);
  assert.deepEqual(option.yAxis.data, ['2026-09-05', '2026-09-06']);
  assert.deepEqual(option.xAxis.data, ['00:00', '23:45']);
  assert.match(option.tooltip.formatter({ data: option.series[0].data[0] }), /Outside the selected time range/);
  assert.match(option.tooltip.formatter({ data: option.series[0].data[1] }), /2026-09-05 23:45–2026-09-06 00:00 UTC/);
  const saturdays = chart([row('2026-09-05', 240, 1, 0), row('2026-09-12', 240, 2, 0)]);
  assert.equal(saturdays.yAxis.data.length, 2);
  assert.deepEqual(saturdays.series[0].data.map(r => r[2]), [1, 2]);
});
test('current interval tooltip explains observation cutoff', () => {
  const partial = row('2026-09-05', 240, 1, 1);
  partial[7] -= 300000;
  const option = chart([partial]);
  assert.match(option.tooltip.formatter({ data: option.series[0].data[0] }), /Counts through 2026-09-05 04:10 UTC/);
});
test('zoom survives refresh but resets when the selected axes change', () => {
  const first = chart();
  const previous = { xAxis: [{ data: first.xAxis.data }], yAxis: [{ data: first.yAxis.data }],
    dataZoom: [{ start: 25, end: 75 }, { start: 0, end: 100 }] };
  assert.equal(chart(fixture, 1200, false, previous).dataZoom[0].start, 25);
  assert.equal(chart([row('2026-09-06', 240, 0, 0)], 1200, false, previous).dataZoom[0].start, 0);
  const multi = chart(Array.from({ length: 10 }, (_, i) => row('2026-09-' + String(i + 1).padStart(2, '0'), 240, 0, 0)));
  assert.equal(multi.dataZoom[1].show, true);
  assert.ok(multi.dataZoom[1].end < 100);
});
