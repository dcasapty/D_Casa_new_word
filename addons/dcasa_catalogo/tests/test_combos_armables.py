"""Combos cama + colchón que se arman en la venta (pedido de la dueña, 2026-10-22), con productos inventados.

Regla de la dueña: cada colchón, por medida, tiene un «precio en combo» que pone Gerencia; se cobra si en la misma venta
va una cama de su misma medida; sin precio en combo, va a su precio normal; la cama, siempre a su precio normal.
Estas pruebas fijan las reglas en el servidor (no en la pantalla): medidas, existencias, cambiar o quitar la cama, el
tope de descuento de la vendedora, la factura, el PDF y que los combos de siempre (tipo «Combo») siguen igual.
"""
import os
import re
from html import unescape
from unittest.mock import patch

from odoo import Command
from odoo.addons.dcasa_catalogo import reglas
from odoo.addons.dcasa_catalogo.catalogo import atributo_tamano
from odoo.addons.dcasa_catalogo.models import combo_armable
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.misc import file_path

NORMAL_KING, COMBO_KING = 300.0, 260.0
NORMAL_QUEEN, COMBO_QUEEN = 250.0, 215.0


def texto_de(html):
    html = re.sub(r'<style.*?</style>', '', html, flags=re.S)
    html = unescape(re.sub(r'<[^>]+>', '\n', html)).replace('\xa0', ' ')
    lineas = []
    for linea in (x.strip() for x in html.split('\n')):
        if not linea:
            continue
        if lineas and lineas[-1] == '$':
            lineas[-1] = f'$ {linea}'
        else:
            lineas.append(linea)
    return lineas


@tagged('post_install', '-at_install')
class TestReglasCombos(TransactionCase):
    """Las reglas puras: qué es cama o colchón, su medida y quién va con quién."""

    def test_tipo_por_el_nombre(self):
        casos = {
            'Colchón Flex semiortopédico': 'colchon',
            'COLCHON DULCESUENOS SEMI RESORTE Q (A) / DSRSOQ': 'colchon',
            'Cama tapizada King – beige': 'cama',
            'Camarote full': 'cama',
            'BOX SPRING DE METAL SENCILLO TAMAÑO FULL': 'cama',
            'Base de cama metálica Queen – negro': 'cama',
            'BOX TAPIZADO CON ELEVADOR BEIGE TAMAÑO FULL': 'cama',
            'COMBO CAMA FELPA KING + COLCHON FIRST': None,
            'Sofá cama gris': None,
            'COLCHONETA TWIN SENCILLA': None,
            'Protector de colchón queen': None,
            'Mesa de noche blanca': None,
            'CABECERO TAMAÑO QUEEN': None,
        }
        for nombre, tipo in casos.items():
            self.assertEqual(reglas.tipo_combo_del_nombre(nombre), tipo, nombre)

    def test_medida_por_el_nombre(self):
        self.assertEqual(reglas.medida_del_nombre('Cama king de metal'), 'King')
        self.assertEqual(reglas.medida_del_nombre('COLCHON DR DREAM FULL 4/6', 'colchon'), 'Full')
        self.assertEqual(reglas.medida_del_nombre('COLCHON IMPERIAL 3/4 BUEN SUEÑO', 'colchon'), 'Twin')
        self.assertEqual(reglas.medida_del_nombre('COLCHON DULCESUENOS SEMI RESORTE Q (A)', 'colchon'), 'Queen')
        self.assertIsNone(reglas.medida_del_nombre('CAMA ... Q (A)', 'cama'), 'La «Q» suelta solo vale en colchones')
        self.assertIsNone(reglas.medida_del_nombre('Cama con estantes'))
        self.assertIsNone(reglas.medida_del_nombre('Cama full o queen'), 'Dos medidas: no se adivina')
        self.assertEqual(reglas.medida_de_valor('queen'), 'Queen')
        self.assertIsNone(reglas.medida_de_valor('Matrimonial'))

    def test_emparejar_respeta_las_camas_que_hay(self):
        camas = [{'clave': 'C1', 'medida': 'King', 'capacidad': 1}]
        colchones = [
            {'clave': 'M1', 'medida': 'King', 'cantidad': 1, 'con_precio': False, 'preferida': None},
            {'clave': 'M2', 'medida': 'King', 'cantidad': 1, 'con_precio': True, 'preferida': None},
            {'clave': 'M3', 'medida': 'Queen', 'cantidad': 1, 'con_precio': True, 'preferida': None},
        ]
        # Una sola cama king: el colchón CON precio en combo gana aunque esté después; el de otra medida, nada.
        self.assertEqual(reglas.emparejar_combos(camas, colchones), {'M2': ('C1', True)})

    def test_emparejar_cantidades_camarote_y_la_cama_preferida(self):
        camas = [{'clave': 'C1', 'medida': 'Twin', 'capacidad': 1},
                 {'clave': 'C2', 'medida': 'Twin', 'capacidad': 3}]   # un camarote triple
        colchones = [{'clave': 'M1', 'medida': 'Twin', 'cantidad': 3, 'con_precio': True, 'preferida': 'C2'},
                     {'clave': 'M2', 'medida': 'Twin', 'cantidad': 2, 'con_precio': True, 'preferida': None}]
        pares = reglas.emparejar_combos(camas, colchones)
        self.assertEqual(pares, {'M1': ('C2', True)}, 'Quedó una sola plaza libre: dos colchones más no caben')
        colchones[1]['cantidad'] = 1
        self.assertEqual(reglas.emparejar_combos(camas, colchones), {'M1': ('C2', True), 'M2': ('C1', True)})


class CombosCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env['ir.config_parameter'].sudo().set_param('dcasa.descuento_max_vendedora', '10')
        cls.company = cls.env.company
        cls.itbms = cls.company.account_sale_tax_id
        cls.ubicacion = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1).lot_stock_id
        atributo, valores = atributo_tamano(cls.env)
        base = {'type': 'consu', 'is_storable': True, 'invoice_policy': 'order',
                'taxes_id': [Command.set(cls.itbms.ids)]}
        Plantilla = cls.env['product.template']
        # Cama de una sola medida, que la dice en el nombre (como «Cama king de metal»).
        cls.cama_king = Plantilla.create({**base, 'name': 'CAMA DE PRUEBA KING', 'list_price': 400.0}) \
            .product_variant_id
        # Cama con variantes de «Tamaño» (Queen y King).
        cama_var = Plantilla.create({**base, 'name': 'CAMA DE PRUEBA CON TAMAÑOS', 'list_price': 350.0,
                                     'attribute_line_ids': [Command.create({
                                         'attribute_id': atributo.id,
                                         'value_ids': [Command.set((valores['Queen'] | valores['King']).ids)]})]})
        cls.cama_var_queen, cls.cama_var_king = cls._por_medida(cama_var, 'Queen', 'King')
        # Colchón con variantes Queen y King; el precio en combo es POR VARIANTE.
        colchon = Plantilla.create({**base, 'name': 'COLCHON DE PRUEBA', 'list_price': NORMAL_QUEEN,
                                    'attribute_line_ids': [Command.create({
                                        'attribute_id': atributo.id,
                                        'value_ids': [Command.set((valores['Queen'] | valores['King']).ids)]})]})
        colchon.attribute_line_ids.product_template_value_ids.filtered(lambda v: v.name == 'King').price_extra = \
            NORMAL_KING - NORMAL_QUEEN
        cls.colchon_queen, cls.colchon_king = cls._por_medida(colchon, 'Queen', 'King')
        (cls.colchon_queen | cls.colchon_king).invalidate_recordset(['lst_price'])
        cls.colchon_king.dcasa_precio_combo = COMBO_KING
        cls.colchon_queen.dcasa_precio_combo = COMBO_QUEEN
        # Un colchón king sin precio en combo (nadie lo puso: va a precio normal).
        cls.colchon_sin = Plantilla.create({**base, 'name': 'COLCHON DE PRUEBA SIN PRECIO KING',
                                            'list_price': 280.0}).product_variant_id
        cls.mesa = Plantilla.create({**base, 'name': 'MESA DE NOCHE DE PRUEBA', 'list_price': 80.0}).product_variant_id
        for variante in (cls.cama_king, cls.cama_var_queen, cls.cama_var_king, cls.colchon_king, cls.colchon_queen,
                         cls.colchon_sin):
            cls._stock(variante, 5)
        cls.vendedora = new_test_user(cls.env, login='combo_arm_vendedora', groups='dcasa_base.group_vendedora')
        cls.otra = new_test_user(cls.env, login='combo_arm_otra', groups='dcasa_base.group_vendedora')
        cls.gerencia = new_test_user(cls.env, login='combo_arm_gerencia', groups='dcasa_base.group_gerencia')
        cls.cliente = cls.env['res.partner'].create({
            'name': 'CLIENTE DE PRUEBA COMBOS', 'phone': '6000-0099', 'email': 'cliente.combos@example.com'})

    @classmethod
    def _por_medida(cls, plantilla, *medidas):
        por_nombre = {v.product_template_attribute_value_ids.name: v for v in plantilla.product_variant_ids}
        return [por_nombre[m] for m in medidas]

    @classmethod
    def _stock(cls, variante, cantidad):
        cls.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': variante.id, 'location_id': cls.ubicacion.id,
            'inventory_quantity': cantidad})._apply_inventory()

    def orden(self, usuario=None, productos=()):
        usuario = usuario or self.vendedora
        return self.env['sale.order'].with_user(usuario).create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': p.id}) for p in productos]})

    def linea(self, orden, producto):
        return orden.order_line.filtered(lambda ln: ln.product_id == producto)


