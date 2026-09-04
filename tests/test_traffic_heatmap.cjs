// Exercise the exact Charts Function shipped to Grafana, without browser dependencies.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const dashboard = JSON.parse(fs.readFileSync(path.join(__dirname, '../grafana/dashboards/copenhagen-live.json'), 'utf8'));
const render = new Function('context', dashboard.panels.find(p => p.id === 11).options.getOption);
const fixture = Array.from({ length: 168 }, (_, i) => [Math.floor(i / 24) + 1, i % 24, null, null, 0, 0]);
fixture[5 * 24 + 4] = [6, 4, 4, 3, 1, 1];
fixture[5 * 24 + 5] = [6, 5, 0, 0, 1, 1];
fixture[5 * 24 + 6] = [6, 6, null, null, 1, 0];
function chart(rows = fixture, width = 1200, dark = false) {
  const names = ['Weekday', 'Hour', 'Departures', 'Arrivals', 'Selected hours', 'Elapsed hours'];
  const frame = { length: rows.length, fields: names.map((name, i) => ({ name, values: rows.map(r => r[i]) })) };
  const result = render({ panel: { data: { series: [frame] }, chart: { getWidth: () => width } },
    grafana: { theme: { isDark: dark, colors: { text: { primary: '#111', secondary: '#777' }, background: { primary: '#fff' }, border: { medium: '#ccc' } } } } });
  return { ...result.baseOption, media: result.media, testWidth: width };
}
function shapes(option, index, cellSize = [45, 40]) {
  const series = option.series[0], row = series.data[index];
  return series.renderItem({ dataIndex: index }, { value: i => row[i], coord: () => [100, 150], size: () => cellSize, getWidth: () => option.testWidth }).children;
}
test('complete 7 by 24 grid and correct UTC directions', () => {
  const option = chart();
  assert.deepEqual(option.yAxis.data, ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']);
  assert.equal(option.yAxis.inverse, true);
  assert.equal(option.xAxis.data.length, 24);
  assert.equal(option.backgroundColor, 'transparent');
  assert.equal(option.series[0].data.length, 168);
  assert.deepEqual(option.series[0].data[124], [4, 5, 4, 3, 1, 1]);
  assert.match(option.aria.description, /4 departures and 3 arrivals/);
});
test('hover shows both counts, total, and hour', () => {
  const option = chart();
  const tooltip = option.tooltip.formatter({ data: option.series[0].data[124] });
  assert.match(tooltip, /Sat 04:00–05:00 UTC/);
  assert.match(tooltip, /Departures \(left\): 4/);
  assert.match(tooltip, /Arrivals \(right\): 3/);
  assert.match(tooltip, /Total: 7/);
  assert.equal(option.tooltip.renderMode, 'richText');
});
test('outside, future, and elapsed zero cells remain distinct', () => {
  const option = chart();
  assert.match(option.tooltip.formatter({ data: option.series[0].data[0] }), /Outside/);
  assert.match(option.tooltip.formatter({ data: option.series[0].data[126] }), /Not yet elapsed/);
  assert.match(option.tooltip.formatter({ data: option.series[0].data[125] }), /Total: 0/);
  assert.equal(shapes(option, 126)[0].style.lineWidth, 0.6);
  assert.notEqual(shapes(option, 0)[0].style.fill, shapes(option, 125)[0].style.fill);
});
test('two adjacent half cells use different direction colors', () => {
  const halves = shapes(chart(), 124);
  assert.equal(halves.length, 2);
  assert.equal(halves[0].shape.x + halves[0].shape.width, halves[1].shape.x);
  assert.equal(halves[0].shape.width, halves[1].shape.width);
  assert.notEqual(halves[0].style.fill, halves[1].style.fill);
});
test('compact and dark-theme cells keep positive sizes', () => {
  for (const width of [375, 1200]) for (const dark of [false, true]) {
    const option = chart(fixture, width, dark);
    for (const cell of shapes(option, 124, [12, 20])) {
      assert.ok(cell.shape.width > 0);
      assert.ok(cell.shape.height > 0);
    }
  }
  assert.equal(chart().media[0].query.maxWidth, 599);
  assert.equal(chart().media[0].option.xAxis.axisLabel.interval, 5);
  assert.equal(chart().media[1].option.xAxis.axisLabel.interval, 2);
  const option = chart();
  assert.notEqual(option.graphic.elements[4].children[1], option.media[0].option.graphic.elements[4].children[1]);
});
test('empty elapsed range renders zeros without invalid scale values', () => {
  const rows = fixture.map(r => [r[0], r[1], 0, 0, 1, 1]);
  const option = chart(rows);
  assert.match(option.aria.description, /0 departures and 0 arrivals/);
  assert.ok(!JSON.stringify(option).includes('NaN'));
  assert.match(JSON.stringify(option.graphic), /No recorded movements/);
});
test('repeated weekdays state aggregation and exclude future slots', () => {
  const option = chart();
  const tooltip = option.tooltip.formatter({ data: [4, 5, 4, 3, 3, 2] });
  assert.match(tooltip, /Summed across 2 selected hourly slots/);
  assert.match(tooltip, /1 future slot\(s\) excluded/);
});
