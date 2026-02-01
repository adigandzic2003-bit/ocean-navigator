import re
from difflib import SequenceMatcher
from typing import Optional, Dict, List, Tuple

# =============================================================================
# Helpers
# =============================================================================

def _build_context(text: str, start: int, end: int, window: int = 80) -> str:
    return text[max(0, start - window): min(len(text), end + window)].replace("\n", " ").strip()


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
    "k": 1_000,
    "thousand": 1_000,
    "million": 1_000_000,
    "millions": 1_000_000,
    "mio": 1_000_000,
    "mio.": 1_000_000,
    "millionen": 1_000_000,
    "bn": 1_000_000_000,
    "billion": 1_000_000_000,
    "mrd": 1_000_000_000,
    "mrd.": 1_000_000_000,
}


def _normalize_number(num: str) -> float:
    s = num.strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        s = s.replace(",", ".") if len(parts[-1]) <= 2 else s.replace(",", "")
    return float(s)


def _apply_multiplier(value: float, mult: Optional[str]) -> float:
    if not mult:
        return value
    return value * MULTIPLIER_WORDS.get(mult.lower(), 1)


# =============================================================================
# Patterns
# =============================================================================

YEAR = re.compile(r"\b20\d{2}\b")
NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")

VOLUME_UNIT = re.compile(
    r"(?:(million|millions|mio\.?|bn|billion|thousand|k)\s*)?"
    r"(m3|m³|cubic\s*meters?|cubic\s*metres?)\b",
    re.I,
)

INTENSITY = re.compile(r"(kg|t|mg)\s*/\s*m3|m3\s*/\s*(ha|kg)|per\s*m3", re.I)

WATER_CTX = re.compile(
    r"\b(water|wastewater|effluent|discharge|freshwater|abwasser|einleitung)\b", re.I
)

TARGET_LANG = re.compile(
    r"\b(target|aim|goal|by\s+20\d{2}|until\s+20\d{2}|reduce|reduction)\b", re.I
)

SECTION_HEADING = re.compile(r"^\s*\d+\.\s+[A-Z]", re.UNICODE)

NON_VOLUME = re.compile(
    r"\b(people|percent|%|employees|countries|students|minutes|hours|days|ratio|index)\b",
    re.I,
)

INLINE_VOLUME = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<mul>million|millions|mio\.?|bn|billion|thousand|k)?\s*"
    r"(?P<unit>m3|m³|cubic\s*meters?|cubic\s*metres?)\b",
    re.I,
)

# =============================================================================
# KPI semantics
# =============================================================================

KPI_HEADERS = {
    "withdrawal": ["water withdrawal", "water intake", "water abstraction"],
    "consumption": ["water consumption", "water consumed", "water use"],
    "discharge": ["water discharge", "wastewater discharge", "effluent"],
    "recycled": ["water recycling", "water reuse", "recycled water"],
}


def _infer_bucket(text_l: str) -> Optional[str]:
    for k, terms in KPI_HEADERS.items():
        if any(t in text_l for t in terms):
            return k
    return None


# =============================================================================
# TABLE extraction (conservative)
# =============================================================================

def _extract_table_totals(text: str) -> List[Dict]:
    rows = [r.strip() for r in text.splitlines() if r.strip()]
    hits = []

    current_kpi = None
    unit_mult = None
    unit_ttl = 0

    for row in rows:
        row_l = _norm_ws(row)

        if SECTION_HEADING.match(row):
            continue

        # KPI header
        for k, terms in KPI_HEADERS.items():
            if any(t in row_l for t in terms):
                current_kpi = k
                break

        # unit header
        um = VOLUME_UNIT.search(row_l)
        if um:
            unit_mult = um.group(1)
            unit_ttl = 4
            continue
        elif unit_ttl > 0:
            unit_ttl -= 1
        else:
            unit_mult = None

        if not current_kpi:
            continue

        if INTENSITY.search(row_l) or NON_VOLUME.search(row_l):
            continue

        nums = NUMBER.findall(row)
        if not nums:
            continue

        # reject pure years / list numbers
        nums = [n for n in nums if not YEAR.fullmatch(n)]
        if len(nums) != 1:
            continue

        try:
            value = _normalize_number(nums[0])
        except Exception:
            continue

        value = _apply_multiplier(value, unit_mult)

        hits.append(
            {
                "kpi_key": f"water_{current_kpi}_total_m3",
                "value": value,
                "ctx": row,
            }
        )

    return hits


