from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
import psycopg2
import os
import json

router = APIRouter(
    prefix="/ingest",
    tags=["ingest"],
)

class IngestPayload(BaseModel):
    source: str
    url: str
    text: str
    raw_html: Optional[str] = None
    status: str = "new"
    metadata: Dict[str, Any] = {}

@router.post("")
def ingest(payload: IngestPayload):
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
            meta
        )
        VALUES (
            'doc',
            'file',
            %s,
            'scrapy',
            %s,
            %s,
            %s,
            %s
        )
        """,
        (
            payload.url,
            payload.status,
            payload.text,
            payload.url,
            json.dumps(payload.metadata),
        )
    )

    conn.commit()
    cur.close()
    conn.close()

    return {"status": "ok"}
