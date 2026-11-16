"""Campaña del sitio (Black Friday, Black Weekend…), manejada desde el panel por Gerencia.

Pedido de la dueña (2026-11-15): «desde el lugar de productos en el panel administrativo… marcar una casilla y ya
salían». Antes, la campaña Black Weekend se encendía con parámetros que fijaba el arranque del contenedor y los
productos se marcaban desde el Excel del catálogo (models/black_weekend.py).

* ``dcasa.campana``: una por sitio. Nombre, fechas desde/hasta (hora de Panamá, inclusivas) y una frase corta. Con
  alguna fecha puesta, manda ella; sin fechas, sigue mandando la ventana de los parámetros de siempre (que en
  producción ya pasó): ``website._dcasa_bw_ventana``.
* Los productos: la casilla ``dcasa_black_weekend`` (ahora «En la campaña»), su orden y un **precio de campaña**
  opcional (sin ITBMS, como el precio de venta).
* El precio de campaña se cobra de verdad: se escribe como regla de las tarifas del sitio (``product.pricelist.item``
  con ``dcasa_campana``) con las mismas fechas, así que el carrito, la ficha, Brian y Juan ven el mismo precio y al
  terminar vuelve solo el normal. La regla es «precio normal − (normal − campaña)»: en un producto con colores o
  medidas de precio distinto, cada variante baja lo mismo y conserva su diferencia (una regla de precio fijo las
  dejaría todas iguales). Sin las dos fechas no se crea ninguna regla: un precio rebajado sin fin no sale solo.
* La sincronización solo toca las reglas que cambian (crear, actualizar o borrar), porque cada cambio de una tarifa
  hace regenerar toda la tienda del borde (dcasa_tienda_borde).
* Revisión adversarial (2026-11-16, dos vueltas): los campos de la campaña los cambia solo quien cambia precios
  (Gerencia, administradores); las reglas van solo en las tarifas que el sitio ofrece y se quedan 30 días después del
  fin (una cotización o un apartado de la campaña conserva su precio autorizado); la fecha de una cotización solo la
  cambia quien cambia precios (si no, se podría fechar dentro de la campaña); una variante nunca queda en cero o
  negativa; un producto tipo combo no lleva precio de campaña; el carrito se pone al día al pagar y en los bordes de
  la campaña (cron disparado a la hora exacta).
* «Los combos son inamovibles» (la dueña, 2026-11-16: «no quiero tocar en absoluto los combos… aunque se pudiera…
  romper la regla, por ahora no quiero romperla. Pero debería poderse»): la cama y el colchón de un combo armado en la
  cotización (dcasa_catalogo, ``combo_armable.py``) se calculan con la bandera de contexto ``COMBO_SIN_CAMPANA``, que
  saca de la tarifa las reglas de campaña; las demás reglas siguen. El interruptor «La campaña también rebaja los
  combos» (``dcasa_rebaja_combos``, apagado; solo Gerencia y administradores) lo deshace: la bandera no saca las reglas
  de una campaña con el interruptor encendido (cada regla sabe de qué campaña es, ``dcasa_campana_id``; cambiar el
  interruptor no reescribe ninguna regla, así la tienda del borde no se regenera entera).
* Las banderas internas de contexto (esta y las de los combos) valen solo con ``INTERNO``, un objeto de Python que
  una llamada por RPC (JSON) no puede fabricar: mandarlas desde afuera no salta ninguna regla.
* Una línea de una venta que no es de la web se calcula con la fecha en que se agregó (``dcasa_fecha_precio``), no con
  la de la cotización: una cotización abierta en la campaña no le da el precio de campaña a una línea nueva después
  del fin (las reglas siguen 30 días para las líneas que ya tenía). Revisión adversarial, tercera vuelta (I-B).
"""
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.addons.dcasa_base.models.product import _puede_cambiar_precios
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, float_round

_logger = logging.getLogger(__name__)

