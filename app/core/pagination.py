"""
Respuesta paginada común para todas las listas del API:

    {
      "items":   [...],                 registros de la página pedida
      "total":   98,                    registros que cumplen los filtros (todas las páginas)
      "limit":   50,
      "offset":  0,
      "conteos": {"estado": {"ACTIVO": 3, "BAJA": 1}}   (opcional) facetas para los filtros
    }

`conteos` alimenta los chips de filtro de la interfaz ("Al día (2) · En mora (1)"). Se calculan con
los demás filtros aplicados (por ejemplo la búsqueda), pero sin el filtro de la propia faceta, para
que el usuario vea cuántos registros obtendría al elegir cada opción.
"""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class Pagina(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(description="Registros que cumplen los filtros, en todas las páginas")
    limit: int
    offset: int
    conteos: dict[str, dict[str, int]] | None = Field(
        None, description="Facetas: cantidad de registros por cada valor de un filtro")


def contar(db: Session, stmt: Select) -> int:
    """Total de filas de una consulta (sin su ORDER BY, LIMIT ni OFFSET)."""
    return db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0


def contar_por(db: Session, stmt: Select, columna) -> dict[str, int]:
    """Cantidad de filas de la consulta agrupadas por `columna` (faceta)."""
    sub = stmt.order_by(None).subquery()
    col = sub.c[columna.key]
    filas = db.execute(select(col, func.count()).group_by(col).order_by(col))
    return {str(valor): n for valor, n in filas if valor is not None}


def paginar(db: Session, stmt: Select, limit: int, offset: int) -> tuple[list, int]:
    """Devuelve (filas de la página, total)."""
    total = contar(db, stmt)
    filas = list(db.scalars(stmt.limit(limit).offset(offset)).unique())
    return filas, total
