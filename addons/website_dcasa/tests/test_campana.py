"""Campaña del sitio (Black Friday): fechas del panel, precio de campaña como regla de tarifa y lo que se ve en el
sitio.

Pedido de la dueña (2026-11-15): manejar Black Friday desde el panel marcando productos con una casilla, con un
precio de campaña opcional que el carrito cobre de verdad y que vuelva solo al terminar (models/campana.py).
"""
from datetime import date, datetime, timedelta
from unittest.mock import patch
from urllib.parse import unquote

from freezegun import freeze_time

from odoo import Command, fields
from odoo.addons.website_dcasa.models.black_weekend import PARAM_ACTIVO, PARAM_FIN, PARAM_INICIO, articulo_y_nombre
from odoo.addons.website_dcasa.models.campana import COMBO_SIN_CAMPANA, INTERNO, PARAM_FIRMA_CARRITOS, limites_utc
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged


class _Base:

    @classmethod
    def _preparar(cls):
        cls.website = cls.env.ref('website.default_website')
        param = cls.env['ir.config_parameter'].sudo()
        # La ventana vieja (parámetros) apagada: manda la campaña del panel.
        param.set_param(PARAM_ACTIVO, '0')
        param.set_param(PARAM_INICIO, '2020-01-01')
        param.set_param(PARAM_FIN, '2020-01-02')
        cls.env['product.template'].search([('dcasa_black_weekend', '=', True)]).write({'dcasa_black_weekend': False})
        Tarifa = cls.env['product.pricelist']
        cls.tarifa = Tarifa.search([('company_id', 'in', [False, cls.website.company_id.id])], limit=1) \
            or Tarifa.create({'name': 'Prueba'})
        cls.campana = cls.env['dcasa.campana'].search([('website_id', '=', cls.website.id)]) \
            or cls.env['dcasa.campana'].create({'website_id': cls.website.id})
        cls.campana.write({'name': 'Black Friday', 'fecha_inicio': False, 'fecha_fin': False, 'frase': False})
        # Las tarifas encendidas, como en producción, y la del visitante ofrecida al sitio.
        cls.env.ref('base.group_user').write({
            'implied_ids': [Command.link(cls.env.ref('product.group_product_pricelist').id)]})
        cls.env['dcasa.campana']._dcasa_tarifa_del_sitio()
        cls.recamaras = cls.env.ref('website_dcasa.public_category_recamaras')
        cls.cama = cls.env['product.template'].create({
            'name': 'CAMA CAMPAÑA DE PRUEBA', 'list_price': 200.0, 'is_published': True,
            'public_categ_ids': [Command.set(cls.recamaras.ids)], 'website_sequence': -2000,
            'dcasa_combo': 'Combo con colchón First Class $469.99',
        })

    def _reglas(self, plantilla=None):
        dominio = [('dcasa_campana', '=', True)]
        if plantilla:
            dominio.append(('product_tmpl_id', '=', plantilla.id))
        return self.env['product.pricelist.item'].sudo().search(dominio)

    def _precio(self, producto, momento):
        return round(self.tarifa._get_product_price(producto, 1.0, date=momento), 2)


