# api/analyzer/kpi_analyzer.py

import os
import re
import html as ihtml
from typing import List, Dict, Any

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


def _html_to_text(s: str) -> str:
    """
    Sehr einfacher HTML->Plaintext Cleaner (stdlib-only).
    Reicht für Prototyp/Stress-Tests, ohne BeautifulSoup-Abhängigkeit.
    """
    if not s:
        return ""

    # Entferne script/style komplett
    s = re.sub(r"(?is)<script.*?>.*?</script>", " ", s)
    s = re.sub(r"(?is)<style.*?>.*?</style>", " ", s)

    # Ersetze <br>/<p>/<li> etc. durch Newlines, damit Zahlen/Einheiten nicht verkleben
    s = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*p\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*li\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*div\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*tr\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*td\s*>", " ", s)

    # Entferne alle übrigen Tags
    s = re.sub(r"(?s)<[^>]+>", " ", s)

    # HTML entities dekodieren (&nbsp; etc.)
    s = ihtml.unescape(s)

    # Whitespace normalisieren
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)

    return s.strip()


def analyze_document_row(doc_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Nimmt eine Dokument-Zeile (aus der DB oder dem Crawler),
    entscheidet über Relevanz (Filter A) und extrahiert KPIs.
    Gibt eine Liste von KPI-Dicts zurück.
    """

    raw = doc_row.get("raw_text") or ""
    url = doc_row.get("extracted_from_url")

    # DEBUG: Filter A optional überspringen (für Stress-Tests / kontrollierte Runs)
    skip_filter_a = os.environ.get("SKIP_FILTER_A", "").lower() in ("1", "true", "yes")

    # Normalisierung: HTML -> Plaintext, falls HTML-artig
    # (Wir wenden das immer an; bei Plaintext schadet es praktisch nicht.)
    text = _html_to_text(raw)

    # --- 1) Filter A: Grobfilter ---
    if (not skip_filter_a) and (not is_potentially_relevant(text, url=url)):
        return []

    # --- 2) KPI-Detektoren ---
    kpis: List[Dict[str, Any]] = []

    # === WATER KPIs ===
    water_flag_kpi = detect_water_mention(text)
    if water_flag_kpi:
        kpis.append(water_flag_kpi)

    withdrawal_kpi = detect_water_withdrawal_total_m3(text)
    if withdrawal_kpi:
        kpis.append(withdrawal_kpi)

    consumption_kpi = detect_water_consumption_total_m3(text)
    if consumption_kpi:
        kpis.append(consumption_kpi)

    recycled_kpi = detect_water_recycled_total_m3(text)
    if recycled_kpi:
        kpis.append(recycled_kpi)

    discharge_kpi = detect_water_discharge_total_m3(text)
    if discharge_kpi:
        kpis.append(discharge_kpi)

    poll_conc_kpi = detect_water_pollutants_concentration_mg_l(text)
    if poll_conc_kpi:
        kpis.append(poll_conc_kpi)

    poll_total_kpi = detect_water_pollutants_total_kg(text)
    if poll_total_kpi:
        kpis.append(poll_total_kpi)

    # === CLIMATE KPIs ===
    ghg_avoided_kpi = detect_ghg_avoided_total_t_co2e(text)
    if ghg_avoided_kpi:
        kpis.append(ghg_avoided_kpi)

    carbon_seq_kpi = detect_carbon_sequestered_total_t_co2e(text)
    if carbon_seq_kpi:
        kpis.append(carbon_seq_kpi)

    # === COASTAL KPIs ===
    coastline_kpi = detect_coastline_restored_total_km(text)
    if coastline_kpi:
        kpis.append(coastline_kpi)

    habitat_kpi = detect_habitat_restored_total_ha(text)
    if habitat_kpi:
        kpis.append(habitat_kpi)

    # === JOBS & SOCIAL ===
    jobs_created_kpi = detect_jobs_created_total(text)
    if jobs_created_kpi:
        kpis.append(jobs_created_kpi)

    jobs_supported_kpi = detect_jobs_supported_total(text)
    if jobs_supported_kpi:
        kpis.append(jobs_supported_kpi)

    women_share_kpi = detect_women_share_percent(text)
    if women_share_kpi:
        kpis.append(women_share_kpi)

    local_jobs_share_kpi = detect_local_jobs_share_percent(text)
    if local_jobs_share_kpi:
        kpis.append(local_jobs_share_kpi)

    return kpis
