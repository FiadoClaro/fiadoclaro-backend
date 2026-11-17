# FiadoClaro — contexto para Claude Code

Trabajo final del curso SI642 Finanzas e Ingeniería Económica (UPC, 2026-20), grupo 2.
Sistema web de control de cuenta corriente por créditos ("fiado") para pequeños negocios de barrio
(bodegas, fruterías, peluquerías...). Varias tiendas usan la misma plataforma.

## Stack
- Backend: Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 16 (PostgreSQL es obligatorio).
- Frontend (pendiente): React + TypeScript + Vite + Tailwind, siguiendo los mockups de Figma
  https://www.figma.com/design/gdMXRYTYf5JkBJ7bkOSqoc/FiadoClaro
- Auth: JWT + Argon2. Roles: ADMIN_SISTEMA, ADMIN_TIENDA, CLIENTE.

## Cómo correr
- `docker compose up --build` y luego `docker compose exec api python -m scripts.seed --demo`
- Local: `pip install -r requirements.txt`, `alembic upgrade head`, `python -m scripts.seed --demo`,
  `uvicorn app.main:app --reload`. Docs en http://localhost:8000/docs
- Pruebas: crear la base `fiadoclaro_test` y ejecutar `pytest -q` (deben pasar las 23).
- Usuarios demo: admin / Admin123*, dlucho / Lucho2026*, rosa.flores / Rosa2024*Lucho

## Arquitectura
`app/modules/<módulo>/` con `models.py`, `schemas.py`, `service.py`, `router.py`.
Módulos: iam, stores, customers, products, finance, purchases, statements, payments, portal, audit.
- Todas las fórmulas viven en `app/modules/finance/engine.py` (Python puro, sin BD). No dupliques
  cálculos en otros módulos ni en el frontend: el frontend solo muestra lo que devuelve la API
  (usa `POST /purchases/simular` para previsualizar).
- Toda operación que cambia datos llama a `audit.service.registrar(...)` (el enunciado exige registrar todo).
- Siempre filtrar por `actor.tienda_id`: una tienda nunca ve datos de otra.
- Errores de negocio: lanzar `BusinessError` / `NotFoundError` / `ConflictError` de `app/core/errors.py`.
- Fechas: usar `app/core/clock.py` (`ahora()`, `hoy()`), zona America/Lima. En pruebas, `clock.fijar_ahora(...)`.
- Cambios de modelo: editar `models.py` y luego `alembic revision --autogenerate -m "..."`.

## Reglas financieras (Anexo A del enunciado) — no cambiar sin confirmar
- Año comercial 360 días, mes 30 días. Días = fecha final − fecha inicial.
- Montos `numeric(12,2)`, redondeo half up. Tasas en % `numeric(12,7)`; derivadas (TEM, TEA, TCEA) con 10 decimales.
  Nunca usar float: siempre `Decimal`.
- Nominal → efectiva: TEP = (1 + TN/m)^n − 1. Capitalización por defecto: diaria (regla del curso).
- Ciclo: compra antes de la fecha y hora de corte → ese corte; si no, el del mes siguiente.
- Fin de mes: interés compensatorio por los días entre la compra y la fecha de pago.
- Cuotas: método francés vencido ordinario; la gracia (compra → fecha de pago) se capitaliza;
  la primera cuota vence un mes después de la fecha de pago del ciclo.
- No se permiten compras que excedan el crédito disponible ni pagos parciales.
- Mora: tasa moratoria sobre el total que debió pagarse, por los días de atraso; se muestra como ítem aparte.
- Prelación del pago: mora → interés compensatorio → capital.
- La TEA de las tasas no puede superar el tope BCRP vigente (tabla `tope_tasa`).

## Observaciones del profesor ya resueltas en el backend
- La compra guarda una copia de la tasa pactada (un cambio en el cliente no altera compras anteriores).
- `producto.max_meses` (máximo de meses por producto).
- Montos y tasas con decimales precisos.
- Conversión nominal→efectiva, validación del tope, mora y prelación en cuotas, listado en la fecha de corte,
  y uso de la fecha de corte para decidir el ciclo.
- Interfaz: cada campo de formulario debe tener ayuda ("?" con tooltip) en TODAS las ventanas.

## Supuestos pendientes de confirmar con el profesor
1. Durante la mora solo se cobra interés moratorio (no se sigue sumando compensatorio).
2. Una compra exactamente a la hora de corte pasa al ciclo siguiente.
3. Los topes BCRP de la semilla son de ejemplo; actualizar con la circular vigente.

## Pendiente
- Frontend en React según los mockups de Figma.
- Despliegue (Render/Railway + Neon/Supabase).
- El código debe poder ser explicado por el grupo en la exposición: preferir código simple y comentado.
