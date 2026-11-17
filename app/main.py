import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.core.errors import BusinessError
from app.modules.audit.router import router as audit_router
from app.modules.customers.router import router as customers_router
from app.modules.finance.router import router as finance_router
from app.modules.iam.router import router as iam_router
from app.modules.payments.router import router as payments_router
from app.modules.portal.router import router as portal_router
from app.modules.products.router import router as products_router
from app.modules.purchases.router import router as purchases_router
from app.modules.statements.router import router as statements_router
from app.modules.stores.router import router as stores_router

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description=(
        "Control de cuenta corriente por créditos (fiado) de pequeños negocios. "
        "Montos con 2 decimales, tasas con 7+ decimales, año de 360 días y mes de 30."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(BusinessError)
def business_error_handler(_: Request, exc: BusinessError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code})


for r in (
    iam_router,
    stores_router,
    customers_router,
    products_router,
    purchases_router,
    statements_router,
    payments_router,
    portal_router,
    finance_router,
    audit_router,
):
    app.include_router(r, prefix=settings.API_PREFIX)


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok"}


@app.get("/health/db", tags=["Sistema"])
def health_db():
    """Verifica que la base de datos responda y que las migraciones estén aplicadas."""
    started = time.perf_counter()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unreachable", "detail": exc.__class__.__name__},
        )
    return {
        "status": "ok",
        "database": "reachable",
        "alembic_revision": revision,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }
