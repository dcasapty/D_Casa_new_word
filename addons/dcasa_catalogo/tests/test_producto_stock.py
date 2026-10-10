"""Stock ordenable en Productos (``dcasa_stock``, models/product.py).

Pedido de la dueña: marketing arma las campañas a partir del inventario y necesita ver, en la misma lista de
Productos, qué categoría tiene más o menos stock y, dentro de ella, ordenar por precio. El «A la mano» de Odoo se
calcula al vuelo y no se puede ordenar; ``dcasa_stock`` es ese mismo número guardado en el producto.
"""
import json

from lxml import etree

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval


@tagged('post_install', '-at_install')
class TestStockEnProductos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Plantilla = cls.env['product.template']
        cls.camas = cls.env['product.category'].create({'name': 'Zzcamas de prueba'})
        cls.sofas = cls.env['product.category'].create({'name': 'Zzsofas de prueba'})
        base = {'type': 'consu', 'is_storable': True, 'sale_ok': True, 'categ_id': cls.camas.id}
        cls.mucho = Plantilla.create({**base, 'name': 'Zzcama barata mucho stock', 'list_price': 100.0})
        cls.medio = Plantilla.create({**base, 'name': 'Zzcama media', 'list_price': 500.0})
        cls.poco = Plantilla.create({**base, 'name': 'Zzcama cara poco stock', 'list_price': 900.0})
        cls.agotada = Plantilla.create({**base, 'name': 'Zzcama agotada', 'list_price': 300.0})
        cls.sin_control = Plantilla.create({**base, 'name': 'Zzcama sin control', 'list_price': 250.0,
                                            'is_storable': False})
        cls.sofa = Plantilla.create({**base, 'name': 'Zzsofá', 'list_price': 700.0, 'categ_id': cls.sofas.id})
        tamano = cls.env['product.attribute'].create({'name': 'Zztamaño', 'create_variant': 'always', 'value_ids': [
            Command.create({'name': 'Zzqueen'}), Command.create({'name': 'Zzking'})]})
        cls.con_variantes = Plantilla.create({
            **base, 'name': 'Zzcolchón con tamaños', 'list_price': 400.0,
            'attribute_line_ids': [Command.create({'attribute_id': tamano.id,
                                                   'value_ids': [Command.set(tamano.value_ids.ids)]})]})
        cls.v_queen = cls.con_variantes.product_variant_ids.filtered(lambda v: 'Zzqueen' in v.display_name)
        cls.v_king = cls.con_variantes.product_variant_ids.filtered(lambda v: 'Zzking' in v.display_name)

        cls.ubicacion = cls.env['stock.warehouse'].search([], limit=1).lot_stock_id
        cls.Quant = cls.env['stock.quant']
        for plantilla, cantidad in ((cls.mucho, 40), (cls.medio, 12), (cls.poco, 3), (cls.sofa, 9)):
            cls.Quant._update_available_quantity(plantilla.product_variant_id, cls.ubicacion, cantidad)
        cls.Quant._update_available_quantity(cls.v_queen, cls.ubicacion, 20)
        cls.Quant._update_available_quantity(cls.v_king, cls.ubicacion, 2)
        cls.camas_de_prueba = cls.mucho | cls.medio | cls.poco | cls.agotada | cls.sin_control | cls.con_variantes
        cls.todas = cls.camas_de_prueba | cls.sofa

    def propias(self, dominio=None, orden=None, usuario=None):
        """Solo las de esta prueba (la base real trae el catálogo completo)."""
        modelo = self.env['product.template'].with_user(usuario) if usuario else self.env['product.template']
        return modelo.search([('id', 'in', self.todas.ids)] + (dominio or []), order=orden)

    # ------------------------------------------------------------------ la cifra

    def test_suma_todas_las_medidas_y_colores(self):
        self.assertEqual(self.mucho.dcasa_stock, 40)
        self.assertEqual(self.con_variantes.dcasa_stock, 22, 'queen 20 + king 2')
        self.assertEqual(self.agotada.dcasa_stock, 0)

    def test_un_producto_sin_control_de_inventario_vale_cero(self):
        """Odoo no deja crear existencias de lo que no controla inventario: su stock es 0 y no se inventa otra cifra."""
        self.assertEqual(self.sin_control.dcasa_stock, 0)
        with self.assertRaises(ValidationError):
            self.Quant._update_available_quantity(self.sin_control.product_variant_id, self.ubicacion, 5)

    def test_solo_cuenta_lo_que_hay_en_la_bodega_y_la_tienda(self):
        clientes = self.env.ref('stock.stock_location_customers')
        self.Quant._update_available_quantity(self.mucho.product_variant_id, clientes, 7)
        self.assertEqual(self.mucho.dcasa_stock, 40, 'lo que ya está en manos del cliente no es stock')

    def test_se_recalcula_solo_con_cada_movimiento(self):
        variante = self.poco.product_variant_id
        self.Quant._update_available_quantity(variante, self.ubicacion, 10)      # entra mercancía
        self.assertEqual(self.poco.dcasa_stock, 13)
        self.Quant._update_available_quantity(variante, self.ubicacion, -13)     # se vende todo
        self.assertEqual(self.poco.dcasa_stock, 0)
        self.Quant._update_available_quantity(variante, self.ubicacion, -2)      # se vende de más: negativo, real
        self.assertEqual(self.poco.dcasa_stock, -2)

    def test_un_ajuste_de_inventario_lo_actualiza(self):
        variante = self.medio.product_variant_id
        quant = self.Quant.with_context(inventory_mode=True).create({
            'product_id': variante.id, 'location_id': self.ubicacion.id, 'inventory_quantity': 30})
        quant.action_apply_inventory()
        self.assertEqual(self.medio.dcasa_stock, 30, 'el conteo físico reemplaza lo que había (12)')

    def test_borrar_la_existencia_lo_baja_a_cero(self):
        self.Quant.search([('product_id', '=', self.sofa.product_variant_id.id)]).sudo().unlink()
        self.assertEqual(self.sofa.dcasa_stock, 0)

    def test_activar_o_quitar_el_control_de_inventario_lo_recalcula(self):
        self.mucho.is_storable = False
        self.assertEqual(self.mucho.dcasa_stock, 0)
        self.mucho.is_storable = True
        self.assertEqual(self.mucho.dcasa_stock, 40, 'las existencias seguían ahí')

    def test_una_medida_archivada_ya_no_cuenta(self):
        self.v_king.active = False
        self.assertEqual(self.con_variantes.dcasa_stock, 20)
        self.assertEqual(self.con_variantes.dcasa_stock, self.con_variantes.qty_available,
                         'igual que el «A la mano» de Odoo')

    def test_es_el_mismo_numero_que_el_a_la_mano_de_odoo(self):
        for plantilla in self.todas:
            esperado = plantilla.qty_available if plantilla.is_storable else 0
            self.assertEqual(plantilla.dcasa_stock, esperado, plantilla.name)

    def test_lo_guardado_es_el_total_aunque_el_movimiento_venga_de_una_pantalla_filtrada(self):
        """El contexto de una pantalla (``location``, ``warehouse_id``) cambia el «A la mano» que ella muestra, pero
        no puede cambiar lo que se guarda en el producto."""
        almacen = self.ubicacion.warehouse_id
        otra = self.env['stock.location'].create({'name': 'Zzotra bodega', 'usage': 'internal',
                                                  'location_id': almacen.view_location_id.id})
        self.Quant.with_context(location=otra.id, warehouse_id=almacen.id)._update_available_quantity(
            self.poco.product_variant_id, otra, 4)
        self.assertEqual(self.poco.dcasa_stock, 7, '3 en la tienda + 4 en la otra bodega')

    # ------------------------------------------------------------------ ordenar, filtrar y agrupar

    def test_ordenar_camas_por_mayor_y_menor_stock(self):
        camas = [('categ_id', '=', self.camas.id), ('is_storable', '=', True)]
        mayor = self.propias(camas, 'dcasa_stock desc, id')
        self.assertEqual(mayor.mapped('dcasa_stock'), [40, 22, 12, 3, 0])
        self.assertEqual(mayor[0], self.mucho)
        menor = self.propias(camas + [('dcasa_stock', '>', 0)], 'dcasa_stock asc, id')
        self.assertEqual(menor.mapped('dcasa_stock'), [3, 12, 22, 40])
        self.assertEqual(menor[0], self.poco)

    def test_dentro_de_la_categoria_se_ordena_por_precio_en_los_dos_sentidos(self):
        camas = [('categ_id', '=', self.camas.id)]
        self.assertEqual(self.propias(camas, 'list_price asc, id')[0], self.mucho)
        self.assertEqual(self.propias(camas, 'list_price desc, id')[0], self.poco)
        # Y el stock sigue visible al lado: lo más caro es lo que menos hay.
        mas_caro = self.propias(camas, 'list_price desc, id')[0]
        self.assertEqual((mas_caro.list_price, mas_caro.dcasa_stock), (900.0, 3))

    def test_los_filtros_disponibles_pocas_y_agotados(self):
        arch = self.env['product.template'].get_view(
            self.env.ref('product.product_template_search_view').id, 'search')['arch']
        raiz = etree.fromstring(arch)
        dominios = {}
        for nombre in ('dcasa_disponibles', 'dcasa_pocas', 'dcasa_agotados'):
            (filtro,) = raiz.xpath(f'//filter[@name="{nombre}"]')
            dominios[nombre] = safe_eval(filtro.get('domain'))
        camas = [('categ_id', '=', self.camas.id)]
        self.assertEqual(self.propias(camas + dominios['dcasa_disponibles']),
                         self.mucho | self.medio | self.poco | self.con_variantes)
        self.assertEqual(self.propias(camas + dominios['dcasa_pocas']), self.poco, '1 a 5 unidades')
        self.assertEqual(self.propias(camas + dominios['dcasa_agotados']), self.agotada,
                         'lo que no controla inventario no está agotado')

    def test_agrupar_por_categoria_suma_el_stock(self):
        grupos = self.env['product.template']._read_group(
            [('id', 'in', self.todas.ids)], ['categ_id'], ['dcasa_stock:sum'])
        por_categoria = {categoria.id: total for categoria, total in grupos}
        self.assertEqual(por_categoria[self.camas.id], 40 + 12 + 3 + 22)
        self.assertEqual(por_categoria[self.sofas.id], 9)

    # ------------------------------------------------------------------ la pantalla

    def test_quien_vende_lee_y_ordena_por_stock(self):
        vendedora = new_test_user(self.env, login='vende_stock',
                                  groups='base.group_user,sales_team.group_sale_salesman')
        lectura = self.env['product.template'].with_user(vendedora).search_read(
            [('id', 'in', self.todas.ids), ('is_storable', '=', True)], ['name', 'dcasa_stock'],
            order='dcasa_stock desc')
        self.assertEqual(lectura[0]['dcasa_stock'], 40)
        self.assertEqual(lectura[0]['name'], 'Zzcama barata mucho stock')

    def test_la_lista_de_productos_trae_la_columna_stock_y_esconde_la_de_odoo(self):
        accion = self.env.ref('sale.product_template_action')
        vista = accion.view_ids.filtered(lambda v: v.view_mode == 'list').view_id
        arch = self.env['product.template'].get_view(vista.id, 'list')['arch']
        self.assertRegex(arch, r'name="dcasa_stock"[^>]*optional="show"')
        # El «A la mano» de Odoo era el mismo número pero no se ordenaba: sigue en las columnas opcionales.
        self.assertNotRegex(arch, r'name="qty_available"[^>]*optional="show"')
        self.assertNotRegex(arch, r'name="virtual_available"[^>]*optional="show"')

    def test_productos_abre_en_lista(self):
        self.assertEqual(self.env.ref('sale.product_template_action').view_mode.split(',')[0], 'list')
        self.assertEqual(self.env.ref('stock.product_template_action_product').view_mode.split(',')[0], 'list')

    def test_los_favoritos_de_orden_son_para_todo_el_equipo(self):
        esperado = {
            'dcasa_catalogo.filtro_productos_stock_mayor': ['dcasa_stock desc'],
            'dcasa_catalogo.filtro_productos_stock_menor': ['dcasa_stock asc'],
            'dcasa_catalogo.filtro_productos_precio_mayor': ['list_price desc'],
            'dcasa_catalogo.filtro_productos_precio_menor': ['list_price asc'],
        }
        Plantilla = self.env['product.template']
        for xmlid, orden in esperado.items():
            favorito = self.env.ref(xmlid)
            self.assertEqual(favorito.model_id, 'product.template', xmlid)
            self.assertFalse(favorito.user_ids, f'{xmlid}: compartido, no personal')
            self.assertEqual(json.loads(favorito.sort), orden, xmlid)
            Plantilla.search(safe_eval(favorito.domain), order=favorito.sort and ', '.join(json.loads(favorito.sort)),
                             limit=1)   # el dominio y el orden son válidos
        self.assertIn('dcasa_stock', self.env.ref('dcasa_catalogo.filtro_productos_stock_menor').domain)

    def test_la_pantalla_aparte_ya_no_existe(self):
        """Pedido de la dueña: una sola página de Productos. Nada quedó de «Stock y precios»."""
        self.assertNotIn('dcasa.producto.stock', self.env.registry)
        self.assertFalse(self.env['ir.model'].search([('model', '=', 'dcasa.producto.stock')]))
        self.assertFalse(self.env['ir.ui.menu'].search([('name', 'ilike', 'Stock y precios')]))
        self.assertFalse(self.env['ir.actions.act_window'].search([('res_model', '=', 'dcasa.producto.stock')]))
        self.assertFalse(self.env['ir.filters'].search([('model_id', '=', 'dcasa.producto.stock')]))
