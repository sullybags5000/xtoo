from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .indexer import Indexer
from .query import Query as Ask
from .query import moment
from .query import run as answer
from .store import Store
from .vectors import ready as vectors_ready


def create_app(settings: Settings, *, background: bool = True) -> FastAPI:
    store = Store(settings.data_dir)
    # Drop removed sources before making any cached results available.
    store.retain_roots({str(p) for p in settings.folders})
    indexer = Indexer(settings, store)

    @asynccontextmanager
    async def lifespan(app):
        if background:
            indexer.start()
        yield
        indexer.close()

    app = FastAPI(title="Xtoo", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.indexer = indexer
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

    @app.middleware("http")
    async def browser_headers(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'; object-src 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def home():
        return FileResponse(static / "index.html")

    @app.get("/api/search")
    def search(
        q: str = Query("", max_length=500),
        kind: str = Query("", max_length=12),
        offset: int = Query(0, ge=0),
        limit: int = Query(40, ge=1, le=100),
        entity: str = Query("", max_length=120),
        collapse: bool = Query(False),
        meaning: bool = Query(False),
        people: bool = Query(False),
        since: str = Query("", max_length=10),
        until: str = Query("", max_length=10),
    ):
        try:
            asked = Ask(
                text=q,
                kind=kind,
                entity=entity,
                since=moment(since),
                until=moment(until, end_of_day=True),
                collapse=collapse,
                meaning=meaning,
                people_only=people,
                offset=offset,
                limit=limit,
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return answer(store, asked)

    @app.get("/api/entities")
    def entities(prefix: str = Query("", max_length=120)):
        return {"items": store.entities(prefix)}

    @app.get("/api/documents/{document_id}")
    def document(document_id: int):
        item = store.document(document_id)
        if item is None:
            raise HTTPException(404, "Document is no longer indexed")
        item["preview_truncated"] = len(item["content"]) > 100_000
        item["content"] = item["content"][:100_000]
        return item

    @app.get("/api/status")
    def status():
        kinds = store.stats()
        return {
            **indexer.status(),
            "total_documents": sum(kinds.values()),
            "kinds": kinds,
            "folders": [str(p) for p in settings.folders],
            "interval_seconds": settings.interval_seconds,
            "semantic": vectors_ready(store),
        }

    @app.post("/api/index", status_code=202)
    def refresh(request: Request):
        if request.headers.get("x-xtoo-request") != "1":
            raise HTTPException(403, "Missing local application header")
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Cross-origin requests are not allowed")
        indexer.request_scan()
        return {"message": "Scan requested"}

    return app