# =============================================================================
# INLINE extraction (strict)
# =============================================================================

def _extract_inline_totals(text: str) -> List[Dict]:
    hits = []

    for m in INLINE_VOLUME.finditer(text):
        s, e = m.span()
        sent_s, sent_e = _get_sentence_bounds(text, s)
        sent = text[sent_s:sent_e]
        sent_l = sent.lower()

        if TARGET_LANG.search(sent_l):
            continue
        if INTENSITY.search(sent_l) or NON_VOLUME.search(sent_l):
            continue

        bucket = _infer_bucket(sent_l)
        if not bucket:
            continue

        try:
            value = _normalize_number(m.group("num"))
        except Exception:
            continue

        value = _apply_multiplier(value, m.group("mul"))

        hits.append(
            {
                "kpi_key": f"water_{bucket}_total_m3",
                "value": value,
                "ctx": _build_context(text, s, e, 120),
            }
        )

    return hits


# =============================================================================
# Public detectors
# =============================================================================

def detect_water_mention(text: str) -> Optional[Dict]:
    if "water" in text.lower():
        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_mention_flag",
            "kpi_value": 1,
            "kpi_unit": "flag",
            "ctx": "water mentioned",
        }
    return None


def detect_water_table_volumes(text: str) -> Optional[List[Dict]]:
    hits = _extract_table_totals(text) + _extract_inline_totals(text)
    if not hits:
        return None

    # dedupe by key+value
    seen = set()
    out = []
    for h in hits:
        key = (h["kpi_key"], round(h["value"], 3))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "record_type": "kpi",
                "source_type": "kpi",
                "company": None,
                "kpi_key": h["kpi_key"],
                "kpi_value": h["value"],
                "kpi_unit": "m3",
                "ctx": h["ctx"],
            }
        )
    return out


def detect_water_withdrawal_total_m3(text: str):
    return detect_water_table_volumes(text)


def detect_water_consumption_total_m3(text: str):
    return detect_water_table_volumes(text)


def detect_water_recycled_total_m3(text: str):
    return detect_water_table_volumes(text)


def detect_water_discharge_total_m3(text: str):
    return detect_water_table_volumes(text)


def detect_water_pollutants_total_kg(text: str) -> Optional[Dict]:
    return None  # bewusst nicht Kernfokus im Prototyp


def detect_water_pollutants_concentration_mg_l(text: str):
    return None


def detect_water_stress_flag(text: str) -> Optional[Dict]:
    if re.search(r"water stress|water scarcity|wasserstress", text, re.I):
        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_stress_flag",
            "kpi_value": 1,
            "kpi_unit": "flag",
            "ctx": "water stress context",
        }
    return None


def detect_water_management_measures_flag(text: str) -> Optional[Dict]:
    if re.search(r"(water).*(manage|reduce|optimi|monitor)", text, re.I):
        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_management_measures_flag",
            "kpi_value": 1,
            "kpi_unit": "flag",
            "ctx": "water management measures",
        }
    return None
# =============================================================================
# Legacy compatibility helper (REQUIRED by coastal / jobs detectors)
# DO NOT REMOVE
# =============================================================================

def _parse_quantity_with_multiplier(raw_number: str, raw_multiplier: Optional[str]):
    """
    Legacy helper used by coastal / jobs detectors.
    Kept for backward compatibility.
    """
    try:
        value = _normalize_number(raw_number)
    except Exception:
        return None

    if not raw_multiplier:
        return value

    return value * MULTIPLIER_WORDS.get(raw_multiplier.lower().strip(), 1)