@tagged('post_install', '-at_install')
@freeze_time('2026-11-20 12:00:00')   # una semana antes: la campaña ya está programada y sus reglas existen
class TestCampanaPrecios(_Base, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._preparar()

    def _en_campana(self, precio=150.0, inicio=date(2026, 11, 27), fin=date(2026, 11, 30)):
        self.campana.write({'fecha_inicio': inicio, 'fecha_fin': fin})
        self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': precio})

    def test_regla_con_las_fechas_en_hora_de_panama(self):
        self._en_campana()
        regla = self._reglas(self.cama).filtered(lambda r: r.pricelist_id == self.tarifa)
        self.assertEqual(len(regla), 1)
        self.assertEqual((regla.compute_price, regla.base, regla.price_surcharge), ('formula', 'list_price', -50.0))
        self.assertEqual(regla.date_start, datetime(2026, 11, 27, 5, 0, 0))   # 00:00 en Panamá
        self.assertEqual(regla.date_end, datetime(2026, 12, 1, 4, 59, 59))    # 23:59:59 del 30 en Panamá
        variante = self.cama.product_variant_id
        self.assertEqual(self._precio(variante, datetime(2026, 11, 27, 4, 59, 59)), 200.0, 'antes: el normal')
        self.assertEqual(self._precio(variante, datetime(2026, 11, 27, 5, 0, 0)), 150.0, 'empieza a las 00:00')
        self.assertEqual(self._precio(variante, datetime(2026, 12, 1, 4, 59, 59)), 150.0, 'último segundo')
        self.assertEqual(self._precio(variante, datetime(2026, 12, 1, 5, 0, 0)), 200.0, 'termina sola')

    def test_sin_las_dos_fechas_no_hay_precio_de_campana(self):
        self._en_campana(inicio=False, fin=False)
        self.assertFalse(self._reglas())
        self.campana.fecha_inicio = date(2026, 11, 27)
        self.assertFalse(self._reglas(), 'un precio rebajado sin fin no sale solo')
        self.campana.fecha_fin = date(2026, 11, 30)
        self.assertTrue(self._reglas(self.cama))
        self.campana.write({'fecha_inicio': False, 'fecha_fin': False})
        self.assertFalse(self._reglas(), 'quitar las fechas borra las reglas')

    def test_cada_variante_baja_lo_mismo(self):
        medida = self.env['product.attribute'].create({'name': 'Medida prueba', 'create_variant': 'always'})
        full, king = self.env['product.attribute.value'].create([
            {'name': 'Full', 'attribute_id': medida.id}, {'name': 'King', 'attribute_id': medida.id}])
        self.cama.write({'attribute_line_ids': [Command.create({
            'attribute_id': medida.id, 'value_ids': [Command.set([full.id, king.id])]})]})
        self.cama.attribute_line_ids.product_template_value_ids.filtered(
            lambda v: v.product_attribute_value_id == king).price_extra = 60.0
        self._en_campana(precio=180.0)
        momento = datetime(2026, 11, 28, 15, 0)
        precios = {v.product_template_attribute_value_ids.name: self._precio(v, momento)
                   for v in self.cama.product_variant_ids}
        self.assertEqual(precios, {'Full': 180.0, 'King': 240.0}, 'la King conserva sus 60 de diferencia')

    def test_el_precio_de_campana_tiene_que_ser_menor(self):
        for precio in (200.0, 250.0, -5.0):
            with self.subTest(precio=precio), self.assertRaises(ValidationError):
                self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': precio})

    def test_desmarcar_o_borrar_el_precio_quita_la_regla(self):
        self._en_campana()
        self.cama.dcasa_campana_precio = False
        self.assertFalse(self._reglas(self.cama))
        self.cama.dcasa_campana_precio = 150.0
        self.assertTrue(self._reglas(self.cama))
        self.cama.dcasa_black_weekend = False
        self.assertFalse(self._reglas(self.cama), 'fuera de la campaña, sin precio de campaña')

    def test_el_precio_normal_cambia_y_la_rebaja_se_ajusta(self):
        self._en_campana()
        self.cama.list_price = 220.0
        self.assertEqual(self._reglas(self.cama)[:1].price_surcharge, -70.0)
        # Si el normal baja por debajo del de campaña (p. ej. el Excel del catálogo), no se bloquea: la regla se va.
        self.cama.list_price = 140.0
        self.assertFalse(self._reglas(self.cama))

    def test_solo_toca_las_reglas_que_cambian(self):
        self._en_campana()
        regla = self._reglas(self.cama)
        self.cama.write({'name': 'CAMA CAMPAÑA RENOMBRADA'})
        self.env['product.template']._dcasa_campana_sincronizar()
        self.assertEqual(self._reglas(self.cama), regla, 'la misma regla, no una nueva')

    def test_la_regla_no_se_edita_a_mano(self):
        self._en_campana()
        gerente = self.env['res.users'].create({
            'name': 'Gerente prueba', 'login': 'gerente_campana',
            'group_ids': [Command.set([self.env.ref('base.group_user').id, self.env.ref('dcasa_base.group_gerencia').id,
                                       self.env.ref('sales_team.group_sale_manager').id])]})
        with self.assertRaises(UserError):
            self._reglas(self.cama)[:1].with_user(gerente).write({'price_surcharge': -150.0})

    def test_descuento_en_porcentaje_a_varios(self):
        otra = self.env['product.template'].create({'name': 'OTRA CAMA', 'list_price': 199.99})
        asistente = self.env['dcasa.campana.descuento'].with_context(
            active_ids=(self.cama | otra).ids).create({'porcentaje': 15})
        asistente.action_aplicar()
        self.assertEqual((self.cama.dcasa_campana_precio, otra.dcasa_campana_precio), (170.0, 169.99))
        self.assertTrue(self.cama.dcasa_black_weekend and otra.dcasa_black_weekend)
        with self.assertRaises(ValidationError):
            self.env['dcasa.campana.descuento'].create({'porcentaje': 100})

    def test_empezar_de_cero(self):
        self._en_campana()
        self.campana.action_empezar_de_cero()
        self.assertFalse(self.cama.dcasa_black_weekend)
        self.assertFalse(self.cama.dcasa_campana_precio)
        self.assertFalse(self._reglas())
        self.assertIn('Empezar de cero', self.campana.message_ids[:1].body)

    def test_fechas_al_reves(self):
        with self.assertRaises(ValidationError):
            self.campana.write({'fecha_inicio': date(2026, 11, 30), 'fecha_fin': date(2026, 11, 27)})

    def test_la_ventana_y_el_nombre(self):
        self._en_campana()
        self.assertEqual(self.website._dcasa_campana_nombre(), 'Black Friday')
        self.assertFalse(self.website._dcasa_black_weekend_activo(ahora=datetime(2026, 11, 27, 4, 59)))
        self.assertTrue(self.website._dcasa_black_weekend_activo(ahora=datetime(2026, 11, 27, 5, 0)))
        self.assertTrue(self.website._dcasa_black_weekend_activo(ahora=datetime(2026, 12, 1, 4, 59)))
        self.assertFalse(self.website._dcasa_black_weekend_activo(ahora=datetime(2026, 12, 1, 5, 0)))
        self.assertEqual(self.website._dcasa_bw_fechas(), 'del 27 al 30 de noviembre de 2026')
        # Sin fechas en el panel manda la ventana de siempre (los parámetros), con su nombre.
        self.campana.write({'fecha_inicio': False, 'fecha_fin': False})
        self.assertEqual(self.website._dcasa_campana_nombre(), 'Black Weekend')
        self.assertFalse(self.website._dcasa_black_weekend_activo(ahora=datetime(2026, 11, 28, 12, 0)))

    def test_precio_vigente_para_juan_y_andres(self):
        self._en_campana()
        vigente = self.website._dcasa_campana_precio_vigente
        self.assertIsNone(vigente(self.cama, ahora=datetime(2026, 11, 26, 12, 0)))
        self.assertEqual(vigente(self.cama, ahora=datetime(2026, 11, 28, 12, 0)), 150.0)
        self.assertIsNone(vigente(self.cama, ahora=datetime(2026, 12, 2, 12, 0)))

    def test_con_las_tarifas_apagadas_no_hay_precio_de_campana(self):
        self.env.ref('base.group_user').write({
            'implied_ids': [Command.unlink(self.env.ref('product.group_product_pricelist').id)]})
        if self.env['res.groups']._is_feature_enabled('product.group_product_pricelist'):
            self.skipTest('Otro grupo enciende las tarifas en esta base')
        self._en_campana()
        self.assertFalse(self._reglas(), 'la página no las aplicaría y el carrito sí: ninguna')
        self.assertTrue(self.campana.tarifas_apagadas)

    def test_las_reglas_se_quedan_un_mes_para_las_cotizaciones_de_la_campana(self):
        self._en_campana()
        self.assertTrue(self._reglas(self.cama), 'programada: ya existe (con sus fechas no cuenta antes)')
        with freeze_time('2026-12-15 12:00:00'):
            self.env['dcasa.campana']._dcasa_campana_carritos_al_dia()
            self.assertTrue(self._reglas(self.cama), 'una cotización del 28 sigue con su precio autorizado')
            self.assertIsNone(self.website._dcasa_campana_precio_vigente(self.cama), 'pero ya no rige')
        with freeze_time('2026-12-31 06:00:00'):
            self.env['dcasa.campana']._dcasa_campana_carritos_al_dia()
            self.assertFalse(self._reglas(), 'un mes después del fin el cron la quita')

    def test_solo_quien_cambia_precios_cambia_la_fecha_de_una_cotizacion(self):
        vendedora = self.env['res.users'].create({
            'name': 'Vendedora fecha', 'login': 'vendedora_fecha',
            'group_ids': [Command.set([self.env.ref('dcasa_base.group_vendedora').id])]})
        cliente = self.env['res.partner'].create({'name': 'Cliente fecha'})
        orden = self.env['sale.order'].create({
            'partner_id': cliente.id, 'user_id': vendedora.id,
            'order_line': [Command.create({'product_id': self.cama.product_variant_id.id})]})
        with self.assertRaises(AccessError):
            orden.with_user(vendedora).write({'date_order': datetime(2026, 11, 28, 15, 0)})
        with self.assertRaises(AccessError):
            orden.with_user(vendedora).write({'date_order': datetime(2026, 11, 28, 15, 0), 'state': 'draft'})
        orden.write({'date_order': datetime(2026, 11, 28, 15, 0)})   # el sistema (y Gerencia), sí
        # Al crearla tampoco: nace con la hora actual.
        nueva = self.env['sale.order'].with_user(vendedora).create({
            'partner_id': cliente.id, 'user_id': vendedora.id, 'date_order': datetime(2026, 11, 28, 15, 0)})
        self.assertEqual(nueva.date_order.date(), date(2026, 11, 20), 'la fecha de hoy, no la que mandó')

    def test_un_combo_no_lleva_precio_de_campana(self):
        variante = self.cama.product_variant_id
        combo = self.env['product.combo'].create({
            'name': 'Combo campaña', 'combo_item_ids': [Command.create({'product_id': variante.id})]})
        producto = self.env['product.template'].create({
            'name': 'COMBO CAMA', 'type': 'combo', 'list_price': 300.0, 'combo_ids': [Command.set(combo.ids)]})
        with self.assertRaises(ValidationError):
            producto.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 250.0})

    def test_solo_gerencia_cambia_la_campana(self):
        vendedora = self.env['res.users'].create({
            'name': 'Vendedora campaña', 'login': 'vendedora_campana',
            'group_ids': [Command.set([self.env.ref('dcasa_base.group_vendedora').id])]})
        cama = self.cama.with_user(vendedora)
        for valores in ({'dcasa_campana_precio': 1.0}, {'dcasa_black_weekend': True}, {'dcasa_bw_orden': 5}):
            with self.subTest(valores=valores), self.assertRaises(AccessError):
                cama.write(valores)
        with self.assertRaises(AccessError):
            self.env['product.template'].with_user(vendedora).create(
                {'name': 'Nueva', 'list_price': 50.0, 'dcasa_black_weekend': True, 'dcasa_campana_precio': 1.0})
        with self.assertRaises(AccessError):
            self.campana.with_user(vendedora).action_empezar_de_cero()
        cama.write({'name': 'CAMA RENOMBRADA POR LA VENDEDORA'})   # lo demás del producto, sí

    def test_ninguna_medida_queda_en_cero_o_negativa(self):
        medida = self.env['product.attribute'].create({'name': 'Medida barata', 'create_variant': 'always'})
        twin, king = self.env['product.attribute.value'].create([
            {'name': 'Twin', 'attribute_id': medida.id}, {'name': 'King', 'attribute_id': medida.id}])
        self.cama.write({'list_price': 300.0, 'attribute_line_ids': [Command.create({
            'attribute_id': medida.id, 'value_ids': [Command.set([twin.id, king.id])]})]})
        self.cama.attribute_line_ids.product_template_value_ids.filtered(
            lambda v: v.product_attribute_value_id == twin).price_extra = -150.0
        with self.assertRaises(ValidationError):
            self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 120.0})   # la Twin a −30
        self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 200.0})       # la Twin a 50: bien

    def test_un_precio_propio_de_la_tarifa_no_se_pisa(self):
        self.env['product.pricelist.item'].create({
            'pricelist_id': self.tarifa.id, 'applied_on': '1_product', 'product_tmpl_id': self.cama.id,
            'compute_price': 'fixed', 'fixed_price': 120.0})
        self._en_campana()
        self.assertFalse(self._reglas(self.cama).filtered(lambda r: r.pricelist_id == self.tarifa))

    def test_la_regla_no_se_borra_a_mano(self):
        self._en_campana()
        gerente = self.env['res.users'].create({
            'name': 'Gerente borra', 'login': 'gerente_borra_regla',
            'group_ids': [Command.set([self.env.ref('dcasa_base.group_gerencia').id])]})
        with self.assertRaises(UserError):
            self._reglas(self.cama)[:1].with_user(gerente).unlink()

    def test_la_bandera_de_los_combos_saca_la_campana_y_el_interruptor_la_devuelve(self):
        """«Los combos son inamovibles» (la dueña, 2026-11-16): una pieza de un combo armado (dcasa_catalogo) se calcula
        con ``COMBO_SIN_CAMPANA``: sin las reglas de campaña, con las demás reglas de la tarifa."""
        otra = self.env['product.template'].create({'name': 'OTRA CON PRECIO PROPIO', 'list_price': 100.0})
        self.env['product.pricelist.item'].create({
            'pricelist_id': self.tarifa.id, 'applied_on': '1_product', 'product_tmpl_id': otra.id,
            'compute_price': 'fixed', 'fixed_price': 90.0})
        self._en_campana()
        variante = self.cama.product_variant_id
        momento = datetime(2026, 11, 28, 15, 0)
        combo = self.tarifa.with_context(**{COMBO_SIN_CAMPANA: INTERNO})
        self.assertEqual(self._precio(variante, momento), 150.0)
        self.assertEqual(round(combo._get_product_price(variante, 1.0, date=momento), 2), 200.0, 'en combo: el normal')
        self.assertEqual(round(combo._get_product_price(otra.product_variant_id, 1.0, date=momento), 2), 90.0,
                         'las demás reglas de la tarifa siguen')
        # La bandera mandada desde afuera (por RPC llega como ``true``) no vale.
        de_afuera = self.tarifa.with_context(**{COMBO_SIN_CAMPANA: True})
        self.assertEqual(round(de_afuera._get_product_price(variante, 1.0, date=momento), 2), 150.0)
        self.assertFalse(self.campana.dcasa_rebaja_combos, 'apagado de fábrica')
        self.assertEqual(self._reglas(self.cama).dcasa_campana_id, self.campana)
        regla = self._reglas(self.cama)
        Regla = type(self.env['product.pricelist.item'])
        with patch.object(Regla, 'write', side_effect=AssertionError('el interruptor no reescribe reglas')), \
                patch.object(Regla, 'create', side_effect=AssertionError('ni crea reglas')):
            self.campana.dcasa_rebaja_combos = True
        self.assertEqual(self._reglas(self.cama), regla, 'la misma regla')
        self.assertEqual(round(combo._get_product_price(variante, 1.0, date=momento), 2), 150.0,
                         'encendido: el combo también toma la campaña')
        self.campana.dcasa_rebaja_combos = False
        self.assertEqual(round(combo._get_product_price(variante, 1.0, date=momento), 2), 200.0)

    def test_solo_gerencia_y_administradores_cambian_el_interruptor_de_combos(self):
        Usuarios = self.env['res.users']
        grupos = {
            'vendedora': ['dcasa_base.group_vendedora'],
            # Puede cambiar precios (administra productos y ventas) pero no es Gerencia: no decide sobre los combos.
            'precios': ['base.group_user', 'product.group_product_manager', 'sales_team.group_sale_manager'],
            'gerencia': ['dcasa_base.group_gerencia'],
            'admin': ['base.group_user', 'base.group_system'],
        }
        usuarios = {clave: Usuarios.create({
            'name': f'Combos {clave}', 'login': f'combos_interruptor_{clave}',
            'group_ids': [Command.set([self.env.ref(g).id for g in lista])]}) for clave, lista in grupos.items()}
        for clave in ('vendedora', 'precios'):
            with self.subTest(clave), self.assertRaisesRegex(AccessError, 'rebaja los combos'):
                self.campana.with_user(usuarios[clave]).write({'dcasa_rebaja_combos': True})
        self.assertFalse(self.campana.dcasa_rebaja_combos)
        self.campana.with_user(usuarios['gerencia']).write({'dcasa_rebaja_combos': True})
        self.assertTrue(self.campana.dcasa_rebaja_combos)
        self.campana.with_user(usuarios['admin']).write({'dcasa_rebaja_combos': False})
        self.assertFalse(self.campana.dcasa_rebaja_combos)
        # La pantalla lo muestra (la abre solo Gerencia o un administrador).
        arch = self.env['dcasa.campana'].with_user(usuarios['gerencia']).get_views([(False, 'form')])
        self.assertIn('name="dcasa_rebaja_combos"', arch['views']['form']['arch'])

    def test_una_linea_nueva_despues_del_fin_no_toma_el_precio_de_campana(self):
        """I-B: Odoo calcula con la fecha de la cotización y las reglas se quedan 30 días después del fin; fuera de la
        web cada línea se calcula con la fecha en que se agregó."""
        self._en_campana()
        cliente = self.env['res.partner'].create({'name': 'Cliente I-B'})
        variante = self.cama.product_variant_id
        with freeze_time('2026-11-28 15:00:00'):
            orden = self.env['sale.order'].create({
                'partner_id': cliente.id, 'pricelist_id': self.tarifa.id,
                'order_line': [Command.create({'product_id': variante.id})]})
            vieja = orden.order_line
            self.assertEqual(vieja.price_unit, 150.0)
        with freeze_time('2026-12-10 15:00:00'):   # terminó; la regla sigue para las cotizaciones de la campaña
            nueva = self.env['sale.order.line'].create({'order_id': orden.id, 'product_id': variante.id})
            self.assertEqual(nueva.price_unit, 200.0, 'una línea nueva va al precio de hoy')
            vieja.product_uom_qty = 2
            self.assertEqual(vieja.price_unit, 150.0, 'la de la campaña conserva su precio')
            orden.action_update_prices()
            self.assertEqual((vieja.price_unit, nueva.price_unit), (150.0, 200.0))
        # Y al revés: una cotización de antes de la campaña, con una línea agregada en la campaña.
        antes = self.env['sale.order'].create({
            'partner_id': cliente.id, 'pricelist_id': self.tarifa.id,
            'order_line': [Command.create({'product_id': variante.id})]})
        self.assertEqual(antes.order_line.price_unit, 200.0)
        with freeze_time('2026-11-28 15:00:00'):
            en_campana = self.env['sale.order.line'].create({'order_id': antes.id, 'product_id': variante.id})
            self.assertEqual(en_campana.price_unit, 150.0)

    def test_la_vendedora_no_le_cambia_la_fecha_del_precio_a_una_linea(self):
        self._en_campana()
        vendedora = self.env['res.users'].create({
            'name': 'Vendedora fecha línea', 'login': 'vendedora_fecha_linea',
            'group_ids': [Command.set([self.env.ref('dcasa_base.group_vendedora').id])]})
        cliente = self.env['res.partner'].create({'name': 'Cliente fecha línea'})
        orden = self.env['sale.order'].with_user(vendedora).create({
            'partner_id': cliente.id, 'user_id': vendedora.id, 'pricelist_id': self.tarifa.id})
        linea = self.env['sale.order.line'].with_user(vendedora).create({
            'order_id': orden.id, 'product_id': self.cama.product_variant_id.id,
            'dcasa_fecha_precio': datetime(2026, 11, 28, 15, 0)})
        self.assertEqual(linea.dcasa_fecha_precio, datetime(2026, 11, 20, 12, 0), 'la de hoy, no la que mandó')
        self.assertEqual(linea.price_unit, 200.0)
        with self.assertRaises(AccessError):
            linea.with_user(vendedora).write({'dcasa_fecha_precio': datetime(2026, 11, 28, 15, 0)})

    def test_los_textos_con_el_nombre_en_femenino_o_en_plural(self):
        self._en_campana()
        casos = {
            'Black Friday': ('Ver todo el Black Friday', 'me interesa del Black Friday: '),
            'Navidad': ('Ver toda la Navidad', 'me interesa de la Navidad: '),
            'Semana del Mueble': ('Ver toda la Semana del Mueble', 'me interesa de la Semana del Mueble: '),
            'Fiestas Patrias': ('Ver todas las Fiestas Patrias', 'me interesa de las Fiestas Patrias: '),
            'Día de las Madres': ('Ver todo el Día de las Madres', 'me interesa del Día de las Madres: '),
            'La Gran Venta': ('Ver toda la Gran Venta', 'me interesa de la Gran Venta: '),
        }
        for nombre, (ver_todo, interesa) in casos.items():
            with self.subTest(nombre):
                self.campana.name = nombre
                self.assertEqual(self.website._dcasa_campana_ver_todo(), ver_todo)
                self.assertIn(interesa, unquote(self.website._dcasa_bw_whatsapp(self.cama, 'DC-1')))
        self.assertEqual(articulo_y_nombre('Cyber Monday'), ('el', 'Cyber Monday'))
        self.assertEqual(articulo_y_nombre('Promociones de enero'), ('las', 'Promociones de enero'))
        self.assertEqual(articulo_y_nombre('Mes de la Patria'), ('el', 'Mes de la Patria'))
        self.assertEqual(articulo_y_nombre('Promo Navideña'), ('la', 'Promo Navideña'))
        self.assertEqual(articulo_y_nombre('Expo Muebles'), ('la', 'Expo Muebles'))
        self.assertEqual(articulo_y_nombre('Promos de enero'), ('las', 'Promos de enero'))

    def test_la_tarifa_de_respaldo_se_retira_cuando_el_sitio_tiene_una_propia(self):
        Tarifa = self.env['product.pricelist']
        dominio = Tarifa._get_website_pricelists_domain(self.website)
        respaldo = Tarifa.search(dominio).filtered('dcasa_respaldo_del_sitio')
        if not respaldo:
            self.skipTest('En esta base el sitio ya tenía su tarifa: no hubo respaldo')
        self._en_campana()
        self.assertTrue(self._reglas(self.cama).filtered(lambda r: r.pricelist_id == respaldo))
        cupon = Tarifa.create({'name': 'Cupón (prueba)', 'code': 'PRUEBA10', 'selectable': False})
        self.assertTrue(respaldo.selectable, 'una tarifa de cupón no es la del visitante: el respaldo se queda')
        propia = Tarifa.create({'name': 'Solo la web (prueba)', 'website_id': self.website.id})
        self.assertFalse(respaldo.selectable)
        self.assertEqual(Tarifa.search(dominio), propia | cupon)
        self.assertEqual(self._reglas(self.cama).pricelist_id, propia, 'la campaña pasa a la tarifa del sitio')

    def test_limites_utc(self):
        self.assertEqual(limites_utc(date(2026, 11, 27), date(2026, 11, 27)),
                         (datetime(2026, 11, 27, 5, 0, 0), datetime(2026, 11, 28, 4, 59, 59)))

    def test_la_tarifa_queda_ofrecida_al_sitio(self):
        if not self.env['res.groups']._is_feature_enabled('product.group_product_pricelist'):
            self.skipTest('Sin tarifas encendidas no hay nada que ofrecer')
        Tarifa = self.env['product.pricelist']
        tarifa = self.website.user_id.partner_id.property_product_pricelist
        if not tarifa or tarifa.website_id:
            self.skipTest('La tarifa del visitante ya es del sitio')
        Tarifa.search(Tarifa._get_website_pricelists_domain(self.website)).write({'selectable': False, 'code': False})
        self.assertFalse(Tarifa.search_count(Tarifa._get_website_pricelists_domain(self.website)))
        self.env['dcasa.campana']._dcasa_tarifa_del_sitio()
        self.assertTrue(tarifa.selectable)
        self.assertIn(tarifa, Tarifa.search(Tarifa._get_website_pricelists_domain(self.website)))


