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
VOLUME_UNIT_PATTERN = re.compile(
    r"(?:(million|millions|mio\.?|mrd\.?|bn|billion|thousand|k)\s*)?"
    r"(m3|m³|cubic\s*meters?|cubic\s*metres?)\b",
    re.IGNORECASE,
)

# Unit-only hint (m3) without multiplier
UNIT_ONLY_HINT = re.compile(r"\b(m3|m³|cubic\s*meters?|cubic\s*metres?)\b", re.IGNORECASE)

# Intensity patterns to EXCLUDE (kg/m³, m³/ha, per m³, etc.)
INTENSITY_HINT = re.compile(r"(/|per\s+)(m3|m³|cubic\s*meters?|cubic\s*metres?)\b", re.IGNORECASE)

# Water context guard for ambiguous units like "kg" in long ESG docs
WATER_CONTEXT_PATTERN = re.compile(
    r"\b(water|wastewater|effluent|discharge|abwasser|einleitung|gew[äa]sser|surface\s*water|"
    r"freshwater|groundwater|sewage|waste\s*water)\b",
    re.IGNORECASE,
)

# Exclude target/forward-looking statements for "total" KPIs
TARGET_LANGUAGE_HINT = re.compile(
    r"\b(target|aim|goal|will|shall|plan|intend|by\s+20\d{2}|until\s+20\d{2}|"
    r"bis\s+20\d{2}|ziel|anstreben|soll|werden)\b",
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
    "withdrawal": ["withdraw", "withdrawal", "intake", "abstraction", "entnahme"],
    "consumption": ["consume", "consumption", "use", "verbrauch", "nutzung"],
    "discharge": ["discharge", "effluent", "wastewater", "abwass", "einleitung"],
    "recycled": ["reuse", "reus", "recycle", "reclaimed", "reclaim", "wiederverwend", "rückgewinn", "recycl"],
}

# If a row contains these tokens, it is probably NOT a water volume KPI even if "water" appears.
# This is a pragmatic anti-noise list based on the false positives you observed.
NON_VOLUME_CONTEXT_HINTS = re.compile(
    r"\b(people|persons?|students?|minutes?|mins?|hours?|days?|borewells?|stations?|"
    r"farmers?|hectares?|ha\b|km\b|percent|%|share|ratio|index|score|"
    r"kg/m³|kg/m3|t/m³|mg/l|mg\/l)\b",
    re.IGNORECASE,
)


# =============================================================================
# Lightweight fuzzy matching (no external deps)
# =============================================================================

def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _row_matches_any_trigger(row_l: str, triggers: List[str], fuzzy: bool = True) -> bool:
    for t in triggers:
        if t in row_l:
            return True

    if not fuzzy:
        return False

    # Fuzzy only on short-ish rows (header-ish)
    if len(row_l) > 180:
        return False

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
    return [l.strip() for l in text.splitlines() if l.strip()]


# =============================================================================
# Core table-driven volume extraction (precision-hardened)
# =============================================================================

