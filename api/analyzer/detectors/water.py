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
# Patterns / Lexicons
# =============================================================================

YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")

# Units for volumes
VOLUME_UNIT_PATTERN = re.compile(
    r"(?:(million|millions|mio\.?|mrd\.?|bn|billion|thousand|k)\s*)?"
    r"(m3|m³|cubic\s*meters?|cubic\s*metres?)\b",
    re.IGNORECASE,
)

UNIT_ONLY_HINT = re.compile(r"\b(m3|m³|cubic\s*meters?|cubic\s*metres?)\b", re.IGNORECASE)

# Exclude intensities/ratios (these caused your earlier false positives like kg/m³)
INTENSITY_HINT = re.compile(
    r"\b(kg|t|tonnes?|g|mg)\s*/\s*(m3|m³)\b|"
    r"\b(per|/)\s*(m3|m³|cubic\s*meters?|cubic\s*metres?)\b|"
    r"\b(m3|m³)\s*/\s*(ha|hectares?)\b",
    re.IGNORECASE,
)

# Water context guard used for pollutants
WATER_CONTEXT_PATTERN = re.compile(
    r"\b(water|wastewater|effluent|discharge|abwasser|einleitung|gew[äa]sser|surface\s*water|"
    r"freshwater|groundwater|sewage|waste\s*water)\b",
    re.IGNORECASE,
)

# Target language filter (we’ll apply it ONLY for narrative matches by default)
TARGET_LANGUAGE_HINT = re.compile(
    r"\b(target|aim|goal|will|shall|plan|intend|by\s+20\d{2}|until\s+20\d{2}|"
    r"bis\s+20\d{2}|ziel|anstreben|soll|werden)\b",
    re.IGNORECASE,
)

# Rows that are clearly headings/TOC-like (e.g., "1. The Company")
SECTION_HEADING_HINT = re.compile(r"^\s*\d+\.\s+[A-ZÄÖÜ]", re.UNICODE)

# Common non-volume contexts: keep conservative, but DO NOT include "countries" etc. too aggressively for tables
NON_VOLUME_CONTEXT_HINTS = re.compile(
    r"\b(people|persons?|students?|minutes?|mins?|hours?|days?|"
    r"employees?|stations?|farmers?|"
    r"percent|%|share|ratio|index|score)\b",
    re.IGNORECASE,
)

# KPI header triggers
WATER_HEADERS = {
    "withdrawal": [
        "water withdrawal", "water withdrawals", "withdrawn water",
        "water intake", "freshwater intake", "water abstraction", "freshwater abstraction",
        "wasserentnahme", "entnahme von wasser",
        # tables in your doc:
        "water withdrawals by source", "withdrawals & recycling", "water withdrawals & recycling",
    ],
    "consumption": [
        "water consumption", "water consumed", "freshwater consumption",
        "water use", "total water use", "freshwater use",
        "wasserverbrauch", "wasserverbrauch gesamt",
        "water consumption", "total water consumption",
    ],
    "discharge": [
        "water discharge", "wastewater discharge", "effluent", "effluent discharge",
        "wastewater", "treated wastewater", "abwassereinleitung", "abwasser", "einleitung",
        "water discharge by destination", "total water discharge",
    ],
    "recycled": [
        "water recycling", "water reuse", "reused water", "recycled water",
        "reclaimed water", "water reclaimed",
        "wasserrecycling", "wasserrückgewinnung", "wiederverwendetes wasser",
        # tables in your doc:
        "recycling", "reuse and recycling", "water recycling and reuse",
    ],
}

ROW_KPI_HINTS = {
    "withdrawal": ["withdraw", "withdrawal", "intake", "abstraction", "entnahme"],
    "consumption": ["consume", "consumption", "use", "verbrauch", "nutzung"],
    "discharge": ["discharge", "effluent", "wastewater", "abwass", "einleitung"],
    "recycled": ["reuse", "reus", "recycle", "recycling", "reclaimed", "reclaim", "wiederverwend", "rückgewinn", "recycl"],
}

# Inline “value + multiplier + m3” pattern (captures narrative KPIs like "32 million m³ in 2024")
INLINE_VOLUME_EXPR = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<mul>thousand|k|million|millions|mio\.?|mrd\.?|bn|billion)?\s*"
    r"(?P<unit>m3|m³|cubic\s*meters?|cubic\s*metres?)\b",
    re.IGNORECASE,
)