@tagged('post_install', '-at_install')
class TestProductosParaCombos(CombosCommon):

    def test_tipo_y_medida_salen_del_tamano_o_del_nombre(self):
        self.assertEqual((self.cama_king.dcasa_tipo_combo, self.cama_king.dcasa_medida), ('cama', 'King'))
        self.assertEqual((self.cama_var_queen.dcasa_medida, self.cama_var_king.dcasa_medida), ('Queen', 'King'))
        self.assertEqual((self.colchon_king.dcasa_tipo_combo, self.colchon_king.dcasa_medida), ('colchon', 'King'))
        self.assertFalse(self.mesa.dcasa_tipo_combo)
        self.assertEqual((self.colchon_king.dcasa_combo_ahorro, self.colchon_king.dcasa_combo_aviso), (40.0, False))
        self.assertEqual(self.colchon_sin.dcasa_combo_aviso, 'Sin precio en combo: va a precio normal')

    def test_gerencia_corrige_la_medida_y_se_respeta_aunque_el_nombre_no_la_diga(self):
        cama = self.env['product.product'].create({'name': 'CAMA DE PRUEBA SIN MEDIDA', 'list_price': 90.0})
        self.assertEqual((cama.dcasa_tipo_combo, cama.dcasa_medida), ('cama', False))
        self.assertEqual(cama.dcasa_combo_aviso, 'Falta la medida')
        cama.with_user(self.gerencia).dcasa_medida = 'Full'
        cama.product_tmpl_id.with_user(self.gerencia).name = 'CAMA DE PRUEBA SIN MEDIDA (ROBLE)'
        self.assertEqual(cama.dcasa_medida, 'Full', 'Renombrar sin decir la medida no borra la que puso Gerencia')

    def test_el_precio_en_combo_menor_que_el_normal_mayor_que_cero_y_solo_en_colchones(self):
        Gerencia = self.colchon_king.with_user(self.gerencia)
        with self.assertRaisesRegex(ValidationError, 'menor que su precio normal'):
            Gerencia.dcasa_precio_combo = NORMAL_KING
        with self.assertRaisesRegex(ValidationError, 'mayor que 0'):
            Gerencia.dcasa_precio_combo = -5
        with self.assertRaisesRegex(ValidationError, 'solo los colchones'):
            self.cama_king.with_user(self.gerencia).dcasa_precio_combo = 100
        Gerencia.dcasa_precio_combo = 0     # vacío: vuelve a precio normal
        self.assertEqual(self.colchon_king.dcasa_combo_aviso, 'Sin precio en combo: va a precio normal')

    def test_solo_gerencia_pone_el_precio_en_combo_la_medida_y_el_tipo(self):
        with self.assertRaisesRegex(AccessError, 'Solo Gerencia'):
            self.colchon_king.with_user(self.vendedora).dcasa_precio_combo = 200
        with self.assertRaisesRegex(AccessError, 'Solo Gerencia'):
            self.colchon_king.with_user(self.vendedora).dcasa_medida = 'Queen'
        with self.assertRaisesRegex(AccessError, 'Solo Gerencia'):
            self.mesa.product_tmpl_id.with_user(self.vendedora).dcasa_tipo_combo = 'cama'
        with self.assertRaisesRegex(AccessError, 'Solo Gerencia'):
            self.cama_king.product_tmpl_id.with_user(self.vendedora).dcasa_colchones_por_cama = 3
        # Renombrar sí le toca a la vendedora, y el tipo que sugiere el nombre nuevo se guarda sin error.
        self.mesa.product_tmpl_id.with_user(self.vendedora).write({
            'name': 'MESA DE NOCHE DE PRUEBA (NOGAL)', 'dcasa_tipo_combo': False})
        self.assertEqual(self.colchon_king.dcasa_precio_combo, COMBO_KING)

    def test_la_lista_de_precios_en_combo_existe_para_gerencia(self):
        accion = self.cama_king.product_tmpl_id.with_user(self.gerencia).action_dcasa_precios_combo()
        self.assertEqual(accion['res_model'], 'product.product')
        self.assertIn(('product_tmpl_id', '=', self.cama_king.product_tmpl_id.id), accion['domain'])
        menu = self.env.ref('dcasa_catalogo.menu_precios_combo')
        self.assertIn(self.env.ref('sales_team.group_sale_manager'), menu.group_ids)

    def test_el_boton_va_en_la_ficha_del_producto_y_no_en_la_variante(self):
        # La ficha de la variante hereda de la del producto: si el botón llegara ahí, Odoo no la cargaría.
        plantilla = self.env['product.template'].with_user(self.gerencia).get_views([(False, 'form')])
        variante = self.env['product.product'].with_user(self.gerencia).get_views([(False, 'form')])
        self.assertIn('action_dcasa_precios_combo', plantilla['views']['form']['arch'])
        self.assertNotIn('action_dcasa_precios_combo', variante['views']['form']['arch'])