ZONA = pytz.timezone('America/Panama')
# Lo último que rigió de la campaña cuando se pusieron al día los carritos (``_dcasa_campana_carritos_al_dia``).
PARAM_FIRMA_CARRITOS = 'website_dcasa.campana_firma_carritos'
# Carritos más viejos que esto (sin tocar) no se recalculan con el cron (al pagar, sí: ``_check_cart``).
DIAS_DE_CARRITO = 30
# Las reglas de campaña se quedan este tiempo después del fin: una cotización o un apartado hecho en la campaña sigue
# con su precio autorizado (dcasa_base calcula el precio permitido con la fecha del pedido). Para nuevos pedidos no
# cuentan: sus fechas ya pasaron.
DESPUES_DEL_FIN = timedelta(days=30)
# Lo que define la campaña de un producto: lo cambia solo quien cambia precios (dcasa_base, CAMPOS_SOLO_GERENCIA).
CAMPOS_CAMPANA = frozenset({'dcasa_black_weekend', 'dcasa_bw_orden', 'dcasa_bw_variante_id', 'dcasa_campana_precio'})
# Contexto para escribir muchos productos y sincronizar una sola vez al final.
SIN_SINCRONIZAR = 'dcasa_campana_sin_sincronizar'
# El valor de las banderas internas de contexto: un objeto que JSON no puede fabricar (una llamada por RPC que mande la
# clave con ``true`` no vale). Se compara con ``is`` (``es_interno``).
INTERNO = object()
# Contexto con que se calcula una pieza de un combo armado (dcasa_catalogo): la tarifa sin las reglas de campaña, salvo
# las de una campaña que también rebaja los combos (``dcasa_rebaja_combos``). Su valor: ``INTERNO``.
COMBO_SIN_CAMPANA = 'dcasa_tarifa_sin_campana'


def es_interno(env, clave):
    """¿Trae el contexto la bandera interna ``clave`` puesta por el código (no por una llamada de afuera)?"""
    return env.context.get(clave) is INTERNO


def _exigir_precios(env):
    if not _puede_cambiar_precios(env):
        raise AccessError(env._('Solo Gerencia y los administradores cambian la campaña del sitio y sus precios.'))


def _exigir_gerencia(env):
    """El interruptor de los combos: solo Gerencia y los administradores (no basta con poder cambiar precios)."""
    if not (env.su or env.user.has_group('dcasa_base.group_gerencia') or env.user.has_group('base.group_system')):
        raise AccessError(env._('Solo Gerencia y los administradores deciden si la campaña también rebaja los combos.'))


