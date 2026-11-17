"""
Errores de negocio y traducción de errores de validación a mensajes en español.

Todas las respuestas de error del API tienen la misma forma:

    {
      "detail":  "Mensaje para mostrar al usuario",
      "code":    "codigo_estable_para_el_frontend",
      "errores": [{"campo": "condicion.tasa", "mensaje": "..."}],   (solo en validaciones)
      "datos":   {...}                                              (opcional, información extra)
    }
"""
from typing import Any


class BusinessError(Exception):
    """Regla de negocio incumplida (422)."""

    status_code = 422

    def __init__(self, message: str, code: str = "regla_negocio", datos: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.datos = datos


class NotFoundError(BusinessError):
    status_code = 404

    def __init__(self, entidad: str, id_: object = None):
        msg = f"{entidad} no encontrado" + (f" (id={id_})" if id_ is not None else "")
        super().__init__(msg, code="no_encontrado")


class ConflictError(BusinessError):
    status_code = 409

    def __init__(self, message: str):
        super().__init__(message, code="conflicto")


class ForbiddenError(BusinessError):
    status_code = 403

    def __init__(self, message: str = "No tienes permiso para esta operación"):
        super().__init__(message, code="prohibido")


# ------------------------------------------------------- errores de validación
# Nombres legibles de los campos, para armar mensajes como "El DNI es obligatorio".
NOMBRES_CAMPO = {
    "username": "El usuario", "password": "La contraseña", "password_actual": "La contraseña actual",
    "password_nueva": "La nueva contraseña", "nombre": "El nombre", "nombres": "Los nombres",
    "apellidos": "Los apellidos", "dni": "El DNI", "ruc": "El RUC", "telefono": "El teléfono",
    "correo": "El correo", "direccion": "La dirección", "razon_social": "La razón social",
    "nombre_comercial": "El nombre comercial", "giro": "El giro", "codigo": "El código",
    "unidad_medida": "La unidad de medida", "precio_contado": "El precio al contado",
    "precio_lista_credito": "El precio de lista a crédito", "max_meses": "El máximo de meses",
    "valor": "La tasa", "periodo_dias": "El periodo de la tasa", "capitalizacion_dias": "La capitalización",
    "limite_credito": "El límite de crédito", "dia_corte": "El día de corte", "dia_pago": "El día de pago",
    "hora_corte": "La hora de corte", "cantidad": "La cantidad", "items": "Los productos",
    "num_cuotas": "El número de cuotas", "monto": "El monto", "fecha_pago": "La fecha de pago",
    "fecha_corte": "La fecha de corte", "tea_maxima": "La TEA máxima", "vigente_desde": "La fecha de vigencia",
}

# Mensajes específicos cuando un campo no cumple su formato (patrón)
FORMATO_CAMPO = {
    "dni": "El DNI debe tener exactamente 8 dígitos",
    "ruc": "El RUC debe tener exactamente 11 dígitos",
    "username": "El usuario solo puede tener letras, números, punto, guion, guion bajo y @",
}


def _campo(loc: tuple) -> tuple[str, str]:
    """('body', 'condicion', 'tasa', 'valor') -> ('condicion.tasa.valor', 'valor')."""
    partes = [str(p) for p in loc if p not in ("body", "query", "path", "header", "form")]
    return ".".join(partes) or "solicitud", (partes[-1] if partes else "")


def _concordancia(nombre: str) -> tuple[str, str, str, str]:
    """
    Formas que concuerdan con el sujeto ("La contraseña" -> obligatoria, debe, tiene, válida).
    Devuelve (sufijo del adjetivo: o/a/os/as, verbo deber, verbo tener, verbo ser).
    """
    plural = nombre.startswith(("Los ", "Las "))
    femenino = nombre.startswith(("La ", "Las "))
    sufijo = ("a" if femenino else "o") + ("s" if plural else "")
    return sufijo, ("deben" if plural else "debe"), ("tienen" if plural else "tiene"), ("son" if plural else "es")


def mensaje_validacion(error: dict) -> dict[str, str]:
    """Convierte un error de Pydantic en {"campo", "mensaje"} en español."""
    ruta, campo = _campo(tuple(error.get("loc", ())))
    nombre = NOMBRES_CAMPO.get(campo, f"El campo '{campo}'" if campo else "La solicitud")
    tipo, ctx = error.get("type", ""), error.get("ctx") or {}
    o, debe, tiene, es = _concordancia(nombre)
    valido = "válid" + o

    if tipo == "missing":
        msg = f"{nombre} {es} obligatori{o}"
    elif tipo == "string_too_short":
        msg = f"{nombre} {debe} tener al menos {ctx.get('min_length')} caracteres"
    elif tipo == "string_too_long":
        msg = f"{nombre} no puede{'n' if debe == 'deben' else ''} tener más de {ctx.get('max_length')} caracteres"
    elif tipo == "string_pattern_mismatch":
        msg = FORMATO_CAMPO.get(campo, f"{nombre} no {tiene} el formato correcto")
    elif tipo == "greater_than":
        msg = f"{nombre} {debe} ser mayor que {ctx.get('gt')}"
    elif tipo == "greater_than_equal":
        msg = f"{nombre} {debe} ser mayor o igual que {ctx.get('ge')}"
    elif tipo == "less_than":
        msg = f"{nombre} {debe} ser menor que {ctx.get('lt')}"
    elif tipo == "less_than_equal":
        msg = f"{nombre} {debe} ser menor o igual que {ctx.get('le')}"
    elif tipo in ("int_parsing", "int_type", "int_from_float"):
        msg = f"{nombre} {debe} ser un número entero"
    elif tipo in ("decimal_parsing", "decimal_type", "float_parsing", "float_type"):
        msg = f"{nombre} {debe} ser un número"
    elif tipo == "decimal_max_places":
        msg = f"{nombre} admite{'n' if debe == 'deben' else ''} como máximo {ctx.get('decimal_places')} decimales"
    elif tipo == "decimal_max_digits":
        msg = f"{nombre} {tiene} demasiados dígitos"
    elif tipo in ("date_parsing", "date_from_datetime_parsing", "date_type"):
        msg = f"{nombre} {debe} ser una fecha válida (AAAA-MM-DD)"
    elif tipo in ("datetime_parsing", "datetime_type"):
        msg = f"{nombre} {debe} ser una fecha y hora válida"
    elif tipo in ("time_parsing", "time_type"):
        msg = f"{nombre} {debe} ser una hora válida (HH:MM)"
    elif tipo in ("literal_error", "enum"):
        msg = f"{nombre} {debe} ser uno de: {ctx.get('expected', '')}"
    elif tipo in ("too_short", "list_too_short"):
        msg = f"{nombre} {debe} tener al menos {ctx.get('min_length')} elemento(s)"
    elif tipo in ("string_type", "bool_type", "bool_parsing", "model_type", "dict_type", "list_type"):
        msg = f"{nombre} {tiene} un tipo de dato incorrecto"
    elif tipo == "json_invalid":
        msg = "El cuerpo de la solicitud no es un JSON válido"
    elif tipo == "value_error" and campo == "correo":
        msg = "El correo no es válido"
    elif tipo in ("value_error", "assertion_error"):
        # Mensajes de nuestros validadores (ya están en español): quitar el prefijo de Pydantic.
        msg = str(error.get("msg", "")).removeprefix("Value error, ").removeprefix("Assertion failed, ")
    else:
        msg = f"{nombre} no {es} {valido}"
    return {"campo": ruta, "mensaje": msg}
