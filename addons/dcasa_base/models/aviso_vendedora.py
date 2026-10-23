"""El aviso a la vendedora cuando se factura y cuando se cobra su venta (decisión de la dueña, 2026-10-22).

Cuando Caja o Gerencia facturaban el pedido de una vendedora, a ella le llegaba el aviso automático de Odoo «Te
asignaron Asiento contable Borrador de factura» (la vendedora de la factura es un campo con seguimiento y Odoo avisa a
quien «asigna»), que la confundía. Ahora:

* Ese aviso de Odoo ya no sale en los asientos contables. Ella sigue siguiendo la factura, como antes.
* Al **publicar** la factura, cuando ya tiene número: «Se facturó tu venta S00139 (INV/2026/01117)» («un anticipo de
  tu venta» si la factura es solo de anticipo).
* Cuando la venta queda **cobrada** (todas sus facturas pagadas y nada más por facturar): «Tu venta S00139 ya está
  cobrada». Un abono no la deja cobrada.
* Va a su bandeja de Odoo (el chat, con su campanita), atado al pedido: al tocarlo abre la venta. Una sola vez por
  factura y por venta (pasar a borrador y volver a publicar no lo repite) y nunca a quien hizo la acción sobre su
  propia venta: ya lo sabe.
* Una factura sin pedido con vendedora (una suelta que hizo Caja) avisa igual, con el número de la factura.
* Un aviso nunca hace fallar la factura ni el cobro: si algo se tuerce, queda en el registro.
"""
import logging

from markupsafe import Markup

from odoo import models

_logger = logging.getLogger(__name__)
COBRADA = ('paid', 'in_payment')


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _message_auto_subscribe_followers(self, updated_values, default_subtype_ids):
        """Sin «Te asignaron Asiento contable …»: quien queda de vendedora sigue la factura, sin ese aviso."""
        return [(partner_id, subtipos, False) for partner_id, subtipos, _plantilla
                in super()._message_auto_subscribe_followers(updated_values, default_subtype_ids)]

    def _post(self, soft=True):
        publicadas = super()._post(soft=soft)
        publicadas._dcasa_avisar_a_la_vendedora('facturada')
        return publicadas

    def _invoice_paid_hook(self):
        res = super()._invoice_paid_hook()
        self.filtered(lambda m: m.payment_state in COBRADA)._dcasa_avisar_a_la_vendedora('cobrada')
        return res

    # ------------------------------------------------------------------

    def _dcasa_avisar_a_la_vendedora(self, momento):
        """``momento``: ``'facturada'`` (al publicar) o ``'cobrada'`` (al quedar pagada)."""
        for factura in self.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
                                     and not m.dcasa_historica):
            try:
                with self.env.cr.savepoint():
                    for registro, vendedora, texto in factura.sudo()._dcasa_avisos_de_venta(momento):
                        registro._dcasa_avisar(vendedora, texto)
            except Exception:
                _logger.exception('No se pudo avisar a la vendedora de la factura %s (%s)', factura.name, momento)

    def _dcasa_avisos_de_venta(self, momento):
        """``[(registro, vendedora, texto)]``: a quién avisar, de qué, y en qué registro (el pedido, o la factura si no
        salió de uno). Sin la vendedora que hizo la acción ni usuarios inactivos o externos."""
        self.ensure_one()
        quien = self.env.user
        avisos = []
        lineas = self.line_ids.sale_line_ids
        por_vendedora = {}
        for pedido in lineas.order_id:
            if pedido.user_id:
                por_vendedora.setdefault(pedido.user_id, self.env['sale.order'])
                por_vendedora[pedido.user_id] |= pedido
        if not lineas and self.invoice_user_id:
            por_vendedora[self.invoice_user_id] = None
        for vendedora, suyos in por_vendedora.items():
            if vendedora == quien or not vendedora.active or vendedora.share:
                continue
            if suyos is None:  # una factura suelta: la venta es la factura
                texto = (self.env._('Se facturó tu venta %s', self.name) if momento == 'facturada'
                         else self.env._('Tu venta %s ya está cobrada', self.name))
                avisos.append((self, vendedora, texto))
                continue
            pedidos = suyos.filtered(_venta_cobrada) if momento == 'cobrada' else suyos
            if not pedidos:
                continue
            registro = pedidos if len(pedidos) == 1 else self
            nombres, plural = ', '.join(pedidos.mapped('name')), len(pedidos) > 1
            if momento == 'facturada':
                anticipo = all(linea.is_downpayment for linea in lineas if linea.order_id in pedidos)
                texto = _texto_facturada(self.env, nombres, self.name, plural, anticipo)
            else:
                texto = (self.env._('Tus ventas %s ya están cobradas', nombres) if plural
                         else self.env._('Tu venta %s ya está cobrada', nombres))
            avisos.append((registro, vendedora, texto))
        return avisos


def _venta_cobrada(pedido):
    """¿La venta está cobrada? Nada más por facturar y todas sus facturas publicadas, pagadas."""
    facturas = pedido.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
    return (pedido.invoice_status != 'to invoice' and bool(facturas)
            and all(factura.payment_state in COBRADA for factura in facturas))


def _texto_facturada(env, ventas, factura, plural, anticipo):
    if anticipo:
        return env._('Se facturó un anticipo de tu venta %(venta)s (%(factura)s)', venta=ventas, factura=factura)
    if plural:
        return env._('Se facturaron tus ventas %(ventas)s (%(factura)s)', ventas=ventas, factura=factura)
    return env._('Se facturó tu venta %(venta)s (%(factura)s)', venta=ventas, factura=factura)


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _dcasa_avisar(self, vendedora, texto):
        """Un aviso a la bandeja de ``vendedora`` atado a este registro, una sola vez (el mismo texto no se repite).
        Sin asunto: en la bandeja saldría repetido («Asunto: …» y el mismo texto debajo)."""
        self.ensure_one()
        partner = vendedora.partner_id
        if self.env['mail.message'].sudo().search_count([
                ('model', '=', self._name), ('res_id', '=', self.id), ('message_type', '=', 'user_notification'),
                ('body', 'ilike', texto), ('partner_ids', 'in', partner.ids)], limit=1):
            return
        self.sudo().with_context(lang=partner.lang or self.env.lang).message_notify(
            partner_ids=partner.ids, body=Markup('<p>%s</p>') % texto,
            email_layout_xmlid='mail.mail_notification_light')
