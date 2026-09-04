WITH bounds AS (
  SELECT $__timeFrom()::timestamptz AS range_start,
         $__timeTo()::timestamptz AS range_end,
         LEAST($__timeTo()::timestamptz, now()) AS elapsed_end
), selected_hours AS (
  SELECT extract(isodow FROM slot AT TIME ZONE 'UTC')::integer AS weekday,
         extract(hour FROM slot AT TIME ZONE 'UTC')::integer AS hour,
         count(*) AS selected_hours,
         count(*) FILTER (WHERE GREATEST(slot, b.range_start) < b.elapsed_end) AS elapsed_hours
  FROM bounds b
  CROSS JOIN LATERAL generate_series(
    date_trunc('hour', b.range_start AT TIME ZONE 'UTC') AT TIME ZONE 'UTC',
    b.range_end - interval '1 microsecond', interval '1 hour'
  ) AS slot
  WHERE b.range_end > b.range_start
  GROUP BY 1, 2
), counts AS (
  SELECT extract(isodow FROM e.event_at AT TIME ZONE 'UTC')::integer AS weekday,
         extract(hour FROM e.event_at AT TIME ZONE 'UTC')::integer AS hour,
         count(*) FILTER (WHERE e.event_type = 'departure') AS departures,
         count(*) FILTER (WHERE e.event_type = 'arrival') AS arrivals
  FROM flight_events e CROSS JOIN bounds b
  WHERE e.airport = 'EKCH'
    AND e.event_at >= b.range_start AND e.event_at < b.elapsed_end
  GROUP BY 1, 2
)
SELECT d.weekday AS "Weekday", h.hour AS "Hour",
       CASE WHEN s.elapsed_hours > 0 THEN COALESCE(c.departures, 0) END AS "Departures",
       CASE WHEN s.elapsed_hours > 0 THEN COALESCE(c.arrivals, 0) END AS "Arrivals",
       COALESCE(s.selected_hours, 0) AS "Selected hours",
       COALESCE(s.elapsed_hours, 0) AS "Elapsed hours"
FROM generate_series(1, 7) AS d(weekday)
CROSS JOIN generate_series(0, 23) AS h(hour)
LEFT JOIN selected_hours s USING (weekday, hour)
LEFT JOIN counts c USING (weekday, hour)
ORDER BY d.weekday, h.hour
