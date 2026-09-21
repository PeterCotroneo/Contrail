"""Country lookup from an ICAO 24-bit address (the transponder hex id).

ICAO allocates 24-bit address blocks to states (Annex 10, Vol III). The adsb.lol
/ adsb.fi feeds give only the hex; OpenSky already supplies a country, so this is
mainly for the community feeds. Covers the major allocations — enough for the
vast majority of real traffic; anything unmatched returns "".
"""

# (start, end, country) — inclusive hex ranges, ascending. A representative set
# of the ICAO allocation covering the high-traffic states and regional blocks.
_RANGES = [
    (0x004000, 0x0043FF, "Zimbabwe"),
    (0x006000, 0x006FFF, "Mozambique"),
    (0x008000, 0x00FFFF, "South Africa"),
    (0x010000, 0x017FFF, "Egypt"),
    (0x018000, 0x01FFFF, "Libya"),
    (0x020000, 0x027FFF, "Morocco"),
    (0x028000, 0x02FFFF, "Tunisia"),
    (0x030000, 0x0303FF, "Botswana"),
    (0x032000, 0x032FFF, "Cameroon"),
    (0x034000, 0x034FFF, "Congo"),
    (0x038000, 0x038FFF, "Ivory Coast"),
    (0x03E000, 0x03EFFF, "Gabon"),
    (0x040000, 0x040FFF, "Ethiopia"),
    (0x044000, 0x044FFF, "Kenya"),
    (0x04C000, 0x04CFFF, "Libya"),
    (0x050000, 0x050FFF, "Nigeria"),
    (0x054000, 0x054FFF, "Sudan"),
    (0x05A000, 0x05AFFF, "Tanzania"),
    (0x060000, 0x060FFF, "Uganda"),
    (0x06C000, 0x06CFFF, "Zambia"),
    (0x100000, 0x1FFFFF, "Russia"),
    (0x201000, 0x2013FF, "Namibia"),
    (0x202000, 0x2023FF, "Eritrea"),
    (0x300000, 0x33FFFF, "Italy"),
    (0x340000, 0x37FFFF, "Spain"),
    (0x380000, 0x3BFFFF, "France"),
    (0x3C0000, 0x3FFFFF, "Germany"),
    (0x400000, 0x43FFFF, "United Kingdom"),
    (0x440000, 0x447FFF, "Austria"),
    (0x448000, 0x44FFFF, "Belgium"),
    (0x450000, 0x457FFF, "Bulgaria"),
    (0x458000, 0x45FFFF, "Denmark"),
    (0x460000, 0x467FFF, "Finland"),
    (0x468000, 0x46FFFF, "Greece"),
    (0x470000, 0x477FFF, "Hungary"),
    (0x478000, 0x47FFFF, "Norway"),
    (0x480000, 0x487FFF, "Netherlands"),
    (0x488000, 0x48FFFF, "Poland"),
    (0x490000, 0x497FFF, "Portugal"),
    (0x498000, 0x49FFFF, "Czechia"),
    (0x4A0000, 0x4A7FFF, "Romania"),
    (0x4A8000, 0x4AFFFF, "Sweden"),
    (0x4B0000, 0x4B7FFF, "Switzerland"),
    (0x4B8000, 0x4BFFFF, "Turkey"),
    (0x4C0000, 0x4C7FFF, "Serbia"),
    (0x4C8000, 0x4C83FF, "Cyprus"),
    (0x4CA000, 0x4CAFFF, "Ireland"),
    (0x4CC000, 0x4CCFFF, "Iceland"),
    (0x4D0000, 0x4D03FF, "Luxembourg"),
    (0x500000, 0x5003FF, "Slovakia"),
    (0x501000, 0x5013FF, "Ukraine"),
    (0x508000, 0x50FFFF, "Ukraine"),
    (0x510000, 0x5103FF, "Belarus"),
    (0x511000, 0x5113FF, "Estonia"),
    (0x512000, 0x5123FF, "Latvia"),
    (0x516000, 0x5163FF, "Croatia"),
    (0x51C000, 0x51CFFF, "Lithuania"),
    (0x600000, 0x6003FF, "Armenia"),
    (0x600800, 0x600BFF, "Azerbaijan"),
    (0x680000, 0x6803FF, "Georgia"),
    (0x700000, 0x700FFF, "Afghanistan"),
    (0x708000, 0x70FFFF, "Iraq"),
    (0x710000, 0x717FFF, "Iran"),
    (0x718000, 0x71FFFF, "Israel"),
    (0x720000, 0x727FFF, "Jordan"),
    (0x728000, 0x72FFFF, "Lebanon"),
    (0x730000, 0x737FFF, "Saudi Arabia"),
    (0x738000, 0x73FFFF, "Kuwait"),
    (0x740000, 0x747FFF, "Qatar"),
    (0x760000, 0x767FFF, "Oman"),
    (0x768000, 0x76FFFF, "Pakistan"),
    (0x770000, 0x777FFF, "United Arab Emirates"),
    (0x780000, 0x7BFFFF, "China"),
    (0x7C0000, 0x7FFFFF, "Australia"),
    (0x800000, 0x83FFFF, "India"),
    (0x840000, 0x87FFFF, "Japan"),
    (0x880000, 0x887FFF, "Thailand"),
    (0x888000, 0x88FFFF, "Vietnam"),
    (0x890000, 0x890FFF, "China"),
    (0x894000, 0x894FFF, "China"),
    (0x8A0000, 0x8A7FFF, "Indonesia"),
    (0x8B0000, 0x8B7FFF, "Philippines"),
    (0x900000, 0x9003FF, "Marshall Islands"),
    (0xA00000, 0xAFFFFF, "United States"),
    (0xC00000, 0xC3FFFF, "Canada"),
    (0xC80000, 0xC87FFF, "New Zealand"),
    (0xC90000, 0xC90FFF, "Fiji"),
    (0xE00000, 0xE3FFFF, "Argentina"),
    (0xE40000, 0xE7FFFF, "Brazil"),
    (0xE80000, 0xE80FFF, "Chile"),
    (0xE84000, 0xE84FFF, "Colombia"),
    (0xE94000, 0xE94FFF, "Peru"),
    (0xE80000, 0xE81FFF, "Chile"),
    (0xEA0000, 0xEA7FFF, "Venezuela"),
]


def country_for_hex(hexid):
    """Return the country for an ICAO 24-bit address (hex string), or ""."""
    if not hexid:
        return ""
    try:
        n = int(str(hexid).strip(), 16)
    except (TypeError, ValueError):
        return ""
    for start, end, country in _RANGES:
        if start <= n <= end:
            return country
    return ""
