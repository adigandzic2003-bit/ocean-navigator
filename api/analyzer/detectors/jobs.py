# api/analyzer/detectors/jobs_social.py

import re
from typing import Optional, Dict

from .water import _build_context_snippet, _get_sentence_bounds


NUMBER_PATTERN = re.compile(
    r"""
    (?P<number>
        \d{1,3}
        (?:[.,]\d{3})*      # Tausendergruppen
        (?:[.,]\d+)?        # Dezimalteil
        |
        \d+
    )
    """,
    re.VERBOSE,
)

PERCENT_PATTERN = re.compile(
    r"""
    (?P<number>
        \d{1,3}
        (?:[.,]\d+)?        # Dezimalteil bei Prozent
    )
    \s*%
    """,
    re.VERBOSE,
)


def _normalize_number_str(num_str: str) -> float:
    """
    Wandelt '18,000' / '18.000' / '42,5' sauber in float um.
    - Komma + 3 Ziffern dahinter -> Tausendertrennung (3,500 -> 3500)
    - Komma + 1–2 Ziffern dahinter -> Dezimal (42,5 -> 42.5)
    """
    s = num_str.strip()

    # Fall 1: hat Komma, aber keinen Punkt -> genauer betrachten
    if "," in s and "." not in s:
        parts = s.split(",")
        # z.B. '3,500' -> ['3','500']  => Tausendertrennzeichen
        if len(parts[-1]) == 3 and all(p.isdigit() for p in parts):
            s = "".join(parts)  # '3500'
        else:
            # z.B. '42,5' -> Dezimal
            s = s.replace(",", ".")
    # Fall 2: hat Punkt, aber kein Komma
    elif "." in s and "," not in s:
        parts = s.split(".")
        # z.B. '18.000' -> ['18','000'] => Tausendertrennzeichen
        if len(parts[-1]) == 3 and all(p.isdigit() for p in parts):
            s = "".join(parts)  # '18000'
        # z.B. '42.5' -> bereits Dezimal, unverändert lassen
    # Fall 3: hat beides -> gehe von ',' = Tausender, '.' = Dezimal aus
    elif "," in s and "." in s:
        s = s.replace(",", "")

    return float(s)

def _find_best_number_near_keywords(
    text: str,
    keywords: list[str],
    percent: bool = False,
) -> Optional[Dict]:
    """
    Sucht im Text nach einem der Keywords und findet im gleichen Satz
    die Zahl (oder Prozentzahl), die diesem Keyword am nächsten ist.
    Gibt value + ctx zurück.
    """
    if not text:
        return None

    text_lower = text.lower()
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

    kw_pos = keyword_positions[0]
    sent_start, sent_end = _get_sentence_bounds(text, kw_pos)
    sentence = text[sent_start:sent_end]

    pattern = PERCENT_PATTERN if percent else NUMBER_PATTERN

    candidates = []
    for m in pattern.finditer(sentence):
        num_str = m.group("number")
        try:
            value = _normalize_number_str(num_str)
        except ValueError:
            continue

        abs_pos = sent_start + m.start()
        dist = abs(abs_pos - kw_pos)
        ctx = _build_context_snippet(text, abs_pos, abs_pos + len(num_str))

        candidates.append(
            {
                "value": value,
                "ctx": ctx,
                "distance": dist,
            }
        )

    if not candidates:
        return None

    best = min(candidates, key=lambda c: c["distance"])
    return {"value": float(best["value"]), "ctx": best["ctx"]}


# === D1: Jobs created total ===================================================

JOBS_CREATED_KEYWORDS = [
    "jobs created",
    "new jobs",
    "new jobs created",
    "neu geschaffene arbeitsplätze",
    "neu geschaffene jobs",
]


def detect_jobs_created_total(text: str) -> Optional[Dict]:
    match = _find_best_number_near_keywords(text, JOBS_CREATED_KEYWORDS, percent=False)
    if not match:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "jobs_created_total",
        "kpi_value": match["value"],
        "kpi_unit": "jobs",
        "ctx": match["ctx"],
    }


# === D2: Jobs supported total ================================================

JOBS_SUPPORTED_KEYWORDS = [
    "jobs supported",
    "direct and indirect jobs",
    "supported jobs",
    "supported employment",
    "arbeitsplätze unterstützt",
    "geschaffene und gesicherte arbeitsplätze",
]


def detect_jobs_supported_total(text: str) -> Optional[Dict]:
    match = _find_best_number_near_keywords(text, JOBS_SUPPORTED_KEYWORDS, percent=False)
    if not match:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "jobs_supported_total",
        "kpi_value": match["value"],
        "kpi_unit": "jobs",
        "ctx": match["ctx"],
    }


# === D3: Women share in workforce (%) ========================================

WOMEN_SHARE_KEYWORDS = [
    "women employed",
    "share of women",
    "female employees",
    "women in the workforce",
    "frauenanteil",
    "frauen im unternehmen",
    "woman accounted for",
]


def detect_women_share_percent(text: str) -> Optional[Dict]:
    match = _find_best_number_near_keywords(text, WOMEN_SHARE_KEYWORDS, percent=True)
    if not match:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "women_share_percent",
        "kpi_value": match["value"],
        "kpi_unit": "%",
        "ctx": match["ctx"],
    }


# === D4: Local jobs share (%) ================================================

LOCAL_JOBS_SHARE_KEYWORDS = [
    "local jobs",
    "local employment",
    "local workforce",
    "lokale arbeitsplätze",
    "lokale beschäftigung",
    "local employees",
]


def detect_local_jobs_share_percent(text: str) -> Optional[Dict]:
    match = _find_best_number_near_keywords(text, LOCAL_JOBS_SHARE_KEYWORDS, percent=True)
    if not match:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "local_jobs_share_percent",
        "kpi_value": match["value"],
        "kpi_unit": "%",
        "ctx": match["ctx"],
    }