# =============================================================================
# Lightweight fuzzy matching
# =============================================================================

def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _row_matches_any_trigger(row_l: str, triggers: List[str], fuzzy: bool = True) -> bool:
    for t in triggers:
        if t in row_l:
            return True

    if not fuzzy:
        return False

    if len(row_l) > 220:
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
# Text segmentation
# =============================================================================

def _iter_table_rows(text: str) -> List[str]:
    return [l.strip() for l in text.splitlines() if l.strip()]


# =============================================================================
# Core extraction – TABLE MODE (year-aware)
# =============================================================================

def _extract_table_volumes(text: str, max_hits: int = 80) -> List[Dict]:
    """
    Table-ish extraction for structures like:
        2021 2022 2023 2024
        Total water withdrawals 55 53 53 53
        ...
        Million m3

    Key idea:
    - Detect a YEAR header row => remember years + index of latest year
    - Detect a unit header row ("Million m3") => remember multiplier + TTL
    - For a data row under a year-header, pick the value at latest-year index
    """
    rows = _iter_table_rows(text)

    hits: List[Dict] = []

    current_kpi: Optional[str] = None

    table_years: List[int] = []
    latest_year_index: Optional[int] = None
    year_context_ttl = 0

    current_multiplier: Optional[str] = None
    unit_context_ttl = 0

    for row in rows:
        row_l = _norm_ws(row)

        # Skip obvious TOC/section headings
        if SECTION_HEADING_HINT.search(row):
            continue

        # --- KPI header detection ---
        for kpi_key, triggers in WATER_HEADERS.items():
            if _row_matches_any_trigger(row_l, triggers, fuzzy=True):
                current_kpi = kpi_key
                break

        # --- Year header detection ---
        years = [int(y) for y in YEAR_PATTERN.findall(row)]
        if len(years) >= 2:
            table_years = years
            latest_year = max(table_years)
            latest_year_index = table_years.index(latest_year)
            year_context_ttl = 12
            # continue; (don’t return; next rows are data)
            continue
        else:
            if year_context_ttl > 0:
                year_context_ttl -= 1
            else:
                table_years = []
                latest_year_index = None

        # --- Unit header detection ---
        um = VOLUME_UNIT_PATTERN.search(row_l)
        if um:
            current_multiplier = um.group(1)  # may be None
            unit_context_ttl = 12
            continue
        elif UNIT_ONLY_HINT.search(row_l):
            current_multiplier = None
            unit_context_ttl = 12
            continue
        else:
            if unit_context_ttl > 0:
                unit_context_ttl -= 1
            else:
                current_multiplier = None

        # Must have KPI bucket by header or row hints
        row_kpi = current_kpi or _infer_kpi_from_row(row_l)
        if not row_kpi:
            continue

        # Intensity rows are never totals
        if INTENSITY_HINT.search(row_l):
            continue

        # Avoid non-volume contexts in table rows only if row also looks narrative
        # (Tables can contain "countries" somewhere nearby; don’t kill them too hard.)
        if NON_VOLUME_CONTEXT_HINTS.search(row_l) and len(row_l) > 140:
            continue

        nums = NUMBER_PATTERN.findall(row)
        if not nums:
            continue

        # Reject numeric-only rows like "2" / "17"
        if re.fullmatch(r"\d+(?:[.,]\d+)?", row.strip()):
            continue

        picked_str: Optional[str] = None

        # If we have a year header context and enough numbers, pick the latest-year column
        if latest_year_index is not None and len(nums) >= (latest_year_index + 1):
            picked_str = nums[latest_year_index]
        else:
            # Otherwise: pick number closest to a unit token if present; else first non-year number
            unit_m = VOLUME_UNIT_PATTERN.search(row_l) or UNIT_ONLY_HINT.search(row_l)
            if unit_m:
                unit_pos = unit_m.start()
                best = None
                best_dist = 10**9
                for m in NUMBER_PATTERN.finditer(row):
                    if YEAR_PATTERN.fullmatch(m.group(0)):
                        continue
                    dist = abs(m.start() - unit_pos)
                    if dist < best_dist:
                        best_dist = dist
                        best = m.group(0)
                picked_str = best
            else:
                # Conservative: only accept if we recently saw a unit header
                if unit_context_ttl <= 0:
                    continue
                for n in nums:
                    if YEAR_PATTERN.fullmatch(n):
                        continue
                    picked_str = n
                    break

        if not picked_str:
            continue

        try:
            value = _normalize_number(picked_str)
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
# Core extraction – INLINE/NARRATIVE MODE
# =============================================================================

