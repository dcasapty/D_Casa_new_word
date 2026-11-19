"""La transacción de Tilopay: crear la página de pago, y confirmar SOLO preguntándole a Tilopay.

Qué cuenta como «pagado» (docs/TILOPAY.md §4 y §5):

* Nada que llegue por el navegador (el retorno) ni por un aviso decide un pago. Sirven para saber QUÉ orden revisar.
* ``_dcasa_tilopay_confirmar`` bloquea la transacción, consulta a Tilopay con la orden QUE GUARDAMOS, y
  ``tilopay_api.evaluar_consulta`` compara orden, monto, moneda, aprobación y entorno. Solo entonces ``_set_done``.
* ``_apply_updates`` solo acepta ``DatosVerificados`` (lo que sale de esa evaluación).
* Una falla de Tilopay o de la red deja la transacción como estaba (nunca «pagada») y no tumba nada.
"""
import logging
import re
import secrets
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import psycopg2
from markupsafe import Markup

from odoo import SUPERUSER_ID, api, fields, models, modules
from odoo.exceptions import ValidationError
from odoo.tools import float_repr, float_round
from odoo.tools.urls import urljoin

from . import tilopay_api as api_tilopay

_logger = logging.getLogger(__name__)

CODIGO = 'tilopay'
RUTA_RETORNO = '/payment/tilopay/return'
RUTA_AVISO = '/payment/tilopay/webhook'

ESPERA_ENTRE_CONSULTAS = 5            # segundos entre dos consultas de la misma transacción
INTENTOS_EN_CURSO = 5                 # páginas de pago abiertas sin terminar por pedido…
VENTANA_DE_INTENTOS = timedelta(minutes=15)   # …en este rato
VIDA_DE_UN_INTENTO = timedelta(hours=24)      # sin pago a las 24 h: vencida
VENTANA_DEL_CRON = timedelta(days=3)          # hasta cuándo se pregunta por una transacción sin confirmar
MINIMO_PARA_EL_CRON = timedelta(minutes=2)    # no se le gana al cliente que todavía está pagando
LOTE_DEL_CRON = 50

MENSAJE_ERROR_RECHAZO = ('Tilopay no pudo aprobar este pago. Puedes intentarlo de nuevo con otra tarjeta o elegir otra '
                         'forma de pago.')
MENSAJE_ERROR_DISTINTO = ('Tilopay reportó un cobro distinto al de tu pedido, así que no lo tomamos como pago. Nuestro '
                          'equipo lo revisa; escríbenos por WhatsApp si necesitas ayuda.')
MENSAJE_CANCELADO = ('El pago no se completó. Tu pedido sigue guardado: puedes intentarlo de nuevo o elegir otra forma '
                     'de pago.')
