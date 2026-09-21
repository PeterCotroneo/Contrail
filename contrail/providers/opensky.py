"""OpenSky Network provider — keyless (anonymous) live ADS-B via bounding box.

``GET /api/states/all?lamin&lomin&lamax&lomax`` returns
``{"time": .., "states": [[...], ..]}`` where each state is a fixed-order array
(see ``_IDX``). Anonymous access works but is rate-limited, so we poll more
gently than the community feeds. Altitudes/speeds arrive in metres and m/s and
are converted to feet / knots / ft-per-min to match the base contract.
"""

import json

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl, QTimer
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

from .base import AircraftProvider
from .._debug import dbg

POLL_MS = 10000            # anonymous OpenSky is rate-limited; poll gently
USER_AGENT = "ContrailQGIS/0.1 (QGIS plugin)"
M_TO_FT = 3.28084
MS_TO_KT = 1.94384
MS_TO_FTMIN = 196.850393

_IDX = {"icao24": 0, "callsign": 1, "country": 2, "lon": 5, "lat": 6,
        "baro_alt": 7, "on_ground": 8, "velocity": 9, "track": 10,
        "vert_rate": 11, "geo_alt": 13, "squawk": 14, "category": 17}

# OpenSky numeric emitter-category index -> ADS-B category code (see base doc)
_CATEGORY = {2: "A1", 3: "A2", 4: "A3", 5: "A4", 6: "A5", 7: "A6", 8: "A7",
             9: "B1", 10: "B2", 11: "B3", 12: "B4", 14: "B6", 15: "B7",
             16: "C1", 17: "C2", 18: "C3", 19: "C3", 20: "C3"}


def _mul(v, k):
    return v * k if isinstance(v, (int, float)) else None


class OpenSkyProvider(AircraftProvider):
    id = "opensky"
    label = "OpenSky Network"
    help_text = ('Free, keyless live ADS-B from the OpenSky Network. No account '
                 'needed (anonymous access is rate-limited; a free OpenSky '
                 'account raises the limits if you hit them).')

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
        dbg("Polling OpenSky Network")
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
        lat_min, lon_min, lat_max, lon_max = self._bbox
        url = ("https://opensky-network.org/api/states/all"
               f"?lamin={lat_min:.4f}&lomin={lon_min:.4f}"
               f"&lamax={lat_max:.4f}&lomax={lon_max:.4f}")
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", USER_AGENT.encode())
        req.setRawHeader(b"Accept", b"application/json")
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._on_reply(reply))

    def _on_reply(self, reply):
        reply.deleteLater()
        if not self._want:
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.error.emit(
                f"OpenSky unreachable ({reply.errorString()}). Anonymous access "
                "is rate-limited — try again shortly or slow the polling.")
            return
        try:
            data = json.loads(bytes(reply.readAll()))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"OpenSky returned bad JSON: {exc}")
            return
        states = data.get("states") or []
        for s in states:
            hexid = (s[_IDX["icao24"]] or "").strip().lower()
            if not hexid:
                continue
            cat = s[_IDX["category"]] if len(s) > _IDX["category"] else None
            self.aircraft_update.emit({
                "hex": hexid,
                "callsign": (s[_IDX["callsign"]] or "").strip(),
                "country": (s[_IDX["country"]] or "").strip(),
                "lat": s[_IDX["lat"]],
                "lon": s[_IDX["lon"]],
                "track": s[_IDX["track"]],
                "gs": _mul(s[_IDX["velocity"]], MS_TO_KT),
                "altitude": _mul(s[_IDX["baro_alt"]] if s[_IDX["baro_alt"]] is not None
                                 else s[_IDX["geo_alt"]], M_TO_FT),
                "vert_rate": _mul(s[_IDX["vert_rate"]], MS_TO_FTMIN),
                "squawk": (s[_IDX["squawk"]] or "").strip() if s[_IDX["squawk"]] else "",
                "category": _CATEGORY.get(cat, ""),
                "on_ground": bool(s[_IDX["on_ground"]]),
            })
        self.status_changed.emit("Connected")
        dbg(f"OpenSky: {len(states)} aircraft")
