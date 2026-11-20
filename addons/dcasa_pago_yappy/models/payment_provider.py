"""El proveedor «Yappy directo»: lee sus claves del entorno del contenedor y decide si se ofrece en la tienda.

Las claves NO tienen campo: no hay dónde guardarlas ni dónde mostrarlas. La pantalla enseña «Claves cargadas» (qué
variables faltan, por su nombre, nunca un valor), el «Entorno» (lo que dice ``YAPPY_ENTORNO``) y el dominio declarado
(no es secreto: es la dirección pública del sitio, y compararlo letra por letra con el de Yappy Comercial es lo que más
falla). «Probar conexión» le pide a Yappy que valide el ID de comercio y el dominio; la clave secreta solo se usa para
firmar el aviso y no se puede comprobar sin un cobro (el mensaje lo dice).
"""
import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.addons.dcasa_base import _nombrar
from odoo.addons.payment import utils as payment_utils
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import format_datetime

from . import yappy_api as api_yappy

_logger = logging.getLogger(__name__)

CODIGO = 'yappy'
CODIGO_DEL_METODO = 'yappy_directo'
# el «Yappy» de la tienda de siempre (website_dcasa): se pide el número por WhatsApp
CODIGO_DEL_METODO_MANUAL = 'yappy'
NOMBRE = 'Yappy directo'
NOMBRE_DEL_METODO = 'Yappy'
# el mismo diario «Yappy» que dcasa_base crea para los cobros de la tienda (si no existe, se crea igual)
CODIGO_DIARIO = 'YAPPY'
NOMBRE_DIARIO = 'Yappy'

