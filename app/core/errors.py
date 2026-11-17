"""Errores de negocio. Se traducen a respuestas HTTP en main.py."""


class BusinessError(Exception):
    """Regla de negocio incumplida (422)."""

    status_code = 422

    def __init__(self, message: str, code: str = "regla_negocio"):
        super().__init__(message)
        self.message = message
        self.code = code


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
