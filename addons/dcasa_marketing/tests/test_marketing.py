"""Marketing: stock por categoría, más vendidos, movimiento y quietos por periodo, fotos que faltan, permisos, el acceso
del Inicio y las herramientas de Brian.

Todo se mide dentro de una categoría propia de la prueba (ZZMK…), así no se mezcla con el catálogo de la base."""
from odoo.addons.dcasa_brian.models import pasos
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .comun import MarketingCommon, crear_usuario, foto


@tagged('post_install', '-at_install')
class TestMarketing(MarketingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        p = cls.producto
        cls.cama = p('ZZMK Cama vendida', 'ZZMK-CAMA', stock=20, con_foto=True, extras=2)
        cls.mesa = p('ZZMK Mesa entregada', 'ZZMK-MESA', stock=9, con_foto=True)
        cls.silla = p('ZZMK Silla de las dos', 'ZZMK-SILLA', stock=15)
        cls.quieta_nunca = p('ZZMK Repisa nunca vendida', 'ZZMK-REPISA', stock=4)
        cls.quieta_vieja = p('ZZMK Lámpara de hace tiempo', 'ZZMK-LAMPARA', stock=30, con_foto=True, extras=1)
        cls.quieta_menos_vieja = p('ZZMK Banco de hace poco', 'ZZMK-BANCO', stock=2)
        cls.agotada = p('ZZMK Cómoda agotada', 'ZZMK-COMODA', stock=0)
        cls.de_otra = p('ZZMK Puff de otra categoría', 'ZZMK-PUFF', stock=50, categoria=cls.otra_categoria)
        cls.mesa.product_variant_id.barcode = 'ZZMK7750001'

    def setUp(self):
        super().setUp()
        # Semana: cama 5 vendidas (6 menos 1 devuelta); silla 2 vendidas y 3 entregadas; mesa 4 entregadas.
        self.facturar(self.cama, 6, dias_atras=1)
        self.facturar(self.cama, 1, dias_atras=1, nota=True)
        self.facturar(self.silla, 2, dias_atras=2)
        self.entregar(self.silla, 3, dias_atras=2)
        self.entregar(self.mesa, 4, dias_atras=3)
        # Fuera de la semana pero dentro de 15 días: la lámpara 7 vendidas hace 10 días.
        self.facturar(self.quieta_vieja, 7, dias_atras=10)
        # Dentro del mes, fuera de 15 días: el banco 1 vendido hace 20 días; la lámpara también hace 25.
        self.facturar(self.quieta_menos_vieja, 1, dias_atras=20)
        self.facturar(self.quieta_vieja, 1, dias_atras=25)
        # La repisa nunca se vendió. El puff es de otra categoría: 9 vendidos hace 3 días.
        self.facturar(self.de_otra, 9, dias_atras=3)

    def datos(self, periodo='semana', categoria=None, usuario=None):
        return self.marketing(usuario).datos(periodo=periodo, categoria=categoria or self.categoria.id)

    @staticmethod
    def ids(filas):
        return [fila['id'] for fila in filas]

    def test_solo_gerencia_y_administradores(self):
        for metodo, kwargs in (('datos', {}), ('buscar_fotos', {}), ('accion_productos', {'ids': []})):
            with self.subTest(metodo=metodo), self.assertRaises(AccessError):
                getattr(self.marketing(self.vendedora), metodo)(**kwargs)
            with self.subTest(metodo=metodo, quien='bodega'), self.assertRaises(AccessError):
                getattr(self.marketing(self.bodega), metodo)(**kwargs)
        self.assertTrue(self.datos())
        admin = self.env.ref('base.user_admin')
        self.assertTrue(self.marketing(admin).datos(periodo='mes'))
        # El menú y el acceso del Inicio tienen el mismo permiso.
        menu = self.env.ref('dcasa_marketing.menu_marketing')
        self.assertEqual(set(menu.group_ids.ids),
                         {self.env.ref('sales_team.group_sale_manager').id, self.env.ref('base.group_system').id})
        self.assertEqual(menu.action, self.env.ref('dcasa_marketing.accion_marketing'))

    def test_periodos_semana_15_dias_y_mes(self):
        for clave, dias in (('semana', 7), ('15_dias', 15), ('mes', 30)):
            periodo = self.datos(clave)['periodo']
            self.assertEqual(periodo['dias'], dias)
            self.assertEqual(periodo['hasta'], str(self.hoy))
            self.assertIn(f'Últimos {dias} días', periodo['etiqueta'])
        with self.assertRaises(UserError):
            self.datos('anio')
        self.assertEqual([p['clave'] for p in self.datos()['periodos']], ['semana', '15_dias', 'mes'])

    def test_mas_vendidos_del_periodo_con_la_base_del_inicio(self):
        semana = self.datos('semana')['mas_vendidos']
        self.assertEqual(self.ids(semana), [self.cama.id, self.silla.id], 'la nota de crédito resta: 5 y 2')
        self.assertEqual([f['unidades'] for f in semana], [5, 2])
        quince = self.datos('15_dias')['mas_vendidos']
        self.assertEqual(self.ids(quince), [self.quieta_vieja.id, self.cama.id, self.silla.id])
        mes = self.datos('mes')['mas_vendidos']
        self.assertEqual([f['unidades'] for f in mes], [8, 5, 2, 1])
        self.assertEqual(mes[-1]['id'], self.quieta_menos_vieja.id)
        self.assertNotIn(self.de_otra.id, self.ids(mes), 'la categoría filtra')
        todas = self.marketing().datos(periodo='semana')['mas_vendidos']
        self.assertIn(self.de_otra.id, self.ids(todas), 'sin categoría, todas')

    def test_mayor_movimiento_cuenta_una_vez_lo_vendido_y_entregado(self):
        filas = {f['id']: f for f in self.datos('semana')['mas_movimiento']}
        self.assertEqual(set(filas), {self.cama.id, self.silla.id, self.mesa.id})
        self.assertEqual((filas[self.silla.id]['vendidas'], filas[self.silla.id]['entregadas'],
                          filas[self.silla.id]['movimiento']), (2, 3, 3), 'lo mayor, no la suma')
        self.assertEqual(filas[self.mesa.id]['movimiento'], 4, 'solo entregada')
        self.assertEqual(filas[self.cama.id]['movimiento'], 5, 'solo facturada')
        self.assertEqual(self.ids(self.datos('semana')['mas_movimiento']), [self.cama.id, self.mesa.id, self.silla.id])
        # Una devolución del cliente resta lo entregado.
        self.entregar(self.mesa, 1, dias_atras=1, devolver=True)
        filas = {f['id']: f for f in self.datos('semana')['mas_movimiento']}
        self.assertEqual(filas[self.mesa.id]['entregadas'], 3)

    def test_quietos_con_stock_sin_ventas_ni_salidas_los_que_nunca_se_vendieron_primero(self):
        semana = self.datos('semana')
        quietos = self.ids(semana['quietos'])
        # La repisa nunca se vendió; el banco se vendió por última vez hace 20 días y la lámpara hace 10.
        self.assertEqual(quietos, [self.quieta_nunca.id, self.quieta_menos_vieja.id, self.quieta_vieja.id])
        self.assertEqual(semana['quietos_total'], 3)
        self.assertEqual(sorted(semana['quietos_ids']), sorted(quietos))
        self.assertNotIn(self.agotada.id, quietos, 'sin stock no es quieto: no hay qué empujar')
        nunca, banco, lampara = semana['quietos']
        self.assertIsNone(nunca['ultima_venta'])
        self.assertEqual(banco['dias_sin_vender'], 20)
        self.assertEqual(lampara['dias_sin_vender'], 10)
        self.assertEqual(lampara['stock'], 30)
        # En 15 días la lámpara ya se movió; en el mes, el banco también.
        self.assertEqual(self.ids(self.datos('15_dias')['quietos']), [self.quieta_nunca.id, self.quieta_menos_vieja.id])
        self.assertEqual(self.ids(self.datos('mes')['quietos']), [self.quieta_nunca.id])

    def test_stock_por_categoria_mas_y_menos_sin_los_agotados(self):
        stock = self.datos()['stock']
        self.assertEqual(stock['mas'][0]['id'], self.quieta_vieja.id)
        self.assertEqual(stock['menos'][0]['id'], self.quieta_menos_vieja.id)
        self.assertNotIn(self.agotada.id, self.ids(stock['menos']))
        self.assertEqual(stock['agotados'], 1)
        self.assertEqual(stock['con_stock'], 6)
        # Con 6 productos con stock, cada uno sale en una sola lista: 3 arriba y 3 abajo.
        self.assertEqual(len(stock['mas']), 3)
        self.assertEqual(len(stock['menos']), 3)
        self.assertFalse(set(self.ids(stock['mas'])) & set(self.ids(stock['menos'])))
        self.assertNotIn(self.de_otra.id, self.ids(stock['mas']))
        otra = self.marketing().datos(categoria=self.otra_categoria.id)['stock']
        self.assertEqual(self.ids(otra['mas']), [self.de_otra.id])
        # La lista de categorías trae la de la prueba con cuántos productos.
        categorias = {c['id']: c for c in self.datos()['categorias']}
        self.assertEqual(categorias[self.categoria.id]['productos'], 7)
        with self.assertRaises(UserError):
            self.marketing().datos(categoria=999999999)
        with self.assertRaises(UserError):
            self.marketing().datos(categoria='Salas')

    def test_las_subcategorias_son_tipos_como_en_el_inicio(self):
        """Como «Unidades vendidas por tipo» del Inicio: «Muebles / Salas / Modulares» es del tipo «Salas»."""
        hija = self.env['product.category'].create({'name': 'ZZMK Salas hija', 'parent_id': self.categoria.id})
        nieta = self.env['product.category'].create({'name': 'ZZMK Modulares', 'parent_id': hija.id})
        sofa = self.producto('ZZMK Sofá modular', 'ZZMK-MODULAR', stock=100, categoria=nieta)
        self.assertEqual(self.ids(self.marketing().datos(categoria=hija.id)['stock']['mas']), [sofa.id])
        self.assertNotIn(sofa.id, self.ids(self.datos()['stock']['mas']), 'no se mezcla con lo de la raíz')
        nombres = {c['id']: c['nombre'] for c in self.datos()['categorias']}
        self.assertEqual(nombres.get(hija.id), 'ZZMK Salas hija')
        self.assertNotIn(nieta.id, nombres)

    def test_los_productos_sin_categoria_tambien_se_eligen(self):
        """Odoo 19 no exige categoría: esos productos salen juntos en «Sin categoría» y no se pierden."""
        huerfano = self.producto('ZZMK Producto sin categoría', 'ZZMK-HUERFANO', stock=3)
        huerfano.categ_id = False
        sin = next(c for c in self.marketing().datos()['categorias'] if c['id'] == 'sin')
        self.assertEqual(sin['nombre'], 'Sin categoría')
        self.assertGreaterEqual(sin['productos'], 1)
        datos = self.marketing().datos(categoria='sin')
        self.assertEqual(datos['categoria'], 'sin')
        self.assertIn(huerfano.id, datos['quietos_ids'], 'con stock y sin ventas: quieto')
        self.assertNotIn(self.cama.id, datos['quietos_ids'] + self.ids(datos['stock']['mas']), 'solo los sin categoría')
        self.assertIn(huerfano.id, self.ids(self.marketing().buscar_fotos(texto='ZZMK-HUERFANO', filtro='todos',
                                                                           categoria='sin')['productos']))

    def test_fotos_que_faltan_buscar_por_nombre_codigo_y_codigo_de_barras(self):
        Marketing = self.marketing()
        resultado = Marketing.buscar_fotos(filtro='faltan', categoria=self.categoria.id)
        por_id = {f['id']: f for f in resultado['productos']}
        self.assertEqual(por_id[self.mesa.id]['fotos'], 1)
        self.assertEqual(por_id[self.silla.id]['fotos'], 0)
        self.assertNotIn(self.cama.id, por_id, 'la cama tiene 3: no le falta')
        self.assertEqual([f['fotos'] for f in resultado['productos']],
                         sorted(f['fotos'] for f in resultado['productos']), 'primero las sin foto')
        self.assertEqual(resultado['conteo'], {'sin_foto': 4, 'una_foto': 1, 'productos': 7})
        self.assertEqual(self.ids(Marketing.buscar_fotos(filtro='una_foto', categoria=self.categoria.id)['productos']),
                         [self.mesa.id])
        sin = Marketing.buscar_fotos(filtro='sin_foto', categoria=self.categoria.id)['productos']
        self.assertTrue(all(f['fotos'] == 0 and not f['con_foto'] for f in sin))
        for texto, esperado in (('lámpara tiempo', self.quieta_vieja), ('ZZMK-CAMA', self.cama),
                                ('ZZMK7750001', self.mesa), ('zzmk mesa', self.mesa)):
            with self.subTest(texto=texto):
                encontrados = Marketing.buscar_fotos(texto=texto, filtro='todos')['productos']
                self.assertEqual(self.ids(encontrados), [esperado.id])
        codigo = self.cama.dcasa_codigo_publico
        if codigo:
            self.assertEqual(self.ids(Marketing.buscar_fotos(texto=codigo, filtro='todos')['productos']),
                             [self.cama.id])
        lampara = Marketing.buscar_fotos(texto='ZZMK-LAMPARA', filtro='todos')['productos'][0]
        self.assertEqual(lampara['fotos'], 2)
        with self.assertRaises(UserError):
            Marketing.buscar_fotos(filtro='raro')
        with self.assertRaises(UserError):
            Marketing.buscar_fotos(texto=['x'])
        # Los conteos de arriba de la pantalla.
        self.assertEqual(self.datos()['fotos'], {'sin_foto': 4, 'una_foto': 1, 'productos': 7})

    def test_subir_la_foto_saca_al_producto_de_la_lista_de_faltan(self):
        self.silla.with_user(self.gerencia).dcasa_fotos_subir([{'nombre': 'a', 'datos': foto()},
                                                               {'nombre': 'b', 'datos': foto()}])
        faltan = self.ids(self.marketing().buscar_fotos(filtro='faltan', categoria=self.categoria.id)['productos'])
        self.assertNotIn(self.silla.id, faltan)

    def test_la_lista_de_productos_para_campanas(self):
        accion = self.marketing().accion_productos(ids=[self.cama.id, self.mesa.id], nombre='Más quietos')
        self.assertEqual(accion['res_model'], 'product.template')
        self.assertEqual(accion['domain'], [('id', 'in', [self.cama.id, self.mesa.id])])
        self.assertEqual(accion['name'], 'Más quietos')
        self.assertEqual(accion['id'], self.env.ref('sale.product_template_action').id, 'la misma lista de campañas')
        for malo in ('1,2', [True], ['x']):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.marketing().accion_productos(ids=malo)

    def test_el_inicio_tiene_marketing_para_gerencia_y_no_para_la_vendedora(self):
        def atajos(usuario):
            return {a['clave']: a for a in self.env['dcasa.tablero'].with_user(usuario).obtener_datos()['atajos']}
        marketing = atajos(self.gerencia).get('marketing')
        self.assertTrue(marketing)
        self.assertEqual(marketing['accion'], 'dcasa_marketing.accion_marketing')
        self.assertIsNone(marketing['vista'])
        self.assertNotIn('marketing', atajos(self.vendedora))
        contador = crear_usuario(self.env, 'zzmk_contador', ['account.group_account_user'])
        self.assertNotIn('marketing', atajos(contador), 'el contador no tiene las ventas de la tienda en Marketing')
        claves = list(atajos(self.gerencia))
        self.assertLess(claves.index('escaner'), claves.index('marketing'))
        if 'oportunidades' in claves:
            self.assertLess(claves.index('marketing'), claves.index('oportunidades'))


@tagged('post_install', '-at_install')
class TestBrianMarketing(MarketingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cama = cls.producto('ZZMK Cama de Brian', 'ZZMK-BR-CAMA', stock=5, con_foto=True)
        cls.quieta = cls.producto('ZZMK Repisa de Brian', 'ZZMK-BR-REPISA', stock=8)

    def herramientas(self, usuario):
        return self.env['brian.herramientas'].with_user(usuario)

    def test_las_herramientas_y_quien_las_tiene(self):
        de_gerencia = {h['name'] for h in self.herramientas(self.gerencia).catalogo()}
        de_vendedora = {h['name'] for h in self.herramientas(self.vendedora).catalogo()}
        self.assertLessEqual({'movimiento_de_productos', 'fotos_que_faltan'}, de_gerencia)
        self.assertIn('fotos_que_faltan', de_vendedora)
        self.assertNotIn('movimiento_de_productos', de_vendedora, 'las ventas de toda la tienda son de Gerencia')
        negado = self.herramientas(self.vendedora).ejecutar('movimiento_de_productos', {'periodo': 'semana'})
        self.assertFalse(negado['ok'])

    def test_quietos_y_movimiento_de_esta_semana(self):
        self.facturar(self.cama, 3, dias_atras=1)
        r = self.herramientas(self.gerencia).ejecutar(
            'movimiento_de_productos', {'periodo': 'semana', 'que': 'todo', 'categoria': 'ZZMK Categoría de prueba'})
        self.assertTrue(r['ok'], r)
        datos = r['datos']
        self.assertEqual([f['codigo'] for f in datos['mas_vendidos']], ['ZZMK-BR-CAMA'])
        self.assertEqual(datos['mas_vendidos'][0]['unidades'], 3)
        self.assertEqual([f['codigo'] for f in datos['mas_movimiento']], ['ZZMK-BR-CAMA'])
        self.assertEqual([f['codigo'] for f in datos['quietos']], ['ZZMK-BR-REPISA'])
        self.assertIn('nunca', datos['quietos'][0]['ultima_venta'])
        self.assertIn('Últimos 7 días', datos['periodo'])
        solo = self.herramientas(self.gerencia).ejecutar(
            'movimiento_de_productos', {'periodo': 'mes', 'que': 'quietos', 'categoria': 'zzmk categoria de prueba'})
        self.assertTrue(solo['ok'], solo)
        self.assertNotIn('mas_vendidos', solo['datos'])
        malo = self.herramientas(self.gerencia).ejecutar('movimiento_de_productos', {'categoria': 'No existe ZZ'})
        self.assertFalse(malo['ok'])
        self.assertIn('No encontré la categoría', malo['error'])

    def test_el_paso_se_lee_en_palabras(self):
        self.assertEqual(pasos.titulo_paso('movimiento_de_productos', {}),
                         'Revisando qué se mueve y qué está quieto')
        self.assertEqual(pasos.titulo_paso('fotos_que_faltan', {'texto': 'cama'}),
                         'Buscando productos sin fotos «cama»')

    def test_productos_sin_foto(self):
        r = self.herramientas(self.vendedora).ejecutar(
            'fotos_que_faltan', {'estado': 'sin_foto', 'categoria': 'ZZMK Categoría de prueba'})
        self.assertTrue(r['ok'], r)
        self.assertEqual([f['codigo'] for f in r['datos']['productos']], ['ZZMK-BR-REPISA'])
        self.assertEqual(r['datos']['sin_foto'], 1)
        self.assertEqual(r['datos']['con_una_sola_foto'], 1)
        self.assertIn('Marketing', r['datos']['donde_subirlas'])
