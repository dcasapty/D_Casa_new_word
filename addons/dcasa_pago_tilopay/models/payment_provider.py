"""El proveedor «Tilopay»: lee sus claves del entorno del contenedor y decide si se ofrece en la tienda.

Las claves NO tienen campo: no hay dónde guardarlas ni dónde mostrarlas. La pantalla enseña solo «Conectado» (están
las tres
cargadas) y «Entorno» (lo que dice ``TILOPAY_ENTORNO``). «Probar conexión» abre sesión en Tilopay y dice sí o no.
"""
import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.addons.dcasa_base import _nombrar
from odoo.addons.payment import utils as payment_utils
from odoo.exceptions import AccessError, UserError

from . import tilopay_api as api_tilopay

_logger = logging.getLogger(__name__)

CODIGO = 'tilopay'
NOMBRE = 'Tilopay'
NOMBRE_DEL_METODO = 'Tarjeta, Yappy y más (Tilopay)'
CODIGO_DIARIO = 'TLP'
NOMBRE_DIARIO = 'Tilopay'

# Lo que lee el cliente (voz de D'CASA: de tú, sin gritos).
MENSAJES = {
    'pre_msg': 'Pagar con tarjeta o Yappy: te llevamos a la página segura de Tilopay, pagas ahí y regresas a la '
               'tienda. Tu pedido se confirma apenas Tilopay nos avisa.',
    'pending_msg': 'Estamos esperando que Tilopay confirme tu pago. Toma unos segundos; no cierres esta página.',
    'done_msg': '¡Pago recibido! Confirmamos tu pedido y te escribimos para coordinar la entrega.',
    'cancel_msg': 'El pago no se completó. Tu pedido sigue guardado: puedes intentarlo de nuevo o elegir otra forma '
                  'de pago.',
}


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[(CODIGO, NOMBRE)], ondelete={CODIGO: 'set default'})
    dcasa_tilopay_conectado = fields.Selection(
        [('si', 'Sí'), ('no', 'No')], string='Conectado', compute='_compute_dcasa_tilopay')
    dcasa_tilopay_entorno = fields.Selection(
        [(api_tilopay.PRUEBA, 'Prueba'), (api_tilopay.PRODUCCION, 'Producción')], string='Entorno',
        compute='_compute_dcasa_tilopay')
    dcasa_tilopay_aviso = fields.Text(string='Estado en la tienda', compute='_compute_dcasa_tilopay')
    dcasa_tilopay_prueba_fecha = fields.Datetime('Última prueba de conexión', readonly=True, copy=False)
    dcasa_tilopay_prueba_ok = fields.Boolean('La última prueba salió bien', readonly=True, copy=False)
    dcasa_tilopay_prueba_texto = fields.Char(string='Última prueba', compute='_compute_dcasa_tilopay')

    # ------------------------------------------------------------------ lo que se ve (nunca una clave)

    @api.depends('code', 'state', 'dcasa_tilopay_prueba_fecha', 'dcasa_tilopay_prueba_ok')
    def _compute_dcasa_tilopay(self):
        for proveedor in self:
            if proveedor.code != CODIGO:
                proveedor.dcasa_tilopay_conectado = False
                proveedor.dcasa_tilopay_entorno = False
                proveedor.dcasa_tilopay_aviso = False
                proveedor.dcasa_tilopay_prueba_texto = False
                continue
            proveedor.dcasa_tilopay_conectado = 'si' if proveedor._dcasa_tilopay_conectado() else 'no'
            proveedor.dcasa_tilopay_entorno = api_tilopay.entorno_esperado()
            problema = proveedor._dcasa_tilopay_problema()
            proveedor.dcasa_tilopay_aviso = problema or self.env._(
                'Listo: Tilopay aparece en la tienda como «%s».', NOMBRE_DEL_METODO)
            if proveedor.dcasa_tilopay_prueba_fecha:
                proveedor.dcasa_tilopay_prueba_texto = self.env._(
                    '%(resultado)s (%(fecha)s)',
                    resultado=self.env._('salió bien') if proveedor.dcasa_tilopay_prueba_ok else self.env._('falló'),
                    fecha=fields.Datetime.to_string(proveedor.dcasa_tilopay_prueba_fecha))
            else:
                proveedor.dcasa_tilopay_prueba_texto = self.env._('todavía no se ha probado')

    def _dcasa_tilopay_conectado(self):
        """Las tres claves están cargadas en el servidor (no dice si Tilopay las acepta: eso lo dice «Probar
        conexión»)."""
        return api_tilopay.credenciales() is not None

    def _dcasa_tilopay_cliente(self):
        credenciales = api_tilopay.credenciales()
        if credenciales is None:
            raise api_tilopay.ErrorTilopay('claves', 'faltan las claves en el servidor')
        return api_tilopay.Cliente(credenciales)

    def _dcasa_tilopay_entorno(self):
        return api_tilopay.entorno_esperado()

    def _dcasa_tilopay_problema(self):
        """Por qué Tilopay NO se ofrece hoy, en una frase para una persona; ``None`` si se ofrece."""
        self.ensure_one()
        if self.state == 'disabled':
            return self.env._(
                'Está apagado: nadie lo ve en la tienda. Se enciende con «Modo de prueba» o «Habilitado».')
        if not self._dcasa_tilopay_conectado():
            return self.env._('Faltan las claves en Cloudflare (TILOPAY_API_KEY, TILOPAY_API_USER y '
                              'TILOPAY_API_PASSWORD). Mientras tanto, Tilopay no aparece en la tienda.')
        entorno = self._dcasa_tilopay_entorno()
        if self.state == 'enabled' and entorno != api_tilopay.PRODUCCION:
            return self.env._(
                'Cloudflare dice «prueba» (TILOPAY_ENTORNO) y aquí está «Habilitado». Pon «Modo de prueba» o, '
                'cuando vayas a cobrar de verdad, cambia TILOPAY_ENTORNO a «produccion». No se ofrece mientras no '
                'coincidan.')
        if self.state == 'test' and entorno != api_tilopay.PRUEBA:
            return self.env._('Cloudflare dice «produccion» (TILOPAY_ENTORNO) y aquí está en «Modo de prueba». Pon '
                              '«Habilitado» o cambia TILOPAY_ENTORNO a «prueba». No se ofrece mientras no coincidan.')
        return None

    def _dcasa_tilopay_ofrecible(self):
        self.ensure_one()
        return self.code == CODIGO and self._dcasa_tilopay_problema() is None

    # ------------------------------------------------------------------ cuándo se ofrece

    def _get_supported_currencies(self):
        monedas = super()._get_supported_currencies()
        if self.code == CODIGO:
            monedas = monedas.filtered(lambda moneda: moneda.name == 'USD')
        return monedas

    def _get_default_payment_method_codes(self):
        if self.code != CODIGO:
            return super()._get_default_payment_method_codes()
        return {CODIGO}

    def _activate_default_pms(self):
        """Al encender el proveedor se asegura su diario «Tilopay»: sin él, Odoo mandaría el cobro al primer diario de
        banco que encuentre (y los pagos de Tilopay se mezclarían con los del banco)."""
        super()._activate_default_pms()
        for proveedor in self.filtered(lambda p: p.code == CODIGO):
            proveedor._dcasa_tilopay_asegurar_diario()

    @api.model
    def _get_compatible_providers(self, *args, report=None, **kwargs):
        """Tilopay solo se ofrece para pagar un PEDIDO de venta (versión 1) y solo si está activo, con las claves
        cargadas y coherente con ``TILOPAY_ENTORNO``. Sin eso, ni sale ni estorba."""
        proveedores = super()._get_compatible_providers(*args, report=report, **kwargs)
        tilopay = proveedores.filtered(lambda p: p.code == CODIGO)
        if not tilopay:
            return proveedores
        fuera = tilopay.filtered(lambda p: not kwargs.get('sale_order_id') or not p._dcasa_tilopay_ofrecible())
        if fuera:
            payment_utils.add_to_report(report, fuera, available=False, reason=self.env._('Tilopay no está listo'))
        return proveedores - fuera

    # ------------------------------------------------------------------ probar la conexión

    def _dcasa_tilopay_exigir_gerencia(self):
        if not self.env.su and not (self.env.user.has_group('dcasa_base.group_gerencia')
                                    or self.env.user.has_group('base.group_system')):
            raise AccessError(self.env._('Solo Gerencia y los administradores prueban la conexión con Tilopay.'))

    def action_dcasa_tilopay_probar(self):
        """Botón «Probar conexión»: abre sesión en Tilopay y dice sí o no. No muestra ni guarda ningún dato."""
        self._dcasa_tilopay_exigir_gerencia()
        # Ya se comprobó el grupo; el modelo de proveedores solo lo lee el administrador del sistema.
        proveedor = self.sudo()
        proveedor.ensure_one()
        if proveedor.code != CODIGO:
            raise UserError(self.env._('Este botón es solo del proveedor Tilopay.'))
        credenciales = api_tilopay.credenciales()
        if credenciales is None:
            bien, texto = False, self.env._(
                'No hay claves cargadas: pégalas en Cloudflare (ver «Estado en la tienda»).')
        else:
            try:
                api_tilopay.Cliente(credenciales).probar()
                bien, texto = True, self.env._('Sí: Tilopay aceptó el usuario y la contraseña.')
            except api_tilopay.ErrorTilopay as error:
                _logger.warning('Tilopay: la prueba de conexión falló (%s).', error.tipo)
                texto = {
                    'claves': self.env._(
                        'No: Tilopay no aceptó el usuario y la contraseña. Revisa las claves en Cloudflare.'),
                    'red': self.env._('No: no se pudo hablar con Tilopay ahora. Intenta de nuevo en un momento.'),
                }.get(error.tipo, self.env._('No: Tilopay respondió algo inesperado. Intenta de nuevo.'))
                bien = False
        proveedor.write({'dcasa_tilopay_prueba_fecha': fields.Datetime.now(), 'dcasa_tilopay_prueba_ok': bien})
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': self.env._('Conexión con Tilopay'), 'message': texto,
                       'type': 'success' if bien else 'danger', 'sticky': not bien,
                       # Que «Última prueba» se actualice en la pantalla sin que haya que recargarla.
                       'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }

    # ------------------------------------------------------------------ al instalar

    def _dcasa_tilopay_preparar(self):
        """El diario «Tilopay», el nombre y los mensajes en español. Se puede repetir sin duplicar nada."""
        self.ensure_one()
        proveedor = self.sudo()
        diario = proveedor._dcasa_tilopay_diario()
        if diario and not proveedor.journal_id:
            proveedor.journal_id = diario
        _nombrar(proveedor, NOMBRE)
        idiomas = [codigo for codigo, _n in self.env['res.lang'].get_installed()]
        for idioma in idiomas:
            escrito = proveedor.with_context(lang=idioma)
            for campo, texto in MENSAJES.items():
                escrito[campo] = Markup('<p>%s</p>') % texto
        metodo = self.env.ref('dcasa_pago_tilopay.payment_method_tilopay', raise_if_not_found=False)
        if metodo:
            _nombrar(metodo.sudo(), NOMBRE_DEL_METODO)

    def _dcasa_tilopay_asegurar_diario(self):
        """Si el proveedor todavía no tiene un diario propio (un método de cobro ligado a él), lo liga al «Tilopay»."""
        self.ensure_one()
        proveedor = self.sudo()
        ligado = self.env['account.payment.method.line'].sudo().search_count(
            [('payment_provider_id', '=', proveedor.id), ('journal_id', '!=', False)], limit=1)
        if not ligado:
            proveedor.journal_id = proveedor._dcasa_tilopay_diario()

    def _dcasa_tilopay_diario(self):
        """El diario de banco «Tilopay» de la empresa del proveedor (lo crea si no existe)."""
        self.ensure_one()
        Diario = self.env['account.journal'].sudo().with_context(active_test=False)
        diario = Diario.search([('company_id', '=', self.company_id.id), ('code', '=', CODIGO_DIARIO)], limit=1)
        if not diario:
            diario = Diario.search([('company_id', '=', self.company_id.id), ('name', '=', NOMBRE_DIARIO),
                                    ('type', '=', 'bank')], limit=1)
        if not diario:
            diario = Diario.create({
                'name': NOMBRE_DIARIO, 'code': CODIGO_DIARIO, 'type': 'bank', 'company_id': self.company_id.id})
            _logger.info("D'CASA: diario «%s» creado para los cobros de Tilopay (la contadora revisa su cuenta).",
                         NOMBRE_DIARIO)
        return diario
