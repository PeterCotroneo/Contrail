"""Live aircraft layer: buffer incoming ADS-B reports and flush to a memory
layer in batches so the map stays responsive under a busy feed.

Provider messages arrive as normalised aircraft dicts (see providers/base.py)
and are merged by ICAO hex address. Markers are triangles oriented to the
aircraft's track and coloured by emitter category (with an Emergency override
for 7500/7600/7700 squawks). Aircraft not heard from for a while are expired.
"""

import os
import time

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsMarkerSymbol,
    QgsSvgMarkerSymbolLayer,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsPointClusterRenderer,
    QgsProperty,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsMessageLog,
    Qgis,
)

from ._debug import dbg
from .icao import country_for_hex
from .airlines import operator_for_callsign

LAYER_NAME = "Contrail — Live Aircraft"
_PLANE_SVG = os.path.join(os.path.dirname(__file__), "plane.svg")

# ordered layer fields
_FIELDS = [
    ("hex", QVariant.String),
    ("callsign", QVariant.String),
    ("operator", QVariant.String),
    ("flag", QVariant.String),
    ("type", QVariant.String),
    ("cat_group", QVariant.String),
    ("squawk", QVariant.String),
    ("emergency", QVariant.String),
    ("altitude", QVariant.Int),
    ("gs", QVariant.Double),
    ("track", QVariant.Double),
    ("vert_rate", QVariant.Int),
    ("on_ground", QVariant.Int),
    ("rotation", QVariant.Double),
    ("last_seen", QVariant.String),
]
_FIELD_INDEX = {name: i for i, (name, _t) in enumerate(_FIELDS)}

_ALIASES = {
    "hex": "ICAO hex", "callsign": "Callsign", "operator": "Operator",
    "flag": "Country",
    "type": "Aircraft type", "cat_group": "Category", "squawk": "Squawk",
    "emergency": "Emergency", "altitude": "Altitude (ft)", "gs": "Ground speed (kn)",
    "track": "Track (°)", "vert_rate": "Vertical rate (ft/min)",
    "on_ground": "On ground", "last_seen": "Last seen (UTC)",
}

_MAP_TIP = (
    "<b>[% coalesce(nullif(\"callsign\",''),\"hex\") %]</b> "
    "<span style='color:gray'>[% \"hex\" %]</span>"
    "[% CASE WHEN \"flag\" IS NOT NULL AND \"flag\" != '' THEN ' · ' || \"flag\" ELSE '' END %]<br/>"
    "[% CASE WHEN \"operator\" IS NOT NULL AND \"operator\" != '' "
    "THEN \"operator\" || '<br/>' ELSE '' END %]"
    "[% coalesce(nullif(\"type\",''),\"cat_group\") %]"
    "[% CASE WHEN \"on_ground\" = 1 THEN ' · on ground' ELSE '' END %]<br/>"
    "Alt [% coalesce(\"altitude\",'?') %] ft · [% coalesce(\"gs\",'?') %] kn · "
    "Track [% coalesce(\"track\",'?') %]°"
    "[% CASE WHEN \"vert_rate\" IS NOT NULL AND \"vert_rate\" != 0 "
    "THEN ' · ' || \"vert_rate\" || ' ft/min' ELSE '' END %]<br/>"
    "[% CASE WHEN \"squawk\" IS NOT NULL AND \"squawk\" != '' "
    "THEN 'Squawk ' || \"squawk\" ELSE '' END %]"
    "[% CASE WHEN \"emergency\" IS NOT NULL AND \"emergency\" NOT IN ('','none') "
    "THEN ' · ⚠ ' || \"emergency\" ELSE '' END %]"
    "<br/><span style='color:gray'>Last seen [% coalesce(\"last_seen\",'—') %]</span>"
)

# category -> colour (also the order shown in the legend)
CATEGORY_COLORS = [
    ("Light", "#2ca02c"),
    ("Small", "#1f77b4"),
    ("Large", "#17becf"),
    ("Heavy", "#d62728"),
    ("High-perf", "#9467bd"),
    ("Rotorcraft", "#ff7f0e"),
    ("Special", "#8c564b"),
    ("Emergency", "#e377c2"),
    ("Unknown", "#b0b0b0"),
]

