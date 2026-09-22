"""Provider registry.

Adding a new ADS-B source: implement AircraftProvider in a new module, declare
its ``config_fields`` (what the configure dialog should ask for), and register
its class below. The plugin builds its provider dropdown and settings dialog
from PROVIDERS + each provider's config_fields — nothing else needs to change.
"""

from .base import AircraftProvider
from .adsb import AdsbLolProvider, AdsbFiProvider
from .opensky import OpenSkyProvider

# id -> provider class (order shown in the dropdown; the first is the default).
# adsb.fi leads — it rate-limits less aggressively than adsb.lol, so it gives a
# smoother refresh out of the box.
PROVIDERS = {
    AdsbFiProvider.id: AdsbFiProvider,
    AdsbLolProvider.id: AdsbLolProvider,
    OpenSkyProvider.id: OpenSkyProvider,
}

__all__ = [
    "AircraftProvider", "AdsbFiProvider", "AdsbLolProvider",
    "OpenSkyProvider", "PROVIDERS",
]
