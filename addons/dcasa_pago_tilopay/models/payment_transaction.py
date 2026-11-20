"""La transacción de Tilopay: crear la página de pago, y confirmar SOLO preguntándole a Tilopay.

Qué cuenta como «pagado» (docs/TILOPAY.md §4 y §5):

* Nada que llegue por el navegador (el retorno) ni por un aviso decide un pago. Sirven para saber QUÉ orden revisar.
* ``_dcasa_tilopay_confirmar`` bloquea la transacción, consulta a Tilopay con la orden QUE GUARDAMOS, y
  ``tilopay_api.evaluar_consulta`` compara orden, monto, moneda, aprobación y entorno. Solo entonces ``_set_done``.
* ``_apply_updates`` solo acepta ``DatosVerificados`` (lo que sale de esa evaluación).
* Una falla de Tilopay o de la red deja la transacción como estaba (nunca «pagada») y no tumba nada.
* El dinero que entra y no cuadra con el pedido (el total cambió mientras el cliente pagaba, el pedido ya estaba
  cancelado, o el pago fue de prueba) nunca pasa en silencio: queda en el pedido una nota y, cuando hay que actuar, una
  actividad para Gerencia.
"""
import hashlib
import hmac
import logging
import re
import secrets
import time
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import psycopg2
from markupsafe import Markup

from odoo import SUPERUSER_ID, api, fields, models, modules
from odoo.addons.dcasa_base.red import llave_ip
from odoo.exceptions import ValidationError
from odoo.http import request
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
# Cada página de pago es una llamada a ``processPayment`` en la cuenta de Tilopay: un tope global por hora (un límite
# técnico para que nadie llene la cuenta con páginas basura; muy por encima de lo que vende la tienda).
TOPE_PAGINAS_POR_HORA = 300
# …y un tope por conexión (una huella de la dirección, no la dirección) para que UNA sola fuente no llene el global y
# deje a todos sin Tilopay esa hora. No cuenta a las personas del equipo ni las páginas que ya se pagaron.
TOPE_PAGINAS_POR_CONEXION_HORA = 30
# A quién se le pregunta cuándo (la tarea corre cada 10 minutos): lo reciente, seguido; lo viejo sin novedad, cada hora;
# lo rechazado o cancelado (por si el cliente pagó después en la misma página), cada 3 horas.
EDAD_DE_LO_RECIENTE = timedelta(hours=1)
ESPERA_DE_LO_RECIENTE = timedelta(minutes=8)
ESPERA_DE_LO_VIEJO = timedelta(hours=1)                # lo que Tilopay SÍ conoce (tiene una fila de esa orden)
ESPERA_DE_LO_VIEJO_SIN_REGISTRO = timedelta(hours=3)   # lo que Tilopay nunca ha visto: un carrito abandonado
ESPERA_DE_LO_CERRADO = timedelta(hours=3)
# Una transacción a la que Tilopay nunca le vio ni una fila (nadie llegó a pagar) deja de preguntarse pasado este rato;
# si después llega un retorno o un aviso de esa orden (señal de vida), vuelve a preguntarse sola.
VIDA_DE_LO_SIN_REGISTRO = timedelta(hours=24)
# La tarea programada comparte el único hilo de tareas con las demás (entre ellas la que termina los pagos de Odoo): se
# queda corta a propósito. Y si Tilopay está lento, una consulta más puede tardar hasta 15 s.
PRESUPUESTO_DEL_CRON = 40
# Las rutas web (retorno, aviso, estado) solo consultan lo reciente; lo viejo lo deja a la tarea, que va en orden.
VENTANA_DE_LAS_RUTAS = timedelta(hours=3)
ORIGENES_WEB = ('retorno', 'aviso', 'estado')
SEGUNDOS_ENTRE_SENALES = 60
# Una fila de Tilopay con un estado que el código no entiende, sin resolverse pasada esta edad, se le cuenta a Gerencia.
EDAD_PARA_AVISAR_UN_ESTADO_RARO = timedelta(hours=1)
FALLAS_SEGUIDAS_PARA_PARAR = 3                # si Tilopay no contesta tres veces seguidas, se deja para la próxima

MENSAJE_ERROR_RECHAZO = ('Tilopay no pudo aprobar este pago. Puedes intentarlo de nuevo con otra tarjeta o elegir otra '
                         'forma de pago.')
