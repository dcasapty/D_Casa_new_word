"""«Stock y precios»: la lista de solo lectura para elegir qué empujar en una campaña (models/producto_stock.py)."""
import json
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

MODELO = 'dcasa.producto.stock'


@tagged('post_install', '-at_install')
class TestProductoStock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Plantilla = cls.env['product.template']
        cls.categoria = cls.env['product.category'].create({'name': 'Zzcamas de prueba'})
        cls.otra_categoria = cls.env['product.category'].create({'name': 'Zzsofas de prueba'})
        cls.hija = cls.env['product.category'].create({'name': 'Zzcamas king', 'parent_id': cls.categoria.id})
        cls.tienda = cls.env['product.public.category'].create({'name': 'Zzdormitorio'})
        base = {'type': 'consu', 'is_storable': True, 'sale_ok': True, 'categ_id': cls.categoria.id,
                'public_categ_ids': [Command.set(cls.tienda.ids)]}
        cls.mucho = Plantilla.create({**base, 'name': 'Zzcama barata mucho stock', 'default_code': 'ZZ-A',
                                      'list_price': 100.0, 'is_published': True})
        cls.poco = Plantilla.create({**base, 'name': 'Zzcama cara poco stock', 'default_code': 'ZZ-B',
                                     'list_price': 900.0, 'is_published': False, 'dcasa_black_weekend': True})
        cls.agotada = Plantilla.create({**base, 'name': 'Zzcama agotada', 'default_code': 'ZZ-C',
                                        'list_price': 500.0, 'categ_id': cls.otra_categoria.id})
        cls.sin_control = Plantilla.create({**base, 'name': 'Zzcama sin control', 'default_code': 'ZZ-D',
                                            'list_price': 300.0, 'is_storable': False})
        cls.umbral_alto = Plantilla.create({**base, 'name': 'Zzcama umbral alto', 'default_code': 'ZZ-E',
                                            'list_price': 200.0, 'available_threshold': 10.0,
                                            'categ_id': cls.hija.id})
        tamano = cls.env['product.attribute'].create({'name': 'Zztamaño', 'create_variant': 'always', 'value_ids': [
            Command.create({'name': 'Zzqueen'}), Command.create({'name': 'Zzking'})]})
        cls.con_variantes = Plantilla.create({
            **base, 'name': 'Zzcolchón con tamaños', 'default_code': 'ZZ-F', 'list_price': 400.0,
            'attribute_line_ids': [Command.create({'attribute_id': tamano.id,
                                                   'value_ids': [Command.set(tamano.value_ids.ids)]})]})
        king = cls.con_variantes.attribute_line_ids.product_template_value_ids.filtered(
            lambda v: v.name == 'Zzking')
        king.price_extra = 150.0
        cls.v_queen = cls.con_variantes.product_variant_ids.filtered(lambda v: 'Zzqueen' in v.display_name)
        cls.v_king = cls.con_variantes.product_variant_ids.filtered(lambda v: 'Zzking' in v.display_name)
        # No deben salir: archivado, servicio y no vendible.
        cls.archivado = Plantilla.create({**base, 'name': 'Zzcama archivada', 'active': False})
        cls.servicio = Plantilla.create({'name': 'Zzservicio', 'type': 'service', 'categ_id': cls.categoria.id})
        cls.no_vendible = Plantilla.create({**base, 'name': 'Zzcama no vendible', 'sale_ok': False})

        cls.ubicacion = cls.env['stock.warehouse'].search([], limit=1).lot_stock_id
        quant = cls.env['stock.quant']
        for plantilla, cantidad in ((cls.mucho, 40), (cls.poco, 3), (cls.umbral_alto, 8)):
            quant._update_available_quantity(plantilla.product_variant_id, cls.ubicacion, cantidad)
        quant._update_available_quantity(cls.v_queen, cls.ubicacion, 20)
        quant._update_available_quantity(cls.v_king, cls.ubicacion, 2)
        # De «mucho» hay 12 reservadas: libres 28.
        cls.env['stock.quant'].search([('product_id', '=', cls.mucho.product_variant_id.id)]).reserved_quantity = 12
        cls.plantillas = [cls.mucho, cls.poco, cls.agotada, cls.sin_control, cls.umbral_alto, cls.con_variantes]

    # ------------------------------------------------------------------

    def _actualizar(self):
        """La lista se calcula en la base de datos: se escribe lo pendiente y se olvida lo ya leído de ella."""
        self.env.flush_all()
        self.env.invalidate_all()

    def filas(self, dominio=None, orden=None, usuario=None):
        self._actualizar()
        modelo = self.env[MODELO].with_user(usuario) if usuario else self.env[MODELO]
        propios = [('product_tmpl_id', 'in', [p.id for p in self.plantillas])]
        return modelo.search((dominio or []) + propios, order=orden)

    def fila(self, plantilla, variante=None):
        self._actualizar()
        variante = variante or plantilla.product_variant_id
        (fila,) = self.env[MODELO].search([('product_id', '=', variante.id)])
        return fila

    # ------------------------------------------------------------------ qué sale y con qué cifras

    def test_solo_productos_vendibles_activos_y_de_bienes(self):
        nombres = set(self.filas().mapped('product_id.name'))
        self.assertIn('Zzcama barata mucho stock', nombres)
        self.assertEqual(self.env[MODELO].search_count([('product_tmpl_id', 'in', [
            self.archivado.id, self.servicio.id, self.no_vendible.id])]), 0,
            'ni archivados, ni servicios, ni lo que no se vende')

    def test_existencia_reservado_y_libre(self):
        fila = self.fila(self.mucho)
        self.assertEqual((fila.stock, fila.reservado, fila.disponible), (40, 12, 28))
        self.assertEqual(fila.estado_stock, 'disponible')
        self.assertEqual(fila.default_code, 'ZZ-A')
        self.assertEqual(fila.categ_id, self.categoria)
        self.assertEqual(fila.categoria_web_id, self.tienda)
        self.assertEqual(fila.product_tmpl_id, self.mucho)
        self.assertTrue(fila.controla_stock)

    def test_estado_del_stock_con_la_misma_regla_que_juan_y_la_tienda(self):
        self.assertEqual(self.fila(self.poco).estado_stock, 'pocas', '3 libres, umbral 5 por defecto')
        self.assertEqual(self.fila(self.agotada).estado_stock, 'agotado', 'sin existencias')
        self.assertEqual(self.fila(self.umbral_alto).estado_stock, 'pocas', '8 libres, umbral 10 de su ficha')
        self.assertEqual(self.fila(self.mucho).estado_stock, 'disponible')
        # Lo reservado no se puede ofrecer: 3 existentes y 3 reservadas = agotado.
        self.env['stock.quant'].search([('product_id', '=', self.poco.product_variant_id.id)]).reserved_quantity = 3
        self.assertEqual(self.fila(self.poco).estado_stock, 'agotado')

    def test_un_producto_sin_control_de_inventario_no_inventa_cifra(self):
        fila = self.fila(self.sin_control)
        self.assertEqual(fila.estado_stock, 'sin_control')
        self.assertFalse(fila.controla_stock)
        self.assertEqual((fila.stock, fila.reservado, fila.disponible, fila.valor_a_precio), (0, 0, 0, 0))

    def test_el_precio_suma_el_extra_de_la_variante(self):
        self.assertEqual(self.fila(self.con_variantes, self.v_queen).precio, 400.0)
        self.assertEqual(self.fila(self.con_variantes, self.v_king).precio, 550.0)
        self.assertEqual(self.fila(self.con_variantes, self.v_king).stock, 2)
        self.assertEqual(len(self.filas(dominio=[('product_tmpl_id', '=', self.con_variantes.id)])), 2,
                         'una fila por variante')

    def test_valor_a_precio_de_venta_sin_costos(self):
        self.assertEqual(self.fila(self.mucho).valor_a_precio, 40 * 100.0)
        self.assertEqual(self.fila(self.con_variantes, self.v_king).valor_a_precio, 2 * 550.0)
        self.assertEqual(self.fila(self.agotada).valor_a_precio, 0.0)
        # Un stock negativo no resta valor.
        self.env['stock.quant']._update_available_quantity(self.agotada.product_variant_id, self.ubicacion, -4)
        self.assertEqual(self.fila(self.agotada).valor_a_precio, 0.0)
        campos = set(self.env[MODELO]._fields)
        self.assertFalse(campos & {'standard_price', 'costo', 'margen', 'cost'}, 'esta lista no enseña costos')

    def test_publicado_black_weekend_y_ventas_de_30_dias(self):
        self.assertTrue(self.fila(self.mucho).publicado)
        self.assertFalse(self.fila(self.poco).publicado)
        self.assertTrue(self.fila(self.poco).en_black_weekend)
        self.assertFalse(self.fila(self.mucho).en_black_weekend)
        cliente = self.env['res.partner'].create({'name': 'Cliente de la prueba de stock'})
        ahora = fields.Datetime.now()

        def vender(plantilla, unidades, estado, fecha):
            orden = self.env['sale.order'].create({
                'partner_id': cliente.id, 'date_order': fecha,
                'order_line': [Command.create({'product_id': plantilla.product_variant_id.id,
                                               'product_uom_qty': unidades})]})
            orden.state = estado     # se fuerza el estado: la prueba no necesita mover inventario
            return orden
        vender(self.mucho, 6, 'sale', ahora - timedelta(days=5))
        vender(self.mucho, 2, 'sale', ahora - timedelta(days=29))
        vender(self.mucho, 50, 'sale', ahora - timedelta(days=45))      # fuera de la ventana
        vender(self.mucho, 40, 'draft', ahora - timedelta(days=1))      # una cotización no es una venta
        self.assertEqual(self.fila(self.mucho).vendidas_30d, 8)
        self.assertEqual(self.fila(self.poco).vendidas_30d, 0)
        dormidos = self.filas(dominio=[('disponible', '>', 0), ('vendidas_30d', '=', 0)])
        self.assertIn(self.poco.product_variant_id, dormidos.product_id)
        self.assertNotIn(self.mucho.product_variant_id, dormidos.product_id)

    # ------------------------------------------------------------------ ordenar, filtrar y agrupar

    def test_los_cuatro_favoritos_de_orden_existen_y_ordenan(self):
        favoritos = {
            'filtro_stock_mayor': ['stock desc'], 'filtro_stock_menor': ['stock asc'],
            'filtro_precio_mayor': ['precio desc'], 'filtro_precio_menor': ['precio asc']}
        for xmlid, orden in favoritos.items():
            filtro = self.env.ref(f'dcasa_catalogo.{xmlid}')
            self.assertEqual(json.loads(filtro.sort), orden, xmlid)
            self.assertEqual(filtro.model_id, MODELO)
            self.assertFalse(filtro.user_ids, 'compartido con todos')
            self.assertEqual(filtro.action_id.id, self.env.ref('dcasa_catalogo.action_dcasa_producto_stock').id)

    def test_menor_stock_primero_deja_fuera_lo_agotado(self):
        filtro = self.env.ref('dcasa_catalogo.filtro_stock_menor')
        con_favorito = self.filas(dominio=safe_eval(filtro.domain), orden='stock asc')
        self.assertNotIn('agotado', con_favorito.mapped('estado_stock'))
        self.assertNotIn('sin_control', con_favorito.mapped('estado_stock'))
        self.assertEqual(con_favorito[:1].stock, 2, 'el king del colchón: el que menos tiene sin estar agotado')

    def test_mayor_y_menor_stock_primero(self):
        con_control = [('controla_stock', '=', True), ('product_tmpl_id', '!=', self.agotada.id)]
        mayor = self.filas(dominio=con_control, orden='stock desc').mapped('stock')
        self.assertEqual(mayor, sorted(mayor, reverse=True))
        self.assertEqual(mayor[0], 40)
        menor = self.filas(dominio=con_control, orden='stock asc').mapped('stock')
        self.assertEqual(menor, sorted(menor))
        self.assertEqual(menor[0], 2)
        # Lo que no controla inventario (sin cifra, queda en 0) no encabeza «mayor stock primero»: va con los ceros.
        con_todo = self.filas(orden='stock desc')
        self.assertEqual(con_todo[:1].stock, 40)
        self.assertEqual(con_todo.mapped('stock'), sorted(con_todo.mapped('stock'), reverse=True))
        self.assertEqual(con_todo[-2:].mapped('stock'), [0, 0])

    def test_mayor_y_menor_precio_primero(self):
        mayor = self.filas(orden='precio desc').mapped('precio')
        self.assertEqual(mayor, sorted(mayor, reverse=True))
        self.assertEqual(mayor[0], 900.0)
        menor = self.filas(orden='precio asc').mapped('precio')
        self.assertEqual(menor[0], 100.0)

    def test_filtros_por_estado_precio_y_categoria(self):
        self.assertEqual(self.filas([('estado_stock', '=', 'agotado')]).mapped('default_code'), ['ZZ-C'])
        pocas = self.filas([('estado_stock', '=', 'pocas')])
        self.assertEqual(set(pocas.product_tmpl_id), {self.poco, self.umbral_alto, self.con_variantes},
                         'el tamaño king del colchón (2 unidades) también es «pocas»')
        self.assertEqual(pocas.filtered(lambda f: f.product_tmpl_id == self.con_variantes).product_id, self.v_king)
        caros = self.filas([('precio', '>', 600)])
        self.assertEqual(caros.mapped('default_code'), ['ZZ-B'])
        camas = self.filas([('categ_id', 'child_of', self.categoria.id)])
        self.assertEqual(set(camas.product_tmpl_id), {self.mucho, self.poco, self.sin_control, self.umbral_alto,
                                                      self.con_variantes},
                         'la categoría trae a sus hijas; la agotada es de otra categoría')
        en_tienda = self.filas([('public_categ_ids', 'in', self.tienda.ids)])
        self.assertEqual(len(en_tienda), len(self.filas()))

    def test_buscar_por_nombre_o_codigo(self):
        self.assertEqual(self.filas([('product_id', 'ilike', 'cara poco')]).mapped('default_code'), ['ZZ-B'])
        self.assertEqual(self.filas([('default_code', 'ilike', 'ZZ-A')]).mapped('default_code'), ['ZZ-A'])

    def test_agrupar_por_categoria_suma_el_stock(self):
        grupos = self.env[MODELO]._read_group(
            [('product_tmpl_id', 'in', [p.id for p in self.plantillas])], ['categ_id'], ['stock:sum', '__count'])
        por_categoria = {categoria.id: (stock, n) for categoria, stock, n in grupos}
        # Camas: «mucho» 40 + «poco» 3 + colchón (20 + 2) + sin control (sin cifra) = 65 en 5 variantes.
        self.assertEqual(por_categoria[self.categoria.id], (65, 5))
        self.assertEqual(por_categoria[self.otra_categoria.id], (0, 1))
        self.assertEqual(por_categoria[self.hija.id], (8, 1))

    # ------------------------------------------------------------------ pantallas y permisos

    def test_las_vistas_y_el_panel_de_categorias_cargan(self):
        modelo = self.env[MODELO]
        vistas = modelo.get_views([(False, 'list'), (False, 'kanban'), (False, 'pivot'), (False, 'graph'),
                                   (False, 'search')])
        self.assertEqual(set(vistas['views']), {'list', 'kanban', 'pivot', 'graph', 'search'})
        # Lo que pide la lista en pantalla (con la foto, el cliente web agrega «write_date» para no ver una foto vieja).
        resultado = modelo.web_search_read(
            [('product_tmpl_id', 'in', [p.id for p in self.plantillas])],
            {'image_128': {}, 'product_id': {'fields': {'display_name': {}}}, 'precio': {}, 'stock': {},
             'estado_stock': {}, 'write_date': {}, 'currency_id': {'fields': {'display_name': {}}}},
            limit=80)
        self.assertEqual(resultado['length'], 7)
        self.assertTrue(all(fila['write_date'] for fila in resultado['records']))
        raiz = modelo.search_panel_select_range('categ_id', enable_counters=True)
        self.assertTrue(any(v['display_name'] == 'Zzcamas de prueba' for v in raiz['values']))
        accion = self.env.ref('dcasa_catalogo.action_dcasa_producto_stock')
        self.assertEqual(accion.view_mode, 'list,kanban,pivot,graph')
        self.assertEqual(accion.path, 'stock-y-precios')

    def test_la_vendedora_y_bodega_leen_y_nadie_escribe(self):
        vendedora = new_test_user(self.env, login='zz_stock_vendedora',
                                  groups='base.group_user,sales_team.group_sale_salesman')
        bodega = new_test_user(self.env, login='zz_stock_bodega', groups='base.group_user,stock.group_stock_user')
        for usuario in (vendedora, bodega):
            self.assertTrue(self.filas(usuario=usuario), usuario.login)
        fila = self.fila(self.mucho)
        with self.assertRaises(AccessError):
            fila.with_user(vendedora).write({'stock': 1})
        with self.assertRaises(AccessError):
            self.env[MODELO].with_user(vendedora).create({'precio': 1})
        with self.assertRaises(AccessError):
            fila.with_user(vendedora).unlink()

    def test_quien_no_es_del_equipo_no_la_ve(self):
        portal = new_test_user(self.env, login='zz_stock_portal', groups='base.group_portal')
        interno = new_test_user(self.env, login='zz_stock_interno', groups='base.group_user')
        for usuario in (portal, interno):
            with self.assertRaises(AccessError, msg=usuario.login):
                self.env[MODELO].with_user(usuario).search_count([])

    def test_los_menus_son_de_ventas_y_de_inventario(self):
        ventas = self.env.ref('dcasa_catalogo.menu_dcasa_stock_y_precios')
        inventario = self.env.ref('dcasa_catalogo.menu_dcasa_stock_y_precios_inventario')
        self.assertEqual(ventas.parent_id, self.env.ref('sale.sale_menu_root'))
        self.assertEqual(inventario.parent_id, self.env.ref('stock.menu_warehouse_report'))
        self.assertEqual(ventas.action.id, inventario.action.id)
