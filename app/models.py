"""Registro de todos los modelos (lo usan Alembic y las pruebas)."""
from app.core.database import Base  # noqa: F401
from app.modules.audit.models import Bitacora  # noqa: F401
from app.modules.customers.models import Cliente, CondicionCredito  # noqa: F401
from app.modules.finance.models import TopeTasa  # noqa: F401
from app.modules.iam.models import Usuario  # noqa: F401
from app.modules.payments.models import Pago  # noqa: F401
from app.modules.products.models import Producto  # noqa: F401
from app.modules.purchases.models import Compra, CompraDetalle, Cuota  # noqa: F401
from app.modules.statements.models import EstadoCuenta  # noqa: F401
from app.modules.stores.models import Tienda  # noqa: F401
