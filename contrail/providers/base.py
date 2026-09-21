"""Provider abstraction for Contrail.

A provider is anything that can deliver live ADS-B aircraft reports for a
geographic area — adsb.lol / adsb.fi / OpenSky today, but the layer and UI never
need to know which one. To add a provider, subclass :class:`AircraftProvider`,
do your I/O off the GUI thread, and emit ``aircraft_update`` with the normalised
aircraft dict below.

Normalised aircraft dict (keys a provider may emit; all optional except hex):
    hex (str)          - ICAO 24-bit address, lowercase hex — unique id
    callsign (str)     - flight/callsign, trimmed
    lat, lon (float)   - position (WGS84)
    track (float)      - true track over ground, degrees (used for rotation)
    gs (float)         - ground speed, knots
    altitude (float)   - barometric altitude, feet
    vert_rate (float)  - vertical rate, feet/min
    category (str)     - ADS-B emitter category code ("A1".."C3")
    type_desc (str)    - human aircraft type/description, if the feed has it
    squawk (str)       - transponder code
    emergency (str)    - emergency status, if reported
    on_ground (bool)   - True if the aircraft reports on the ground
    last_seen (str)    - provider timestamp, if any

The aircraft store merges reports by hex, so a provider can emit whichever
fields a given message contains.
"""

from qgis.PyQt.QtCore import QObject, pyqtSignal


class AircraftProvider(QObject):
    """Abstract live-ADS-B source. Subclasses implement start()/stop()."""

    aircraft_update = pyqtSignal(dict)  # one normalised aircraft dict per report
    status_changed = pyqtSignal(str)    # human-readable connection status
    error = pyqtSignal(str)             # human-readable error

    #: short identifier used in config/registry (e.g. "adsblol")
    id = "base"
    #: label shown in the provider dropdown
    label = "Abstract provider"
    #: one-line help / how-to shown in the configure dialog
    help_text = ""
    #: settings the provider needs, rendered by the configure dialog as fields.
    #: each is {"key", "label", "masked" (bool), "placeholder"/"default" (opt)}.
    #: an empty list means the provider needs no configuration.
    config_fields = []

    def __init__(self, settings=None, parent=None):
        """`settings` is a dict of {field key: value} gathered from
        ``config_fields`` (empty/absent for providers that need none)."""
        super().__init__(parent)
        self.settings = settings or {}

    @classmethod
    def needs_config(cls):
        return bool(cls.config_fields)

    def start(self, bboxes):
        """Begin polling for ``bboxes`` — a list of (lat_min, lon_min, lat_max,
        lon_max) tuples. Must not block the GUI thread."""
        raise NotImplementedError

    def stop(self):
        """Stop polling and release resources."""
        raise NotImplementedError

    def update_area(self, bboxes):
        """Change the tracked area on a live provider (default: no-op). Same
        bbox format as start()."""
        pass