@tagged('post_install', '-at_install')
class TestPrecioEnCombo(CombosCommon):

    def test_cama_y_colchon_de_la_misma_medida_van_a_precio_en_combo(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        cama, colchon = self.linea(orden, self.cama_king), self.linea(orden, self.colchon_king)
        self.assertEqual((cama.price_unit, colchon.price_unit), (400.0, COMBO_KING))
        self.assertEqual(colchon.dcasa_combo_cama_id, cama)
        self.assertTrue(colchon.dcasa_combo_con_precio)
        self.assertEqual((colchon.dcasa_combo_ahorro, orden._dcasa_ahorro_combos()), (40.0, 40.0))
        self.assertEqual(colchon.dcasa_combo_texto, 'Combo · ahorras $40.00')
        self.assertEqual(cama.dcasa_combo_texto, 'Combo')
        self.assertEqual(colchon.technical_price_unit, colchon.price_unit, 'No queda como «precio a mano»')

    def test_medidas_distintas_colchon_solo_o_sin_precio_en_combo_van_a_precio_normal(self):
        orden = self.orden(productos=[self.cama_var_queen, self.colchon_king, self.colchon_sin])
        self.assertEqual(self.linea(orden, self.colchon_king).price_unit, NORMAL_KING, 'Cama queen, colchón king')
        orden = self.orden(productos=[self.colchon_queen])
        self.assertEqual(orden.order_line.price_unit, NORMAL_QUEEN, 'Sin cama no hay combo')
        orden = self.orden(productos=[self.cama_king, self.colchon_sin])
        colchon = self.linea(orden, self.colchon_sin)
        self.assertEqual(colchon.price_unit, 280.0, 'Sin precio en combo: precio normal, no se inventa ninguno')
        self.assertEqual(colchon.dcasa_combo_texto, 'Combo · sin precio en combo')

    def test_la_variante_de_la_cama_es_la_que_cuenta(self):
        orden = self.orden(productos=[self.cama_var_queen, self.colchon_queen])
        self.assertEqual(self.linea(orden, self.colchon_queen).price_unit, COMBO_QUEEN)

    def test_quitar_la_cama_devuelve_el_colchon_a_su_precio_normal(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        self.linea(orden, self.cama_king).with_user(self.vendedora).unlink()
        colchon = orden.order_line
        self.assertEqual((colchon.price_unit, colchon.dcasa_combo_con_precio), (NORMAL_KING, False))
        self.assertFalse(colchon.dcasa_combo_cama_id)
        # Y al volver a poner la cama, vuelve el precio en combo.
        self.env['sale.order.line'].with_user(self.vendedora).create(
            {'order_id': orden.id, 'product_id': self.cama_king.id})
        self.assertEqual(colchon.price_unit, COMBO_KING)

    def test_cambiar_la_cama_por_otra_medida_o_bajarla_a_cero(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        cama, colchon = self.linea(orden, self.cama_king), self.linea(orden, self.colchon_king)
        cama.with_user(self.vendedora).product_id = self.cama_var_queen
        self.assertEqual(colchon.price_unit, NORMAL_KING)
        cama.with_user(self.vendedora).product_id = self.cama_var_king
        self.assertEqual(colchon.price_unit, COMBO_KING)
        cama.with_user(self.vendedora).product_uom_qty = 0
        self.assertEqual(colchon.price_unit, NORMAL_KING)

    def test_mas_colchones_que_camas_van_a_precio_normal(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        colchon = self.linea(orden, self.colchon_king)
        colchon.with_user(self.vendedora).product_uom_qty = 2
        self.assertEqual(colchon.price_unit, NORMAL_KING, 'Dos colchones y una cama: no es combo')
        self.linea(orden, self.cama_king).with_user(self.vendedora).product_uom_qty = 2
        self.assertEqual(colchon.price_unit, COMBO_KING, 'Dos camas y dos colchones: dos combos')
        self.assertEqual(colchon.dcasa_combo_ahorro, 80.0)

    def test_un_camarote_lleva_varios_colchones(self):
        self.cama_king.product_tmpl_id.with_user(self.gerencia).dcasa_colchones_por_cama = 2
        orden = self.orden(productos=[self.cama_king])
        self.env['sale.order.line'].with_user(self.vendedora).create(
            {'order_id': orden.id, 'product_id': self.colchon_king.id, 'product_uom_qty': 2})
        self.assertEqual(self.linea(orden, self.colchon_king).price_unit, COMBO_KING)

    def test_el_colchon_antes_que_la_cama_en_la_misma_carga(self):
        """Juan y Brian crean la cotización de una vez; el orden de las líneas no cambia el precio."""
        orden = self.orden(productos=[self.colchon_king, self.cama_king])
        self.assertEqual(self.linea(orden, self.colchon_king).price_unit, COMBO_KING)

    def test_la_tienda_en_linea_no_arma_combos(self):
        website = self.env['website'].search([], limit=1)
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'website_id': website.id,
            'order_line': [Command.create({'product_id': p.id}) for p in (self.cama_king, self.colchon_king)]})
        self.assertEqual(self.linea(orden, self.colchon_king).price_unit, NORMAL_KING)

    def test_actualizar_precios_conserva_el_combo(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        orden.with_user(self.vendedora).action_update_prices()
        self.assertEqual(self.linea(orden, self.colchon_king).price_unit, COMBO_KING)


@tagged('post_install', '-at_install')
class TestTopeYCombos(CombosCommon):
    """El precio en combo lo autorizó Gerencia: no es rebaja de la vendedora, y no abre huecos."""

    def test_la_vendedora_no_pone_el_precio_en_combo_a_mano_sin_la_cama(self):
        orden = self.orden(productos=[self.colchon_king])
        with self.assertRaisesRegex(ValidationError, 'puedes rebajar hasta 10'):
            orden.order_line.with_user(self.vendedora).price_unit = COMBO_KING

    def test_sobre_el_precio_en_combo_rebaja_hasta_su_tope_y_no_mas(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        colchon = self.linea(orden, self.colchon_king)
        colchon.with_user(self.vendedora).discount = 10
        self.assertAlmostEqual(colchon.price_subtotal, COMBO_KING * 0.9)
        with self.assertRaisesRegex(ValidationError, 'puedes rebajar hasta 10'):
            colchon.with_user(self.vendedora).discount = 11

    def test_un_precio_a_mano_en_el_colchon_no_sobrevive_si_se_quita_la_cama(self):
        """El hueco: la vendedora deja el colchón al precio de combo «a mano» y después quita la cama."""
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        colchon = self.linea(orden, self.colchon_king)
        colchon.with_user(self.vendedora).price_unit = COMBO_KING * 0.95     # rebaja suya, dentro del tope
        self.linea(orden, self.cama_king).with_user(self.vendedora).unlink()
        self.assertEqual(colchon.price_unit, NORMAL_KING, 'Sin cama, el colchón vuelve a su precio normal')

    def test_quitar_la_cama_con_un_descuento_global_no_bloquea_a_la_vendedora(self):
        descuento = self.env['product.product'].create({
            'name': 'DESCUENTO DE PRUEBA', 'type': 'service', 'list_price': 0.0, 'taxes_id': [Command.clear()]})
        self.company.sale_discount_product_id = descuento
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        asistente = self.env['sale.order.discount'].with_user(self.vendedora).with_context(
            active_id=orden.id, active_model='sale.order').create({
                'sale_order_id': orden.id, 'discount_type': 'so_discount', 'discount_percentage': 0.02})
        asistente.action_apply_discount()
        # Si el colchón se quedara a precio de combo, el tope lo vería como rebaja y bloquearía quitar la cama.
        self.linea(orden, self.cama_king).with_user(self.vendedora).unlink()
        self.assertEqual(self.linea(orden, self.colchon_king).price_unit, NORMAL_KING)

    def test_el_flag_del_combo_no_se_falsea_a_mano(self):
        orden = self.orden(productos=[self.colchon_king])
        orden.order_line.with_user(self.vendedora).write({'dcasa_combo_con_precio': True})
        self.assertFalse(orden.order_line.dcasa_combo_con_precio, 'El sistema lo vuelve a calcular')
        self.assertEqual(orden.order_line.price_unit, NORMAL_KING)


@tagged('post_install', '-at_install')
class TestPanelArmarCombo(CombosCommon):

    def test_armar_cambiar_y_quitar_desde_el_panel(self):
        orden = self.orden()
        Orden = orden.with_user(self.vendedora)
        accion = Orden.action_dcasa_armar_combo()
        self.assertEqual((accion['tag'], accion['target'], accion['params']['order_id']),
                         ('dcasa_armar_combo', 'new', orden.id))
        panel = Orden.dcasa_combo_agregar(cama_id=self.cama_king.id, colchon_id=self.colchon_king.id, cantidad=2)
        (combo,) = panel['combos']
        self.assertEqual((combo['cama']['cantidad'], combo['colchones'][0]['cantidad']), (2.0, 2.0))
        self.assertEqual((combo['total'], combo['ahorro']), (2 * 400.0 + 2 * COMBO_KING, 80.0))
        self.assertEqual(panel['ahorro_total'], 80.0)
        # Cambiar el colchón por el de la misma medida sin precio en combo: va a su precio normal.
        panel = Orden.dcasa_combo_cambiar(combo['cama']['linea_id'], colchon_id=self.colchon_sin.id)
        self.assertEqual(self.linea(orden, self.colchon_sin).price_unit, 280.0)
        self.assertFalse(panel['ahorro_total'])
        # Cambiar la cama por una queen exige un colchón queen…
        with self.assertRaisesRegex(UserError, 'misma medida'):
            Orden.dcasa_combo_cambiar(combo['cama']['linea_id'], cama_id=self.cama_var_queen.id)
        # …y con los dos cambios juntos, el colchón queen va a precio en combo.
        panel = Orden.dcasa_combo_cambiar(combo['cama']['linea_id'], cama_id=self.cama_var_queen.id,
                                          colchon_id=self.colchon_queen.id)
        self.assertEqual(orden.order_line.product_id, self.cama_var_queen | self.colchon_queen)
        self.assertEqual(self.linea(orden, self.colchon_queen).price_unit, COMBO_QUEEN)
        self.assertEqual(len(panel['combos']), 1)
        panel = Orden.dcasa_combo_quitar(panel['combos'][0]['cama']['linea_id'])
        self.assertFalse(orden.order_line)
        self.assertEqual(panel['combos'], [])

    def test_agregar_el_colchon_a_una_cama_que_ya_estaba(self):
        orden = self.orden(productos=[self.cama_king, self.mesa])
        panel = orden.with_user(self.vendedora).dcasa_combo_panel()
        (cama,) = panel['camas_solas']
        panel = orden.with_user(self.vendedora).dcasa_combo_agregar(
            colchon_id=self.colchon_king.id, cama_linea_id=cama['linea_id'])
        self.assertEqual(len(panel['combos']), 1)
        self.assertEqual(self.linea(orden, self.colchon_king).price_unit, COMBO_KING)

    def test_buscar_camas_y_ver_los_colchones_de_su_medida_con_existencia(self):
        Orden = self.orden().with_user(self.vendedora)
        camas = Orden.dcasa_combo_camas(texto='cama de prueba king')['camas']
        self.assertIn(self.cama_king.id, [c['id'] for c in camas])
        reinas = Orden.dcasa_combo_camas(medida='Queen')['camas']
        self.assertEqual({c['medida'] for c in reinas}, {'Queen'})
        self._stock(self.colchon_sin, 0)
        respuesta = Orden.dcasa_combo_colchones(self.cama_king.id)
        ids = [c['id'] for c in respuesta['colchones']]
        self.assertIn(self.colchon_king.id, ids)
        self.assertNotIn(self.colchon_queen.id, ids, 'Solo los de su medida')
        self.assertNotIn(self.colchon_sin.id, ids, 'Sin existencia no sale…')
        self.assertGreaterEqual(respuesta['agotados'], 1)
        todos = Orden.dcasa_combo_colchones(self.cama_king.id, todos=True)
        self.assertIn(self.colchon_sin.id, [c['id'] for c in todos['colchones']], '…salvo que se pidan todos')
        fila = next(c for c in respuesta['colchones'] if c['id'] == self.colchon_king.id)
        self.assertEqual((fila['precio'], fila['precio_combo'], fila['ahorro']), (NORMAL_KING, COMBO_KING, 40.0))
        self.assertNotIn('referencia_excel', fila)

    def test_una_cama_sin_medida_no_ofrece_colchones(self):
        cama = self.env['product.product'].create({'name': 'CAMA DE PRUEBA SIN MEDIDA', 'list_price': 90.0})
        respuesta = self.orden().with_user(self.vendedora).dcasa_combo_colchones(cama.id)
        self.assertTrue(respuesta['falta_medida'])
        self.assertEqual(respuesta['colchones'], [])

    def test_el_texto_del_excel_solo_lo_ve_gerencia_y_no_cuenta(self):
        self.cama_king.product_tmpl_id.dcasa_combo = 'Combo con colchón $999.99'
        orden = self.orden(usuario=self.gerencia)
        fila = next(c for c in orden.with_user(self.gerencia).dcasa_combo_camas(texto='CAMA DE PRUEBA KING')['camas']
                    if c['id'] == self.cama_king.id)
        self.assertEqual(fila['referencia_excel'], 'Combo con colchón $999.99')
        fila = next(c for c in self.orden().with_user(self.vendedora).dcasa_combo_camas(
            texto='CAMA DE PRUEBA KING')['camas'] if c['id'] == self.cama_king.id)
        self.assertNotIn('referencia_excel', fila)
        panel = orden.with_user(self.gerencia).dcasa_combo_agregar(
            cama_id=self.cama_king.id, colchon_id=self.colchon_king.id)
        self.assertEqual(panel['combos'][0]['total'], 400.0 + COMBO_KING)

    def test_no_se_arma_en_una_venta_confirmada_ni_en_la_de_otra_vendedora(self):
        orden = self.orden(productos=[self.mesa])
        orden.action_confirm()
        with self.assertRaisesRegex(UserError, 'ya no es una cotización'):
            orden.with_user(self.vendedora).dcasa_combo_agregar(
                cama_id=self.cama_king.id, colchon_id=self.colchon_king.id)
        ajena = self.orden(usuario=self.otra)
        with self.assertRaises(AccessError):
            ajena.with_user(self.vendedora).dcasa_combo_agregar(
                cama_id=self.cama_king.id, colchon_id=self.colchon_king.id)
        with self.assertRaises(AccessError):
            ajena.with_user(self.vendedora).dcasa_combo_panel()

    def test_no_se_mezclan_medidas_ni_productos_que_no_son_cama_o_colchon(self):
        Orden = self.orden().with_user(self.vendedora)
        with self.assertRaisesRegex(UserError, 'misma medida'):
            Orden.dcasa_combo_agregar(cama_id=self.cama_king.id, colchon_id=self.colchon_queen.id)
        with self.assertRaisesRegex(UserError, 'ya no está a la venta'):
            Orden.dcasa_combo_agregar(cama_id=self.mesa.id, colchon_id=self.colchon_king.id)
        with self.assertRaisesRegex(UserError, 'de 1 a 20'):
            Orden.dcasa_combo_agregar(cama_id=self.cama_king.id, colchon_id=self.colchon_king.id, cantidad=0)

    def test_el_boton_de_la_lista_de_lineas_abre_el_panel_de_su_cotizacion(self):
        orden = self.orden()
        accion = self.env['sale.order.line'].with_user(self.vendedora).with_context(
            order_id=orden.id).action_dcasa_armar_combo()
        self.assertEqual(accion['params']['order_id'], orden.id)


@tagged('post_install', '-at_install')
class TestFacturaYPapel(CombosCommon):

    def _combo_confirmado(self):
        orden = self.orden(usuario=self.gerencia, productos=[self.cama_king, self.colchon_king, self.mesa])
        orden.action_confirm()
        return orden

    def assertDescuentoEnSuRenglon(self, texto, descuento, donde):
        """Decisión de la dueña (2026-10-23): la cama y el colchón a su precio normal, «Combo cama + colchón» en los
        dos, y el descuento del combo en su propio renglón (no rebajado en ninguna pieza)."""
        self.assertEqual(texto.count('Combo cama + colchón'), 2, f'{donde}: las dos piezas')
        self.assertEqual(texto.count('Descuento combo cama + colchón'), 1, donde)
        i = texto.index('Descuento combo cama + colchón')
        self.assertEqual(' '.join(texto[i + 1:i + 3]), f'−$ {descuento}', f'{donde}: {texto[i:i + 4]}')
        normales = [pieza for pieza in texto if pieza.endswith(f'{NORMAL_KING:.2f}')]
        self.assertGreaterEqual(len(normales), 2, f'{donde}: el colchón a su precio normal, y su importe normal')
        self.assertNotIn(f'{COMBO_KING:.2f}', ' '.join(texto), f'{donde}: nunca el precio rebajado del colchón')
        self.assertFalse([pieza for pieza in texto if 'ahorras' in pieza], donde)

    def test_la_cotizacion_en_pdf_dice_combo_y_el_descuento_en_su_renglon(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        html = self.env['ir.actions.report']._render_qweb_html('sale.report_saleorder', orden.ids)[0].decode()
        self.assertDescuentoEnSuRenglon(texto_de(html), '40.00', 'cotización')
        self.assertEqual(orden.amount_untaxed, 400.0 + COMBO_KING, 'Las cuentas no cambian: solo cómo se ve')

    def test_el_papel_reparte_lo_que_vale_la_linea_al_centavo(self):
        """Con o sin ITBMS en la columna: importe normal − descuento = lo de la línea."""
        orden = self.orden(usuario=self.gerencia, productos=[self.cama_king, self.colchon_king, self.mesa])
        colchon = self.linea(orden, self.colchon_king)
        for campo in ('price_subtotal', 'price_total'):
            papel = colchon._dcasa_combo_en_papel(campo)
            self.assertEqual(papel['precio'], NORMAL_KING)
            self.assertAlmostEqual(papel['importe'] - papel['descuento'], colchon[campo], places=2)
        self.assertEqual(colchon._dcasa_combo_en_papel()['descuento'], NORMAL_KING - COMBO_KING)
        for otra in (self.cama_king, self.mesa):
            self.assertFalse(self.linea(orden, otra)._dcasa_combo_en_papel(), otra.name)

    def test_el_papel_no_inventa_un_precio_normal(self):
        """Revisión (2026-10-23): si el colchón ya no está al precio que le puso el sistema (la vendedora lo cambió a
        mano, aunque sea al precio normal) o lleva un descuento % encima, sale tal cual: el papel no se inventa un
        «precio normal» ni un descuento que el cliente no recibe, y lo que se ve cuadra."""
        orden = self.orden(usuario=self.gerencia, productos=[self.cama_king, self.colchon_king])
        colchon = self.linea(orden, self.colchon_king)
        self.assertTrue(colchon._dcasa_combo_en_papel())
        colchon.discount = 10.0
        self.assertFalse(colchon._dcasa_combo_en_papel(), 'con un % encima sale como antes')
        colchon.discount = 0.0
        for a_mano in (COMBO_KING - 10, NORMAL_KING):
            colchon.price_unit = a_mano
            self.assertFalse(colchon._dcasa_combo_en_papel(), a_mano)
        html = self.env['ir.actions.report']._render_qweb_html('sale.report_saleorder', orden.ids)[0].decode()
        texto = texto_de(html)
        self.assertNotIn('Descuento combo cama + colchón', texto)
        self.assertNotIn(f'{NORMAL_KING + NORMAL_KING - COMBO_KING:.2f}', ' '.join(texto))
        self.assertEqual(texto.count('Combo cama + colchón'), 2, 'sigue siendo un combo')

    def test_la_factura_no_inventa_un_precio_normal(self):
        """En el borrador de la factura: si cambian el precio o el producto de la línea del colchón, sale tal cual (y
        si ya no es el colchón, sin la marca del combo)."""
        factura = self._combo_confirmado()._create_invoices()
        colchon = factura.invoice_line_ids.filtered(lambda ln: ln.product_id == self.colchon_king)
        self.assertTrue(colchon._dcasa_combo_en_papel())
        colchon.price_unit = COMBO_KING - 10
        self.assertFalse(colchon._dcasa_combo_en_papel(), 'precio cambiado en la factura')
        colchon.price_unit = COMBO_KING
        self.assertTrue(colchon._dcasa_combo_en_papel())
        colchon.product_id = self.mesa
        colchon.price_unit = COMBO_KING
        self.assertFalse(colchon._dcasa_combo_en_papel(), 'ya no es el colchón del combo')
        self.assertNotEqual(colchon._dcasa_etiqueta(), 'Combo cama + colchón')

    def test_la_factura_lleva_el_combo_el_ahorro_y_el_inventario_por_pieza(self):
        orden = self._combo_confirmado()
        self.assertEqual(set(orden.picking_ids.move_ids.product_id.ids),
                         {self.cama_king.id, self.colchon_king.id, self.mesa.id}, 'Cada pieza sale de la bodega')
        factura = orden._create_invoices()
        factura.action_post()
        colchon = factura.invoice_line_ids.filtered(lambda ln: ln.product_id == self.colchon_king)
        cama = factura.invoice_line_ids.filtered(lambda ln: ln.product_id == self.cama_king)
        self.assertEqual((colchon.price_unit, colchon.dcasa_combo_rol, colchon.dcasa_combo_ahorro_unitario),
                         (COMBO_KING, 'colchon', 40.0))
        self.assertEqual(cama.dcasa_combo_rol, 'cama')
        self.assertEqual(factura._dcasa_ahorro_combos(), 40.0)
        self.assertEqual(factura.amount_untaxed, 400.0 + COMBO_KING + 80.0)
        html = self.env['ir.actions.report']._render_qweb_html('account.report_invoice', factura.ids)[0].decode()
        self.assertDescuentoEnSuRenglon(texto_de(html), '40.00', 'factura')
        # Una nota de crédito sale tal cual.
        nota = factura._reverse_moves()
        self.assertFalse(nota.invoice_line_ids.filtered('dcasa_combo_rol'))
        self.assertEqual(nota._dcasa_ahorro_combos(), 0.0)
        self.assertFalse(any(linea._dcasa_combo_en_papel() for linea in nota.invoice_line_ids))

    def test_los_reportes_por_producto_ven_cada_pieza(self):
        self._combo_confirmado()
        self.env.flush_all()
        filas = self.env['sale.report'].sudo()._read_group(
            [('product_id', 'in', (self.cama_king | self.colchon_king).ids)], ['product_id'], ['price_subtotal:sum'])
        self.assertEqual({producto.id: total for producto, total in filas},
                         {self.cama_king.id: 400.0, self.colchon_king.id: COMBO_KING})

    def test_el_texto_para_el_cliente(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king, self.mesa])
        self.assertEqual(self.linea(orden, self.colchon_king)._dcasa_texto_combo(), 'Combo cama + colchón',
                         'Lo que se descuenta va en su propio renglón')
        self.assertEqual(self.linea(orden, self.cama_king)._dcasa_texto_combo(), 'Combo cama + colchón')
        self.assertEqual(self.linea(orden, self.mesa)._dcasa_texto_combo(), '')


@tagged('post_install', '-at_install')
class TestPreciosAprobados(CombosCommon):
    """Los descuentos de combo que aprobó la dueña (2026-10-23) se cargan una vez (migración 19.0.1.12.0) y solo donde
    todo cuadra: si el precio normal cambió o Gerencia ya puso uno, no se adivina ni se pisa."""

    def test_solo_donde_todo_cuadra_y_una_sola_vez(self):
        Plantilla = self.env['product.template']
        base = {'type': 'consu', 'taxes_id': [Command.set(self.itbms.ids)]}

        def colchon(codigo, precio):
            return Plantilla.create({**base, 'name': f'COLCHON ZZ APROBADO {codigo} FULL', 'default_code': codigo,
                                     'list_price': precio}).product_variant_id

        cuadra, otro_precio, ya_tenia = colchon('ZZ-AP-1', 96.99), colchon('ZZ-AP-2', 85.0), colchon('ZZ-AP-3', 184.99)
        ya_tenia.dcasa_precio_combo = 150.0
        aprobados = {'ZZ-AP-1': (96.99, 87.0), 'ZZ-AP-2': (81.99, 75.0), 'ZZ-AP-3': (184.99, 159.0),
                     'ZZ-AP-NO': (10.0, 5.0)}
        Variante = self.env['product.product']
        with patch.dict(combo_armable.PRECIOS_COMBO_APROBADOS, aprobados, clear=True):
            self.assertEqual(Variante._dcasa_cargar_precios_combo_aprobados(), {
                'ZZ-AP-1': 'cargado', 'ZZ-AP-2': 'otro_precio', 'ZZ-AP-3': 'ya_tenia', 'ZZ-AP-NO': 'no_encontrado'})
            self.assertEqual(Variante._dcasa_cargar_precios_combo_aprobados()['ZZ-AP-1'], 'ya_tenia', 'Una vez')
        self.assertEqual((cuadra.dcasa_precio_combo, cuadra.dcasa_combo_ahorro), (87.0, 9.99))
        self.assertFalse(otro_precio.dcasa_precio_combo)
        self.assertEqual(ya_tenia.dcasa_precio_combo, 150.0, 'Lo que puso Gerencia no se pisa')

    def test_con_el_catalogo_real_quedan_los_cuatro_descuentos(self):
        Variante = self.env['product.product'].with_context(active_test=False)
        codigos = list(combo_armable.PRECIOS_COMBO_APROBADOS)
        if Variante.search_count([('default_code', 'in', codigos)]) != len(codigos):
            self.skipTest('Sin el catálogo del sistema anterior en esta base.')
        resultado = Variante._dcasa_cargar_precios_combo_aprobados()
        self.assertTrue(set(resultado.values()) <= {'cargado', 'ya_tenia'}, resultado)
        ahorros = {codigo: Variante.search([('default_code', '=', codigo)]).dcasa_combo_ahorro for codigo in codigos}
        self.assertEqual(ahorros, {'IM-2002': 9.99, 'IM-2001': 6.99, 'DSRSOQ': 25.99, 'CSOK-10': 33.99})


@tagged('post_install', '-at_install')
class TestCombosDeSiempre(CombosCommon):
    """Los combos tipo «Combo» de Odoo (los que ya existían) siguen igual: sus piezas no se emparejan."""

    def test_un_combo_nativo_conserva_su_precio_repartido(self):
        grupos = self.env['product.combo'].create([
            {'name': 'Cama', 'combo_item_ids': [Command.create({'product_id': self.cama_king.id})]},
            {'name': 'Colchón', 'combo_item_ids': [Command.create({'product_id': self.colchon_king.id})]}])
        combo = self.env['product.template'].create({
            'name': 'COMBO DE PRUEBA KING', 'type': 'combo', 'list_price': 600.0,
            'taxes_id': [Command.set(self.itbms.ids)], 'combo_ids': [Command.set(grupos.ids)]})
        self.assertFalse(combo.dcasa_tipo_combo)
        orden = self.orden(usuario=self.gerencia)
        linea = orden._dcasa_agregar_producto(combo.product_variant_id)
        piezas = orden.order_line - linea
        self.assertAlmostEqual(sum(piezas.mapped('price_subtotal')), 600.0)
        self.assertFalse(piezas.filtered('dcasa_combo_con_precio'))
        orden.action_confirm()
        self.assertEqual(orden.state, 'sale')


@tagged('post_install', '-at_install')
class TestEstilosDelPanel(TransactionCase):

    def test_el_scss_del_panel_compila(self):
        """Un error de SCSS deja TODO el panel de Odoo sin estilos («A css error occured»): se compila aquí."""
        import sass
        ruta = file_path('dcasa_catalogo/static/src/combo/armar_combo.scss')
        self.assertTrue(os.path.exists(ruta))
        css = sass.compile(filename=ruta)
        self.assertIn('.o_dcasa_armar_combo', css)
