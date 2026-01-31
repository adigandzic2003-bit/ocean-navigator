import os
import json
import httpx
import hashlib
from datetime import datetime


# --- einfacher Wasser-Grobfilter (high recall) ---
WATER_TERMS = [
    "water", "wastewater", "freshwater", "withdrawal", "discharge", "effluent",
    "wasser", "abwasser", "frischwasser", "wasserentnahme", "wassernutzung", "einleitung",
    "m3", "m³", "liter", "l/"
]


def water_prefilter(text: str) -> tuple[bool, str]:
    """
    Sehr einfacher Grobfilter:
    - >=2 Treffer aus WATER_TERMS
    ODER
    - 1 Kernbegriff + Einheit
    """
    t = (text or "").lower()
    hits = [w for w in WATER_TERMS if w in t]

    if len(hits) >= 2:
        return True, f"hits={hits[:6]}"

    core = any(w in t for w in ["water", "wasser", "wastewater", "abwasser", "withdrawal", "wasserentnahme"])
    unit = any(w in t for w in ["m3", "m³", "liter", "l/"])

    if core and unit:
        return True, "core+unit"

    return False, f"hits={hits[:6]}"


class IngestPipeline:
    def __init__(self, api_base: str):
        self.api_base = api_base.rstrip("/")

    @classmethod
    def from_crawler(cls, crawler):
        api_base = (
            crawler.settings.get("OIN_API_BASE")
            or os.getenv("OIN_API_BASE")
            or "http://localhost:8000"
        )
        return cls(api_base)

    def process_item(self, item, spider):
        text = item.get("text") or ""
        raw_html = item.get("raw_html")

        # Hash für Nachvollziehbarkeit / Dedupe
        content_hash = hashlib.sha256(
            text.encode("utf-8", errors="ignore")
        ).hexdigest() if text else None

        # Grobfilter
        is_relevant, reason = water_prefilter(text)
        status = "new" if is_relevant else "rejected_filterA"

        payload = {
            "source": item.get("source_domain") or "scrapy",
            "url": item.get("source_url"),
            "text": text,
            "raw_html": raw_html,
            "status": status,
            "metadata": {
                "source_domain": item.get("source_domain"),
                "source_type": item.get("source_type"),
                "title": item.get("title"),
                "mime_type": item.get("mime_type"),
                "lang": item.get("lang"),
                "status_code": item.get("status_code"),
                "published_at": item.get("published_at"),
                "crawl_ts": item.get("crawl_ts") or datetime.utcnow().isoformat() + "Z",
                "content_hash": content_hash,
                "prefilter_reason": reason,
                "spider": spider.name,
                "meta": item.get("meta", {}),
            },
        }

        try:
            r = httpx.post(f"{self.api_base}/ingest", json=payload, timeout=30)
            r.raise_for_status()
            spider.logger.info(
                f"[INGEST] {payload['url']} → {r.status_code} ({status})"
            )
        except Exception as e:
            spider.logger.error(
                f"[INGEST ERROR] {payload.get('url')} → {e}"
            )
            raise

        return item
