"""Vender un combo de cama + colchón (tipo «Combo» de Odoo 19) de punta a punta, con productos inventados.

Cómo lo hace Odoo y lo que estas pruebas fijan: la línea del combo va en 0 y sin impuesto; debajo va una línea por cada
pieza con la parte del precio del combo que le toca (y su ITBMS); la entrega descuenta la cama y el colchón; la factura
lleva el combo como título de sección y las piezas debajo; el tope de descuento de la vendedora, los puntos de Socios
y la comisión de vendedores cuentan el neto UNA vez (sobre las piezas, no sobre el título).
"""
import re
from html import unescape

from odoo.addons.dcasa_socios.tests.common import SociosCommon
from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

PRECIO_COMBO = 320.0


@tagged('post_install', '-at_install')
class TestVentaDeCombos(SociosCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ubicacion = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1).lot_stock_id
        cls.ubicacion = ubicacion

        def producto(codigo, nombre, precio):
            variante = cls.env['product.product'].create({
                'name': nombre, 'default_code': codigo, 'type': 'consu', 'is_storable': True, 'list_price': precio,
                'taxes_id': [(6, 0, cls.itbms.ids)], 'invoice_policy': 'order'})
            cls.env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': variante.id, 'location_id': ubicacion.id, 'inventory_quantity': 10})._apply_inventory()
            return variante
        cls.cama = producto('CMB-CAMA', 'CAMA KING DE PRUEBA CMB-CAMA', 150.0)
        cls.colchon = producto('CMB-COL', 'COLCHON KING DE PRUEBA CMB-COL', 200.0)
        cls.extra = producto('CMB-COL2', 'COLCHON KING DE PRUEBA OTRO', 230.0)
        grupos = cls.env['product.combo'].create([
            {'name': 'Cama', 'combo_item_ids': [(0, 0, {'product_id': cls.cama.id})]},
            {'name': 'Colchón', 'combo_item_ids': [(0, 0, {'product_id': cls.colchon.id})]}])
        cls.combo = cls.env['product.template'].create({
            'name': 'COMBO CAMA KING DE PRUEBA', 'type': 'combo', 'list_price': PRECIO_COMBO,
            'taxes_id': [(6, 0, cls.itbms.ids)], 'combo_ids': [(6, 0, grupos.ids)]})
        cls.vendedora = new_test_user(
            cls.env, login='combo_vendedora', groups='sales_team.group_sale_salesman,account.group_account_invoice')
        cls.gerente = new_test_user(
            cls.env, login='combo_gerente', groups='sales_team.group_sale_manager,account.group_account_invoice')

    def orden(self, cantidad=1, usuario=None):
        orden = self.env['sale.order'].with_user(usuario or self.env.user).create({'partner_id': self.cliente.id})
        linea = orden._dcasa_agregar_producto(self.combo.product_variant_id, cantidad)
        return orden, linea, orden.order_line - linea

    def stock(self, variante):
        return variante.with_context(location=self.ubicacion.id).qty_available

    # --- La cotización ---------------------------------------------------------------------

    def test_la_cotizacion_lleva_la_linea_del_combo_en_cero_y_una_linea_por_pieza(self):
        orden, combo, piezas = self.orden()
        self.assertEqual(piezas.product_id, self.cama | self.colchon)
        self.assertEqual((combo.price_unit, combo.price_subtotal, combo.tax_ids.ids), (0.0, 0.0, []))
        self.assertEqual(piezas.linked_line_id, combo)
        self.assertEqual(piezas.mapped('product_uom_qty'), [1.0, 1.0])
        self.assertEqual(piezas.sorted('id').mapped('combo_item_id.combo_id.name'), ['Cama', 'Colchón'])

    def test_el_precio_del_combo_se_reparte_entre_las_piezas_y_suma_exacto(self):
        orden, _combo, piezas = self.orden()
        por_producto = {p.product_id: p.price_unit for p in piezas}
        # Reparto de Odoo: proporcional al precio de lista de cada pieza (150 y 200) y el centavo que sobra a la última.
        self.assertEqual(por_producto, {self.cama: 137.14, self.colchon: 182.86})
        self.assertEqual(sum(piezas.mapped('price_subtotal')), PRECIO_COMBO)
        self.assertEqual((orden.amount_untaxed, orden.amount_tax, orden.amount_total), (320.0, 22.40, 342.40))
        self.assertEqual(piezas.tax_ids, self.itbms, 'Cada pieza lleva el ITBMS que se suma')

    def test_dos_combos_son_dos_de_cada_pieza(self):
        orden, combo, piezas = self.orden(cantidad=2)
        self.assertEqual((combo.product_uom_qty, piezas.mapped('product_uom_qty')), (2.0, [2.0, 2.0]))
        self.assertEqual((orden.amount_untaxed, orden.amount_total), (640.0, 684.80))

    def test_un_grupo_con_opciones_suma_el_recargo_de_la_opcion_que_se_escoge(self):
        grupo = self.combo.combo_ids.filtered(lambda g: g.name == 'Colchón')
        grupo.combo_item_ids = [(0, 0, {'product_id': self.extra.id, 'extra_price': 15.0})]
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id})
        with self.assertRaisesRegex(UserError, 'hay que escoger'):
            orden._dcasa_agregar_producto(self.combo.product_variant_id, 1)
        linea = orden._dcasa_agregar_producto(self.combo.product_variant_id, 1, elecciones={grupo.id: self.extra.id})
        piezas = orden.order_line - linea
        self.assertEqual(piezas.product_id, self.cama | self.extra)
        self.assertEqual(sum(piezas.mapped('price_subtotal')), PRECIO_COMBO + 15.0, 'El recargo se suma al combo')

    def test_el_precio_de_un_combo_no_se_cambia_a_mano(self):
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id})
        with self.assertRaisesRegex(UserError, 'no se cambia a mano'):
            orden._dcasa_agregar_producto(self.combo.product_variant_id, 1, price_unit=100)

    def test_un_producto_normal_es_una_sola_linea(self):
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id})
        linea = orden._dcasa_agregar_producto(self.cama, 3)
        self.assertEqual((orden.order_line, linea.product_uom_qty, linea.price_unit), (linea, 3.0, 150.0))

    # --- Confirmar ---------------------------------------------------------------------------

    def test_un_combo_sin_sus_piezas_no_se_confirma(self):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [(0, 0, {'product_id': self.combo.product_variant_id.id, 'product_uom_qty': 1})]})
        with self.assertRaisesRegex(UserError, 'no tiene todas sus piezas'):
            orden.action_confirm()
        self.assertEqual(orden.state, 'draft')
        orden2, _combo, piezas = self.orden()
        piezas[:1].unlink()
        with self.assertRaisesRegex(UserError, 'no tiene todas sus piezas'):
            orden2.action_confirm()

    def test_la_entrega_descuenta_la_cama_y_el_colchon_nunca_el_combo(self):
        orden, _combo, _piezas = self.orden(cantidad=2)
        orden.action_confirm()
        (entrega,) = orden.picking_ids
        self.assertEqual(sorted(entrega.move_ids.mapped('product_id.default_code')), ['CMB-CAMA', 'CMB-COL'])
        self.assertEqual(entrega.move_ids.mapped('product_uom_qty'), [2.0, 2.0])
        for movimiento in entrega.move_ids:
            movimiento.quantity = movimiento.product_uom_qty
        entrega.with_context(skip_backorder=True).button_validate()
        self.assertEqual((self.stock(self.cama), self.stock(self.colchon)), (8.0, 8.0))
        self.assertEqual(self.combo.product_variant_id.qty_available, 0.0, 'El combo nunca tiene existencias propias')
        self.assertEqual(orden.order_line.filtered(lambda ln: ln.product_id == self.cama).qty_delivered, 2.0)

    # --- La factura ------------------------------------------------------------------------------

    def facturar(self, cantidad=1, vendedor=None, pagar=False):
        orden, _combo, _piezas = self.orden(cantidad)
        orden.action_confirm()
        factura = orden._create_invoices()
        if vendedor:
            factura.dcasa_vendedor_id = vendedor.id
        factura.action_post()
        if pagar:
            self.pagar(factura)
        return orden, factura

    def test_la_factura_lleva_el_combo_como_titulo_y_las_piezas_debajo_con_totales_exactos(self):
        _orden, factura = self.facturar()
        self.assertEqual(factura.invoice_line_ids.mapped('display_type'), ['line_section', 'product', 'product'])
        seccion, *piezas = factura.invoice_line_ids
        self.assertEqual((seccion.name, seccion.price_subtotal), ('COMBO CAMA KING DE PRUEBA x 1', 0.0))
        self.assertEqual(sorted((p.product_id.default_code, p.price_unit, p.price_subtotal) for p in piezas),
                         [('CMB-CAMA', 137.14, 137.14), ('CMB-COL', 182.86, 182.86)])
        self.assertEqual(piezas[0].tax_ids, self.itbms)
        self.assertEqual((factura.amount_untaxed, factura.amount_tax, factura.amount_total), (320.0, 22.40, 342.40))

    def _texto(self, html):
        html = re.sub(r'<style.*?</style>', '', html, flags=re.S)
        html = unescape(re.sub(r'<[^>]+>', '\n', html)).replace('\xa0', ' ')
        lineas = []
        for linea in (x.strip() for x in html.split('\n')):
            if not linea:
                continue
            if lineas and lineas[-1] == '$':   # el signo y la cifra van en etiquetas distintas: se unen
                lineas[-1] = f'$ {linea}'
            else:
                lineas.append(linea)
        return lineas

    def test_el_pdf_de_la_factura_muestra_el_combo_con_sus_piezas_sin_duplicar_importes(self):
        _orden, factura = self.facturar()
        html = self.env['ir.actions.report']._render_qweb_html('account.report_invoice', factura.ids)[0].decode()
        texto = self._texto(html)
        self.assertIn('COMBO CAMA KING DE PRUEBA x 1', texto)
        self.assertEqual([t for t in texto if t in ('CMB-CAMA', 'CMB-COL')], ['CMB-CAMA', 'CMB-COL'],
                         'Cada pieza una vez, con su código en su columna')
        self.assertIn('$ 137.14', texto)
        self.assertIn('$ 182.86', texto)
        # El título muestra lo que suman sus piezas (un subtotal, no un cobro más) y los totales salen una sola vez.
        self.assertEqual(texto.count('$ 320.00'), 2, 'Subtotal del título del combo y subtotal de la factura')
        self.assertEqual(texto.count('$ 342.40'), 1, 'El total, una sola vez')
        self.assertEqual(texto.count('$ 22.40'), 1)
        self.assertEqual(texto.count('7%'), 2, 'El ITBMS de cada pieza')

    def test_el_titulo_del_combo_suma_solo_sus_piezas_aunque_despues_vengan_flete_y_otros_muebles(self):
        """Odoo suma en un título todo lo que sigue hasta el próximo título: con el flete (o una mesa de noche) después
        del combo, el título cobraría de más. En la factura de D'CASA suma solo las piezas del combo."""
        orden, _combo, _piezas = self.orden()
        flete = self.env.ref('dcasa_invoice.product_flete')
        self.env['sale.order.line'].create(
            {'order_id': orden.id, 'product_id': flete.id, 'product_uom_qty': 1, 'price_unit': 25})
        orden._dcasa_agregar_producto(self.extra, 2)      # un mueble suelto después del combo
        orden.action_confirm()
        factura = orden._create_invoices()
        factura.action_post()
        (titulo,) = factura.invoice_line_ids.filtered(lambda ln: ln.display_type == 'line_section')
        self.assertEqual((titulo.get_section_subtotal(), titulo.get_section_total()), (320.0, 342.4))
        self.assertEqual(factura.amount_untaxed, 320.0 + 25.0 + 2 * 230.0)
        principales, servicios = factura._dcasa_lineas(factura._get_move_lines_to_report())
        self.assertEqual(servicios.product_id, flete)
        self.assertEqual(principales[0].product_id, self.extra, 'El mueble suelto va antes del título del combo')
        self.assertEqual(principales[1].display_type, 'line_section')
        html = self.env['ir.actions.report']._render_qweb_html('account.report_invoice', factura.ids)[0].decode()
        texto = self._texto(html)
        self.assertEqual(texto.count('$ 320.00'), 1, 'El título del combo: lo que suman sus piezas, nada más')
        self.assertIn('$ 805.00', texto)
        self.assertLess(texto.index('CMB-COL2'), texto.index('COMBO CAMA KING DE PRUEBA x 1'))

    def test_la_cotizacion_en_pdf_muestra_lo_mismo(self):
        orden, _combo, _piezas = self.orden()
        html = self.env['ir.actions.report']._render_qweb_html('sale.report_saleorder', orden.ids)[0].decode()
        texto = self._texto(html)
        self.assertIn('COMBO CAMA KING DE PRUEBA', texto)
        self.assertIn('$ 137.14', texto)
        self.assertIn('$ 182.86', texto)
        self.assertEqual(texto.count('$ 342.40'), 1)

    # --- Descuento máximo de la vendedora ---------------------------------------------------------

    def test_la_vendedora_vende_un_combo_sin_que_el_tope_estorbe(self):
        orden, combo, piezas = self.orden(usuario=self.vendedora)
        self.assertEqual(sum(piezas.mapped('price_subtotal')), PRECIO_COMBO)
        orden.action_confirm()
        self.assertEqual(orden.state, 'sale')

    def test_el_tope_de_descuento_cuenta_en_las_piezas_del_combo(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa.descuento_max_vendedora', '10')
        _orden, combo, piezas = self.orden(usuario=self.vendedora)
        (combo | piezas).with_user(self.vendedora).write({'discount': 10})      # 10 %: vale
        self.assertEqual(sum(piezas.mapped('price_subtotal')), PRECIO_COMBO * 0.9)
        with self.assertRaisesRegex(ValidationError, 'puedes rebajar hasta 10'):
            piezas.with_user(self.vendedora).write({'discount': 11})
        with self.assertRaisesRegex(ValidationError, 'puedes rebajar hasta 10'):
            piezas[:1].with_user(self.vendedora).write({'discount': 0, 'price_unit': piezas[:1].price_unit * 0.8})

    def test_gerencia_si_puede_dar_mas_descuento_en_un_combo(self):
        _orden, combo, piezas = self.orden(usuario=self.gerente)
        (combo | piezas).with_user(self.gerente).write({'discount': 40})
        self.assertAlmostEqual(sum(piezas.mapped('price_subtotal')), PRECIO_COMBO * 0.6, places=2)

    def test_la_linea_del_combo_en_cero_no_se_mide_contra_el_precio_del_combo(self):
        """Su precio es 0 por diseño: medirla contra el precio de lista haría fallar toda venta de la vendedora."""
        _orden, combo, _piezas = self.orden(usuario=self.vendedora)
        self.assertTrue(combo._dcasa_exenta_tope_descuento())
        self.assertFalse(_piezas[:1]._dcasa_exenta_tope_descuento(), 'Las piezas sí cuentan')

    # --- Puntos de Socios y comisión de vendedores ------------------------------------------------

    def test_los_puntos_de_socios_cuentan_el_total_de_la_factura_una_sola_vez(self):
        _orden, factura = self.facturar(pagar=True)
        compra = factura.dcasa_compra_ids
        self.assertEqual(len(compra), 1)
        self.assertEqual((compra.monto_centavos, compra.puntos), (34240, 342))

    def test_la_comision_de_vendedores_cuenta_el_neto_una_sola_vez(self):
        self.activar_vendedores()
        ana = self.vendedor('Ana Vendedora', '8-111-111', '6100-0001')
        _orden, factura = self.facturar(vendedor=ana, pagar=True)
        comision = factura.dcasa_vend_comision_ids.filtered(lambda c: c.tipo == 'directa')
        self.assertEqual(len(comision), 1)
        self.assertEqual(comision.neto_centavos, 32000, 'Neto de las piezas: $320.00, sin ITBMS y sin contar el título')
        self.assertEqual(comision.puntos, 1280)   # 320.00 × 4 puntos por dólar de las reglas de prueba

    # --- Lo demás del inventario ---------------------------------------------------------------------

    def test_el_stock_del_catalogo_de_un_combo_es_cero_y_no_se_ajusta(self):
        from odoo.addons.dcasa_catalogo.inventario_anterior import _ajustar_stock
        self.assertEqual(self.combo.dcasa_stock, 0.0)
        self.assertFalse(_ajustar_stock(self.env, self.combo.product_variant_id, self.ubicacion, 5.0),
                         'Un combo no tiene existencias propias: no se le hace ajuste de inventario')
        self.assertEqual(self.combo.product_variant_id.qty_available, 0.0)
