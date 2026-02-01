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

# m³ units (ONLY valid trigger for quantitative KPIs)
VOLUME_UNIT_PATTERN = re.compile(
    r"(?:(million|millions|mio\.?|mrd\.?|bn|billion|thousand|k)\s*)?"
    r"(m3|m³|cubic\s*meters?|cubic\s*metres?)\b",
    re.IGNORECASE,
)

UNIT_ONLY_HINT = re.compile(r"\b(m3|m³|cubic\s*meters?|cubic\s*metres?)\b", re.IGNORECASE)

INTENSITY_HINT = re.compile(
    r"(kg|t|tonnes?|mg)\s*/\s*(m3|m³)|"
    r"(per|/)\s*(m3|m³)|"
    r"(m3|m³)\s*/\s*(ha|hectares?)",
    re.IGNORECASE,
)

WATER_CONTEXT_PATTERN = re.compile(
    r"\b(water|wastewater|effluent|discharge|abwasser|einleitung|"
    r"freshwater|groundwater|sewage)\b",
    re.IGNORECASE,
)

SECTION_HEADING_HINT = re.compile(r"^\s*\d+\.\s+[A-ZÄÖÜ]", re.UNICODE)

TARGET_LANGUAGE_HINT = re.compile(
    r"\b(target|aim|goal|by\s+20\d{2}|plan|intend|soll|werden|ziel)\b",
    re.IGNORECASE,
)

NON_VOLUME_CONTEXT_HINTS = re.compile(
    r"\b(people|persons?|students?|employees?|countries?|"
    r"percent|%|ratio|index|score|scope)\b",
    re.IGNORECASE,
)

WATER_HEADERS = {
    "withdrawal": ["water withdrawal", "water intake", "water abstraction", "wasserentnahme"],
    "consumption": ["water consumption", "water use", "wasserverbrauch"],
    "discharge": ["water discharge", "wastewater discharge", "abwassereinleitung"],
    "recycled": ["water recycling", "water reuse", "recycled water", "wasserrecycling"],
}

ROW_KPI_HINTS = {
    "withdrawal": ["withdraw", "intake", "abstraction", "entnahme"],
    "consumption": ["consumption", "use", "verbrauch"],
    "discharge": ["discharge", "effluent", "abwass"],
    "recycled": ["reuse", "recycle", "recycling", "reclaimed"],
}

INLINE_VOLUME_EXPR = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"(?P<mul>thousand|k|million|millions|mio\.?|mrd\.?|bn|billion)?\s*"
    r"(?P<unit>m3|m³|cubic\s*meters?|cubic\s*metres?)\b",
    re.IGNORECASE,
)


# =============================================================================
# Fuzzy helpers
# =============================================================================

def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _row_matches_any_trigger(row_l: str, triggers: List[str]) -> bool:
    for t in triggers:
        if t in row_l:
            return True
    if len(row_l) > 200:
        return False
    return any(_similar(row_l, t) >= 0.85 for t in triggers if len(t) >= 6)


def _infer_kpi_from_row(row_l: str) -> Optional[str]:
    for kpi_key, hints in ROW_KPI_HINTS.items():
        if any(h in row_l for h in hints):
            return kpi_key
    return None


# =============================================================================
# TABLE MODE – STRICT (m³ only)
# =============================================================================