MENSAJE_VENCIDO = 'Este intento de pago venció sin recibirse el pago. Puedes intentarlo de nuevo.'


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    dcasa_tilopay_orden = fields.Char(
        'Orden en Tilopay', readonly=True, copy=False, index='btree_not_null',
        help='El número de orden que se mandó a Tilopay (único para siempre en su cuenta). Se guarda ANTES de pedir la '
             'página de pago y es la única orden con la que se busca y se consulta.')
    dcasa_tilopay_consulta = fields.Datetime('Última consulta a Tilopay', readonly=True, copy=False)
    dcasa_tilopay_entorno_visto = fields.Char('Entorno que dijo Tilopay', readonly=True, copy=False)
    dcasa_tilopay_veredicto = fields.Char('Última respuesta de Tilopay', readonly=True, copy=False)

    _dcasa_tilopay_orden_uniq = models.Constraint(
        'unique(dcasa_tilopay_orden)', 'La orden de Tilopay debe ser única.')

    # ------------------------------------------------------------------ crear la página de pago

    def _get_specific_rendering_values(self, processing_values):
        """Pide a Tilopay la página de pago y manda al cliente allá. Si algo falla, el cliente ve un mensaje claro y la
        venta sigue intacta (la transacción no llega a existir)."""
        if self.provider_code != CODIGO:
            return super()._get_specific_rendering_values(processing_values)
        self._dcasa_tilopay_exigir_listo()
        orden = self._dcasa_tilopay_nueva_orden()
        try:
            url = self.provider_id._dcasa_tilopay_cliente().crear_pago(self._dcasa_tilopay_cuerpo(orden))
        except api_tilopay.ErrorTilopay as error:
            _logger.warning('Tilopay: no se pudo abrir la página de pago de %s: %s', self.reference, error)
            raise ValidationError(self.env._(
                'No pudimos abrir la página de pago de Tilopay. Intenta de nuevo en un momento o elige otra forma de '
                'pago.')) from None
        partes = urlsplit(url)
        return {'api_url': urlunsplit(partes._replace(query='', fragment='')),
                'url_params': dict(parse_qsl(partes.query, keep_blank_values=True))}

    def _dcasa_tilopay_exigir_listo(self):
        """Lo que se exige para abrir una página de pago, aunque el cliente haya mandado un proveedor que no se le
        ofreció."""
        self.ensure_one()
        if not self.provider_id._dcasa_tilopay_ofrecible():
            raise ValidationError(self.env._(
                'Tilopay no está disponible ahora. Elige otra forma de pago o escríbenos por WhatsApp.'))
        if self.currency_id.name != 'USD':
            raise ValidationError(self.env._('Tilopay solo cobra en dólares (USD).'))
        pedidos = self.sale_order_ids
        total_no_coincide = len(pedidos) != 1 or pedidos.currency_id != self.currency_id or \
            self.currency_id.compare_amounts(self.amount, pedidos.amount_total) != 0
        if total_no_coincide or self.currency_id.compare_amounts(pedidos.sudo().amount_paid, 0) > 0:
            raise ValidationError(self.env._(
                'Por ahora Tilopay solo paga el pedido completo. Elige otra forma de pago para un abono.'))
        recientes = self.sudo().search_count([
            ('provider_id', '=', self.provider_id.id), ('dcasa_tilopay_orden', '!=', False), ('id', '!=', self.id),
            ('state', 'in', ('draft', 'pending')), ('sale_order_ids', 'in', pedidos.ids),
            ('create_date', '>=', fields.Datetime.now() - VENTANA_DE_INTENTOS)])
        if recientes >= INTENTOS_EN_CURSO:
            raise ValidationError(self.env._(
                'Ya hay varios intentos de pago en curso para este pedido. Espera unos minutos o elige otra forma '
                'de pago.'))

    def _dcasa_tilopay_nueva_orden(self):
        """``<referencia>-<8 letras y números al azar>``: única para siempre en Tilopay, imposible de adivinar contando
        y distinta entre staging y producción. Se guarda ANTES de llamar a Tilopay."""
        self.ensure_one()
        base = re.sub(r'[^A-Za-z0-9-]', '', self.reference or '')[:24].strip('-')
        for _intento in range(10):
            orden = f'{base or "DC"}-{secrets.token_hex(4)}'
            if api_tilopay.orden_valida(orden) and not self.sudo().search_count(
                    [('dcasa_tilopay_orden', '=', orden)], limit=1):
                break
        else:
            raise ValidationError(self.env._('No se pudo preparar el pago. Intenta de nuevo.'))
        self.sudo().dcasa_tilopay_orden = orden
        self.sudo().provider_reference = orden
        return orden

    def _dcasa_tilopay_cuerpo(self, orden):
        """Lo que se manda a ``processPayment`` (sin la llave): monto y moneda del PEDIDO en el servidor; de la persona,
        solo lo que el pedido ya tiene y la documentación pide."""
        self.ensure_one()
        if not self.partner_email:
            raise ValidationError(self.env._('Falta un correo para el pago: agrégalo en tu dirección.'))
        base = self.provider_id.get_base_url()
        nombre = (self.partner_name or '').strip()
        nombres, _sep, apellidos = nombre.partition(' ')
        nombres = nombres or 'Cliente'
        apellidos = apellidos.strip() or nombres
        pais = (self.partner_country_id.code or 'PA').upper()
        estado = self.partner_state_id.code
        direccion = (self.partner_address or '').strip() or self.partner_city or 'Panamá'
        telefono = re.sub(r'\D', '', self.partner_phone or '') or '00000000'
        datos = {
            'redirect': urljoin(base, RUTA_RETORNO),
            'amount': float_repr(float_round(self.amount, precision_digits=2), 2),
            'currency': self.currency_id.name,
            'orderNumber': orden,
            'capture': '1',
            'billToFirstName': nombres[:60],
            'billToLastName': apellidos[:60],
            'billToAddress': direccion[:100],
            'billToAddress2': (self.partner_city or 'Panamá')[:100],
            'billToCity': (self.partner_city or 'Panamá')[:60],
            'billToState': f'{pais}-{estado}' if estado else pais,
            'billToZipPostCode': (self.partner_zip or '0000')[:12],
            'billToCountry': pais,
            'billToTelephone': telefono[:20],
            'billToEmail': self.partner_email,
            'subscription': '0',
            'platform': 'Odoo',
            'returnData': api_tilopay.codificar_return_data(orden),
            'hashVersion': 'V2',
            'token_version': 'v2',
        }
        return datos

    # ------------------------------------------------------------------ confirmar (lo único que paga)

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code != CODIGO:
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get('reference')

    def _extract_amount_data(self, payment_data):
        """El marco de Odoo vuelve a comparar monto y moneda: aquí solo para un pago aprobado ya verificado."""
        if self.provider_code != CODIGO:
            return super()._extract_amount_data(payment_data)
        if (isinstance(payment_data, api_tilopay.DatosVerificados)
                and payment_data.get('veredicto') == api_tilopay.APROBADO):
            return {'amount': float(payment_data['monto']), 'currency_code': payment_data['moneda']}
        return None

    def _apply_updates(self, payment_data):
        if self.provider_code != CODIGO:
            return super()._apply_updates(payment_data)
        if not isinstance(payment_data, api_tilopay.DatosVerificados):
            # Defensa: ningún camino que no haya consultado a Tilopay puede mover el estado de un pago.
            _logger.warning('Tilopay: se ignoraron datos que no vienen de una consulta a Tilopay (%s).', self.reference)
            return
        veredicto = payment_data['veredicto']
        anterior = self.dcasa_tilopay_veredicto
        estado_previo = self.state
        valores = {'dcasa_tilopay_veredicto': veredicto}
        if payment_data.get('entorno_visto'):
            valores['dcasa_tilopay_entorno_visto'] = payment_data['entorno_visto']
        self.write(valores)
        detalle = payment_data.get('detalle') or ''
        if veredicto == api_tilopay.APROBADO:
            self.provider_reference = payment_data.get('id_tilopay') or self.dcasa_tilopay_orden
            self._set_done(extra_allowed_states=('cancel', 'error'))
            if estado_previo in ('cancel', 'error'):
                self._dcasa_tilopay_anotar(self.env._(
                    'Tilopay confirmó un pago aprobado que llegó después de marcarse «%(estado)s»: el pedido se tomó '
                    'como pagado.', estado=estado_previo))
            self._dcasa_tilopay_avisar_si_ya_estaba_pagado()
        elif veredicto == api_tilopay.RECHAZADO:
            self._set_error(MENSAJE_ERROR_RECHAZO)
            if anterior != veredicto:
                self._dcasa_tilopay_anotar(self.env._('Tilopay no aprobó el intento de pago: %s', detalle))
        elif veredicto in (api_tilopay.MONTO, api_tilopay.MONEDA):
            self._set_error(MENSAJE_ERROR_DISTINTO)
            if anterior != veredicto:
                self._dcasa_tilopay_anotar(self.env._(
                    'Tilopay dice haber cobrado algo distinto al pedido (%s). NO se tomó como pago: revísalo en el '
                    'panel de Tilopay.', detalle))
        else:  # sin registro, entorno, captura, ambiguo, inválido: no cambia nada
            _logger.warning('Tilopay: la transacción %s sigue como está (%s: %s).', self.reference, veredicto, detalle)
            if veredicto == api_tilopay.SIN_REGISTRO and payment_data.get('navegador_cancelo') \
                    and self.state in ('draft', 'pending'):
                self._set_canceled(MENSAJE_CANCELADO)
            elif veredicto not in (api_tilopay.SIN_REGISTRO, anterior):
                self._dcasa_tilopay_anotar(self.env._(
                    'Tilopay respondió algo que no se pudo tomar como pago (%s): %s. El pedido sigue sin pagar; '
                    'revísalo en el panel de Tilopay.', veredicto, detalle))

    def _dcasa_tilopay_bloquear(self):
        """Bloquea la fila de la transacción mientras se consulta: dos avisos a la vez no la procesan dos veces. Si otra
        petición ya la tiene, devuelve ``False`` (ella se encarga)."""
        self.ensure_one()
        self.flush_recordset()
        self.env.cr.execute('SELECT id FROM payment_transaction WHERE id = %s FOR UPDATE SKIP LOCKED', [self.id])
        if not self.env.cr.fetchone():
            return False
        self.invalidate_recordset()
        return True

    def _dcasa_tilopay_confirmar(self, origen, navegador_cancelo=False):
        """Pregunta a Tilopay por esta transacción y aplica lo que diga. Devuelve el veredicto, o un texto de por qué no
        hizo nada (``ya_pagada``, ``apagado``, ``ocupada``, ``espera``, ``sin_respuesta``). Nunca lanza por culpa de
        Tilopay. ``navegador_cancelo`` es solo una pista (el navegador volvió sin ``code = 1``): jamás paga."""
        self.ensure_one()
        tx = self.sudo()
        proveedor = tx.provider_id
        if proveedor.code != CODIGO or not tx.dcasa_tilopay_orden:
            return None
        if tx.state == 'done':
            return 'ya_pagada'
        if proveedor.state == 'disabled' or not proveedor._dcasa_tilopay_conectado():
            return 'apagado'
        if not tx._dcasa_tilopay_bloquear():
            return 'ocupada'
        if tx.state == 'done':
            return 'ya_pagada'
        ahora = fields.Datetime.now()
        if tx.dcasa_tilopay_consulta and (ahora - tx.dcasa_tilopay_consulta).total_seconds() < ESPERA_ENTRE_CONSULTAS:
            return 'espera'
        tx.dcasa_tilopay_consulta = ahora
        try:
            cuerpo = proveedor._dcasa_tilopay_cliente().consultar(tx.dcasa_tilopay_orden)
        except api_tilopay.ErrorTilopay as error:
            _logger.warning('Tilopay (%s): no se pudo consultar la transacción %s: %s', origen, tx.reference, error)
            return 'sin_respuesta'
        monto = Decimal(float_repr(float_round(tx.amount, precision_digits=2), 2))
        datos = api_tilopay.evaluar_consulta(
            cuerpo, tx.dcasa_tilopay_orden, monto, tx.currency_id.name, proveedor._dcasa_tilopay_entorno())
        datos = tx._dcasa_tilopay_coherente_con_su_modo(datos)
        datos['reference'] = tx.reference
        datos['navegador_cancelo'] = bool(navegador_cancelo)
        tx._process(CODIGO, datos)
        _logger.info('Tilopay (%s): transacción %s → %s.', origen, tx.reference, datos['veredicto'])
        if datos['veredicto'] == api_tilopay.APROBADO:
            tx._dcasa_tilopay_adelantar_el_cierre()
        return datos['veredicto']

    def _dcasa_tilopay_coherente_con_su_modo(self, datos):
        """Un pago aprobado solo vale si el modo en que Tilopay dice que ocurrió es el mismo en que se CREÓ la
        transacción (``is_live``: «Habilitado» en Odoo = real). Si alguien cambia de modo con pagos a medias, no se
        mezclan."""
        self.ensure_one()
        if datos['veredicto'] != api_tilopay.APROBADO:
            return datos
        if self.is_live != (datos.get('entorno_visto') == api_tilopay.PRODUCCION):
            return api_tilopay.DatosVerificados(
                veredicto=api_tilopay.ENTORNO, orden=datos['orden'], entorno_visto=datos.get('entorno_visto'),
                detalle='la transacción se creó en otro modo que el del pago (prueba o real)')
        return datos

    def _dcasa_tilopay_adelantar_el_cierre(self):
        """Pide que la tarea de Odoo que termina los pagos (confirmar el pedido, el cobro) corra enseguida y no dentro
        de 10 minutos: el cliente puede no estar mirando. Si no se puede, igual corre en su hora."""
        try:
            with self.env.cr.savepoint():
                cron = self.env.ref('payment.cron_post_process_payment_tx', raise_if_not_found=False)
                if cron:
                    cron.sudo()._trigger()
        except Exception:  # noqa: BLE001
            _logger.warning('Tilopay: no se pudo adelantar el cierre de %s (corre a su hora).', self.reference)

    def _dcasa_tilopay_avisar_si_ya_estaba_pagado(self):
        """Si el cliente abrió dos páginas de pago y pagó las dos, los dos pagos son dinero real y los dos se aceptan;
        pero el equipo tiene que saber que a uno hay que devolverle el dinero (se hace en el panel de Tilopay)."""
        for pedido in self.sudo().sale_order_ids:
            otros = pedido.transaction_ids.filtered(lambda t: t != self and t.state == 'done')
            ya_pagado = sum(otros.mapped('amount'))
            if otros and pedido.currency_id.compare_amounts(ya_pagado, pedido.amount_total) >= 0:
                self._dcasa_tilopay_anotar(self.env._(
                    'Este pedido ya estaba pagado y Tilopay confirmó otro pago completo (%(ref)s): hay que devolverle '
                    'uno al cliente desde el panel de Tilopay.', ref=self.reference))
                return

    def _dcasa_tilopay_anotar(self, texto):
        """Una nota interna (solo el equipo) en los pedidos de esta transacción. Nunca hace fallar un pago."""
        try:
            with self.env.cr.savepoint():
                robot = self.env['res.users'].sudo().browse(SUPERUSER_ID).partner_id
                cuerpo = Markup('<p>%s</p>') % texto   # ``%`` escapa: un texto de afuera nunca es HTML
                for pedido in self.sudo().sale_order_ids:
                    pedido.message_post(body=cuerpo, author_id=robot.id, subtype_xmlid='mail.mt_note')
        except Exception:  # noqa: BLE001 - una nota que no sale no debe tumbar la confirmación
            _logger.exception('Tilopay: no se pudo dejar la nota en el pedido de %s.', self.reference)

    @api.model
    def _dcasa_tilopay_buscar(self, orden):
        """La transacción de Tilopay con esa orden (la nuestra), o vacío. Igualdad exacta, sin armar SQL con texto."""
        orden = api_tilopay.orden_valida(orden)
        if not orden:
            return self.browse()
        return self.sudo().search([('dcasa_tilopay_orden', '=', orden), ('provider_id.code', '=', CODIGO)], limit=1)

    # ------------------------------------------------------------------ la tarea programada

    @api.model
    def _cron_dcasa_tilopay_reconciliar(self, limite=LOTE_DEL_CRON):
        """Pregunta por los pagos de Tilopay que quedaron sin confirmar (el aviso de compras no se reintenta y el
        cliente puede cerrar la pestaña). Los de más de 24 horas sin pago pasan a vencidos. Devuelve cuántos revisó.
        Sin proveedor activo y con claves, no hace nada (y no llama a nadie)."""
        proveedores = self.env['payment.provider'].sudo().search([('code', '=', CODIGO), ('state', '!=', 'disabled')])
        proveedores = proveedores.filtered(lambda p: p._dcasa_tilopay_conectado())
        if not proveedores:
            return 0
        ahora = fields.Datetime.now()
        pendientes = self.sudo().search([
            ('provider_id', 'in', proveedores.ids), ('dcasa_tilopay_orden', '!=', False),
            ('state', 'in', ('draft', 'pending')),
            ('create_date', '>=', ahora - VENTANA_DEL_CRON), ('create_date', '<=', ahora - MINIMO_PARA_EL_CRON),
        ], order='dcasa_tilopay_consulta asc nulls first, id', limit=limite)
        revisadas = 0
        sin_pago = (api_tilopay.SIN_REGISTRO, api_tilopay.RECHAZADO)
        for pendiente in pendientes:
            tx = pendiente.with_prefetch()
            try:
                with self.env.cr.savepoint():
                    veredicto = tx._dcasa_tilopay_confirmar('cron')
                    vencida = tx.create_date <= ahora - VIDA_DE_UN_INTENTO
                    if tx.state in ('draft', 'pending') and veredicto in sin_pago and vencida:
                        tx._set_canceled(MENSAJE_VENCIDO)
                revisadas += 1
                if not modules.module.current_test:   # una prueba no puede confirmar la base
                    self.env.cr.commit()
            except psycopg2.OperationalError:
                if not modules.module.current_test:
                    self.env.cr.rollback()
            except Exception:  # noqa: BLE001 - un pago con problemas no detiene a los demás (el savepoint ya deshizo lo suyo)
                _logger.exception('Tilopay: error al revisar la transacción %s.', tx.reference)
        return revisadas
