"""Fetch the Swiss Ephemeris files needed for Sun-through-Saturn calculations.

Files are saved locally under backend/ephe and are ignored by Git. These data
files are distributed by Astrodienst separately from the Python binding.
"""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1] / "ephe"
BASE_URL = "https://raw.githubusercontent.com/aloistr/swisseph/master/ephe"
FILES = ("sepl_18.se1", "semo_18.se1")


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for filename in FILES:
        destination = ROOT / filename
        if destination.is_file() and destination.stat().st_size:
            print(f"Already present: {destination}")
            continue
        url = f"{BASE_URL}/{filename}"
        print(f"Downloading {filename} from the Swiss Ephemeris repository")
        with urlopen(url, timeout=60) as response:
            payload = response.read()
        if not payload:
            raise RuntimeError(f"Downloaded an empty ephemeris file: {filename}")
        destination.write_bytes(payload)
        print(f"Saved {destination} ({len(payload):,} bytes)")


if __name__ == "__main__":
    main()
