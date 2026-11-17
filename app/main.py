import logging
import time

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.database import engine
from app.core.errors import BusinessError, mensaje_validacion
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

logger = logging.getLogger("fiadoclaro")

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


def _error(status_code: int, detail: str, code: str, **extra) -> JSONResponse:
    """Forma única de las respuestas de error (ver app/core/errors.py)."""
    contenido = {"detail": detail, "code": code}
    contenido.update({k: v for k, v in extra.items() if v is not None})
    return JSONResponse(status_code=status_code, content=jsonable_encoder(contenido))


@app.exception_handler(BusinessError)
def business_error_handler(_: Request, exc: BusinessError):
    return _error(exc.status_code, exc.message, exc.code, datos=exc.datos)


@app.exception_handler(RequestValidationError)
def validation_error_handler(_: Request, exc: RequestValidationError):
    """Datos mal enviados: un mensaje en español por campo; `detail` resume el primero."""
    errores = [mensaje_validacion(e) for e in exc.errors()]
    resumen = errores[0]["mensaje"] if len(errores) == 1 else f"Revisa {len(errores)} campos: {errores[0]['mensaje']}"
    return _error(422, resumen, "validacion", errores=errores)


@app.exception_handler(StarletteHTTPException)
def http_error_handler(_: Request, exc: StarletteHTTPException):
    mensajes = {404: "Recurso no encontrado", 405: "Método no permitido"}
    detail = exc.detail if isinstance(exc.detail, str) and exc.status_code not in mensajes else mensajes.get(
        exc.status_code, str(exc.detail))
    codigos = {401: "no_autenticado", 403: "prohibido", 404: "no_encontrado", 405: "metodo_no_permitido"}
    resp = _error(exc.status_code, detail, codigos.get(exc.status_code, "http"))
    for k, v in (exc.headers or {}).items():
        resp.headers[k] = v
    return resp


@app.exception_handler(IntegrityError)
def integrity_error_handler(_: Request, exc: IntegrityError):
    """Una restricción de la base rechazó los datos (duplicado, regla CHECK, llave foránea)."""
    origen = str(getattr(exc, "orig", exc))
    if "unique" in origen.lower() or "duplicate" in origen.lower():
        return _error(409, "Ya existe un registro con esos datos", "duplicado")
    if "foreign key" in origen.lower():
        return _error(409, "El registro está relacionado con datos que no existen o no se pueden modificar",
                      "relacion_invalida")
    return _error(422, "Los datos no cumplen las reglas del sistema", "restriccion")


@app.exception_handler(Exception)
def unexpected_error_handler(_: Request, exc: Exception):
    logger.exception("Error no controlado", exc_info=exc)
    return _error(500, "Ocurrió un error inesperado. Inténtalo de nuevo; si persiste, avisa al administrador.",
                  "error_interno")


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
