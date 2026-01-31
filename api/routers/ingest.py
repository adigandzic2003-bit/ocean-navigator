# api/routers/ingest.py

from fastapi import APIRouter

# Dieser Router ist für zukünftige Ingest-Endpunkte gedacht (z.B. Crawler → API → DB).
# Aktuell definieren wir hier bewusst KEINE /analyze-Route mehr,
# damit die Analyse ausschließlich über api/routers/analyze.py läuft.

router = APIRouter(
    prefix="/ingest",
    tags=["ingest"],
)

# Beispiel-Platzhalter (für spätere Ingest-Endpoints):
#
# @router.post("/doc")
# def ingest_doc(payload: Dict[str, Any], db=Depends(get_db)):
#     ...
#     return {"status": "ok"}
