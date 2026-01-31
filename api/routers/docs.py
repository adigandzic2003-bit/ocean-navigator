from fastapi import APIRouter
from api.db import get_conn
router = APIRouter()
@router.get("/docs-latest")
def docs_latest():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, company, title, source_type, source_id, created_at
                FROM oin.oin_master
                WHERE record_type='doc'
                ORDER BY created_at DESC
                LIMIT 5;
            """)
            rows = cur.fetchall()
    return {"docs":[{"id":str(r[0]),"company":r[1],"title":r[2],"source_type":r[3],"source_id":r[4],"created_at":r[5].isoformat()} for r in rows]}
@router.post("/debug/insert-doc-demo")
def insert_doc_demo():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO oin.oin_master
                (record_type, source_type, source_id, company, title)
                VALUES ('doc','web','https://example.com/fastapi-demo','Demo GmbH','FastAPI Insert Demo')
                RETURNING id;
            """)
            new_id = cur.fetchone()[0]
    return {"inserted_id": str(new_id)}
