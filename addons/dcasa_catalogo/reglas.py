"""Reglas del catálogo de D'CASA sin dependencias de Odoo.

Las comparten la carga del catálogo (``catalogo.py``), el script que lee el Excel de la
empresa (``scripts/importar_catalogo.py``) y la importación de Excel de proveedores de Brian
(``dcasa_brian``): la misma categoría y el mismo tamaño salen del mismo nombre.
"""
import re

TAMANOS = ['Twin', 'Full', 'Queen', 'King']

# Categoría de la tienda según el nombre del producto (primera regla que coincide).
CATEGORIAS = [
    (r'colch', 'colchones'),
    (r'mueble de tv', 'muebles_tv'),
    (r'sof[aá]', 'salas'),
    (r'zapatera', 'zapateras'),
    (r'escritorio|mesa ajustable', 'oficina'),
    (r'estante|librero|organizador|mueble de cocina|mueble type', 'organizacion'),
    (r'cama|camarote|mesa de noche|peinadora|tocador|gavetero', 'recamaras'),
]


def categoria_de_nombre(nombre, defecto=None):
    """«Cama tapizada King» → 'recamaras'. Sin coincidencia → ``defecto``."""
    for patron, clave in CATEGORIAS:
        if re.search(patron, nombre or '', re.I):
            return clave
    return defecto


def tamano_del_nombre(nombre):
    """«Cama king» es de un solo tamaño, King: así aparece al filtrar la tienda por tamaño."""
    m = re.search(r'\b(twin|full|queen|king)\b', nombre or '', re.I)
    return m.group(1).capitalize() if m else None
