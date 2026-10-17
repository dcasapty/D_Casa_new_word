"""El primer abono: al menos la mitad del total (decisión de la gerencia A3, 17 oct 2026; docs/DECISIONES_CONTABLES.md).

* En el asistente «Pagar» (y en todo lo que lo usa: Brian ``registrar_pago``, «Registrar cobro» del Inicio…), el
  primer pago de una factura de cliente que todavía no tiene pagos tiene que ser al menos la mitad de su total
  (``ANTICIPO_MINIMO``). Si es menos, solo Gerencia (o un administrador) lo registra; a los demás les sale el mensaje
  «El primer abono debe ser de al menos la mitad: $X. Si es menos, lo registra Gerencia.», y el asistente lo avisa
  antes de pulsar el botón.
* Nunca frena un pago completo (aunque sea menos de la mitad del total, porque una nota de crédito ya bajó lo que
  falta) ni los pagos siguientes de un abono (libres).
* La conciliación bancaria (o aplicar a la factura un cobro que ya estaba) NO se frena: el dinero ya entró. Si así
  entra un primer abono menor a la mitad, queda una nota en la factura para que Gerencia lo revise. Cuando Gerencia lo
  registra con «Pagar», la nota dice quién lo autorizó. Lo que corre con ``sudo`` (la tienda web, la carga del sistema
  anterior) no deja notas.
"""
import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from . import formato

_logger = logging.getLogger(__name__)
CLAVE = 'dcasa_primer_abono_antes'
POR_PAGAR = 'dcasa_primer_abono_por_pagar'