_CAT_GROUP = {"A1": "Light", "A2": "Small", "A3": "Large", "A4": "Large",
              "A5": "Heavy", "A6": "High-perf", "A7": "Rotorcraft"}
_EMERGENCY_SQUAWKS = {"7500", "7600", "7700"}

# Identity fields that don't change for an aircraft within a session — remembered
# so a plane that leaves the view and returns keeps its callsign/type/category
# instead of resetting. See AircraftStore._static_cache.
_STATIC_KEYS = ("callsign", "category", "type_desc", "country")


def _cat_group(rec):
    if str(rec.get("squawk") or "") in _EMERGENCY_SQUAWKS:
        return "Emergency"
    code = (rec.get("category") or "").upper()
    if code in _CAT_GROUP:
        return _CAT_GROUP[code]
    if code[:1] in ("B", "C"):
        return "Special"
    return "Unknown"


def _rotation(rec):
    """Track if valid (0..359), else 0."""
    try:
        f = float(rec.get("track"))
    except (TypeError, ValueError):
        return 0.0
    return f if 0 <= f < 360 else 0.0


class AircraftStore:
    def __init__(self):
        self._layer = None
        self._records = {}   # hex -> merged field dict (+ _last_update wall clock)
        self._fid = {}       # hex -> feature id in the layer
        self._pending_new = set()
        self._pending_upd = set()
        self._airborne_only = False  # "show only airborne" filter state
        # Session-long memory of each aircraft's identity fields, so one that
        # leaves the view and returns keeps its callsign/type/category. Plain
        # scalars keyed by hex — small and never touches the layer.
        self._static_cache = {}

    # --- layer lifecycle -------------------------------------------------
    def ensure_layer(self):
        if self._layer is not None and self._layer_valid():
            return self._layer
        fields = QgsFields()
        for name, qtype in _FIELDS:
            fields.append(QgsField(name, qtype))
        layer = QgsVectorLayer("Point?crs=EPSG:4326", LAYER_NAME, "memory")
        layer.dataProvider().addAttributes(fields.toList())
        layer.updateFields()
        for name, alias in _ALIASES.items():
            idx = layer.fields().indexOf(name)
            if idx >= 0:
                layer.setFieldAlias(idx, alias)
        layer.setMapTipTemplate(_MAP_TIP)
        self._add_actions(layer)
        self._style(layer)
        QgsProject.instance().addMapLayer(layer)
        self._apply_airborne_filter()  # honour the toggle across start/stop

    def _add_actions(self, layer):
        """Right-click / Identify actions that open the aircraft on a live
        tracker, keyed by ICAO hex. No scraping — just links."""
        try:
            from qgis.core import QgsAction
            try:
                url_type = Qgis.AttributeActionType.OpenUrl
            except AttributeError:
                url_type = QgsAction.ActionType.OpenUrl
            targets = [
                ("View on ADS-B Exchange",
                 'https://globe.adsbexchange.com/?icao=[% "hex" %]'),
                ("View on FlightAware",
                 'https://flightaware.com/live/modes/[% "hex" %]/redirect'),
            ]
            for label, url in targets:
                layer.actions().addAction(url_type, label, url)
        except Exception as exc:  # noqa: BLE001 - actions are a nicety
            QgsMessageLog.logMessage(f"actions skipped: {exc}", "Contrail",
                                     Qgis.MessageLevel.Warning)
        self._layer = layer
        self._records.clear()
        self._fid.clear()
        self._pending_new.clear()
        self._pending_upd.clear()
        return layer

    def airborne_count(self):
        """How many tracked aircraft are airborne (not reporting on-ground)."""
        return sum(1 for rec in self._records.values() if not rec.get("on_ground"))

    def set_airborne_filter(self, on):
        """Show only airborne aircraft when ``on`` — hides those on the ground
        via a layer subset, without dropping them from the store."""
        self._airborne_only = bool(on)
        self._apply_airborne_filter()

    def _apply_airborne_filter(self):
        if not self._layer_valid():
            return
        expr = '"on_ground" = 0' if self._airborne_only else ""
        try:
            self._layer.setSubsetString(expr)
        except Exception as exc:  # noqa: BLE001 - never let a filter break data
            QgsMessageLog.logMessage(
                f"airborne filter skipped: {exc}", "Contrail", Qgis.MessageLevel.Warning)

    def layer(self):
        return self._layer if self._layer_valid() else None

    def _layer_valid(self):
        try:
            return self._layer is not None and self._layer.isValid()
        except RuntimeError:
            return False

    def remove_layer(self):
        if self._layer_valid():
            QgsProject.instance().removeMapLayer(self._layer.id())
        self._layer = None
        self._records.clear()
        self._fid.clear()

    def _style(self, layer):
        try:
            categories = []
            for group, color in CATEGORY_COLORS:
                svg = QgsSvgMarkerSymbolLayer(_PLANE_SVG)
                svg.setSize(6)
                svg.setFillColor(QColor(color))
                svg.setStrokeColor(QColor("black"))
                svg.setStrokeWidth(0.2)
                sym = QgsMarkerSymbol()
                sym.changeSymbolLayer(0, svg)   # plane silhouette, not a triangle
                sym.setDataDefinedAngle(QgsProperty.fromField("rotation"))
                categories.append(QgsRendererCategory(group, sym, group))
            by_cat = QgsCategorizedSymbolRenderer("cat_group", categories)
            # Wrap the category renderer in a point-cluster renderer so aircraft
            # that overlap on screen (e.g. stacked near a busy airport) collapse
            # into a single badge showing the count, and fan back out into
            # individual markers as you zoom in. Tolerance is screen-based.
            cluster = QgsPointClusterRenderer()
            cluster.setEmbeddedRenderer(by_cat)
            cluster.setTolerance(3.5)
            try:
                cluster.setToleranceUnit(Qgis.RenderUnit.Millimeters)
            except (AttributeError, TypeError):
                pass  # older binding: keep the default tolerance unit
            layer.setRenderer(cluster)
            pal = QgsPalLayerSettings()
            pal.fieldName = "callsign"
            layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
            layer.setLabelsEnabled(True)
        except Exception as exc:  # noqa: BLE001 - styling must never block data
            QgsMessageLog.logMessage(f"styling skipped: {exc}", "Contrail",
                                     Qgis.MessageLevel.Warning)

    # --- ingest / flush --------------------------------------------------
    def ingest(self, ac):
        hexid = ac.get("hex")
        if not hexid:
            return
        rec = self._records.get(hexid)
        if rec is None:
            # New (or re-appearing) aircraft — seed with any identity we already
            # learned this session so it isn't Unknown before the next report.
            rec = dict(self._static_cache.get(hexid, {}))
            self._records[hexid] = rec
        for key, val in ac.items():
            if val is not None and val != "":
                rec[key] = val
        # Remember identity fields for the whole session.
        cache = self._static_cache.setdefault(hexid, {})
        for key in _STATIC_KEYS:
            val = ac.get(key)
            if val is not None and val != "":
                cache[key] = val
        rec["_last_update"] = time.time()
        has_pos = rec.get("lat") is not None and rec.get("lon") is not None
        if hexid in self._fid:
            self._pending_upd.add(hexid)
        elif has_pos:
            self._pending_new.add(hexid)

    def _attrs(self, rec):
        return {
            _FIELD_INDEX["callsign"]: rec.get("callsign", ""),
            _FIELD_INDEX["operator"]: operator_for_callsign(rec.get("callsign")),
            _FIELD_INDEX["flag"]: rec.get("country") or country_for_hex(rec.get("hex")),
            _FIELD_INDEX["type"]: rec.get("type_desc", ""),
            _FIELD_INDEX["cat_group"]: _cat_group(rec),
            _FIELD_INDEX["squawk"]: rec.get("squawk", ""),
            _FIELD_INDEX["emergency"]: rec.get("emergency", ""),
            _FIELD_INDEX["altitude"]: (int(rec["altitude"]) if rec.get("altitude") is not None else None),
            _FIELD_INDEX["gs"]: rec.get("gs"),
            _FIELD_INDEX["track"]: rec.get("track"),
            _FIELD_INDEX["vert_rate"]: (int(rec["vert_rate"]) if rec.get("vert_rate") is not None else None),
            _FIELD_INDEX["on_ground"]: 1 if rec.get("on_ground") else 0,
            _FIELD_INDEX["rotation"]: _rotation(rec),
            _FIELD_INDEX["last_seen"]: rec.get("last_seen", ""),
        }

    def flush(self):
        """Apply buffered adds/updates to the layer in one pass. Main thread."""
        if not self._layer_valid() or (not self._pending_new and not self._pending_upd):
            return
        n_new = len(self._pending_new)
        dp = self._layer.dataProvider()

        # additions
        if self._pending_new:
            feats, hexes = [], []
            for hexid in self._pending_new:
                rec = self._records.get(hexid)
                if not rec:
                    continue
                feat = QgsFeature(self._layer.fields())
                feat.setGeometry(QgsGeometry.fromPointXY(
                    QgsPointXY(float(rec["lon"]), float(rec["lat"]))))
                attrs = [None] * len(_FIELDS)
                attrs[_FIELD_INDEX["hex"]] = hexid
                for idx, val in self._attrs(rec).items():
                    attrs[idx] = val
                feat.setAttributes(attrs)
                feats.append(feat)
                hexes.append(hexid)
            if feats:
                ok, added = dp.addFeatures(feats)
                if added:
                    # map by each feature's own hex (order-independent) so we
                    # never lose an id and duplicate the aircraft next message
                    for f in added:
                        h = f["hex"]
                        if h:
                            self._fid[h] = f.id()
                else:
                    want = set(hexes)
                    for feat in self._layer.getFeatures():
                        h = feat["hex"]
                        if h in want:
                            self._fid[h] = feat.id()
            self._pending_new.clear()

        # updates (geometry + attributes)
        if self._pending_upd:
            geom_changes, attr_changes = {}, {}
            for hexid in self._pending_upd:
                fid = self._fid.get(hexid)
                rec = self._records.get(hexid)
                if fid is None or not rec:
                    continue
                if rec.get("lat") is not None and rec.get("lon") is not None:
                    geom_changes[fid] = QgsGeometry.fromPointXY(
                        QgsPointXY(float(rec["lon"]), float(rec["lat"])))
                attr_changes[fid] = self._attrs(rec)
            if geom_changes:
                dp.changeGeometryValues(geom_changes)
            if attr_changes:
                dp.changeAttributeValues(attr_changes)
            self._pending_upd.clear()

        self._layer.updateExtents()
        self._layer.triggerRepaint()
        if n_new:
            dbg(f"+{n_new} new aircraft · {self._layer.featureCount()} on the map")

    def expire(self, max_age_seconds):
        if not self._layer_valid():
            return
        now = time.time()
        stale = [h for h, rec in self._records.items()
                 if now - rec.get("_last_update", now) > max_age_seconds]
        fids = [self._fid[h] for h in stale if h in self._fid]
        if fids:
            self._layer.dataProvider().deleteFeatures(fids)
            self._layer.triggerRepaint()
            dbg(f"removed {len(fids)} aircraft not seen recently")
        for h in stale:
            self._records.pop(h, None)
            self._fid.pop(h, None)

    def count(self):
        return len(self._fid)

    def retain_within(self, bbox):
        """Drop aircraft outside bbox (lat_min, lon_min, lat_max, lon_max) so the
        map reflects the area currently being watched after a pan/zoom."""
        if not self._layer_valid():
            return
        lat_min, lon_min, lat_max, lon_max = bbox
        outside = []
        for h, rec in self._records.items():
            try:
                lat, lon = float(rec.get("lat")), float(rec.get("lon"))
            except (TypeError, ValueError):
                # No position yet — keep it (not on the map; don't lose identity).
                continue
            if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
                outside.append(h)
        fids = [self._fid[h] for h in outside if h in self._fid]
        if fids:
            self._layer.dataProvider().deleteFeatures(fids)
            self._layer.triggerRepaint()
        for h in outside:
            self._records.pop(h, None)
            self._fid.pop(h, None)