def _infer_kpi_from_snippet(snippet_l: str) -> Optional[str]:
    # strongest disambiguation first
    if "discharge" in snippet_l or "wastewater" in snippet_l or "effluent" in snippet_l or "abwass" in snippet_l:
        return "discharge"
    if "consumption" in snippet_l or "consumed" in snippet_l or "verbrauch" in snippet_l:
        return "consumption"
    if "withdraw" in snippet_l or "withdrawal" in snippet_l or "intake" in snippet_l or "abstraction" in snippet_l or "entnahme" in snippet_l:
        return "withdrawal"
    if "recycling" in snippet_l or "recycle" in snippet_l or "reuse" in snippet_l or "reclaimed" in snippet_l or "rückgewinn" in snippet_l:
        return "recycled"
    return None


def _extract_inline_volumes(text: str, max_hits: int = 40) -> List[Dict]:
    hits: List[Dict] = []

    for m in INLINE_VOLUME_EXPR.finditer(text):
        s, e = m.span()

        # quick intensity guard (e.g., kg/m³) – check small window around match
        near = text[max(0, s - 40): min(len(text), e + 40)].lower()
        if INTENSITY_HINT.search(near):
            continue

        # avoid targets/goals for narrative totals (these are often not “actuals”)
        sent_s, sent_e = _get_sentence_bounds(text, s)
        sent = text[sent_s:sent_e]
        sent_l = sent.lower()
        if TARGET_LANGUAGE_HINT.search(sent_l):
            continue

        kpi_bucket = _infer_kpi_from_snippet(sent_l)
        if not kpi_bucket:
            # fallback: look a bit wider
            snippet_l = _build_context(text, s, e, window=140).lower()
            kpi_bucket = _infer_kpi_from_snippet(snippet_l)

        if not kpi_bucket:
            continue

        try:
            value = _normalize_number(m.group("num"))
        except ValueError:
            continue

        value = _apply_multiplier(value, m.group("mul"))

        hits.append(
            {
                "kpi_key": f"water_{kpi_bucket}_total_m3",
                "value": value,
                "ctx": _build_context(text, s, e, window=140),
            }
        )

        if len(hits) >= max_hits:
            return hits

    return hits


def _dedupe_hits(hits: List[Dict]) -> List[Dict]:
    # Very lightweight dedupe: same kpi_key + same value (rounded) => keep first
    seen = set()
    out = []
    for h in hits:
        key = (h.get("kpi_key"), round(float(h.get("value", 0.0)), 6))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


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
# A1–A4 – Quantitative Volumes (table + inline)
# =============================================================================

def detect_water_table_volumes(text: str) -> Optional[List[Dict]]:
    table_hits = _extract_table_volumes(text)
    inline_hits = _extract_inline_volumes(text)

    hits = _dedupe_hits(table_hits + inline_hits)
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
    for m in POLLUTANT_TOTAL_PATTERN.finditer(text):
        if not _has_water_context_near(text, *m.span(), window=160):
            continue

        ctx = _build_context(text, *m.span(), window=160)
        ctx_l = ctx.lower()

        # avoid intensity contexts
        if INTENSITY_HINT.search(ctx_l) or "mg/l" in ctx_l:
            continue

        try:
            value = _normalize_number(m.group(1))
        except ValueError:
            continue

        unit = m.group(2).lower()
        if unit.startswith("t"):
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
                    "ctx": _build_context(text, s, e, window=160),
                }

    return None


# =============================================================================
# Backwards-compatible wrappers (API stability)
# IMPORTANT: These return the combined list (withdrawal/consumption/discharge/recycled),
# and your analyzer should extend/flatten lists (as in your current setup).
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
# Legacy stub
# =============================================================================

def detect_water_pollutants_concentration_mg_l(text: str):
    return None


# =============================================================================
# Legacy compatibility helper (do NOT remove – required by other detectors)
# =============================================================================

def _parse_quantity_with_multiplier(raw_number: str, raw_multiplier: Optional[str]):
    try:
        value = _normalize_number(raw_number)
    except Exception:
        return None

    if not raw_multiplier:
        return value

    return value * MULTIPLIER_WORDS.get(raw_multiplier.lower().strip(), 1)
