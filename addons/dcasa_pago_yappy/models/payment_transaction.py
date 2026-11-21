"""La transacción de Yappy: abrir el cobro, y pagar SOLO con el aviso firmado.

Qué cuenta como «pagado» (docs/YAPPY.md §3):

* **El navegador nunca marca un pago.** ``eventSuccess`` del botón de Yappy es solo para la pantalla. Lo único que
  paga es el aviso (IPN) con su hash HMAC comprobado en tiempo constante y con un dominio nuestro
  (``yappy_api.verificar_aviso``).
* ``_apply_updates`` solo acepta ``AvisoVerificado``, que se crea únicamente después de esa comprobación.
* El aviso no trae el monto: se paga el de NUESTRA transacción (el que mandamos al abrir el cobro). Antes de darlo por
  bueno se compara con lo que vale el pedido AHORA; si no coincide, no se paga solo.
* Estados: ``E`` → pagado; ``R`` (no confirmó en 5 minutos), ``C`` (canceló en la app) y ``X`` (la solicitud venció) →
  cancelado, cada uno con su mensaje. Idempotente: el mismo aviso dos veces no duplica nada; un pago ya hecho no se
  deshace con un aviso contrario; un cobro que llega a una transacción ya cerrada NO se paga solo: lo revisa una
  persona.
* Si el aviso se pierde (Yappy no documenta una consulta de estado): una tarea deja un pendiente a Caja pasados 15
  minutos. No paga ni cancela por su cuenta. Caja confirma el cobro, después de mirarlo en Yappy Comercial, con el
  botón «Confirmar que el dinero entró» (``action_dcasa_yappy_confirmar_cobro``): pasa por el MISMO camino que el
  aviso (un solo cobro, queda quién y cuándo) y el aviso tardío que llegue después no hace nada. NUNCA se registra a
  mano el cobro de una orden que sigue abierta: si ya había dinero registrado por otra vía, el aviso va a revisión
  (nunca un segundo cobro).
* El dinero que entra y no cuadra con el pedido nunca pasa en silencio: nota en el pedido y, cuando hay que actuar,
  una actividad.
"""
import hashlib
import hmac
import logging
from collections import namedtuple
from datetime import timedelta

from markupsafe import Markup

from odoo import SUPERUSER_ID, api, fields, models, modules
from odoo.addons.dcasa_base import DCASA_TZ
from odoo.addons.dcasa_base.red import llave_ip
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.tools import float_repr, float_round
from odoo.tools.misc import format_datetime

from . import resumen
from . import yappy_api as api_yappy

_logger = logging.getLogger(__name__)

CODIGO = 'yappy'

TOPE_DE_RECHAZOS = 5                           # avisos rechazados que se anotan por transacción (más son ruido)
INTENTOS_EN_CURSO = 5                          # cobros abiertos sin terminar por pedido…
VENTANA_DE_INTENTOS = timedelta(minutes=15)    # …en este rato
# Cada orden creada es una llamada a la cuenta de Yappy: un tope global por hora y otro por conexión (límites técnicos,
# no cifras del negocio; muy por encima de lo que vende la tienda).
TOPE_ORDENES_POR_HORA = 300
TOPE_ORDENES_POR_CONEXION_HORA = 30
# Yappy cierra la solicitud a los 5 minutos: a los 15 sin aviso, una persona mira
ESPERA_DEL_AVISO = timedelta(minutes=15)
LOTE_DEL_CRON = 50
MAX_LINEAS_DE_AVISOS = 20

MENSAJE_NO_CONFIRMO = (
    'No confirmaste el pago a tiempo: la solicitud de Yappy dura cinco minutos. Tu pedido sigue guardado: puedes '
    'volver a intentarlo o elegir otra forma de pago.')
MENSAJE_CANCELO = (
    'Cancelaste el pago en la app de Yappy. Tu pedido sigue guardado: puedes intentarlo otra vez o elegir otra forma '
    'de pago.')
MENSAJE_VENCIO = (
    'La solicitud de pago venció sin empezarse. Tu pedido sigue guardado: puedes generar una nueva desde tu pedido.')
MENSAJE_ERROR_TOTAL = (
    'Tu pedido cambió mientras pagabas, así que no tomamos ese cobro como el pago. Nuestro equipo lo revisa y te '
    'escribe; también puedes escribirnos por WhatsApp.')
MENSAJE_REVISION = (
    'Yappy nos avisó de un cobro de este pedido que no pudimos tomar como pago solo. Nuestro equipo lo revisa y te '
    'escribe; también puedes escribirnos por WhatsApp.')
MENSAJE_PEDIDO_ANULADO = (
    'Tu pedido ya no estaba vigente cuando Yappy confirmó tu pago. Nuestro equipo lo revisa y te escribe; también '
    'puedes escribirnos por WhatsApp.')
MENSAJE_YA_PAGADO = (
    'Tu pedido ya figuraba como pagado y Yappy nos avisó de otro cobro. Nuestro equipo lo revisa y te escribe; también '
    'puedes escribirnos por WhatsApp.')
MENSAJE_OTRO_DINERO = (
    'Yappy nos avisó de tu cobro, pero encontramos otro pago registrado a tu nombre y no pudimos tomarlo como el pago '
    'de este pedido solo. Nuestro equipo lo revisa y te escribe; también puedes escribirnos por WhatsApp.')
MENSAJES_FINALES = {api_yappy.RECHAZADO: MENSAJE_NO_CONFIRMO, api_yappy.CANCELADO: MENSAJE_CANCELO,
                    api_yappy.EXPIRADO: MENSAJE_VENCIO}
NOMBRES_DE_ESTADO = {api_yappy.EJECUTADO: 'ejecutado (pagó)', api_yappy.RECHAZADO: 'rechazado (no confirmó a tiempo)',
                     api_yappy.CANCELADO: 'cancelado (en la app)', api_yappy.EXPIRADO: 'expirado (nunca empezó)'}

# Lo que se le dice a la clienta cuando Yappy rechaza el cobro (por código; los demás, algo genérico y claro).
MENSAJE_GENERICO = (
    'No pudimos abrir el pago con Yappy ahora. Intenta de nuevo en un momento o elige otra forma de pago; si quieres, '
    'escríbenos por WhatsApp.')
MENSAJES_DE_YAPPY = {
    'E005': 'Ese número no está registrado en Yappy. Revisa que sea el celular donde tienes la app de Yappy.',
}
MENSAJE_YA_ESTABA = (
    'Ya habíamos mandado ese cobro a Yappy. Pulsa el botón de Yappy otra vez para generar uno nuevo; no te cobramos '
    'dos veces.')
MENSAJE_OCUPADO = (
    'Hay muchos pagos en curso en este momento. Intenta de nuevo en unos minutos o elige otra forma de pago.')

AvisoVerificado = namedtuple('AvisoVerificado', 'orden estado confirmacion manual', defaults=(None,))
AvisoVerificado.__doc__ = (
    'Lo que le entrega el controlador a ``_apply_updates``: un aviso que ya pasó ``verificar_aviso``. Los parámetros '
    'del navegador son texto: nunca pueden ser esta clase (``_apply_updates`` la exige). ``manual`` es el usuario '
    '(``res.users``) de Caja que confirmó el cobro mirando Yappy Comercial (``action_dcasa_yappy_confirmar_cobro``) y '
    'es ``None`` en un aviso de Yappy.')
GRUPOS_DE_CAJA = 'dcasa_base.group_caja,account.group_account_user,base.group_system'



