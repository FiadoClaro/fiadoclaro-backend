from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.customers.schemas import ResumenCredito


class ListadoPendienteOut(BaseModel):
    """Listado de pago aún no pagado, con la mora calculada a hoy."""

    id: int
    fecha_corte: date
    fecha_pago: date
    vencido: bool
    total_a_pagar: Decimal = Field(description="Compras e intereses del listado, sin mora")
    dias_mora: int
    interes_moratorio: Decimal
    interes_compensatorio_mora: Decimal
    total_exigible: Decimal = Field(description="Lo que debe pagar hoy por este listado (incluye mora)")


class CompraFinDeMesOut(BaseModel):
    id: int
    fecha_hora: datetime
    descripcion: str = Field(description="Productos de la compra, ej. '3x Leche Gloria Azul 400g, 1x Arroz...'")
    atendido_por: str
    monto: Decimal
    dias: int = Field(description="Días entre la compra y la fecha de pago")
    interes: Decimal
    total: Decimal
    fecha_pago: date
    en_listado: bool = Field(description="True si ya está en un listado generado")


class CuotaPortalOut(BaseModel):
    numero: int
    fecha_vencimiento: date
    monto: Decimal
    estado: Literal["PAGADA", "PENDIENTE", "VENCIDA"]


class CompraEnCuotasOut(BaseModel):
    id: int
    fecha_hora: datetime
    descripcion: str
    atendido_por: str
    monto: Decimal
    num_cuotas: int
    valor_cuota: Decimal
    saldo_pendiente: Decimal = Field(description="Suma de las cuotas que faltan pagar")
    cuotas_pagadas: int
    cuotas: list[CuotaPortalOut]


class PortalResumenOut(BaseModel):
    """Todo lo que muestra la pantalla 'Mi estado de cuenta' del vecino, ya calculado."""

    cliente: str
    dni: str
    tienda: str
    tienda_ruc: str
    credito: ResumenCredito = Field(description="Límite, utilizado, disponible, próximo corte y pago")
    estado_pago: Literal["AL_DIA", "EN_MORA"]
    dias_mora: int = Field(description="Días de atraso del listado vencido más antiguo (0 si está al día)")
    vencio_el: date | None = Field(description="Fecha de pago del listado vencido más antiguo")
    proxima_fecha_limite: date = Field(description="Próxima fecha de pago que aún no vence")
    total_a_pagar_hoy: Decimal = Field(description="Suma de los listados pendientes con su mora a hoy")
    saldo_anterior: Decimal = Field(description="Parte de lo anterior que viene de listados previos al más reciente")
    deuda_por_vencer: Decimal = Field(description="Cuotas y compras aún no incluidas en ningún listado")
    saldo_total: Decimal = Field(description="Toda la deuda: total a pagar hoy + deuda por vencer")
    listados_pendientes: list[ListadoPendienteOut]
    compras_fin_de_mes: list[CompraFinDeMesOut] = Field(description="Compras a fin de mes aún no pagadas")
    compras_en_cuotas: list[CompraEnCuotasOut] = Field(description="Compras en cuotas con saldo pendiente")
