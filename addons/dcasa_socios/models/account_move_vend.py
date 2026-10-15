import logging

from odoo import fields, models
from odoo.exceptions import UserError

from . import reglas as R

_logger = logging.getLogger(__name__)
GRUPO_GERENTE = 'sales_team.group_sale_manager'


class AccountMove(models.Model):
    _inherit = 'account.move'

    dcasa_vendedor_id = fields.Many2one(
        'res.partner', string='Vendedor (código VEN…)', copy=False, index='btree_not_null', ondelete='restrict',
        domain="[('dcasa_vendedor_estado', '=', 'activo')]",
        help='El vendedor del programa de esta venta: viene de la cotización o se anota aquí si la factura se hizo '
             'directa. Cuando la factura se paga, el vendedor gana sus puntos.')
    dcasa_vendedor_anotado_por = fields.Many2one('res.users', string='Código anotado por', readonly=True, copy=False)
    dcasa_vend_comision_ids = fields.One2many('dcasa.vend.comision', 'move_id', string='Comisiones de vendedor')

    def write(self, vals):
        if 'dcasa_vendedor_id' in vals:
            nuevo = vals['dcasa_vendedor_id'] or False
            for move in self.filtered(lambda m: m.dcasa_vendedor_id.id != nuevo):
                if move.sudo().dcasa_vend_comision_ids.filtered(lambda c: not c.anulada_en):
                    raise UserError(self.env._(
                        'La factura %s ya dio comisión de vendedor: primero se anula esa comisión.', move.name))
                if move.state == 'posted' and not self.env.su and not self.env.user.has_group(GRUPO_GERENTE):
                    raise UserError(self.env._('La factura %s ya está publicada: el vendedor solo lo cambia Gerencia.',
                                               move.name))
            vals.setdefault('dcasa_vendedor_anotado_por', self.env.user.id)
        return super().write(vals)

    def _invoice_paid_hook(self):
        res = super()._invoice_paid_hook()
        Comision = self.env['dcasa.vend.comision'].sudo()
        for move in self.filtered(lambda m: m.move_type == 'out_invoice' and not m.dcasa_historica
                                  and m.payment_state in ('paid', 'in_payment')):
            try:
                # El programa nunca hace fallar un cobro: si algo se tuerce, el error queda en el registro.
                with self.env.cr.savepoint():
                    Comision._registrar_desde_factura(move)
            except Exception:
                _logger.exception('No se pudo registrar la comisión de vendedor de la factura %s', move.name)
        return res

    def _dcasa_anular_comisiones_de_vendedor(self, motivo):
        comisiones = self.sudo().dcasa_vend_comision_ids.filtered(lambda c: not c.anulada_en)
        if comisiones:
            # por_factura: la factura misma se deshace, así que si vuelve a quedar pagada la comisión puede volver.
            comisiones._anular(motivo, self.env.user.login, por_factura=True)

    def button_draft(self):
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            move._dcasa_anular_comisiones_de_vendedor(self.env._('La factura %s volvió a borrador.', move.name))
        return super().button_draft()

    def button_cancel(self):
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            move._dcasa_anular_comisiones_de_vendedor(self.env._('Se canceló la factura %s.', move.name))
        return super().button_cancel()

    def unlink(self):
        """Borrar un borrador no se queda trabado por una comisión de vendedor (mismo trato que los puntos del
        socio, ver ``account_move.py``): la que siga activa se anula con su asiento contrario, DESPUÉS de borrar, y
        queda en la historia sin factura."""
        self.check_access('unlink')  # antes de anular puntos con sudo (método público por RPC)
        comisiones = self.sudo().dcasa_vend_comision_ids.filtered(lambda c: not c.anulada_en)
        motivos = {c.id: self.env._('Se eliminó la factura %s.', c.name) for c in comisiones}
        res = super().unlink()
        for comision in comisiones:
            comision._anular(motivos[comision.id], self.env.user.login, por_factura=True)
        return res

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        # Nota de crédito sobre una venta que dio comisión: total anula, parcial descuenta lo proporcional.
        for nota in posted.filtered(lambda m: m.move_type == 'out_refund' and m.reversed_entry_id):
            original = nota.reversed_entry_id
            comisiones = original.sudo().dcasa_vend_comision_ids.filtered(lambda c: not c.anulada_en)
            if not comisiones:
                continue
            neto = R.a_centavos(original.amount_untaxed_signed)
            devuelto = R.a_centavos(abs(nota.amount_untaxed_signed))
            if devuelto >= neto:
                comisiones._anular(self.env._('Nota de crédito %s', nota.name), self.env.user.login)
            else:
                comisiones._devolucion_parcial(nota, neto, self.env.user.login)
        posted._dcasa_reabrir_comisiones()
        return posted

    def _dcasa_reabrir_comisiones(self):
        """Una factura que volvió a borrador y se publica otra vez con su pago todavía puesto vuelve a estar pagada
        sin que Odoo avise: se reabre la comisión que se había anulado por esa corrección. Nunca hace fallar la
        publicación."""
        pagadas = self.filtered(lambda m: m.move_type == 'out_invoice' and not m.dcasa_historica
                                and m.payment_state in ('paid', 'in_payment'))
        if not pagadas:
            return
        Comision = self.env['dcasa.vend.comision'].sudo()
        for move in Comision.search([('move_id', 'in', pagadas.ids), ('anulada_por_factura', '=', True)]).move_id:
            try:
                with self.env.cr.savepoint():
                    Comision._registrar_desde_factura(move)
            except Exception:  # noqa: BLE001  — el programa de vendedores nunca hace fallar una factura
                _logger.exception('No se pudo volver a dar la comisión de vendedor de la factura %s', move.name)
