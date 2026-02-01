# api/analyzer/detectors/water.py

import re
from typing import Optional, Dict, List

# --- Backwards compatibility for other detectors ----------------------------

def _build_context_snippet(text: str, start: int, end: int, window: int = 80) -> str:
    return _build_context(text, start, end, window)

# === A0: Einfacher Wasser-Mention-Flag ========================================


def detect_water_mention(text: str) -> Optional[Dict]:
    if not text:
        return None

    keywords = ["water", "wasser"]
    if any(kw in text.lower() for kw in keywords):
        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_mention_flag",
            "kpi_value": 1,
            "kpi_unit": "flag",
            "ctx": "text contains water reference",
        }

    return None


# === Gemeinsame Helfer ========================================================

MULTIPLIER_WORDS = {
    "million": 1_000_000,
    "millions": 1_000_000,
    "billion": 1_000_000_000,
    "billions": 1_000_000_000,
    "bn": 1_000_000_000,
    "mio": 1_000_000,
    "mio.": 1_000_000,
    "millionen": 1_000_000,
    "mrd": 1_000_000_000,
    "mrd.": 1_000_000_000,
    "milliarden": 1_000_000_000,
}


def _normalize_number(num_str: str) -> float:
    s = num_str.strip()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) <= 2:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    return float(s)


def _parse_quantity_with_multiplier(raw_number: str, raw_multiplier: Optional[str]) -> Optional[float]:
    try:
        base = _normalize_number(raw_number)
    except ValueError:
        return None

    if not raw_multiplier:
        return base

    return base * MULTIPLIER_WORDS.get(raw_multiplier.lower().strip(), 1)


WATER_VOLUME_PATTERN = re.compile(
    r"""
    (?P<number>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+)
    \s*
    (?P<multiplier>million|millions|billion|billions|bn|mio\.?|millionen|mrd\.?|milliarden)?
    \s*
    (?P<unit>m3|m³|cubic\s+meters?|kubikmeter)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _get_sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    start = pos
    while start > 0 and text[start - 1] not in ".!?":
        start -= 1
    end = pos
    while end < len(text) and text[end] not in ".!?":
        end += 1
    return start, min(len(text), end + 1)


def _build_context(text: str, start: int, end: int, window: int = 80) -> str:
    return text[max(0, start - window): min(len(text), end + window)].replace("\n", " ").strip()


def _first_match_for_keywords(text: str, keywords: List[str]) -> Optional[Dict]:
    text_lower = text.lower()
    for kw in keywords:
        idx = text_lower.find(kw.lower())
        if idx == -1:
            continue

        s_start, s_end = _get_sentence_bounds(text, idx)
        sentence = text[s_start:s_end]

        for m in WATER_VOLUME_PATTERN.finditer(sentence):
            value = _parse_quantity_with_multiplier(m.group("number"), m.group("multiplier"))
            if value is None:
                continue

            abs_start = s_start + m.start()
            return {
                "value": float(value),
                "ctx": _build_context(text, abs_start, abs_start + len(m.group(0))),
            }
    return None


# === A1: Gesamtwasserentnahme =================================================


def detect_water_withdrawal_total_m3(text: str) -> Optional[Dict]:
    keywords = ["withdrawal", "water abstraction", "wasserentnahme", "entnahme von wasser"]
    hit = _first_match_for_keywords(text, keywords)
    if not hit:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "water_withdrawal_total_m3",
        "kpi_value": hit["value"],
        "kpi_unit": "m3",
        "ctx": hit["ctx"],
    }


# === A2: Gesamtwasserverbrauch ===============================================


def detect_water_consumption_total_m3(text: str) -> Optional[Dict]:
    keywords = ["water consumption", "water consumed", "wasserverbrauch", "verbrauch von wasser"]
    hit = _first_match_for_keywords(text, keywords)
    if not hit:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "water_consumption_total_m3",
        "kpi_value": hit["value"],
        "kpi_unit": "m3",
        "ctx": hit["ctx"],
    }


# === A3: Wiederverwendetes Wasser =============================================


def detect_water_recycled_total_m3(text: str) -> Optional[Dict]:
    keywords = ["recycled water", "water reuse", "wasserwiederverwendung", "wasserrecycling"]
    hit = _first_match_for_keywords(text, keywords)
    if not hit:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "water_recycled_total_m3",
        "kpi_value": hit["value"],
        "kpi_unit": "m3",
        "ctx": hit["ctx"],
    }


# === A4: Wassereinleitung =====================================================


def detect_water_discharge_total_m3(text: str) -> Optional[Dict]:
    keywords = ["wastewater discharge", "effluent", "abwassereinleitung", "abwasser"]
    hit = _first_match_for_keywords(text, keywords)
    if not hit:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "water_discharge_total_m3",
        "kpi_value": hit["value"],
        "kpi_unit": "m3",
        "ctx": hit["ctx"],
    }


# === A5: Schadstoffkonzentration ==============================================


POLLUTANT_CONC_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mg\/l|ppm)", re.IGNORECASE)


def detect_water_pollutants_concentration_mg_l(text: str) -> Optional[Dict]:
    for m in POLLUTANT_CONC_PATTERN.finditer(text):
        try:
            value = float(m.group(1).replace(",", "."))
        except ValueError:
            continue

        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_pollutants_concentration_mg_l",
            "kpi_value": value,
            "kpi_unit": "mg/L",
            "ctx": _build_context(text, *m.span()),
        }
    return None


# === A6: Schadstofffracht =====================================================


POLLUTANT_TOTAL_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|t|tonnes?)", re.IGNORECASE)


def detect_water_pollutants_total_kg(text: str) -> Optional[Dict]:
    for m in POLLUTANT_TOTAL_PATTERN.finditer(text):
        try:
            value = _normalize_number(m.group(1))
        except ValueError:
            continue

        if m.group(2).startswith("t"):
            value *= 1000

        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_pollutants_total_kg",
            "kpi_value": value,
            "kpi_unit": "kg",
            "ctx": _build_context(text, *m.span()),
        }
    return None


# === A7: Wasserstress (qualitativ) ============================================


WATER_STRESS_KEYWORDS = [
    "water stress",
    "water scarcity",
    "wasserstress",
    "wasserknappheit",
    "arid",
    "semi-arid",
    "wasserarme region",
]


def detect_water_stress_flag(text: str) -> Optional[Dict]:
    text_l = text.lower()
    if any(kw in text_l for kw in WATER_STRESS_KEYWORDS):
        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_stress_flag",
            "kpi_value": 1,
            "kpi_unit": "flag",
            "ctx": "reference to water-stressed region or scarcity",
        }
    return None


# === A8: Wassermanagement-Maßnahmen (qualitativ) ==============================


MANAGEMENT_VERBS = [
    "reduce", "reducing", "optimize", "monitor", "manage", "improve",
    "reduzieren", "optimieren", "überwachen", "steuern", "verbessern",
]

MANAGEMENT_OBJECTS = [
    "water", "wasser", "abwasser", "water use", "water consumption",
    "wasserverbrauch", "wasserentnahme",
]


def detect_water_management_measures_flag(text: str) -> Optional[Dict]:
    t = text.lower()
    if any(v in t for v in MANAGEMENT_VERBS) and any(o in t for o in MANAGEMENT_OBJECTS):
        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_management_measures_flag",
            "kpi_value": 1,
            "kpi_unit": "flag",
            "ctx": "water-related management action detected",
        }
    return None