def _pagado(factura):
    """Lo pagado con cobros (sin las notas de crédito aplicadas)."""
    return sum(pago.get('amount') or 0.0 for pago in factura._dcasa_pagos() if not pago.get('is_refund'))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _reconcile_pre_hook(self):
        data = super()._reconcile_pre_hook()
        if self.env.su:  # la tienda web, la carga del sistema anterior, el cron: sin avisos
            return data
        try:  # solo lee: nunca estorba la conciliación
            # Lo cargado del sistema anterior (``dcasa_historica``) es historia: no lleva avisos.
            candidatas = self.move_id.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted' and not m.dcasa_historica
                and m.payment_state in ('not_paid', 'partial'))
            data[CLAVE] = candidatas.filtered(lambda m: not m._dcasa_tiene_pagos()).ids
        except Exception:  # noqa: BLE001 - un aviso nunca hace fallar un pago
            _logger.exception('DCASA_ABONO no se pudo revisar el primer abono antes de conciliar')
        return data

    def _reconcile_post_hook(self, data):
        res = super()._reconcile_post_hook(data)
        ids = data.get(CLAVE)
        if ids:
            try:
                with self.env.cr.savepoint():
                    self.env['account.move'].browse(ids)._dcasa_avisar_primer_abono_bajo(
                        por_pagar=bool(self.env.context.get(POR_PAGAR)))
            except Exception:  # noqa: BLE001 - un aviso nunca hace fallar un pago
                _logger.exception('DCASA_ABONO no se pudo dejar el aviso del primer abono')
        return res


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _dcasa_primer_abono_por_debajo(self):
        """Las facturas (de las que no tenían pagos antes) que quedaron con un primer abono menor a la mitad."""
        return self.filtered(
            lambda f: f._dcasa_tiene_pagos() and f.currency_id.compare_amounts(f.amount_residual, 0) > 0
            and f.currency_id.compare_amounts(_pagado(f), f._dcasa_minimo_primer_abono()) < 0)

    def _dcasa_avisar_primer_abono_bajo(self, por_pagar=False):
        """Deja una nota en cada factura cuyo primer abono quedó por debajo de la mitad (solo lee y escribe la nota)."""
        for factura in self._dcasa_primer_abono_por_debajo():
            texto = self.env._('Primer abono de %(pagado)s: es menos de la mitad del total (%(total)s).',
                               pagado=formato.dinero(_pagado(factura)), total=formato.dinero(factura.amount_total))
            if por_pagar and self.env.user._dcasa_es_gerencia():
                texto += ' ' + self.env._('Lo autorizó y lo registró %s (Gerencia).', self.env.user.name)
            elif por_pagar:
                texto += ' ' + self.env._('Lo registró %s.', self.env.user.name)
            else:
                texto += ' ' + self.env._('Entró sin pasar por «Pagar» (conciliación bancaria o un cobro que ya '
                                          'estaba): el dinero ya entró. Que Gerencia lo revise.')
            factura.sudo().message_post(body=Markup('<p>%s</p>') % texto, message_type='comment',
                                        subtype_xmlid='mail.mt_note', author_id=self.env.user.partner_id.id)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    dcasa_aviso_primer_abono = fields.Char(
        'Aviso del primer abono', compute='_compute_dcasa_aviso_primer_abono',
        help='El primer abono de una factura de cliente es al menos la mitad del total; si es menos, lo registra '
             'Gerencia.')

    def _dcasa_factura_con_primer_abono_bajo(self):
        """La factura de cliente cuyo primer abono (este pago) queda por debajo de la mitad, o una vacía.

        Solo cuando el asistente paga una sola factura con un monto que se puede cambiar (si no, Odoo paga cada factura
        completa). Varias facturas en un solo pago se revisan después de pagar (``_create_payments``)."""
        self.ensure_one()
        vacia = self.env['account.move']
        if self.partner_type != 'customer' or self.payment_type != 'inbound' or not self.can_edit_wizard:
            return vacia
        facturas = self.line_ids.move_id
        if len(facturas) != 1 or facturas.move_type != 'out_invoice' or facturas.currency_id != self.currency_id:
            return vacia
        moneda = self.currency_id
        if moneda.compare_amounts(self.amount, facturas.amount_residual) >= 0:  # el pago completo es libre
            return vacia
        if facturas._dcasa_tiene_pagos():  # los abonos siguientes son libres
            return vacia
        if moneda.compare_amounts(self.amount, facturas._dcasa_minimo_primer_abono()) >= 0:
            return vacia
        return facturas

    @api.depends('amount', 'line_ids', 'can_edit_wizard', 'payment_type', 'partner_type', 'currency_id')
    @api.depends_context('uid')
    def _compute_dcasa_aviso_primer_abono(self):
        gerencia = self.env.user._dcasa_es_gerencia()
        for wizard in self:
            factura = wizard._dcasa_factura_con_primer_abono_bajo()
            if not factura:
                wizard.dcasa_aviso_primer_abono = False
            elif gerencia:
                wizard.dcasa_aviso_primer_abono = self.env._(
                    'Es el primer abono y es menos de la mitad (%s). Como eres Gerencia, puedes registrarlo: queda una '
                    'nota en la factura.', formato.dinero(factura._dcasa_minimo_primer_abono()))
            else:
                wizard.dcasa_aviso_primer_abono = factura._dcasa_mensaje_primer_abono()

    def _create_payments(self):
        self.ensure_one()
        self._dcasa_exigir_permiso()  # dcasa_base: quién cobra (ese mensaje va primero)
        libre = self.env.su or self.env.user._dcasa_es_gerencia()
        sin_pagos = self.env['account.move']
        if not libre and self.partner_type == 'customer' and self.payment_type == 'inbound':
            factura = self._dcasa_factura_con_primer_abono_bajo()
            if factura:
                raise UserError(factura._dcasa_mensaje_primer_abono())
            sin_pagos = self.line_ids.move_id.filtered(
                lambda m: m.move_type == 'out_invoice' and not m._dcasa_tiene_pagos())
        pagos = super(AccountPaymentRegister, self.with_context(**{POR_PAGAR: True}))._create_payments()
        # Varias facturas en un solo pago: lo que quedó en cada una (todo se deshace si una quedó por debajo).
        bajas = sin_pagos._dcasa_primer_abono_por_debajo()
        if bajas:
            raise UserError(bajas[0]._dcasa_mensaje_primer_abono())
        return pagos
