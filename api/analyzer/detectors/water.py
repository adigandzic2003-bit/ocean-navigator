import re
from typing import Optional, Dict, List


# =============================================================================
# Shared helpers (stable API)
# =============================================================================

def _build_context(text: str, start: int, end: int, window: int = 80) -> str:
    return text[max(0, start - window): min(len(text), end + window)].replace("\n", " ").strip()


def _build_context_snippet(text: str, start: int, end: int, window: int = 80) -> str:
    return _build_context(text, start, end, window)


# =============================================================================
# Number parsing
# =============================================================================

MULTIPLIER_WORDS = {
    "million": 1_000_000,
    "millions": 1_000_000,
    "mio": 1_000_000,
    "mio.": 1_000_000,
    "millionen": 1_000_000,
    "billion": 1_000_000_000,
    "bn": 1_000_000_000,
    "mrd": 1_000_000_000,
    "mrd.": 1_000_000_000,
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


def _apply_multiplier(value: float, multiplier: Optional[str]) -> float:
    if not multiplier:
        return value
    return value * MULTIPLIER_WORDS.get(multiplier.lower().strip(), 1)


# =============================================================================
# Table-aware segmentation
# =============================================================================

YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")
UNIT_PATTERN = re.compile(r"(million|mio\.?|mrd\.?)?\s*(m3|m³)", re.IGNORECASE)

WATER_HEADERS = {
    "withdrawal": ["water withdrawal", "water withdrawals", "wasserentnahme"],
    "consumption": ["water consumption", "wasserverbrauch"],
    "discharge": ["water discharge", "abwassereinleitung", "wastewater"],
    "recycled": ["water recycling", "water reuse", "wasserrecycling"],
}


def _iter_table_rows(text: str) -> List[str]:
    return [l.strip() for l in text.splitlines() if l.strip()]


# =============================================================================
# Core table-driven volume extraction
# =============================================================================

def _extract_table_volumes(text: str, max_hits: int = 20) -> List[Dict]:
    rows = _iter_table_rows(text)

    current_kpi: Optional[str] = None
    current_multiplier: Optional[str] = None
    hits: List[Dict] = []

    for row in rows:
        row_l = row.lower()

        # --- KPI header detection ---
        for kpi_key, triggers in WATER_HEADERS.items():
            if any(t in row_l for t in triggers):
                current_kpi = kpi_key

        # --- Unit detection (table header like "Million m3") ---
        unit_match = UNIT_PATTERN.search(row_l)
        if unit_match:
            current_multiplier = unit_match.group(1)

        # --- Numeric row (likely data row) ---
        if current_kpi and current_multiplier and NUMBER_PATTERN.search(row):
            numbers = NUMBER_PATTERN.findall(row)

            for num in numbers:
                try:
                    value = _normalize_number(num)
                except ValueError:
                    continue

                value = _apply_multiplier(value, current_multiplier)

                hits.append({
                    "kpi_key": f"water_{current_kpi}_total_m3",
                    "value": value,
                    "ctx": row,
                })

                if len(hits) >= max_hits:
                    return hits

    return hits


# =============================================================================
# A0 – Mention
# =============================================================================

def detect_water_mention(text: str) -> Optional[Dict]:
    if "water" in text.lower() or "wasser" in text.lower():
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
# A1–A4 – Table-first quantitative KPIs
# =============================================================================

def detect_water_table_volumes(text: str) -> Optional[List[Dict]]:
    hits = _extract_table_volumes(text)
    if not hits:
        return None

    return [
        {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": h["kpi_key"],
            "kpi_value": h["value"],
            "kpi_unit": "m3",
            "ctx": h["ctx"],
        }
        for h in hits
    ]


# =============================================================================
# A5–A6 – Pollutants (already table-friendly)
# =============================================================================

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
# A7–A8 – Qualitative
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

# =============================================================================
# Backwards-compatible wrappers (API stability)
# =============================================================================

def detect_water_withdrawal_total_m3(text: str):
    return detect_water_table_volumes(text)


def detect_water_consumption_total_m3(text: str):
    return detect_water_table_volumes(text)


def detect_water_recycled_total_m3(text: str):
    return detect_water_table_volumes(text)


def detect_water_discharge_total_m3(text: str):
    return detect_water_table_volumes(text)

# =============================================================================
# Backwards-compatible wrappers for legacy analyzer imports
# =============================================================================

def detect_water_pollutants_concentration_mg_l(text: str):
    """
    Legacy wrapper.
    Konzentrationswerte werden aktuell nicht tabellenbasiert extrahiert,
    daher bewusst None (keine KPI).
    """
    return None