def limites_utc(inicio, fin):
    """(desde, hasta) en UTC sin zona, como los guarda Odoo: de las 00:00:00 del inicio a las 23:59:59 del fin."""
    desde = ZONA.localize(datetime.combine(inicio, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
    hasta = ZONA.localize(datetime.combine(fin, time(23, 59, 59))).astimezone(pytz.utc).replace(tzinfo=None)
    return desde, hasta


class DcasaCampana(models.Model):
    _name = 'dcasa.campana'
    _description = 'Campaña del sitio'
    _inherit = ['mail.thread']
    _order = 'id'

    name = fields.Char('Nombre', required=True, default='Black Friday', tracking=True,
                       help='Sale en la portada, en la página de la campaña y en la etiqueta de las tarjetas.')
    website_id = fields.Many2one('website', 'Sitio', required=True, ondelete='cascade', index=True,
                                 default=lambda self: self.env['website'].get_current_website())
    fecha_inicio = fields.Date('Desde', tracking=True,
                               help='Primer día de la campaña (desde las 00:00, hora de Panamá).')
    fecha_fin = fields.Date('Hasta', tracking=True,
                            help='Último día de la campaña (hasta las 23:59, hora de Panamá).')
    frase = fields.Char('Frase corta', tracking=True,
                        help='Debajo del título en la portada y en la página. Sin cifras inventadas: los precios '
                             'salen de cada producto.')
    dcasa_rebaja_combos = fields.Boolean(
        'La campaña también rebaja los combos', default=False, tracking=True,
        help='Apagado (lo normal): los combos cama + colchón que se arman en la cotización van a su precio de siempre, '
             'sin el precio de campaña, aunque la cama o el colchón lo tengan. Encendido: la cama y el colchón del '
             'combo también toman el precio de campaña. Solo lo cambian Gerencia y los administradores.')
    estado = fields.Selection([('apagada', 'Apagada'), ('programada', 'Programada'), ('activa', 'Activa ahora'),
                               ('terminada', 'Terminada')], compute='_compute_estado')
    producto_count = fields.Integer('Productos en la campaña', compute='_compute_producto_count')
    tarifas_apagadas = fields.Boolean(compute='_compute_tarifas_apagadas')
    con_precio_count = fields.Integer('Con precio de campaña', compute='_compute_producto_count')

    _sitio_unico = models.Constraint('unique(website_id)', 'Cada sitio tiene una sola campaña.')

    @api.constrains('fecha_inicio', 'fecha_fin')
    def _check_fechas(self):
        for campana in self:
            if campana.fecha_inicio and campana.fecha_fin and campana.fecha_inicio > campana.fecha_fin:
                raise ValidationError(self.env._('La fecha «Hasta» no puede ser antes de «Desde».'))

    @api.depends('fecha_inicio', 'fecha_fin')
    def _compute_estado(self):
        hoy = datetime.now(pytz.utc).astimezone(ZONA).date()
        for campana in self:
            inicio, fin = campana.fecha_inicio, campana.fecha_fin
            if not (inicio or fin):
                campana.estado = 'apagada'
            elif inicio and hoy < inicio:
                campana.estado = 'programada'
            elif fin and hoy > fin:
                campana.estado = 'terminada'
            else:
                campana.estado = 'activa'

    def _compute_tarifas_apagadas(self):
        apagadas = not self.env['res.groups']._is_feature_enabled('product.group_product_pricelist')
        for campana in self:
            campana.tarifas_apagadas = apagadas

    def _compute_producto_count(self):
        Producto = self.env['product.template'].sudo()
        marcados = Producto.search_count([('dcasa_black_weekend', '=', True)])
        con_precio = Producto.search_count([('dcasa_black_weekend', '=', True), ('dcasa_campana_precio', '>', 0)])
        for campana in self:
            campana.producto_count = marcados
            campana.con_precio_count = con_precio

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('dcasa_rebaja_combos') for vals in vals_list):
            _exigir_gerencia(self.env)
        campanas = super().create(vals_list)
        self.env['product.template']._dcasa_campana_sincronizar()
        campanas._dcasa_campana_programar()
        return campanas

    def write(self, vals):
        if 'dcasa_rebaja_combos' in vals:
            _exigir_gerencia(self.env)
        resultado = super().write(vals)
        # El interruptor de los combos no toca las reglas: lo lee la tarifa al calcular (_get_applicable_rules_domain).
        if {'fecha_inicio', 'fecha_fin', 'website_id'} & set(vals):
            self.env['product.template']._dcasa_campana_sincronizar()
            self._dcasa_campana_programar()
        return resultado

    def unlink(self):
        resultado = super().unlink()
        self.env['product.template']._dcasa_campana_sincronizar()
        return resultado

    def _dcasa_campana_momentos(self):
        """Los momentos en que cambia lo que rige: el inicio, el fin y cuando se quitan las reglas."""
        momentos = []
        for campana in self.filtered(lambda c: c.fecha_inicio and c.fecha_fin):
            desde, hasta = limites_utc(campana.fecha_inicio, campana.fecha_fin)
            momentos += [desde, hasta + timedelta(seconds=1), hasta + DESPUES_DEL_FIN + timedelta(minutes=1)]
        return [m for m in momentos if m > fields.Datetime.now()]

    def _dcasa_campana_programar(self):
        """El cron de los carritos corre justo en el inicio y el fin (no esperar a la hora siguiente)."""
        cron = self.env.ref('website_dcasa.ir_cron_dcasa_campana_carritos', raise_if_not_found=False)
        if cron:
            for momento in self._dcasa_campana_momentos():
                cron.sudo()._trigger(at=momento)

    @api.model
    def _dcasa_tarifa_del_sitio(self):
        """Deja la tarifa del visitante disponible en cada sitio (se llama al instalar o actualizar el módulo).

        En esta base la tarifa general («Default») no estaba ofrecida al sitio: el visitante no tenía tarifa
        (``request.pricelist`` vacío) y la página mostraba el precio del producto a secas, mientras el carrito sí la
        usaba (la del contacto). Con una regla de campaña, la página diría el precio normal y el carrito cobraría el
        de campaña. Marcarla «seleccionable» la ofrece al sitio; con una sola tarifa Odoo no muestra ningún selector
        y los precios no cambian (no tiene otras reglas). No toca nada si ya hay una tarifa ofrecida.
        """
        if not self.env['res.groups']._is_feature_enabled('product.group_product_pricelist'):
            return
        for sitio in self.env['website'].sudo().search([]):
            if self.env['product.pricelist'].sudo().search_count(
                    self.env['product.pricelist']._get_website_pricelists_domain(sitio), limit=1):
                continue
            # La tarifa pública de Odoo; si no está, la del visitante sin sesión.
            tarifa = self.env.ref('product.list0', raise_if_not_found=False)
            if not (tarifa and tarifa.active and tarifa.company_id in (sitio.company_id, self.env['res.company'])):
                tarifa = sitio.user_id.sudo().partner_id.property_product_pricelist
            if tarifa and not tarifa.website_id:
                tarifa.write({'selectable': True})
                _logger.info('Campaña: la tarifa %s queda ofrecida al sitio %s.', tarifa.display_name, sitio.name)

    @api.model
    def _dcasa_campana_firma(self, ahora=None):
        """Lo que rige en este momento: «plantilla:rebaja» de cada regla de campaña en fechas, ordenado."""
        momento = ahora or fields.Datetime.now()
        reglas = self.env['product.pricelist.item'].sudo().search([
            ('dcasa_campana', '=', True), ('date_start', '<=', momento), ('date_end', '>=', momento)])
        return ','.join(sorted({f'{r.product_tmpl_id.id}:{r.price_surcharge:.2f}' for r in reglas}))

    @api.model
    def _dcasa_campana_carritos_al_dia(self, ahora=None):
        """Cron horario: si cambió lo que rige (empieza o termina la campaña, o cambió un precio o una fecha), pone al
        día los precios de los carritos abiertos de la tienda que tienen alguno de esos productos.

        Odoo calcula cada línea nueva del carrito con la hora actual, pero no vuelve a calcular las que ya estaban: una
        cama puesta el 26 seguiría a precio normal el 27 aunque la página diga el de campaña. Solo carritos (borrador,
        de la tienda, sin fecha de apartado); nunca un apartado ni un pedido confirmado. Devuelve cuántos tocó.
        """
        self.env['product.template']._dcasa_campana_sincronizar(ahora)   # crear o borrar reglas según la hora
        param = self.env['ir.config_parameter'].sudo()
        firma = self._dcasa_campana_firma(ahora)
        # El registro de verdad: get_param lee igual «no existe» y «vacío» (sin campaña), y vacío → campaña es justo
        # cuando hay que poner al día los carritos.
        registro = param.search([('key', '=', PARAM_FIRMA_CARRITOS)], limit=1)
        antes = (registro.value or '') if registro else None
        if antes == firma:
            return 0
        param.set_param(PARAM_FIRMA_CARRITOS, firma)
        if antes is None:
            return 0   # primera vez: solo se anota lo que rige
        plantillas = {int(par.split(':')[0]) for par in (antes or '').split(',') + firma.split(',') if par}
        if not plantillas:
            return 0
        Pedido = self.env['sale.order'].sudo()
        dominio = [('state', '=', 'draft'), ('website_id', '!=', False),
                   ('order_line.product_id.product_tmpl_id', 'in', list(plantillas)),
                   ('write_date', '>=', fields.Datetime.now() - timedelta(days=DIAS_DE_CARRITO))]
        if 'dcasa_apartado_vence' in Pedido._fields:
            dominio.append(('dcasa_apartado_vence', '=', False))
        carritos = Pedido.search(dominio)
        carritos._dcasa_campana_al_dia(plantillas)
        if carritos:
            _logger.info('Campaña: %s carritos de la tienda al día con los precios que rigen.', len(carritos))
        return len(carritos)

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------

    @api.model
    def action_abrir(self):
        """El menú «Campaña del sitio»: abre la del sitio actual (la crea apagada si no existe)."""
        sitio = self.env['website'].get_current_website()
        campana = self.search([('website_id', '=', sitio.id)], limit=1)
        if not campana:
            campana = self.create({'website_id': sitio.id})
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Campaña del sitio'),
            'res_model': self._name,
            'res_id': campana.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_productos(self):
        """La lista para elegir los productos, con su casilla, su orden y su precio de campaña."""
        accion = self.env['ir.actions.act_window']._for_xml_id('website_dcasa.action_dcasa_campana_productos')
        return accion

    def action_empezar_de_cero(self):
        """Desmarca todos los productos y borra sus precios de campaña (para empezar una campaña nueva)."""
        self.ensure_one()
        _exigir_precios(self.env)
        marcados = self.env['product.template'].search([
            '|', ('dcasa_black_weekend', '=', True), ('dcasa_campana_precio', '!=', False)])
        cantidad = len(marcados)
        marcados.with_context(**{SIN_SINCRONIZAR: True}).write(
            {'dcasa_black_weekend': False, 'dcasa_campana_precio': False, 'dcasa_bw_orden': 0})
        self.env['product.template']._dcasa_campana_sincronizar()
        self.message_post(body=self.env._('Empezar de cero: %(n)s productos desmarcados y sin precio de campaña.',
                                          n=cantidad))
        return True


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dcasa_campana_precio = fields.Float(
        'Precio de campaña', digits='Product Price', copy=False,
        help='Opcional, sin ITBMS (como el precio de venta). Solo rige en las fechas de la campaña y solo si el '
             'producto está marcado; el carrito lo cobra y la tarjeta muestra el precio normal tachado. Vacío: el '
             'producto sale con su precio normal. Si tiene colores o medidas con precio distinto, cada uno baja lo '
             'mismo.')
    dcasa_campana_descuento = fields.Float('Descuento %', compute='_compute_dcasa_campana_descuento', digits=(16, 1))

    @api.depends('dcasa_campana_precio', 'list_price')
    def _compute_dcasa_campana_descuento(self):
        for producto in self:
            precio, normal = producto.dcasa_campana_precio, producto.list_price
            producto.dcasa_campana_descuento = (normal - precio) / normal * 100 if precio and normal else 0.0

    # Solo al escribir el precio de campaña: si después baja el precio normal (p. ej. el Excel del catálogo), no se
    # bloquea; esa regla simplemente no se crea mientras el de campaña no sea menor (``_dcasa_campana_deseadas``).
    @api.constrains('dcasa_campana_precio')
    def _check_dcasa_campana_precio(self):
        for producto in self:
            precio = producto.dcasa_campana_precio
            if not precio:
                continue
            if precio < 0:
                raise ValidationError(self.env._('El precio de campaña de «%s» no puede ser negativo.', producto.name))
            if float_compare(precio, producto.list_price, precision_digits=2) >= 0:
                raise ValidationError(self.env._(
                    'El precio de campaña de «%(nombre)s» (%(campana).2f) tiene que ser menor que su precio normal '
                    '(%(normal).2f).', nombre=producto.name, campana=precio, normal=producto.list_price))
            if producto.type == 'combo':
                raise ValidationError(self.env._(
                    '«%s» es un combo: su precio sale de sus partes y no lleva precio de campaña. Pon el precio de '
                    'campaña en los productos que lo forman.', producto.name))
            minimo = producto._dcasa_campana_variante_mas_barata()
            if minimo + precio - producto.list_price <= 0:
                raise ValidationError(self.env._(
                    'Con ese precio de campaña, una medida o un color de «%(nombre)s» quedaría en cero o negativo '
                    '(cada uno baja lo mismo: %(rebaja).2f). Pon un precio de campaña mayor.',
                    nombre=producto.name, rebaja=producto.list_price - precio))

    def _dcasa_campana_variante_mas_barata(self):
        """El precio normal de la variante activa más barata (con su diferencia de color o medida)."""
        self.ensure_one()
        variantes = self.sudo().product_variant_ids.filtered('active')
        return min(variantes.mapped('lst_price')) if variantes else self.list_price

    @api.model_create_multi
    def create(self, vals_list):
        if any(CAMPOS_CAMPANA.intersection(v) and any(v.get(c) for c in CAMPOS_CAMPANA) for v in vals_list):
            _exigir_precios(self.env)
        productos = super().create(vals_list)
        if any(v.get('dcasa_black_weekend') or v.get('dcasa_campana_precio') for v in vals_list):
            self._dcasa_campana_sincronizar()
        return productos

    def write(self, vals):
        if CAMPOS_CAMPANA.intersection(vals):
            _exigir_precios(self.env)
        resultado = super().write(vals)
        if {'dcasa_black_weekend', 'dcasa_campana_precio', 'list_price', 'active', 'company_id'} & set(vals):
            self._dcasa_campana_sincronizar()
        return resultado

    @api.model
    def _dcasa_campana_tarifas(self, sitio):
        """Las tarifas que el sitio ofrece al visitante (no las de mayoristas ni las internas). Si no ofrece ninguna,
        la del visitante sin sesión."""
        Tarifa = self.env['product.pricelist'].sudo()
        # Sin las de cupón (code): ahí la campaña pisaría el porcentaje del cupón.
        tarifas = Tarifa.search(Tarifa._get_website_pricelists_domain(sitio)).filtered(lambda t: not t.code)
        return tarifas or sitio.user_id.sudo().partner_id.property_product_pricelist

    @api.model
    def _dcasa_campana_deseadas(self, ahora=None):
        """{(tarifa, plantilla): {surcharge, date_start, date_end}}: las reglas que tienen que existir ahora."""
        deseadas = {}
        if not self.env['res.groups']._is_feature_enabled('product.group_product_pricelist'):
            # Con las tarifas apagadas la página no las aplica (request.pricelist vacío) pero el carrito sí (la del
            # contacto): una regla haría cobrar un precio distinto del que se muestra. Sin reglas, la campaña sale
            # con los precios normales y la pantalla lo avisa (tarifas_apagadas).
            return deseadas
        Campana = self.env['dcasa.campana'].sudo()
        productos = self.sudo().with_context(active_test=True).search([
            ('dcasa_black_weekend', '=', True), ('dcasa_campana_precio', '>', 0)])
        momento = ahora or fields.Datetime.now()
        Regla = self.env['product.pricelist.item'].sudo()
        for campana in Campana.search([('fecha_inicio', '!=', False), ('fecha_fin', '!=', False)]):
            desde, hasta = limites_utc(campana.fecha_inicio, campana.fecha_fin)
            if momento > hasta + DESPUES_DEL_FIN:
                continue   # terminó hace más de un mes: ya no hace falta para las cotizaciones de la campaña
            sitio = campana.website_id
            moneda = sitio.company_id.currency_id
            # Solo las tarifas que el sitio ofrece (en esta base, la general: también la usan las vendedoras al
            # cotizar en esas fechas, el mismo precio en la tienda y en la web).
            for tarifa in self._dcasa_campana_tarifas(sitio):
                if tarifa.currency_id != moneda:
                    _logger.warning('Campaña: la tarifa %s no está en %s; no lleva precios de campaña.',
                                    tarifa.display_name, moneda.name)
                    continue
                for producto in productos:
                    if float_compare(producto.dcasa_campana_precio, producto.list_price, precision_digits=2) >= 0:
                        continue
                    rebaja = float_round(producto.dcasa_campana_precio - producto.list_price,
                                         precision_rounding=moneda.rounding)
                    if producto.type == 'combo' or producto._dcasa_campana_variante_mas_barata() + rebaja <= 0:
                        continue   # combo, o una medida quedaría en cero o negativa (la validación ya lo impide)
                    # Una regla propia vigente de ese producto en esa tarifa (precio especial) manda: no se pisa.
                    if Regla.search_count([
                            ('pricelist_id', '=', tarifa.id), ('dcasa_campana', '=', False),
                            ('min_quantity', '<=', 1),
                            '|', ('date_end', '=', False), ('date_end', '>=', momento),
                            '|', ('product_tmpl_id', '=', producto.id),
                            ('product_id', 'in', producto.product_variant_ids.ids)], limit=1):
                        _logger.warning('Campaña: %s ya tiene un precio propio en la tarifa %s; no lleva el de '
                                        'campaña.', producto.display_name, tarifa.display_name)
                        continue
                    deseadas[(tarifa.id, producto.id)] = {
                        'price_surcharge': rebaja, 'date_start': desde, 'date_end': hasta,
                        'dcasa_campana_id': campana.id}
        return deseadas

    @api.model
    def _dcasa_campana_sincronizar(self, ahora=None):
        """Deja las reglas de campaña de las tarifas iguales a lo deseado, tocando solo lo que cambió."""
        if self.env.context.get(SIN_SINCRONIZAR):
            return
        Regla = self.env['product.pricelist.item'].sudo().with_context(active_test=False)
        existentes = Regla.search([('dcasa_campana', '=', True)])
        if not existentes and not self.env['dcasa.campana'].sudo().search_count(
                [('fecha_inicio', '!=', False), ('fecha_fin', '!=', False)], limit=1):
            return   # sin campaña con fechas ni reglas: nada que hacer (las importaciones del catálogo no pagan esto)
        deseadas = self._dcasa_campana_deseadas(ahora)
        sobran = Regla.browse()
        for regla in existentes:
            clave = (regla.pricelist_id.id, regla.product_tmpl_id.id)
            quiero = deseadas.pop(clave, None)
            if quiero is None:
                sobran |= regla
                continue
            cambios = {campo: valor for campo, valor in quiero.items() if regla[campo] != valor}
            if cambios:
                regla.write(cambios)
        if sobran:
            sobran.unlink()
        if deseadas:
            Regla.create([{
                'pricelist_id': tarifa_id,
                'applied_on': '1_product',
                'product_tmpl_id': plantilla_id,
                'compute_price': 'formula',
                'base': 'list_price',
                'price_discount': 0.0,
                'dcasa_campana': True,
                **valores,
            } for (tarifa_id, plantilla_id), valores in deseadas.items()])


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    dcasa_campana = fields.Boolean(
        'Regla de la campaña del sitio', readonly=True, copy=False, index=True,
        help='La crea y la borra la campaña del sitio (Sitio web › Campaña del sitio). No se edita a mano: se '
             'cambia el precio de campaña del producto o las fechas de la campaña.')
    dcasa_campana_id = fields.Many2one(
        'dcasa.campana', 'Campaña', readonly=True, copy=False, ondelete='set null',
        help='La campaña del sitio que creó esta regla. Con su interruptor «La campaña también rebaja los combos» '
             'apagado, la regla no rebaja la cama ni el colchón de un combo armado en la cotización.')

    def _show_discount_on_shop(self):
        """En la tienda, el precio de campaña sale con el normal tachado (Odoo solo lo hace con descuentos en %)."""
        if self and len(self) == 1 and self.dcasa_campana:
            return True
        return super()._show_discount_on_shop()

    def write(self, vals):
        if not self.env.su and any(r.dcasa_campana for r in self):
            raise UserError(self.env._('Esta regla la maneja la campaña del sitio: cambia el precio de campaña del '
                                       'producto o las fechas en Sitio web › Campaña del sitio.'))
        return super().write(vals)

    def unlink(self):
        if not self.env.su and any(r.dcasa_campana for r in self):
            raise UserError(self.env._('Esta regla la maneja la campaña del sitio: se quita desmarcando el producto o '
                                       'cambiando las fechas en Sitio web › Campaña del sitio.'))
        return super().unlink()


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    def _get_applicable_rules_domain(self, products, date, **kwargs):
        """Con ``COMBO_SIN_CAMPANA`` (una pieza de un combo armado), sin las reglas de la campaña que no rebajan los
        combos: la pieza toma lo que le daría la tarifa sin campaña (sus otras reglas o su precio normal)."""
        dominio = super()._get_applicable_rules_domain(products, date, **kwargs)
        if es_interno(self.env, COMBO_SIN_CAMPANA):
            # El interruptor se lee de la campaña en este momento (sudo: la vendedora no lee dcasa.campana).
            rebajan = self.env['dcasa.campana'].sudo().search([('dcasa_rebaja_combos', '=', True)]).ids
            dominio = [*dominio, '|', ('dcasa_campana', '=', False), ('dcasa_campana_id', 'in', rebajan)]
        return dominio


class DcasaCampanaDescuento(models.TransientModel):
    """«Aplicar un mismo % a los seleccionados»: llena el precio de campaña de cada uno (redondeado al centavo)."""
    _name = 'dcasa.campana.descuento'
    _description = 'Aplicar un descuento a los productos de la campaña'

    porcentaje = fields.Float('Descuento %', required=True, digits=(16, 1))
    producto_ids = fields.Many2many('product.template', string='Productos',
                                    default=lambda self: self.env.context.get('active_ids') or [])

    @api.constrains('porcentaje')
    def _check_porcentaje(self):
        for asistente in self:
            if not 0 < asistente.porcentaje < 100:
                raise ValidationError(self.env._('El descuento tiene que estar entre 0 y 100 %.'))

    def action_aplicar(self):
        self.ensure_one()
        _exigir_precios(self.env)
        for producto in self.producto_ids.with_context(**{SIN_SINCRONIZAR: True}):
            moneda = producto.currency_id
            precio = float_round(producto.list_price * (1 - self.porcentaje / 100), precision_rounding=moneda.rounding)
            producto.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': precio if precio > 0 else False})
        self.env['product.template']._dcasa_campana_sincronizar()
        return {'type': 'ir.actions.act_window_close'}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model_create_multi
    def create(self, vals_list):
        # Una cotización nueva nace con la hora actual: quien no cambia precios no la fecha dentro de una campaña (el
        # formulario manda la hora en que se abrió, por eso la tolerancia).
        if not self.env.su and not _puede_cambiar_precios(self.env):
            ahora = fields.Datetime.now()
            for vals in vals_list:
                fecha = fields.Datetime.to_datetime(vals.get('date_order')) if vals.get('date_order') else None
                if fecha and abs(fecha - ahora) > timedelta(hours=1):
                    vals['date_order'] = ahora
        return super().create(vals_list)

    def write(self, vals):
        # La fecha de una cotización: solo la cambia quien cambia precios (de ella salían el precio autorizado y la
        # regla de campaña de sus líneas; desde I-B cada línea fuera de la web usa la suya, pero las líneas de antes y
        # los pedidos de la web siguen con la del pedido). Confirmar (que también la escribe, con state='sale') y el
        # sistema, sí.
        if ('date_order' in vals and vals.get('state') != 'sale' and not self.env.su
                and not _puede_cambiar_precios(self.env)
                and any(orden.state in ('draft', 'sent') for orden in self)):
            raise AccessError(self.env._('Solo Gerencia cambia la fecha de una cotización (de ella sale su precio).'))
        return super().write(vals)

    @api.model
    def _dcasa_campana_hay(self):
        """¿Hay algo de campaña que pueda haber cambiado precios (reglas o algo que rigió)?"""
        if self.env['product.pricelist.item'].sudo().search_count([('dcasa_campana', '=', True)], limit=1):
            return True
        return bool(self.env['ir.config_parameter'].sudo().get_param(PARAM_FIRMA_CARRITOS))

    def _check_cart_is_ready_to_be_paid(self):
        # El último paso antes de cobrar: también al día con lo que rige (quien abrió el pago a las 23:59).
        self._dcasa_campana_al_dia_si_hay()
        return super()._check_cart_is_ready_to_be_paid()

    def _dcasa_campana_al_dia_si_hay(self):
        if self and self._dcasa_campana_hay():
            self._dcasa_campana_al_dia()

    @api.model
    def _dcasa_campana_plantillas_en_juego(self):
        """Productos cuyo precio puede haber cambiado por la campaña: marcados, con precio de campaña, con regla de
        campaña o en lo último que rigió."""
        Producto = self.env['product.template'].sudo()
        ids = set(Producto.search(['|', ('dcasa_black_weekend', '=', True), ('dcasa_campana_precio', '>', 0)]).ids)
        ids |= set(self.env['product.pricelist.item'].sudo().search([('dcasa_campana', '=', True)]).product_tmpl_id.ids)
        firma = self.env['ir.config_parameter'].sudo().get_param(PARAM_FIRMA_CARRITOS) or ''
        ids |= {int(par.split(':')[0]) for par in firma.split(',') if par}
        return ids

    def _dcasa_campana_al_dia(self, plantillas=None):
        """Vuelve a calcular el precio de las líneas de esos productos en carritos de la tienda (borrador, sin
        apartado): las demás líneas, los premios de puntos (dcasa_socios) y el envío no se tocan."""
        plantillas = self._dcasa_campana_plantillas_en_juego() if plantillas is None else set(plantillas)
        if not plantillas:
            return
        for orden in self.filtered(lambda o: o.state == 'draft' and o.website_id):
            if 'dcasa_apartado_vence' in orden._fields and orden.dcasa_apartado_vence:
                continue
            lineas = orden._get_update_prices_lines().filtered(
                lambda linea: linea.product_id.product_tmpl_id.id in plantillas)
            if not lineas:
                continue
            # Las partes de un combo de Odoo toman su precio del combo: van con él.
            if 'combo_item_id' in lineas._fields:
                principales = lineas
                lineas |= orden.order_line.filtered(
                    lambda linea, principales=principales: linea.combo_item_id and linea.linked_line_id in principales)
            lineas.invalidate_recordset(['pricelist_item_id'])
            lineas.with_context(force_price_recomputation=True)._compute_price_unit()
            lineas.discount = 0.0
            lineas._compute_discount()
            if hasattr(orden, '_dcasa_limpiar_premios_web'):
                orden._dcasa_limpiar_premios_web()   # si la compra bajó por debajo del premio de puntos


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # I-B (revisión adversarial, tercera vuelta): sin esto, una cotización hecha en la campaña le daba el precio de
    # campaña a cualquier línea nueva hasta 30 días después del fin (Odoo calcula con la fecha del pedido y las reglas
    # se quedan ese tiempo para las cotizaciones de la campaña).
    dcasa_fecha_precio = fields.Datetime(
        'Fecha del precio', readonly=True, copy=False,
        help='Cuándo se agregó la línea. En las ventas que no son de la tienda en línea, su precio de tarifa (y el de '
             'campaña) se calcula con esta fecha y no con la de la cotización. Vacía en las líneas de antes: usan la '
             'fecha de la cotización.')

    @api.model_create_multi
    def create(self, vals_list):
        # Como la fecha de la cotización: quien no cambia precios no fecha una línea dentro de una campaña.
        ahora = fields.Datetime.now()
        fija = not self.env.su and not _puede_cambiar_precios(self.env)
        for vals in vals_list:
            if fija or not vals.get('dcasa_fecha_precio'):
                vals['dcasa_fecha_precio'] = ahora
        return super().create(vals_list)

    def write(self, vals):
        if 'dcasa_fecha_precio' in vals and not self.env.su and not _puede_cambiar_precios(self.env):
            raise AccessError(self.env._('Solo Gerencia cambia la fecha del precio de una línea.'))
        return super().write(vals)

    def _get_order_date(self):
        """La fecha con que se calcula el precio de la línea: en una venta que no es de la web, cuando se agregó la
        línea (una línea nueva en una cotización de la campaña ya no toma el precio de campaña después del fin; una
        agregada en la campaña a una cotización vieja, sí). La tienda en línea sigue como Odoo (el carrito, con la hora
        actual) y las líneas de antes de este cambio, con la fecha del pedido."""
        self.ensure_one()
        if self.order_id.website_id:
            return super()._get_order_date()
        if self.dcasa_fecha_precio:
            return self.dcasa_fecha_precio
        if not self._origin.id:
            return fields.Datetime.now()   # línea nueva en la pantalla, todavía sin guardar
        return super()._get_order_date()
