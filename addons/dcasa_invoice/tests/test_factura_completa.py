"""La factura «completa»: cliente con entrega, flete, descuento, abono parcial y textos de la empresa."""
from odoo import fields
from odoo.tests import TransactionCase, tagged

from ..models import lineas


@tagged('post_install', '-at_install')
class TestFacturaCompleta(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.company.write({'dcasa_factura_garantia': False, 'dcasa_factura_cambios': False,
                           'dcasa_factura_terminos': False})
        pa = cls.env.ref('base.pa').id
        cls.cliente = cls.env['res.partner'].create({
            'name': 'KAREN SANJUR', 'vat': '8-797-2148', 'phone': '+507 61234567', 'email': 'karen@example.com',
            'street': 'Calle 5, Barrio Balboa', 'city': 'La Chorrera', 'country_id': pa,
        })
        cls.entrega = cls.env['res.partner'].create({
            'name': 'Casa de Karen', 'type': 'delivery', 'parent_id': cls.cliente.id,
            'street': 'Villa Lucre, casa 12', 'city': 'Arraiján', 'country_id': pa, 'phone': '6999-0000',
        })
        cls.vendedora = cls.env['res.users'].create({'name': 'Ana Vendedora', 'login': 'ana.vendedora'})
        cls.colchon = cls.env['product.product'].create({
            'name': 'COLCHON IMPERIAL TWIN 3/4 BUEN SUEÑO', 'default_code': 'IM-2001', 'type': 'consu',
        })
        cls.cama = cls.env['product.product'].create({
            'name': 'CAMA QUEEN GREY CON ESTANTES', 'default_code': '1062010735N', 'type': 'consu',
        })
        cls.flete = cls.env.ref('dcasa_invoice.product_flete')
        cls.armado = cls.env['product.product'].create({'name': 'Armado en casa', 'type': 'service'})

    def _factura(self, lineas_vals, **valores):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, vals) for vals in lineas_vals], **valores,
        })
        factura.action_post()
        return factura

    def _factura_completa(self):
        return self._factura([
            {'product_id': self.colchon.id, 'quantity': 2, 'price_unit': 81.99},
            {'product_id': self.cama.id, 'quantity': 1, 'price_unit': 158.02, 'discount': 10},
            {'product_id': self.flete.id, 'quantity': 1, 'price_unit': 25.00},
        ], partner_shipping_id=self.entrega.id, invoice_user_id=self.vendedora.id,
            delivery_date=fields.Date.today(), invoice_origin='S01004',
            invoice_payment_term_id=self.env.ref('account.account_payment_term_immediate').id)

    def _abonar(self, factura, monto):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids,
        ).create({'payment_date': factura.invoice_date, 'amount': monto})._create_payments()

    def _render(self, factura):
        return self.env['ir.actions.report']._render_qweb_html('account.report_invoice', factura.ids)[0].decode()

    # --- Líneas ------------------------------------------------------------------------

    def test_codigo_separado_de_la_descripcion(self):
        self.assertEqual(lineas.codigo_y_descripcion('[IM-2001] COLCHON IMPERIAL TWIN / IM-2001', 'IM-2001'),
                         ('IM-2001', 'COLCHON IMPERIAL TWIN'))
        self.assertEqual(lineas.codigo_y_descripcion('[ABC] Mesa\nDe roble'), ('ABC', 'Mesa\nDe roble'))
        self.assertEqual(lineas.codigo_y_descripcion('Flete', None), ('', 'Flete'))
        factura = self._factura_completa()
        html = self._render(factura)
        self.assertIn('>IM-2001<', html)
        self.assertNotIn('[IM-2001]', html)
        self.assertIn('Código', html)

    def test_flete_en_su_bloque(self):
        factura = self._factura_completa()
        linea_flete = factura.invoice_line_ids.filtered(lambda linea: linea.product_id == self.flete)
        self.assertTrue(linea_flete._dcasa_es_flete())
        self.assertTrue(linea_flete._dcasa_es_servicio())
        principales, servicios = factura._dcasa_lineas(factura._get_move_lines_to_report())
        self.assertEqual(servicios, linea_flete)
        self.assertEqual(len(principales), 2)
        self.assertEqual(factura._dcasa_titulo_servicios(servicios), 'Flete y envío')
        html = self._render(factura)
        self.assertIn('o_dcasa_servicios', html)
        self.assertIn('Flete y envío', html)

    def test_titulo_del_bloque_segun_lo_que_lleva(self):
        factura = self._factura([
            {'product_id': self.cama.id, 'quantity': 1, 'price_unit': 158.02},
            {'product_id': self.flete.id, 'quantity': 1, 'price_unit': 25.00},
            {'product_id': self.armado.id, 'quantity': 1, 'price_unit': 15.00},
        ])
        _principales, servicios = factura._dcasa_lineas(factura._get_move_lines_to_report())
        self.assertEqual(len(servicios), 2)
        self.assertEqual(factura._dcasa_titulo_servicios(servicios), 'Flete y servicios')
        solo_armado = servicios.filtered(lambda linea: linea.product_id == self.armado)
        self.assertEqual(factura._dcasa_titulo_servicios(solo_armado), 'Servicios')

    def test_factura_solo_de_flete_no_separa_nada(self):
        factura = self._factura([{'product_id': self.flete.id, 'quantity': 1, 'price_unit': 25.00}])
        principales, servicios = factura._dcasa_lineas(factura._get_move_lines_to_report())
        self.assertEqual(len(principales), 1)
        self.assertFalse(servicios)
        self.assertNotIn('o_dcasa_servicios', self._render(factura))

    def test_columna_itbms_corta(self):
        itbms = self.company.account_sale_tax_id
        self.assertEqual(lineas.etiqueta_impuestos(itbms), '7%')
        self.assertEqual(lineas.etiqueta_impuestos(itbms.browse()), '')
        factura = self._factura_completa()
        linea = factura.invoice_line_ids.filtered(lambda linea: linea.product_id == self.cama)
        self.assertEqual(linea._dcasa_impuestos(), '7%')
        html = self._render(factura)
        self.assertIn('>7%<', html)
        self.assertNotIn('ITBMS 7% Venta', html, 'El nombre interno del impuesto no va en la columna')

    def test_producto_flete_sin_precio_inventado(self):
        self.assertEqual(self.flete.list_price, 0)
        self.assertFalse(self.flete.description_sale, 'Las condiciones de entrega las redacta la dueña')
        self.assertEqual(self.flete.default_code, 'DCASA-FLETE')
        self.assertEqual(self.flete.categ_id, self.env.ref('dcasa_invoice.categ_flete'))

    # --- Cabecera ------------------------------------------------------------------------

    def test_cliente_entrega_y_datos(self):
        factura = self._factura_completa()
        self.assertEqual(factura._dcasa_entrega(), self.entrega)
        html = self._render(factura)
        for texto in ('KAREN SANJUR', 'RUC', '8-797-2148', '6123-4567', 'karen@example.com', 'Calle 5, Barrio Balboa',
                      '>Entrega<', 'Villa Lucre, casa 12', 'Arraiján', '6999-0000',
                      'Fecha de factura', 'Vence', 'Pedido', 'S01004', 'Vendedora', 'Ana Vendedora', 'Condiciones'):
            self.assertIn(texto, html, texto)
        datos = dict(factura._dcasa_datos())
        self.assertEqual(datos['Pedido'], 'S01004')
        self.assertEqual(datos['Vendedora'], 'Ana Vendedora')
        self.assertEqual(datos['Fecha de entrega'], factura._dcasa_fecha(fields.Date.today()))
        # La entrega se imprime con su propio nombre y sin repetir la identificación del cliente.
        self.assertIn('>Casa de Karen<', html)
        self.assertEqual(html.count('8-797-2148'), 1)

    def test_referencia_igual_al_pedido_no_se_repite(self):
        factura = self._factura_completa()
        factura.ref = 'S01004'  # Odoo copia el pedido en la referencia al facturar una venta
        self.assertNotIn('Referencia', dict(factura._dcasa_datos()))
        factura.ref = 'Pago en dos partes'
        self.assertEqual(dict(factura._dcasa_datos())['Referencia'], 'Pago en dos partes')

    def test_sin_entrega_distinta_no_se_imprime(self):
        # Odoo elige sola la dirección de entrega hija del cliente; este cliente no tiene ninguna.
        otro = self.env['res.partner'].create({'name': 'Luis Sin Entrega', 'country_id': self.env.ref('base.pa').id})
        factura = self._factura([{'product_id': self.cama.id, 'quantity': 1, 'price_unit': 158.02}],
                                partner_id=otro.id)
        self.assertFalse(factura._dcasa_entrega())
        html = self._render(factura)
        self.assertNotIn('>Entrega<', html)
        self.assertNotIn('Villa Lucre', html)

    # --- Totales, descuento y abonos ---------------------------------------------------

    def test_descuento_y_abono_parcial(self):
        factura = self._factura_completa()
        self.assertAlmostEqual(factura._dcasa_total_descuento(), 15.80)
        self._abonar(factura, 100.00)
        self.assertEqual(factura.payment_state, 'partial')
        abonos = factura._dcasa_abonos()
        self.assertEqual(len(abonos), 1)
        self.assertAlmostEqual(abonos[0]['monto'], 100.00)
        self.assertTrue(abonos[0]['medio'])
        self.assertNotIn('Manual', abonos[0]['medio'], 'El método genérico de Odoo no le dice nada al cliente')
        self.assertEqual(abonos[0]['fecha'], factura._dcasa_fecha(factura.invoice_date))
        html = self._render(factura)
        # El widget monetario separa el símbolo del número: «$<span …>15.80</span>».
        for texto in ('Descuento', '>15.80<', 'Abono del', '>100.00<', 'Pagado', 'Por pagar', 'Pago parcial',
                      'Saldo pendiente', 'Son:', 'Dólares'):
            self.assertIn(texto, html, texto)
        self.assertIn(f'>{factura.amount_residual:,.2f}<', html)
        self.assertIn('Medio de pago', html, 'Con un abono ya se sabe con qué se pagó')

    def test_sin_pagos_no_hay_filas_de_abono(self):
        factura = self._factura_completa()
        html = self._render(factura)
        self.assertNotIn('Abono del', html)
        self.assertNotIn('Por pagar', html)
        self.assertNotIn('Medio de pago', html, 'Sin pagos ni medio previsto, no se inventa uno')

    def test_pagada_dos_abonos(self):
        factura = self._factura_completa()
        self._abonar(factura, 100.00)
        self._abonar(factura, factura.amount_residual)
        self.assertTrue(factura._dcasa_is_paid())
        self.assertEqual(len(factura._dcasa_abonos()), 2)
        html = self._render(factura)
        self.assertEqual(html.count('Abono del'), 2)
        self.assertIn('Pagada el', html)
        self.assertNotIn('Vence', html)

    # --- Textos de la empresa ----------------------------------------------------------

    def test_sin_textos_de_la_empresa_no_se_imprime_nada(self):
        self.assertEqual(self.company._dcasa_bloques_legales(), [])
        html = self._render(self._factura_completa())
        self.assertNotIn('o_dcasa_legales', html)
        for texto in ('Garantía', 'Cambios y devoluciones', 'Términos'):
            self.assertNotIn(f'<strong>{texto}</strong>', html)

    def test_textos_de_la_empresa_se_imprimen_tal_cual(self):
        self.company.write({'dcasa_factura_garantia': 'Texto de garantía de prueba.',
                            'dcasa_factura_terminos': '  Texto de términos de prueba.  '})
        self.assertEqual(self.company._dcasa_bloques_legales(), [
            ('Garantía', 'Texto de garantía de prueba.'), ('Términos', 'Texto de términos de prueba.')])
        html = self._render(self._factura_completa())
        self.assertIn('Texto de garantía de prueba.', html)
        self.assertIn('Texto de términos de prueba.', html)
        self.assertNotIn('Cambios y devoluciones', html)

    # --- Pie, hoja y cotización ----------------------------------------------------------

    def test_pie_con_whatsapp_correo_ruc_y_direccion(self):
        html = self._render(self._factura_completa())
        self.assertIn('WhatsApp', html)
        self.assertIn(self.company.email, html)
        self.assertIn('155779346-2-2026 DV7', html)
        self.assertIn(self.company.street, html)
        self.assertNotIn('familia panameña', html)

    def test_hoja_carta(self):
        self.assertEqual(self.company.paperformat_id, self.env.ref('dcasa_invoice.paperformat_dcasa_carta'))
        self.assertEqual(self.company.paperformat_id.format, 'Letter')

    def test_cotizacion_comparte_el_formato(self):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'partner_shipping_id': self.entrega.id, 'user_id': self.vendedora.id,
            'order_line': [
                (0, 0, {'product_id': self.colchon.id, 'product_uom_qty': 2, 'price_unit': 81.99, 'discount': 5}),
                (0, 0, {'product_id': self.flete.id, 'product_uom_qty': 1, 'price_unit': 25.00}),
            ],
        })
        self.assertEqual(orden._dcasa_titulo(), 'Cotización')
        self.assertEqual(orden._dcasa_entrega(), self.entrega)
        self.assertAlmostEqual(orden._dcasa_total_descuento(), 8.20)
        html = self.env['ir.actions.report']._render_qweb_html('sale.report_saleorder', orden.ids)[0].decode()
        for texto in ('Cotización', 'Código', '>IM-2001<', 'Flete y envío', '>Entrega<', 'Villa Lucre, casa 12',
                      'Vendedora', 'Ana Vendedora', 'Descuento', 'Descripción', 'Precio unitario', 'Importe'):
            self.assertIn(texto, html, texto)
        self.assertNotIn('[IM-2001]', html)
        self.assertNotIn('Quotation', html)
        orden.action_confirm()
        self.assertEqual(orden._dcasa_titulo(), 'Pedido')
