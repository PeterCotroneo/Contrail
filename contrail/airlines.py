"""Operator lookup from a flight callsign.

An airline callsign is a 3-letter ICAO airline designator followed by the flight
number (which starts with a digit): ``BAW123`` (British Airways), ``DLH3VT``
(Lufthansa), ``RYR33RN`` (Ryanair). Private / general-aviation aircraft use
their registration as the callsign instead (``N12345``, ``GABCD``), which is not
an airline code — the digit-after-the-code test filters those out.

Covers the major global carriers, cargo operators and large regionals — enough
for most commercial traffic; anything unmatched returns "".
"""

# ICAO 3-letter designator -> operator name
AIRLINES = {
    # --- North America ---
    "AAL": "American Airlines", "DAL": "Delta Air Lines", "UAL": "United Airlines",
    "SWA": "Southwest Airlines", "JBU": "JetBlue", "ASA": "Alaska Airlines",
    "NKS": "Spirit Airlines", "FFT": "Frontier Airlines", "HAL": "Hawaiian Airlines",
    "SKW": "SkyWest", "RPA": "Republic Airways", "EDV": "Endeavor Air",
    "ACA": "Air Canada", "WJA": "WestJet", "JZA": "Jazz Aviation",
    "AMX": "Aeroméxico", "VOI": "Volaris", "FDX": "FedEx", "UPS": "UPS",
    "GTI": "Atlas Air", "ATN": "Air Transport Intl",
    # --- United Kingdom / Ireland ---
    "BAW": "British Airways", "SHT": "British Airways Shuttle",
    "CFE": "BA CityFlyer", "EZY": "easyJet", "EJU": "easyJet Europe",
    "EXS": "Jet2", "TOM": "TUI Airways", "VIR": "Virgin Atlantic",
    "LOG": "Loganair", "EIN": "Aer Lingus", "RYR": "Ryanair", "RUK": "Ryanair UK",
    # --- Europe ---
    "DLH": "Lufthansa", "GEC": "Lufthansa Cargo", "AFR": "Air France",
    "KLM": "KLM", "IBE": "Iberia", "IBS": "Iberia Express", "VLG": "Vueling",
    "SWR": "Swiss", "AUA": "Austrian Airlines", "BEL": "Brussels Airlines",
    "TAP": "TAP Air Portugal", "SAS": "SAS", "FIN": "Finnair",
    "NAX": "Norwegian", "NOZ": "Norwegian", "WZZ": "Wizz Air", "WUK": "Wizz Air UK",
    "LOT": "LOT Polish Airlines", "EWG": "Eurowings", "TRA": "Transavia",
    "TVF": "Transavia France", "VOE": "Volotea", "ITY": "ITA Airways",
    "AEE": "Aegean Airlines", "CAI": "Corendon", "PGT": "Pegasus",
    "CLX": "Cargolux", "ICE": "Icelandair", "AFL": "Aeroflot", "SDM": "Rossiya",
    "THY": "Turkish Airlines", "THK": "AJet",
    # --- Middle East ---
    "UAE": "Emirates", "ETD": "Etihad Airways", "QTR": "Qatar Airways",
    "SVA": "Saudia", "MEA": "Middle East Airlines", "RJA": "Royal Jordanian",
    "GFA": "Gulf Air", "KAC": "Kuwait Airways", "OMA": "Oman Air",
    "ELY": "El Al", "IAW": "Iraqi Airways", "ABY": "Air Arabia", "FDB": "flydubai",
    # --- Asia / Pacific ---
    "CCA": "Air China", "CES": "China Eastern", "CSN": "China Southern",
    "CHH": "Hainan Airlines", "CPA": "Cathay Pacific", "HDA": "Cathay Dragon",
    "ANA": "All Nippon Airways", "JAL": "Japan Airlines", "KAL": "Korean Air",
    "AAR": "Asiana Airlines", "SIA": "Singapore Airlines", "SLK": "Scoot",
    "MAS": "Malaysia Airlines", "AXM": "AirAsia", "THA": "Thai Airways",
    "EVA": "EVA Air", "CAL": "China Airlines", "GIA": "Garuda Indonesia",
    "PAL": "Philippine Airlines", "CEB": "Cebu Pacific", "VJC": "VietJet",
    "HVN": "Vietnam Airlines", "AIC": "Air India", "IGO": "IndiGo",
    "QFA": "Qantas", "JST": "Jetstar", "VOZ": "Virgin Australia",
    "ANZ": "Air New Zealand",
    # --- Africa / South America ---
    "ETH": "Ethiopian Airlines", "MSR": "EgyptAir", "RAM": "Royal Air Maroc",
    "SAA": "South African Airways", "KQA": "Kenya Airways", "DAH": "Air Algérie",
    "LAN": "LATAM", "TAM": "LATAM Brasil", "GLO": "GOL", "AZU": "Azul",
    "AVA": "Avianca", "ARG": "Aerolíneas Argentinas",
}


def operator_for_callsign(callsign):
    """Return the operating airline for a callsign, or "" if it's not a
    recognised airline designator (e.g. a private registration)."""
    if not callsign:
        return ""
    cs = str(callsign).strip().upper()
    if len(cs) >= 4 and cs[:3].isalpha() and cs[3].isdigit():
        return AIRLINES.get(cs[:3], "")
    return ""
