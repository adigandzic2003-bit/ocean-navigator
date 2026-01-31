from fastapi import APIRouter
from api.db import get_conn
router = APIRouter()
@router.get("/kpis-latest")
def kpis_latest():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, company, kpi_key, kpi_value, kpi_unit, kpi_period_start, kpi_period_end, source_id
                FROM oin.oin_master
                WHERE record_type='kpi'
                ORDER BY created_at DESC
                LIMIT 5;
            """)
            rows = cur.fetchall()
    return {"kpis":[{"id":str(r[0]),"company":r[1],"kpi_key":r[2],"kpi_value":r[3],"kpi_unit":r[4],
                     "period_start": r[5].isoformat() if r[5] else None,
                     "period_end": r[6].isoformat() if r[6] else None,
                     "source_id": r[7]} for r in rows]}
@router.post("/debug/insert-kpi-demo")
def insert_kpi_demo():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO oin.oin_master
                (record_type, source_type, source_id, company,
                 kpi_key, kpi_value, kpi_unit, kpi_method, confidence,
                 kpi_period_start, kpi_period_end)
                VALUES
                ('kpi','analysis','hash:doc:test123','Demo GmbH',
                 'wastewater_discharge_m3',120000,'m3/year','manual',0.9,
                 '2024-01-01','2024-12-31')
                RETURNING id;
            """)
            new_id = cur.fetchone()[0]
    return {"inserted_kpi_id": str(new_id)}
