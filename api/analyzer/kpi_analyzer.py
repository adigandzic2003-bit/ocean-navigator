# api/analyzer/kpi_analyzer.py

import os
import re
import html as ihtml
from typing import List, Dict, Any, Optional

# Filter A
from .relevance_filter import is_potentially_relevant

# Water Detectors (A0–A7)
from .detectors.water import (
    detect_water_mention,
    detect_water_withdrawal_total_m3,
    detect_water_consumption_total_m3,
    detect_water_recycled_total_m3,
    detect_water_discharge_total_m3,
    detect_water_pollutants_concentration_mg_l,
    detect_water_pollutants_total_kg,
    detect_water_stress_flag,
    detect_water_management_measures_flag,
)

# Climate Detectors (B1–B2)
from .detectors.climate import (
    detect_ghg_avoided_total_t_co2e,
    detect_carbon_sequestered_total_t_co2e,
)

# Coastal Detectors (C1–C2)
from .detectors.coastal import (
    detect_coastline_restored_total_km,
    detect_habitat_restored_total_ha,
)

# Jobs/Social Detectors (D1–D4)
from .detectors.jobs import (
    detect_jobs_created_total,
    detect_jobs_supported_total,
    detect_women_share_percent,
    detect_local_jobs_share_percent,
)

# -----------------------------------------------------------------------------
# Text normalization
# -----------------------------------------------------------------------------

_TAG_LIKELY_HTML = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"(?is)<script.*?>.*?</script>")
_STYLE_RE = re.compile(r"(?is)<style.*?>.*?</style>")
_OTHER_TAGS_RE = re.compile(r"(?s)<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n\s*\n+")


def _looks_like_html(s: str) -> bool:
    if not s:
        return False
    # cheap heuristic: if we see multiple tags, treat as html-ish
    return bool(_TAG_LIKELY_HTML.search(s))


def _html_to_text(s: str) -> str:
    """
    Very simple HTML->Plaintext cleaner (stdlib-only).
    Keeps newlines around common block-ish tags so tables/numbers don't glue together.
    """
    if not s:
        return ""

    s = _SCRIPT_RE.sub(" ", s)
    s = _STYLE_RE.sub(" ", s)

    # Add newlines for some structural tags
    s = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*p\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*li\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*div\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*tr\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*td\s*>", " ", s)

    s = _OTHER_TAGS_RE.sub(" ", s)
    s = ihtml.unescape(s)

    s = _WS_RE.sub(" ", s)
    s = _MULTI_NL_RE.sub("\n", s)

    return s.strip()


def _normalize_text(raw: str) -> str:
    """
    Normalizes input text for detectors.
    Only runs HTML stripping if the content looks like HTML, otherwise keeps plaintext as-is.
    """
    if not raw:
        return ""
    if _looks_like_html(raw):
        return _html_to_text(raw)
    # Plaintext: still normalize excessive whitespace lightly, keep linebreaks.
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = _WS_RE.sub(" ", raw)
    raw = _MULTI_NL_RE.sub("\n", raw)
    return raw.strip()


# -----------------------------------------------------------------------------
# KPI utilities
# -----------------------------------------------------------------------------

def _as_list(maybe_kpis: Any) -> List[Dict[str, Any]]:
    """
    Normalize detector return types to List[Dict].
    - None -> []
    - Dict -> [Dict]
    - List[Dict] -> List[Dict]
    """
    if not maybe_kpis:
        return []
    if isinstance(maybe_kpis, dict):
        return [maybe_kpis]
    if isinstance(maybe_kpis, list):
        # keep only dict items, ignore weird stuff silently
        return [x for x in maybe_kpis if isinstance(x, dict)]
    return []


def _set_defaults(kpi: Dict[str, Any], url: Optional[str]) -> Dict[str, Any]:
    """
    Ensure stable fields exist, while staying compatible with existing DB insert logic.
    (We do NOT rename keys here; we only add safe defaults.)
    """
    kpi.setdefault("record_type", "kpi")
    kpi.setdefault("source_type", "kpi")
    kpi.setdefault("company", None)

    # Common convenience keys used across the project:
    # some detectors use ctx, some use kpi_context; keep both aligned.
    if "ctx" in kpi and "kpi_context" not in kpi:
        kpi["kpi_context"] = kpi["ctx"]
    if "kpi_context" in kpi and "ctx" not in kpi:
        kpi["ctx"] = kpi["kpi_context"]

    # Store URL if downstream wants it (safe no-op if insert ignores it)
    if url and "extracted_from_url" not in kpi:
        kpi["extracted_from_url"] = url

    return kpi


