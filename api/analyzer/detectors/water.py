import re
from difflib import SequenceMatcher
from typing import Optional, Dict, List, Tuple

# =============================================================================
# Shared helpers (stable API)
# =============================================================================

def _build_context(text: str, start: int, end: int, window: int = 80) -> str:
    return (
        text[max(0, start - window): min(len(text), end + window)]
        .replace("\n", " ")
        .strip()
    )


def _build_context_snippet(text: str, start: int, end: int, window: int = 80) -> str:
    return _build_context(text, start, end, window)


def _get_sentence_bounds(text: str, pos: int) -> Tuple[int, int]:
    """
    Legacy helper used by other detectors (coastal/jobs).
    Simple sentence boundary detection around position pos.
    """
    start = pos
    while start > 0 and text[start - 1] not in ".!?":
        start -= 1

    end = pos
    while end < len(text) and text[end] not in ".!?":
        end += 1

    return start, min(len(text), end + 1)


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


# =============================================================================
# Number parsing
# =============================================================================

MULTIPLIER_WORDS = {
    "thousand": 1_000,
    "k": 1_000,
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
        # Decide by last separator which is decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        # If last part is 1-2 digits, likely decimal comma
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
# Patterns / Lexicons
# =============================================================================

YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")

# Accept "m3", "m³", optional "cubic meters", and optional multiplier words.
# - multiplier group is optional: we'll still extract m3 values without it.
VOLUME_UNIT_PATTERN = re.compile(
    r"(?:(million|millions|mio\.?|mrd\.?|bn|billion|thousand|k)\s*)?"
    r"(m3|m³|cubic\s*meters?|cubic\s*metres?)\b",
    re.IGNORECASE,
)

# For table-style headers, also accept unit-only lines ("m3") without "million".
UNIT_ONLY_HINT = re.compile(r"\b(m3|m³|cubic\s*meters?|cubic\s*metres?)\b", re.IGNORECASE)

# Water context guard for ambiguous units like "kg" in long ESG docs
WATER_CONTEXT_PATTERN = re.compile(
    r"\b(water|wastewater|effluent|discharge|abwasser|einleitung|gew[äa]sser|surface\s*water|"
    r"freshwater|groundwater|sewage|waste\s*water)\b",
    re.IGNORECASE,
)

# Extend triggers to catch marketing/variation without ML
WATER_HEADERS = {
    "withdrawal": [
        "water withdrawal", "water withdrawals", "withdrawn water",
        "water intake", "freshwater intake", "water abstraction", "freshwater abstraction",
        "wasserentnahme", "entnahme von wasser",
    ],
    "consumption": [
        "water consumption", "water consumed", "freshwater consumption",
        "water use", "total water use", "freshwater use",
        "wasserverbrauch", "wasserverbrauch gesamt",
    ],
    "discharge": [
        "water discharge", "wastewater discharge", "effluent", "effluent discharge",
        "wastewater", "treated wastewater", "abwassereinleitung", "abwasser", "einleitung",
    ],
    "recycled": [
        "water recycling", "water reuse", "reused water", "recycled water",
        "reclaimed water", "water reclaimed",
        "wasserrecycling", "wasserrückgewinnung", "wiederverwendetes wasser",
    ],
}

# Optional synonyms to decide a KPI from a row even if header wasn't captured.
ROW_KPI_HINTS = {
    "withdrawal": ["withdraw", "intake", "abstraction", "entnahme"],
    "consumption": ["consume", "consumption", "use", "verbrauch", "nutzung"],
    "discharge": ["discharge", "effluent", "wastewater", "abwass", "einleitung"],
    "recycled": ["reuse", "reus", "recycle", "reclaim", "wiederverwend", "rückgewinn", "recycl"],
}


# =============================================================================
# Lightweight fuzzy matching (no external deps)
# =============================================================================

def _similar(a: str, b: str) -> float:
    # Cheap fuzzy ratio for header-like lines
    return SequenceMatcher(None, a, b).ratio()


def _row_matches_any_trigger(row_l: str, triggers: List[str], fuzzy: bool = True) -> bool:
    # Exact substring fast-path
    for t in triggers:
        if t in row_l:
            return True

    if not fuzzy:
        return False

    # Fuzzy only on short-ish rows (header-ish)
    if len(row_l) > 180:
        return False

    # Compare against triggers with moderate threshold
    for t in triggers:
        if len(t) < 6:
            continue
        if _similar(row_l, t) >= 0.84:
            return True
    return False


def _infer_kpi_from_row(row_l: str) -> Optional[str]:
    for kpi_key, hints in ROW_KPI_HINTS.items():
        if any(h in row_l for h in hints):
            return kpi_key
    return None


# =============================================================================
# Table-aware segmentation
# =============================================================================

def _iter_table_rows(text: str) -> List[str]:
    # Keep order; strip empties
    return [l.strip() for l in text.splitlines() if l.strip()]


# =============================================================================
# Core table-driven volume extraction (improved)
# =============================================================================

def _extract_table_volumes(text: str, max_hits: int = 50) -> List[Dict]:
    """
    Extract water-related volume KPIs from table-ish text.

    Improvements vs. old version:
    - Accept m3/m³ even without "million" multipliers.
    - Keep 'current_multiplier' optional; defaults to 1.
    - Fuzzy header detection for minor variations/typos.
    - Row-level KPI inference if header not set.
    - Avoid exploding on random numeric lines by requiring a unit hint
      either in current header context or in the same row.
    """
    rows = _iter_table_rows(text)

    current_kpi: Optional[str] = None
    current_multiplier: Optional[str] = None
    have_unit_context: bool = False  # tracks if we saw any m3 unit near header recently

    hits: List[Dict] = []

    for row in rows:
        row_l = _norm_ws(row)

        # --- KPI header detection (exact + fuzzy) ---
        for kpi_key, triggers in WATER_HEADERS.items():
            if _row_matches_any_trigger(row_l, triggers, fuzzy=True):
                current_kpi = kpi_key
                # When KPI header changes, we keep unit context but don't force it
                # (unit may be in next line)
                break

        # --- Unit detection (header lines like "million m3" or just "m3") ---
        unit_match = VOLUME_UNIT_PATTERN.search(row_l)
        if unit_match:
            current_multiplier = unit_match.group(1)  # may be None
            have_unit_context = True
        elif UNIT_ONLY_HINT.search(row_l):
            # Unit without multiplier
            current_multiplier = None
            have_unit_context = True

        # --- Determine if this row is a numeric data row ---
        if not NUMBER_PATTERN.search(row):
            continue

        # For extraction, we require a unit hint either:
        # - in this same row, or
        # - previously in header context (have_unit_context)
        row_has_unit = bool(UNIT_ONLY_HINT.search(row_l) or VOLUME_UNIT_PATTERN.search(row_l))
        if not (row_has_unit or have_unit_context):
            continue

        # KPI decision:
        # - prefer current_kpi from header
        # - otherwise infer from the row text itself
        row_kpi = current_kpi or _infer_kpi_from_row(row_l)
        if not row_kpi:
            continue

        # Extract numbers
        numbers = NUMBER_PATTERN.findall(row)
        if not numbers:
            continue

        for num in numbers:
            try:
                value = _normalize_number(num)
            except ValueError:
                continue

            value = _apply_multiplier(value, current_multiplier)

            hits.append(
                {
                    "kpi_key": f"water_{row_kpi}_total_m3",
                    "value": value,
                    "ctx": row,
                }
            )

            if len(hits) >= max_hits:
                return hits

    return hits


# =============================================================================
# A0 – Mention
# =============================================================================

def detect_water_mention(text: str) -> Optional[Dict]:
    t = text.lower()
    if "water" in t or "wasser" in t:
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
# A5–A6 – Pollutants
# =============================================================================

# Improve: prevent matching random "kg" unrelated to water by requiring water-context near match.
POLLUTANT_TOTAL_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|t|tonnes?)\b", re.IGNORECASE)


