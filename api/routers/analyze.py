from typing import Any, Dict, List, Tuple
import hashlib

from fastapi import APIRouter, Depends, Query
from psycopg2.extras import RealDictCursor

from api.db import get_db
from api.analyzer.kpi_analyzer import analyze_document_row

router = APIRouter(prefix="/analyze", tags=["analyze"])


def _normalize_ctx(ctx: str) -> str:
    """
    Leichte Normalisierung des Kontextes für Deduplizierung.
    Kein NLP, nur deterministisch.
    """
    if not ctx:
        return ""
    return " ".join(ctx.lower().split())


def _kpi_fingerprint(kpi: Dict[str, Any]) -> str:
    """
    Erzeugt einen stabilen Fingerprint für ein KPI innerhalb eines Dokuments.
    """
    raw = "|".join(
        [
            kpi.get("kpi_key", ""),
            str(kpi.get("kpi_value", "")),
            str(kpi.get("kpi_unit", "")),
            _normalize_ctx(kpi.get("ctx", "")),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


@router.post("/")
def analyze_docs(
    limit: int = Query(20, ge=1, le=200),
    db=Depends(get_db),
):
    """
    Holt bis zu limit DOC-Records aus oin.oin_master mit status='new',
    wendet den KPI-Analyzer an und speichert gefundene KPIs wieder in oin.oin_master.
    Doppelte KPIs pro Dokument werden unterdrückt.
    """

    cur = db.cursor(cursor_factory=RealDictCursor)

    # 1) DOCs holen
    cur.execute(
        """
        SELECT
            id,
            source_id,
            company,
            raw_text,
            extracted_from_url
        FROM oin.oin_master
        WHERE record_type = 'doc'
          AND status IN ('new','rejected_filterA')
        ORDER BY created_at ASC
        LIMIT %s;
        """,
        (limit,),
    )
    docs: List[Dict[str, Any]] = cur.fetchall()

    if not docs:
        return {"status": "ok", "docs_analyzed": 0, "kpis_inserted": 0}

    analyzed_count = 0
    kpi_inserted = 0

    # 2) Analyse
    for doc in docs:
        doc_id = doc["id"]
        doc_source_id = doc.get("source_id") or doc.get("extracted_from_url")
        extracted_from_url = doc.get("extracted_from_url")
        company = doc.get("company")

        kpi_results = analyze_document_row(doc)

        # --- Normalisieren (Dict | List[Dict]) ---
        normalized_kpis: List[Dict[str, Any]] = []
        for item in kpi_results:
            if isinstance(item, list):
                normalized_kpis.extend(item)
            elif isinstance(item, dict):
                normalized_kpis.append(item)

        # --- NEU: Deduplizierung pro Dokument ---
        seen_fingerprints: set[str] = set()
        unique_kpis: List[Dict[str, Any]] = []

        for kpi in normalized_kpis:
            fp = _kpi_fingerprint(kpi)
            if fp in seen_fingerprints:
                continue
            seen_fingerprints.add(fp)
            unique_kpis.append(kpi)

        # --- Persistenz ---
        for kpi in unique_kpis:
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
                    'kpi',
                    'kpi',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                );
                """,
                (
                    doc_source_id,
                    company,
                    kpi["kpi_key"],
                    kpi["kpi_value"],
                    kpi.get("kpi_unit"),
                    kpi.get("ctx"),
                    extracted_from_url,
                    doc_id,
                    1.0,
                ),
            )
            kpi_inserted += 1

        # 3) DOC auf processed setzen
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
