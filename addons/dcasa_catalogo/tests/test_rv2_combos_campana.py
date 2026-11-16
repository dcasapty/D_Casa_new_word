"""Segunda revisión adversarial de «los combos son inamovibles» (2026-11-16). Datos inventados.

Cada prueba vigila un hallazgo ya arreglado: partir camas no hace fallar la venta, el precio a mano no se pisa y las
guardas de Gerencia no se saltan con los ``default_`` del contexto.
"""
from datetime import timedelta

from odoo import Command, fields
from odoo.addons.website_dcasa.models.campana import con_defaults
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .test_combos_armables import COMBO_KING, NORMAL_KING, CombosCommon


@tagged('post_install', '-at_install', 'rv_combos')
class TestRv2CombosCampana(CombosCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('base.group_user').write({
            'implied_ids': [Command.link(cls.env.ref('product.group_product_pricelist').id)]})
        Campana = cls.env['dcasa.campana']
        Campana._dcasa_tarifa_del_sitio()
        sitio = cls.env.ref('website.default_website')
        cls.tarifa = cls.env['product.template']._dcasa_campana_tarifas(sitio)[:1]
        cls.cliente.property_product_pricelist = cls.tarifa
        cls.campana = Campana.search([('website_id', '=', sitio.id)]) or Campana.create({'website_id': sitio.id})
        hoy = fields.Date.context_today(cls.campana)
        cls.campana.write({'fecha_inicio': hoy - timedelta(days=1), 'fecha_fin': hoy + timedelta(days=1),
                           'dcasa_rebaja_combos': False})
        # Cama king 400 → 385 en campaña (pierde 15 al entrar al combo) y colchón king 300 solo, 260 en combo (gana
        # 40). Gana más de lo que pierde, así que el combo se queda: es el escenario en que todavía hay que partir
        # líneas de camas. El caso al revés tiene su propia prueba más abajo.
        cls.cama_king.product_tmpl_id.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 385.0})
        # Un producto para la línea de descuento de importe fijo (negativa).
        cls.descuento = cls.env['product.template'].create({
            'name': 'DESCUENTO DE PRUEBA', 'type': 'service', 'list_price': 0.0}).product_variant_id

    # --- 1. Partir la línea de camas nunca hace fallar la venta ----------------------

    def test_partir_camas_con_un_descuento_de_importe_fijo_no_revienta_la_venta(self):
        """3 camas king a 400 y un descuento de −100 (dentro del tope del 10 %). Al agregar el colchón del combo, la
        línea de camas se parte en 1 (en combo, 400) + 2 (con campaña, 350). Entre las dos escrituras el pedido queda
        a medias: el tope NO se puede medir ahí.
        """
        orden = self.orden(productos=[self.cama_king])
        camas = self.linea(orden, self.cama_king)
        camas.with_user(self.vendedora).product_uom_qty = 3
        self.env['sale.order.line'].with_user(self.gerencia).create({
            'order_id': orden.id, 'product_id': self.descuento.id, 'price_unit': -100.0, 'name': 'Descuento'})
        # Lo que fallaba: esta línea reventaba con «El descuento total de la cotización pasa del tope».
        self.env['sale.order.line'].with_user(self.vendedora).create(
            {'order_id': orden.id, 'product_id': self.colchon_king.id, 'product_uom_qty': 1})
        colchon = self.linea(orden, self.colchon_king)
        self.assertEqual(colchon.price_unit, COMBO_KING, 'el colchón entró en combo')
        camas = self.linea(orden, self.cama_king)
        self.assertEqual(sum(camas.mapped('product_uom_qty')), 3, 'no se perdió ni se duplicó ninguna cama')
        self.assertEqual(sorted(camas.mapped('price_unit')), [385.0, 400.0],
                         'la del combo a 400 (sin campaña) y las dos de sobra a 385 (con campaña)')

    def test_el_tope_de_descuento_se_mide_con_el_pedido_ya_partido(self):
        """El sudo con que se parte NO apaga el tope: se mide después, con las dos líneas de camas ya hechas. Con el
        pedido partido (cama del combo 400 + dos camas 350 + colchón 260 = 1360 autorizado, piso 1224), un descuento
        de importe fijo de −200 deja 1160 y la vendedora no lo puede poner."""
        orden = self.orden(productos=[self.cama_king])
        self.linea(orden, self.cama_king).with_user(self.vendedora).product_uom_qty = 3
        self.env['sale.order.line'].with_user(self.vendedora).create(
            {'order_id': orden.id, 'product_id': self.colchon_king.id, 'product_uom_qty': 1})
        camas = self.linea(orden, self.cama_king)
        self.assertEqual(sorted(camas.mapped('price_unit')), [385.0, 400.0], 'el pedido quedó partido')
        autorizado = 400.0 + 2 * 385.0 + COMBO_KING
        self.assertAlmostEqual(sum(orden.order_line.mapped(lambda ln: ln.price_unit * ln.product_uom_qty)),
                               autorizado, places=2)
        with self.assertRaisesRegex(ValidationError, 'tope'):
            self.env['sale.order.line'].with_user(self.vendedora).create({
                'order_id': orden.id, 'product_id': self.descuento.id, 'price_unit': -200.0, 'name': 'Descuento'})

    def test_partir_camas_sin_descuento_sigue_partiendo_igual(self):
        """Sin líneas negativas no hay nada que medir: el reparto es el de siempre."""
        orden = self.orden(productos=[self.cama_king])
        self.linea(orden, self.cama_king).with_user(self.vendedora).product_uom_qty = 2
        self.env['sale.order.line'].with_user(self.vendedora).create(
            {'order_id': orden.id, 'product_id': self.colchon_king.id, 'product_uom_qty': 1})
        camas = self.linea(orden, self.cama_king)
        self.assertEqual(sorted(camas.mapped('price_unit')), [385.0, 400.0])
        self.assertEqual(sum(camas.mapped('product_uom_qty')), 2)

    # --- 2. El precio negociado a mano no se pisa ------------------------------------

    def test_el_precio_a_mano_de_la_cama_no_se_pisa_al_entrar_al_combo(self):
        """La vendedora deja la cama en 380 (su tope se lo permite). Agregar el colchón del combo la sacaba de la
        campaña y la devolvía a 400: el cliente ya tenía la cotización en 380."""
        orden = self.orden(productos=[self.cama_king])
        cama = self.linea(orden, self.cama_king)
        self.assertEqual(cama.price_unit, 385.0, 'sola, la cama toma la campaña')
        cama.with_user(self.vendedora).price_unit = 380.0
        self.env['sale.order.line'].with_user(self.vendedora).create(
            {'order_id': orden.id, 'product_id': self.colchon_king.id, 'product_uom_qty': 1})
        cama = self.linea(orden, self.cama_king)
        self.assertEqual(cama.price_unit, 380.0, 'el precio que puso la vendedora se respeta')
        self.assertTrue(cama.dcasa_combo_sin_campana, 'y la cama sigue marcada como pieza del combo')

    def test_el_precio_a_mano_de_la_cama_no_se_pisa_al_salir_del_combo(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        cama = self.linea(orden, self.cama_king)
        self.assertEqual(cama.price_unit, 400.0, 'en combo, sin campaña')
        cama.with_user(self.vendedora).price_unit = 390.0
        self.linea(orden, self.colchon_king).with_user(self.vendedora).unlink()
        self.assertEqual(self.linea(orden, self.cama_king).price_unit, 390.0)

    def test_sin_precio_a_mano_la_cama_sigue_recalculandose_sola(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        self.assertEqual(self.linea(orden, self.cama_king).price_unit, 400.0)
        self.linea(orden, self.colchon_king).with_user(self.vendedora).unlink()
        self.assertEqual(self.linea(orden, self.cama_king).price_unit, 385.0,
                         'fuera del combo vuelve sola al precio de campaña')

    # --- 3. Comprar junto nunca sale más caro que comprar por separado ---------------

    def test_si_la_campana_deja_el_colchon_mas_barato_suelto_no_hay_combo(self):
        """El ejemplo de la dueña (2026-11-16): colchón de $300 normal, $260 en combo, y en Black Friday a $150.
        Suelto se paga $150, así que en combo NO se puede cobrar $260. Ese colchón deja de contar como combo: va a
        $150 y la cama que iba con él también toma su precio de campaña ($350)."""
        # El precio de campaña se pone en la plantilla y cada medida baja lo mismo: 100 en la queen deja la king
        # en 150 (300 − 150), justo el ejemplo de la dueña.
        self.colchon_king.product_tmpl_id.with_user(self.gerencia).write(
            {'dcasa_black_weekend': True, 'dcasa_campana_precio': 100.0})
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        colchon, cama = self.linea(orden, self.colchon_king), self.linea(orden, self.cama_king)
        self.assertEqual(colchon.price_unit, 150.0, 'el colchón se cobra al precio de Black Friday, no a 260')
        self.assertEqual(cama.price_unit, 385.0, 'y la cama también toma su precio de Black Friday')
        self.assertFalse(colchon.dcasa_combo_con_precio, 'no cuenta como combo')
        self.assertFalse(cama.dcasa_combo_sin_campana, 'y la cama no queda marcada como pieza de combo')
        self.assertFalse(colchon.dcasa_combo_ahorro_unitario, 'no se anuncia ningún ahorro que no existe')
        juntos = cama.price_unit + colchon.price_unit
        sueltos = 385.0 + 150.0
        self.assertEqual(juntos, sueltos, 'comprar junto nunca sale más caro que comprar por separado')

    def test_la_cama_en_oferta_y_el_colchon_no_el_combo_no_puede_salir_mas_caro(self):
        """El segundo ejemplo de la dueña (2026-11-16): cama de $400 que en Black Friday va a $350, y colchón de $300
        que en combo vale $260 (el colchón NO está en oferta).

        Sueltos: 350 + 300 = $650. En combo saldría 400 + 260 = $660: diez dólares MÁS por comprar junto. Como el
        combo encarece, se deshace: cada pieza va a su precio de campaña (la cama) o al normal (el colchón)."""
        self.cama_king.product_tmpl_id.with_user(self.gerencia).write({'dcasa_campana_precio': 350.0})
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        cama, colchon = self.linea(orden, self.cama_king), self.linea(orden, self.colchon_king)
        self.assertEqual((cama.price_unit, colchon.price_unit), (350.0, NORMAL_KING))
        self.assertEqual(cama.price_unit + colchon.price_unit, 650.0, 'lo mismo que comprarlas por separado')
        self.assertFalse(colchon.dcasa_combo_con_precio, 'el combo se deshizo')
        self.assertFalse(cama.dcasa_combo_sin_campana, 'la cama conserva su precio de Black Friday')
        self.assertFalse(colchon.dcasa_combo_ahorro_unitario, 'y en el papel no sale «descuento combo»')

    def test_si_el_combo_sigue_siendo_el_mas_barato_se_queda_tal_cual(self):
        """Sin nada en campaña, la cama no pierde nada y el combo gana: se queda como siempre."""
        self.cama_king.product_tmpl_id.with_user(self.gerencia).write(
            {'dcasa_black_weekend': False, 'dcasa_campana_precio': False})
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        cama, colchon = self.linea(orden, self.cama_king), self.linea(orden, self.colchon_king)
        self.assertEqual((cama.price_unit, colchon.price_unit), (400.0, COMBO_KING))
        self.assertTrue(colchon.dcasa_combo_con_precio)
        self.assertEqual(colchon.dcasa_combo_ahorro_unitario, 40.0)

    def test_si_la_campana_no_le_gana_al_combo_el_combo_sigue_igual(self):
        """Con el colchón en campaña a $280 (más que los $260 del combo), el combo sigue mandando: $260, y la cama
        vuelve a su precio sin campaña ($400), que es la regla «los combos son inamovibles»."""
        # 230 en la queen deja la king en 280: más que los 260 del combo.
        self.colchon_king.product_tmpl_id.with_user(self.gerencia).write(
            {'dcasa_black_weekend': True, 'dcasa_campana_precio': 230.0})
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        colchon, cama = self.linea(orden, self.colchon_king), self.linea(orden, self.cama_king)
        self.assertEqual(colchon.price_unit, COMBO_KING)
        self.assertEqual(cama.price_unit, 400.0)
        self.assertTrue(colchon.dcasa_combo_con_precio)

    def test_el_colchon_que_pierde_el_combo_no_le_roba_la_cama_a_otro(self):
        """Una cama king y dos colchones king: uno con campaña a $150 (ya no es combo) y el otro con su precio en
        combo. La cama le toca al que sí es combo."""
        self.colchon_king.product_tmpl_id.with_user(self.gerencia).write(
            {'dcasa_black_weekend': True, 'dcasa_campana_precio': 100.0})
        otro = self.env['product.template'].with_user(self.gerencia).create({
            'name': 'COLCHON DE PRUEBA KING DOS', 'type': 'consu', 'is_storable': True,
            'list_price': 300.0}).product_variant_id
        otro.with_user(self.gerencia).write({'dcasa_medida': 'King', 'dcasa_precio_combo': 255.0})
        orden = self.orden(productos=[self.cama_king, self.colchon_king, otro])
        self.assertEqual(self.linea(orden, self.colchon_king).price_unit, 150.0)
        self.assertEqual(self.linea(orden, otro).price_unit, 255.0, 'el que sí es combo se queda con la cama')
        self.assertEqual(self.linea(orden, self.cama_king).price_unit, 400.0, 'esa cama sí va sin campaña')

    # --- 4. Las guardas de Gerencia no se saltan con el contexto ---------------------

    def test_los_colchones_por_cama_no_se_ponen_con_un_default_del_contexto(self):
        Plantilla = self.env['product.template'].with_user(self.vendedora)
        with self.assertRaises(AccessError):
            Plantilla.with_context(default_dcasa_colchones_por_cama=6).create(
                {'name': 'CAMAROTE DE PRUEBA POR CONTEXTO', 'list_price': 500.0})

    def test_el_precio_en_combo_no_se_pone_con_un_default_del_contexto(self):
        Variante = self.env['product.product'].with_user(self.vendedora)
        with self.assertRaises(AccessError):
            Variante.with_context(default_dcasa_precio_combo=5.0).create(
                {'name': 'COLCHON DE PRUEBA POR CONTEXTO', 'list_price': 300.0})

    def test_el_precio_de_campana_no_se_pone_con_un_default_del_contexto(self):
        Plantilla = self.env['product.template'].with_user(self.vendedora)
        with self.assertRaises(AccessError):
            Plantilla.with_context(default_dcasa_campana_precio=1.0).create(
                {'name': 'PRODUCTO DE PRUEBA POR CONTEXTO', 'list_price': 300.0})
        with self.assertRaises(AccessError):
            Plantilla.with_context(default_dcasa_black_weekend=True).create(
                {'name': 'PRODUCTO DE PRUEBA POR CONTEXTO 2', 'list_price': 300.0})

    def test_el_interruptor_de_los_combos_lee_el_default_del_contexto(self):
        """La guarda MIRA el contexto (no lo prohíbe): Gerencia sí puede crear la campaña así."""
        sitio = self.env.ref('website.default_website')
        self.campana.unlink()   # una campaña por sitio
        campana = self.env['dcasa.campana'].with_user(self.gerencia).with_context(
            default_dcasa_rebaja_combos=True).create({'website_id': sitio.id})
        self.assertTrue(campana.dcasa_rebaja_combos)

    def test_con_defaults_junta_lo_que_de_verdad_se_va_a_guardar(self):
        """El ayudante que cierra el hueco: Odoo aplica los ``default_`` del contexto DENTRO de create, después de
        nuestros overrides, así que una guarda que solo mira ``vals`` se salta con el contexto."""
        entorno = self.env(context=dict(self.env.context, default_dcasa_rebaja_combos=True))
        self.assertEqual(con_defaults(entorno, {}, ('dcasa_rebaja_combos',)), {'dcasa_rebaja_combos': True})
        self.assertEqual(con_defaults(entorno, {'dcasa_rebaja_combos': False}, ('dcasa_rebaja_combos',)),
                         {'dcasa_rebaja_combos': False}, 'lo que viene en vals manda')
        self.assertEqual(con_defaults(entorno, {}, ('otro_campo',)), {}, 'solo los campos que se piden')
