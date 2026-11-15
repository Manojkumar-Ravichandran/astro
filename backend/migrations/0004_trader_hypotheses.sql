CREATE UNIQUE INDEX IF NOT EXISTS idx_trader_rule_source_title
    ON trader_rules(source_document_id, title);

INSERT INTO trader_rules (title, hypothesis_text, status, source_document_id)
SELECT seed.title, seed.hypothesis_text, 'hypothesis',
       (SELECT id FROM source_documents WHERE title='Trader calendar examples from user-provided brief' ORDER BY id LIMIT 1)
FROM (
    SELECT 'Moon × Venus Square (90°)' AS title,
           'Trader-reported hypothesis: the first 15 minutes may produce fake movements; the market may reverse in the opposite direction; another reversal may follow after approximately one hour; a 5-minute range breakout is used for confirmation.' AS hypothesis_text
    UNION ALL SELECT 'Moon × Venus Conjunction (0°)',
           'Trader-reported hypothesis: one side may make a sharp move; the opposite side may make the real move; a sideways period may occur; further sharp movements may follow.'
    UNION ALL SELECT 'Moon × Venus Semi-square (45°) + Sun × Saturn Sesquiquadrate (135°)',
           'Trader-reported hypothesis: the first movement may be a trap; short covering may start in the morning; candles may subsequently shrink.'
) AS seed
WHERE NOT EXISTS (
    SELECT 1 FROM trader_rules existing
    WHERE existing.title=seed.title
      AND existing.source_document_id=(SELECT id FROM source_documents WHERE title='Trader calendar examples from user-provided brief' ORDER BY id LIMIT 1)
);

INSERT OR IGNORE INTO rule_aspects (rule_id, planet_1, planet_2, aspect_angle_degrees)
SELECT rule.id, 'Moon', 'Venus', 90
FROM trader_rules rule WHERE rule.title='Moon × Venus Square (90°)';

INSERT OR IGNORE INTO rule_aspects (rule_id, planet_1, planet_2, aspect_angle_degrees)
SELECT rule.id, 'Moon', 'Venus', 0
FROM trader_rules rule WHERE rule.title='Moon × Venus Conjunction (0°)';

INSERT OR IGNORE INTO rule_aspects (rule_id, planet_1, planet_2, aspect_angle_degrees)
SELECT rule.id, 'Moon', 'Venus', 45
FROM trader_rules rule WHERE rule.title='Moon × Venus Semi-square (45°) + Sun × Saturn Sesquiquadrate (135°)'
UNION ALL
SELECT rule.id, 'Sun', 'Saturn', 135
FROM trader_rules rule WHERE rule.title='Moon × Venus Semi-square (45°) + Sun × Saturn Sesquiquadrate (135°)';