class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    dcasa_yappy_orden = fields.Char(
        'Orden en Yappy', readonly=True, copy=False, index='btree_not_null',
        help='La orden que se mandó a Yappy (de 1 a 15 letras y números): empieza con el número del pedido de Odoo y '
             'termina con cinco letras o números al azar, para que cada intento sea único. Es lo que se ve en el '
             'reporte de Yappy Comercial. Se guarda ANTES de llamar a Yappy y es la única orden con la que se busca '
             'un aviso.')
    # Los datos de la persona que paga (su celular de Yappy) y los identificadores de la conexión y de Yappy son de
    # Caja y superiores A NIVEL DE CAMPO (``groups``): la vendedora tiene permiso de leer transacciones (Facturación)
    # y sin esto los leía por RPC de todas las clientas, aunque el menú no se le mostrara.
    dcasa_yappy_id = fields.Char(
        'Transacción de Yappy', readonly=True, copy=False, groups=GRUPOS_DE_CAJA,
        help='El identificador que dio Yappy al crear la orden (solo informativo).')
    dcasa_yappy_celular = fields.Char(
        'Celular de Yappy', readonly=True, copy=False, groups=GRUPOS_DE_CAJA,
        help='El celular (8 números, sin +507) de la app de Yappy de quien paga: a ese número le llega la solicitud. '
             'Es un dato de la clienta y vive solo aquí.')
    dcasa_yappy_iniciada = fields.Datetime(
        'Mandada a Yappy', readonly=True, copy=False,
        help='Cuándo se mandó la orden a Yappy. Pasados 15 minutos sin aviso, una persona la revisa.')
    dcasa_yappy_estado = fields.Selection(
        [(api_yappy.EJECUTADO, 'Ejecutado: pagó'), (api_yappy.RECHAZADO, 'Rechazado: no confirmó en 5 minutos'),
         (api_yappy.CANCELADO, 'Cancelado en la app'), (api_yappy.EXPIRADO, 'Expirado: nunca empezó')],
        string='Último aviso de Yappy', readonly=True, copy=False)
    dcasa_yappy_aviso_fecha = fields.Datetime('Cuándo llegó el aviso', readonly=True, copy=False)
    dcasa_yappy_avisos = fields.Text(
        'Avisos recibidos', readonly=True, copy=False,
        help='Cada aviso firmado que llegó de esta orden, en orden. Sirve para entender qué pasó (un cobro que llega '
             'después de un rechazo, por ejemplo).')
    dcasa_yappy_confirmacion = fields.Char(
        'Número de confirmación (informativo)', readonly=True, copy=False,
        help='Lo que Yappy mandó como «confirmationNumber». NO está firmado y su significado no está documentado: solo '
             'se muestra para mirarlo, nunca decide nada.')
    dcasa_yappy_codigo = fields.Char(
        'Último código de error de Yappy', readonly=True, copy=False,
        help='El código con el que Yappy rechazó abrir el cobro (E005 número no registrado, E010 montos, E011 '
             'direcciones…). Ayuda a entender por qué el cliente no pudo pagar.')
    dcasa_yappy_huella = fields.Char(
        'Conexión de Yappy (huella)', readonly=True, copy=False, index='btree_not_null', groups=GRUPOS_DE_CAJA)
    dcasa_yappy_revision = fields.Boolean(
        'Cobro de Yappy: lo revisa una persona', readonly=True, copy=False, index='btree_not_null',
        help='Yappy avisó de un cobro que no se pudo tomar como pago solo (el pedido cambió, la transacción ya estaba '
             'cerrada, o era de otro entorno). NUNCA se paga sola: se resuelve a mano.')
    dcasa_yappy_sin_aviso = fields.Boolean(
        'Ya se avisó que Yappy no avisó', readonly=True, copy=False, index='btree_not_null',
        help='La tarea ya le dejó a Caja el pendiente de mirar esta orden en Yappy Comercial (una sola vez).')
    dcasa_yappy_confirmada_por = fields.Many2one(
        'res.users', 'Cobro confirmado a mano por', readonly=True, copy=False, ondelete='set null',
        groups=GRUPOS_DE_CAJA,
        help='Quién de Caja confirmó, mirando Yappy Comercial, que el dinero de esta orden entró (botón «Confirmar '
             'que el '
             'dinero entró»). Vacío si pagó el aviso de Yappy.')
    dcasa_yappy_confirmada_fecha = fields.Datetime(
        'Cobro confirmado a mano el', readonly=True, copy=False, groups=GRUPOS_DE_CAJA)
    dcasa_yappy_rechazos = fields.Integer(
        'Avisos rechazados', readonly=True, copy=False,
        help='Cuántas veces llamaron a la dirección del aviso con esta orden y NO se aceptó (dominio escrito '
             'distinto, firma '
             'que no cuadra o claves que faltan). Pudo ser un aviso real de Yappy o alguien probando la dirección: el '
             'cobro no se paga solo. Tope: 5.')
    dcasa_yappy_rechazo = fields.Char(
        'Último aviso rechazado', readonly=True, copy=False,
        help='Por qué no se aceptó el último aviso de esta orden, en palabras fijas. Nunca lleva texto que haya '
             'llegado en la petición, ni la firma ni una clave: lo que llegó queda solo en el registro del servidor.')

    dcasa_pedido_id = fields.Many2one(
        'sale.order', string='Pedido', compute='_compute_dcasa_pedido', help='El pedido de venta que se paga.')
    dcasa_lineas_ids = fields.Many2many(
        'sale.order.line', string='Qué compró', compute='_compute_dcasa_pedido',
        help='Las líneas del pedido que se paga: producto, modelo, cantidad, precio y descuento. La API de Yappy no '
             'manda detalle de la compra: vive en el pedido.')
    dcasa_cliente_celular = fields.Char('Celular del cliente', compute='_compute_dcasa_pedido')
    dcasa_entrega_texto = fields.Char('Entrega', compute='_compute_dcasa_pedido')
    dcasa_origen_texto = fields.Char('Origen', compute='_compute_dcasa_pedido')

    _dcasa_yappy_orden_uniq = models.Constraint('unique(dcasa_yappy_orden)', 'La orden de Yappy debe ser única.')

    # ------------------------------------------------------------------ qué compró

    @api.depends('sale_order_ids')
    def _compute_dcasa_pedido(self):
        for tx in self:
            pedido = tx.sale_order_ids[:1]
            tx.dcasa_pedido_id = pedido
            tx.dcasa_lineas_ids = pedido.order_line.filtered(lambda linea: not linea.display_type) if pedido else False
            tx.dcasa_cliente_celular = resumen.celular_del_cliente(pedido) if pedido else False
            tx.dcasa_entrega_texto = resumen.entrega(pedido) if pedido else False
            tx.dcasa_origen_texto = resumen.origen(pedido) if pedido else False

    # ------------------------------------------------------------------ abrir el cobro

    def _get_specific_processing_values(self, processing_values):
        """El cobro con Yappy es «directo»: no hay página a la que mandar a la clienta (lo hace el botón de Yappy en
        nuestra página). Aquí solo se exige que todo esté listo ANTES de dejar crear la transacción: si algo falla, la
        transacción no llega a existir y la clienta ve un mensaje claro."""
        valores = super()._get_specific_processing_values(processing_values)
        if self.provider_code == CODIGO:
            self._dcasa_yappy_exigir_listo()
        return valores

    def _dcasa_yappy_exigir_listo(self):
        """Lo que se exige para cobrar con Yappy, aunque la clienta haya mandado un proveedor que no se le ofreció."""
        self.ensure_one()
        proveedor = self.provider_id
        if not proveedor._dcasa_yappy_ofrecible():
            raise ValidationError(self.env._(
                'Yappy no está disponible ahora. Elige otra forma de pago o escríbenos por WhatsApp.'))
        interno = self.env.user._is_internal()
        if proveedor._dcasa_yappy_solo_para_el_equipo() and not interno:
            # Lo mismo que hace Odoo al MOSTRAR los proveedores: uno sin publicar (p. ej. en «Modo de prueba») es solo
            # de personas internas. Sin esto, un visitante lo abre mandando el número del proveedor a mano.
            raise ValidationError(self.env._(
                'Yappy no está disponible ahora. Elige otra forma de pago o escríbenos por WhatsApp.'))
        if self.currency_id.name != 'USD':
            raise ValidationError(self.env._('Yappy solo cobra en dólares (USD).'))
        pedidos = self.sale_order_ids
        if pedidos.filtered(lambda pedido: pedido.state == 'cancel'):
            raise ValidationError(self.env._(
                'Este pedido ya no está vigente (se canceló), así que no se puede pagar. Escríbenos por WhatsApp y te '
                'ayudamos.'))
        total_no_coincide = len(pedidos) != 1 or pedidos.currency_id != self.currency_id or \
            self.currency_id.compare_amounts(self.amount, pedidos.amount_total) != 0
        if total_no_coincide or self.currency_id.compare_amounts(pedidos.sudo().amount_paid, 0) > 0:
            raise ValidationError(self.env._(
                'Por ahora Yappy solo paga el pedido completo. Elige otra forma de pago para un abono.'))
        if self.currency_id.compare_amounts(self.amount, 0) <= 0:
            raise ValidationError(self.env._('No hay nada que pagar en este pedido.'))

    def _dcasa_yappy_exigir_topes(self):
        """Los topes de cobros abiertos: por pedido, por conexión y en total por hora. Se miran ANTES de llamar a
        Yappy."""
        self.ensure_one()
        self._dcasa_yappy_bloquear_pedidos()
        pedidos = self.sale_order_ids
        interno = self.env.user._is_internal()
        recientes = self.sudo().search_count([
            ('provider_id', '=', self.provider_id.id), ('dcasa_yappy_orden', '!=', False), ('id', '!=', self.id),
            ('state', 'in', ('draft', 'pending')), ('sale_order_ids', 'in', pedidos.ids),
            ('create_date', '>=', fields.Datetime.now() - VENTANA_DE_INTENTOS)])
        if recientes >= INTENTOS_EN_CURSO:
            raise ValidationError(self.env._(
                'Ya hay varios intentos de pago en curso para este pedido. Espera unos minutos o elige otra forma '
                'de pago.'))
        hace_una_hora = fields.Datetime.now() - timedelta(hours=1)
        huella = self._dcasa_yappy_huella_de_la_conexion()
        if huella and not interno and self.sudo().search_count([
                ('provider_id', '=', self.provider_id.id), ('dcasa_yappy_huella', '=', huella),
                ('state', '!=', 'done'), ('dcasa_yappy_orden', '!=', False), ('create_date', '>=', hace_una_hora)]) \
                >= TOPE_ORDENES_POR_CONEXION_HORA:
            raise ValidationError(self.env._(
                'Has abierto varios intentos de pago seguidos desde esta conexión. Espera un rato o elige otra forma '
                'de pago.'))
        en_la_hora = self.sudo().search_count([
            ('provider_id', '=', self.provider_id.id), ('dcasa_yappy_orden', '!=', False), ('state', '!=', 'done'),
            ('create_date', '>=', hace_una_hora)])
        if en_la_hora >= TOPE_ORDENES_POR_HORA:
            _logger.warning('Yappy: tope de %s órdenes por hora alcanzado.', TOPE_ORDENES_POR_HORA)
            raise ValidationError(MENSAJE_OCUPADO)

    def _dcasa_yappy_bloquear_pedidos(self):
        """Hace que el tope de cobros abiertos por pedido sea ESTRICTO aunque lleguen varios a la vez. Antes de
        contar, se «toca» la fila del pedido (un ``UPDATE`` que no cambia nada): quien llegue después espera a que
        termine el primero y, como PostgreSQL trabaja con una foto de la base tomada al empezar, en vez de contar con
        datos viejos recibe «no pude serializar» y Odoo repite la petición ENTERA con una foto nueva (la misma salida
        que ya usa el aviso). Sin esto, 12 conexiones sobre el mismo pedido abrían 6 cobros en vez de 5."""
        self.ensure_one()
        pedidos = self.sudo().sale_order_ids
        if pedidos:
            self.env.cr.execute('UPDATE sale_order SET write_date = write_date WHERE id IN %s', [tuple(pedidos.ids)])

    @api.model
    def _dcasa_yappy_huella_de_la_conexion(self):
        """Una huella (HMAC con el secreto de la base) de la conexión que abre el cobro, o ``False`` si no hay petición
        web (una tarea, una prueba) o la base no tiene secreto. No se guarda la dirección."""
        try:
            direccion = request.httprequest.remote_addr
        except (RuntimeError, AttributeError):
            return False
        secreto = self.env['ir.config_parameter'].sudo().get_param('database.secret') or ''
        if not direccion or not secreto:
            return False
        mensaje = f'yappy-conexion:{llave_ip(direccion)}'.encode()
        return hmac.new(secreto.encode(), mensaje, hashlib.sha256).hexdigest()[:24]

    def _dcasa_yappy_bloquear(self):
        """Bloquea la fila de la transacción (esperando su turno): dos avisos o dos peticiones a la vez la procesan una
        detrás de la otra y cada una ve lo que hizo la anterior."""
        self.ensure_one()
        self.flush_recordset()
        self.env.cr.execute('SELECT id FROM payment_transaction WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        return bool(self.env.cr.fetchone())

    def _dcasa_yappy_nueva_orden(self):
        """Una orden de 1 a 15 letras y números, con el número del pedido delante y única (se guarda ANTES de
        llamar)."""
        self.ensure_one()
        base = self.sale_order_ids[:1].name or self.reference
        for _intento in range(10):
            orden = api_yappy.orden_nueva(base)
            if api_yappy.orden_valida(orden) and not self.sudo().search_count(
                    [('dcasa_yappy_orden', '=', orden)], limit=1):
                return orden
        raise ValidationError(self.env._('No se pudo preparar el pago. Intenta de nuevo.'))

    def _dcasa_yappy_iniciar(self, celular):
        """Abre el cobro en Yappy para esta transacción y devuelve lo que necesita el botón del navegador:
        ``{'transactionId', 'token', 'documentName'}`` (ninguno es secreto; la clave secreta no sale de aquí).

        Una transacción abre UNA orden en Yappy: si algo sale mal, la clienta pulsa el botón otra vez y se crea una
        transacción nueva con una orden nueva. Lanza ``ValidationError`` con un mensaje para la clienta."""
        self.ensure_one()
        tx = self.sudo()
        if tx.provider_code != CODIGO or not tx._dcasa_yappy_bloquear():
            raise ValidationError(MENSAJE_GENERICO)
        if tx.state != 'draft' or tx.dcasa_yappy_orden:
            raise ValidationError(self.env._(
                'Este intento de pago ya se usó. Pulsa el botón de Yappy otra vez para empezar uno nuevo.'))
        tx._dcasa_yappy_exigir_listo()
        tx._dcasa_yappy_exigir_topes()
        celular_limpio = api_yappy.celular_de_yappy(celular)
        if not celular_limpio:
            raise ValidationError(self.env._(
                'Escribe el celular de tu app de Yappy: 8 números, sin el +507 (por ejemplo 6123 4567).'))
        if not api_yappy.hay_cupo():
            raise ValidationError(MENSAJE_OCUPADO)     # sin cupo no se toca nada: la clienta lo reintenta
        orden = tx._dcasa_yappy_nueva_orden()
        huella = tx._dcasa_yappy_huella_de_la_conexion()
        tx.write({'dcasa_yappy_orden': orden, 'provider_reference': orden, 'dcasa_yappy_celular': celular_limpio,
                  'dcasa_yappy_iniciada': fields.Datetime.now(), **({'dcasa_yappy_huella': huella} if huella else {})})
        tx.flush_recordset()
        if not modules.module.current_test:
            # La orden queda guardada ANTES de llamar a Yappy: si el proceso se cae a media llamada, un aviso tardío de
            # esa orden se reconoce (si no, sería un cobro sin dueño).
            self.env.cr.commit()
        monto = api_yappy.importe(float_round(tx.amount, precision_digits=2))
        url_del_aviso = tx.provider_id._dcasa_yappy_url_del_aviso()
        try:
            datos = tx.provider_id._dcasa_yappy_cliente().crear_orden(orden, celular_limpio, monto, url_del_aviso)
        except api_yappy.ErrorYappy as error:
            tx._dcasa_yappy_no_se_pudo_abrir(error)
            raise ValidationError(tx._dcasa_yappy_mensaje_de(error)) from None
        tx.dcasa_yappy_id = datos['transactionId']
        tx._set_pending()
        return datos

    def _dcasa_yappy_mensaje_de(self, error):
        if error.tipo == 'ya_estaba':
            return MENSAJE_YA_ESTABA
        if error.tipo == 'ocupado':
            return MENSAJE_OCUPADO
        return MENSAJES_DE_YAPPY.get(error.codigo, MENSAJE_GENERICO)

    def _dcasa_yappy_no_se_pudo_abrir(self, error):
        """Qué queda en la transacción cuando Yappy no abrió el cobro. Lo que Yappy rechazó con claridad (el número no
        está registrado, montos, direcciones…) cierra la transacción: no hay orden en Yappy que pueda cobrarse. Lo
        dudoso (se cortó la llamada, respuesta rara) la deja ESPERANDO: la orden pudo haberse creado y un aviso tardío
        la reconoce. «Ya estaba» (E007) también espera: la orden existe en Yappy aunque no tengamos con qué abrirle el
        botón."""
        self.ensure_one()
        _logger.warning(
            'Yappy: no se pudo abrir el cobro de %s (%s, %s).', self.reference, error.tipo, error.codigo or '-')
        if error.codigo:
            self.dcasa_yappy_codigo = error.codigo
        if error.tipo in ('rechazo', 'comercio') and error.codigo != 'E007':
            self._set_error(MENSAJE_GENERICO if error.codigo != 'E005' else MENSAJES_DE_YAPPY['E005'])
        elif error.tipo in ('red', 'respuesta', 'ya_estaba'):
            self._set_pending()
        elif error.tipo == 'ocupado':       # no se intentó nada: queda como si no se hubiera empezado
            self.write({'dcasa_yappy_orden': False, 'dcasa_yappy_iniciada': False, 'dcasa_yappy_celular': False})

    # ------------------------------------------------------------------ el aviso (lo único que paga)

    @api.model
    def _dcasa_yappy_buscar(self, orden):
        """La transacción de Yappy con esa orden (la nuestra), o vacío. Igualdad exacta, sin armar SQL con texto."""
        orden = api_yappy.orden_valida(orden)
        if not orden:
            return self.browse()
        return self.sudo().search([('dcasa_yappy_orden', '=', orden), ('provider_id.code', '=', CODIGO)], limit=1)

    def _dcasa_yappy_aplicar_aviso(self, aviso):
        """Aplica un aviso que YA pasó ``verificar_aviso`` (el controlador lo comprobó). Bloquea la fila y la
        procesa."""
        self.ensure_one()
        tx = self.sudo()
        if tx.provider_code != CODIGO or not tx.dcasa_yappy_orden or tx.dcasa_yappy_orden != aviso.orden:
            return None
        tx._dcasa_yappy_bloquear()
        verificado = AvisoVerificado(aviso.orden, aviso.estado, aviso.confirmacion)
        tx._process(CODIGO, verificado)
        return tx.state

    def _dcasa_yappy_anotar_rechazo(self, motivo):
        """Un aviso de esta orden se rechazó (dominio escrito distinto, firma que no cuadra, claves que faltan): queda
        anotado en la transacción (con tope: son rastros, no una bitácora que un atacante pueda llenar) para que el
        pendiente de Caja no diga «Yappy no avisó» cuando sí llegó algo y no lo pudimos aceptar. No paga, no cancela, no
        cambia el estado. Devuelve ``True`` si lo anotó.

        ``motivo`` es el CÓDIGO del rechazo (``yappy_api.RECHAZO_*``), no un texto: lo que se guarda es la frase fija de
        ``motivo_para_caja``. Nada de lo que llegó en la petición (el ``domain``, por ejemplo, que escribe quien llama)
        entra a la transacción ni al pendiente de Caja (RV7, R7-3)."""
        self.ensure_one()
        tx = self.sudo()
        if tx.provider_code != CODIGO or tx.state not in ('draft', 'pending') \
                or tx.dcasa_yappy_rechazos >= TOPE_DE_RECHAZOS:
            return False
        tx.write({'dcasa_yappy_rechazos': tx.dcasa_yappy_rechazos + 1,
                  'dcasa_yappy_rechazo': api_yappy.motivo_para_caja(motivo)})
        return True

    # ------------------------------------------------------------------ Caja confirma el cobro (en Yappy Comercial)

    def _dcasa_yappy_exigir_caja(self):
        if not self.env.su and not any(self.env.user.has_group(grupo) for grupo in GRUPOS_DE_CAJA.split(',')):
            raise AccessError(self.env._('Solo Caja, Gerencia y contabilidad confirman un cobro de Yappy.'))

    def action_dcasa_yappy_confirmar_cobro(self):
        """Botón «Confirmar que el dinero entró» (Caja, Gerencia, contabilidad): para el cobro cuyo aviso no llegó. La
        persona abrió Yappy Comercial, vio la orden con su dinero, y lo confirma aquí. Pasa por el MISMO camino que el
        aviso de Yappy (``_process`` → ``_apply_updates``): las mismas comprobaciones (entorno, pedido vivo, pedido no
        pagado ya por otra vía, total), UN solo cobro, y queda anotado quién y cuándo. El aviso que llegue tarde
        después no hace nada. Solo sirve con la transacción abierta: una ya cerrada o marcada para revisar se resuelve
        con su pendiente. Esto NO es registrar el cobro a mano en el diario (eso duplicaría el cobro si el aviso
        llegara después)."""
        self.ensure_one()
        self._dcasa_yappy_exigir_caja()
        quien = self.env.user.sudo()
        tx = self.sudo()
        if tx.provider_code != CODIGO or not tx.dcasa_yappy_orden:
            raise UserError(self.env._('Este botón es solo de un cobro de Yappy directo con su orden.'))
        tx._dcasa_yappy_bloquear()
        if tx.state == 'done':
            return self._dcasa_yappy_notificar(
                self.env._('Esta orden ya figura como pagada: no hay nada más que confirmar.'), 'info')
        if tx.state not in ('draft', 'pending'):
            raise UserError(self.env._(
                'Esta transacción ya está cerrada («%s»). Si Yappy cobró, ya tiene su pendiente para revisarlo: '
                'míralo en '
                'el pedido.', tx.state))
        if not tx._dcasa_yappy_la_recibio_yappy():
            # Un borrador con su orden pero sin el identificador que da Yappy al crearla: la orden nunca llegó a Yappy
            # (un corte a mitad de /iniciar, o los segundos en que se está llamando). Nadie vio ese dinero (RV7, R7-6).
            raise UserError(self.env._(
                'Yappy todavía no recibió esta orden (el cobro se quedó a medio abrir), así que no hay nada que '
                'confirmar. Si la clienta quiere pagar, que pulse el botón de Yappy otra vez; si Yappy sí cobró, el '
                'aviso firmado de Yappy es lo que deja el pedido pagado.'))
        tx._process(CODIGO, AvisoVerificado(tx.dcasa_yappy_orden, api_yappy.EJECUTADO, '', quien))
        if tx.state == 'done':
            return self._dcasa_yappy_notificar(self.env._(
                'Listo: el cobro de la orden %s quedó confirmado a tu nombre. El pedido se confirma y el pago cae en '
                'el '
                'diario Yappy en un momento. Si el aviso de Yappy llega después, no hace nada.', tx.dcasa_yappy_orden),
                'success')
        return self._dcasa_yappy_notificar(self.env._(
            'No se pudo tomar como pago solo y quedó para revisar: %s. Mira la alerta en el pedido.',
            tx.state_message or '—'), 'warning', pegajoso=True)

    def _dcasa_yappy_la_recibio_yappy(self):
        """¿Yappy llegó a recibir esta orden? Sí si la transacción ya está ``pending`` (se marca al recibir la
        respuesta de Yappy, y también cuando la llamada se cortó a medias y la orden pudo haberse creado) o si Yappy ya
        devolvió su identificador. Un borrador con orden y sin identificador es una orden que se guardó ANTES de llamar
        y a la que Yappy nunca contestó."""
        self.ensure_one()
        return self.state != 'draft' or bool(self.sudo().dcasa_yappy_id)

    def _dcasa_yappy_notificar(self, mensaje, tipo, pegajoso=False):
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': self.env._('Cobro de Yappy'), 'message': mensaje, 'type': tipo, 'sticky': pegajoso,
                           'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code != CODIGO:
            return super()._extract_reference(provider_code, payment_data)
        return None

    def _extract_amount_data(self, payment_data):
        """El aviso no trae monto: no hay nada que comparar contra el aviso (el monto se paga de NUESTRA transacción y
        se compara con el pedido en ``_dcasa_yappy_coherente``)."""
        if self.provider_code != CODIGO:
            return super()._extract_amount_data(payment_data)
        return None

    def _apply_updates(self, payment_data):
        if self.provider_code != CODIGO:
            return super()._apply_updates(payment_data)
        if not isinstance(payment_data, AvisoVerificado):
            # Defensa: ningún camino que no haya comprobado la firma puede mover el estado de un pago.
            _logger.warning('Yappy: se ignoraron datos que no vienen de un aviso firmado (%s).', self.reference)
            return
        estado = payment_data.estado
        nuevo = self._dcasa_yappy_registrar_aviso(payment_data)
        self._dcasa_yappy_cerrar_el_pendiente_sin_aviso(payment_data)
        if self.state == 'done':
            if estado != api_yappy.EJECUTADO and nuevo:
                self._dcasa_yappy_alertar_contradiccion(estado)
            # el mismo aviso otra vez (o el aviso tardío de un cobro ya confirmado a mano), o uno contrario a un pago ya
            # hecho: no se toca nada
            return
        if estado == api_yappy.EJECUTADO:
            self._dcasa_yappy_aplicar_ejecutado(payment_data.manual)
        elif self.state in ('draft', 'pending', 'authorized'):
            self._set_canceled(MENSAJES_FINALES[estado])
        elif self.state == 'cancel' and nuevo:
            _logger.info('Yappy: aviso %s de %s, que ya estaba cancelada.', estado, self.reference)

    def _dcasa_yappy_registrar_aviso(self, aviso):
        """Deja anotado el aviso (la bitácora, el último estado y la confirmación informativa). Devuelve ``True`` si
        es la primera vez que llega ese estado (un aviso repetido no escribe nada). Una confirmación a mano de Caja se
        anota con su propia letra («M»), así un aviso «E» tardío todavía se anota después como lo que es."""
        lineas = (self.dcasa_yappy_avisos or '').splitlines()
        letra = 'M' if aviso.manual else aviso.estado
        if any(linea.startswith(f'{letra} ') for linea in lineas):
            return False
        ahora = fields.Datetime.now()
        cuando = format_datetime(self.env, ahora, tz=DCASA_TZ, dt_format='medium')
        if aviso.manual:
            lineas.append(f"M · cobro confirmado a mano por {aviso.manual.name} (mirando Yappy Comercial) · {cuando}")
            valores = {'dcasa_yappy_avisos': '\n'.join(lineas[-MAX_LINEAS_DE_AVISOS:])}
        else:
            lineas.append(f"{aviso.estado} · {NOMBRES_DE_ESTADO[aviso.estado]} · {cuando}")
            valores = {'dcasa_yappy_avisos': '\n'.join(lineas[-MAX_LINEAS_DE_AVISOS:]),
                       'dcasa_yappy_estado': aviso.estado, 'dcasa_yappy_aviso_fecha': ahora}
            if aviso.confirmacion:
                valores['dcasa_yappy_confirmacion'] = aviso.confirmacion
        self.write(valores)
        return True

    def _dcasa_yappy_cerrar_el_pendiente_sin_aviso(self, aviso):
        """Llegó el aviso (el que sea: pagó, rechazó, canceló, expiró) o Caja confirmó el cobro: el pendiente «sin
        aviso de pago» de esta orden ya no tiene razón de ser y se cierra solo, con una nota de qué lo cerró. Si
        quedara abierto diría «Yappy no avisó nada» de una orden que ya tiene su aviso (y empujaría a registrar el
        cobro a mano otra vez). Nunca hace fallar un pago."""
        try:
            with self.env.cr.savepoint():
                resumen_del_pendiente = self.env._('Yappy: sin aviso de pago (%s)', self.dcasa_yappy_orden)
                pendientes = self.env['mail.activity'].sudo().search([
                    ('res_model', '=', 'sale.order'), ('res_id', 'in', self.sudo().sale_order_ids.ids),
                    ('summary', '=', resumen_del_pendiente)])
                if pendientes:
                    que_paso = (self.env._('Caja confirmó el cobro a mano') if aviso.manual else
                                self.env._('Llegó el aviso de Yappy: %s', NOMBRES_DE_ESTADO[aviso.estado]))
                    pendientes.with_user(SUPERUSER_ID).action_feedback(
                        feedback=self.env._('%(que)s (orden %(orden)s). Ya no hace falta mirar si Yappy avisó.',
                                            que=que_paso, orden=self.dcasa_yappy_orden))
        except Exception:  # noqa: BLE001 - cerrar un pendiente no debe tumbar el pago
            _logger.exception('Yappy: no se pudo cerrar el pendiente de %s.', self.reference)

    def _dcasa_yappy_aplicar_ejecutado(self, manual=None):
        """Un aviso «E» firmado (o el cobro que Caja confirmó mirando Yappy Comercial): el dinero entró. Se paga SOLO
        si la transacción sigue abierta y todo cuadra; si no, el dinero entró pero lo resuelve una persona (nunca se
        paga solo). Lo que NUNCA hace es registrar un segundo cobro de un pedido que ya está pagado por otra vía."""
        if self.dcasa_yappy_revision:
            return      # ya la tiene una persona
        como = (self.env._('el aviso de Yappy') if not manual else
                self.env._('la confirmación a mano de %s', manual.name))
        if self.state not in ('draft', 'pending', 'authorized'):
            # Cancelada o con error y llega un cobro: el dinero pudo entrar a pesar de lo que se le dijo a la clienta.
            self._dcasa_yappy_pedir_revision(
                self.env._(
                    'Yappy avisó que el cliente PAGÓ la orden %(orden)s, pero esa transacción ya estaba cerrada '
                    '(«%(estado)s»). El dinero pudo entrar. NO se tomó como pago solo. Revisa el reporte de Yappy '
                    'Comercial: si el cobro está, o devuélvelo, o confirma el pedido y registra el pago a mano en el '
                    'diario Yappy.', orden=self.dcasa_yappy_orden, estado=self.state),
                MENSAJE_REVISION, extra_allowed_states=('cancel', 'error'))
            return
        entorno_actual = api_yappy.entorno_esperado() == api_yappy.PRODUCCION
        if bool(self.is_live) != entorno_actual:
            self._dcasa_yappy_pedir_revision(
                self.env._(
                    'Llegó un pago de la orden %(orden)s (%(como)s), pero esta transacción se abrió en otro entorno '
                    '(prueba o real) que el de ahora. NO se tomó como pago solo.', orden=self.dcasa_yappy_orden,
                    como=como),
                MENSAJE_REVISION)
            return
        pedidos = self.sudo().sale_order_ids
        anulados = pedidos.filtered(lambda pedido: pedido.state == 'cancel')
        if anulados:
            # El pedido se anuló (una vendedora, o el apartado que vence por la noche) mientras la clienta aprobaba en
            # su app. El dinero entró; el pedido no existe. Nunca se «cobra» un pedido anulado ni se le dice
            # «Confirmamos tu pedido»: lo resuelve una persona (se devuelve el cobro, o se reabre el pedido).
            self._dcasa_yappy_pedir_revision(
                self.env._(
                    'Llegó un pago de la orden %(orden)s (%(como)s) de %(monto)s %(moneda)s, pero el pedido %(pedido)s '
                    'está CANCELADO. El dinero entró y NO se tomó como pago de ningún pedido. Habla con el cliente: '
                    'o se '
                    'devuelve el cobro desde Yappy Comercial, o reabres el pedido, lo confirmas y registras a mano '
                    'el pago '
                    'en el diario Yappy.', orden=self.dcasa_yappy_orden, como=como, monto=float_repr(self.amount, 2),
                    moneda=self.currency_id.name, pedido=', '.join(anulados.mapped('name'))),
                MENSAJE_PEDIDO_ANULADO, titulo=self.env._('Yappy: cobro de un pedido que ya no está vivo'))
            return
        dinero_antes, es_seguro = self._dcasa_yappy_dinero_de_otra_via()
        if dinero_antes and es_seguro:
            self._dcasa_yappy_pedir_revision(
                self.env._(
                    'Llegó un pago de la orden %(orden)s (%(como)s), pero este pedido YA TENÍA dinero registrado por '
                    'otra '
                    'vía: %(detalle)s. NO se registró otro cobro. Si es el mismo dinero (lo normal cuando Caja '
                    'registró el '
                    'cobro a mano porque el aviso tardaba), no hay nada más que hacer: cierra este pendiente. Si el '
                    'cliente pagó dos veces, hay que devolverle uno desde Yappy Comercial.',
                    orden=self.dcasa_yappy_orden, como=como, detalle=dinero_antes),
                MENSAJE_YA_PAGADO, titulo=self.env._('Yappy: el pedido ya estaba pagado (%s)', self.dcasa_yappy_orden))
            return
        if dinero_antes:
            # Solo hay un cobro SUELTO (sin factura, de este cliente): no se sabe de qué pedido es (RV8, R8-3). Se
            # dicen las dos posibilidades y qué hacer en cada una; a la clienta no se le afirma que su pedido ya estaba
            # pagado.
            self._dcasa_yappy_pedir_revision(
                self.env._(
                    'Llegó un pago de la orden %(orden)s (%(como)s), pero hay otro dinero de este cliente registrado a '
                    'mano sin factura: %(detalle)s. NO se registró otro cobro y no se sabe de qué pedido es ese '
                    'dinero. Si ese cobro es de ESTE pedido (lo normal si Caja lo registró a mano porque el aviso '
                    'tardaba), no hay nada más que hacer: cierra este pendiente; y si el cliente pagó dos veces, '
                    'devuélvele uno '
                    'desde Yappy Comercial. Si ese cobro es de OTRO pedido del mismo cliente (un anticipo, por '
                    'ejemplo), entonces el dinero de Yappy SÍ es de este pedido: confirma ESTE pedido a mano, '
                    'factúralo y registra su pago en el diario Yappy.',
                    orden=self.dcasa_yappy_orden, como=como, detalle=dinero_antes),
                MENSAJE_OTRO_DINERO,
                titulo=self.env._('Yappy: hay otro dinero del cliente sin factura (%s)', self.dcasa_yappy_orden))
            return
        coincide, detalle = self._dcasa_yappy_total_del_pedido()
        if not coincide:
            self._dcasa_yappy_pedir_revision(
                self.env._(
                    'Yappy cobró %(monto)s %(moneda)s (orden %(orden)s) y el pedido cambió mientras el cliente pagaba: '
                    '%(detalle)s. El dinero entró y NO se tomó como pago del pedido, y no se va a pagar solo aunque el '
                    'pedido vuelva a valer lo cobrado. Habla con el cliente: o se devuelve el cobro desde Yappy '
                    'Comercial, o, si te quedas con el pago, ajustas el pedido al monto cobrado, lo confirmas y lo '
                    'facturas, y registras a mano el pago en el diario Yappy.', monto=float_repr(self.amount, 2),
                    moneda=self.currency_id.name, orden=self.dcasa_yappy_orden, detalle=detalle),
                MENSAJE_ERROR_TOTAL, titulo=self.env._('Yappy: cobro que no cuadra con el pedido'))
            return
        self._set_done()
        if manual:
            self.write({'dcasa_yappy_confirmada_por': manual.id, 'dcasa_yappy_confirmada_fecha': fields.Datetime.now()})
        self._dcasa_yappy_anotar_el_pago()
        self._dcasa_yappy_avisos_tras_el_pago()
        self._dcasa_yappy_adelantar_el_cierre()

    def _dcasa_yappy_cobros_sueltos(self):
        """Los cobros «sueltos» que Caja registró a mano en el diario de Yappy para este cliente DESPUÉS de abrirse este
        cobro: un ``account.payment`` de cliente, entrante, en el diario de Yappy, sin transacción en línea y sin
        factura a la que esté aplicado (así lo deja el cobro suelto de Pagos, sin pasar por una factura). Las facturas
        con pagos ya las cuenta ``_dcasa_yappy_dinero_de_otra_via``. Es una regla gruesa a propósito: si el mismo
        cliente tiene otro cobro suelto en esa ventana, el aviso va a revisión (una persona mira) y nunca se paga de
        más (RV7, R7-5)."""
        self.ensure_one()
        tx = self.sudo()
        diario = tx.provider_id.journal_id
        pedidos = tx.sale_order_ids
        if not diario or not pedidos or not tx.create_date:
            return self.env['account.payment']
        # El sudo() mira solo pagos de CLIENTE entrantes (para un pago, el equivalente de filtrar las facturas por
        # out_invoice/out_refund: nunca pagos de proveedor ni salientes). El resultado no se le devuelve a nadie que no
        # cobre: solo cuenta el dinero y nombra el cobro en la alerta para Caja o Gerencia.
        clientes = pedidos.partner_id | pedidos.partner_invoice_id | tx.partner_id
        clientes |= clientes.commercial_partner_id
        sueltos = self.env['account.payment'].sudo().search([
            ('journal_id', '=', diario.id), ('payment_type', '=', 'inbound'), ('partner_type', '=', 'customer'),
            ('partner_id', 'in', clientes.ids), ('state', 'not in', ('draft', 'canceled', 'rejected')),
            ('payment_transaction_id', '=', False), ('create_date', '>=', tx.create_date)])
        return sueltos.filtered(lambda pago: not pago.reconciled_invoice_ids)

    def _dcasa_yappy_dinero_de_otra_via(self):
        """``(frase, es_seguro)``: una frase de cuál es el dinero que este pedido YA tenía antes de que se pagara esta
        transacción (otro cobro en línea hecho, una factura con pagos registrados, o un cobro suelto de Caja en el
        diario de Yappy, que es lo que deja un cobro a mano); vacía si no había ninguno. Mientras esta transacción siga
        abierta, todo pago que figure es de otra vía. ``es_seguro`` es ``False`` cuando SOLO hay cobros sueltos: un
        cobro sin factura no dice de qué pedido es, y el mensaje a la clienta no puede afirmar «ya figuraba como pagado»
        (RV8, R8-3). Se valoró comparar también el monto y NO se hizo: no distingue un cobro parcial de ESTE pedido (que
        sí sería dinero doble) de un anticipo de otro; ver ``docs/YAPPY.md`` §14."""
        self.ensure_one()
        partes = []
        sueltos = self._dcasa_yappy_cobros_sueltos()
        if sueltos:
            partes.append(self.env._(
                'un cobro suelto registrado a mano en el diario Yappy (%s)', ', '.join(sueltos.mapped('name'))))
        solo_sueltos = bool(partes)
        for pedido in self.sudo().sale_order_ids:
            otras = pedido.transaction_ids.filtered(lambda t: t != self and t.state in ('authorized', 'done'))
            if otras:
                partes.append(self.env._('otro cobro en línea (%s)', ', '.join(otras.mapped('reference'))))
                solo_sueltos = False
            facturas = pedido.invoice_ids.filtered(
                lambda f: f.move_type == 'out_invoice' and f.state == 'posted'
                and f.payment_state in ('paid', 'in_payment', 'partial'))
            if facturas:
                partes.append(self.env._(
                    'la factura %s ya tiene pagos registrados', ', '.join(facturas.mapped('name'))))
                solo_sueltos = False
        return '; '.join(partes), bool(partes) and not solo_sueltos

    def _dcasa_yappy_pedir_revision(self, texto, mensaje_al_cliente, titulo=None, extra_allowed_states=()):
        """Marca la transacción para que la resuelva una persona: nunca se paga sola. El cliente ve un mensaje claro y
        Gerencia recibe una nota y una actividad en el pedido."""
        self.dcasa_yappy_revision = True
        if self.state != 'error':
            self._set_error(mensaje_al_cliente, extra_allowed_states=extra_allowed_states)
        self._dcasa_yappy_alertar(texto, titulo or self.env._('Yappy: cobro para revisar (%s)', self.dcasa_yappy_orden))

    def _dcasa_yappy_alertar_contradiccion(self, estado):
        """Ya estaba pagada y llega un aviso de que NO se pagó: no se deshace nada, pero alguien lo mira (una sola
        vez)."""
        self._dcasa_yappy_alertar(
            self.env._(
                'La orden %(orden)s de Yappy ya estaba pagada y ahora Yappy avisó «%(estado)s». No se deshizo el pago. '
                'Revisa el reporte de Yappy Comercial para confirmar que el cobro está.',
                orden=self.dcasa_yappy_orden, estado=NOMBRES_DE_ESTADO[estado]),
            self.env._('Yappy: avisos que se contradicen (%s)', self.dcasa_yappy_orden), una_vez=True)

    # ------------------------------------------------------------------ el pedido

    def _dcasa_yappy_total_del_pedido(self):
        """``(coincide, detalle)``: ¿el pedido vale ahora lo mismo que se cobró? El monto que se mandó a Yappy es el del
        pedido de aquel momento; el carrito sigue editable mientras la transacción está abierta."""
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

    def _check_amount_and_confirm_order(self):
        """Override de ``sale``: la última puerta antes de confirmar un pedido pagado con Yappy. Si el pedido ya no vale
        lo cobrado, no se confirma solo (el dinero entró; Gerencia se entera). Después de confirmar, un pedido pagado
        completo deja de ser un «apartado» (la tienda lo marca así cuando confirma sola)."""
        yappy = self.filtered(lambda tx: tx.provider_code == CODIGO)
        distintas = self.browse()
        for tx in yappy:
            coincide, detalle = tx._dcasa_yappy_total_del_pedido()
            if not coincide:
                distintas |= tx
                tx._dcasa_yappy_alertar(
                    self.env._(
                        'Yappy cobró %(monto)s %(moneda)s (orden %(orden)s), pero %(detalle)s. El pedido NO se '
                        'confirmó solo: habla con el cliente y devuelve el cobro desde Yappy Comercial o ajusta el '
                        'pedido.',
                        monto=float_repr(tx.amount, 2), moneda=tx.currency_id.name, orden=tx.dcasa_yappy_orden,
                        detalle=detalle),
                    self.env._('Yappy: cobro que no cuadra con el pedido'))
        for tx in yappy - distintas:
            anulados = tx.sudo().sale_order_ids.filtered(lambda pedido: pedido.state == 'cancel')
            if anulados:
                # Se anuló entre el aviso y esta tarea (el aviso mismo ya manda a revisión lo que llega con el pedido
                # anulado).
                tx._dcasa_yappy_alertar(
                    self.env._(
                        'Yappy cobró %(monto)s %(moneda)s (orden %(orden)s) de un pedido que se canceló justo después: '
                        '%(pedido)s. El dinero entró y el pedido no se va a confirmar solo. O se devuelve el cobro '
                        'desde Yappy Comercial, o se reabre el pedido.', monto=float_repr(tx.amount, 2),
                        moneda=tx.currency_id.name, orden=tx.dcasa_yappy_orden,
                        pedido=', '.join(anulados.mapped('name'))),
                    self.env._('Yappy: cobro de un pedido que ya no está vivo'), una_vez=True)
        confirmados = super(PaymentTransaction, self - distintas)._check_amount_and_confirm_order()
        for tx in yappy - distintas:
            tx._dcasa_yappy_soltar_el_apartado()
        return confirmados

    def _dcasa_yappy_soltar_el_apartado(self):
        """Un pedido de la web cobrado completo ya no es un apartado por vencer (``website_dcasa``)."""
        self.ensure_one()
        if self.state != 'done':
            return
        for pedido in self.sudo().sale_order_ids:
            if 'dcasa_apartado_vence' in pedido._fields and pedido.dcasa_apartado_vence \
                    and pedido.currency_id.compare_amounts(self.amount, pedido.amount_total) >= 0:
                pedido.dcasa_apartado_vence = False

    def _dcasa_yappy_anotar_el_pago(self):
        """LA NOTA QUE LE DICE AL EQUIPO QUÉ COMPRÓ ESTA PERSONA: queda en el pedido (donde el equipo ya se entera de
        los pedidos de la web: sus notas internas y la tarjeta «Compraron en la web y aún no se entregan»), con el
        detalle: productos y modelos, cantidades, precios, descuentos, envío, total, cliente, entrega, origen y cómo
        pagó. Nunca hace fallar un pago."""
        try:
            with self.env.cr.savepoint():
                robot = self.env['res.users'].sudo().browse(SUPERUSER_ID).partner_id
                for pedido in self.sudo().sale_order_ids:
                    pedido.message_post(
                        body=resumen.nota_de_pago(self.env, self.sudo(), pedido), author_id=robot.id,
                        subtype_xmlid='mail.mt_note')
        except Exception:  # noqa: BLE001 - una nota que no sale no debe tumbar la confirmación
            _logger.exception('Yappy: no se pudo dejar la nota de la compra en el pedido de %s.', self.reference)

    def _dcasa_yappy_avisos_tras_el_pago(self):
        """Lo que el equipo tiene que saber de un pago, además de que entró: si fue una prueba (el pedido se confirma
        igual y quien prepara la entrega no lo puede adivinar). Un pedido anulado ya no llega hasta aquí: va a
        revisión."""
        self.ensure_one()
        if not self.is_live:
            self._dcasa_yappy_anotar(self.env._(
                'Pagado en el modo de PRUEBA de Yappy: no entró dinero real, aunque el pedido se confirmó. Revísalo '
                'antes de preparar la entrega.'))

    def _dcasa_yappy_adelantar_el_cierre(self):
        """Pide que la tarea de Odoo que termina los pagos (confirmar el pedido, el cobro) corra enseguida y no dentro
        de 10 minutos: la clienta puede no estar mirando."""
        try:
            with self.env.cr.savepoint():
                cron = self.env.ref('payment.cron_post_process_payment_tx', raise_if_not_found=False)
                if cron:
                    cron.sudo()._trigger()
        except Exception:  # noqa: BLE001
            _logger.warning('Yappy: no se pudo adelantar el cierre de %s (corre a su hora).', self.reference)

    # ------------------------------------------------------------------ notas y actividades

    def _dcasa_yappy_anotar(self, texto):
        """Una nota interna (solo el equipo) en los pedidos de esta transacción. Nunca hace fallar un pago."""
        try:
            with self.env.cr.savepoint():
                robot = self.env['res.users'].sudo().browse(SUPERUSER_ID).partner_id
                cuerpo = Markup('<p>%s</p>') % texto      # ``%`` escapa: un texto de afuera nunca es HTML
                for pedido in self.sudo().sale_order_ids:
                    pedido.message_post(body=cuerpo, author_id=robot.id, subtype_xmlid='mail.mt_note')
        except Exception:  # noqa: BLE001
            _logger.exception('Yappy: no se pudo dejar la nota en el pedido de %s.', self.reference)

    def _dcasa_yappy_destinatarios(self):
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

    def _dcasa_yappy_alertar(self, texto, resumen_de_la_actividad, una_vez=False, destinos=None):
        """Una nota interna en el pedido Y una actividad para Gerencia (o a ``destinos``): para algo de lo que alguien
        tiene que ocuparse. No repite la actividad si ya hay una igual abierta; con ``una_vez``, tampoco la nota. Nunca
        hace fallar un pago."""
        pedidos = self.sudo().sale_order_ids
        if una_vez and self.env['mail.activity'].sudo().search_count([
                ('res_model', '=', 'sale.order'), ('res_id', 'in', pedidos.ids),
                ('summary', '=', resumen_de_la_actividad)], limit=1):
            return
        self._dcasa_yappy_anotar(texto)
        try:
            with self.env.cr.savepoint():
                destinos = destinos if destinos is not None else self._dcasa_yappy_destinatarios()
                Actividad = self.env['mail.activity'].sudo()
                for pedido in pedidos:
                    for usuario in destinos:
                        if Actividad.search_count([
                                ('res_model', '=', 'sale.order'), ('res_id', '=', pedido.id),
                                ('user_id', '=', usuario.id), ('summary', '=', resumen_de_la_actividad)], limit=1):
                            continue
                        pedido.activity_schedule(
                            'mail.mail_activity_data_todo', summary=resumen_de_la_actividad,
                            note=Markup('<p>%s</p>') % texto, user_id=usuario.id)
        except Exception:  # noqa: BLE001 - un aviso que no sale no debe tumbar la confirmación
            _logger.exception('Yappy: no se pudo dejar la actividad (%s).', self.reference)

    # ------------------------------------------------------------------ el aviso que no llegó

    @api.model
    def _cron_dcasa_yappy_sin_aviso(self, limite=LOTE_DEL_CRON):
        """Yappy no tiene consulta de estado: si el aviso se pierde, nadie lo vuelve a mandar. Pasados 15 minutos de
        haber mandado la orden (Yappy la cierra a los 5), le deja a Caja (o a Gerencia si nadie tiene Caja) un
        pendiente claro en el pedido: mirar la orden en el reporte de Yappy Comercial. UNA sola vez por transacción.
        **No paga ni cancela nada por su cuenta.** Sin claves cargadas no hace nada. Devuelve cuántas dejó."""
        if api_yappy.credenciales() is None:
            return 0
        pendientes = self.sudo().search([
            ('provider_id.code', '=', CODIGO), ('state', 'in', ('draft', 'pending')),
            ('dcasa_yappy_orden', '!=', False), ('dcasa_yappy_sin_aviso', '=', False),
            ('dcasa_yappy_revision', '=', False),
            ('dcasa_yappy_iniciada', '<=', fields.Datetime.now() - ESPERA_DEL_AVISO),
        ], order='dcasa_yappy_iniciada', limit=limite)
        dejadas = 0
        for tx in pendientes:
            try:
                with self.env.cr.savepoint():
                    tx.dcasa_yappy_sin_aviso = True
                    tx._dcasa_yappy_pedir_que_miren_la_orden()
                    dejadas += 1
                if not modules.module.current_test:
                    self.env.cr.commit()
            except Exception:  # noqa: BLE001 - una transacción con problemas no detiene a las demás
                _logger.exception('Yappy: no se pudo dejar el pendiente de %s.', tx.reference)
        return dejadas

    def _dcasa_yappy_pedir_que_miren_la_orden(self):
        self.ensure_one()
        pedido = self.sale_order_ids[:1]
        destinos = self.env['sale.order']._dcasa_atienden_lo_sin_vendedora() or self._dcasa_yappy_destinatarios()
        # Lo que escribió la clienta (su nombre, su celular, un valor personalizado de un producto) va entre comillas y
        # recortado: nunca como parte de la frase, donde «NOTA PARA CAJA: pulsa Confirmar» pasaría por una orden
        # (RV8, R8-4).
        detalle = '; '.join(
            resumen.frase_de_linea(pedido, fila) for fila in resumen.lineas(pedido, citar=True)) if pedido else ''
        # Si llegó una llamada a la dirección del aviso y se RECHAZÓ, no es verdad que «Yappy no avisó nada»; pero
        # tampoco se sabe que Yappy avisó: pudo ser un aviso real o alguien probando la dirección. Se dice lo que se
        # sabe, con el motivo en palabras fijas (nunca texto de quien llamó: eso empujaría a Caja a confirmar sin mirar
        # Yappy Comercial; RV7, R7-3).
        if self.dcasa_yappy_rechazos:
            que_paso = self.env._(
                'y NO se pudo aceptar ningún aviso. A nuestra dirección de avisos llegaron %(cuantos)s llamada(s) con '
                'esta orden y ninguna se pudo aceptar (%(motivo)s). Pudo ser un aviso real de Yappy o alguien probando '
                'la dirección: por eso no se sabe si el dinero entró. Mira Yappy Comercial.',
                cuantos=self.dcasa_yappy_rechazos, motivo=self.dcasa_yappy_rechazo or '—')
        else:
            que_paso = self.env._('y Yappy no avisó nada.')
        if self._dcasa_yappy_la_recibio_yappy():
            que_hacer = self.env._(
                'si el cobro entró, abre esta transacción (Facturación › Clientes › Pagos con Yappy) y pulsa '
                '«Confirmar que el dinero entró»; NO registres el cobro a mano en el diario: si el aviso llegara '
                'tarde, el cobro quedaría doble. Si no entró, el pedido sigue guardado para retomarlo con el '
                'cliente.')
        else:
            # Un borrador con orden y sin el identificador de Yappy (un corte a mitad de /iniciar): el botón de Caja no
            # la acepta (RV7, R7-6), así que el pendiente no puede mandar a pulsarlo.
            que_hacer = self.env._(
                'esta orden se quedó a medio abrir (Yappy nunca devolvió su identificador), así que el botón '
                '«Confirmar que el dinero entró» NO la acepta. Si la orden no aparece en el reporte, no pasó nada y el '
                'pedido sigue guardado para retomarlo con el cliente. Si aparece con el dinero, es un caso raro: NO '
                'registres el cobro a mano en el diario (si el aviso llegara tarde, el cobro quedaría doble) y avisa a '
                'quien programa, con el número de la orden.')
        self._dcasa_yappy_alertar(
            self.env._(
                'Pasaron más de 15 minutos desde que se le mandó a Yappy la orden %(orden)s (pedido %(pedido)s, '
                '%(monto)s %(moneda)s, cliente %(cliente)s) %(que_paso)s Yappy cierra la solicitud a los '
                '5 minutos. Abre el reporte de Yappy Comercial y busca la orden %(orden)s (empieza con el número del '
                'pedido): %(que_hacer)s El sistema no pagó ni canceló nada solo. Compró: %(detalle)s',
                orden=self.dcasa_yappy_orden, pedido=pedido.name or '—', monto=float_repr(self.amount, 2),
                moneda=self.currency_id.name,
                cliente=(f"{resumen.cita(pedido.partner_id.name)} {resumen.cita(resumen.celular_del_cliente(pedido))}"
                         if pedido else '—'),
                que_paso=que_paso, que_hacer=que_hacer, detalle=detalle or '—'),
            self.env._('Yappy: sin aviso de pago (%s)', self.dcasa_yappy_orden), destinos=destinos)
