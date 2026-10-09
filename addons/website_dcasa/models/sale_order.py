"""Apartados de la tienda en línea que nadie reclama (decisión de la dueña, 2026-10-09).

Con «Pago al recibir o en la tienda», Odoo confirma el pedido solo y reserva el inventario; con transferencia o Yappy
el pedido queda como cotización enviada, esperando el pago. Si el cliente nunca llega, el inventario quedaba
apartado para siempre y el equipo creía que esa venta iba a ocurrir.

* Al quedar «por cobrar» (cotización enviada o confirmada sola por la tienda) un pedido de la web recibe una fecha:
  ``dcasa_apartado_vence`` = hoy + los días de apartado (Ajustes › Sitio web; 7 por defecto, 0 = apagado).
* Una vendedora puede mover esa fecha (extender) desde el pedido. Si ELLA confirma el pedido, es una decisión
  suya y la fecha se borra: nada se anula solo.
* Cada noche, los pedidos de la web cuya fecha ya pasó y que nadie reclamó se anulan: se cancela la entrega
  (el inventario vuelve a quedar libre) y queda una nota en el pedido.
* «Reclamado» = hay una factura publicada, un pago hecho o autorizado, o una entrega ya hecha. Eso nunca se anula solo.
"""
import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models

_logger = logging.getLogger(__name__)

PARAMETRO_DIAS = 'website_dcasa.apartado_dias'
DIAS_POR_DEFECTO = 7


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_apartado_vence = fields.Date(
        'El apartado vence', copy=False, index='btree_not_null', tracking=True,
        help='Pedido de la tienda en línea que sigue sin cobrarse: si llega esta fecha sin que se reclame, se anula '
             'solo y el inventario vuelve a quedar libre. Puedes moverla para darle más días al cliente.')

    @api.model
    def _dcasa_dias_de_apartado(self):
        """Días que se guarda un pedido de la tienda sin cobrar. 0 = no vence nunca (apagado)."""
        valor = self.env['ir.config_parameter'].sudo().get_param(PARAMETRO_DIAS)
        try:
            return max(int(valor), 0) if valor not in (None, False, '') else DIAS_POR_DEFECTO
        except (TypeError, ValueError):
            return DIAS_POR_DEFECTO

    def _dcasa_marcar_apartado(self):
        """Fecha de vencimiento para los pedidos de la web que quedan por cobrar y todavía no la tienen."""
        dias = self._dcasa_dias_de_apartado()
        if not dias:
            return
        hoy = fields.Date.context_today(self)
        for orden in self.filtered(lambda o: o.website_id and not o.dcasa_apartado_vence):
            orden.sudo().dcasa_apartado_vence = hoy + timedelta(days=dias)

    def action_quotation_sent(self):
        resultado = super().action_quotation_sent()
        self._dcasa_marcar_apartado()
        return resultado

    def _action_confirm(self):
        resultado = super()._action_confirm()
        if self.env.uid != SUPERUSER_ID and self.env.user.has_group('base.group_user'):
            # La confirmó una persona del equipo: es decisión suya, no se anula sola.
            self.filtered('dcasa_apartado_vence').sudo().dcasa_apartado_vence = False
        else:
            self._dcasa_marcar_apartado()   # la confirmó la tienda sola (pago al recibir o en la tienda)
        return resultado

    def _dcasa_apartado_reclamado(self):
        """¿Ya hay dinero, factura o entrega? Entonces no se anula solo, pase lo que pase."""
        self.ensure_one()
        if self.invoice_ids.filtered(lambda f: f.state == 'posted'):
            return True
        if self.transaction_ids.filtered(lambda t: t.state in ('authorized', 'done')):
            return True
        return bool(self.picking_ids.filtered(lambda p: p.state == 'done'))

    @api.model
    def _dcasa_cron_vencer_apartados(self):
        """Cada noche: anula los apartados de la tienda cuya fecha pasó y que nadie reclamó. Devuelve cuántos."""
        hoy = fields.Date.context_today(self)
        vencidos = self.sudo().search([
            ('website_id', '!=', False), ('state', 'in', ('sent', 'sale')),
            ('dcasa_apartado_vence', '!=', False), ('dcasa_apartado_vence', '<', hoy)], limit=200)
        anulados = 0
        for orden in vencidos:
            try:
                with self.env.cr.savepoint():
                    if orden._dcasa_apartado_reclamado():
                        orden.dcasa_apartado_vence = False   # ya hay cobro o entrega: deja de vigilarse
                        continue
                    fecha = orden.dcasa_apartado_vence
                    orden._action_cancel()
                    orden.message_post(
                        body=self.env._(
                            'Apartado vencido: nadie reclamó este pedido hasta el %(fecha)s. Se anuló y el inventario '
                            'volvió a quedar libre.', fecha=fecha),
                        subtype_xmlid='mail.mt_note')
                    anulados += 1
            except Exception:
                _logger.exception('No se pudo vencer el apartado del pedido %s', orden.name)
        if anulados:
            _logger.info('Apartados vencidos anulados: %s', anulados)
        return anulados