@tagged('post_install', '-at_install')
class TestCampanaCarritos(_Base, TransactionCase):
    """Los carritos abiertos se ponen al día cuando cambia lo que rige; los apartados y los pedidos, nunca."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._preparar()
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente carrito'})

    def _pedido(self, **valores):
        return self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'website_id': self.website.id, 'pricelist_id': self.tarifa.id,
            'order_line': [Command.create({'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})],
            **valores})

    def test_el_carrito_viejo_toma_el_precio_de_campana(self):
        param = self.env['ir.config_parameter'].sudo()
        param.set_param(PARAM_FIRMA_CARRITOS, '')
        carrito = self._pedido()
        apartado = self._pedido()
        if 'dcasa_apartado_vence' in apartado._fields:
            apartado.dcasa_apartado_vence = fields.Date.today() + timedelta(days=3)
        self.assertEqual(carrito.order_line.price_unit, 200.0)
        # Empieza la campaña hoy (los carritos de la tienda se calculan con la hora actual).
        hoy = fields.Date.context_today(self.campana)
        self.campana.write({'fecha_inicio': hoy - timedelta(days=1), 'fecha_fin': hoy + timedelta(days=1)})
        self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 150.0})
        self.assertGreaterEqual(self.env['dcasa.campana']._dcasa_campana_carritos_al_dia(), 1)
        self.assertEqual(carrito.order_line.price_unit, 150.0)
        if 'dcasa_apartado_vence' in apartado._fields:
            self.assertEqual(apartado.order_line.price_unit, 200.0, 'un apartado guarda el precio que se le dio')
        # Nada cambió: no vuelve a tocar nada.
        self.assertEqual(self.env['dcasa.campana']._dcasa_campana_carritos_al_dia(), 0)
        # Termina (Gerencia quita el precio): vuelve al normal.
        self.cama.dcasa_campana_precio = False
        self.env['dcasa.campana']._dcasa_campana_carritos_al_dia()
        self.assertEqual(carrito.order_line.price_unit, 200.0)

    def test_poner_al_dia_los_precios_no_marca_el_carrito_como_tocado_por_el_equipo(self):
        """Cuarta revisión: el cron (que corre como OdooBot, un usuario interno) y el pago del visitante recalculan el
        precio de las líneas; eso lo hace el servidor y no debe dejar el carrito como «tocado por el equipo» (la venta
        saldría señalada como del equipo en toda la campaña)."""
        param = self.env['ir.config_parameter'].sudo()
        param.set_param(PARAM_FIRMA_CARRITOS, '')
        publico = self.env.ref('base.public_user')
        por_cron, por_pago = self._pedido(), self._pedido()
        for carrito in (por_cron, por_pago):
            carrito._dcasa_escribir_marca(dcasa_nacio_en_web=True, dcasa_creada_por_id=publico.id)
        hoy = fields.Date.context_today(self.campana)
        self.campana.write({'fecha_inicio': hoy - timedelta(days=1), 'fecha_fin': hoy + timedelta(days=1)})
        self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 150.0})
        self.assertFalse(self.env.user.share, 'el cron corre como un usuario interno (OdooBot)')
        self.assertGreaterEqual(self.env['dcasa.campana']._dcasa_campana_carritos_al_dia(), 1)
        self.assertEqual(por_cron.order_line.price_unit, 150.0)
        self.assertFalse(por_cron.dcasa_tocada_por_id)
        por_pago.with_user(publico).sudo()._dcasa_campana_al_dia()      # lo que hace el pago del visitante
        self.assertEqual(por_pago.order_line.price_unit, 150.0)
        self.assertFalse(por_pago.dcasa_tocada_por_id)

    def test_la_primera_vez_solo_anota(self):
        param = self.env['ir.config_parameter'].sudo()
        param.search([('key', '=', PARAM_FIRMA_CARRITOS)]).unlink()
        carrito = self._pedido()
        hoy = fields.Date.context_today(self.campana)
        self.campana.write({'fecha_inicio': hoy - timedelta(days=1), 'fecha_fin': hoy + timedelta(days=1)})
        self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 150.0})
        param.search([('key', '=', PARAM_FIRMA_CARRITOS)]).unlink()
        al_dia = self.env['dcasa.campana']._dcasa_campana_carritos_al_dia()
        self.assertEqual(al_dia, 0, 'sin firma anterior: solo anota')
        self.assertIsNotNone(param.get_param(PARAM_FIRMA_CARRITOS, None))
        self.assertEqual(carrito.order_line.price_unit, 200.0)

    def test_al_pagar_el_carrito_toma_el_precio_que_rige(self):
        carrito = self._pedido()
        hoy = fields.Date.context_today(self.campana)
        self.campana.write({'fecha_inicio': hoy - timedelta(days=1), 'fecha_fin': hoy + timedelta(days=1)})
        self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 150.0})
        self.assertEqual(carrito.order_line.price_unit, 200.0, 'Odoo no recalcula sola la línea que ya estaba')
        carrito._dcasa_campana_al_dia()   # lo que hace _check_cart antes de pagar
        self.assertEqual(carrito.order_line.price_unit, 150.0)


@tagged('post_install', '-at_install')
class TestCampanaSitio(_Base, HttpCase):

    def setUp(self):
        super().setUp()
        self._preparar()
        hoy = fields.Date.context_today(self.campana)
        self.hoy = hoy

    def _activa(self, precio=150.0):
        self.campana.write({'fecha_inicio': self.hoy - timedelta(days=1), 'fecha_fin': self.hoy + timedelta(days=2)})
        self.cama.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': precio})

    def test_activa_portada_menu_y_pagina(self):
        self._activa()
        portada = self.url_open('/').text
        self.assertIn('Black Friday', portada)
        self.assertIn('CAMA CAMPAÑA DE PRUEBA'.title()[:10], portada.title())
        self.assertIn('o_dcasa_precio_antes', portada, 'el precio normal tachado')
        self.assertRegex(portada, r'150[.,]00')
        self.assertIn('href="/promociones"', portada)
        self.assertIn('o_dcasa_menu_promo', portada, '«Promociones» en el menú')
        # Los combos son intocables (la dueña, 2026-11-16): su línea sigue, con su precio de siempre.
        self.assertIn('Combo con colchón First Class', portada, 'con precio de campaña, el combo sigue')
        self.assertRegex(portada, r'469[.,]99')
        pagina = self.url_open('/promociones')
        self.assertEqual(pagina.status_code, 200)
        self.assertIn('Black Friday', pagina.text)
        vieja = self.url_open('/black-weekend', allow_redirects=False)
        self.assertEqual(vieja.status_code, 301)
        self.assertTrue(vieja.headers['Location'].endswith('/promociones'))

    def test_sin_precio_de_campana_sale_el_combo_y_el_normal(self):
        self._activa(precio=False)
        portada = self.url_open('/').text
        self.assertIn('Combo con colchón First Class', portada)
        self.assertRegex(portada, r'200[.,]00')

    def test_nombre_en_femenino_en_la_portada_y_la_pagina(self):
        self._activa()
        self.campana.name = 'Navidad'
        portada = self.url_open('/').text
        self.assertIn('Ver toda la Navidad', portada)
        self.assertNotIn('Ver todo el Navidad', portada)
        pagina = unquote(self.url_open('/promociones').text)
        self.assertIn('quiero información de la Navidad', pagina)
        self.assertIn('me interesa de la Navidad', pagina)

    def test_frase_del_panel(self):
        self._activa()
        self.campana.frase = 'Muebles seleccionados'
        self.assertIn('Muebles seleccionados', self.url_open('/').text)

    def test_apagada_no_sale_nada(self):
        portada = self.url_open('/').text
        self.assertNotIn('o_dcasa_menu_promo', portada)
        self.assertNotIn('class="o_dcasa_bw"', portada)
        self.assertEqual(self.url_open('/promociones').status_code, 404)
