# api/analyzer/detectors/water.py

import re
from typing import Optional, Dict


# === Einfacher Flag-Detektor ===================================================


def detect_water_mention(text: str) -> Optional[Dict]:
    """
    Einfacher Detektor: setzt ein Flag, wenn 'water' oder 'Wasser' im Text vorkommt.
    Nutzt du als "A0"-Signal: hier lohnt sich genaueres Hinsehen.
    """
    if not text:
        return None

    keywords = ["water", "Wasser"]
    if any(kw in text for kw in keywords):
        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_mention_flag",
            "kpi_value": 1,
            "kpi_unit": "flag",
            "ctx": "text contains 'water'/'Wasser'",
        }

    return None


# === Gemeinsame Helfer für alle Wasser-KPIs ====================================

MULTIPLIER_WORDS = {
    # Englisch
    "million": 1_000_000,
    "millions": 1_000_000,
    "billion": 1_000_000_000,
    "billions": 1_000_000_000,
    "bn": 1_000_000_000,
    # Deutsch
    "mio": 1_000_000,
    "mio.": 1_000_000,
    "millionen": 1_000_000,
    "mrd": 1_000_000_000,
    "mrd.": 1_000_000_000,
    "milliarden": 1_000_000_000,
}


def _normalize_number(num_str: str) -> float:
    """
    Wandelt Strings wie '123,456', '1.234,56', '1,234.56' in float.

    Heuristik:
    - Wenn Komma UND Punkt vorkommen:
        - Wenn Komma hinter Punkt -> Punkt = Tausender, Komma = Dezimal (europäisch)
        - Wenn Punkt hinter Komma -> Komma = Tausender, Punkt = Dezimal (englisch)
    - Wenn nur Komma: Komma = Dezimal oder Tausender, wird heuristisch entschieden
    - Wenn nur Punkt: Punkt = Dezimal oder Tausender – Python kriegt das meist hin.
    """
    s = num_str.strip()

    if "," in s and "." in s:
        last_comma = s.rfind(",")
        last_dot = s.rfind(".")
        if last_comma > last_dot:
            # z.B. '1.234,56' -> '1234.56'
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            # z.B. '1,234.56' -> '1234.56'
            s = s.replace(",", "")
    elif "," in s:
        # z.B. '123,45' -> '123.45' oder '1,234' -> '1234'
        parts = s.split(",")
        if len(parts[-1]) in (1, 2):  # eher Dezimalteil
            s = s.replace(".", "")  # evtl. Tausenderpunkte entfernen
            s = s.replace(",", ".")
        else:
            # vermutlich Tausendertrennung: '1,234,567'
            s = s.replace(",", "")
    # nur Punkt: normaler Dezimalpunkt oder Tausender – float() versucht sein Bestes
    return float(s)


def _parse_quantity_with_multiplier(
    raw_number: str,
    raw_multiplier: Optional[str],
) -> Optional[float]:
    """
    Nimmt eine Rohzahl + evtl. Multiplikatorwort ('million', 'Mio.', 'billion', 'Mrd.')
    und gibt den Wert als float zurück.
    """
    try:
        base = _normalize_number(raw_number)
    except ValueError:
        return None

    if not raw_multiplier:
        return base

    key = raw_multiplier.strip().lower()
    multiplier = MULTIPLIER_WORDS.get(key, 1)
    return base * multiplier


