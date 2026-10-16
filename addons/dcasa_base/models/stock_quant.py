"""Solo Gerencia ajusta las existencias a mano (hallazgo del 2026-10-16).

Odoo deja que cualquiera con permiso de Inventario (la Vendedora lo tiene) edite la cantidad contada en
Inventario › Inventario físico y la aplique: el ajuste queda como un movimiento, pero sin motivo y sin que nadie lo
haya autorizado. El Escáner › Contar y las herramientas de Brian ya exigen Gerencia; aquí se cierra la tercera
puerta, en el modelo, para que valga igual en la pantalla, por RPC y para Brian (que actúa como el usuario real).

Lo que NO cambia: validar entregas y recepciones, que mueven existencias por sus propios movimientos.
"""
from odoo import api, models
from odoo.exceptions import UserError

CAMPOS_DE_AJUSTE = frozenset({
    'inventory_quantity', 'inventory_quantity_auto_apply', 'inventory_diff_quantity', 'inventory_quantity_set',
})


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _dcasa_exigir_gerencia_para_ajustar(self):
        if self.env.su or self.env.user.has_group('stock.group_stock_manager'):
            return
        raise UserError(self.env._(
            'Solo Gerencia ajusta las existencias a mano. Pídele a Gerencia que haga el ajuste (con el Escáner › '
            'Contar) y deja escrito el motivo.'))

    @api.model_create_multi
    def create(self, vals_list):
        if self._is_inventory_mode() and any(CAMPOS_DE_AJUSTE & set(vals) for vals in vals_list):
            self._dcasa_exigir_gerencia_para_ajustar()
        return super().create(vals_list)

    def write(self, vals):
        if self._is_inventory_mode() and CAMPOS_DE_AJUSTE & set(vals):
            self._dcasa_exigir_gerencia_para_ajustar()
        return super().write(vals)

    def _apply_inventory(self, date=None):
        if self:
            self._dcasa_exigir_gerencia_para_ajustar()
        return super()._apply_inventory(date)
