"""
Motor financiero de FiadoClaro (Python puro, sin base de datos ni FastAPI).

Convenciones del Anexo A del enunciado:
  * Año comercial de 360 días y mes comercial de 30 días.
  * Conversión explícita de tasa nominal a efectiva.
  * Prelación de pagos: mora -> interés compensatorio (por atraso y del listado) -> capital.
  * Montos redondeados a 2 decimales; tasas con al menos 7 decimales
    (internamente se trabaja con 34 dígitos significativos y se guardan 10 decimales).

Conteo de días (guía del curso): días = fecha final - fecha inicial
(el primer día no se cuenta y el día del vencimiento sí).

Todas las tasas se reciben en PORCENTAJE (3.5 significa 3.5 %).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, getcontext

getcontext().prec = 34

D = Decimal
CERO = D("0")
UNO = D("1")
CIEN = D("100")
CENTIMO = D("0.01")
DECIMALES_TASA = D("0.0000000001")  # 10 decimales (> 7 exigidos)

DIAS_ANIO = 360
DIAS_MES = 30

NOMINAL = "NOMINAL"
EFECTIVA = "EFECTIVA"


# ----------------------------------------------------------------- redondeo
def dinero(x: Decimal | int | str) -> Decimal:
    """Redondeo monetario a 2 decimales (half up)."""
    return D(x).quantize(CENTIMO, rounding=ROUND_HALF_UP)


def tasa_q(x: Decimal) -> Decimal:
    """Redondeo de tasas a 10 decimales para guardar o mostrar."""
    return D(x).quantize(DECIMALES_TASA, rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------- tasas
@dataclass(frozen=True)
class Tasa:
    """Tasa pactada tal como la ingresa la tienda."""

    tipo: str                       # NOMINAL o EFECTIVA
    valor_pct: Decimal              # en porcentaje: 3.5 = 3.5 %
    periodo_dias: int               # 30 = mensual, 360 = anual, 90 = trimestral...
    capitalizacion_dias: int | None = None  # solo nominal; 1 = diaria (valor por defecto del curso)

    def __post_init__(self) -> None:
        if self.tipo not in (NOMINAL, EFECTIVA):
            raise ValueError("tipo de tasa debe ser NOMINAL o EFECTIVA")
        if self.periodo_dias <= 0:
            raise ValueError("periodo_dias debe ser mayor a 0")
        if D(self.valor_pct) < 0:
            raise ValueError("la tasa no puede ser negativa")
        if self.tipo == NOMINAL:
            cap = self.capitalizacion_dias or 1
            if cap <= 0 or cap > self.periodo_dias:
                raise ValueError("la capitalización debe estar entre 1 día y el periodo de la tasa")


def tasa_efectiva_periodo(t: Tasa, dias: int | Decimal) -> Decimal:
    """
    TEP equivalente para un plazo de `dias` días.

    Efectiva:  TEP = (1 + TE) ^ (dias / periodo) - 1
    Nominal:   TEP = (1 + TN / m) ^ n - 1
               m = periodo / días de capitalización   (capitalizaciones por periodo de la TN)
               n = dias / días de capitalización      (capitalizaciones en el plazo)
    """
    dias = D(dias)
    if dias == 0:
        return CERO
    i = D(t.valor_pct) / CIEN
    if t.tipo == EFECTIVA:
        return (UNO + i) ** (dias / D(t.periodo_dias)) - UNO
    cap = D(t.capitalizacion_dias or 1)
    m = D(t.periodo_dias) / cap
    n = dias / cap
    return (UNO + i / m) ** n - UNO


def tem(t: Tasa) -> Decimal:
    """Tasa efectiva mensual (30 días)."""
    return tasa_efectiva_periodo(t, DIAS_MES)


def tea(t: Tasa) -> Decimal:
    """Tasa efectiva anual (360 días)."""
    return tasa_efectiva_periodo(t, DIAS_ANIO)


def resumen_tasa(t: Tasa) -> dict[str, Decimal]:
    """Equivalencias en porcentaje, útiles para la interfaz y el informe."""
    return {
        "ted_pct": tasa_q(tasa_efectiva_periodo(t, 1) * CIEN),
        "tem_pct": tasa_q(tem(t) * CIEN),
        "tea_pct": tasa_q(tea(t) * CIEN),
    }


def validar_tope(t: Tasa, tope_tea_pct: Decimal, nombre: str) -> None:
    """La TEA de la tasa pactada no puede superar el tope vigente (BCRP)."""
    tea_pct = tea(t) * CIEN
    if tea_pct > D(tope_tea_pct):
        raise ValueError(
            f"La {nombre} equivale a una TEA de {tasa_q(tea_pct)} %, "
            f"que supera el tope vigente de {D(tope_tea_pct)} %"
        )


# ------------------------------------------------------------------ fechas
def sumar_meses(f: date, meses: int) -> date:
    y, m = divmod(f.month - 1 + meses, 12)
    anio, mes = f.year + y, m + 1
    dia = min(f.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def fecha_pago_de_corte(fecha_corte: date, dia_pago: int) -> date:
    """Primera fecha con día = dia_pago posterior a la fecha de corte."""
    candidata = date(fecha_corte.year, fecha_corte.month, dia_pago)
    return candidata if dia_pago > fecha_corte.day else sumar_meses(candidata, 1)


@dataclass(frozen=True)
class Ciclo:
    fecha_corte: date
    fecha_pago: date


def ciclo_de_compra(fecha_hora: datetime, dia_corte: int, hora_corte: time, dia_pago: int) -> Ciclo:
    """
    Decide en qué ciclo de facturación cae una compra.

    Si la compra se hace ANTES de la fecha y hora de corte de su mes, pertenece a ese corte;
    si no, al corte del mes siguiente (enunciado, punto 5).
    `fecha_hora` debe venir en la hora local de la tienda (con tzinfo).
    """
    corte_mes = date(fecha_hora.year, fecha_hora.month, dia_corte)
    corte_dt = datetime.combine(corte_mes, hora_corte, tzinfo=fecha_hora.tzinfo)
    fecha_corte = corte_mes if fecha_hora < corte_dt else sumar_meses(corte_mes, 1)
    return Ciclo(fecha_corte=fecha_corte, fecha_pago=fecha_pago_de_corte(fecha_corte, dia_pago))


def dias_entre(inicio: date, fin: date) -> int:
    return (fin - inicio).days


# ------------------------------------------------------ compra a fin de mes
@dataclass(frozen=True)
class ResultadoFinDeMes:
    dias: int
    interes: Decimal
    total: Decimal


def compra_fin_de_mes(monto: Decimal, fecha_compra: date, fecha_pago: date, t: Tasa) -> ResultadoFinDeMes:
    """Interés compensatorio por los días entre la compra y la fecha de pago (punto 5)."""
    dias = dias_entre(fecha_compra, fecha_pago)
    interes = dinero(D(monto) * tasa_efectiva_periodo(t, dias))
    return ResultadoFinDeMes(dias=dias, interes=interes, total=dinero(D(monto) + interes))


# ---------------------------------------------------- compra en cuotas (francés)
@dataclass(frozen=True)
class FilaCronograma:
    numero: int
    fecha_vencimiento: date
    saldo_inicial: Decimal
    interes: Decimal
    amortizacion: Decimal
    cuota: Decimal
    saldo_final: Decimal


@dataclass(frozen=True)
class ResultadoCuotas:
    dias_gracia: int
    interes_gracia: Decimal
    monto_capitalizado: Decimal
    tem: Decimal
    cuota: Decimal
    filas: list[FilaCronograma]
    total_intereses: Decimal
    total_pagado: Decimal
    tcea_pct: Decimal


def compra_en_cuotas(
    monto: Decimal, fecha_compra: date, fecha_pago_ciclo: date, n: int, t: Tasa
) -> ResultadoCuotas:
    """
    Método francés vencido ordinario con meses de 30 días (punto 4).

    1. Periodo de gracia total: días entre la compra y la fecha de pago de su ciclo;
       la deuda se capitaliza: P' = P * (1 + TEP_gracia).
    2. Cuota constante: R = P' * i / (1 - (1 + i)^-n), con i = TEM.
    3. Primera cuota un mes después de la fecha de pago del ciclo.
       La última cuota ajusta el redondeo para que el saldo quede en cero.
    """
    if n < 1:
        raise ValueError("El número de cuotas debe ser al menos 1")
    monto = D(monto)
    dias_gracia = dias_entre(fecha_compra, fecha_pago_ciclo)
    capitalizado = dinero(monto * (UNO + tasa_efectiva_periodo(t, dias_gracia)))
    i = tem(t)
    if i == 0:
        cuota = dinero(capitalizado / n)
    else:
        cuota = dinero(capitalizado * i / (UNO - (UNO + i) ** (-n)))

    filas: list[FilaCronograma] = []
    saldo = capitalizado
    for k in range(1, n + 1):
        interes = dinero(saldo * i)
        if k == n:
            amort = saldo
            cuota_k = amort + interes
        else:
            amort = cuota - interes
            cuota_k = cuota
        filas.append(
            FilaCronograma(
                numero=k,
                fecha_vencimiento=sumar_meses(fecha_pago_ciclo, k),
                saldo_inicial=saldo,
                interes=interes,
                amortizacion=amort,
                cuota=cuota_k,
                saldo_final=saldo - amort,
            )
        )
        saldo -= amort

    total_pagado = sum((f.cuota for f in filas), CERO)
    flujos = [(f.fecha_vencimiento, f.cuota) for f in filas]
    return ResultadoCuotas(
        dias_gracia=dias_gracia,
        interes_gracia=capitalizado - dinero(monto),
        monto_capitalizado=capitalizado,
        tem=tasa_q(i),
        cuota=cuota,
        filas=filas,
        total_intereses=total_pagado - dinero(monto),
        total_pagado=total_pagado,
        tcea_pct=tasa_q(tcea(monto, fecha_compra, flujos) * CIEN),
    )


# ---------------------------------------------------------------- TCEA (TIR)
def tcea(monto: Decimal, fecha_inicio: date, flujos: list[tuple[date, Decimal]], tol: Decimal = D("1e-7")) -> Decimal:
    """
    Tasa de costo efectivo anual: TIR anual (base 360) que iguala el monto financiado
    con el valor presente de las cuotas. Se resuelve por bisección.
    """
    monto = D(monto)

    def van(r: Decimal) -> Decimal:
        return sum(
            (D(c) / (UNO + r) ** (D(dias_entre(fecha_inicio, f)) / DIAS_ANIO) for f, c in flujos), CERO
        ) - monto

    lo, hi = CERO, D("100")  # 0 % a 10 000 % anual
    if van(lo) <= 0:
        return CERO
    for _ in range(300):
        mid = (lo + hi) / 2
        v = van(mid)
        if abs(v) < tol:
            return mid
        if v > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# --------------------------------------------------------------------- mora
@dataclass(frozen=True)
class ResultadoMora:
    dias_mora: int
    interes_moratorio: Decimal


def dias_mora(fecha_vencimiento: date, fecha_pago_real: date) -> int:
    """Días de atraso: fecha real de pago − fecha de pago pactada (0 si pagó a tiempo)."""
    return max(0, dias_entre(fecha_vencimiento, fecha_pago_real))


def interes_moratorio(base: Decimal, fecha_vencimiento: date, fecha_pago_real: date, t_mora: Tasa) -> ResultadoMora:
    """
    Interés moratorio sobre el pago total que debió hacerse en la fecha pactada,
    por los días transcurridos de mora (punto 6).
        IM = base × [(1 + TEP_mora)^(días de mora) − 1]
    """
    dias = dias_mora(fecha_vencimiento, fecha_pago_real)
    if dias == 0:
        return ResultadoMora(0, CERO)
    return ResultadoMora(dias, dinero(D(base) * tasa_efectiva_periodo(t_mora, dias)))


def interes_compensatorio_mora(base: Decimal, fecha_vencimiento: date, fecha_pago_real: date, t_comp: Tasa) -> Decimal:
    """
    Interés compensatorio por los días de atraso (punto 5: "también se deberá pagar intereses
    por los días en exceso"). El dinero se sigue usando durante la mora, así que el compensatorio
    sigue corriendo; el moratorio se suma aparte como penalidad.
        IC_mora = base × [(1 + TEP_comp)^(días de mora) − 1]
    """
    dias = dias_mora(fecha_vencimiento, fecha_pago_real)
    if dias == 0:
        return CERO
    return dinero(D(base) * tasa_efectiva_periodo(t_comp, dias))


# ---------------------------------------------------------------- prelación
@dataclass(frozen=True)
class Imputacion:
    orden: int
    concepto: str
    exigible: Decimal
    imputado: Decimal
    saldo: Decimal


def aplicar_prelacion(
    monto_pagado: Decimal, mora: Decimal, interes_comp_mora: Decimal, interes: Decimal, capital: Decimal
) -> list[Imputacion]:
    """
    Aplica un pago en orden (Anexo A: mora -> interés compensatorio -> capital):
      1) interés moratorio
      2) interés compensatorio por los días de atraso
      3) interés compensatorio del listado
      4) capital
    """
    restante = D(monto_pagado)
    resultado: list[Imputacion] = []
    conceptos = (
        ("INTERES_MORATORIO", D(mora)),
        ("INTERES_COMPENSATORIO_MORA", D(interes_comp_mora)),
        ("INTERES_COMPENSATORIO", D(interes)),
        ("CAPITAL", D(capital)),
    )
    for orden, (concepto, exigible) in enumerate(conceptos, start=1):
        imputado = min(restante, exigible)
        restante -= imputado
        resultado.append(Imputacion(orden, concepto, exigible, imputado, exigible - imputado))
    return resultado
