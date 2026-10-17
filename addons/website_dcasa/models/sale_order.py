"""Apartados que nadie reclama (decisión de la dueña, 2026-10-09; apartados a mano y avisos, 2026-10-10).

Con «Pago al recibir o en la tienda», Odoo confirma el pedido solo y reserva el inventario; con transferencia o Yappy
el pedido queda como cotización enviada, esperando el pago. Si el cliente nunca llega, el inventario quedaba
apartado para siempre y el equipo creía que esa venta iba a ocurrir.

* Al quedar «por cobrar» (cotización enviada o confirmada sola por la tienda) un pedido de la web recibe una fecha:
  ``dcasa_apartado_vence`` = hoy + los días de apartado (Ajustes › Sitio web; 7 por defecto, 0 = apagado).
* Un apartado a mano (WhatsApp, mostrador) usa los mismos días: la vendedora pulsa «Apartar» en el pedido. Un pedido
  hecho a mano SIN ese botón es una venta normal y no vence nunca.
* Una vendedora puede mover esa fecha (extender) desde el pedido. Si ELLA confirma un pedido de la web, es una
  decisión suya y la fecha se borra: nada se anula solo. En un apartado a mano la fecha se queda: ella misma la puso.
* Cada noche, los pedidos con fecha vencida que nadie reclamó se anulan: se cancela la entrega (el inventario vuelve
  a quedar libre) y queda una nota en el pedido.
* Cuando faltan ``DIAS_DE_AVISO`` días o menos, la vendedora del pedido recibe una actividad para avisarle al cliente
  (el aviso al cliente lo manda ella, no el sistema). Se crea una vez por fecha de vencimiento.
* «Reclamado» = hay una factura publicada, un pago hecho o autorizado, o una entrega ya hecha. Eso nunca se anula solo.
"""
import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PARAMETRO_DIAS = 'website_dcasa.apartado_dias'
DIAS_POR_DEFECTO = 7
DIAS_DE_AVISO = 2
RESUMEN_DEL_AVISO = 'Apartado por vencer: avisa al cliente'
APARTADO_WEB = 'Apartado por página web'
APARTADO_TIENDA = 'Apartado en la tienda'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_apartado_vence = fields.Date(
        'El apartado vence', copy=False, index='btree_not_null', tracking=True,
        help='Pedido apartado que sigue sin cobrarse: si llega esta fecha sin que se reclame, se anula solo y el '
             'inventario vuelve a quedar libre. Puedes moverla para darle más días al cliente, o borrarla si la '
             'venta ya es firme.')
    dcasa_apartado_aviso = fields.Date(
        copy=False, readonly=True,
        help='Fecha de vencimiento para la que ya se le dio el aviso a la vendedora (para no repetirlo cada noche).')
    dcasa_apartado_dias = fields.Integer(
        'Días que le quedan', compute='_compute_dcasa_apartado_dias',
        help='Días que faltan para que se anule el apartado (0 = vence hoy, negativo = ya pasó la fecha).')
    dcasa_apartado_origen = fields.Char(
        'Tipo de apartado', compute='_compute_dcasa_apartado_origen',
        help='«Apartado por página web» si el pedido llegó por la tienda en línea; «Apartado en la tienda» si lo '
             'apartó una vendedora con el botón «Apartar» (decisión de la dueña, 2026-10-17: que siempre se vea).')

    @api.depends('dcasa_apartado_vence')
    def _compute_dcasa_apartado_dias(self):
        hoy = fields.Date.context_today(self)
        for orden in self:
            orden.dcasa_apartado_dias = (orden.dcasa_apartado_vence - hoy).days if orden.dcasa_apartado_vence else 0

    @api.depends('dcasa_apartado_vence', 'website_id')
    def _compute_dcasa_apartado_origen(self):
        for orden in self:
            orden.dcasa_apartado_origen = (
                (APARTADO_WEB if orden.website_id else APARTADO_TIENDA) if orden.dcasa_apartado_vence else False)

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

    def action_dcasa_apartar(self):
        """Botón «Apartar»: la vendedora aparta a mano; cuenta los mismos días que un apartado de la tienda."""
        dias = self._dcasa_dias_de_apartado()
        if not dias:
            raise UserError(self.env._(
                'Los apartados están en 0 días, así que no vencen. Cambia los días en Ajustes › Sitio web › '
                '«Apartados de la tienda», o escribe la fecha a mano en el pedido.'))
        hoy = fields.Date.context_today(self)
        for orden in self:
            if orden.state not in ('sent', 'sale'):
                raise UserError(self.env._(
                    'El pedido %s todavía no está enviado ni confirmado: envía la cotización o confírmalo y '
                    'después apártalo.', orden.name))
            if not orden.dcasa_apartado_vence:
                orden.dcasa_apartado_vence = hoy + timedelta(days=dias)
        return True

    def action_quotation_sent(self):
        resultado = super().action_quotation_sent()
        self._dcasa_marcar_apartado()
        return resultado

    def _action_confirm(self):
        resultado = super()._action_confirm()
        if self.env.uid != SUPERUSER_ID and self.env.user.has_group('base.group_user'):
            # La confirmó una persona del equipo: en un pedido de la web es decisión suya y no se anula sola.
            # En un apartado a mano la fecha la puso ella misma: se queda.
            self.filtered(lambda o: o.website_id and o.dcasa_apartado_vence).sudo().dcasa_apartado_vence = False
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
        """Cada noche: anula los apartados cuya fecha pasó y que nadie reclamó, y avisa a la vendedora de los que
        están por vencer. Devuelve cuántos anuló."""
        hoy = fields.Date.context_today(self)
        vencidos = self.sudo().search([
            ('state', 'in', ('sent', 'sale')),
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
        try:
            with self.env.cr.savepoint():
                self._dcasa_avisar_apartados_por_vencer()
        except Exception:
            _logger.exception('No se pudieron revisar los avisos de apartados por vencer')
        return anulados

    @api.model
    def _dcasa_avisar_apartados_por_vencer(self):
        """Actividad para la vendedora del pedido cuando faltan ``DIAS_DE_AVISO`` días o menos. Devuelve cuántas creó.

        Una vez por fecha de vencimiento (``dcasa_apartado_aviso``): si ella la marca como hecha no vuelve a salir esa
        noche, y si mueve la fecha el aviso nuevo llega cuando toque. Los avisos que ya no valen (pedido anulado,
        reclamado o con otra fecha) se quitan. Un pedido que ya se reclamó (factura publicada, pago o entrega) deja de
        vigilarse esa misma noche: se le borra la fecha y sale de la lista de apartados.
        """
        hoy = fields.Date.context_today(self)
        pedidos = self.sudo().search([
            ('state', 'in', ('sent', 'sale')), ('dcasa_apartado_vence', '!=', False)])
        reclamados = pedidos.filtered(lambda o: o._dcasa_apartado_reclamado())
        vigentes = {orden.id: orden.dcasa_apartado_vence for orden in pedidos - reclamados}
        reclamados.dcasa_apartado_vence = False
        avisos = self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'sale.order'), ('summary', '=', RESUMEN_DEL_AVISO)])
        avisos.filtered(lambda a: vigentes.get(a.res_id) != a.date_deadline).unlink()
        creados = 0
        for orden in (pedidos - reclamados).filtered(
                lambda o: hoy <= o.dcasa_apartado_vence <= hoy + timedelta(days=DIAS_DE_AVISO)):
            if orden.dcasa_apartado_aviso == orden.dcasa_apartado_vence or not orden.user_id:
                continue
            cliente = orden.partner_id
            nota = self.env._(
                'El apartado del pedido %(pedido)s de %(cliente)s%(telefono)s vence el %(fecha)s. Avísale por '
                'WhatsApp. Si lo quiere más días, mueve la fecha en el pedido; si ya es una venta firme, bórrala.',
                pedido=orden.name, cliente=cliente.name or '',
                telefono=f' ({cliente.phone})' if cliente.phone else '', fecha=orden.dcasa_apartado_vence)
            orden.activity_schedule(
                'mail.mail_activity_data_todo', date_deadline=orden.dcasa_apartado_vence,
                summary=RESUMEN_DEL_AVISO, note=nota, user_id=orden.user_id.id)
            orden.dcasa_apartado_aviso = orden.dcasa_apartado_vence
            creados += 1
        return creados
