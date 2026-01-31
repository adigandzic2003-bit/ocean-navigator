# api/analyzer/relevance_filter.py

from typing import Optional

from .topics_config import TOPIC_KEYWORDS, OBVIOUSLY_USELESS_HINTS


def is_potentially_relevant(
    text: str,
    url: Optional[str] = None,
    min_length_chars: int = 500,
) -> bool:
    """
    Grober Relevanz-Check (Filter A):
    - versucht klar irrelevante Seiten zu erkennen (Login, Cookie, 404, extrem kurzer Text)
    - lässt alles durch, was irgendein ESG-/Impact-Thema berührt.
    - im Zweifel: eher TRUE (durchlassen) als FALSE (wegwerfen).
    """

    if not text:
        return False

    lower_text = text.lower()

    # 1) Extrem kurzer Text? (z.B. nur ein Cookie-Banner)
    if len(lower_text) < min_length_chars:
        # Wenn der Text kurz ist UND typische "Müll-Hinweise" enthält → wegwerfen
        if any(hint in lower_text for hint in OBVIOUSLY_USELESS_HINTS):
            return False
        # Kurz, aber kein offensichtlicher Müll → im Zweifel durchlassen
        return True

    # 2) Obvious Müll (unabhängig von Länge)
    if any(hint in lower_text for hint in OBVIOUSLY_USELESS_HINTS):
        # Wenn wir hier rausfiltern, sind wir relativ sicher, dass es keine Inhalte sind,
        # die KPIs enthalten (z.B. reine Login-Seiten).
        # Falls du sehr vorsichtig sein willst: diesen Block schwächen oder auskommentieren.
        return False

    # 3) ESG-/Impact-Keywords aus allen Themen-Buckets
    for bucket, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in lower_text:
                return True  # Treffer in irgendeinem Bucket → relevant

    # 4) Kein klarer ESG-Treffer, aber langer Text:
    # Im Zweifel: durchlassen, damit wir keine wichtigen Sachen verpassen.
    return True
