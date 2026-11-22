"""«Rotación» (pedido de Gerencia, 2026-11-22): qué se mueve, qué no y cuánto capital hay parado.

Cada prueba dice lo que cuenta y cómo: los grupos por días sin vender (exactos), lo nuevo y lo de pedido abierto que no
se ofrece como parado, el ancla (80 % de las unidades de 90 días), la cobertura, el capital al costo (el mismo de
«Valor del inventario»), la simulación de rebaja, el filtro por categoría y texto, los permisos (el rol Marketing ve
unidades y días, pero no dinero) y el Excel.
"""
import io
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .comun import MarketingCommon, crear_usuario


class RotacionDatos(MarketingCommon):
    """Los usuarios y los seis productos de la prueba (uno por grupo de días sin vender), con costo y precio."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # El «hoy» de la pantalla es el de quien la mira (Panamá): las fechas de la prueba salen del mismo.
        cls.hoy = fields.Date.context_today(cls.env['dcasa.rotacion'].with_user(cls.gerencia))
        cls.marketing_rol = crear_usuario(cls.env, 'zzmk_rol_marketing', ['dcasa_marketing.group_marketing'])
        cls.admin = crear_usuario(cls.env, 'zzmk_admin_rotacion', ['base.group_system'])
        # Un producto por grupo, todos con costo 60 y precio 100 (sin ITBMS), 2 en existencia.
        cls.fresco = cls.con_costo('ZZRO FRESCO', 2)           # vendido hace 5 días
        cls.treinta = cls.con_costo('ZZRO TREINTA', 2)         # 30 días
        cls.sesenta = cls.con_costo('ZZRO SESENTA', 2)         # 60 días
        cls.noventa = cls.con_costo('ZZRO NOVENTA', 2)         # 90 días
        cls.siglo = cls.con_costo('ZZRO CIENTO OCHENTA', 2)    # 200 días
        cls.nunca = cls.con_costo('ZZRO NUNCA', 2)             # nunca se vendió
        for plantilla, dias in ((cls.fresco, 5), (cls.treinta, 30), (cls.sesenta, 60), (cls.noventa, 90),
                                (cls.siglo, 200)):
            cls.facturar(plantilla, 1, dias_atras=dias)

    # --- Ayudas -----------------------------------------------------------------------------------------------

    @classmethod
    def con_costo(cls, nombre, stock, costo=60.0, precio=100.0, categoria=None):
        """Un producto con su costo puesto ANTES de entrar la mercancía (así la valuación es costo × unidades)."""
        plantilla = cls.producto(nombre, stock=0, precio=precio, categoria=categoria)
        plantilla.standard_price = costo
        if stock:
            cls.env['stock.quant']._update_available_quantity(
                plantilla.product_variant_id, cls.bodega_principal.lot_stock_id, stock)
        return plantilla

    @classmethod
    def facturar(cls, plantilla, cantidad, dias_atras=0, nota=False):
        return MarketingCommon.facturar(cls, plantilla, cantidad, dias_atras, nota)


@tagged('post_install', '-at_install')
class TestRotacion(RotacionDatos):

    def datos(self, usuario=None, **kw):
        return self.env['dcasa.rotacion'].with_user(usuario or self.gerencia).datos(**kw)

    def fila(self, datos, plantilla):
        return next((f for f in datos['productos'] if f['id'] == plantilla.id), None)

    def tarjeta(self, datos, clave):
        return next(t for t in datos['tarjetas'] if t['clave'] == clave)

    def ver(self, vista, usuario=None, **kw):
        """Los productos de la prueba (nombre ZZRO…) en esa vista, por nombre."""
        datos = self.datos(usuario, vista=vista, texto='ZZRO', **kw)
        return {f['nombre']: f for f in datos['productos']}

    # --- Los grupos por días sin vender --------------------------------------------------------------------------

    def test_cada_producto_cae_en_su_grupo_exacto(self):
        """Cinco días → menos de 30; 30 días → «30 a 59» (el límite de abajo cuenta en el grupo de arriba); 60 → «60 a
        89»; 90 → «90 a 179»; 200 → «180 o más»; sin facturas → «nunca vendido»."""
        todos = self.ver('todos')
        esperado = {'ZZRO FRESCO': 'v30', 'ZZRO TREINTA': 'v60', 'ZZRO SESENTA': 'v90', 'ZZRO NOVENTA': 'v180',
                    'ZZRO CIENTO OCHENTA': 'mas180', 'ZZRO NUNCA': 'nunca'}
        self.assertEqual({nombre: fila['grupo'] for nombre, fila in todos.items()}, esperado)
        self.assertEqual(todos['ZZRO NOVENTA']['dias_sin_vender'], 90)
        self.assertIsNone(todos['ZZRO NUNCA']['dias_sin_vender'])
        self.assertIsNone(todos['ZZRO NUNCA']['ultima_venta'])

    def test_una_venta_justo_antes_del_corte_sigue_en_el_grupo_de_abajo(self):
        """29 días sin vender es «menos de 30»: el corte es exacto."""
        justo = self.con_costo('ZZRO JUSTO 29', 1)
        self.facturar(justo, 1, dias_atras=29)
        self.assertEqual(self.ver('todos')['ZZRO JUSTO 29']['grupo'], 'v30')

    def test_30_60_90_y_180_o_mas_suman_lo_que_lleva_ese_tiempo_sin_venderse(self):
        mas_de_30 = set(self.ver('mas_de_30'))
        self.assertEqual(mas_de_30, {'ZZRO TREINTA', 'ZZRO SESENTA', 'ZZRO NOVENTA', 'ZZRO CIENTO OCHENTA',
                                     'ZZRO NUNCA'})
        self.assertEqual(set(self.ver('mas_de_60')), {'ZZRO SESENTA', 'ZZRO NOVENTA', 'ZZRO CIENTO OCHENTA',
                                                      'ZZRO NUNCA'})
        self.assertEqual(set(self.ver('mas_de_90')), {'ZZRO NOVENTA', 'ZZRO CIENTO OCHENTA', 'ZZRO NUNCA'})
        self.assertEqual(set(self.ver('mas_de_180')), {'ZZRO CIENTO OCHENTA', 'ZZRO NUNCA'})

    def test_la_nota_de_credito_resta_pero_no_cambia_la_ultima_venta(self):
        """Una nota de crédito resta unidades de la ventana, pero la última venta sigue siendo la última factura."""
        producto = self.con_costo('ZZRO NOTA', 5)
        self.facturar(producto, 3, dias_atras=40)
        self.facturar(producto, 1, dias_atras=2, nota=True)
        fila = self.ver('todos')['ZZRO NOTA']
        self.assertEqual((fila['vendidas_90'], fila['vendidas_30']), (2.0, -1.0))
        self.assertEqual(fila['dias_sin_vender'], 40)
        self.assertEqual(fila['grupo'], 'v60')

    def test_un_agotado_ya_no_tiene_capital_parado(self):
        agotado = self.con_costo('ZZRO AGOTADO', 0)
        self.facturar(agotado, 1, dias_atras=100)
        self.assertNotIn('ZZRO AGOTADO', self.ver('todos'))
        self.assertNotIn('ZZRO AGOTADO', self.ver('mas_de_90'))

    # --- Nuevo y pedido abierto: no se ofrecen como parados -----------------------------------------------------------

    def recibir(self, plantilla, cantidad, dias_atras):
        """Una recepción de un proveedor hace N días (la primera llegada del producto)."""
        proveedor = self.env.ref('stock.stock_location_suppliers')
        movimiento = self.env['stock.move'].create({
            'product_id': plantilla.product_variant_id.id, 'product_uom_qty': cantidad,
            'product_uom': plantilla.uom_id.id, 'location_id': proveedor.id,
            'location_dest_id': self.bodega_principal.lot_stock_id.id,
        })
        movimiento._action_confirm()
        movimiento.quantity = cantidad
        movimiento.picked = True
        movimiento._action_done()
        movimiento.date = fields.Datetime.to_datetime(self.hoy - timedelta(days=dias_atras)) + timedelta(hours=17)
        return movimiento

    def test_lo_que_llego_hace_poco_y_no_se_vende_es_nuevo_no_parado(self):
        nuevo = self.con_costo('ZZRO NUEVO', 0)
        self.recibir(nuevo, 3, dias_atras=10)
        viejo = self.con_costo('ZZRO VIEJO SIN VENTAS', 0)
        self.recibir(viejo, 3, dias_atras=45)
        todos = self.ver('todos')
        self.assertEqual(todos['ZZRO NUEVO']['grupo'], 'nuevo')
        self.assertEqual(todos['ZZRO VIEJO SIN VENTAS']['grupo'], 'nunca')
        self.assertEqual(todos['ZZRO NUEVO']['llegada'], fields.Date.to_string(self.hoy - timedelta(days=10)))
        self.assertNotIn('ZZRO NUEVO', self.ver('mas_de_30'), 'lo nuevo no se ofrece como candidato a rebajar')
        self.assertIn('ZZRO VIEJO SIN VENTAS', self.ver('mas_de_30'))

    def test_un_ajuste_de_inventario_no_es_una_llegada(self):
        """Las existencias que entraron por un ajuste de inventario (o una carga inicial) no cuentan como «llegó hace
        poco»: solo una recepción de un proveedor."""
        ajustado = self.con_costo('ZZRO AJUSTADO HOY', 0)
        movimiento = self.env['stock.move'].create({
            'product_id': ajustado.product_variant_id.id, 'product_uom_qty': 3,
            'product_uom': ajustado.uom_id.id, 'location_id': ajustado.property_stock_inventory.id,
            'location_dest_id': self.bodega_principal.lot_stock_id.id})
        movimiento._action_confirm()
        movimiento.quantity = 3
        movimiento.picked = True
        movimiento._action_done()
        movimiento.date = fields.Datetime.to_datetime(self.hoy - timedelta(days=5)) + timedelta(hours=17)
        self.assertEqual(ajustado.dcasa_stock, 3)
        fila = self.ver('todos')['ZZRO AJUSTADO HOY']
        self.assertEqual(fila['grupo'], 'nunca')
        self.assertIsNone(fila['llegada'])

    def test_un_pedido_abierto_saca_al_producto_de_los_candidatos(self):
        producto = self.con_costo('ZZRO CON PEDIDO', 5)
        self.facturar(producto, 1, dias_atras=120)
        pedido = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': producto.product_variant_id.id, 'product_uom_qty': 2,
                                           'price_unit': 100.0, 'tax_ids': [Command.clear()]})]})
        self.assertEqual(self.ver('todos')['ZZRO CON PEDIDO']['grupo'], 'v180', 'una cotización no cuenta')
        pedido.action_confirm()
        fila = self.ver('todos')['ZZRO CON PEDIDO']
        self.assertEqual((fila['grupo'], fila['pedido_abierto']), ('abierto', 2.0))
        self.assertNotIn('ZZRO CON PEDIDO', self.ver('mas_de_90'))
        self.assertIn('ZZRO CON PEDIDO', self.ver('abierto'))

    # --- Ancla, rotación y cobertura -------------------------------------------------------------------------------

    def test_el_ancla_es_el_producto_que_solo_hace_mas_del_80_por_ciento_de_las_unidades(self):
        """Uno que vende 100,000 unidades en 90 días hace, él solo, más del 80 % de lo que vende toda la tienda: es
        el único ancla. Los que venden 15 y 10 no lo son."""
        gigante = self.con_costo('ZZRO ANCLA A', 50)
        medio = self.con_costo('ZZRO ANCLA B', 50)
        chico = self.con_costo('ZZRO ANCLA C', 50)
        for plantilla, unidades in ((gigante, 100000), (medio, 15), (chico, 10)):
            self.facturar(plantilla, unidades, dias_atras=10)
        todos = self.ver('todos', orden='rotacion')
        self.assertEqual({n: f['ancla'] for n, f in todos.items() if n.startswith('ZZRO ANCLA')},
                         {'ZZRO ANCLA A': True, 'ZZRO ANCLA B': False, 'ZZRO ANCLA C': False})
        self.assertEqual(list(todos)[:3], ['ZZRO ANCLA A', 'ZZRO ANCLA B', 'ZZRO ANCLA C'],
                         'por rotación, de más a menos unidades de 90 días')
        self.assertEqual(list(self.ver('ancla')), ['ZZRO ANCLA A'])

    def test_el_corte_del_ancla_es_el_80_por_ciento_exacto(self):
        """Cuatro productos que venden 1000, 300, 150 y 50 unidades: el primero llega al 66 % y el segundo al 86 %: con
        el 80 % de corte, los dos primeros son ancla y el tercero ya no (el corte es el 80 %, no el 99 %). La cuenta se
        comprueba contra TODA la tienda, con la regla escrita aparte."""
        for nombre, unidades in (('A', 1000), ('B', 300), ('C', 150), ('D', 50)):
            self.facturar(self.con_costo(f'ZZRO CORTE {nombre}', 5), unidades, dias_atras=10)
        modelo = self.env['dcasa.rotacion'].with_user(self.gerencia)
        hoy, _dinero, filas = modelo._calcular()
        vendidos = sorted((f for f in filas.values() if f['u90'] > 0),
                          key=lambda f: (-f['u90'], f['plantilla'].name or '', f['plantilla'].id))
        total = sum(f['u90'] for f in vendidos)
        acumulado = 0.0
        for fila in vendidos:
            esperado = acumulado < 0.8 * total
            self.assertEqual(fila['ancla'], esperado, fila['plantilla'].name)
            acumulado += fila['u90']
        ancla = {f['plantilla'].name for f in vendidos if f['ancla'] and f['plantilla'].name.startswith('ZZRO CORTE')}
        self.assertEqual(ancla, {'ZZRO CORTE A', 'ZZRO CORTE B'})
        self.assertEqual(hoy, self.hoy)

    def test_la_cobertura_son_los_dias_que_alcanza_lo_que_hay_al_ritmo_de_90_dias(self):
        """90 unidades vendidas en 90 días = 1 al día; con 40 en existencia alcanza para 40 días."""
        rapido = self.con_costo('ZZRO COBERTURA', 40)
        self.facturar(rapido, 90, dias_atras=3)
        fila = self.ver('todos')['ZZRO COBERTURA']
        self.assertEqual((fila['cobertura_dias'], fila['vendidas_90']), (40, 90.0))
        self.assertIsNone(self.ver('todos')['ZZRO NUNCA']['cobertura_dias'], 'sin ventas no se calcula')

    def test_en_90_dias_cuentan_las_facturas_donde_salio_no_solo_las_unidades(self):
        frecuente = self.con_costo('ZZRO FRECUENTE', 9)
        for dias in (1, 20, 40, 100):
            self.facturar(frecuente, 2, dias_atras=dias)
        fila = self.ver('todos')['ZZRO FRECUENTE']
        self.assertEqual((fila['ventas_90'], fila['vendidas_90'], fila['vendidas_30'], fila['vendidas_60']),
                         (3, 6.0, 4.0, 6.0), 'la de hace 100 días queda fuera de las ventanas')

    # --- El dinero ------------------------------------------------------------------------------------------------

    def test_el_capital_es_el_del_valor_del_inventario(self):
        """La suma al costo de los productos activos con existencias es lo que dice la valuación de Odoo, la misma
        de «Valor del inventario»."""
        datos = self.datos(vista='todos', texto='ZZRO')
        self.assertTrue(datos['con_dinero'])
        todos = self.datos(vista='todos')
        valuacion = self.env['dcasa.tablero'].with_user(self.gerencia).valor_del_inventario()
        activos = self.env['product.template'].search([('active', '=', True), ('sale_ok', '=', True),
                                                       ('is_storable', '=', True)])
        archivados_o_fuera = sum(
            costo for producto, _u, costo in self.env['dcasa.tablero']._existencias_valoradas()
            if producto.product_tmpl_id not in activos and _u > 0)
        self.assertAlmostEqual(todos['resumen']['capital'], valuacion['total']['costo'] - archivados_o_fuera, 2)
        fila = self.fila(datos, self.fresco)
        self.assertEqual((fila['capital'], fila['costo_unitario'], fila['precio_unitario'], fila['margen']),
                         (120.0, 60.0, 100.0, 40.0))
        self.assertEqual(fila['venta_total'], 200.0)

    def test_las_tarjetas_suman_el_capital_de_lo_que_tiene_existencias(self):
        datos = self.datos(vista='todos')
        suma = sum(t['capital'] for t in datos['tarjetas'])
        self.assertAlmostEqual(suma, datos['resumen']['capital'], 2)
        self.assertEqual(sum(t['productos'] for t in datos['tarjetas']), datos['resumen']['productos'])
        parados = sum(self.tarjeta(datos, c)['capital'] for c in ('v180', 'mas180', 'nunca'))
        self.assertAlmostEqual(datos['resumen']['capital_parado_90'], parados, 2)

    def test_sin_costo_se_avisa_y_no_tiene_margen(self):
        sin_costo = self.con_costo('ZZRO SIN COSTO', 3, costo=0.0)
        fila = self.ver('todos')['ZZRO SIN COSTO']
        self.assertTrue(fila['sin_costo'])
        self.assertIsNone(fila['margen'])
        self.assertTrue(sin_costo.dcasa_stock)
        self.assertGreaterEqual(self.datos(vista='todos')['resumen']['sin_costo'], 1)

    def test_la_simulacion_de_rebaja_no_toca_ningun_precio(self):
        """Con 20 %: los 6 productos de la prueba valen 100 y cuestan 60, 2 de cada uno. Rebajados quedan en 80
        (margen 25 %): entran 160 por producto; el costo es 120. Con 50 %, el precio (50) queda por debajo del costo
        (60): todos bajan del costo."""
        precio_antes = self.fresco.list_price
        datos = self.datos(vista='mas_de_30', texto='ZZRO', rebaja=20)
        simulacion = datos['simulacion']
        self.assertEqual((simulacion['productos'], simulacion['capital'], simulacion['ingreso']), (5, 600.0, 800.0))
        self.assertEqual((simulacion['ganancia'], simulacion['margen'], simulacion['bajo_costo']), (200.0, 25.0, 0))
        fila = self.fila(datos, self.treinta)
        self.assertEqual((fila['precio_rebaja'], fila['margen_rebaja'], fila['bajo_costo']), (80.0, 25.0, False))
        fuerte = self.datos(vista='mas_de_30', texto='ZZRO', rebaja=50)['simulacion']
        self.assertEqual((fuerte['bajo_costo'], fuerte['unidades_bajo_costo']), (5, 10.0))
        self.assertEqual(self.fresco.list_price, precio_antes, 'solo simula: no cambia ningún precio')

    def test_el_descuento_tiene_que_ser_un_numero_razonable(self):
        for malo in (-5, 100, 1000, 'mucho', [10], True):
            with self.assertRaises(UserError, msg=f'rebaja={malo!r}'):
                self.datos(vista='mas_de_90', rebaja=malo)
        self.assertIsNone(self.datos(vista='mas_de_90', rebaja='')['rebaja'])
        self.assertIsNone(self.datos(vista='mas_de_90', rebaja=0)['rebaja'], 'cero es «sin descuento»')
        self.assertEqual(self.datos(vista='mas_de_90', rebaja='12.5')['rebaja'], 12.5)

    # --- Filtros y orden ------------------------------------------------------------------------------------------

    def test_por_categoria_y_por_texto(self):
        otro = self.con_costo('ZZRO OTRA CATEGORIA', 2, categoria=self.otra_categoria)
        solo_otra = self.datos(vista='todos', categoria=self.otra_categoria.id)
        self.assertIsNotNone(self.fila(solo_otra, otro))
        self.assertIsNone(self.fila(solo_otra, self.fresco))
        self.assertEqual([t['productos'] for t in solo_otra['tarjetas'] if t['clave'] == 'nunca'], [1],
                         'las tarjetas también ven solo esa categoría')
        por_texto = self.datos(vista='todos', categoria=self.categoria.id, texto='zzro noventa')
        self.assertEqual([f['nombre'] for f in por_texto['productos']], ['ZZRO NOVENTA'])
        self.assertEqual(self.tarjeta(por_texto, 'nunca')['productos'], 1,
                         'buscar un nombre no cambia las tarjetas de la categoría')
        with self.assertRaises(UserError):
            self.datos(categoria='no-existe')

    def test_el_orden_por_dias_pone_primero_lo_que_nunca_se_vendio(self):
        nombres = list(self.ver('todos', orden='dias'))
        self.assertEqual(nombres[:3], ['ZZRO NUNCA', 'ZZRO CIENTO OCHENTA', 'ZZRO NOVENTA'])
        self.assertEqual(nombres[-1], 'ZZRO FRESCO')

    def test_los_demas_ordenes_funcionan(self):
        for orden in ('capital', 'rotacion', 'margen', 'cobertura', 'nombre'):
            nombres = list(self.ver('todos', orden=orden))
            self.assertEqual(len(nombres), 6, orden)
        self.assertEqual(list(self.ver('todos', orden='nombre')), sorted(self.ver('todos')))
        with self.assertRaises(UserError):
            self.datos(orden='al-azar')
        with self.assertRaises(UserError):
            self.datos(vista='los-que-quiero')

    def test_la_pantalla_corta_a_100_y_dice_cuantos_hay(self):
        datos = self.datos(vista='todos')
        self.assertLessEqual(len(datos['productos']), 100)
        self.assertEqual(datos['mostrando'], len(datos['productos']))
        self.assertGreaterEqual(datos['total'], 6)

    # --- Permisos ---------------------------------------------------------------------------------------------------

    def test_marketing_ve_unidades_y_dias_pero_no_dinero(self):
        datos = self.datos(self.marketing_rol, vista='mas_de_90', texto='ZZRO', rebaja=20, orden='capital')
        self.assertFalse(datos['con_dinero'])
        self.assertNotIn('simulacion', datos)
        self.assertEqual(datos['orden'], 'dias', 'sin dinero no se ordena por capital')
        for tarjeta in datos['tarjetas']:
            self.assertNotIn('capital', tarjeta)
        self.assertNotIn('capital', datos['resumen'])
        for fila in datos['productos']:
            for clave in ('capital', 'costo_unitario', 'precio_unitario', 'margen', 'venta_total', 'precio_rebaja'):
                self.assertNotIn(clave, fila)
        self.assertEqual({f['nombre'] for f in datos['productos']}, {'ZZRO NOVENTA', 'ZZRO CIENTO OCHENTA',
                                                                      'ZZRO NUNCA'})

    def test_administradores_y_gerencia_ven_el_dinero(self):
        for usuario in (self.gerencia, self.admin):
            self.assertTrue(self.datos(usuario, vista='todos')['con_dinero'])

    def test_vendedora_y_bodega_no_entran(self):
        for usuario in (self.vendedora, self.bodega):
            with self.assertRaises(AccessError):
                self.datos(usuario)
            with self.assertRaises(AccessError):
                self.env['dcasa.rotacion'].with_user(usuario)._excel()

    # --- Excel ----------------------------------------------------------------------------------------------------

    def leer_excel(self, **kw):
        from openpyxl import load_workbook  # noqa: PLC0415
        nombre, contenido = self.env['dcasa.rotacion'].with_user(kw.pop('usuario', self.gerencia))._excel(**kw)
        return nombre, load_workbook(io.BytesIO(contenido), data_only=False)

    def test_el_excel_trae_lo_mismo_que_la_pantalla_y_un_resumen(self):
        nombre, libro = self.leer_excel(vista='mas_de_30', texto='ZZRO', rebaja=20, orden='dias')
        self.assertEqual(nombre, f'rotacion_mas_de_30_{self.hoy.isoformat()}.xlsx')
        self.assertEqual(libro.sheetnames, ['Rotación', 'Resumen'])
        hoja = libro['Rotación']
        filas = [[celda.value for celda in fila] for fila in hoja.iter_rows(min_row=5)]
        encabezado = filas[0]
        self.assertEqual(encabezado[0], 'Producto')
        self.assertIn('Capital parado', encabezado)
        self.assertIn('Precio con 20 % de descuento', encabezado)
        productos = [fila[0] for fila in filas[1:] if fila[0]]
        self.assertEqual(productos, ['ZZRO NUNCA', 'ZZRO CIENTO OCHENTA', 'ZZRO NOVENTA', 'ZZRO SESENTA',
                                     'ZZRO TREINTA'])
        columna = encabezado.index('Días sin vender')
        self.assertEqual([fila[columna] for fila in filas[1:]], ['—', 200, 90, 60, 30])
        resumen = [[c.value for c in f] for f in libro['Resumen'].iter_rows()]
        self.assertEqual(resumen[0][:3], ['Grupo', 'Productos', 'Unidades'])
        self.assertEqual(resumen[-1][0], 'Total')
        self.assertTrue(str(resumen[-1][1]).startswith('=SUM('), 'el total es una fórmula, para que cuadre')

    def test_el_excel_sin_dinero_no_trae_costos(self):
        _nombre, libro = self.leer_excel(usuario=self.marketing_rol, vista='todos', texto='ZZRO', rebaja=20)
        encabezado = [c.value for c in next(libro['Rotación'].iter_rows(min_row=5, max_row=5))]
        for prohibido in ('Costo unitario', 'Capital parado', 'Precio sin ITBMS', 'Margen %'):
            self.assertNotIn(prohibido, encabezado)
        resumen = [c.value for c in next(libro['Resumen'].iter_rows(max_row=1))]
        self.assertNotIn('Capital al costo', resumen)

    def test_un_nombre_que_parece_formula_sale_como_texto(self):
        raro = self.con_costo('=SUM(A1:A9) ZZRO FORMULA', 1)
        _nombre, libro = self.leer_excel(vista='todos', texto='ZZRO FORMULA')
        hoja = libro['Rotación']
        celda = next(c for fila in hoja.iter_rows(min_row=6) for c in fila
                     if c.value and 'ZZRO FORMULA' in str(c.value))
        self.assertEqual(celda.data_type, 's')
        self.assertTrue(raro.dcasa_stock)

    def test_un_nombre_con_formula_de_matriz_tambien_sale_como_texto(self):
        """``strings_to_formulas=False`` de xlsxwriter no cubre «{=...}»: salía como fórmula de matriz y correría en la
        computadora de quien abre el Excel (revisión independiente del 2026-11-22)."""
        # Solo es fórmula de matriz si TODA la celda es «{=...}»: el nombre es justo eso.
        self.con_costo('{=1+1}', 1)
        _nombre, libro = self.leer_excel(vista='todos', texto='{=1+1}')
        celdas = [c for fila in libro['Rotación'].iter_rows(min_row=6) for c in fila if c.value == '{=1+1}']
        self.assertEqual(len(celdas), 1)
        self.assertEqual(celdas[0].data_type, 's', 'texto, no fórmula de matriz')

    def test_elegir_una_categoria_no_hace_una_busqueda_por_producto(self):
        """Con una categoría elegida, la pantalla buscaba las plantillas de la categoría UNA VEZ POR PRODUCTO (crecía
        al cuadrado: 2,600 productos tardaban 8 segundos). Ahora las consultas no crecen con los productos."""
        categoria = self.env['product.category'].create({'name': 'ZZRO Categoría de rendimiento'})

        def consultas():
            self.env.invalidate_all()
            antes = self.env.cr.sql_log_count
            self.datos(vista='todos', categoria=categoria.id)
            return self.env.cr.sql_log_count - antes
        for i in range(3):
            self.con_costo(f'ZZRO RENDIMIENTO A{i}', 1, categoria=categoria)
        con_pocos = consultas()
        for i in range(25):
            self.con_costo(f'ZZRO RENDIMIENTO B{i}', 1, categoria=categoria)
        con_muchos = consultas()
        self.assertLess(con_muchos - con_pocos, 10, (con_pocos, con_muchos))