def _extract_table_volumes(text: str, max_hits: int = 50) -> List[Dict]:
    """
    Extract water-related volume KPIs from table-ish text.

    Precision upgrades (addresses your false positives):
    - Require explicit volume unit (m3/m³/...) either on the same row OR in unit header context.
    - Reject intensity rows (kg/m³, per m³, m³/ha, etc.).
    - Reject forward-looking/target language for "total" KPIs (aim/target/by 2030...).
    - Reject common non-volume contexts (people, minutes, % ...).
    - Avoid treating plain years (2024/2030) as volumes by itself.
    """
    rows = _iter_table_rows(text)

    current_kpi: Optional[str] = None
    current_multiplier: Optional[str] = None
    have_unit_context: bool = False
    unit_context_ttl: int = 0  # keeps unit context for N rows after seeing unit header

    hits: List[Dict] = []

    for row in rows:
        row_l = _norm_ws(row)

        # --- KPI header detection (exact + fuzzy) ---
        for kpi_key, triggers in WATER_HEADERS.items():
            if _row_matches_any_trigger(row_l, triggers, fuzzy=True):
                current_kpi = kpi_key
                break

        # --- Unit detection ---
        unit_match = VOLUME_UNIT_PATTERN.search(row_l)
        if unit_match:
            current_multiplier = unit_match.group(1)  # may be None
            have_unit_context = True
            unit_context_ttl = 8
        elif UNIT_ONLY_HINT.search(row_l):
            current_multiplier = None
            have_unit_context = True
            unit_context_ttl = 8
        else:
            # decay unit context after some rows to prevent "sticky unit" over the whole document
            if unit_context_ttl > 0:
                unit_context_ttl -= 1
            else:
                have_unit_context = False
                current_multiplier = None

        # --- Numeric row check ---
        if not NUMBER_PATTERN.search(row):
            continue

        # --- Guard: ignore trivial numeric-only rows like "2" / "17" / "4" ---
        if re.fullmatch(r"\d+(?:[.,]\d+)?", row.strip()):
            continue


        # --- Precision guards: reject obviously wrong contexts ---
        # 1) intensity
        if INTENSITY_HINT.search(row_l) or "kg/m" in row_l or "mg/l" in row_l:
            continue

        # 2) non-volume contexts (people/minutes/%/etc.)
        if NON_VOLUME_CONTEXT_HINTS.search(row_l):
            continue

        # 3) forward-looking/targets: skip to avoid turning goals into "total" KPIs
        if TARGET_LANGUAGE_HINT.search(row_l):
            continue

        # --- Unit requirement ---
        row_has_unit = bool(UNIT_ONLY_HINT.search(row_l) or VOLUME_UNIT_PATTERN.search(row_l))
        if not (row_has_unit or have_unit_context):
            # no unit on the row and no recent unit header context
            continue

        # --- Determine KPI bucket ---
        row_kpi = current_kpi or _infer_kpi_from_row(row_l)
        if not row_kpi:
            continue

        # --- Extract candidate numbers ---
        numbers = NUMBER_PATTERN.findall(row)
        if not numbers:
            continue

        # If row contains only a year and no other numeric, skip (avoid year-as-volume)
        # Example: "By 2030 ..." would be skipped already by TARGET_LANGUAGE_HINT,
        # but this helps other cases.
        only_years = all(YEAR_PATTERN.fullmatch(n) for n in numbers)
        if only_years:
            continue

        # Heuristic: in real tables, the value is often the first non-year number
        for num in numbers:
            # skip pure years
            if YEAR_PATTERN.fullmatch(num):
                continue

            try:
                value = _normalize_number(num)
            except ValueError:
                continue

            value = _apply_multiplier(value, current_multiplier)

            # sanity: prevent absurd tiny "1,2,3" enumerations from becoming volumes
            # if row starts with "1)" or "2)" and has no other strong evidence, skip
            if re.match(r"^\s*\d+\)\s*", row) and not row_has_unit:
                continue

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

POLLUTANT_TOTAL_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|t|tonnes?)\b", re.IGNORECASE)


def _has_water_context_near(text: str, start: int, end: int, window: int = 140) -> bool:
    snippet = text[max(0, start - window): min(len(text), end + window)]
    return bool(WATER_CONTEXT_PATTERN.search(snippet))


def detect_water_pollutants_total_kg(text: str) -> Optional[Dict]:
    """
    Precision hardened:
    - Requires water context near the match.
    - Skips % / ratios / intensity contexts.
    """
    for m in POLLUTANT_TOTAL_PATTERN.finditer(text):
        if not _has_water_context_near(text, *m.span(), window=160):
            continue

        ctx = _build_context(text, *m.span(), window=120)
        ctx_l = ctx.lower()

        # skip intensity / ratios
        if "kg/m" in ctx_l or "per m" in ctx_l or "mg/l" in ctx_l:
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
            "ctx": ctx,
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
    Explainable, windowed co-occurrence:
    - Requires water term
    - Requires a management verb within +/-120 chars
    """
    t = text.lower()

    if not any(o in t for o in ["water", "wasser", "abwasser", "wastewater", "effluent"]):
        return None

    verbs = [
        "reduce", "reduced", "reducing",
        "monitor", "monitoring",
        "optimize", "optimized", "optimizing",
        "manage", "managed", "managing",
        "reduzieren", "reduziert", "reduzierung",
        "überwachen", "optimieren",
        "managen", "steuern",
    ]
    water_terms = ["water", "wasser", "abwasser", "wastewater", "effluent"]

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
