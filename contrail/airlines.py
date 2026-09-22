"""Operator lookup from a flight callsign.

An airline callsign is a 3-letter ICAO airline designator followed by the flight
number (which starts with a digit): ``BAW123`` (British Airways), ``DLH3VT``
(Lufthansa), ``RYR33RN`` (Ryanair). Private / general-aviation aircraft use their
registration as the callsign instead (``N12345``, ``GABCD``), which is not an
airline code — the digit-after-the-code test filters those out.

The designator table is the full ICAO airline register (from the OpenFlights open
dataset), loaded from airlines.json; where a code has been reused, the
currently-active operator's name is kept. Anything unmatched returns "".
"""

import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "airlines.json")
try:
    with open(_PATH, encoding="utf-8") as _fh:
        AIRLINES = json.load(_fh)
except (OSError, ValueError):
    AIRLINES = {}


def operator_for_callsign(callsign):
    """Return the operating airline for a callsign, or "" if it's not a
    recognised airline designator (e.g. a private registration)."""
    if not callsign:
        return ""
    cs = str(callsign).strip().upper()
    if len(cs) >= 4 and cs[:3].isalpha() and cs[3].isdigit():
        return AIRLINES.get(cs[:3], "")
    return ""