# Lo que lee el cliente (voz de D'CASA: de tú, sin gritos). El título del estado («Pago recibido», «El pago no se
# completó») lo pone la pantalla (website_dcasa, pago_templates.xml): aquí va lo que sigue.
MENSAJES = {
    'pre_msg': 'Pagas desde tu app de Yappy. Tu pedido se confirma apenas Yappy nos avisa.',
    'pending_msg': 'Estamos esperando que Yappy confirme tu pago. Toma unos segundos; no cierres esta página.',
    'done_msg': 'Confirmamos tu pedido y te escribimos para coordinar la entrega.',
    'cancel_msg': 'Tu pedido sigue guardado: puedes intentarlo de nuevo o elegir otra forma de pago.',
}


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[(CODIGO, NOMBRE)], ondelete={CODIGO: 'set default'})
    dcasa_yappy_conectado = fields.Selection(
        [('si', 'Sí'), ('no', 'No')], string='Claves de Yappy cargadas', compute='_compute_dcasa_yappy',
        help='Las dos claves (ID de comercio y clave secreta) y el dominio están cargados en el servidor. No dice que '
             'Yappy las acepte: eso lo dice «Probar conexión» (ID de comercio y dominio) y el primer cobro de prueba '
             '(la clave secreta, que firma el aviso).')
    dcasa_yappy_entorno = fields.Selection(
        [(api_yappy.PRUEBA, 'Prueba'), (api_yappy.PRODUCCION, 'Producción')], string='Entorno de Yappy',
        compute='_compute_dcasa_yappy')
    dcasa_yappy_dominio = fields.Char(
        string='Dominio declarado', compute='_compute_dcasa_yappy',
        help='Lo que dice YAPPY_DOMINIO. Tiene que ser, letra por letra, lo que se escribió en Yappy Comercial al '
             'crear el botón: viaja en cada cobro y entra en la firma del aviso. No es un secreto (es la dirección '
             'del sitio).')
    dcasa_yappy_aviso = fields.Text(string='Yappy en la tienda', compute='_compute_dcasa_yappy')
    dcasa_yappy_prueba_fecha = fields.Datetime('Última prueba de conexión con Yappy', readonly=True, copy=False)
    dcasa_yappy_prueba_ok = fields.Boolean('La última prueba con Yappy salió bien', readonly=True, copy=False)
    dcasa_yappy_prueba_texto = fields.Char(string='Última prueba con Yappy', compute='_compute_dcasa_yappy')

    # ------------------------------------------------------------------ lo que se ve (nunca una clave)

    @api.depends('code', 'state', 'dcasa_yappy_prueba_fecha', 'dcasa_yappy_prueba_ok')
    def _compute_dcasa_yappy(self):
        for proveedor in self:
            if proveedor.code != CODIGO:
                proveedor.dcasa_yappy_conectado = False
                proveedor.dcasa_yappy_entorno = False
                proveedor.dcasa_yappy_dominio = False
                proveedor.dcasa_yappy_aviso = False
                proveedor.dcasa_yappy_prueba_texto = False
                continue
            proveedor.dcasa_yappy_conectado = 'si' if proveedor._dcasa_yappy_conectado() else 'no'
            proveedor.dcasa_yappy_entorno = api_yappy.entorno_esperado()
            proveedor.dcasa_yappy_dominio = api_yappy._variable(api_yappy.VARIABLE_DOMINIO) or False
            problema = proveedor._dcasa_yappy_problema()
            proveedor.dcasa_yappy_aviso = problema or self.env._(
                'Listo: Yappy aparece en la tienda como «%s» y reemplaza al «Yappy» de siempre.', NOMBRE_DEL_METODO)
            if proveedor.dcasa_yappy_prueba_fecha:
                proveedor.dcasa_yappy_prueba_texto = self.env._(
                    '%(resultado)s (%(fecha)s)',
                    resultado=(self.env._('Yappy validó el comercio y el dominio (la clave secreta se comprueba en el '
                                          'primer cobro de prueba)')
                               if proveedor.dcasa_yappy_prueba_ok else self.env._('falló')),
                    fecha=format_datetime(self.env, proveedor.dcasa_yappy_prueba_fecha, dt_format='medium'))
            else:
                proveedor.dcasa_yappy_prueba_texto = self.env._('todavía no se ha probado')

    def _dcasa_yappy_conectado(self):
        """Las claves y el dominio están cargados en el servidor (no dice si Yappy los acepta)."""
        return api_yappy.credenciales() is not None

    def _dcasa_yappy_cliente(self):
        credenciales = api_yappy.credenciales()
        if credenciales is None:
            raise api_yappy.ErrorYappy('comercio', 'faltan las claves en el servidor')
        return api_yappy.Cliente(credenciales)

    def _dcasa_yappy_entorno(self):
        return api_yappy.entorno_esperado()

    def _should_build_inline_form(self, is_validation=False):
        if self.code != CODIGO:
            return super()._should_build_inline_form(is_validation=is_validation)
        return not is_validation

    def _dcasa_yappy_celular_sugerido(self, pedido):
        """El celular de Yappy que ya se escribe en el campo: el del cliente del pedido, si es un celular de Panamá (la
        clienta lo corrige si su Yappy es de otro número). Vacío si no hay uno que sirva."""
        partner = pedido.sudo().partner_id if pedido else False
        if not partner:
            return ''
        celular = api_yappy.celular_de_yappy(partner.phone or getattr(partner, 'mobile', '') or '')
        return f'{celular[:4]} {celular[4:]}' if celular else ''

    def _dcasa_yappy_cdn(self):
        """El script del botón de Yappy del entorno, para la página de pago (solo los dos de Yappy)."""
        return api_yappy.cdn(self._dcasa_yappy_entorno())

    def _dcasa_yappy_problema(self):
        """Por qué Yappy NO se ofrece hoy, en una frase para una persona; ``None`` si se ofrece."""
        self.ensure_one()
        if self.state == 'disabled':
            return self.env._(
                'Está apagado: nadie lo ve en la tienda. Se enciende con «Modo de prueba» o «Habilitado».')
        faltan = api_yappy.faltantes()
        if faltan:
            return self.env._(
                'Faltan cosas en Cloudflare: %s. Mientras tanto, Yappy directo no aparece en la tienda y sigue el '
                '«Yappy» de siempre (te escribimos por WhatsApp).', ', '.join(faltan))
        entorno = self._dcasa_yappy_entorno()
        if api_yappy.entorno_pedido() == api_yappy.PRODUCCION and not api_yappy.servidor_es_produccion():
            if self.state == 'enabled':
                return self.env._(
                    'YAPPY_ENTORNO dice «produccion», pero este servidor no es el de producción: aquí Yappy solo '
                    'cobra en prueba. Pon «Modo de prueba».')
        if self.state == 'enabled' and entorno != api_yappy.PRODUCCION:
            return self.env._(
                'Cloudflare dice «prueba» (YAPPY_ENTORNO) y aquí está «Habilitado». Pon «Modo de prueba» o, cuando '
                'vayas a cobrar de verdad, cambia YAPPY_ENTORNO a «produccion». No se ofrece mientras no coincidan.')
        if self.state == 'test' and entorno != api_yappy.PRUEBA:
            return self.env._(
                'Cloudflare dice «produccion» (YAPPY_ENTORNO) y aquí está en «Modo de prueba». Pon «Habilitado» o '
                'cambia YAPPY_ENTORNO a «prueba». No se ofrece mientras no coincidan.')
        return None

    def _dcasa_yappy_ofrecible(self):
        self.ensure_one()
        return self.code == CODIGO and self._dcasa_yappy_problema() is None

    def _dcasa_yappy_solo_para_el_equipo(self):
        """Verdadero si este proveedor no es para el público: sin publicar (p. ej. en «Modo de prueba», para que lo
        pruebe el equipo), o en «Modo de prueba» en el servidor de PRODUCCIÓN aunque se pulse «Publicado» por error."""
        self.ensure_one()
        return not self.is_published or (self.state == 'test' and api_yappy.servidor_es_produccion())

    # ------------------------------------------------------------------ cuándo se ofrece

    def _get_supported_currencies(self):
        monedas = super()._get_supported_currencies()
        if self.code == CODIGO:
            monedas = monedas.filtered(lambda moneda: moneda.name == 'USD')
        return monedas

    def _get_default_payment_method_codes(self):
        if self.code != CODIGO:
            return super()._get_default_payment_method_codes()
        return {CODIGO_DEL_METODO}

    def _activate_default_pms(self):
        """Al encender el proveedor se asegura su diario «Yappy»: sin él, Odoo mandaría el cobro al primer diario de
        banco que encuentre (y los pagos de Yappy se mezclarían con los del banco)."""
        super()._activate_default_pms()
        for proveedor in self.filtered(lambda p: p.code == CODIGO):
            proveedor._dcasa_yappy_asegurar_diario()

    @api.model
    def _get_compatible_providers(self, *args, report=None, **kwargs):
        """Yappy directo solo se ofrece para pagar un PEDIDO de venta (versión 1) y solo si está activo, con las claves
        cargadas y coherente con ``YAPPY_ENTORNO``. Cuando SÍ se ofrece, el «Yappy» manual de siempre (el que pide el
        número por WhatsApp) deja de ofrecerse: nunca se ven dos «Yappy». Si no se ofrece, el manual sigue como hoy."""
        proveedores = super()._get_compatible_providers(*args, report=report, **kwargs)
        directo = proveedores.filtered(lambda p: p.code == CODIGO)
        if not directo:
            return proveedores
        interno = self.env.user._is_internal()
        fuera = directo.filtered(
            lambda p: not kwargs.get('sale_order_id') or not p._dcasa_yappy_ofrecible()
            or (not interno and p._dcasa_yappy_solo_para_el_equipo()))
        if fuera:
            payment_utils.add_to_report(
                report, fuera, available=False, reason=self.env._('Yappy directo no está listo'))
        proveedores -= fuera
        if directo - fuera:
            manuales = proveedores.filtered(lambda p: CODIGO_DEL_METODO_MANUAL in p.payment_method_ids.mapped('code'))
            if manuales:
                payment_utils.add_to_report(
                    report, manuales, available=False, reason=self.env._('Yappy directo ya está encendido'))
                proveedores -= manuales
        return proveedores

    # ------------------------------------------------------------------ probar la conexión

    def _dcasa_yappy_exigir_gerencia(self):
        if not self.env.su and not (self.env.user.has_group('dcasa_base.group_gerencia')
                                    or self.env.user.has_group('base.group_system')):
            raise AccessError(self.env._('Solo Gerencia y los administradores prueban la conexión con Yappy.'))

    def action_dcasa_yappy_probar(self):
        """Botón «Probar conexión»: le pide a Yappy que valide el ID de comercio y el dominio (paso 1 del cobro; no crea
        ninguna orden ni cobra). La clave secreta no se puede comprobar aquí: solo firma el aviso. No muestra ni guarda
        ningún dato de Yappy (el token se tira)."""
        self._dcasa_yappy_exigir_gerencia()
        proveedor = self.sudo()      # ya se comprobó el grupo; el modelo de proveedores solo lo lee el administrador
        proveedor.ensure_one()
        if proveedor.code != CODIGO:
            raise UserError(self.env._('Este botón es solo del proveedor Yappy directo.'))
        credenciales = api_yappy.credenciales()
        if credenciales is None:
            bien, texto = False, self.env._('Faltan claves o dominio en Cloudflare (ver «Yappy en la tienda»).')
        else:
            try:
                api_yappy.Cliente(credenciales).validar_comercio()
                bien, texto = True, self.env._(
                    'Yappy validó el ID de comercio y el dominio. La clave secreta se comprueba en el primer cobro de '
                    'prueba (es la que firma el aviso).')
            except api_yappy.ErrorYappy as error:
                _logger.warning('Yappy: la prueba de conexión falló (%s, %s).', error.tipo, error.codigo or '-')
                texto = {
                    'comercio': self.env._(
                        'No: Yappy no validó el comercio. Lo más común es que el dominio no sea, letra por letra, el '
                        'que está en Yappy Comercial (revisa «Dominio declarado»), o que el ID de comercio sea de '
                        'otro entorno.'),
                    'red': self.env._('No: no se pudo hablar con Yappy ahora. Intenta de nuevo en un momento.'),
                }.get(error.tipo, self.env._('No: Yappy respondió algo inesperado. Intenta de nuevo.'))
                bien = False
        proveedor.write({'dcasa_yappy_prueba_fecha': fields.Datetime.now(), 'dcasa_yappy_prueba_ok': bien})
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': self.env._('Conexión con Yappy'), 'message': texto,
                       'type': 'warning' if bien else 'danger', 'sticky': not bien,
                       'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }

    # ------------------------------------------------------------------ al instalar

    def _dcasa_yappy_preparar(self):
        """El diario «Yappy» (el de siempre de dcasa_base: los cobros de Yappy directo caen donde ya caen los de Yappy a
        mano), el nombre y los mensajes en español. Se puede repetir sin duplicar nada."""
        self.ensure_one()
        proveedor = self.sudo()
        diario = proveedor._dcasa_yappy_diario()
        if diario and not proveedor.journal_id:
            proveedor.journal_id = diario
        _nombrar(proveedor, NOMBRE)
        idiomas = [codigo for codigo, _n in self.env['res.lang'].get_installed()]
        for idioma in idiomas:
            escrito = proveedor.with_context(lang=idioma)
            for campo, texto in MENSAJES.items():
                escrito[campo] = Markup('<p>%s</p>') % texto
        metodo = self.env.ref('dcasa_pago_yappy.payment_method_yappy', raise_if_not_found=False)
        if metodo:
            _nombrar(metodo.sudo(), NOMBRE_DEL_METODO)

    def _dcasa_yappy_asegurar_diario(self):
        """Si el proveedor todavía no tiene un diario propio (un método de cobro ligado a él), lo liga al «Yappy»."""
        self.ensure_one()
        proveedor = self.sudo()
        ligado = self.env['account.payment.method.line'].sudo().search_count(
            [('payment_provider_id', '=', proveedor.id), ('journal_id', '!=', False)], limit=1)
        if not ligado:
            proveedor.journal_id = proveedor._dcasa_yappy_diario()

    def _dcasa_yappy_diario(self):
        """El diario de banco «Yappy» de la empresa del proveedor (lo crea si no existe)."""
        self.ensure_one()
        Diario = self.env['account.journal'].sudo().with_context(active_test=False)
        diario = Diario.search([('company_id', '=', self.company_id.id), ('code', '=', CODIGO_DIARIO)], limit=1)
        if not diario:
            diario = Diario.search([('company_id', '=', self.company_id.id), ('name', '=', NOMBRE_DIARIO),
                                    ('type', '=', 'bank')], limit=1)
        if not diario:
            diario = Diario.create({
                'name': NOMBRE_DIARIO, 'code': CODIGO_DIARIO, 'type': 'bank', 'company_id': self.company_id.id})
            _logger.info("D'CASA: diario «%s» creado para los cobros de Yappy (la contadora revisa su cuenta).",
                         NOMBRE_DIARIO)
        return diario
