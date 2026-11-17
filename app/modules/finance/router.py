from fastapi import APIRouter, status

from app.core.deps import CurrentActor, DbSession, SystemAdmin
from app.modules.finance import engine, service
from app.modules.finance.schemas import EquivalenciasOut, TasaIn, TopeIn, TopeOut

router = APIRouter(prefix="/finance", tags=["Finanzas - tasas y topes"])


@router.post("/equivalencias", response_model=EquivalenciasOut,
             summary="Convertir una tasa nominal o efectiva a TED, TEM y TEA")
def equivalencias(body: TasaIn, actor: CurrentActor):
    """Útil para el resumen del cliente y el texto de ayuda de la interfaz."""
    return engine.resumen_tasa(body.to_engine())


@router.get("/topes", response_model=list[TopeOut], summary="Ver topes de tasa (BCRP)")
def topes(db: DbSession, actor: CurrentActor):
    return service.listar_topes(db)


@router.post("/topes", response_model=TopeOut, status_code=status.HTTP_201_CREATED,
             summary="Registrar un nuevo tope de tasa vigente")
def crear_tope(body: TopeIn, db: DbSession, actor: SystemAdmin):
    return service.crear_tope(db, actor, body)
