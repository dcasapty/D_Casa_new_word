"""Factura histórica y la dueña de la factura (solo lo suyo, 2026-10-16).

Quien solo ve lo suyo (la Vendedora, ``res.users._dcasa_solo_lo_suyo``) queda siempre como vendedora
(``invoice_user_id``) de la factura, nota o recibo de cliente que crea a mano. Si no, Odoo pondría a la vendedora de
la ficha del cliente y la creación fallaría por permisos. Las facturas que salen de un pedido se crean con ``sudo`` y
llevan la vendedora del pedido; la nota de crédito copia la vendedora de la factura. Caja y contabilidad no cambian.
"""
from odoo import api, fields, models

CLIENTE = ('out_invoice', 'out_refund', 'out_receipt')


class AccountMove(models.Model):
    _inherit = 'account.move'

    dcasa_historica = fields.Boolean(
        'Cargada del sistema anterior', readonly=True, copy=False,
        help='Factura o nota que viene de la carga única de la contabilidad anterior (dcasa_migracion). Es historia: '
             'no se manda a la DGI, no da puntos de Socios y no cambia las páginas de la tienda.')

    def _compute_invoice_default_sale_person(self):
        # El cálculo corre con sudo (campo guardado): se pregunta por la persona, no por el modo sudo.
        tomar = self.browse()
        if self.env.user._dcasa_solo_lo_suyo():
            tomar = self.filtered(lambda m: m.is_sale_document(include_receipts=True) and m.partner_id
                                  and not (m._origin.id and m.invoice_user_id))
        super()._compute_invoice_default_sale_person()
        for move in tomar:
            move.invoice_user_id = self.env.user

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and self.env.user._dcasa_solo_lo_suyo():
            por_defecto = self.env.context.get('default_move_type')
            vals_list = [dict(vals, invoice_user_id=self.env.uid)
                         if vals.get('move_type', por_defecto) in CLIENTE else vals for vals in vals_list]
        return super().create(vals_list)
