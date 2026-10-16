"""Solo Gerencia ajusta las existencias a mano (hallazgo del 2026-10-16).

Odoo deja que cualquiera con permiso de Inventario (la Vendedora lo tiene) edite la cantidad contada en
Inventario › Inventario físico y la aplique: el ajuste queda como un movimiento, pero sin motivo y sin que nadie lo
haya autorizado. El Escáner › Contar y las herramientas de Brian ya exigen Gerencia; aquí se cierra la tercera
puerta, en el modelo, para que valga igual en la pantalla, por RPC y para Brian (que actúa como el usuario real).

Revisión adversarial del mismo día: el candado no puede depender de ``inventory_mode`` (lo pone el cliente en el
contexto). Un ``write({'quantity': 999})`` o un ``create`` con ``quantity`` por RPC, sin ese contexto, caía en la rama
sin restricciones. Ahora la cantidad y lo reservado no los escribe a mano nadie que no sea Gerencia o el sistema.

Lo que NO cambia: validar entregas y recepciones, que mueven existencias por sus propios movimientos (Odoo los corre
con ``sudo()``: ``_update_available_quantity``, ``_update_reserved_quantity``, ``_unlink_zero_quants``…).
"""
from odoo import api, models
from odoo.exceptions import UserError

CAMPOS_DE_AJUSTE = frozenset({
    'inventory_quantity', 'inventory_quantity_auto_apply', 'inventory_diff_quantity', 'inventory_quantity_set',
})
# La cantidad en mano y la reservada: solo las mueve el sistema (con sudo) o Gerencia, en modo inventario o sin él.
CAMPOS_DE_CANTIDAD = frozenset({'quantity', 'reserved_quantity'})


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _dcasa_exigir_gerencia_para_ajustar(self):
        if self.env.su or self.env.user.has_group('stock.group_stock_manager'):
            return
        raise UserError(self.env._(
            'Solo Gerencia ajusta las existencias a mano. Pídele a Gerencia que haga el ajuste (con el Escáner › '
            'Contar) y deja escrito el motivo.'))

    def _dcasa_toca_existencias(self, campos):
        return bool(CAMPOS_DE_CANTIDAD & campos or (self._is_inventory_mode() and CAMPOS_DE_AJUSTE & campos))

    @api.model_create_multi
    def create(self, vals_list):
        if any(self._dcasa_toca_existencias(set(vals)) for vals in vals_list):
            self._dcasa_exigir_gerencia_para_ajustar()
        return super().create(vals_list)

    def write(self, vals):
        if self._dcasa_toca_existencias(set(vals)):
            self._dcasa_exigir_gerencia_para_ajustar()
        return super().write(vals)

    def _apply_inventory(self, date=None):
        if self:
            self._dcasa_exigir_gerencia_para_ajustar()
        return super()._apply_inventory(date)