def _dedupe_kpis(kpis: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Lightweight dedupe to prevent massive duplicates from table extraction.
    Dedupe key: (kpi_key, kpi_value, kpi_unit, normalized ctx prefix)
    """
    seen = set()
    out: List[Dict[str, Any]] = []
    for k in kpis:
        key = (
            k.get("kpi_key"),
            str(k.get("kpi_value")),
            k.get("kpi_unit"),
            (k.get("kpi_context") or k.get("ctx") or "")[:160].strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(k)
    return out


# -----------------------------------------------------------------------------
# Main entrypoint
# -----------------------------------------------------------------------------

def analyze_document_row(doc_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Takes a document row, optionally applies Filter A, then runs detectors and returns KPI dicts.

    Key improvements:
    - Robust handling of detector outputs (Dict vs List[Dict]).
    - Optional Filter A behavior that does not hard-block extraction by default in evaluation.
    - Stable defaults and basic deduplication.
    - Helpful debug logging when KPI extraction returns nothing.
    """

    raw = doc_row.get("raw_text") or ""
    url = doc_row.get("extracted_from_url")

    # --- Env switches ---
    # 1) Skip filter entirely (stress tests / controlled runs)
    skip_filter_a = os.environ.get("SKIP_FILTER_A", "").lower() in ("1", "true", "yes")

    # 2) Soft filter mode: do not block extraction, only annotate (recommended)
    # If set, Filter A is evaluated but never returns [] solely due to irrelevance.
    soft_filter_a = os.environ.get("SOFT_FILTER_A", "").lower() in ("1", "true", "yes")

    # 3) Debug printouts (stdout) for local runs
    debug_kpi = os.environ.get("DEBUG_KPI", "").lower() in ("1", "true", "yes")

    # --- Normalize text ---
    text = _normalize_text(raw)

    # --- Filter A ---
    relevant = True
    if not skip_filter_a:
        try:
            relevant = bool(is_potentially_relevant(text, url=url))
        except Exception as e:
            # In prototype mode, we avoid hard failures due to filter exceptions
            relevant = True
            if debug_kpi:
                print(f"[kpi_analyzer] Filter A error -> treating as relevant: {e!r}")

        if (not soft_filter_a) and (not relevant):
            # Hard block only when SOFT_FILTER_A is not enabled
            if debug_kpi:
                print("[kpi_analyzer] Filter A blocked document (hard mode).")
            return []

    # --- Detectors ---
    kpis: List[Dict[str, Any]] = []

    # WATER
    kpis.extend(_as_list(detect_water_mention(text)))
    kpis.extend(_as_list(detect_water_withdrawal_total_m3(text)))
    kpis.extend(_as_list(detect_water_consumption_total_m3(text)))
    kpis.extend(_as_list(detect_water_recycled_total_m3(text)))
    kpis.extend(_as_list(detect_water_discharge_total_m3(text)))
    kpis.extend(_as_list(detect_water_pollutants_concentration_mg_l(text)))
    kpis.extend(_as_list(detect_water_pollutants_total_kg(text)))
    kpis.extend(_as_list(detect_water_stress_flag(text)))
    kpis.extend(_as_list(detect_water_management_measures_flag(text)))

    # CLIMATE
    kpis.extend(_as_list(detect_ghg_avoided_total_t_co2e(text)))
    kpis.extend(_as_list(detect_carbon_sequestered_total_t_co2e(text)))

    # COASTAL
    kpis.extend(_as_list(detect_coastline_restored_total_km(text)))
    kpis.extend(_as_list(detect_habitat_restored_total_ha(text)))

    # JOBS & SOCIAL
    kpis.extend(_as_list(detect_jobs_created_total(text)))
    kpis.extend(_as_list(detect_jobs_supported_total(text)))
    kpis.extend(_as_list(detect_women_share_percent(text)))
    kpis.extend(_as_list(detect_local_jobs_share_percent(text)))

    # Defaults + annotate relevance (optional)
    out: List[Dict[str, Any]] = []
    for k in kpis:
        if not isinstance(k, dict):
            continue
        k = _set_defaults(k, url=url)

        # Optional annotation useful for evaluation / debugging
        if "relevance_score" not in k:
            # keep existing behavior compatible with your DB insert defaults
            k["relevance_score"] = 1.0 if relevant else 0.2

        out.append(k)

    out = _dedupe_kpis(out)

    if debug_kpi and not out:
        print("[kpi_analyzer] No KPIs extracted.")
        print(f"  url={url}")
        print(f"  raw_len={len(raw)} text_len={len(text)}")
        print(f"  relevant={relevant} (skip={skip_filter_a}, soft={soft_filter_a})")
        # Show a tiny snippet to confirm content
        snippet = text[:400].replace("\n", " ")
        print(f"  text_head={snippet}")

    return out
