from fastapi import FastAPI, Response
from api.routers.health import router as health_router
from api.routers.docs import router as docs_router
from api.routers.kpis import router as kpis_router
from api.routers.ingest import router as ingest_router
from api.routers.analyze import router as analyze_router
app = FastAPI(title="Ocean Impact Navigator API")
@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)
app.include_router(health_router)
app.include_router(docs_router)
app.include_router(kpis_router)
app.include_router(ingest_router)
app.include_router(analyze_router)
