# api/analyzer/detectors/climate.py

import re
from typing import Dict, Optional

# --- Allgemeines Pattern für CO2-Mengen (t, tons, million tons, etc.) ---------

GHG_AMOUNT_PATTERN = re.compile(
    r"""
    (?P<number>
        \d{1,3}
        (?:[.,]\d{3})*        # Tausendergruppen
        (?:[.,]\d+)?          # Dezimalteil
        |
        \d+
    )
    \s*
    (?P<multiplier>
        million|billion|thousand|
        Mio\.?|Mrd\.?|
        mn|bn
    )?
    \s*
    (?P<unit>
        t\s*co2e |
        t\s*co2 |
        t |
        tons?\s*co2e |
        tons?\s*co2 |
        tons? |
        tonnes?\s*co2e |
        tonnes?\s*co2 |
        tonnes?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _normalize_number(num_str: str) -> float:
    """
    Wandelt Strings wie '123,456', '1.234,56', '1,234.56' in float.
    """
    s = num_str.strip()

    if "," in s and "." in s:
        last_comma = s.rfind(",")
        last_dot = s.rfind(".")
        if last_comma > last_dot:
            # '1.234,56' -> '1234.56'
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            # '1,234.56' -> '1234.56'
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) in (1, 2):
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    return float(s)


def _parse_quantity_with_multiplier(raw_number: str, raw_multiplier: Optional[str]) -> Optional[float]:
    """
    Nimmt eine Rohzahl + evtl. Multiplikatorwort ('million', 'Mio.', 'billion', 'Mrd.')
    und gibt den Wert in Basis-Einheit zurück (Tonnen).
    """
    try:
        base = _normalize_number(raw_number)
    except ValueError:
        return None

    if not raw_multiplier:
        return base

    m = raw_multiplier.lower()

    if m in ("thousand",):
        return base * 1_000.0
    if m in ("million", "mio.", "mio"):
        return base * 1_000_000.0
    if m in ("billion", "mrd.", "mrd", "bn"):
        return base * 1_000_000_000.0
    if m in ("mn",):
        return base * 1_000_000.0

    return base


def _build_context_snippet(text: str, start: int, end: int, window: int = 120) -> str:
    """
    Grobes Kontext-Snippet um die Fundstelle [start, end).
    """
    left = max(0, start - window)
    right = min(len(text), end + window)
    snippet = text[left:right].strip()
    return snippet


def _find_best_match_near_keywords(
    text: str,
    keywords: list[str],
) -> Optional[Dict]:
    """
    Einfachere, robuste Logik:
    - suche nach Keywords im Text
    - für jedes Keyword: suche nach GHG-Mengen im Umkreis von ±150 Zeichen
    - wähle die nächstgelegene Menge zu einem Keyword
    """
    if not text:
        return None

    text_lower = text.lower()
    candidates = []

    # 1) Alle Keyword-Positionen sammeln
    kw_positions = []
    for kw in keywords:
        kw_lower = kw.lower()
        start = 0
        while True:
            idx = text_lower.find(kw_lower, start)
            if idx == -1:
                break
            kw_positions.append((kw_lower, idx))
            start = idx + len(kw_lower)

    if not kw_positions:
        return None

    # 2) Für jedes Keyword im Umfeld nach Mengen suchen
    for kw, kw_pos in kw_positions:
        window_left = max(0, kw_pos - 150)
        window_right = min(len(text), kw_pos + 150)
        sub = text[window_left:window_right]

        for match in GHG_AMOUNT_PATTERN.finditer(sub):
            num_str = match.group("number")
            mult_str = match.group("multiplier")

            value = _parse_quantity_with_multiplier(num_str, mult_str)
            if value is None:
                continue

            span_start = window_left + match.start()
            span_end = window_left + match.end()

            distance = abs(span_start - kw_pos)
            ctx = _build_context_snippet(text, span_start, span_end)

            candidates.append(
                {
                    "value": float(value),
                    "ctx": ctx,
                    "distance": distance,
                }
            )

    if not candidates:
        return None

    best = min(candidates, key=lambda c: c["distance"])

    return {
        "value": best["value"],
        "ctx": best["ctx"],
    }


# === B1: GHG emissions avoided (t CO2e) ======================================

GHG_AVOIDED_KEYWORDS = [
    "ghg emissions avoided",
    "emissions avoided",
    "avoided emissions",
    "avoided",
    "emissions saved",
    "co2 savings",
    "co2e savings",
    "savings",
    "saved",
    "vermiedene emissionen",
    "eingesparte emissionen",
]


def detect_ghg_avoided_total_t_co2e(text: str) -> Optional[Dict]:
    """
    Erkennt GHG emissions avoided in t CO2e.
    """
    match = _find_best_match_near_keywords(text, GHG_AVOIDED_KEYWORDS)
    if not match:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "ghg_avoided_total_t_co2e",
        "kpi_value": match["value"],
        "kpi_unit": "t CO2e",
        "ctx": match["ctx"],
    }


# === B2: Carbon sequestered (Blue Carbon, t CO2e) ============================

CARBON_SEQUESTERED_KEYWORDS = [
    "carbon sequestered",
    "co2 sequestered",
    "sequestered",
    "blue carbon",
    "carbon stored",
    "co2 stored",
    "carbon removal",
    "captured",
    "kohlendioxidbindung",
    "kohlenstoffbindung",
]


def detect_carbon_sequestered_total_t_co2e(text: str) -> Optional[Dict]:
    """
    Erkennt Carbon sequestered / Blue Carbon in t CO2e.
    """
    match = _find_best_match_near_keywords(text, CARBON_SEQUESTERED_KEYWORDS)
    if not match:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "carbon_sequestered_total_t_co2e",
        "kpi_value": match["value"],
        "kpi_unit": "t CO2e",
        "ctx": match["ctx"],
    }
