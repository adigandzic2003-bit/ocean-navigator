import re
from typing import Optional, Dict, List


# =============================================================================
# Shared helpers (stable API – do NOT rename lightly)
# =============================================================================

def _build_context(text: str, start: int, end: int, window: int = 80) -> str:
    return text[max(0, start - window): min(len(text), end + window)].replace("\n", " ").strip()


# Backwards compatibility for other detectors
def _build_context_snippet(text: str, start: int, end: int, window: int = 80) -> str:
    return _build_context(text, start, end, window)


def _get_sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    start = pos
    while start > 0 and text[start - 1] not in ".!?":
        start -= 1
    end = pos
    while end < len(text) and text[end] not in ".!?":
        end += 1
    return start, min(len(text), end + 1)


# =============================================================================
# Text segmentation (tables + narrative)
# =============================================================================

def _split_into_analysis_units(text: str) -> list[str]:
    """
    Creates analysis units:
    - normal narrative lines
    - table-like lines with numbers
    """
    if not text:
        return []

    units: list[str] = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        units.append(clean)
    return units


# =============================================================================
# Number parsing
# =============================================================================

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


# =============================================================================
# Volume patterns (m3)
# =============================================================================

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


def _find_volume_hits(
    text: str,
    keywords: list[str],
    max_hits: int = 3,
) -> list[Dict]:
    hits: list[Dict] = []
    units = _split_into_analysis_units(text)

    for unit in units:
        ul = unit.lower()
        if not any(kw.lower() in ul for kw in keywords):
            continue

        for m in WATER_VOLUME_PATTERN.finditer(unit):
            value = _parse_quantity_with_multiplier(m.group("number"), m.group("multiplier"))
            if value is None:
                continue

            hits.append({
                "value": float(value),
                "ctx": unit,
            })

            if len(hits) >= max_hits:
                return hits

    return hits


# =============================================================================
# A0 – Water mention
# =============================================================================

def detect_water_mention(text: str) -> Optional[Dict]:
    if text and ("water" in text.lower() or "wasser" in text.lower()):
        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_mention_flag",
            "kpi_value": 1,
            "kpi_unit": "flag",
            "ctx": "water mentioned in text",
        }
    return None


# =============================================================================
# A1–A4 – Quantitative water KPIs (multi-hit)
# =============================================================================

def _build_volume_kpis(text: str, keywords: list[str], kpi_key: str) -> Optional[List[Dict]]:
    hits = _find_volume_hits(text, keywords)
    if not hits:
        return None

    return [
        {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": kpi_key,
            "kpi_value": h["value"],
            "kpi_unit": "m3",
            "ctx": h["ctx"],
        }
        for h in hits
    ]


def detect_water_withdrawal_total_m3(text: str) -> Optional[List[Dict]]:
    return _build_volume_kpis(
        text,
        ["withdrawal", "water abstraction", "wasserentnahme"],
        "water_withdrawal_total_m3",
    )


def detect_water_consumption_total_m3(text: str) -> Optional[List[Dict]]:
    return _build_volume_kpis(
        text,
        ["water consumption", "water consumed", "wasserverbrauch"],
        "water_consumption_total_m3",
    )


def detect_water_recycled_total_m3(text: str) -> Optional[List[Dict]]:
    return _build_volume_kpis(
        text,
        ["recycled water", "water reuse", "wasserrecycling"],
        "water_recycled_total_m3",
    )


def detect_water_discharge_total_m3(text: str) -> Optional[List[Dict]]:
    return _build_volume_kpis(
        text,
        ["wastewater", "effluent", "abwassereinleitung"],
        "water_discharge_total_m3",
    )


# =============================================================================
# A5–A6 – Pollutants
# =============================================================================

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


# =============================================================================
# A7–A8 – Qualitative KPIs
# =============================================================================

def detect_water_stress_flag(text: str) -> Optional[Dict]:
    if any(k in text.lower() for k in ["water stress", "water scarcity", "wasserstress", "arid"]):
        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_stress_flag",
            "kpi_value": 1,
            "kpi_unit": "flag",
            "ctx": "water stress context detected",
        }
    return None


def detect_water_management_measures_flag(text: str) -> Optional[Dict]:
    if any(v in text.lower() for v in ["reduce", "monitor", "optimize", "manage", "reduzieren", "überwachen"]) \
       and any(o in text.lower() for o in ["water", "wasser", "abwasser"]):
        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_management_measures_flag",
            "kpi_value": 1,
            "kpi_unit": "flag",
            "ctx": "water-related management action",
        }
    return None
