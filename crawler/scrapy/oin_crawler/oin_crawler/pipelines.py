import httpx
import hashlib
from datetime import datetime

class IngestPipeline:
    API_BASE = "http://localhost:8000"

    def process_item(self, item, spider):
        text = item.get("text") or ""
        content_hash = hashlib.sha256(
            text.encode("utf-8", "ignore")
        ).hexdigest() if text else None

        payload = {
            "source_url": item.get("source_url"),
            "source_domain": item.get("source_domain"),
            "source_type": item.get("source_type"),
            "title": item.get("title"),
            "text": text,
            "raw_html": item.get("raw_html"),
            "mime_type": item.get("mime_type"),
            "lang": item.get("lang"),
            "content_hash": content_hash,
            "status_code": item.get("status_code"),
            "published_at": item.get("published_at"),
            "crawl_ts": datetime.utcnow().isoformat() + "Z",
            "meta": item.get("meta", {}),
        }

        try:
            r = httpx.post(f"{self.API_BASE}/ingest", json=payload, timeout=20)
            r.raise_for_status()
            spider.logger.info(f"[INGEST] {payload.get('source_url')} -> {r.status_code}")
        except Exception as e:
            spider.logger.error(f"[INGEST ERROR] {e} for {payload.get('source_url')}")
        return item