# Generischer Zahl+Einheits-Pattern (m³, cubic meters, kubikmeter)
WATER_VOLUME_PATTERN = re.compile(
    r"""
    (?P<number>
        \d{1,3}              # 1–3 Ziffern
        (?:[.,]\d{3})*       # optionale Tausendergruppen: .123 / ,123
        (?:[.,]\d+)?         # optionaler Dezimalteil
        |
        \d+                  # oder einfach nur Ziffern
    )
    \s*
    (?P<multiplier>
        million|millions|billion|billions|bn|
        mio\.?|millionen|
        mrd\.?|mrd|milliarden
    )?
    \s*
    (?P<unit>
        m3|m³|
        cubic\s+meters?|
        cubic\s+metres?|
        kubikmeter
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _build_context_snippet(text: str, start: int, end: int, window: int = 80) -> str:
    """
    Gibt einen Kontext-Schnipsel um die Fundstelle zurück.
    """
    left = max(0, start - window)
    right = min(len(text), end + window)
    snippet = text[left:right].strip()
    return snippet.replace("\n", " ")


def _get_sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    """
    Grobe Satzabgrenzung: sucht das vorherige und nächste Satzendezeichen
    (., !, ?) um die Position 'pos' herum und gibt [start, end) zurück.
    """
    sentence_end_chars = ".!?"

    # Suche nach links bis zum letzten Satzende
    start = pos
    while start > 0 and text[start - 1] not in sentence_end_chars:
        start -= 1

    # Suche nach rechts bis zum nächsten Satzende
    end = pos
    length = len(text)
    while end < length and text[end] not in sentence_end_chars:
        end += 1

    # ein Zeichen weiter, damit der Punkt inkl. ist
    if end < length:
        end += 1

    return start, end


def _span_has_keywords(text: str, start: int, end: int, keywords: list[str], window: int = 60) -> bool:
    """
    Hybrid-Logik:
    1) Keyword muss im selben Satz vorkommen ODER
    2) Keyword im lokalen Kontextfenster (± window Zeichen)

    Dadurch:
    - Kein falsches Matching mehr (wie vorher beim recycling)
    - Keine zu strenge Satzgrenze mehr (wie beim withdrawal)
    """
    # 1) Satzgrenzen bestimmen
    sent_start, sent_end = _get_sentence_bounds(text, (start + end) // 2)
    sentence = text[sent_start:sent_end].lower()

    # Satz-Check
    if any(kw.lower() in sentence for kw in keywords):
        return True

    # 2) Lokales Fenstermatching (gegen Overfitting)
    ctx_start = max(0, start - window)
    ctx_end = min(len(text), end + window)
    context = text[ctx_start:ctx_end].lower()

    return any(kw.lower() in context for kw in keywords)

def _first_match_for_keywords(text: str, keywords: list[str]) -> Optional[Dict]:
    """
    Verbesserte Logik:
    1. Finde den Satz, der das Keyword enthält.
    2. Sammle ALLE m3-Zahlen in diesem Satz.
    3. Bestimme die Zahl, die dem Keyword am nächsten ist (kleinste Textdistanz).
    """

    if not text:
        return None

    text_lower = text.lower()

    # 1) Keyword-Position suchen
    keyword_positions = []
    for kw in keywords:
        start = 0
        kw_lower = kw.lower()
        while True:
            idx = text_lower.find(kw_lower, start)
            if idx == -1:
                break
            keyword_positions.append(idx)
            start = idx + len(kw_lower)

    if not keyword_positions:
        return None

    # Wir nutzen die erste gefundene Keyword-Position
    kw_pos = keyword_positions[0]

    # 2) Satzgrenzen bestimmen
    sent_start, sent_end = _get_sentence_bounds(text, kw_pos)
    sentence = text[sent_start:sent_end]

    # 3) ALLE m3-Zahlen im Satz finden
    candidates = []
    for match in WATER_VOLUME_PATTERN.finditer(sentence):
        num_str = match.group("number")
        multiplier_str = match.group("multiplier")
        value = _parse_quantity_with_multiplier(num_str, multiplier_str)

        if value is None:
            continue

        span_start = match.start()
        # absolute Position im gesamten Text
        abs_pos = sent_start + span_start

        # Distanz zwischen keyword und dieser Zahl
        distance = abs(abs_pos - kw_pos)

        candidates.append({
            "value": float(value),
            "ctx": _build_context_snippet(text, abs_pos, abs_pos + len(num_str)),
            "distance": distance,
        })

    if not candidates:
        return None

    # 4) Die Zahl mit dem geringsten Abstand zum Keyword wählen
    best = min(candidates, key=lambda c: c["distance"])

    return {
        "value": best["value"],
        "ctx": best["ctx"],
    }

# === A1: Gesamtentnahme (water_withdrawal_total_m3) ============================


def detect_water_withdrawal_total_m3(text: str) -> Optional[Dict]:
    """
    Sucht nach Gesamtwasserentnahme (Entnahme / withdrawal) in m3.

    Beispiele:
    - "total water withdrawal of 1.2 million m3"
    - "Wasserentnahme: 800.000 m³"
    - "groundwater withdrawal reached 0.5 bn m3"
    """
    keywords = [
        "withdrawal",
        "withdrawn",
        "water abstraction",
        "abstraction",
        "Wasserentnahme",
        "Entnahme von Wasser",
    ]

    hit = _first_match_for_keywords(text, keywords)
    if not hit:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "water_withdrawal_total_m3",
        "kpi_value": hit["value"],
        "kpi_unit": "m3",
        "ctx": hit["ctx"],
    }


# === A3: Wasserverbrauch (water_consumption_total_m3) ==========================


def detect_water_consumption_total_m3(text: str) -> Optional[Dict]:
    """
    Sucht nach Wasserverbrauch / water consumption in m3.

    Beispiele:
    - "total water consumption was 900,000 m3"
    - "Wasserverbrauch von 0,8 Mio. m³"
    """
    keywords = [
        "water consumption",
        "consumption of water",
        "water consumed",
        "water use",
        "water used",
        "Wasserverbrauch",
        "Verbrauch von Wasser",
    ]

    hit = _first_match_for_keywords(text, keywords)
    if not hit:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "water_consumption_total_m3",
        "kpi_value": hit["value"],
        "kpi_unit": "m3",
        "ctx": hit["ctx"],
    }


# === A4: Wiederverwendetes / recyceltes Wasser (water_recycled_m3) ============


def detect_water_recycled_total_m3(text: str) -> Optional[Dict]:
    """
    Sucht nach recyceltem / wiederverwendetem Wasser in m3.

    Beispiele:
    - "we recycled 100,000 m3 of water"
    - "aufbereitetes und wiederverwendetes Wasser: 0,2 Mio. m³"
    """
    keywords = [
        "recycled water",
        "water recycled",
        "reuse of water",
        "water reuse",
        "reused water",
        "treated wastewater reused",
        "recycled process water",
        "Wasserwiederverwendung",
        "Wasserrecycling",
        "aufbereitetes Wasser",
        "wiederverwendetes Wasser",
    ]

    hit = _first_match_for_keywords(text, keywords)
    if not hit:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "water_recycled_total_m3",
        "kpi_value": hit["value"],
        "kpi_unit": "m3",
        "ctx": hit["ctx"],
    }


# === A5: Abwassereinleitungen (water_discharge_total_m3) =======================


def detect_water_discharge_total_m3(text: str) -> Optional[Dict]:
    """
    Sucht nach Abwassereinleitungen / water discharge in m3.

    Beispiele:
    - "total wastewater discharge was 500,000 m3"
    - "Einleitung von Abwasser: 1,5 Mio. m³"
    """
    keywords = [
        "discharge of wastewater",
        "wastewater discharge",
        "water discharge",
        "effluent discharge",
        "effluent",
        "wastewater",
        "Abwassereinleitung",
        "Einleitung von Abwasser",
        "Abwasser",
        "Einleitungen",
    ]

    hit = _first_match_for_keywords(text, keywords)
    if not hit:
        return None

    return {
        "record_type": "kpi",
        "source_type": "kpi",
        "company": None,
        "kpi_key": "water_discharge_total_m3",
        "kpi_value": hit["value"],
        "kpi_unit": "m3",
        "ctx": hit["ctx"],
    }

# === A6: Schadstoff-Konzentration (mg/L oder ppm) ==============================

POLLUTANTS_CONCENTRATION_PATTERN = re.compile(
    r"""
    (?P<number>
        \d{1,3}
        (?:[.,]\d+)?         # Dezimalteil
    )
    \s*
    (?P<unit>
        mg\/l | mg\/L | mg-?l | mg-?L | mg\s+per\s+l |
        ppm
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def detect_water_pollutants_concentration_mg_l(text: str) -> Optional[Dict]:
    """
    Erkennt Schadstoffkonzentrationen in mg/L oder ppm.
    ppm wird als mg/L interpretiert (1 ppm ≈ 1 mg/L in Wasser).
    """
    if not text:
        return None

    for match in POLLUTANTS_CONCENTRATION_PATTERN.finditer(text):
        number_str = match.group("number").replace(",", ".")
        unit = match.group("unit").lower().strip()

        try:
            value = float(number_str)
        except ValueError:
            continue

        # ppm -> mg/L (vereinfachte Annahme für Wasser)
        if "ppm" in unit:
            value = value

        span_start, span_end = match.span()
        ctx = _build_context_snippet(text, span_start, span_end)

        return {
            "record_type": "kpi",
            "source_type": "kpi",
            "company": None,
            "kpi_key": "water_pollutants_concentration_mg_l",
            "kpi_value": value,
            "kpi_unit": "mg/L",
            "ctx": ctx,
        }

    return None

# === A7: Schadstoff-Gesamtmenge (kg oder t) ====================================

POLLUTANTS_TOTAL_PATTERN = re.compile(
    r"""
    (?P<number>
        \d{1,3}
        (?:[.,]\d{3})*       # Tausendergruppen
        (?:[.,]\d+)?         # Dezimalteil
        |
        \d+
    )
    \s*
    (?P<unit>
        kg | kg\. |
        t | t\. |
        ton | tons | tonne | tonnes
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def detect_water_pollutants_total_kg(text: str) -> Optional[Dict]:
    """
    Erkennt Schadstoff-Gesamtmengen in kg oder t.
    Tonnen werden in kg umgerechnet (1 t = 1000 kg).
    """
    if not text:
        return None

    for match in POLLUTANTS_TOTAL_PATTERN.finditer(text):
        num_raw = match.group("number")
        unit = match.group("unit").lower().strip()

        try:
            value = _normalize_number(num_raw)
        except ValueError:
            continue

        # t / ton / tonnes -> kg
        if unit.startswith("t") or unit.startswith("ton"):
            value *= 1000

        span_start, span_end = match.span()
        ctx = _build_context_snippet(text, span_start, span_end)

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

# === Optional: kleiner Self-Test, wenn man die Datei direkt ausführt ==========

if __name__ == "__main__":
    sample_text = """
    In 2024, the company reported a total water withdrawal of 1.2 million m3 across all sites.
    The total water consumption was 900,000 m3, out of which 100,000 m3 of water were recycled.
    Total wastewater discharge was 0.5 million m3.
    Zusätzlich wurde der Wasserverbrauch (Wasserverbrauch) in Höhe von 0,8 Mio. m³ berichtet.
    """

    print("detect_water_mention:", detect_water_mention(sample_text))
    print("detect_water_withdrawal_total_m3:", detect_water_withdrawal_total_m3(sample_text))
    print("detect_water_consumption_total_m3:", detect_water_consumption_total_m3(sample_text))
    print("detect_water_recycled_total_m3:", detect_water_recycled_total_m3(sample_text))
    print("detect_water_discharge_total_m3:", detect_water_discharge_total_m3(sample_text))
