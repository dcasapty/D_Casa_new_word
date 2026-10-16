"""Revisión adversarial del 2026-10-16: las rutas por las que la vendedora todavía podía saltarse el tope de descuento.

Cada prueba reproduce un hueco que se verificó contra el código anterior (la cama quedaba en $1) y debe fallar si
vuelve. Se prueba como la vendedora, sin sudo, igual que un RPC a mano."""
from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from .test_roles import crear_usuario


@tagged('post_install', '-at_install')
class TestTopeRutas(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('dcasa.descuento_max_vendedora', '10')
        cls.vendedora = crear_usuario(cls.env, 'ruta_vendedora', 'dcasa_base.group_vendedora')
        cls.gerencia = crear_usuario(cls.env, 'ruta_gerencia', 'dcasa_base.group_gerencia')
        cls.cama = cls.env['product.product'].create({'name': 'Cama rutas', 'list_price': 200.0})
        cls.mesa = cls.env['product.product'].create({'name': 'Mesa rutas', 'list_price': 100.0})
        cls.flete = cls.env['product.product'].create({'name': 'Flete rutas', 'type': 'service', 'list_price': 20.0})
        cls.descuento = cls.env['product.product'].create({
            'name': 'Descuento rutas', 'type': 'service', 'list_price': 0.0, 'taxes_id': [Command.clear()]})
        cls.env.company.sale_discount_product_id = cls.descuento
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente rutas'})

    def _orden(self, usuario, productos=None):
        return self.env['sale.order'].with_user(usuario).create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': p.id}) for p in (productos or [self.cama])],
        })

    def _descuento_global(self, usuario, orden, porcentaje):
        asistente = self.env['sale.order.discount'].with_user(usuario).with_context(
            active_id=orden.id, active_model='sale.order').create({
                'sale_order_id': orden.id, 'discount_type': 'so_discount', 'discount_percentage': porcentaje})
        asistente.action_apply_discount()

    # --- El precio que no viaja en los valores ---------------------------------------------------------

    def test_un_precio_por_defecto_en_el_contexto_tambien_se_mide(self):
        """``default_price_unit`` en el contexto del RPC fija el precio sin aparecer en los valores de la línea."""
        orden = self._orden(self.vendedora)
        Linea = self.env['sale.order.line'].with_user(self.vendedora)
        with self.assertRaises(ValidationError):
            Linea.with_context(default_price_unit=1.0).create({'order_id': orden.id, 'product_id': self.cama.id})
        with self.assertRaises(ValidationError):
            Linea.with_context(default_discount=100.0).create({'order_id': orden.id, 'product_id': self.cama.id})

    # --- Las banderas que antes eximían a la línea ------------------------------------------------------

    def test_la_bandera_de_anticipo_no_exime_a_una_linea_con_producto(self):
        orden = self._orden(self.vendedora)
        Linea = self.env['sale.order.line'].with_user(self.vendedora)
        with self.assertRaises(ValidationError):
            Linea.create({'order_id': orden.id, 'product_id': self.cama.id, 'is_downpayment': True,
                          'price_unit': 1.0})
        with self.assertRaises(ValidationError):
            orden.order_line[:1].with_user(self.vendedora).write({'is_downpayment': True, 'price_unit': 1.0})

    def test_quitar_la_bandera_vuelve_a_medir_la_linea(self):
        """Marcar y desmarcar no deja un precio fuera del tope: cualquier cambio de bandera revalida."""
        orden = self._orden(self.vendedora)
        linea = orden.order_line[:1].with_user(self.vendedora)
        with self.assertRaises(ValidationError):
            linea.write({'is_downpayment': True, 'price_unit': 1.0})
        self.assertEqual(orden.order_line.price_unit, 200.0, 'lo rechazado no se queda')

    def test_una_linea_negativa_sin_producto_con_bandera_de_anticipo_cuenta_como_rebaja(self):
        """Un anticipo de Odoo no lleva producto y cuesta cero; si lleva un importe negativo es una rebaja."""
        orden = self._orden(self.vendedora)
        Linea = self.env['sale.order.line'].with_user(self.vendedora)
        with self.assertRaises(ValidationError):
            Linea.create({'order_id': orden.id, 'is_downpayment': True, 'product_uom_qty': -1,
                          'price_unit': 150.0, 'name': 'Anticipo falso'})

    def test_un_anticipo_de_verdad_no_se_bloquea(self):
        """Lo que crea el asistente de anticipos de Odoo: sin producto, cantidad cero, importe positivo."""
        orden = self._orden(self.vendedora)
        linea = self.env['sale.order.line'].with_user(self.vendedora).create({
            'order_id': orden.id, 'is_downpayment': True, 'product_uom_qty': 0.0, 'price_unit': 100.0,
            'name': 'Anticipo'})
        self.assertTrue(linea.exists())

    # --- Cambiar de producto o de unidad con el precio ya escrito ----------------------------------------

    def test_cambiar_de_producto_con_un_precio_pegado_se_mide(self):
        orden = self._orden(self.vendedora, [self.mesa])
        linea = orden.order_line[:1].with_user(self.vendedora)
        linea.write({'price_unit': 90.0})  # la mesa a 90: dentro del tope
        with self.assertRaises(ValidationError):
            linea.write({'product_id': self.cama.id})  # la cama a 90 sería un 55 % de rebaja

    def test_cambiar_de_unidad_de_medida_con_un_precio_pegado_se_mide(self):
        orden = self._orden(self.vendedora)
        linea = orden.order_line[:1].with_user(self.vendedora)
        linea.write({'price_unit': 190.0})  # dentro del tope
        docena = self.env.ref('uom.product_uom_dozen')
        with self.assertRaises(ValidationError):
            linea.write({'product_uom_id': docena.id})  # 190 por docena en vez de 2.400

    # --- Lo que Gerencia ya autorizó no se le cobra a la vendedora --------------------------------------

    def test_en_un_pedido_con_descuento_autorizado_la_vendedora_puede_agregar_notas_y_flete(self):
        orden = self._orden(self.gerencia)
        self._descuento_global(self.gerencia, orden, 0.50)  # Gerencia autoriza el 50 %
        como_vendedora = orden.with_user(self.vendedora)
        como_vendedora.write({'order_line': [
            Command.create({'display_type': 'line_note', 'name': 'Entregar en la tarde'})]})
        como_vendedora.write({'order_line': [Command.create({'product_id': self.flete.id})]})
        nota = como_vendedora.order_line.filtered('display_type')
        nota.unlink()  # y quitar lo que agregó
        self.assertEqual(len(orden.order_line.filtered(lambda linea: linea.product_id == self.flete)), 1)

    def test_en_un_pedido_con_descuento_autorizado_la_vendedora_no_puede_empeorarlo(self):
        orden = self._orden(self.gerencia)
        self._descuento_global(self.gerencia, orden, 0.50)
        cama = orden.order_line.filtered(lambda linea: linea.product_id == self.cama).with_user(self.vendedora)
        with self.assertRaises(ValidationError):
            cama.write({'price_unit': 180.0})  # dentro del tope por línea, pero suma al descuento del pedido
        Linea = self.env['sale.order.line'].with_user(self.vendedora)
        with self.assertRaises(ValidationError):
            Linea.create({'order_id': orden.id, 'product_id': self.cama.id, 'price_unit': 150.0})  # pasa del tope
        # Otra cama con el 10 % que sí le toca no empeora el pedido (el descuento sube con lo que se vende): pasa.
        nueva = Linea.create({'order_id': orden.id, 'product_id': self.cama.id, 'price_unit': 180.0})
        self.assertTrue(nueva.exists())

    def test_en_un_pedido_con_descuento_autorizado_la_vendedora_si_puede_mejorarlo(self):
        orden = self._orden(self.gerencia)
        self._descuento_global(self.gerencia, orden, 0.50)
        orden.with_user(self.vendedora).order_line.filtered(
            lambda linea: linea.product_id == self.descuento).unlink()  # quitar el descuento mejora el pedido
        self.assertFalse(orden.order_line.filtered(lambda linea: linea.product_id == self.descuento))

    # --- Quién no tiene tope --------------------------------------------------------------------------------

    def test_un_administrador_tecnico_sin_gerencia_no_tiene_tope(self):
        admin = crear_usuario(self.env, 'ruta_admin', 'base.group_system', 'dcasa_base.group_vendedora')
        orden = self._orden(admin)
        orden.order_line.with_user(admin).write({'price_unit': 1.0})
        self.assertEqual(orden.order_line.price_unit, 1.0)
