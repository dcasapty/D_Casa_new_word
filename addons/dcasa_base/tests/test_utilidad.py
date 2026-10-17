"""La ganancia de cada venta (pedido de la dueña, 2026-10-16): venta sin ITBMS menos costo, solo para Gerencia."""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from .test_roles import crear_usuario


@tagged('post_install', '-at_install')
class TestUtilidad(TransactionCase):
    """El ejemplo del jefe: una cama que cuesta 107.77 y se vende a 189.99 + ITBMS."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = crear_usuario(cls.env, 'utilidad_vendedora', 'dcasa_base.group_vendedora')
        cls.gerencia = crear_usuario(cls.env, 'utilidad_gerencia', 'dcasa_base.group_gerencia')
        cls.itbms = cls.env['account.tax'].create({
            'name': 'ITBMS utilidad 7%', 'amount': 7.0, 'amount_type': 'percent', 'type_tax_use': 'sale',
            'company_id': cls.env.company.id})
        cls.cama = cls.env['product.product'].create({
            'name': 'Cama utilidad', 'list_price': 189.99, 'standard_price': 107.77,
            'taxes_id': [Command.set(cls.itbms.ids)]})
        cls.sin_costo = cls.env['product.product'].create({
            'name': 'Silla sin costo', 'list_price': 50.0, 'standard_price': 0.0,
            'taxes_id': [Command.set(cls.itbms.ids)]})
        cls.flete = cls.env['product.product'].create({
            'name': 'Flete utilidad', 'type': 'service', 'list_price': 20.0, 'standard_price': 0.0,
            'taxes_id': [Command.set(cls.itbms.ids)]})
        # Con celular y correo: sin ellos la vendedora no confirma la venta (dcasa_contactos, 2026-10-16).
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente utilidad', 'phone': '6000-0021',
                                                     'email': 'cliente.utilidad@example.com'})

    def _orden(self, *lineas, usuario=None):
        return self.env['sale.order'].with_user(usuario or self.env.user).create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create(linea) for linea in lineas],
        })

    def test_el_ejemplo_del_jefe_la_cama_deja_82_22_sin_itbms(self):
        orden = self._orden({'product_id': self.cama.id})
        orden.action_confirm()
        self.assertAlmostEqual(orden.dcasa_utilidad, 82.22, places=2)
        self.assertAlmostEqual(orden.dcasa_venta_neta, 189.99, places=2)
        self.assertAlmostEqual(orden.dcasa_utilidad_pct, 43.3, places=1)
        self.assertAlmostEqual(orden.amount_total, 203.29, places=2, msg='el ITBMS no es ganancia ni costo')
        self.assertFalse(orden.dcasa_sin_costo)

    def test_el_costo_queda_el_de_la_confirmacion_y_no_se_mueve_despues(self):
        orden = self._orden({'product_id': self.cama.id})
        self.cama.standard_price = 120.0          # cambió antes de confirmar: manda el de la confirmación
        orden.action_confirm()
        self.assertAlmostEqual(orden.order_line.dcasa_costo_unitario, 120.0, places=2)
        self.cama.standard_price = 150.0          # cambió después de vender: la venta ya hecha no se mueve
        orden.invalidate_recordset()
        self.assertAlmostEqual(orden.order_line.dcasa_costo_unitario, 120.0, places=2)
        self.assertAlmostEqual(orden.dcasa_utilidad, 189.99 - 120.0, places=2)

    def test_el_descuento_por_linea_baja_la_ganancia(self):
        orden = self._orden({'product_id': self.cama.id, 'discount': 10.0})
        orden.action_confirm()
        self.assertAlmostEqual(orden.dcasa_venta_neta, 170.99, places=2)
        self.assertAlmostEqual(orden.dcasa_utilidad, 170.99 - 107.77, places=2)

    def test_el_descuento_global_rebaja_la_ganancia_sin_tener_costo(self):
        producto_descuento = self.env['product.product'].create({
            'name': 'Descuento utilidad', 'type': 'service', 'list_price': 0.0, 'taxes_id': [Command.clear()]})
        self.env.company.sale_discount_product_id = producto_descuento
        orden = self._orden({'product_id': self.cama.id})
        asistente = self.env['sale.order.discount'].with_user(self.gerencia).with_context(
            active_id=orden.id, active_model='sale.order').create({
                'sale_order_id': orden.id, 'discount_type': 'so_discount', 'discount_percentage': 0.10})
        asistente.action_apply_discount()
        orden.action_confirm()
        # 189.99 − 10 % = 170.99 vendido; el costo no cambia: 107.77
        self.assertAlmostEqual(orden.dcasa_venta_neta, 170.99, places=2)
        self.assertAlmostEqual(orden.dcasa_utilidad, 170.99 - 107.77, places=2)

    def test_los_servicios_positivos_no_inflan_la_ganancia(self):
        orden = self._orden({'product_id': self.cama.id}, {'product_id': self.flete.id})
        orden.action_confirm()
        self.assertAlmostEqual(orden.amount_untaxed, 189.99 + 20.0, places=2)
        self.assertAlmostEqual(orden.dcasa_venta_neta, 189.99, places=2, msg='el flete no tiene costo cargado')
        self.assertAlmostEqual(orden.dcasa_utilidad, 82.22, places=2)

    def test_mercancia_sin_costo_no_inventa_ganancia(self):
        orden = self._orden({'product_id': self.cama.id}, {'product_id': self.sin_costo.id})
        orden.action_confirm()
        self.assertTrue(orden.dcasa_sin_costo)
        self.assertEqual(orden.dcasa_utilidad_pct, 0.0, 'sin porcentaje: no hay con qué calcularlo')
        self.assertTrue(orden.order_line.filtered(lambda linea: linea.product_id == self.sin_costo).dcasa_sin_costo)

    def test_el_costo_se_convierte_a_la_unidad_de_la_linea(self):
        docena = self.env.ref('uom.product_uom_dozen')
        orden = self._orden({'product_id': self.cama.id, 'product_uom_id': docena.id})
        self.assertAlmostEqual(orden.order_line.dcasa_costo_unitario, 107.77 * 12, places=2)

    def test_solo_gerencia_y_administradores_ven_costos_y_ganancia(self):
        orden = self._orden({'product_id': self.cama.id})
        orden.action_confirm()
        for campo in ('dcasa_utilidad', 'dcasa_venta_neta', 'dcasa_utilidad_pct', 'dcasa_sin_costo'):
            with self.assertRaises(AccessError, msg=campo):
                orden.with_user(self.vendedora).read([campo])
            self.assertIn(campo, orden.with_user(self.gerencia).fields_get())
            self.assertNotIn(campo, orden.with_user(self.vendedora).fields_get())
        with self.assertRaises(AccessError):
            orden.order_line.with_user(self.vendedora).read(['dcasa_costo_unitario'])
        self.assertEqual(orden.with_user(self.gerencia).dcasa_utilidad, orden.dcasa_utilidad)
        # lo demás del pedido lo sigue viendo
        self.assertAlmostEqual(orden.with_user(self.vendedora).amount_total, 203.29, places=2)

    # --- Revisión adversarial del 2026-10-16 ----------------------------------------------------------------

    def test_una_venta_con_costo_cero_recupera_el_costo_cuando_se_carga(self):
        """El aviso dice «carga el costo»: la venta que quedó fuera de la ganancia tiene que volver a entrar."""
        silla = self.env['product.product'].create({
            'name': 'Silla costo tardío', 'list_price': 50.0, 'standard_price': 0.0,
            'taxes_id': [Command.set(self.itbms.ids)]})
        orden = self._orden({'product_id': silla.id, 'product_uom_qty': 3})
        orden.action_confirm()
        self.assertTrue(orden.dcasa_sin_costo)
        self.assertEqual(orden.dcasa_utilidad, 0.0)
        silla.standard_price = 30.0
        orden.invalidate_recordset()
        self.assertFalse(orden.dcasa_sin_costo, 'ya tiene costo')
        self.assertAlmostEqual(orden.dcasa_utilidad, 3 * (50.0 - 30.0), places=2)

    def test_cargar_el_costo_no_mueve_las_ventas_que_ya_tenian_costo(self):
        orden = self._orden({'product_id': self.cama.id})
        orden.action_confirm()
        self.cama.standard_price = 200.0
        orden.invalidate_recordset()
        self.assertAlmostEqual(orden.order_line.dcasa_costo_unitario, 107.77, places=2)

    def test_la_cotizacion_sin_confirmar_no_se_toca_al_cargar_el_costo(self):
        silla = self.env['product.product'].create({
            'name': 'Silla cotización', 'list_price': 50.0, 'standard_price': 0.0,
            'taxes_id': [Command.set(self.itbms.ids)]})
        cotizacion = self._orden({'product_id': silla.id})
        silla.standard_price = 30.0
        cotizacion.invalidate_recordset()
        self.assertEqual(cotizacion.order_line.dcasa_costo_unitario, 0.0, 'se toma al confirmar')
        cotizacion.action_confirm()
        self.assertAlmostEqual(cotizacion.order_line.dcasa_costo_unitario, 30.0, places=2)

    def test_la_vendedora_crea_y_confirma_un_pedido_aunque_no_vea_la_ganancia(self):
        """Los campos de ganancia son solo de Gerencia, pero se calculan por dentro: quien vende no choca con ellos."""
        orden = self._orden({'product_id': self.cama.id}, {'product_id': self.flete.id}, usuario=self.vendedora)
        orden.action_confirm()
        self.assertEqual(orden.state, 'sale')
        with self.assertRaises(AccessError):
            orden.read(['dcasa_utilidad'])
        self.assertAlmostEqual(orden.sudo().dcasa_utilidad, 82.22, places=2)
        orden.order_line.with_user(self.vendedora).write({'product_uom_qty': 2})
        self.assertAlmostEqual(orden.sudo().dcasa_utilidad, 2 * 82.22, places=2)
