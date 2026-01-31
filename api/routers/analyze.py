# api/routers/analyze.py

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from psycopg2.extras import RealDictCursor

from api.db import get_db
from api.analyzer.kpi_analyzer import analyze_document_row

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("/")
def analyze_docs(
    limit: int = Query(20, ge=1, le=200),
    db=Depends(get_db),
):
    """
    Holt bis zu limit DOC-Records aus oin.oin_master mit status='new',
    wendet den KPI-Analyzer an und speichert gefundene KPIs wieder in oin.oin_master.
    """

    cur = db.cursor(cursor_factory=RealDictCursor)

    # 1) DOCs holen, die noch nicht verarbeitet wurden
    cur.execute(
        """
        SELECT
            id,
            record_type,
            source_type,
            source_id,
            company,
            raw_text,
            extracted_from_url
        FROM oin.oin_master
        WHERE record_type = 'doc'
          AND status = 'new'
        ORDER BY created_at ASC
        LIMIT %s;
        """,
        (limit,),
    )
    docs: List[Dict[str, Any]] = cur.fetchall()

    if not docs:
        return {
            "status": "ok",
            "docs_analyzed": 0,
            "kpis_inserted": 0,
        }

    analyzed_count = 0
    kpi_inserted = 0

    # 2) Jeden DOC durch den Analyzer schicken
    for doc in docs:
        doc_id = doc["id"]
        doc_source_id = doc.get("source_id") or doc.get("extracted_from_url")
        extracted_from_url = doc.get("extracted_from_url")
        company = doc.get("company")

        kpi_results = analyze_document_row(doc)

        for kpi in kpi_results:
            kpi_key = kpi["kpi_key"]
            kpi_value = kpi["kpi_value"]
            kpi_unit = kpi.get("kpi_unit")
            kpi_context = kpi.get("ctx")

            # Aktuell simple Default-Score
            relevance_score = 1.0

            # KPI-Insert – WICHTIG: source_id kommt vom DOC und ist NICHT NULL
            cur.execute(
                """
                INSERT INTO oin.oin_master (
                    record_type,
                    source_type,
                    source_id,
                    company,
                    kpi_key,
                    kpi_value,
                    kpi_unit,
                    kpi_context,
                    extracted_from_url,
                    doc_ref_id,
                    relevance_score
                )
                VALUES (
                    'kpi',           -- record_type
                    'kpi',           -- source_type
                    %s,              -- source_id (hier vom DOC)
                    %s,              -- company
                    %s,              -- kpi_key
                    %s,              -- kpi_value
                    %s,              -- kpi_unit
                    %s,              -- kpi_context
                    %s,              -- extracted_from_url
                    %s,              -- doc_ref_id
                    %s               -- relevance_score
                );
                """,
                (
                    doc_source_id,       # source_id: NICHT NULL
                    company,
                    kpi_key,
                    kpi_value,
                    kpi_unit,
                    kpi_context,
                    extracted_from_url,
                    doc_id,
                    relevance_score,
                ),
            )
            kpi_inserted += 1

        # 3) Dokument-Status auf 'processed' setzen (auch wenn kein KPI gefunden wurde)
        cur.execute(
            """
            UPDATE oin.oin_master
            SET status = 'processed'
            WHERE id = %s;
            """,
            (doc_id,),
        )
        analyzed_count += 1

    db.commit()

    return {
        "status": "ok",
        "docs_analyzed": analyzed_count,
        "kpis_inserted": kpi_inserted,
    }
