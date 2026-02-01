# api/routers/ingest.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import psycopg2
import os

router = APIRouter(
    prefix="/ingest",
    tags=["ingest"],
)

# -------- Payload --------

class IngestPayload(BaseModel):
    source: str                   # z.B. "chapter7_test"
    url: str                      # file://... oder https://...
    text: str
    raw_html: Optional[str] = None
    status: str = "new"
    metadata: Dict[str, Any] = {}

# -------- Endpoint --------

@router.post("")
def ingest(payload: IngestPayload):
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO oin.oin_master (
                record_type,
                source_type,
                source_id,
                crawler_name,
                status,
                raw_text,
                extracted_from_url,
                content_hash,
                language,
                topic_tags,
                keywords
            )
            VALUES (
                'doc',
                'other',
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                payload.url,                               # source_id
                payload.source,                            # crawler_name
                payload.status,                            # status
                payload.text,                              # raw_text
                payload.url,                               # extracted_from_url
                payload.metadata.get("content_hash"),      # content_hash
                payload.metadata.get("lang"),              # language
                payload.metadata.get("topic_tags"),        # topic_tags
                payload.metadata.get("keywords"),          # keywords
            )
        )

        conn.commit()
        cur.close()
        conn.close()

        return {"status": "ok"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
