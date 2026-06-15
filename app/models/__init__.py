"""Modelos ORM del sistema.

Se importan todos aquí para que ``Base.metadata`` los conozca al crear las tablas
(``Base.metadata.create_all``) y para facilitar los imports en el resto del código.
"""

from app.models.cliente import Cliente
from app.models.comprobante import Comprobante
from app.models.comprobante_item import ComprobanteItem
from app.models.empresa import Empresa
from app.models.producto import Producto
from app.models.punto_venta import PuntoVenta
from app.models.rol import Rol
from app.models.usuario import Usuario

__all__ = [
    "Cliente",
    "Comprobante",
    "ComprobanteItem",
    "Empresa",
    "Producto",
    "PuntoVenta",
    "Rol",
    "Usuario",
]
