WITH bounds AS (
  SELECT $__timeFrom()::timestamptz AS range_start,
         $__timeTo()::timestamptz AS range_end,
         LEAST($__timeTo()::timestamptz, now()) AS elapsed_end
), periods AS (
  SELECT bucket, GREATEST(bucket, b.range_start) AS period_start,
         LEAST(bucket + interval '15 minutes', b.range_end) AS period_end,
         b.elapsed_end
  FROM bounds b
  CROSS JOIN LATERAL generate_series(
    date_bin(interval '15 minutes', b.range_start, timestamptz '1970-01-01 00:00Z'),
    b.range_end - interval '1 microsecond', interval '15 minutes'
  ) AS bucket
  WHERE b.range_end > b.range_start
), counts AS (
  SELECT date_bin(interval '15 minutes', e.event_at, timestamptz '1970-01-01 00:00Z') AS bucket,
         count(*) FILTER (WHERE e.event_type = 'departure') AS departures,
         count(*) FILTER (WHERE e.event_type = 'arrival') AS arrivals
  FROM flight_events e CROSS JOIN bounds b
  WHERE e.airport = 'EKCH'
    AND e.event_at >= b.range_start AND e.event_at < b.elapsed_end
  GROUP BY 1
)
SELECT to_char(p.bucket AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS "Date",
       (extract(hour FROM p.bucket AT TIME ZONE 'UTC') * 60 +
        extract(minute FROM p.bucket AT TIME ZONE 'UTC'))::integer AS "Minute",
       CASE WHEN p.period_start < p.elapsed_end THEN COALESCE(c.departures, 0) END AS "Departures",
       CASE WHEN p.period_start < p.elapsed_end THEN COALESCE(c.arrivals, 0) END AS "Arrivals",
       (p.period_start < p.elapsed_end)::integer AS "Elapsed",
       (extract(epoch FROM p.period_start) * 1000)::double precision AS "Period start",
       (extract(epoch FROM p.period_end) * 1000)::double precision AS "Period end",
       CASE WHEN p.period_start < p.elapsed_end THEN
         (extract(epoch FROM LEAST(p.period_end, p.elapsed_end)) * 1000)::double precision
       END AS "Observed until"
FROM periods p LEFT JOIN counts c USING (bucket)
ORDER BY p.bucket
