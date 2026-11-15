INSERT OR IGNORE INTO timing_methods (name, description, parameters_json)
VALUES ('session_fraction',
        'Candidate: divide the exchange session into equal time fractions; Gann-style hypothesis to test, not an assumed rule.',
        '{"session":"09:15-15:30","subdivisions":6}');