MENSAJE_ERROR_DISTINTO = ('Tilopay reportó un cobro distinto al de tu pedido, así que no lo tomamos como pago. Nuestro '
                          'equipo lo revisa; escríbenos por WhatsApp si necesitas ayuda.')
MENSAJE_CANCELADO = ('El pago no se completó. Tu pedido sigue guardado: puedes intentarlo de nuevo o elegir otra forma '
                     'de pago.')
MENSAJE_VENCIDO = 'Este intento de pago venció sin recibirse el pago. Puedes intentarlo de nuevo.'
ESTADOS_DEL_PEDIDO = {'cancel': 'cancelado', 'draft': 'cotización', 'sent': 'cotización enviada', 'sale': 'confirmado'}
MENSAJE_ERROR_TOTAL = ('Tu pedido cambió mientras pagabas, así que no tomamos ese cobro como el pago. Nuestro equipo '
                       'lo revisa y te escribe; también puedes escribirnos por WhatsApp.')


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    dcasa_tilopay_orden = fields.Char(
        'Orden en Tilopay', readonly=True, copy=False, index='btree_not_null',
        help='El número de orden que se mandó a Tilopay (único para siempre en su cuenta). Se guarda ANTES de pedir la '
             'página de pago y es la única orden con la que se busca y se consulta.')
    dcasa_tilopay_consulta = fields.Datetime('Última consulta a Tilopay', readonly=True, copy=False)
    dcasa_tilopay_entorno_visto = fields.Char('Entorno que dijo Tilopay', readonly=True, copy=False)
    dcasa_tilopay_veredicto = fields.Char('Última respuesta de Tilopay', readonly=True, copy=False)
    dcasa_tilopay_senal = fields.Datetime(
        'Último retorno o aviso', readonly=True, copy=False,
        help='Cuándo llegó por última vez un retorno del cliente o un aviso de Tilopay con la orden de esta '
             'transacción (señal de que alguien llegó a pagar). La tarea programada pregunta primero por estas.')
    dcasa_tilopay_huella = fields.Char(
        'Conexión (huella)', readonly=True, copy=False, index='btree_not_null',
        help='Huella (no la dirección) de la conexión desde la que se abrió la página de pago: sirve para el tope por '
             'conexión. No se puede volver a la dirección sin el secreto de la base.')
    dcasa_tilopay_revision = fields.Boolean(
        'Necesita que una persona la revise', readonly=True, copy=False, index='btree_not_null',
        help='Tilopay cobró y el pedido ya no valía eso: NO se paga sola ni aunque el pedido vuelva a valer lo cobrado '
             '(puede que el equipo ya haya devuelto el cobro en el panel de Tilopay). Se resuelve a mano.')

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
            if error.tipo == 'ocupado':
                raise ValidationError(self.env._(
                    'Hay muchos pagos en curso en este momento. Intenta de nuevo en unos minutos o elige otra forma '
                    'de pago.')) from None
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
        proveedor = self.provider_id
        if not proveedor._dcasa_tilopay_ofrecible():
            raise ValidationError(self.env._(
                'Tilopay no está disponible ahora. Elige otra forma de pago o escríbenos por WhatsApp.'))
        interno = self.env.user._is_internal()
        solo_para_el_equipo = not proveedor.is_published or (
            proveedor.state == 'test' and api_tilopay.servidor_es_produccion())
        if solo_para_el_equipo and not interno:
            # Lo mismo que hace Odoo al MOSTRAR los proveedores: uno sin publicar (p. ej. en «Modo de prueba», para que
            # lo pruebe el equipo) es solo de personas internas. Sin esto, un visitante lo abre mandando el número del
            # proveedor a mano y paga un pedido real con una tarjeta de prueba. Y en el servidor de PRODUCCIÓN el «Modo
            # de prueba» es del equipo aunque se pulse «Publicado» por error (la guía lo prohíbe; el código, también).
            raise ValidationError(self.env._(
                'Tilopay no está disponible ahora. Elige otra forma de pago o escríbenos por WhatsApp.'))
        if self.currency_id.name != 'USD':
            raise ValidationError(self.env._('Tilopay solo cobra en dólares (USD).'))
        pedidos = self.sale_order_ids
        if pedidos.filtered(lambda pedido: pedido.state == 'cancel'):
            raise ValidationError(self.env._(
                'Este pedido ya no está vigente (se canceló), así que no se puede pagar. Escríbenos por WhatsApp y te '
                'ayudamos.'))
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
        hace_una_hora = fields.Datetime.now() - timedelta(hours=1)
        huella = self._dcasa_tilopay_huella_de_la_conexion()
        if huella and not interno and self.sudo().search_count([
                ('provider_id', '=', proveedor.id), ('dcasa_tilopay_huella', '=', huella), ('state', '!=', 'done'),
                ('dcasa_tilopay_orden', '!=', False), ('create_date', '>=', hace_una_hora)]) \
                >= TOPE_PAGINAS_POR_CONEXION_HORA:
            raise ValidationError(self.env._(
                'Has abierto varios intentos de pago seguidos desde esta conexión. Espera un rato o elige otra forma '
                'de pago.'))
        en_la_hora = self.sudo().search_count([
            ('provider_id', '=', proveedor.id), ('dcasa_tilopay_orden', '!=', False), ('state', '!=', 'done'),
            ('create_date', '>=', hace_una_hora)])
        if en_la_hora >= TOPE_PAGINAS_POR_HORA:
            _logger.warning('Tilopay: tope de %s páginas de pago por hora alcanzado.', TOPE_PAGINAS_POR_HORA)
            raise ValidationError(self.env._(
                'Hay muchos pagos en curso en este momento. Intenta de nuevo en unos minutos o elige otra forma de '
                'pago.'))

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
        huella = self._dcasa_tilopay_huella_de_la_conexion()
        if huella:
            self.sudo().dcasa_tilopay_huella = huella
        return orden

    @api.model
    def _dcasa_tilopay_huella_de_la_conexion(self):
        """Una huella (HMAC con el secreto de la base) de la conexión que pide la página de pago, o ``False`` si no hay
        petición web (una tarea, una prueba) o la base no tiene secreto. No se guarda la dirección."""
        try:
            direccion = request.httprequest.remote_addr
        except (RuntimeError, AttributeError):
            return False
        secreto = self.env['ir.config_parameter'].sudo().get_param('database.secret') or ''
        if not direccion or not secreto:
            return False
        mensaje = f'tilopay-conexion:{llave_ip(direccion)}'.encode()
        return hmac.new(secreto.encode(), mensaje, hashlib.sha256).hexdigest()[:24]

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
            self._dcasa_tilopay_aplicar_aprobado(payment_data, estado_previo)
        elif veredicto == api_tilopay.RECHAZADO:
            self._dcasa_tilopay_cerrar_con_error(
                MENSAJE_ERROR_RECHAZO, anterior, veredicto,
                self.env._('Tilopay no aprobó el intento de pago: %s', detalle))
        elif veredicto in (api_tilopay.MONTO, api_tilopay.MONEDA):
            self._dcasa_tilopay_cerrar_con_error(
                MENSAJE_ERROR_DISTINTO, anterior, veredicto, self.env._(
                    'Tilopay dice haber cobrado algo distinto al pedido (%s). NO se tomó como pago: revísalo en el '
                    'panel de Tilopay.', detalle))
        elif veredicto == api_tilopay.TOTAL_PEDIDO:
            self._dcasa_tilopay_aplicar_total_distinto(anterior, detalle)
        else:  # sin registro, pendiente, entorno, captura, ambiguo, inválido: no cambia nada
            self._dcasa_tilopay_aplicar_sin_cambio(payment_data, anterior)

    def _dcasa_tilopay_aplicar_aprobado(self, payment_data, estado_previo):
        self.provider_reference = payment_data.get('id_tilopay') or self.dcasa_tilopay_orden
        self._set_done(extra_allowed_states=('cancel', 'error'))
        if estado_previo in ('cancel', 'error'):
            self._dcasa_tilopay_anotar(self.env._(
                'Tilopay confirmó un pago aprobado que llegó después de marcarse «%(estado)s»: el pedido se tomó '
                'como pagado.', estado=estado_previo))
        self._dcasa_tilopay_avisar_si_ya_estaba_pagado()
        self._dcasa_tilopay_avisos_tras_el_pago()

    def _dcasa_tilopay_cerrar_con_error(self, mensaje, anterior, veredicto, nota):
        """Una transacción abierta pasa a «error» con ``mensaje`` (lo que lee el cliente). La nota para el equipo sale
        solo la primera vez que aparece ese veredicto (la tarea programada vuelve a preguntar y no debe repetirla)."""
        if self.state in ('draft', 'pending'):
            self._set_error(mensaje)
        if anterior != veredicto:
            self._dcasa_tilopay_anotar(nota)

    def _dcasa_tilopay_aplicar_total_distinto(self, anterior, detalle):
        """Aprobado y por el monto de la transacción, pero el pedido ya no vale eso: el dinero ENTRÓ y no se toma como
        pago de este pedido. No se queda pendiente (el cliente vería «esperando» para siempre): error con un mensaje
        claro, y aviso a Gerencia para devolver o ajustar. Si el total vuelve a coincidir, una consulta posterior sí lo
        da por pagado."""
        if self.state in ('draft', 'pending'):
            self._set_error(MENSAJE_ERROR_TOTAL)
        self.dcasa_tilopay_revision = True
        if anterior != api_tilopay.TOTAL_PEDIDO:
            self._dcasa_tilopay_alertar(
                self.env._(
                    'Tilopay cobró %(monto)s %(moneda)s (%(ref)s) y el pedido cambió mientras el cliente pagaba: '
                    '%(detalle)s. El dinero entró y NO se tomó como pago del pedido, y no se va a pagar solo aunque '
                    'el pedido vuelva a valer lo cobrado. Habla con el cliente: o se devuelve el cobro desde el panel '
                    'de Tilopay, o, si te quedas con el pago, ajustas el pedido al monto cobrado y lo registras a '
                    'mano como pago en el diario Tilopay.', monto=float_repr(self.amount, 2),
                    moneda=self.currency_id.name, ref=self.reference, detalle=detalle),
                self.env._('Tilopay: cobro que no cuadra con el pedido'))

    def _dcasa_tilopay_alertar_estado_raro(self, detalle):
        """Una fila de Tilopay con un estado que el código no entiende y que no se resuelve: si ese estado resultara ser
        el de un pago aprobado, el dinero entró y nadie se enteraría. Nota y actividad para Gerencia, una sola vez por
        transacción (el resumen lleva la referencia)."""
        self._dcasa_tilopay_alertar(
            self.env._(
                'Tilopay tiene un movimiento de la transacción %(ref)s con un estado que el sistema no entiende '
                '(%(detalle)s) y no se ha resuelto. Si el cliente pagó, el dinero pudo entrar sin que nadie lo '
                'confirmara: revísala en el panel de Tilopay.', ref=self.reference, detalle=detalle),
            self.env._('Tilopay: estado que no se entiende (%s)', self.reference), una_vez=True)

    def _dcasa_tilopay_aplicar_sin_cambio(self, payment_data, anterior):
        veredicto, detalle = payment_data['veredicto'], payment_data.get('detalle') or ''
        _logger.warning('Tilopay: la transacción %s sigue como está (%s: %s).', self.reference, veredicto, detalle)
        edad = fields.Datetime.now() - self.create_date
        if veredicto == api_tilopay.PENDIENTE and edad >= EDAD_PARA_AVISAR_UN_ESTADO_RARO:
            self._dcasa_tilopay_alertar_estado_raro(detalle)
        if veredicto == api_tilopay.SIN_REGISTRO and payment_data.get('navegador_cancelo') \
                and self.state in ('draft', 'pending'):
            self._set_canceled(MENSAJE_CANCELADO)
        elif veredicto not in (api_tilopay.SIN_REGISTRO, api_tilopay.PENDIENTE, anterior):
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
        hizo nada: ``ya_pagada``, ``apagado``, ``ocupada`` (otra petición la tiene), ``vieja`` (las rutas web solo
        consultan lo reciente; la tarea se encarga), ``saturada`` (ya hay demasiadas llamadas a Tilopay a la vez),
        ``espera`` (se preguntó hace menos de 5 s), ``sin_respuesta``. Nunca lanza por culpa de Tilopay.
        ``navegador_cancelo`` es solo una pista (el navegador volvió sin ``code = 1``): jamás paga.

        Nada de lo que llegue por la web puede agotar las conexiones de la base: cada llamada a Tilopay retiene una
        (hasta 15 s si Tilopay está lento), así que hay un tope global de llamadas a la vez (``api_tilopay.cupo``) y las
        rutas web solo consultan transacciones recientes."""
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
        prioritario = origen == 'cron'
        if origen in ORIGENES_WEB:
            tx._dcasa_tilopay_marcar_senal(ahora)         # la tarea preguntará primero por las que tienen señal
            if tx.create_date < ahora - VENTANA_DE_LAS_RUTAS:
                return 'vieja'
        if not api_tilopay.hay_cupo(prioritario):
            return 'saturada'
        consulta_anterior = tx.dcasa_tilopay_consulta
        if consulta_anterior and (ahora - consulta_anterior).total_seconds() < ESPERA_ENTRE_CONSULTAS:
            return 'espera'
        tx.dcasa_tilopay_consulta = ahora
        try:
            cuerpo = proveedor._dcasa_tilopay_cliente(prioritario).consultar(tx.dcasa_tilopay_orden)
        except api_tilopay.ErrorTilopay as error:
            if error.tipo == 'ocupado':
                tx.dcasa_tilopay_consulta = consulta_anterior       # no se preguntó: no cuenta como pregunta
                return 'saturada'
            _logger.warning('Tilopay (%s): no se pudo consultar la transacción %s: %s', origen, tx.reference, error)
            return 'sin_respuesta'
        monto = Decimal(float_repr(float_round(tx.amount, precision_digits=2), 2))
        datos = api_tilopay.evaluar_consulta(
            cuerpo, tx.dcasa_tilopay_orden, monto, tx.currency_id.name, proveedor._dcasa_tilopay_entorno())
        datos = tx._dcasa_tilopay_coherente_con_su_modo(datos)
        datos = tx._dcasa_tilopay_coherente_con_el_pedido(datos)
        datos['reference'] = tx.reference
        datos['navegador_cancelo'] = bool(navegador_cancelo)
        tx._process(CODIGO, datos)
        _logger.info('Tilopay (%s): transacción %s → %s.', origen, tx.reference, datos['veredicto'])
        if datos['veredicto'] == api_tilopay.APROBADO:
            tx._dcasa_tilopay_adelantar_el_cierre()
        return datos['veredicto']

    def _dcasa_tilopay_marcar_senal(self, ahora):
        """Anota que llegó un retorno o un aviso de esta orden (a lo más una vez por minuto). La fila ya está bloqueada
        por esta petición, así que escribirla no hace esperar a nadie."""
        self.ensure_one()
        if not self.dcasa_tilopay_senal or (ahora - self.dcasa_tilopay_senal).total_seconds() >= SEGUNDOS_ENTRE_SENALES:
            self.dcasa_tilopay_senal = ahora

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

    def _dcasa_tilopay_total_del_pedido(self):
        """``(coincide, detalle)``: ¿el pedido vale ahora lo mismo que se cobró? La página de pago se abre con el total
        del pedido de ese momento, pero la transacción en «borrador» deja el carrito editable: otra pestaña o la
        vendedora pueden cambiarlo antes de que el cliente pague. Se compara con el pedido de AHORA, no con lo que se
        guardó al abrir."""
        self.ensure_one()
        pedidos = self.sudo().sale_order_ids
        moneda = self.currency_id
        if len(pedidos) != 1:
            return False, self.env._('la transacción no está ligada a un solo pedido')
        if pedidos.currency_id != moneda:
            return False, self.env._('el pedido %s ya está en otra moneda', pedidos.name)
        if moneda.compare_amounts(self.amount, pedidos.amount_total) != 0:
            return False, self.env._(
                'el pedido %(pedido)s ahora vale %(total)s %(moneda)s', pedido=pedidos.name,
                total=float_repr(pedidos.amount_total, 2), moneda=moneda.name)
        return True, ''

    def _dcasa_tilopay_coherente_con_el_pedido(self, datos):
        """Un pago aprobado solo se da por pagado si el pedido sigue valiendo lo que se cobró. Si no, el veredicto
        pasa a ``TOTAL_PEDIDO``: no se paga, y el equipo se entera de que el dinero entró."""
        self.ensure_one()
        if datos['veredicto'] != api_tilopay.APROBADO:
            return datos
        coincide, detalle = self._dcasa_tilopay_total_del_pedido()
        if coincide and self.dcasa_tilopay_revision:
            # Ya se avisó que el pedido cambió y el cobro entró: aunque el pedido vuelva a valer lo cobrado, NO se paga
            # solo (el equipo pudo devolver el cobro en el panel de Tilopay y que la consulta no lo muestre aparte).
            coincide, detalle = False, self.env._(
                'este cobro ya se marcó para revisión de una persona: no se paga solo')
        if coincide:
            return datos
        return api_tilopay.DatosVerificados(
            veredicto=api_tilopay.TOTAL_PEDIDO, orden=datos['orden'], entorno_visto=datos.get('entorno_visto'),
            detalle=detalle)

    def _check_amount_and_confirm_order(self):
        """Override de ``sale``: la última puerta antes de confirmar un pedido pagado con Tilopay. Aunque la consulta
        ya comparó el total, entre ese momento y esta tarea el pedido pudo cambiar otra vez: si ya no vale lo cobrado,
        no se confirma solo (el dinero entró; Gerencia se entera). Después de confirmar, un pedido pagado completo deja
        de ser un «apartado» (la tienda lo marca así cuando confirma sola)."""
        tilopay = self.filtered(lambda tx: tx.provider_code == CODIGO)
        distintas = self.browse()
        for tx in tilopay:
            coincide, detalle = tx._dcasa_tilopay_total_del_pedido()
            if not coincide:
                distintas |= tx
                tx._dcasa_tilopay_alertar(
                    self.env._(
                        'Tilopay cobró %(monto)s %(moneda)s (%(ref)s), pero %(detalle)s. El pedido NO se confirmó '
                        'solo: habla con el cliente y devuelve el cobro desde el panel de Tilopay o ajusta el '
                        'pedido.', monto=float_repr(tx.amount, 2), moneda=tx.currency_id.name, ref=tx.reference,
                        detalle=detalle),
                    self.env._('Tilopay: cobro que no cuadra con el pedido'))
        confirmados = super(PaymentTransaction, self - distintas)._check_amount_and_confirm_order()
        for tx in tilopay - distintas:
            tx._dcasa_tilopay_soltar_el_apartado()
        return confirmados

    def _dcasa_tilopay_soltar_el_apartado(self):
        """Un pedido de la web cobrado completo ya no es un apartado por vencer (``website_dcasa``). Si ese módulo no
        está, no hay nada que soltar."""
        self.ensure_one()
        if self.state != 'done':
            return
        for pedido in self.sudo().sale_order_ids:
            if 'dcasa_apartado_vence' in pedido._fields and pedido.dcasa_apartado_vence \
                    and pedido.currency_id.compare_amounts(self.amount, pedido.amount_total) >= 0:
                pedido.dcasa_apartado_vence = False

    def _dcasa_tilopay_avisos_tras_el_pago(self):
        """Lo que el equipo tiene que saber de un pago aprobado, además de que entró: si el pedido ya no está vivo, o si
        fue una tarjeta de PRUEBA (el pedido se confirma igual y quien prepara la entrega no lo puede adivinar)."""
        self.ensure_one()
        for pedido in self.sudo().sale_order_ids:
            if pedido.state not in ('draft', 'sent', 'sale'):
                self._dcasa_tilopay_alertar(
                    self.env._(
                        'Tilopay cobró %(monto)s %(moneda)s (%(ref)s) de un pedido que está «%(estado)s»: el dinero '
                        'entró y el pedido no se va a confirmar solo. O se devuelve el cobro desde el panel de '
                        'Tilopay, o se reabre el pedido.', monto=float_repr(self.amount, 2),
                        moneda=self.currency_id.name, ref=self.reference,
                        estado=ESTADOS_DEL_PEDIDO.get(pedido.state, pedido.state)),
                    self.env._('Tilopay: cobro de un pedido que ya no está vivo'))
        if not self.is_live:
            self._dcasa_tilopay_anotar(self.env._(
                'Pagado con una tarjeta de PRUEBA en el modo de prueba de Tilopay: no entró dinero real, aunque el '
                'pedido se confirmó. Revísalo antes de preparar la entrega.'))

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

    def _dcasa_tilopay_destinatarios(self):
        """A quién se le avisa de un cobro que no cuadra: Gerencia; si nadie la tiene, quien administra el sistema. Solo
        personas internas y activas."""
        Usuarios = self.env['res.users'].sudo()
        internos = [('share', '=', False), ('active', '=', True)]
        for xmlid in ('dcasa_base.group_gerencia', 'base.group_system'):
            grupo = self.env.ref(xmlid, raise_if_not_found=False)
            if grupo:
                usuarios = Usuarios.search(internos + [('all_group_ids', 'in', grupo.ids)])
                if usuarios:
                    return usuarios
        return Usuarios

    def _dcasa_tilopay_alertar(self, texto, resumen, una_vez=False):
        """Una nota interna en el pedido Y una actividad para Gerencia: para un cobro del que alguien tiene que ocuparse
        (el dinero entró). No repite la actividad si ya hay una igual abierta; con ``una_vez``, tampoco la nota. Nunca
        hace fallar un pago."""
        if una_vez and self.env['mail.activity'].sudo().search_count([
                ('res_model', '=', 'sale.order'), ('res_id', 'in', self.sudo().sale_order_ids.ids),
                ('summary', '=', resumen)], limit=1):
            return
        self._dcasa_tilopay_anotar(texto)
        try:
            with self.env.cr.savepoint():
                destinos = self._dcasa_tilopay_destinatarios()
                Actividad = self.env['mail.activity'].sudo()
                for pedido in self.sudo().sale_order_ids:
                    for usuario in destinos:
                        if Actividad.search_count([
                                ('res_model', '=', 'sale.order'), ('res_id', '=', pedido.id),
                                ('user_id', '=', usuario.id), ('summary', '=', resumen)], limit=1):
                            continue
                        pedido.activity_schedule(
                            'mail.mail_activity_data_todo', summary=resumen, note=Markup('<p>%s</p>') % texto,
                            user_id=usuario.id)
        except Exception:  # noqa: BLE001 - un aviso que no sale no debe tumbar la confirmación
            _logger.exception('Tilopay: no se pudo dejar la actividad para Gerencia (%s).', self.reference)

    @api.model
    def _dcasa_tilopay_buscar(self, orden):
        """La transacción de Tilopay con esa orden (la nuestra), o vacío. Igualdad exacta, sin armar SQL con texto."""
        orden = api_tilopay.orden_valida(orden)
        if not orden:
            return self.browse()
        return self.sudo().search([('dcasa_tilopay_orden', '=', orden), ('provider_id.code', '=', CODIGO)], limit=1)

    # ------------------------------------------------------------------ la tarea programada

    @api.model
    def _dcasa_tilopay_pendientes(self, proveedores, ahora, excluidas, limite):
        """Las transacciones de Tilopay a las que toca preguntarles, en este orden:

        1. Las que tienen **señal de vida** (llegó un retorno o un aviso con su orden desde la última consulta): alguien
           llegó a pagar. Van primero, sin esperar a su reloj.
        2. Las demás, la que lleva MÁS tiempo sin respuesta primero (``coalesce(última consulta, creación)``): lo nuevo
           no se cuela delante de lo que ya esperaba.

        A qué ritmo (siempre de los últimos 3 días, y sin las que acaban de nacer):

        * Sin confirmar (borrador o pendiente), de menos de una hora: cada 8 minutos.
        * Sin confirmar, de más de una hora: cada hora si Tilopay ya tiene una fila de esa orden; cada 3 horas si nunca
          ha visto nada de ella (casi siempre un carrito abandonado).
        * Con error o canceladas: cada 3 horas (el cliente pudo pagar después, en la misma página); pero si Tilopay
          nunca vio nada de esa orden, solo durante el primer día.
        * Nunca las que esperan a una persona (``dcasa_tilopay_revision``).
        """
        self.env['payment.transaction'].flush_model()
        self.env.cr.execute("""
            SELECT id FROM (
                SELECT id, state, create_date, dcasa_tilopay_consulta,
                       COALESCE(dcasa_tilopay_veredicto, 'sin_registro') = 'sin_registro' AS sin_registro,
                       (dcasa_tilopay_senal IS NOT NULL AND (dcasa_tilopay_consulta IS NULL
                            OR dcasa_tilopay_senal > dcasa_tilopay_consulta)) AS con_senal
                  FROM payment_transaction
                 WHERE provider_id IN %(proveedores)s
                   AND dcasa_tilopay_orden IS NOT NULL
                   AND NOT COALESCE(dcasa_tilopay_revision, FALSE)
                   AND id <> ALL(%(excluidas)s::int[])
                   AND create_date >= %(desde)s
            ) t
             WHERE (con_senal AND state IN ('draft', 'pending', 'error', 'cancel'))
                OR (create_date <= %(hasta)s AND (
                    (state IN ('draft', 'pending') AND (
                        dcasa_tilopay_consulta IS NULL
                        OR dcasa_tilopay_consulta <= CASE
                            WHEN create_date >= %(reciente)s THEN %(corte_reciente)s
                            WHEN sin_registro THEN %(corte_viejo_sin_registro)s
                            ELSE %(corte_viejo)s END))
                    OR (state IN ('error', 'cancel')
                        AND (NOT sin_registro OR create_date >= %(un_dia)s)
                        AND (dcasa_tilopay_consulta IS NULL OR dcasa_tilopay_consulta <= %(corte_cerrado)s))))
             ORDER BY (NOT con_senal), COALESCE(dcasa_tilopay_consulta, create_date), id
             LIMIT %(limite)s""", {
            'proveedores': tuple(proveedores.ids), 'excluidas': list(excluidas),
            'desde': ahora - VENTANA_DEL_CRON, 'hasta': ahora - MINIMO_PARA_EL_CRON,
            'reciente': ahora - EDAD_DE_LO_RECIENTE, 'corte_reciente': ahora - ESPERA_DE_LO_RECIENTE,
            'corte_viejo': ahora - ESPERA_DE_LO_VIEJO,
            'corte_viejo_sin_registro': ahora - ESPERA_DE_LO_VIEJO_SIN_REGISTRO,
            'corte_cerrado': ahora - ESPERA_DE_LO_CERRADO, 'un_dia': ahora - VIDA_DE_LO_SIN_REGISTRO,
            'limite': limite})
        return self.sudo().browse([fila[0] for fila in self.env.cr.fetchall()])

    @api.model
    def _cron_dcasa_tilopay_reconciliar(self, limite=LOTE_DEL_CRON):
        """Pregunta por los pagos de Tilopay que quedaron sin confirmar (el aviso de compras no se reintenta y el
        cliente puede cerrar la pestaña). Los de más de 24 horas sin pago pasan a vencidos. Trabaja por lotes hasta
        acabar lo que toca o hasta gastar su tiempo (``PRESUPUESTO_DEL_CRON``: comparte el hilo de tareas con otras);
        si Tilopay no contesta tres veces seguidas, para y lo deja para la próxima vuelta. Devuelve cuántos revisó. Sin
        proveedor activo y con claves, no hace nada (y no llama a nadie)."""
        proveedores = self.env['payment.provider'].sudo().search([('code', '=', CODIGO), ('state', '!=', 'disabled')])
        proveedores = proveedores.filtered(lambda p: p._dcasa_tilopay_conectado())
        if not proveedores:
            return 0
        ahora = fields.Datetime.now()
        inicio = time.monotonic()
        vistas, revisadas, fallas_seguidas = [], 0, 0
        sin_pago = (api_tilopay.SIN_REGISTRO, api_tilopay.RECHAZADO, api_tilopay.PENDIENTE)
        while time.monotonic() - inicio < PRESUPUESTO_DEL_CRON and fallas_seguidas < FALLAS_SEGUIDAS_PARA_PARAR:
            lote = self._dcasa_tilopay_pendientes(proveedores, ahora, vistas, limite)
            if not lote:
                break
            vistas.extend(lote.ids)
            for pendiente in lote:
                if time.monotonic() - inicio >= PRESUPUESTO_DEL_CRON or fallas_seguidas >= FALLAS_SEGUIDAS_PARA_PARAR:
                    break
                tx = pendiente.with_prefetch()
                try:
                    with self.env.cr.savepoint():
                        veredicto = tx._dcasa_tilopay_confirmar('cron')
                        vencida = tx.create_date <= ahora - VIDA_DE_UN_INTENTO
                        if tx.state in ('draft', 'pending') and veredicto in sin_pago and vencida:
                            if veredicto == api_tilopay.PENDIENTE:
                                tx._dcasa_tilopay_alertar_estado_raro(tx.dcasa_tilopay_veredicto)
                            tx._set_canceled(MENSAJE_VENCIDO)
                    revisadas += 1
                    fallas_seguidas = fallas_seguidas + 1 if veredicto == 'sin_respuesta' else 0
                    if not modules.module.current_test:   # una prueba no puede confirmar la base
                        self.env.cr.commit()
                except psycopg2.OperationalError:
                    if not modules.module.current_test:
                        self.env.cr.rollback()
                except Exception:  # noqa: BLE001 - un pago con problemas no detiene a los demás (el savepoint deshizo lo suyo)
                    _logger.exception('Tilopay: error al revisar la transacción %s.', tx.reference)
        if fallas_seguidas >= FALLAS_SEGUIDAS_PARA_PARAR:
            _logger.warning('Tilopay: no contestó %s veces seguidas; el resto se revisa en la próxima vuelta.',
                            FALLAS_SEGUIDAS_PARA_PARAR)
        _logger.info('Tilopay (tarea): %s revisadas en %.1f s (presupuesto %s s).', revisadas,
                     time.monotonic() - inicio, PRESUPUESTO_DEL_CRON)
        return revisadas