def _extract_table_volumes(text: str, max_hits: int = 40) -> List[Dict]:
    rows = [l.strip() for l in text.splitlines() if l.strip()]
    hits: List[Dict] = []

    current_kpi: Optional[str] = None
    current_multiplier: Optional[str] = None
    unit_context = False
    unit_ttl = 0

    for row in rows:
        row_l = _norm_ws(row)

        if SECTION_HEADING_HINT.match(row):
            continue

        for kpi_key, triggers in WATER_HEADERS.items():
            if _row_matches_any_trigger(row_l, triggers):
                current_kpi = kpi_key
                break

        um = VOLUME_UNIT_PATTERN.search(row_l)
        if um:
            current_multiplier = um.group(1)
            unit_context = True
            unit_ttl = 4
            continue
        elif UNIT_ONLY_HINT.search(row_l):
            current_multiplier = None
            unit_context = True
            unit_ttl = 4
            continue
        else:
            if unit_ttl > 0:
                unit_ttl -= 1
            else:
                unit_context = False
                current_multiplier = None

        if not current_kpi:
            continue
        if INTENSITY_HINT.search(row_l):
            continue
        if TARGET_LANGUAGE_HINT.search(row_l):
            continue
        if NON_VOLUME_CONTEXT_HINTS.search(row_l):
            continue

        nums = list(NUMBER_PATTERN.finditer(row))
        if not nums:
            continue

        um = VOLUME_UNIT_PATTERN.search(row_l) or UNIT_ONLY_HINT.search(row_l)
        if not um:
            continue  # HARD RULE: no m³ unit → no quantitative KPI

        unit_pos = um.start()
        best = None
        best_dist = 10**9
        for m in nums:
            if YEAR_PATTERN.fullmatch(m.group(0)):
                continue
            dist = abs(m.start() - unit_pos)
            if dist < best_dist:
                best_dist = dist
                best = m

        if not best:
            continue

        try:
            value = _normalize_number(best.group(0))
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
# INLINE / NARRATIVE MODE – STRICT
# =============================================================================

def _infer_kpi_from_snippet(snippet_l: str) -> Optional[str]:
    if "discharge" in snippet_l or "effluent" in snippet_l:
        return "discharge"
    if "consumption" in snippet_l or "verbrauch" in snippet_l:
        return "consumption"
    if "withdraw" in snippet_l or "intake" in snippet_l or "abstraction" in snippet_l:
        return "withdrawal"
    if "recycling" in snippet_l or "reuse" in snippet_l:
        return "recycled"
    return None


def _extract_inline_volumes(text: str, max_hits: int = 20) -> List[Dict]:
    hits: List[Dict] = []

    for m in INLINE_VOLUME_EXPR.finditer(text):
        s, e = m.span()

        sent_s, sent_e = _get_sentence_bounds(text, s)
        sent = text[sent_s:sent_e]
        sent_l = sent.lower()

        if INTENSITY_HINT.search(sent_l):
            continue
        if TARGET_LANGUAGE_HINT.search(sent_l):
            continue

        kpi_bucket = _infer_kpi_from_snippet(sent_l)
        if not kpi_bucket:
            continue

        try:
            value = _normalize_number(m.group("num"))
        except ValueError:
            continue

        value = _apply_multiplier(value, m.group("mul"))

        hits.append({
            "kpi_key": f"water_{kpi_bucket}_total_m3",
            "value": value,
            "ctx": _build_context(text, s, e, window=120),
        })

        if len(hits) >= max_hits:
            return hits

    return hits


def _dedupe_hits(hits: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for h in hits:
        key = (h["kpi_key"], round(float(h["value"]), 3))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


# =============================================================================
# KPI DETECTORS
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


def detect_water_table_volumes(text: str) -> Optional[List[Dict]]:
    hits = _dedupe_hits(_extract_table_volumes(text) + _extract_inline_volumes(text))
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


def detect_water_pollutants_total_kg(text: str) -> Optional[Dict]:
    return None  # unchanged


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
    t = text.lower()
    if not any(o in t for o in ["water", "wasser", "abwasser", "wastewater"]):
        return None
    if any(v in t for v in ["reduce", "monitor", "optimize", "manage", "reduzieren", "überwachen"]):
        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_management_measures_flag",
            "kpi_value": 1,
            "kpi_unit": "flag",
            "ctx": "water management action detected",
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
# Legacy stubs (DO NOT REMOVE)
# =============================================================================

def detect_water_pollutants_concentration_mg_l(text: str):
    return None


def _parse_quantity_with_multiplier(raw_number: str, raw_multiplier: Optional[str]):
    try:
        value = _normalize_number(raw_number)
    except Exception:
        return None
    if not raw_multiplier:
        return value
    return value * MULTIPLIER_WORDS.get(raw_multiplier.lower().strip(), 1)