def _has_water_context_near(text: str, start: int, end: int, window: int = 120) -> bool:
    snippet = text[max(0, start - window): min(len(text), end + window)]
    return bool(WATER_CONTEXT_PATTERN.search(snippet))


def detect_water_pollutants_total_kg(text: str) -> Optional[Dict]:
    for m in POLLUTANT_TOTAL_PATTERN.finditer(text):
        # Guard: water context nearby, otherwise skip
        if not _has_water_context_near(text, *m.span(), window=140):
            continue

        try:
            value = _normalize_number(m.group(1))
        except ValueError:
            continue

        unit = m.group(2).lower()
        if unit.startswith("t"):  # t / tonne(s)
            value *= 1000.0

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
    t = text.lower()
    if any(k in t for k in ["water stress", "water scarcity", "wasserstress", "arid", "drought"]):
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
    """
    Slightly hardened:
    - Still simple and explainable
    - Avoids triggering on generic 'reduce' without water context nearby
    """
    t = text.lower()

    # Quick reject if no water-related term exists at all
    if not any(o in t for o in ["water", "wasser", "abwasser", "wastewater", "effluent"]):
        return None

    # Look for management verbs near a water token
    verbs = ["reduce", "reduced", "reducing", "monitor", "monitoring", "optimize", "optimize", "manage", "managed",
             "reduzieren", "reduziert", "überwachen", "optimieren", "managen", "steuern"]
    water_terms = ["water", "wasser", "abwasser", "wastewater", "effluent"]

    # Simple windowed co-occurrence: for each verb match, require water within +/-120 chars
    for v in verbs:
        for m in re.finditer(r"\b" + re.escape(v) + r"\b", t):
            s, e = m.span()
            snippet = t[max(0, s - 120): min(len(t), e + 120)]
            if any(w in snippet for w in water_terms):
                return {
                    "record_type": "kpi",
                    "source_type": "kpi",
                    "company": None,
                    "kpi_key": "water_management_measures_flag",
                    "kpi_value": 1,
                    "kpi_unit": "flag",
                    "ctx": _build_context(text, s, e),
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
# Backwards-compatible wrapper for legacy analyzer imports
# =============================================================================

def detect_water_pollutants_concentration_mg_l(text: str):
    """
    Legacy detector stub.
    Concentration KPIs (mg/L) are intentionally not extracted in this prototype.
    """
    return None


# =============================================================================
# Legacy compatibility stubs (do NOT remove – required by other detectors)
# =============================================================================

def _parse_quantity_with_multiplier(raw_number: str, raw_multiplier: Optional[str]):
    """
    Legacy helper for coastal/jobs detectors.
    Tabellenlogik nutzt eigene Pfade – hier nur Fallback.
    """
    try:
        value = _normalize_number(raw_number)
    except Exception:
        return None

    if not raw_multiplier:
        return value

    return value * MULTIPLIER_WORDS.get(raw_multiplier.lower().strip(), 1)
