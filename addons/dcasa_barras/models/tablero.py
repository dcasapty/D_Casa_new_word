"""El acceso «Bodega» del Inicio: para quien despacha (el mismo permiso que su menú de Inventario)."""
from odoo import models


class DcasaTablero(models.AbstractModel):
    _inherit = 'dcasa.tablero'

    def _atajos(self, permisos):
        """Bodega va justo antes del Escáner, con cuántas entregas esperan (las mismas del panel)."""
        atajos = super()._atajos(permisos)
        if not self.env.user.has_group('stock.group_stock_user') \
                or not self.env.ref('dcasa_barras.accion_bodega', raise_if_not_found=False):
            return atajos
        cuantas = len(self.env['dcasa.bodega']._despachables())   # las mismas del panel: con pago o abono
        if not cuantas:
            detalle = 'Nada por despachar'
        else:
            detalle = '1 entrega por despachar' if cuantas == 1 else f'{cuantas} entregas por despachar'
        bodega = {
            'clave': 'bodega', 'titulo': 'Bodega', 'detalle': detalle, 'icono': 'fa-truck',
            'accion': 'dcasa_barras.accion_bodega', 'vista': None, 'cuenta': cuantas,
        }
        posicion = next((i for i, atajo in enumerate(atajos) if atajo['clave'] == 'escaner'), len(atajos))
        atajos.insert(posicion, bodega)
        return atajos
