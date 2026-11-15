# Swiss Ephemeris licensing decision

This is a private local-use project. No distribution or public service is being prepared, so no license selection is required for the current milestone. If the app is later distributed or used to activate a public service, the developer must first choose and comply with one of Swiss Ephemeris's dual-license options: AGPL or its Professional License. The maintained `pysweph` binding is derived from `pyswisseph` and Swiss Ephemeris; review its bundled notices together with Swiss Ephemeris terms before any such future use.

Official references:

- [Swiss Ephemeris licensing information](https://www.astro.com/swisseph/swephinfo_e.htm)
- [Swiss Ephemeris programming manual](https://www.astro.com/swisseph/swephprg.htm)
- [pyswisseph source project](https://github.com/astrorigin/pyswisseph)
- [pysweph continuation and migration notes](https://pypi.org/project/pysweph/)

The calculation code requests `FLG_SWIEPH` and, by default, refuses results if the library reports fallback to Moshier. Set the ephemeris data directory explicitly in `CalculationConfig`; do not treat successful import of the Python binding as proof that Swiss ephemeris files were used.
