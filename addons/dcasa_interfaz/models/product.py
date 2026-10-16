"""«Lo que no se mueve»: productos con existencias que no se han vendido en un tiempo (pedido del jefe, 2026-10-16)."""
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

DIAS_SIN_MOVIMIENTO = 90


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def dcasa_accion_sin_movimiento(self, dias=DIAS_SIN_MOVIMIENTO):
        """La lista de productos vendibles con existencias y **sin ninguna venta confirmada** en los últimos ``dias``
        días: lo que no gusta o está mal puesto. Solo para Gerencia y administradores, como todas las estadísticas."""
        usuario = self.env.user
        if not (usuario.has_group('sales_team.group_sale_manager') or usuario.has_group('base.group_system')):
            raise AccessError(self.env._('Las estadísticas del negocio son de Gerencia.'))
        try:
            dias = min(max(int(dias), 1), 3650)
        except (TypeError, ValueError, OverflowError):
            raise UserError(self.env._('Escribe los días como un número entero, por ejemplo 90.')) from None
        desde = fields.Datetime.now() - timedelta(days=dias)
        vendidos = self.env['sale.order.line']._read_group(
            [('order_id.state', '=', 'sale'), ('order_id.date_order', '>=', desde), ('product_id', '!=', False)],
            ['product_id'])
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Lo que no se mueve (sin ventas en %(dias)s días)', dias=dias),
            'res_model': 'product.product',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('is_storable', '=', True), ('sale_ok', '=', True), ('qty_available', '>', 0),
                       ('id', 'not in', [producto.id for (producto,) in vendidos])],
            'context': {'search_default_filter_to_sell': 0},
        }
