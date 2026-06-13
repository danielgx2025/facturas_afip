"""Excepciones propias de la capa de integración con AFIP.

Permiten distinguir el tipo de problema y traducirlo a mensajes claros para el
usuario, manteniendo el detalle técnico en el log.
"""

from __future__ import annotations


class AfipError(Exception):
    """Error base de la integración con AFIP."""


class AfipAuthError(AfipError):
    """Falla de autenticación WSAA.

    Causas típicas: certificado vencido o inválido, clave privada incorrecta,
    relación no delegada en el "Administrador de Relaciones" de AFIP.
    """


class AfipConnectionError(AfipError):
    """Problemas de conexión con AFIP (timeout, WSDL caído, red)."""


class AfipValidationError(AfipError):
    """AFIP rechazó el comprobante o devolvió errores de validación.

    Attributes:
        errores: lista de errores devueltos por AFIP.
        observaciones: lista de observaciones (el comprobante puede ser válido
            pero con advertencias).
    """

    def __init__(
        self,
        mensaje: str,
        errores: list[str] | None = None,
        observaciones: list[str] | None = None,
    ) -> None:
        super().__init__(mensaje)
        self.errores = errores or []
        self.observaciones = observaciones or []
