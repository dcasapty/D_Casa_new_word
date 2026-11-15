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
"""
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_round

_logger = logging.getLogger(__name__)

ZONA = pytz.timezone('America/Panama')
# Lo último que rigió de la campaña cuando se pusieron al día los carritos (``_dcasa_campana_carritos_al_dia``).
PARAM_FIRMA_CARRITOS = 'website_dcasa.campana_firma_carritos'
# Carritos más viejos que esto (sin tocar) no se recalculan: ya nadie vuelve a ellos.
DIAS_DE_CARRITO = 30


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
        campanas = super().create(vals_list)
        self.env['product.template']._dcasa_campana_sincronizar()
        return campanas

    def write(self, vals):
        resultado = super().write(vals)
        if {'fecha_inicio', 'fecha_fin', 'website_id'} & set(vals):
            self.env['product.template']._dcasa_campana_sincronizar()
        return resultado

    def unlink(self):
        resultado = super().unlink()
        self.env['product.template']._dcasa_campana_sincronizar()
        return resultado

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
        param = self.env['ir.config_parameter'].sudo()
        firma = self._dcasa_campana_firma(ahora)
        antes = param.get_param(PARAM_FIRMA_CARRITOS)
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
        for carrito in carritos:
            carrito._recompute_prices()
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
        marcados = self.env['product.template'].search([
            '|', ('dcasa_black_weekend', '=', True), ('dcasa_campana_precio', '!=', False)])
        cantidad = len(marcados)
        marcados.write({'dcasa_black_weekend': False, 'dcasa_campana_precio': False, 'dcasa_bw_orden': 0})
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

    @api.model_create_multi
    def create(self, vals_list):
        productos = super().create(vals_list)
        if any(v.get('dcasa_black_weekend') or v.get('dcasa_campana_precio') for v in vals_list):
            self._dcasa_campana_sincronizar()
        return productos

    def write(self, vals):
        resultado = super().write(vals)
        if {'dcasa_black_weekend', 'dcasa_campana_precio', 'list_price', 'active', 'company_id'} & set(vals):
            self._dcasa_campana_sincronizar()
        return resultado

    @api.model
    def _dcasa_campana_deseadas(self):
        """{(tarifa, plantilla): {surcharge, date_start, date_end}}: las reglas que tienen que existir ahora."""
        deseadas = {}
        Campana = self.env['dcasa.campana'].sudo()
        productos = self.sudo().with_context(active_test=True).search([
            ('dcasa_black_weekend', '=', True), ('dcasa_campana_precio', '>', 0)])
        for campana in Campana.search([('fecha_inicio', '!=', False), ('fecha_fin', '!=', False)]):
            desde, hasta = limites_utc(campana.fecha_inicio, campana.fecha_fin)
            sitio = campana.website_id
            moneda = sitio.company_id.currency_id
            # Todas las tarifas activas que puede usar el sitio: las suyas y las generales de la empresa (la del
            # visitante sin sesión sale de su contacto, no de website.pricelist_ids). Así también las ven las
            # vendedoras al cotizar en esas fechas: el mismo precio en la tienda y en la web.
            tarifas = self.env['product.pricelist'].sudo().search([
                ('company_id', 'in', [False, sitio.company_id.id]), ('website_id', 'in', [False, sitio.id])])
            for tarifa in tarifas:
                if tarifa.currency_id != moneda:
                    _logger.warning('Campaña: la tarifa %s no está en %s; no lleva precios de campaña.',
                                    tarifa.display_name, moneda.name)
                    continue
                for producto in productos:
                    if float_compare(producto.dcasa_campana_precio, producto.list_price, precision_digits=2) >= 0:
                        continue
                    rebaja = float_round(producto.dcasa_campana_precio - producto.list_price,
                                         precision_rounding=moneda.rounding)
                    deseadas[(tarifa.id, producto.id)] = {
                        'price_surcharge': rebaja, 'date_start': desde, 'date_end': hasta}
        return deseadas

    @api.model
    def _dcasa_campana_sincronizar(self):
        """Deja las reglas de campaña de las tarifas iguales a lo deseado, tocando solo lo que cambió."""
        Regla = self.env['product.pricelist.item'].sudo().with_context(active_test=False)
        deseadas = self._dcasa_campana_deseadas()
        existentes = Regla.search([('dcasa_campana', '=', True)])
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
        for producto in self.producto_ids:
            moneda = producto.currency_id
            precio = float_round(producto.list_price * (1 - self.porcentaje / 100), precision_rounding=moneda.rounding)
            producto.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': precio if precio > 0 else False})
        return {'type': 'ir.actions.act_window_close'}
