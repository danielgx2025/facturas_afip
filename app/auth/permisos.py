"""Catálogo de permisos del sistema (secciones controlables por rol).

Fuente única de verdad usada por:
- el formulario de roles (genera los checkboxes),
- la validación al crear/editar un rol,
- la siembra de roles base en ``scripts/init_db.py``,
- la dependencia ``require_permission`` (clave de cada gate de router).

Cada clave es un permiso; el valor es la etiqueta que se muestra al usuario.
"""

from __future__ import annotations

PERMISOS: dict[str, str] = {
    "dashboard": "Dashboard y estadísticas",
    "facturas": "Comprobantes (emitir y consultar)",
    "clientes": "Clientes",
    "productos": "Productos",
    "empresas": "Empresas y certificados",
    "usuarios": "Usuarios y roles",
}

# Permiso que habilita la administración de usuarios y roles. Quien lo tiene es,
# en la práctica, un "administrador" (ancla de la protección anti-bloqueo).
PERMISO_ADMIN = "usuarios"


def es_permiso_valido(permiso: str) -> bool:
    """Indica si ``permiso`` pertenece al catálogo conocido."""
    return permiso in PERMISOS


def filtrar_permisos(permisos: list[str]) -> list[str]:
    """Devuelve solo los permisos válidos (en el orden del catálogo)."""
    seleccionados = set(permisos)
    return [clave for clave in PERMISOS if clave in seleccionados]
