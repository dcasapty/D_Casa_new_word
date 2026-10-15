import logging

from odoo import fields, models

from . import reglas as R

_logger = logging.getLogger(__name__)
AVISOS_MAXIMOS = 3


class AccountMove(models.Model):
    _inherit = 'account.move'

    dcasa_compra_ids = fields.One2many('dcasa.compra', 'move_id', string='Compra con puntos')

    # ------------------------------------------------------------------------
    # La factura pagada suma puntos — sin volver a teclear la venta
    # ------------------------------------------------------------------------

    def _invoice_paid_hook(self):
        res = super()._invoice_paid_hook()
        Compra = self.env['dcasa.compra'].sudo()
        # Las facturas cargadas del sistema anterior son historia: no dan puntos.
        for move in self.filtered(lambda m: m.move_type == 'out_invoice' and not m.dcasa_historica
                                  and m.payment_state in ('paid', 'in_payment')):
            Compra._registrar_desde_factura(move)
        return res

    # ------------------------------------------------------------------------
    # Y si la factura se deshace, sus puntos también
    # ------------------------------------------------------------------------

    def _dcasa_anular_compras(self, motivo):
        compras = self.sudo().dcasa_compra_ids.filtered(lambda c: not c.anulada_en)
        if compras:
            # por_factura: la factura misma se deshace, así que si vuelve a quedar pagada sus puntos pueden volver.
            compras._anular(motivo, self.env.user.login, por_factura=True)

    def button_draft(self):
        self.check_access('write')  # antes de anular puntos con sudo (método público por RPC)
        # Los pagos que tenía la factura se miran antes de tocar nada; el aviso sale después, solo si Odoo aceptó.
        con_pagos = self._dcasa_pagos_ligados()
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            move._dcasa_anular_compras(self.env._('La factura %s volvió a borrador.', move.name))
        res = super().button_draft()
        self._dcasa_avisar_pagos(con_pagos, borrada=False)
        return res

    def button_cancel(self):
        self.check_access('write')  # antes de anular puntos con sudo (método público por RPC)
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            move._dcasa_anular_compras(self.env._('Se canceló la factura %s.', move.name))
        return super().button_cancel()

    def unlink(self):
        """Borrar un borrador no se queda trabado por los puntos que dio.

        Lo normal es que la compra ya esté anulada (la factura volvió a borrador antes de poder borrarse). Si todavía
        queda una activa, se anula con su asiento contrario; el libro no se toca. La compra se queda en la historia
        del programa, sin factura (la clave foránea es ``set null``) pero con su número y su motivo. Se anula DESPUÉS
        de borrar: si Odoo se niega (una factura publicada no se borra), no se tocó ningún punto.
        """
        self.check_access('unlink')  # antes de anular puntos con sudo (método público por RPC)
        compras = self.sudo().dcasa_compra_ids.filtered(lambda c: not c.anulada_en)
        motivos = {compra.id: self.env._('Se eliminó la factura %s.', compra.name) for compra in compras}
        con_pagos = self._dcasa_pagos_ligados()
        res = super().unlink()
        for compra in compras:
            compra._anular(motivos[compra.id], self.env.user.login, por_factura=True)
        self._dcasa_avisar_pagos(con_pagos, borrada=True)
        return res

    # ------------------------------------------------------------------------
    # El pago de una factura que se deshace no se borra: se avisa dónde cancelarlo
    # ------------------------------------------------------------------------

    def _dcasa_pagos_ligados(self):
        """``[(factura, número, pagos)]`` de las facturas de cliente que tienen pagos conciliados. Nunca falla."""
        ligados = []
        try:
            with self.env.cr.savepoint():
                for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
                    pagos = move.sudo()._get_reconciled_payments()
                    if pagos:
                        ligados.append((move, move.name, pagos))
        except Exception:  # noqa: BLE001  — un aviso nunca hace fallar la factura
            _logger.exception('No se pudieron revisar los pagos de las facturas %s', self.ids)
            return []
        return ligados

    def _dcasa_ruta_de_pagos(self):
        """«Facturación › Clientes › Pagos», tal como la ve quien está leyendo (sale del menú real)."""
        menu = self.env.ref('account.menu_action_account_payments_receivable', raise_if_not_found=False)
        if not menu:
            return self.env._('Facturación › Clientes › Pagos')
        return ' › '.join(menu.sudo().complete_name.split('/'))

    def _dcasa_avisar_pagos(self, con_pagos, borrada):
        """Avisa a quien lo hizo (aviso emergente que se queda hasta cerrarlo) y deja una nota en la factura y en cada
        pago. Al volver a borrador el pago sigue ligado a la factura; al borrarla queda sin aplicar. No cambia lo que
        hace el botón y nunca lo hace fallar: si algo se tuerce, queda en el registro."""
        if not con_pagos:
            return
        try:
            with self.env.cr.savepoint():
                ruta = self._dcasa_ruta_de_pagos()
                for avisadas, (factura, numero, pagos) in enumerate(con_pagos):
                    lista = ', '.join(pagos[:3].mapped(lambda p: p.name or p.display_name))
                    if len(pagos) > 3:
                        lista += self.env._(' y %s más', len(pagos) - 3)
                    textos = self._dcasa_texto_de_pagos(numero, lista, ruta, len(pagos) > 1, borrada)
                    # La nota queda en la factura (si sigue existiendo) y en cada pago: el rastro no se pierde aunque
                    # luego se borre el borrador.
                    if not borrada and factura.exists():
                        factura.sudo().message_post(body=textos['aviso'], message_type='comment',
                                                    subtype_xmlid='mail.mt_note')
                    for pago in pagos.sudo():
                        pago.message_post(body=textos['aviso'], message_type='comment', subtype_xmlid='mail.mt_note')
                    persona = self.env.user.partner_id
                    # Un aviso por factura, con tope: un borrado de muchas facturas no llena la pantalla de avisos.
                    if persona and avisadas < AVISOS_MAXIMOS:
                        self.env['bus.bus']._sendone(persona, 'simple_notification', {
                            'type': 'warning', 'sticky': True, 'title': textos['titulo'],
                            'message': textos['aviso']})
        except Exception:  # noqa: BLE001  — un aviso nunca hace fallar la factura
            _logger.exception('No se pudo avisar de los pagos de las facturas %s', self.ids)

    def _dcasa_texto_de_pagos(self, numero, lista, ruta, varios, borrada):
        _ = self.env._
        datos = {'factura': numero, 'pagos': lista, 'ruta': ruta}
        if borrada:
            aviso = (_('Se eliminó la factura %(factura)s. Los pagos %(pagos)s quedaron sin aplicar. '
                       'Si eran de prueba, cancélalos en %(ruta)s.', **datos) if varios else
                     _('Se eliminó la factura %(factura)s. El pago %(pagos)s quedó sin aplicar. '
                       'Si era de prueba, cancélalo en %(ruta)s.', **datos))
            return {'titulo': _('Pago sin aplicar'), 'aviso': aviso}
        aviso = (_('Los pagos %(pagos)s siguen ligados a la factura %(factura)s. Si borras el borrador, esos pagos '
                   'quedan sin aplicar. Si eran de prueba, cancélalos en %(ruta)s.', **datos) if varios else
                 _('El pago %(pagos)s sigue ligado a la factura %(factura)s. Si borras el borrador, ese pago '
                   'queda sin aplicar. Si era de prueba, cancélalo en %(ruta)s.', **datos))
        return {'titulo': _('La factura tenía pago'), 'aviso': aviso}

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        # Nota de crédito sobre una factura que dio puntos: total anula, parcial descuenta.
        for nota in posted.filtered(lambda m: m.move_type == 'out_refund' and m.reversed_entry_id):
            original = nota.reversed_entry_id
            compras = original.sudo().dcasa_compra_ids.filtered(lambda c: not c.anulada_en)
            if not compras:
                continue
            devuelto = R.a_centavos(abs(nota.amount_total_signed))
            if devuelto >= compras.monto_centavos:
                compras._anular(self.env._('Nota de crédito %s', nota.name), self.env.user.login)
            else:
                compras._devolucion_parcial(nota, self.env.user.login)
        posted._dcasa_reabrir_compras()
        return posted

    def _dcasa_reabrir_compras(self):
        """Una factura que volvió a borrador y se publica otra vez con su pago todavía puesto vuelve a estar pagada
        sin que Odoo avise (solo avisa cuando el pago se concilia): sin esto, el cliente de una venta real quedaría
        sin los puntos que se anularon por la corrección. Nunca hace fallar la publicación."""
        pagadas = self.filtered(lambda m: m.move_type == 'out_invoice' and not m.dcasa_historica
                                and m.payment_state in ('paid', 'in_payment'))
        if not pagadas:
            return
        Compra = self.env['dcasa.compra'].sudo()
        for move in Compra.search([('move_id', 'in', pagadas.ids), ('anulada_por_factura', '=', True)]).move_id:
            try:
                with self.env.cr.savepoint():
                    Compra._registrar_desde_factura(move)
            except Exception:  # noqa: BLE001  — el programa de puntos nunca hace fallar una factura
                _logger.exception('No se pudieron volver a dar los puntos de la factura %s', move.name)

    # ------------------------------------------------------------------------
    # Lo que se imprime en la factura
    # ------------------------------------------------------------------------

    def _dcasa_puntos_por_ganar(self):
        """Cuántos puntos da esta factura al pagarse (para imprimirlo antes del pago)."""
        self.ensure_one()
        monto = R.a_centavos(self.amount_total_signed)
        if self.move_type != 'out_invoice' or monto <= 0:
            return 0
        try:
            return R.puntos_de_compra(monto, R.cargar_reglas())
        except R.FaltaConfigurar:
            return 0

    def _dcasa_socios_factura(self):
        """Lo que la factura impresa dice del programa. Solo lectura del libro y de las reglas.

        Devuelve un dict (o None si no hay nada que decir):
        socio, codigo, compra (la compra activa que dio puntos), por_ganar (si aún no se
        pagó), saldo (suma del libro), canjes (premios cobrados en el pedido), padrino_codigo
        (para invitar a quien no es socio), web (dominio público).
        """
        self.ensure_one()
        ficha = self.sudo().commercial_partner_id
        if ficha._is_public():
            return None
        compra = self.sudo().dcasa_compra_ids.filtered(lambda c: not c.anulada_en)[:1]
        canjes = self.sudo().invoice_line_ids.sale_line_ids.dcasa_canje_id
        pedidos = self.sudo().invoice_line_ids.sale_line_ids.order_id
        padrino = ficha.dcasa_referido_por_id or pedidos.dcasa_referido_por_id[:1]
        return {
            'socio': bool(ficha.dcasa_socio_codigo),
            'codigo': ficha.dcasa_socio_codigo or '',
            'compra': compra,
            'por_ganar': 0 if compra else self._dcasa_puntos_por_ganar(),
            'saldo': ficha.dcasa_saldo,
            'canjes': canjes,
            'padrino_codigo': padrino.dcasa_socio_codigo or '',
            'web': self.company_id._dcasa_url_publica_corta(),
        }


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _dcasa_es_premio(self):
        self.ensure_one()
        premio = self.env.ref('dcasa_socios.product_premio_canje', raise_if_not_found=False)
        return bool(self.sudo().sale_line_ids.dcasa_canje_id) or bool(premio and self.product_id == premio)

    def _dcasa_etiqueta(self):
        """La línea con que se cobró un premio se imprime identificada como tal."""
        if self._dcasa_es_premio():
            return "Premio Socios D'CASA"
        return super()._dcasa_etiqueta()

    def _dcasa_va_aparte(self):
        """El premio es un descuento, no un servicio que se cobra: se queda entre los muebles."""
        if self._dcasa_es_premio():
            return False
        return super()._dcasa_va_aparte()
