"""adsb.lol / adsb.fi providers — keyless live ADS-B over HTTP.

Both serve the readsb/tar1090 aircraft JSON via a point+radius query
(``/v2/lat/{lat}/lon/{lon}/dist/{nm}``, max 250 nm). We poll, converting the
map's bounding box to a centre + radius, and normalise each aircraft to the
base-class contract. Keyless — no account needed. Uses QGIS's own network
manager (async, non-blocking), exactly like the Digitraffic provider in Wake.
"""

import json
import math

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl, QTimer
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

from .base import AircraftProvider
from .._debug import dbg

POLL_MS = 5000
MAX_NM = 250               # adsb.lol / adsb.fi max search radius
USER_AGENT = "ContrailQGIS/0.1 (QGIS plugin)"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _bbox_to_point_radius(bbox):
    """(lat_min, lon_min, lat_max, lon_max) -> (centre_lat, centre_lon, nm)
    covering the box (1 deg latitude ~= 60 nm; longitude scaled by cos lat)."""
    lat_min, lon_min, lat_max, lon_max = bbox
    clat = (lat_min + lat_max) / 2.0
    clon = (lon_min + lon_max) / 2.0
    dlat = (lat_max - lat_min) / 2.0
    dlon = (lon_max - lon_min) / 2.0 * math.cos(math.radians(clat))
    nm = math.sqrt(dlat * dlat + dlon * dlon) * 60.0
    return clat, clon, max(1, min(MAX_NM, int(math.ceil(nm))))


def _normalise(a):
    hexid = (a.get("hex") or "").strip().lower()
    if not hexid:
        return None
    alt = a.get("alt_baro")
    on_ground = (alt == "ground")
    return {
        "hex": hexid,
        "callsign": (a.get("flight") or "").strip(),
        "lat": _num(a.get("lat")),
        "lon": _num(a.get("lon")),
        "track": _num(a.get("track") if a.get("track") is not None else a.get("dir")),
        "gs": _num(a.get("gs")),
        "altitude": None if on_ground else _num(alt),
        "vert_rate": _num(a.get("baro_rate") if a.get("baro_rate") is not None
                          else a.get("geom_rate")),
        "category": (a.get("category") or "").strip(),
        "type_desc": (a.get("desc") or a.get("t") or "").strip(),
        "squawk": (a.get("squawk") or "").strip(),
        "emergency": (a.get("emergency") or "").strip(),
        "on_ground": on_ground,
    }


class AdsbJsonProvider(AircraftProvider):
    """Shared logic for readsb/tar1090 point-radius JSON feeds. Subclasses set
    ``base_url`` (ending at the ``/v2`` prefix)."""

    base_url = ""

    def __init__(self, settings=None, parent=None):
        super().__init__(settings, parent)
        self._bbox = None
        self._want = False
        self._nam = QgsNetworkAccessManager.instance()
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)

    def start(self, bboxes):
        self._bbox = bboxes[0] if bboxes else None
        self._want = True
        self.status_changed.emit("Connecting…")
        dbg(f"Polling {self.label}")
        self._fetch()
        self._timer.start()

    def stop(self):
        self._want = False
        self._timer.stop()

    def update_area(self, bboxes):
        self._bbox = bboxes[0] if bboxes else None

    def _poll(self):
        if self._want:
            self._fetch()

    def _fetch(self):
        if not self._bbox:
            return
        clat, clon, nm = _bbox_to_point_radius(self._bbox)
        url = f"{self.base_url}/lat/{clat:.4f}/lon/{clon:.4f}/dist/{nm}"
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", USER_AGENT.encode())
        req.setRawHeader(b"Accept", b"application/json")
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._on_reply(reply))

    def _on_reply(self, reply):
        reply.deleteLater()
        if not self._want:
            return
        # reply.error() is an enum member that is truthy even for NoError (0),
        # so compare explicitly.
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.error.emit(f"{self.label} unreachable ({reply.errorString()}).")
            return
        try:
            data = json.loads(bytes(reply.readAll()))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"{self.label} returned bad JSON: {exc}")
            return
        ac = data.get("ac") or data.get("aircraft") or []
        for a in ac:
            rec = _normalise(a)
            if rec:
                self.aircraft_update.emit(rec)
        self.status_changed.emit("Connected")
        dbg(f"{self.label}: {len(ac)} aircraft")


class AdsbLolProvider(AdsbJsonProvider):
    id = "adsblol"
    label = "adsb.lol"
    base_url = "https://api.adsb.lol/v2"
    help_text = ('Free, keyless community ADS-B network — no account needed. '
                 'Coverage is wherever volunteers run receivers (dense over '
                 'Europe/North America, sparser elsewhere).')


class AdsbFiProvider(AdsbJsonProvider):
    id = "adsbfi"
    label = "adsb.fi"
    base_url = "https://opendata.adsb.fi/api/v2"
    help_text = ('Free, keyless community ADS-B network (adsb.fi) — no account '
                 'needed. Carries an aircraft-type description.')
