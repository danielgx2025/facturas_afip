"""Utilidades de seguridad: hashing y verificación de contraseñas.

Usa la librería ``bcrypt`` directamente (en lugar de passlib, que quedó sin
mantenimiento y es incompatible con bcrypt moderno). bcrypt opera sobre los
primeros 72 bytes de la contraseña; se recorta explícitamente para evitar el
error de versiones recientes que rechazan secretos más largos.
"""

from __future__ import annotations

import bcrypt

_MAX_BCRYPT_BYTES = 72


def _to_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_MAX_BCRYPT_BYTES]


def hash_password(plain_password: str) -> str:
    """Devuelve el hash bcrypt de una contraseña en texto plano."""
    return bcrypt.hashpw(_to_bytes(plain_password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña contra su hash almacenado."""
    try:
        return bcrypt.checkpw(
            _to_bytes(plain_password), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False
