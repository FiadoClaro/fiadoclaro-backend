# Fórmulas de FiadoClaro

Inventario de **todas** las fórmulas y cálculos del backend: qué calcula cada una, para qué sirve, en qué
archivo y línea está, y quién la usa. Todos los cálculos financieros viven en
[`app/modules/finance/engine.py`](app/modules/finance/engine.py); los demás módulos solo los llaman y suman
o restan sus resultados.

Notación usada en este documento:

| Símbolo | Significado |
|---|---|
| `P` | Monto (capital) |
| `i` | Tasa en fracción (3.5 % → 0.035) |
| `TE` | Tasa efectiva pactada (en fracción) |
| `TN` | Tasa nominal pactada (en fracción) |
| `TEP` | Tasa efectiva del plazo que se está calculando |
| `TED`, `TEM`, `TEA` | Tasa efectiva diaria (1 día), mensual (30 días) y anual (360 días) |
| `p` | Días del periodo de la tasa pactada (30 = mensual, 360 = anual, 90 = trimestral…) |
| `c` | Días de capitalización de una tasa nominal (1 = diaria) |
| `d` | Días del plazo |
| `n` | Número de cuotas |
| `R` | Cuota constante del método francés |

---

## Índice

0. [Convenciones y constantes](#0-convenciones-y-constantes)
1. [Redondeo](#1-redondeo)
2. [Tasas de interés](#2-tasas-de-interés)
3. [Fechas, días y ciclo de facturación](#3-fechas-días-y-ciclo-de-facturación)
4. [Compra a fin de mes](#4-compra-a-fin-de-mes)
5. [Compra en cuotas (método francés)](#5-compra-en-cuotas-método-francés)
6. [TCEA](#6-tcea-tasa-de-costo-efectivo-anual)
7. [Mora](#7-mora)
8. [Listado de pago (estado de cuenta)](#8-listado-de-pago-estado-de-cuenta)
9. [Pago y prelación](#9-pago-y-prelación)
10. [Crédito del cliente](#10-crédito-del-cliente)
11. [Reglas y rangos numéricos (validaciones)](#11-reglas-y-rangos-numéricos-validaciones)
12. [Cálculos no financieros](#12-cálculos-no-financieros)
13. [Mapa: qué fórmula se usa en cada operación](#13-mapa-qué-fórmula-se-usa-en-cada-operación)
14. [Observaciones para la exposición](#14-observaciones-para-la-exposición)

---

## 0. Convenciones y constantes

Fuente: Anexo A del enunciado. Archivo: [engine.py:23-36](app/modules/finance/engine.py#L23-L36).

| Constante | Valor | Para qué |
|---|---|---|
| `DIAS_ANIO` | 360 | Año comercial: la TEA es la tasa de 360 días |
| `DIAS_MES` | 30 | Mes comercial: la TEM es la tasa de 30 días |
| `getcontext().prec` | 34 | Precisión interna de `Decimal` (34 dígitos significativos). Nunca se usa `float` |
| `CENTIMO` | 0.01 | Redondeo de montos |
| `DECIMALES_TASA` | 0.0000000001 | Redondeo de tasas a 10 decimales (el enunciado exige al menos 7) |

**Tasas de entrada:** siempre en **porcentaje** (`3.5` significa 3.5 %). Antes de calcular se dividen
entre 100: `i = valor_pct / 100` ([engine.py:85](app/modules/finance/engine.py#L85)).

**Tipos de columna** ([app/core/types.py](app/core/types.py)):

| Tipo | Definición | Uso |
|---|---|---|
| `Monto` | `NUMERIC(12,2)` | Todos los montos en soles/dólares |
| `Tasa` | `NUMERIC(12,7)` | Tasas pactadas en % (7 decimales) |
| `TasaDerivada` | `NUMERIC(16,10)` | TEM, TEA y TCEA calculadas (fracción, 10 decimales) |
| `Cantidad` | `NUMERIC(10,3)` | Cantidades de producto (ej. 2.500 kg) |

---

## 1. Redondeo

### 1.1 Redondeo monetario
```
dinero(x) = x redondeado a 2 decimales, half up
```
- **Dónde:** `dinero()` en [engine.py:40](app/modules/finance/engine.py#L40).
- **Para qué:** todo monto que se muestra o se guarda (intereses, cuotas, totales, mora). Anexo A:
  "redondeo para expresiones monetarias con 2 decimales".
- **Half up:** 0.005 sube (10.005 → 10.01; 2.675 → 2.68). Con `float`, 2.675 daría 2.67.

### 1.2 Redondeo de tasas
```
tasa_q(x) = x redondeado a 10 decimales, half up
```
- **Dónde:** `tasa_q()` en [engine.py:45](app/modules/finance/engine.py#L45).
- **Para qué:** guardar o mostrar TED/TEM/TEA/TCEA. Anexo A: "tasa de interés … por lo menos 7 decimales".
- Los cálculos intermedios **no** se redondean: se usa la tasa con 34 dígitos y solo se redondea el
  resultado final.

---

## 2. Tasas de interés

### 2.1 Tasa efectiva de un plazo (fórmula central)
Función `tasa_efectiva_periodo(t, d)` en [engine.py:73-91](app/modules/finance/engine.py#L73-L91).
Todas las demás fórmulas de interés se apoyan en esta.

**Si la tasa pactada es EFECTIVA** (conversión entre efectivas):
```
TEP = (1 + TE) ^ (d / p) − 1
```

**Si la tasa pactada es NOMINAL** (conversión nominal → efectiva):
```
m   = p / c        capitalizaciones que hay en el periodo de la tasa nominal
n   = d / c        capitalizaciones que hay en el plazo
TEP = (1 + TN / m) ^ n − 1
```
- Si no se indica capitalización, `c = 1` (**diaria**, regla del curso).
- Si `d = 0` → `TEP = 0` (no hay interés).
- **Para qué:** convertir la tasa pactada (nominal o efectiva, de cualquier periodo) a la tasa exacta
  del plazo que se necesita: los días de una compra, de un mes, de la mora, etc. Anexo A: "fórmula de
  conversión explícita para tasa nominal y efectiva".

| Ejemplo | Cálculo | Resultado |
|---|---|---|
| TEM 3.5 % → TEA | 1.035^(360/30) − 1 | 51.10686573 % |
| TEA 12 % → TEM | 1.12^(30/360) − 1 | 0.94887929 % |
| TEM 3 % → TED | 1.03^(1/30) − 1 | 0.09857790 % |
| TNA 36 % cap. diaria → TEM | (1 + 0.36/360)^30 − 1 | 3.04390875 % |
| TNA 36 % cap. diaria → TEA | (1 + 0.36/360)^360 − 1 | 43.30716103 % |
| TNA 24 % cap. mensual → TEM | (1 + 0.24/12)^1 − 1 | 2 % |
| TNA 24 % cap. mensual → trimestral (90 días) | (1 + 0.24/12)^3 − 1 | 6.12080 % |

### 2.2 TEM, TEA y TED
```
TEM = TEP con d = 30       → tem()  en engine.py:94
TEA = TEP con d = 360      → tea()  en engine.py:99
TED = TEP con d = 1        → dentro de resumen_tasa()
```
- **Para qué:**
  - **TEM:** es la `i` del método francés (sección 5) y se guarda en cada compra (`compra.tem`).
  - **TEA:** para compararla con el tope del BCRP (2.4) y se guarda en cada compra (`compra.tea`).
  - **TED, TEM y TEA:** se muestran juntas como "equivalencias" en la interfaz.

### 2.3 Resumen de equivalencias
```
ted_pct = tasa_q(TED × 100)
tem_pct = tasa_q(TEM × 100)
tea_pct = tasa_q(TEA × 100)
```
- **Dónde:** `resumen_tasa()` en [engine.py:104-110](app/modules/finance/engine.py#L104-L110).
- **Usada en:**
  - `POST /finance/equivalencias` ([finance/router.py:14](app/modules/finance/router.py#L14)): convertidor de tasas.
  - Datos del cliente ([customers/service.py:40](app/modules/customers/service.py#L40)).
  - Simulación y detalle de compra ([purchases/service.py:48](app/modules/purchases/service.py#L48)).

### 2.4 Tope de tasa (BCRP)
```
TEA_pactada × 100 ≤ tea_maxima vigente (mismo tipo y misma moneda del crédito)     (si no, se rechaza)
```
- **Base legal:** art. 1243 del Código Civil y Circular N° 0008-2021-BCRP (operaciones entre personas ajenas
  al sistema financiero). El BCRP recalcula la compensatoria cada semestre (mayo y noviembre); la moratoria
  máxima es el 15 % de la compensatoria. Todo en TEA.
- **Relación entre topes** (la publica el BCRP; el sistema guarda ambos valores tal como se publican):
  ```
  TEA_moratoria_máxima = 15 % × TEA_compensatoria_máxima       (misma moneda y mismo semestre)
  ```
  Comprobación: 114.68 × 0.15 = 17.20 (soles); 103.14 × 0.15 = 15.47 (dólares); 114.13 × 0.15 = 17.12.
- **Valores cargados en la tabla `tope_tasa`:**

  | Tipo | Soles (PEN) | Dólares (USD) | Vigencia |
  |---|---|---|---|
  | Compensatoria | 114.68 % | 103.14 % | desde el 01/11/2026 (noviembre 2026 – abril 2027) |
  | Moratoria | 17.20 % | 15.47 % | desde el 01/11/2026 (noviembre 2026 – abril 2027) |
  | Compensatoria | 114.13 % | — | 01/05/2026 – 31/10/2026 (semestre anterior) |
  | Moratoria | 17.12 % | — | 01/05/2026 – 31/10/2026 (semestre anterior) |

  Los del semestre anterior se conservan como historial: cada compra se valida con el tope vigente **en su
  fecha**, y las compras de demostración son de setiembre y octubre de 2026.
- **Actualización semestral:** el BCRP publica nuevos topes en mayo y noviembre. Al salir la publicación,
  el administrador del sistema registra 4 filas nuevas (compensatoria y moratoria, en soles y en dólares)
  con `POST /finance/topes`, indicando `vigente_desde` y la fuente. No se borra nada: las filas anteriores
  quedan como historial y el sistema elige automáticamente la que rige para cada fecha.

- **Dónde:** `validar_tope()` en [engine.py](app/modules/finance/engine.py); `validar_topes()` en
  [finance/service.py](app/modules/finance/service.py) la aplica a la compensatoria **y** a la moratoria.
- **Tope vigente:** el registro de `tope_tasa` del mismo tipo y moneda con la `vigente_desde` más reciente que
  sea `≤` la fecha evaluada (las compras antiguas se validan con el tope de su fecha).
- **Para qué:** ninguna tasa pactada puede superar la máxima del BCRP. Se valida al crear o editar las
  condiciones del cliente y al registrar cada compra.
- Ejemplo: TEM 3.5 % → TEA 51.11 % ≤ 114.68 % ✔. Una TEA de 110 % pasa en soles pero no en dólares (103.14 %).

### 2.5 Copia de la tasa (snapshot)
No es una fórmula, pero define **qué tasa entra** en cada fórmula:
- **Compensatoria:** cada compra copia la tasa del cliente al registrarse
  ([purchases/service.py:157-160](app/modules/purchases/service.py#L157-L160)). Intereses, cuotas y
  compensatorio por atraso usan **la tasa de la compra**, no la actual del cliente.
- **Moratoria:** cada listado copia la tasa moratoria del cliente el día del corte
  ([statements/service.py](app/modules/statements/service.py), al crear el `EstadoCuenta`). La mora usa
  **la tasa del listado**.

---

## 3. Fechas, días y ciclo de facturación

### 3.1 Días entre dos fechas
```
días = fecha_final − fecha_inicial       (días calendario)
```
- **Dónde:** `dias_entre()` en [engine.py:157](app/modules/finance/engine.py#L157).
- **Convención:** el primer día no se cuenta y el último sí (15/09 → 26/09 = 11 días).
- **Para qué:** días de gracia o de interés de una compra, días de mora, plazo de cada flujo en la TCEA.

### 3.2 Sumar meses
```
(año, mes) + k meses; día = mín(día original, último día del mes destino)
```
- **Dónde:** `sumar_meses()` en [engine.py:124](app/modules/finance/engine.py#L124).
- **Para qué:** fechas de vencimiento de las cuotas (26/09 + 1 mes = 26/10) y pasar al corte del mes
  siguiente. Si el día no existe (31/01 + 1 mes) usa el último día del mes (28/02).

### 3.3 Fecha de pago de un corte
```
si dia_pago > día del corte → fecha de pago = mismo mes del corte, día dia_pago
si no                       → fecha de pago = mes siguiente al corte, día dia_pago
```
- **Dónde:** `fecha_pago_de_corte()` en [engine.py:131](app/modules/finance/engine.py#L131).
- **Para qué:** saber cuándo vence el listado de un corte. Corte el 20, pago el 26 → 26 del mismo mes.
  Corte el 25, pago el 5 → 5 del mes siguiente.
- **Usada en:** `ciclo_de_compra()` y al generar el listado
  ([statements/service.py:79](app/modules/statements/service.py#L79)).

### 3.4 Ciclo de una compra
```
momento_corte = fecha (año y mes de la compra, día de corte) a la hora de corte (hora de Lima)
si fecha_hora_compra < momento_corte → fecha_corte = ese corte
si no                                → fecha_corte = corte del mes siguiente
fecha_pago = fecha_pago_de_corte(fecha_corte, dia_pago)
```
- **Dónde:** `ciclo_de_compra()` en [engine.py:143](app/modules/finance/engine.py#L143).
- **Para qué:** punto 5 del enunciado: una compra antes de la fecha **y hora** de corte entra en ese
  ciclo; si no, "su obligación de pago será en el mes inmediatamente posterior".
- **Borde:** una compra **exactamente** a la hora de corte pasa al ciclo siguiente (se usa `<`).
- **Usada en:** registro y simulación de compras
  ([purchases/service.py:106](app/modules/purchases/service.py#L106)) y "próximo corte / próximo pago"
  del cliente ([customers/service.py:67](app/modules/customers/service.py#L67)).

| Compra | Corte | Hora corte | Día pago | Fecha de corte | Fecha de pago |
|---|---|---|---|---|---|
| 15/09 10:00 | 20 | 18:00 | 26 | 20/09 | 26/09 |
| 20/09 17:59 | 20 | 18:00 | 26 | 20/09 | 26/09 |
| 20/09 18:00 | 20 | 18:00 | 26 | 20/10 | 26/10 |
| 10/11 12:00 | 25 | 18:00 | 5 | 25/11 | 05/12 |
| 28/12 12:00 | 25 | 18:00 | 5 | 25/01 | 05/02 |

---

## 4. Compra a fin de mes

Punto 5: pagan intereses "por los días transcurridos entre la fecha de compra y la fecha de pago".

```
d       = fecha_pago − fecha_compra
interés = dinero( P × TEP(d) )
total   = dinero( P + interés )
```
- **Dónde:** `compra_fin_de_mes()` en [engine.py:169-173](app/modules/finance/engine.py#L169-L173).
- **Usada en:** [purchases/service.py:112](app/modules/purchases/service.py#L112).
- **Se guarda como una sola cuota** ([purchases/service.py:113-114](app/modules/purchases/service.py#L113-L114)):
  `saldo_inicial = P`, `interés`, `amortización = P`, `cuota = total`, `saldo_final = 0`.
  En la compra: `interes_total = interés`, `monto_capitalizado = P`, `valor_cuota = total`.
- El interés es **compuesto**: 60 días a TEM 3 % = 1.03² − 1 = 6.09 %, no 6 %.

| Monto | Tasa | Días | Interés |
|---|---|---|---|
| 1000 | TEM 3 % | 1 / 15 / 30 / 60 / 90 / 180 / 360 | 0.99 / 14.89 / 30.00 / 60.90 / 92.73 / 194.05 / 425.76 |
| 100 | TEM 3.5 % | 20 | 2.32 |
| 500 | TEM 3.5 % | 45 | 26.48 |
| 1000 | TNA 36 % cap. diaria | 30 | 30.44 |

---

## 5. Compra en cuotas (método francés)

Punto 4: "método francés vencido simple ordinario (tomando en cuenta meses de 30 días)", con periodo de
gracia total capitalizado. Función `compra_en_cuotas()` en
[engine.py:201-259](app/modules/finance/engine.py#L201-L259). Usada en
[purchases/service.py:119](app/modules/purchases/service.py#L119).

### 5.1 Periodo de gracia total (capitalización)
```
d_gracia        = fecha_pago_del_ciclo − fecha_compra
P'              = dinero( P × (1 + TEP(d_gracia)) )        monto capitalizado
interés_gracia  = P' − P
```
- **Para qué:** entre la compra y la primera fecha de pago no se paga nada, pero el interés corre y se
  suma al capital antes de calcular la cuota (ejemplo del enunciado: 15/09 → 26/09 = 11 días).

### 5.2 Cuota constante
```
i = TEM
R = dinero( P' × i / (1 − (1 + i)^(−n)) )
si i = 0 → R = dinero( P' / n )
```

### 5.3 Cronograma (para cada cuota k = 1 … n)
```
fecha_vencimiento_k = sumar_meses(fecha_pago_del_ciclo, k)
saldo_inicial_1     = P'
interés_k           = dinero( saldo_inicial_k × i )
amortización_k      = R − interés_k                     (k < n)
amortización_n      = saldo_inicial_n                   (última: cancela el saldo)
cuota_k             = R                                 (k < n)
cuota_n             = amortización_n + interés_n        (última: ajusta el redondeo)
saldo_final_k       = saldo_inicial_k − amortización_k
saldo_inicial_k+1   = saldo_final_k
```
- La primera cuota vence **un mes después** de la fecha de pago del ciclo.
- **Ajuste de la última cuota:** como `R` se redondea a céntimos, se acumula una diferencia de a lo más
  `0.005 × Σ (1 + i)^k` (k = 0 … n−1). La última cuota la absorbe para que el saldo termine exactamente
  en 0. Con 3 cuotas es 1 o 2 céntimos; con 24 cuotas puede llegar a unos 10 céntimos.

### 5.4 Totales de la compra en cuotas
```
total_pagado     = Σ cuota_k
total_intereses  = total_pagado − P          (incluye el interés de la gracia)
Σ amortización_k = P'
```
En la compra se guarda: `interes_total = total_intereses`, `monto_capitalizado = P'`, `valor_cuota = R`,
`tem = tasa_q(TEM)`, `tea = tasa_q(TEA)` ([purchases/service.py:160](app/modules/purchases/service.py#L160)).

### 5.5 Ejemplos
**Sin gracia:** 1000 a TEM 3 %, 3 cuotas → `R = 353.53`

| k | Saldo inicial | Interés | Amortización | Cuota | Saldo final |
|---|---|---|---|---|---|
| 1 | 1000.00 | 30.00 | 323.53 | 353.53 | 676.47 |
| 2 | 676.47 | 20.29 | 333.24 | 353.53 | 343.23 |
| 3 | 343.23 | 10.30 | 343.23 | 353.53 | 0.00 |

**Ejemplo del enunciado:** 1000 a TEM 3 %, compra 15/09, pago 26/09, 3 cuotas → 11 días de gracia,
`P' = 1010.90`, `R = 357.38`

| k | Vence | Saldo inicial | Interés | Amortización | Cuota | Saldo final |
|---|---|---|---|---|---|---|
| 1 | 26/10 | 1010.90 | 30.33 | 327.05 | 357.38 | 683.85 |
| 2 | 26/11 | 683.85 | 20.52 | 336.86 | 357.38 | 346.99 |
| 3 | 26/12 | 346.99 | 10.41 | 346.99 | 357.40 | 0.00 |

Total pagado 1072.16; intereses 72.16 (10.90 de gracia + 61.26 de las cuotas).

---

## 6. TCEA (tasa de costo efectivo anual)

```
Buscar r tal que:   VAN(r) = Σ [ pago_k / (1 + r)^(días_k / 360) ] − P = 0
Cuotas:      días_k = días de gracia + 30 × k        (mes comercial de 30 días, Anexo A)
Fin de mes:  días   = días entre la compra y la fecha de pago
TCEA % = tasa_q(r × 100)
```
- **Dónde:** `tcea(monto, flujos)` en [engine.py](app/modules/finance/engine.py); `flujos` = [(días, monto)].
- **Método:** bisección entre 0 y 100 (0 % a 10 000 % anual), hasta 300 iteraciones o `|VAN| < 1e-7`.
  Si `VAN(0) ≤ 0` (no hay interés) → TCEA = 0.
- **Convención de 30 días:** cada cuota se ubica a "gracia + 30 días por mes", no por los días reales del
  calendario. Así, sin gracia ni costos extra, la TCEA coincide con la TEA, y febrero u octubre dan el mismo
  resultado. Con gracia, la TCEA queda un poco por encima de la TEA porque esa gracia se capitaliza.
- **Para qué:** costo total anual del crédito para el cliente (incluye la gracia).
- **Usada en:** `compra_en_cuotas()` (todo el cronograma) y en las compras a fin de mes
  ([purchases/service.py](app/modules/purchases/service.py)), con un solo pago. Se guarda como fracción en `compra.tcea`.

---

## 7. Mora

Punto 5: "intereses por los días en exceso (días de mora)". Punto 6: "intereses moratorios del pago
total que debería haber sido en una fecha determinada y los días transcurridos de mora, al cual se le
aplica la tasa de interés moratoria pactada".

### 7.1 Días de mora
```
días_mora = máx(0, fecha_pago_real − fecha_pago_pactada)
```
- **Dónde:** `dias_mora()` en [engine.py:297](app/modules/finance/engine.py#L297).
- Pagar antes o el mismo día pactado → 0 (nunca negativo).

### 7.2 Interés moratorio
```
IM = dinero( base × TEP_moratoria(días_mora) )
base = total_a_pagar del listado (el pago total que debió hacerse)
```
- **Dónde:** `interes_moratorio()` en [engine.py:302](app/modules/finance/engine.py#L302); aplicado en
  `calcular_mora()` ([statements/service.py:49](app/modules/statements/service.py#L49)).
- **Tasa:** **una sola**, la moratoria copiada en el listado el día del corte (`estado_cuenta.tasa_mora`).
- **Para qué:** penalidad por pagar tarde. Se muestra como ítem `INTERES_MORA` del listado.

### 7.3 Interés compensatorio por los días de atraso
```
IC_mora = Σ  dinero( cuota_j × TEP_compensatoria_de_su_compra(días_mora) )
          j ∈ líneas del listado
```
- **Dónde:** `interes_compensatorio_mora()` en [engine.py:314](app/modules/finance/engine.py#L314);
  sumado línea por línea en `calcular_mora()` ([statements/service.py:61-63](app/modules/statements/service.py#L61-L63)).
- **Tasa:** la compensatoria **copiada en cada compra**.
- **Para qué:** durante la mora el cliente sigue usando el dinero, así que sigue corriendo el interés
  compensatorio además del moratorio. Se muestra como ítem `INTERES_COMP_MORA` del listado.
- Misma fórmula que el moratorio; solo cambia la tasa.

### 7.4 Total de la mora
```
mora_total = dinero( IM + IC_mora )
```
- **Dónde:** `Mora.total` en [statements/service.py:45](app/modules/statements/service.py#L45).

| Base | Tasa | Días de atraso | Resultado |
|---|---|---|---|
| 46.68 | Moratoria TEM 2 % | 10 | IM = 0.31 |
| 1000 | Moratoria TEM 2 % | 30 | IM = 20.00 |
| 1000 | Moratoria TEA 15 % | 45 | IM = 17.62 |
| 1000 | Moratoria TNA 18 % cap. diaria | 15 | IM = 7.53 |
| 1000 | Compensatoria TEM 3.5 % | 10 | IC_mora = 11.53 |

---

## 8. Listado de pago (estado de cuenta)

Punto 6: se genera en la fecha de corte con las compras ordenadas por fecha y sus intereses.

### 8.1 Qué cuotas entran
```
cuotas del cliente con: compra VIGENTE, cuota PENDIENTE, sin listado asignado
                        y fecha_vencimiento ≤ fecha_pago del listado
```
- **Dónde:** `_generar_para()` en [statements/service.py](app/modules/statements/service.py).
- Solo se puede generar si `ahora ≥ fecha_corte + hora_corte`.

### 8.2 Totales del listado
```
total_capital  = dinero( Σ amortización_j )
total_interes  = dinero( Σ interés_j )
total_a_pagar  = dinero( Σ cuota_j )          (= total_capital + total_interes; sin mora)
```
- **Dónde:** `_recalcular_totales()` en [statements/service.py:68-71](app/modules/statements/service.py#L68-L71).

### 8.3 Total exigible a una fecha
```
total_exigible = dinero( total_a_pagar + mora_total )
```
- **Dónde:** detalle del listado ([statements/service.py:203](app/modules/statements/service.py#L203)) y
  cotización del pago ([payments/service.py:41](app/modules/payments/service.py#L41)).
- La mora se calcula **a la fecha de consulta** mientras el listado está pendiente; ya pagado, se toma lo
  guardado en el pago.

### 8.4 Listado vencido
```
vencido = (estado = PENDIENTE) y (hoy > fecha_pago)
```
- **Dónde:** [statements/service.py:149](app/modules/statements/service.py#L149).

---

## 9. Pago y prelación

### 9.1 Pago exacto (sin pagos parciales)
```
monto_pagado = total_exigible a la fecha de pago     (si no, se rechaza)
fecha_corte ≤ fecha_pago ≤ hoy
```
- **Dónde:** [payments/service.py:53](app/modules/payments/service.py#L53) y `_fecha_valida()` en el mismo
  archivo. Punto 5: "no debe permitirse … pagos parciales".

### 9.2 Prelación (orden de imputación)
Anexo A: "orden de imputación o prelación de pagos como mora, interés compensatorio y capital".
```
restante = monto_pagado
para cada concepto, en este orden:
    1. INTERES_MORATORIO            (IM)
    2. INTERES_COMPENSATORIO_MORA   (IC_mora)
    3. INTERES_COMPENSATORIO        (total_interes del listado)
    4. CAPITAL                      (total_capital del listado)
  imputado = mín(restante, exigible)
  restante = restante − imputado
  saldo    = exigible − imputado
```
- **Dónde:** `aplicar_prelacion()` en [engine.py:337](app/modules/finance/engine.py#L337).
- **Usada en:** cotización ([payments/service.py:42](app/modules/payments/service.py#L42)) y para
  reconstruir la imputación de un pago guardado
  ([payments/service.py:94](app/modules/payments/service.py#L94)).
- Como el pago siempre es exacto, todos los conceptos quedan con saldo 0. El orden sirve para dejar
  registrado a qué se aplicó cada sol.

### 9.3 Cuadre del pago (en la base de datos)
```
monto_total = monto_mora + monto_interes_comp_mora + monto_interes + monto_capital
dias_mora ≥ 0
```
- **Dónde:** restricciones `CHECK` de la tabla `pago`
  ([payments/models.py:19-23](app/modules/payments/models.py#L19-L23)).

### 9.4 Efectos del pago
- Listado → `PAGADO`; sus cuotas → `PAGADA`.
- Una compra pasa a `CANCELADA` cuando **todas** sus cuotas están `PAGADA`.

Ejemplo (listado de 46.68 pagado con 10 días de atraso):

| Orden | Concepto | Imputado |
|---|---|---|
| 1 | Interés moratorio | 0.31 |
| 2 | Compensatorio por atraso | 0.54 |
| 3 | Compensatorio del listado | 1.18 |
| 4 | Capital | 45.50 |
| | **Total** | **47.53** |

---

## 10. Crédito del cliente

### 10.1 Subtotal y monto de la compra
```
subtotal_línea = dinero( cantidad × precio_lista_credito )
monto_compra   = dinero( Σ subtotal_línea )
```
- **Dónde:** [purchases/service.py:83](app/modules/purchases/service.py#L83) y
  [purchases/service.py:93](app/modules/purchases/service.py#L93).
- Se usa el **precio de lista a crédito** del producto, copiado en la compra.

### 10.2 Crédito utilizado
```
utilizado = dinero( Σ amortización de cuotas PENDIENTE de compras VIGENTE )
```
- **Dónde:** `capital_pendiente()` en [customers/service.py:44](app/modules/customers/service.py#L44).
- En compras en cuotas, Σ amortizaciones = `P'` (incluye la gracia capitalizada).

### 10.3 Crédito disponible
```
disponible (al comprar) = dinero( límite − utilizado )                 purchases/service.py:94
disponible (resumen)    = dinero( máx(0, límite − utilizado) )         customers/service.py:66
monto_compra ≤ disponible                                              (si no, se rechaza)
disponible_después      = dinero( disponible − monto_compra )          purchases/service.py:130
```
- Punto 5: "no debe permitirse compras que excedan el monto permitido para el cliente".

### 10.4 Porcentaje utilizado
```
porcentaje_utilizado = dinero( utilizado / límite × 100 )
```
- **Dónde:** [customers/service.py:72](app/modules/customers/service.py#L72).

### 10.5 Estado de pago del cliente
```
EN_MORA si tiene algún listado PENDIENTE con fecha_pago < hoy; si no, AL_DIA
```
- **Dónde:** [customers/service.py:54-73](app/modules/customers/service.py#L54-L73).

### 10.6 Máximo de cuotas de una compra
```
máximo = mín( max_meses del cliente, max_meses de cada producto de la compra )
num_cuotas ≤ máximo                                     (si no, se rechaza)
```
- **Dónde:** [purchases/service.py:88](app/modules/purchases/service.py#L88).

### 10.7 Total a pagar de una compra (al consultarla)
```
total_a_pagar = Σ cuota_k
```
- **Dónde:** [purchases/service.py:199](app/modules/purchases/service.py#L199).

---

## 11. Reglas y rangos numéricos (validaciones)

| Regla | Dónde |
|---|---|
| Tasa en % entre 0 y 1000, hasta 7 decimales | [finance/schemas.py:14](app/modules/finance/schemas.py#L14) |
| Periodo de la tasa entre 1 y 360 días | [finance/schemas.py:15](app/modules/finance/schemas.py#L15) |
| Nominal: capitalización por defecto 1 día; `1 ≤ c ≤ p` | [finance/schemas.py:20-28](app/modules/finance/schemas.py#L20-L28), [engine.py:60-70](app/modules/finance/engine.py#L60-L70) |
| Efectiva: no lleva capitalización | [finance/schemas.py:22-23](app/modules/finance/schemas.py#L22-L23) |
| Tasas ≥ 0 | [customers/models.py:51](app/modules/customers/models.py#L51) |
| TEA ≤ tope BCRP vigente (compensatoria y moratoria) | Sección 2.4 |
| Tope BCRP > 0 | [finance/models.py:20](app/modules/finance/models.py#L20) |
| Límite de crédito > 0, 2 decimales | [customers/schemas.py:25](app/modules/customers/schemas.py#L25), [customers/models.py:52](app/modules/customers/models.py#L52) |
| Máximo de meses del cliente entre 1 y 36 | [customers/schemas.py:26](app/modules/customers/schemas.py#L26), [customers/models.py:53](app/modules/customers/models.py#L53) |
| Día de corte y día de pago entre 1 y 28 | [customers/schemas.py:27-29](app/modules/customers/schemas.py#L27-L29), [customers/models.py:54](app/modules/customers/models.py#L54) |
| Día de corte ≠ día de pago | [customers/schemas.py:33](app/modules/customers/schemas.py#L33), [customers/models.py:55](app/modules/customers/models.py#L55) |
| Precios > 0 | [products/models.py:17](app/modules/products/models.py#L17) |
| Precio de lista a crédito ≥ precio contado | [products/schemas.py:32](app/modules/products/schemas.py#L32) |
| Producto: al menos una modalidad | [products/models.py:18](app/modules/products/models.py#L18) |
| Producto en cuotas: máximo de meses entre 1 y 36 | [products/models.py:19-21](app/modules/products/models.py#L19-L21) |
| Cantidad > 0 (hasta 3 decimales) | [purchases/models.py:80](app/modules/purchases/models.py#L80) |
| Monto de la compra > 0 | [purchases/models.py:24](app/modules/purchases/models.py#L24) |
| Fin de mes → 1 cuota; cuotas → n ≥ 1 (máx. 36) | [purchases/models.py:25-28](app/modules/purchases/models.py#L25-L28) |
| Fecha de la compra ≤ ahora | [purchases/service.py](app/modules/purchases/service.py) (`_calcular`) |
| Moneda del producto = moneda del crédito | [purchases/service.py](app/modules/purchases/service.py) (`_calcular`) |
| No comprar en un ciclo cuyo listado ya se pagó | `_validar_ciclo_abierto()` en [purchases/service.py:135](app/modules/purchases/service.py#L135) |
| DNI de 8 dígitos; RUC de 11 dígitos | [customers/models.py:19](app/modules/customers/models.py#L19), [stores/models.py:15](app/modules/stores/models.py#L15) |

---

## 12. Cálculos no financieros

Para que el inventario esté completo, estos son los demás cálculos del código. No intervienen en el
dinero del cliente.

| Cálculo | Fórmula | Dónde |
|---|---|---|
| Vencimiento del token de sesión | `exp = ahora (UTC) + JWT_EXPIRE_MINUTES` (480 min por defecto) | [core/security.py:27](app/core/security.py#L27) |
| Latencia del health check | `latency_ms = round((t_fin − t_inicio) × 1000, 1)` | [main.py:82](app/main.py#L82) |
| Filtro "hasta" en compras | `< inicio del día (hasta + 1 día)` | [purchases/service.py:222-223](app/modules/purchases/service.py#L222-L223) |
| Filtro "hasta" en la bitácora | `< inicio del día (hasta + 1 día)` en hora de Lima | [audit/service.py:55](app/modules/audit/service.py#L55) |
| Paginación de clientes | `clientes[offset : offset + limit]` | [customers/service.py:152](app/modules/customers/service.py#L152) |
| Hora local | Sin zona → se asume Lima; con zona → se convierte a Lima | [core/clock.py](app/core/clock.py) |

---

## 13. Mapa: qué fórmula se usa en cada operación

| Operación (endpoint) | Fórmulas que intervienen |
|---|---|
| Convertir tasa (`POST /finance/equivalencias`) | 2.1, 2.2, 2.3, 1.2 |
| Crear/editar condiciones del cliente | 2.1, 2.2, 2.4, 11 |
| Ver cliente (resumen de crédito) | 2.3, 3.4, 10.2, 10.3, 10.4, 10.5 |
| Simular o registrar compra a fin de mes | 10.1, 10.2, 10.3, 2.4, 3.4, 4, 6, 1.1 |
| Simular o registrar compra en cuotas | 10.1, 10.2, 10.3, 10.6, 2.4, 3.4, 5, 6, 1.1 |
| Generar listado en la fecha de corte | 3.3, 8.1, 8.2, 2.5 (copia de la tasa moratoria) |
| Ver listado | 8.2, 7.1–7.4, 8.3, 8.4 |
| Cotizar pago | 7.1–7.4, 8.3, 9.2 |
| Registrar pago | 7.1–7.4, 8.3, 9.1, 9.2, 9.3, 9.4 |

---

## 14. Observaciones para la exposición

1. **Días reales vs. mes de 30 días.** Las tasas se convierten con mes de 30 días y año de 360 días. Los
   **días de un plazo** (gracia, interés a fin de mes, mora) se cuentan con el calendario real
   (`fecha final − fecha inicial`), como pide la guía del curso.
2. **TCEA con meses de 30 días.** Cada cuota se ubica a "gracia + 30 × k" días (Anexo A). Sin gracia, la
   TCEA es igual a la TEA; con gracia, un poco mayor.
3. **Última cuota.** Puede diferir unos céntimos de las demás por el ajuste de redondeo (sección 5.3).
4. **Crédito utilizado en cuotas.** Se mide con la amortización pendiente, que incluye el interés de la
   gracia capitalizado. Una compra de 1000 en cuotas puede ocupar 1010.90 de crédito.
5. **Dos intereses durante la mora.** El moratorio (penalidad, con la tasa moratoria del listado, sobre el
   pago total) y el compensatorio por atraso (con la tasa de cada compra, línea por línea). Se muestran
   como dos ítems separados y se cobran en ese orden.
6. **Pruebas.** Los ejemplos de este documento están verificados en `tests/` (`pytest -q`).
