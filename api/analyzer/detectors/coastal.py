# api/analyzer/detectors/coastal.py

import re
from typing import Dict, Optional

from .water import (
    _normalize_number,
    _parse_quantity_with_multiplier,
    _build_context_snippet,
    _get_sentence_bounds,
)

# --- Allgemeine Patterns für km und ha ---------------------------------------

DISTANCE_PATTERN = re.compile(
    r"""
    (?P<number>
        \d{1,3}
        (?:[.,]\d{3})*        # Tausender
        (?:[.,]\d+)?          # Dezimal
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
        km|kilometers?|kilometres?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

AREA_PATTERN = re.compile(
    r"""
    (?P<number>
        \d{1,3}
        (?:[.,]\d{3})*
        (?:[.,]\d+)?          # Dezimal
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
        ha|hectares?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

def _find_best_match_for_pattern_near_keywords(
    text: str,
    pattern: re.Pattern,
    keywords: list[str],
) -> Optional[Dict]:
    """
    Generische Logik:
    - Suche alle Sätze, die eines der Keywords enthalten
    - Finde darin km-/ha-Werte
    - Gib den ersten passenden Treffer mit Kontext zurück
    """
    if not text:
        return None

    text_lower = text.lower()

    # Alle Positionen von Keywords sammeln
    keyword_positions = []
    for kw in keywords:
        kw_lower = kw.lower()
        start = 0
        while True:
            idx = text_lower.find(kw_lower, start)
            if idx == -1:
                break
            keyword_positions.append(idx)
            start = idx + len(kw_lower)

    if not keyword_positions:
        return None

    # Wir gehen nacheinander durch alle Keyword-Sätze
    for kw_pos in keyword_positions:
        sent_start, sent_end = _get_sentence_bounds(text, kw_pos)
        sentence = text[sent_start:sent_end]

        for match in pattern.finditer(sentence):
            num_str = match.group("number")
            mult_str = match.group("multiplier")

            value = _parse_quantity_with_multiplier(num_str, mult_str)
            if value is None:
                continue

            span_start = match.start()
            abs_pos = sent_start + span_start

            ctx = _build_context_snippet(text, abs_pos, abs_pos + len(num_str))
            return {
                "value": float(value),
                "ctx": ctx,
            }

    return None


# === C1: Küstenlinie wiederhergestellt (km) ==================================

COASTLINE_KEYWORDS = [
    "coastline restored",
    "restored coastline",
    "coastal program",
    "shoreline protection",
    "shoreline restored",
    "coastal restoration",
    "shoreline stabilization",
    "Küstenlinie wiederhergestellt",
    "Küstenschutzprogramm",
]

def detect_coastline_restored_total_km(text: str) -> Optional[Dict]:
    """
    Erkennt wiederhergestellte / stabilisierte Küstenlinie in km.
    """
    match = _find_best_match_for_pattern_near_keywords(
        text,
        DISTANCE_PATTERN,
        COASTLINE_KEYWORDS,
    )
    if not match:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "coastline_restored_total_km",
        "kpi_value": match["value"],
        "kpi_unit": "km",
        "ctx": match["ctx"],
    }


# === C2: Habitate wiederhergestellt (ha) =====================================

HABITAT_KEYWORDS = [
    "habitats were restored",
    "restored habitats",
    "mangrove habitats",
    "seagrass habitats",
    "wetlands were restored",
    "wetlands restored",
    "habitat restoration",
    "Habitatflächen wiederhergestellt",
    "Feuchtgebiete renaturiert",
]

def detect_habitat_restored_total_ha(text: str) -> Optional[Dict]:
    """
    Erkennt wiederhergestellte Habitate / Flächen in ha.
    """
    match = _find_best_match_for_pattern_near_keywords(
        text,
        AREA_PATTERN,
        HABITAT_KEYWORDS,
    )
    if not match:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "habitat_restored_total_ha",
        "kpi_value": match["value"],
        "kpi_unit": "ha",
        "ctx": match["ctx"],
    }
