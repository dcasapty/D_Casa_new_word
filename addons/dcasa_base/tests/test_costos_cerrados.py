"""Costo cerrado (etapa 1b(a)): el costo, el precio del proveedor y el margen de los reportes de factura solo los
ven Gerencia, administradores, contabilidad, compras e inventario; la Vendedora, Caja y bodega no, ni en pantalla ni
por la conexión de datos. Y aun así siguen vendiendo, facturando, recibiendo y entregando (el sistema sí lee el costo
por dentro para valorar)."""
from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from .test_roles import crear_usuario

CAMPOS_PRODUCTO = ('standard_price', 'avg_cost', 'total_value', 'seller_ids', 'variant_seller_ids')


@tagged('post_install', '-at_install')
class TestCostosCerrados(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.vendedora = crear_usuario(env, 'costo_vendedora', 'dcasa_base.group_vendedora')
        cls.caja = crear_usuario(env, 'costo_caja', 'dcasa_base.group_caja')
        cls.bodega = crear_usuario(env, 'costo_bodega', 'stock.group_stock_user')
        cls.gerencia = crear_usuario(env, 'costo_gerencia', 'dcasa_base.group_gerencia')
        cls.contador = crear_usuario(env, 'costo_contador', 'account.group_account_user')
        cls.lector = crear_usuario(env, 'costo_lector', 'account.group_account_readonly')
        cls.compras = crear_usuario(env, 'costo_compras', 'purchase.group_purchase_user')
        cls.inventario = crear_usuario(env, 'costo_inventario', 'stock.group_stock_manager')
        cls.admin = env.ref('base.user_admin')
        cls.sin_costo = (cls.vendedora, cls.caja, cls.bodega)
        cls.con_costo = (cls.gerencia, cls.contador, cls.lector, cls.compras, cls.inventario, cls.admin)

        cls.cliente = env['res.partner'].create({
            'name': 'CLIENTE DE PRUEBA COSTO', 'phone': '6000-0031', 'email': 'cliente.costo@example.com'})
        cls.proveedor = env['res.partner'].create({'name': 'PROVEEDOR DE PRUEBA COSTO'})
        cls.producto = env['product.product'].create({
            'name': 'Sofá costo cerrado', 'is_storable': True, 'list_price': 500.0, 'standard_price': 210.0,
            'seller_ids': [Command.create({'partner_id': cls.proveedor.id, 'price': 205.0})],
        })
        cls.almacen = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
        env['stock.quant']._update_available_quantity(cls.producto, cls.almacen.lot_stock_id, 10)

    # ------------------------------------------------------------------
    # Lo que se niega
    # ------------------------------------------------------------------

    def test_sin_el_grupo_no_se_lee_el_costo_por_ningun_camino(self):
        for usuario in self.sin_costo:
            with self.subTest(usuario=usuario.login):
                producto = self.producto.with_user(usuario)
                plantilla = producto.product_tmpl_id
                for registro in (producto, plantilla):
                    with self.assertRaises(AccessError):
                        registro.read(['standard_price'])
                    with self.assertRaises(AccessError):
                        registro.web_read({'name': {}, 'standard_price': {}})
                    with self.assertRaises(AccessError):
                        registro.search_read([('id', '=', registro.id)], ['name', 'standard_price'])
                    with self.assertRaises(AccessError):
                        registro.web_search_read([('id', '=', registro.id)], {'standard_price': {}})
                    with self.assertRaises(AccessError):
                        registro.search([('standard_price', '>', 100)])
                    with self.assertRaises(AccessError):
                        registro.search([], order='standard_price desc', limit=1)
                    self.assertNotIn('standard_price', registro.fields_get())
                # Por una relación (la línea de una venta pidiendo el costo de su producto).
                with self.assertRaises(AccessError):
                    self.env['sale.order.line'].with_user(usuario).search(
                        [('product_id.standard_price', '>', 100)])
                # El precio del proveedor.
                precio = self.producto.seller_ids.with_user(usuario)
                with self.assertRaises(AccessError):
                    precio.read(['price'])
                with self.assertRaises(AccessError):
                    precio.search_read([], ['partner_id', 'price'])
                self.assertNotIn('price', precio.fields_get())

    def test_un_pedido_de_otro_modelo_no_trae_el_costo_del_producto(self):
        """El formulario de la venta pide los datos del producto con web_read/onchange: el costo no viaja."""
        orden = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]})
        with self.assertRaises(AccessError):
            orden.order_line.web_read({'product_id': {'fields': {'standard_price': {}}}})
        with self.assertRaises(AccessError):
            self.env['sale.order'].with_user(self.vendedora).onchange(
                {'partner_id': self.cliente.id,
                 'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]}, [],
                {'partner_id': {'fields': {'display_name': {}}},
                 'order_line': {'fields': {'product_id': {'fields': {'standard_price': {}}}}}})

    def test_el_margen_del_analisis_de_facturas_se_niega(self):
        Reporte = self.env['account.invoice.report']
        for usuario in self.sin_costo:
            with self.subTest(usuario=usuario.login):
                reporte = Reporte.with_user(usuario)
                self.assertNotIn('price_margin', reporte.fields_get())
                self.assertNotIn('inventory_value', reporte.fields_get())
                with self.assertRaises(AccessError):
                    reporte.formatted_read_group([], ['product_id'], ['price_margin:sum'])
                with self.assertRaises(AccessError):
                    reporte.search_read([], ['price_margin'], limit=1)
        for usuario in (self.gerencia, self.contador, self.admin):
            with self.subTest(usuario=usuario.login):
                Reporte.with_user(usuario).formatted_read_group([], ['product_id'], ['price_margin:sum'])
                self.assertIn('price_margin', Reporte.with_user(usuario).fields_get())

    # ------------------------------------------------------------------
    # Lo que se ve
    # ------------------------------------------------------------------

    def test_quien_controla_la_tienda_si_ve_el_costo(self):
        for usuario in self.con_costo:
            with self.subTest(usuario=usuario.login):
                producto = self.producto.with_user(usuario)
                self.assertEqual(producto.read(['standard_price'])[0]['standard_price'], 210.0)
                self.assertIn('standard_price', producto.fields_get())
                self.assertIn(self.producto, producto.search([('standard_price', '>', 100)]))
                self.assertEqual(self.producto.seller_ids.with_user(usuario).read(['price'])[0]['price'], 205.0)

    def _campos_de_las_vistas(self, usuario, modelo):
        """Todos los campos que las vistas de ese modelo le muestran (o le piden en secreto) a esa persona."""
        vistas = self.env[modelo].with_user(usuario).get_views(
            [(False, 'form'), (False, 'list'), (False, 'kanban'), (False, 'search')])
        nombres = set()
        for vista in vistas['views'].values():
            arbol = etree.fromstring(vista['arch'])
            nombres |= {nodo.get('name') for nodo in arbol.iter('field')}
            nombres |= {nodo.get('for') for nodo in arbol.iter('label') if nodo.get('for')}
        return nombres, set(vistas['models'].get(modelo, ()))

    def test_las_pantallas_no_muestran_el_costo_a_quien_no_lo_ve(self):
        for modelo in ('product.template', 'product.product'):
            for usuario in self.sin_costo:
                with self.subTest(modelo=modelo, usuario=usuario.login):
                    nombres, campos = self._campos_de_las_vistas(usuario, modelo)
                    self.assertFalse(nombres & set(CAMPOS_PRODUCTO), nombres & set(CAMPOS_PRODUCTO))
                    self.assertNotIn('standard_price', campos)
            nombres, campos = self._campos_de_las_vistas(self.gerencia, modelo)
            self.assertIn('standard_price', nombres, modelo)
        lista = self.env['account.invoice.report'].with_user(self.vendedora).get_views([(False, 'list')])
        arbol = etree.fromstring(lista['views']['list']['arch'])
        self.assertFalse({n.get('name') for n in arbol.iter('field')} & {'price_margin', 'inventory_value'})

    def test_ninguna_vista_de_productos_ni_proveedores_muestra_el_costo(self):
        """Todas las vistas (también las que abre una acción con su propia vista, de cualquier módulo)."""
        cerrados = {
            'product.template': set(CAMPOS_PRODUCTO), 'product.product': set(CAMPOS_PRODUCTO),
            'product.supplierinfo': {'price', 'price_discounted', 'discount'},
            'account.invoice.report': {'price_margin', 'inventory_value'},
        }
        for modelo, campos in cerrados.items():
            vistas = self.env['ir.ui.view'].search([('model', '=', modelo), ('mode', '=', 'primary'),
                                                    ('type', 'in', ('list', 'form', 'kanban', 'search', 'pivot',
                                                                    'graph'))])
            self.assertTrue(vistas, modelo)
            for vista in vistas:
                for usuario in (self.vendedora, self.bodega):
                    if not self.env[modelo].with_user(usuario).has_access('read'):
                        continue   # ni siquiera abre ese modelo
                    with self.subTest(modelo=modelo, vista=vista.xml_id or vista.name, usuario=usuario.login):
                        arbol = etree.fromstring(self.env[modelo].with_user(usuario).get_view(
                            vista.id, vista.type)['arch'])
                        # Los campos del modelo mismo (no los de una lista de otro modelo dentro de un campo).
                        propios = {nodo.get('name') for nodo in arbol.iter('field')
                                   if not any(a.tag == 'field' for a in nodo.iterancestors())}
                        self.assertFalse(propios & campos, propios & campos)

    def test_el_formulario_del_producto_se_abre_para_la_vendedora(self):
        """Lo que pide el formulario (sus campos) se puede leer: abrir la ficha no da error."""
        vistas = self.env['product.template'].with_user(self.vendedora).get_views([(False, 'form')])
        arbol = etree.fromstring(vistas['views']['form']['arch'])
        especificacion = {nodo.get('name'): {} for nodo in arbol.iter('field')
                          if nodo.getparent() is not None and not any(
                              a.tag == 'field' for a in nodo.iterancestors())}
        valores = self.producto.product_tmpl_id.with_user(self.vendedora).web_read(especificacion)
        self.assertEqual(valores[0]['id'], self.producto.product_tmpl_id.id)

    # ------------------------------------------------------------------
    # El trabajo de todos los días sigue igual
    # ------------------------------------------------------------------

    def test_la_vendedora_vende_entrega_y_factura(self):
        orden = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 2})]})
        orden.action_confirm()
        entrega = orden.picking_ids.with_user(self.vendedora)
        entrega.move_ids.quantity = 2
        entrega.move_ids.picked = True
        entrega.button_validate()
        self.assertEqual(entrega.state, 'done')
        factura = orden._create_invoices()
        factura.with_user(self.vendedora).action_post()
        self.assertEqual(factura.state, 'posted')
        self.assertEqual(self.producto.qty_available, 8)

    def test_bodega_recibe_y_entrega(self):
        proveedores = self.env.ref('stock.stock_location_suppliers')
        clientes = self.env.ref('stock.stock_location_customers')
        stock = self.almacen.lot_stock_id
        for tipo, origen, destino in ((self.almacen.in_type_id, proveedores, stock),
                                      (self.almacen.out_type_id, stock, clientes)):
            picking = self.env['stock.picking'].with_user(self.bodega).create({
                'picking_type_id': tipo.id, 'location_id': origen.id, 'location_dest_id': destino.id,
                'move_ids': [Command.create({
                    'product_id': self.producto.id, 'product_uom_qty': 3, 'location_id': origen.id,
                    'location_dest_id': destino.id})],
            })
            picking.action_confirm()
            picking.move_ids.quantity = 3
            picking.move_ids.picked = True
            picking.button_validate()
            self.assertEqual(picking.state, 'done')
        self.assertEqual(self.producto.qty_available, 10)

    def test_bodega_recibe_una_compra(self):
        compra = self.env['purchase.order'].with_user(self.gerencia).create({
            'partner_id': self.proveedor.id, 'date_planned': fields.Datetime.now(),
            'order_line': [Command.create({'product_id': self.producto.id, 'product_qty': 4})]})
        compra.button_confirm()
        recepcion = compra.picking_ids.with_user(self.bodega)
        recepcion.move_ids.quantity = 4
        recepcion.move_ids.picked = True
        recepcion.button_validate()
        self.assertEqual(recepcion.state, 'done')
        self.assertEqual(self.producto.qty_available, 14)
