# FiadoClaro — Backend (FastAPI + PostgreSQL)

API del sistema de control de cuenta corriente por créditos (fiado) para pequeños negocios.
Curso SI642 Finanzas e Ingeniería Económica, trabajo final 2026-20.

## Puesta en marcha

### Opción A: Docker (lo más rápido)

```bash
cp .env.example .env
docker compose up --build
docker compose exec api python -m scripts.seed --demo   # opcional: Bodega Don Lucho de ejemplo
```

API en http://localhost:8000 y documentación interactiva en http://localhost:8000/docs

### Opción B: local

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # ajusta DATABASE_URL a tu PostgreSQL
createdb fiadoclaro                  # o desde pgAdmin
alembic upgrade head                 # crea las tablas
python -m scripts.seed --demo        # admin + topes + datos de ejemplo
uvicorn app.main:app --reload
```

### Comandos del día a día

| Qué | Comando |
|---|---|
| Levantar la API | `uvicorn app.main:app --reload` |
| Crear tablas / aplicar cambios | `alembic upgrade head` |
| Nueva migración tras cambiar un modelo | `alembic revision --autogenerate -m "describe el cambio"` |
| Cargar datos base | `python -m scripts.seed` (agrega `--demo` para datos de ejemplo) |
| Pruebas | `pytest -q` (todas) o `pytest -q -m "not integracion"` (solo cálculos, sin base de datos) |

Usuarios de la semilla: `admin / Admin123*` (sistema), `dlucho / Lucho2026*` (tienda), `08765432@bodegadonlucho.com / Rosa2024*Lucho` (cliente).

## Estructura por módulos

```
app/
├── core/            config, conexión BD, seguridad (Argon2 + JWT), roles, reloj, errores
├── modules/
│   ├── iam/         login, usuario actual, cambio de contraseña
│   ├── stores/      alta/baja de tiendas y su administrador        (admin del sistema)
│   ├── customers/   clientes y condiciones de crédito              (admin de tienda)
│   ├── products/    catálogo de productos y servicios              (admin de tienda)
│   ├── finance/     MOTOR FINANCIERO (engine.py) + topes de tasa
│   ├── purchases/   compras a fin de mes y en cuotas
│   ├── statements/  listado de pago en la fecha de corte
│   ├── payments/    pagos con mora y prelación
│   ├── portal/      consultas del vecino                           (cliente)
│   └── audit/       bitácora de operaciones
├── models.py        registro de modelos para Alembic
└── main.py
```

Cada módulo tiene `models.py` (tablas), `schemas.py` (entrada/salida), `service.py` (reglas) y `router.py` (endpoints).
`finance/engine.py` es Python puro: todas las fórmulas viven ahí y se prueban sin base de datos.

## Comandos de la API frente al enunciado

| Enunciado | Endpoint | Rol |
|---|---|---|
| Login con usuario y clave | `POST /api/v1/iam/login` | todos |
| 1) Alta/baja de tienda con credenciales | `POST /stores`, `POST /stores/{id}/baja`, `/alta` | admin sistema |
| 2) Alta/baja de productos con precio contado, lista a crédito, fin de mes o meses | `POST /products`, `PUT /products/{id}`, `/baja`, `/alta` | admin tienda |
| 3) Alta/baja de clientes con tasa nominal o efectiva, moneda, límite, máximo de meses, corte y pago | `POST /customers`, `PUT /customers/{id}/condicion`, `/baja`, `/alta` | admin tienda |
| Validación del tope de tasa | automática al crear cliente, cambiar condición y comprar | — |
| 4) Compra en meses: francés vencido ordinario con gracia capitalizada | `POST /purchases/simular`, `POST /purchases` (`CUOTAS`) | admin tienda |
| 5) Compra a fin de mes, ciclo por fecha y hora de corte, límite de crédito | `POST /purchases` (`FIN_MES`) | admin tienda |
| 6) Listado de pago en la fecha de corte, compras por fecha, mora en ítem aparte | `POST /statements/generar`, `GET /statements/{id}` | admin tienda |
| 5) Sin pagos parciales; mora por días de atraso; prelación | `GET /payments/cotizar/{id}`, `POST /payments` | admin tienda |
| Consultas del lado del cliente | `GET /portal/me`, `/portal/compras`, `/portal/listados` | cliente |
| Registrar todas las operaciones | `GET /audit` | admins |
| Conversión de tasas (ayuda en interfaz) | `POST /finance/equivalencias` | todos |

## Reglas de cálculo (Anexo A)

- Año de 360 días y mes de 30. Días = fecha final − fecha inicial.
- Tasas en porcentaje con 7 decimales en BD; cálculos internos con 34 dígitos; montos a 2 decimales (half up).
- Nominal → efectiva: `TEP = (1 + TN/m)^n − 1`, con `m = periodo/capitalización` y `n = días/capitalización`.
  Si no se indica capitalización, es diaria (regla del curso).
- Fin de mes: `I = monto × ((1 + TEM)^(días/30) − 1)` entre la compra y la fecha de pago.
- Cuotas: se capitaliza la gracia `P' = P × (1 + TEP_gracia)`; cuota `R = P' × i / (1 − (1+i)^−n)`;
  la primera vence un mes después de la fecha de pago del ciclo; la última ajusta el redondeo.
- Ciclo: compra antes de la fecha y hora de corte → ese corte; después → corte del mes siguiente.
- Mora: tasa moratoria (copiada en la compra) sobre el total que debió pagarse, por los días de atraso.
- Prelación: mora → interés compensatorio → capital.
- Cada compra guarda una copia de la tasa pactada; cambiar la condición del cliente no altera compras anteriores.

## Supuestos a confirmar con el profesor

1. Durante la mora se cobra solo el interés moratorio (no se sigue sumando compensatorio).
2. Una compra hecha exactamente a la hora de corte pasa al ciclo siguiente ("antes de la hora" es estricto).
3. Los topes de `tope_tasa` de la semilla son de ejemplo: actualízalos con la circular vigente del BCRP
   (`POST /finance/topes`).
4. El crédito utilizado es el capital pendiente de las cuotas (en compras en cuotas incluye la gracia capitalizada).
