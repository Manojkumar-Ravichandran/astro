PRAGMA foreign_keys = ON;

CREATE UNIQUE INDEX IF NOT EXISTS idx_published_event_source_unique
    ON published_events(source_document_id, event_date, planet_1, planet_2, source_angle_degrees, source_locator);
CREATE UNIQUE INDEX IF NOT EXISTS idx_published_time_source_unique
    ON published_times(published_event_id, local_time, timezone);

INSERT INTO source_documents (title, source_name, notes)
SELECT 'Trader calendar examples from user-provided brief', 'User-provided pasted brief',
       'Only the dates, labels and clock times explicitly present in the brief are included. Original image references and publication dates were not supplied.'
WHERE NOT EXISTS (SELECT 1 FROM source_documents WHERE title='Trader calendar examples from user-provided brief');

INSERT OR IGNORE INTO published_events
    (source_document_id, event_date, planet_1, planet_2, source_aspect_label, source_angle_degrees, source_locator)
SELECT (SELECT id FROM source_documents WHERE title='Trader calendar examples from user-provided brief' ORDER BY id LIMIT 1),
       seed.event_date, seed.planet_1, seed.planet_2, seed.label, seed.angle, seed.locator
FROM (
    SELECT '2026-05-26' AS event_date, 'Moon' AS planet_1, 'Venus' AS planet_2, '90°' AS label, 90.0 AS angle, 'pasted-brief:2026-05-26:moon-venus' AS locator
    UNION ALL SELECT '2026-06-18', 'Moon', 'Venus', '0°', 0.0, 'pasted-brief:2026-06-18:moon-venus'
    UNION ALL SELECT '2026-08-20', 'Moon', 'Venus', '45°', 45.0, 'pasted-brief:2026-08-20:moon-venus'
    UNION ALL SELECT '2026-08-20', 'Sun', 'Saturn', '135°', 135.0, 'pasted-brief:2026-08-20:sun-saturn'
    UNION ALL SELECT '2026-08-24', 'Moon', 'Venus', '90°', 90.0, 'pasted-brief:2026-08-24:moon-venus'
    UNION ALL SELECT '2026-09-22', 'Moon', 'Venus', '90°', 90.0, 'pasted-brief:2026-09-22:moon-venus'
) AS seed
WHERE NOT EXISTS (SELECT 1 FROM published_events existing WHERE existing.source_locator=seed.locator);

INSERT OR IGNORE INTO published_times (published_event_id, local_time, timezone, source_locator)
SELECT event.id, seed.local_time, 'Asia/Kolkata', seed.locator
FROM (
    SELECT 'pasted-brief:2026-05-26:moon-venus' AS event_locator, '10:10' AS local_time, 'pasted-brief:2026-05-26:time:10:10' AS locator
    UNION ALL SELECT 'pasted-brief:2026-05-26:moon-venus', '11:20', 'pasted-brief:2026-05-26:time:11:20'
    UNION ALL SELECT 'pasted-brief:2026-05-26:moon-venus', '12:25', 'pasted-brief:2026-05-26:time:12:25'
    UNION ALL SELECT 'pasted-brief:2026-05-26:moon-venus', '13:25', 'pasted-brief:2026-05-26:time:13:25'
    UNION ALL SELECT 'pasted-brief:2026-05-26:moon-venus', '14:35', 'pasted-brief:2026-05-26:time:14:35'
    UNION ALL SELECT 'pasted-brief:2026-06-18:moon-venus', '10:15', 'pasted-brief:2026-06-18:time:10:15'
    UNION ALL SELECT 'pasted-brief:2026-06-18:moon-venus', '11:20', 'pasted-brief:2026-06-18:time:11:20'
    UNION ALL SELECT 'pasted-brief:2026-06-18:moon-venus', '12:30', 'pasted-brief:2026-06-18:time:12:30'
    UNION ALL SELECT 'pasted-brief:2026-06-18:moon-venus', '13:35', 'pasted-brief:2026-06-18:time:13:35'
    UNION ALL SELECT 'pasted-brief:2026-06-18:moon-venus', '14:40', 'pasted-brief:2026-06-18:time:14:40'
    UNION ALL SELECT 'pasted-brief:2026-08-20:moon-venus', '10:25', 'pasted-brief:2026-08-20:time:10:25'
    UNION ALL SELECT 'pasted-brief:2026-08-20:moon-venus', '11:25', 'pasted-brief:2026-08-20:time:11:25'
    UNION ALL SELECT 'pasted-brief:2026-08-20:moon-venus', '12:30', 'pasted-brief:2026-08-20:time:12:30'
    UNION ALL SELECT 'pasted-brief:2026-08-20:moon-venus', '13:35', 'pasted-brief:2026-08-20:time:13:35'
    UNION ALL SELECT 'pasted-brief:2026-08-20:moon-venus', '14:40', 'pasted-brief:2026-08-20:time:14:40'
    UNION ALL SELECT 'pasted-brief:2026-08-24:moon-venus', '09:20', 'pasted-brief:2026-08-24:time:09:20'
    UNION ALL SELECT 'pasted-brief:2026-08-24:moon-venus', '10:25', 'pasted-brief:2026-08-24:time:10:25'
    UNION ALL SELECT 'pasted-brief:2026-08-24:moon-venus', '12:25', 'pasted-brief:2026-08-24:time:12:25'
    UNION ALL SELECT 'pasted-brief:2026-08-24:moon-venus', '14:30', 'pasted-brief:2026-08-24:time:14:30'
    UNION ALL SELECT 'pasted-brief:2026-09-22:moon-venus', '09:20', 'pasted-brief:2026-09-22:time:09:20'
    UNION ALL SELECT 'pasted-brief:2026-09-22:moon-venus', '10:15', 'pasted-brief:2026-09-22:time:10:15'
    UNION ALL SELECT 'pasted-brief:2026-09-22:moon-venus', '11:20', 'pasted-brief:2026-09-22:time:11:20'
    UNION ALL SELECT 'pasted-brief:2026-09-22:moon-venus', '12:20', 'pasted-brief:2026-09-22:time:12:20'
    UNION ALL SELECT 'pasted-brief:2026-09-22:moon-venus', '13:15', 'pasted-brief:2026-09-22:time:13:15'
    UNION ALL SELECT 'pasted-brief:2026-09-22:moon-venus', '14:20', 'pasted-brief:2026-09-22:time:14:20'
) AS seed
JOIN published_events event ON event.source_locator=seed.event_locator
WHERE NOT EXISTS (SELECT 1 FROM published_times existing WHERE existing.source_locator=seed.locator);

INSERT OR IGNORE INTO timing_methods (name, description, parameters_json)
VALUES
    ('session_open_interval', 'Candidate: repeat at a fixed interval anchored to NSE session open.', '{"anchor":"09:15","interval_minutes":65}'),
    ('aspect_time_interval', 'Candidate: repeat at a fixed interval from an exact planetary event time.', '{"anchor":"exact_aspect_time","interval_minutes":65}'),
    ('best_fit_repeating_interval', 'Candidate: search a configurable interval range for the lowest timing error.', '{"minimum_interval_minutes":50,"maximum_interval_minutes":90}');
