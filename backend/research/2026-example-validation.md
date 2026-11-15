# 2026 example validation

This is a validation note for the supplied examples, not seeded application event data. Trader-published labels and times remain source records; the calculated column uses standard aspect terminology.

## Calculation method

- Swiss Ephemeris 2.10.03 through the `pysweph` Python binding, which links the official Swiss Ephemeris C library.
- Official planetary and lunar `.se1` files in the ignored local `backend/ephe/` directory. The calculation requested `FLG_SWIEPH | FLG_SPEED`; strict Swiss-file mode was enabled and would fail if the library fell back to Moshier.
- Geocentric tropical apparent ecliptic longitudes.
- Exact crossings were bracketed at 3-hour intervals and refined with Brent's method to 0.05-second tolerance.
- Times below are Asia/Kolkata (IST). The trader's clock times are transcribed from the supplied brief and were not used as calculation inputs.

## Calendar event comparison

| Trader date | Pair | Trader label | Standard calculated aspect | Exact calculated event (IST) | Result |
|---|---|---:|---|---|---|
| 2026-05-26 | Moon–Venus | 90° | Square, 90° | 2026-05-26 12:38:24 | Same date; agrees with the earlier preliminary 12:38 |
| 2026-06-18 | Moon–Venus | 0° | Conjunction, 0° | 2026-06-18 01:58:06 | Same date; agrees with the earlier preliminary 01:58 |
| 2026-08-20 | Moon–Venus | 45° | Semi-square, 45° | 2026-08-20 09:56:26 | Same date; agrees with the earlier preliminary 09:56 |
| 2026-08-20 | Sun–Saturn | 135° | Sesquiquadrate, 135° | 2026-08-22 11:04:12 | No exact event on the trader date. Closest separation on Aug 20 was 133.521° at 23:45 IST (1.479° from exact). |
| 2026-08-24 | Moon–Venus | 90° | Square, 90° | 2026-08-24 12:00:04 | Same date; agrees with the earlier preliminary 12:00 |
| 2026-09-22 | Moon–Venus | 90° | Square, 90° | 2026-09-22 11:10:11 | Same date; agrees with the earlier preliminary 11:10 |

## Published intraday times (kept separate)

| Trader date | Published times (IST) |
|---|---|
| 2026-05-26 | 10:10, 11:20, 12:25, 13:25, 14:35 |
| 2026-06-18 | 10:15, 11:20, 12:30, 13:35, 14:40 |
| 2026-08-20 | 10:25, 11:25, 12:30, 13:35, 14:40 |
| 2026-08-24 | 09:20, 10:25, 12:25, 14:30 |
| 2026-09-22 | 09:20, 10:15, 11:20, 12:20, 13:15, 14:20 |

These lists have not been treated as astronomical events or validated as trading signals. The next research phase can compare candidate timing formulas against these source times.
