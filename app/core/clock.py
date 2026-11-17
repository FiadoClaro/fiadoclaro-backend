"""Reloj del negocio en la zona horaria de la tienda (aislado para poder simular fechas en pruebas)."""
from datetime import date, datetime

from app.core.config import settings

_ahora_fijo: datetime | None = None


def fijar_ahora(dt: datetime | None) -> None:
    """Solo para pruebas: congela el reloj en `dt` (None vuelve al reloj real)."""
    global _ahora_fijo
    _ahora_fijo = a_hora_local(dt) if dt else None


def ahora() -> datetime:
    return _ahora_fijo or datetime.now(settings.tz)


def hoy() -> date:
    return ahora().date()


def a_hora_local(dt: datetime) -> datetime:
    """Convierte a la hora local de la tienda; si viene sin zona, se asume que ya es hora local."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=settings.tz)
    return dt.astimezone(settings.tz)
