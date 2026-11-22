"""«Movimiento» (pedido de la dueña, 2026-11-22): lo que más y lo que menos se mueve, comparando dos periodos.

Cada prueba dice lo que cuenta y cómo: los dos periodos (exactos, con sus extremos), los seis estados, el cambio y su
porcentaje, las notas de crédito, los pedidos (facturas), el resumen, el gráfico, las listas y su orden, los
permisos (el rol Marketing ve unidades, pero no dinero) y el Excel.
"""
import calendar
import io
from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .comun import MarketingCommon, crear_usuario


class MovimientoDatos(MarketingCommon):
    """Productos con ventas conocidas en «los últimos 30 días» (hoy y 29 días atrás) y en los 30 de justo antes (de 59
    a 30 días atrás), todos con precio de factura 10."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # El «hoy» de la pantalla es el de quien la mira (Panamá): las fechas de la prueba salen del mismo.
        cls.hoy = fields.Date.context_today(cls.env['dcasa.movimiento_productos'].with_user(cls.gerencia))
        cls.marketing_rol = crear_usuario(cls.env, 'zzmk_rol_marketing', ['dcasa_marketing.group_marketing'])
        cls.admin = crear_usuario(cls.env, 'zzmk_admin_movimiento', ['base.group_system'])
        cls.categoria_mv = cls.env['product.category'].create({'name': 'ZZMV Categoría'})
        cls.sube = cls.articulo('ZZMV SUBE', 5)                   # este: 6 · antes: 2
        cls.baja = cls.articulo('ZZMV BAJA', 5)                   # este: 1 · antes: 4
        cls.igual = cls.articulo('ZZMV IGUAL', 5)                 # este: 2 · antes: 2
        cls.despierta = cls.articulo('ZZMV DESPIERTA', 5)         # este: 3 · antes: 0
        cls.enfria = cls.articulo('ZZMV ENFRIA', 5)               # este: 0 · antes: 3
        cls.quieto = cls.articulo('ZZMV QUIETO', 4)               # sin ventas en ninguno
        cls.nada = cls.articulo('ZZMV NADA', 0)                   # sin ventas y sin existencias: no sale
        # Este periodo: 29 días atrás es el primer día y hoy el último.
        cls.facturar(cls.sube, 4, dias_atras=29)
        cls.facturar(cls.sube, 2, dias_atras=0)
        cls.facturar(cls.baja, 1, dias_atras=3)
        cls.facturar(cls.igual, 2, dias_atras=10)
        cls.facturar(cls.despierta, 3, dias_atras=1)
        # El de justo antes: 30 días atrás es su último día y 59 el primero.
        cls.facturar(cls.sube, 2, dias_atras=30)
        cls.facturar(cls.baja, 3, dias_atras=40)
        cls.facturar(cls.baja, 1, dias_atras=59)
        cls.facturar(cls.igual, 2, dias_atras=45)
        cls.facturar(cls.enfria, 3, dias_atras=30)
        # Fuera de los dos: 60 días atrás ya no cuenta.
        cls.facturar(cls.quieto, 5, dias_atras=60)
        cls.facturar(cls.nada, 5, dias_atras=60)

    @classmethod
    def articulo(cls, nombre, stock):
        plantilla = cls.producto(nombre, stock=stock, categoria=cls.categoria_mv)
        plantilla.standard_price = 6.0
        return plantilla

    @classmethod
    def facturar(cls, plantilla, cantidad, dias_atras=0, nota=False):
        return MarketingCommon.facturar(cls, plantilla, cantidad, dias_atras, nota)


@tagged('post_install', '-at_install')
class TestMovimiento(MovimientoDatos):

    def datos(self, usuario=None, **kw):
        kw.setdefault('categoria', self.categoria_mv.id)
        return self.env['dcasa.movimiento_productos'].with_user(usuario or self.gerencia).datos(**kw)

    def fila(self, datos, plantilla):
        return next((f for f in datos['productos'] if f['id'] == plantilla.id), None)

    def ver(self, vista='todos', **kw):
        return {f['nombre']: f for f in self.datos(vista=vista, **kw)['productos']}

    # --- Los dos periodos --------------------------------------------------------------------------------------------

    def test_los_dias_se_cuentan_con_sus_dos_extremos(self):
        """30 días son hoy y los 29 de antes; el periodo de justo antes va de 59 a 30 días atrás."""
        datos = self.datos()
        self.assertEqual((datos['este']['desde'], datos['este']['hasta'], datos['este']['dias']),
                         (str(self.hoy - timedelta(days=29)), str(self.hoy), 30))
        self.assertEqual((datos['otro']['desde'], datos['otro']['hasta'], datos['otro']['dias']),
                         (str(self.hoy - timedelta(days=59)), str(self.hoy - timedelta(days=30)), 30))
        filas = self.ver()
        self.assertEqual(filas['ZZMV SUBE']['vendidas_este'], 6.0, 'hoy y 29 días atrás cuentan en este periodo')
        self.assertEqual(filas['ZZMV SUBE']['vendidas_otro'], 2.0, '30 días atrás ya es del periodo de comparación')
        self.assertEqual(filas['ZZMV BAJA']['vendidas_otro'], 4.0, '59 días atrás es el primer día de la comparación')
        self.assertEqual(filas['ZZMV QUIETO']['vendidas_otro'], 0.0, '60 días atrás no cuenta en ninguno')

    def test_los_periodos_rapidos(self):
        for clave, dias in (('7', 7), ('15', 15), ('30', 30), ('60', 60), ('90', 90)):
            datos = self.datos(periodo=clave)
            self.assertEqual(datos['este']['dias'], dias, clave)
            self.assertEqual(datos['este']['hasta'], str(self.hoy))
            self.assertEqual(datos['otro']['dias'], dias, clave)
            self.assertEqual(datos['otro']['hasta'], str(self.hoy - timedelta(days=dias)),
                             'la comparación termina justo antes de que empiece este periodo')

    def test_este_mes_y_el_mes_pasado(self):
        primero = self.hoy.replace(day=1)
        datos = self.datos(periodo='este_mes')
        self.assertEqual((datos['este']['desde'], datos['este']['hasta']), (str(primero), str(self.hoy)))
        anterior = date(primero.year - (primero.month == 1), 12 if primero.month == 1 else primero.month - 1, 1)
        ultimo = calendar.monthrange(anterior.year, anterior.month)[1]
        self.assertEqual(datos['otro']['desde'], str(anterior))
        esperado_hasta = anterior.replace(day=min(self.hoy.day, ultimo))
        self.assertEqual(datos['otro']['hasta'], str(esperado_hasta),
                         'el mismo tramo del mes pasado (nunca pasa de su último día)')
        pasado = self.datos(periodo='mes_pasado')
        self.assertEqual((pasado['este']['desde'], pasado['este']['hasta']),
                         (str(anterior), str(anterior.replace(day=ultimo))))
        self.assertEqual(pasado['este']['dias'], ultimo)
        self.assertEqual(pasado['otro']['hasta'], str(anterior - timedelta(days=1)),
                         'el mes anterior termina justo antes de que empiece el mes pasado')

    def test_el_mismo_periodo_del_anio_pasado(self):
        datos = self.datos(periodo='30', contra='anio')
        self.assertEqual(datos['otro']['hasta'], str(self.hoy.replace(year=self.hoy.year - 1))
                         if not (self.hoy.month == 2 and self.hoy.day == 29) else str(date(self.hoy.year - 1, 2, 28)))
        self.facturar(self.sube, 7, dias_atras=365 + 2)     # un año y dos días atrás: dentro del tramo del año pasado
        filas = self.ver(periodo='30', contra='anio')
        self.assertEqual(filas['ZZMV SUBE']['vendidas_otro'], 7.0)
        self.assertEqual(filas['ZZMV SUBE']['vendidas_este'], 6.0)

    def test_fechas_escritas_a_mano(self):
        desde, hasta = self.hoy - timedelta(days=10), self.hoy - timedelta(days=5)
        antes_d, antes_h = self.hoy - timedelta(days=50), self.hoy - timedelta(days=40)
        datos = self.datos(periodo='fechas', desde=str(desde), hasta=str(hasta), contra='fechas',
                           contra_desde=str(antes_d), contra_hasta=str(antes_h), vista='todos')
        self.assertEqual((datos['este']['dias'], datos['otro']['dias']), (6, 11))
        filas = {f['nombre']: f for f in datos['productos']}
        self.assertEqual(filas['ZZMV IGUAL']['vendidas_este'], 2.0, '10 días atrás es el primer día de «este»')
        self.assertEqual(filas['ZZMV BAJA']['vendidas_otro'], 3.0, '40 días atrás es el último día de la comparación')
        self.assertEqual(filas['ZZMV IGUAL']['vendidas_otro'], 2.0, '45 días atrás está dentro de la comparación')

    def test_fechas_que_no_valen(self):
        malas = [
            dict(periodo='fechas'),                                                       # sin fechas
            dict(periodo='fechas', desde='no-es-fecha', hasta=str(self.hoy)),
            dict(periodo='fechas', desde=str(self.hoy), hasta=str(self.hoy - timedelta(days=1))),   # al revés
            dict(periodo='fechas', desde=str(self.hoy), hasta=str(self.hoy + timedelta(days=1))),   # del futuro
            dict(periodo='fechas', desde=str(self.hoy - timedelta(days=400)), hasta=str(self.hoy)),  # más de un año
            dict(contra='fechas'),                                                         # sin las de la comparación
            dict(contra='fechas', contra_desde=str(self.hoy - timedelta(days=5)),
                 contra_hasta=str(self.hoy)),                                                  # cruzados
            dict(periodo='una-semana'), dict(contra='con-mi-tio'), dict(vista='ninguna'), dict(orden='al-azar'),
            dict(texto=12),
        ]
        for mala in malas:
            with self.subTest(mala=mala), self.assertRaises(UserError):
                self.datos(**mala)
        # Un <input type=date> deja escribir el año 0001: antes daba un error 500; ahora un mensaje.
        for absurda in (dict(periodo='fechas', desde='0001-01-01', hasta='0001-01-05'),
                        dict(periodo='fechas', desde='1999-12-31', hasta='2000-01-05'),
                        dict(contra='fechas', contra_desde='0001-01-01', contra_hasta='0001-01-05')):
            with self.subTest(absurda=absurda), self.assertRaises(UserError):
                self.datos(**absurda)
        # Con «año pasado», un periodo de 366 días se cruzaría con su comparación: se avisa.
        with self.assertRaises(UserError):
            self.datos(periodo='fechas', desde=str(self.hoy - timedelta(days=365)), hasta=str(self.hoy),
                       contra='anio')
        # Un periodo de justo un año sí vale.
        self.assertEqual(self.datos(periodo='fechas', desde=str(self.hoy - timedelta(days=365)),
                                    hasta=str(self.hoy))['este']['dias'], 366)

    # --- Los estados y el cambio ------------------------------------------------------------------------------------

    def test_cada_producto_tiene_un_solo_estado(self):
        filas = self.ver()
        esperado = {'ZZMV SUBE': 'subio', 'ZZMV BAJA': 'bajo', 'ZZMV IGUAL': 'igual', 'ZZMV DESPIERTA': 'desperto',
                    'ZZMV ENFRIA': 'enfrio', 'ZZMV QUIETO': 'quieto'}
        self.assertEqual({nombre: fila['estado'] for nombre, fila in filas.items()}, esperado)
        self.assertNotIn('ZZMV NADA', filas, 'sin ventas y sin existencias no sale')
        self.assertEqual(filas['ZZMV SUBE']['nombre_estado'], 'Subió')
        self.assertEqual(filas['ZZMV ENFRIA']['nombre_estado'], 'Se enfrió')

    def test_el_cambio_y_su_porcentaje(self):
        filas = self.ver()
        self.assertEqual((filas['ZZMV SUBE']['cambio'], filas['ZZMV SUBE']['cambio_pct']), (4.0, 200.0))
        self.assertEqual((filas['ZZMV BAJA']['cambio'], filas['ZZMV BAJA']['cambio_pct']), (-3.0, -75.0))
        self.assertEqual((filas['ZZMV IGUAL']['cambio'], filas['ZZMV IGUAL']['cambio_pct']), (0.0, 0.0))
        self.assertEqual((filas['ZZMV ENFRIA']['cambio'], filas['ZZMV ENFRIA']['cambio_pct']), (-3.0, -100.0))
        self.assertEqual(filas['ZZMV DESPIERTA']['cambio'], 3.0)
        self.assertIsNone(filas['ZZMV DESPIERTA']['cambio_pct'],
                          'sin ventas antes no hay porcentaje (no se divide entre 0)')

    def test_la_nota_de_credito_resta_unidades(self):
        self.facturar(self.sube, 1, dias_atras=4, nota=True)
        fila = self.ver()['ZZMV SUBE']
        self.assertEqual((fila['vendidas_este'], fila['cambio'], fila['cambio_pct']), (5.0, 3.0, 150.0))
        self.assertEqual(fila['pedidos_este'], 2, 'una nota de crédito resta unidades, pero no es un pedido')
        self.assertEqual(self.datos()['resumen']['pedidos']['a'], 5, 'ni en el total de pedidos del resumen')
        # Si devolvieron más de lo que vendieron, no es «bajó»: es 0 ventas.
        self.facturar(self.despierta, 5, dias_atras=2, nota=True)
        fila = self.ver()['ZZMV DESPIERTA']
        self.assertEqual(fila['vendidas_este'], -2.0)
        self.assertEqual(fila['estado'], 'quieto',
                         'con devoluciones de sobra cuenta como sin ventas, y tiene existencias')
        # Y el porcentaje nunca baja de -100 % (antes decía -166.7 % de lo que ya no se vendía).
        self.facturar(self.enfria, 5, dias_atras=2, nota=True)
        fila = self.ver()['ZZMV ENFRIA']
        self.assertEqual((fila['estado'], fila['cambio_pct']), ('enfrio', -100.0))

    def test_los_pedidos_son_facturas_distintas(self):
        """Salir en dos facturas mueve más que salir en una sola con las mismas unidades."""
        fila = self.ver()['ZZMV SUBE']
        self.assertEqual((fila['pedidos_este'], fila['pedidos_otro']), (2, 1))
        grande = self.articulo('ZZMV GRANDE', 20)
        self.facturar(grande, 6, dias_atras=2)
        suelto = self.articulo('ZZMV SUELTO', 20)
        for dia in (2, 3, 4):
            self.facturar(suelto, 2, dias_atras=dia)
        filas = self.ver()
        self.assertEqual((filas['ZZMV GRANDE']['vendidas_este'], filas['ZZMV GRANDE']['pedidos_este']), (6.0, 1))
        self.assertEqual((filas['ZZMV SUELTO']['vendidas_este'], filas['ZZMV SUELTO']['pedidos_este']), (6.0, 3))

    def test_los_servicios_y_los_anticipos_no_cuentan(self):
        flete = self.env['product.product'].create({'name': 'ZZMV FLETE', 'type': 'service', 'list_price': 5})
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': self.hoy, 'date': self.hoy,
            'invoice_line_ids': [Command.create({'product_id': flete.id, 'quantity': 1, 'price_unit': 5,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        self.assertNotIn('ZZMV FLETE', self.ver(categoria=None, texto='ZZMV FLETE'))

    def test_la_cobertura_sale_del_ritmo_de_este_periodo(self):
        """Sube: 5 en existencia y 6 vendidas en 30 días (0.2 al día) → alcanza para 25 días. Sin ventas: no se
        calcula."""
        filas = self.ver()
        self.assertEqual(filas['ZZMV SUBE']['cobertura_dias'], 25)
        self.assertEqual(filas['ZZMV DESPIERTA']['cobertura_dias'], 50, '5 ÷ (3 ÷ 30)')
        self.assertIsNone(filas['ZZMV QUIETO']['cobertura_dias'])
        self.assertIsNone(filas['ZZMV ENFRIA']['cobertura_dias'])
        # Con 7 días el ritmo es otro: Despierta vendió 3 (hace 1 día) → 5 ÷ (3 ÷ 7) = 11.7 → 12.
        semana = self.ver(periodo='7')
        self.assertEqual(semana['ZZMV DESPIERTA']['vendidas_este'], 3.0)
        self.assertEqual(semana['ZZMV DESPIERTA']['cobertura_dias'], 12)

    # --- Las listas ------------------------------------------------------------------------------------------------

    def test_las_listas_y_sus_conteos(self):
        datos = self.datos()
        conteos = {v['clave']: v['productos'] for v in datos['vistas']}
        self.assertEqual(conteos, {'venden': 4, 'subieron': 2, 'bajaron': 1, 'enfriaron': 1, 'quietos': 1, 'todos': 6})
        nombres = {clave: {f['nombre'] for f in self.datos(vista=clave)['productos']} for clave in conteos}
        self.assertEqual(nombres['venden'], {'ZZMV SUBE', 'ZZMV BAJA', 'ZZMV IGUAL', 'ZZMV DESPIERTA'})
        self.assertEqual(nombres['subieron'], {'ZZMV SUBE', 'ZZMV DESPIERTA'}, 'los que despertaron también subieron')
        self.assertEqual(nombres['bajaron'], {'ZZMV BAJA'})
        self.assertEqual(nombres['enfriaron'], {'ZZMV ENFRIA'})
        self.assertEqual(nombres['quietos'], {'ZZMV QUIETO'})

    def test_cada_lista_viene_en_su_orden(self):
        def orden(vista, **kw):
            return [f['nombre'] for f in self.datos(vista=vista, **kw)['productos']]
        self.assertEqual(orden('venden'), ['ZZMV SUBE', 'ZZMV DESPIERTA', 'ZZMV IGUAL', 'ZZMV BAJA'])
        self.assertEqual(orden('subieron'), ['ZZMV SUBE', 'ZZMV DESPIERTA'], 'por cuánto subieron (4 y 3)')
        self.assertEqual(self.datos(vista='subieron')['orden'], 'cambio')
        self.assertEqual(self.datos(vista='bajaron')['orden'], 'baja')
        self.assertEqual(self.datos(vista='quietos')['orden'], 'dias')
        self.assertEqual(orden('todos', orden='baja')[:2], ['ZZMV BAJA', 'ZZMV ENFRIA'],
                         'lo que más bajó, primero (los dos bajaron 3: a igualdad, por nombre)')
        self.assertEqual(orden('todos', orden='antes')[:2], ['ZZMV BAJA', 'ZZMV ENFRIA'], 'vendían 4 y 3')
        self.assertEqual(orden('todos', orden='nombre'), sorted(orden('todos')))
        self.assertEqual(len(orden('todos', orden='cobertura')), 6)
        self.assertEqual(len(orden('todos', orden='dias')), 6)
        self.assertEqual(len(orden('todos', orden='capital')), 6)

    def test_categoria_texto_y_tope_de_filas(self):
        otra = self.producto('ZZMV OTRA CATEGORIA', stock=3, categoria=self.otra_categoria)
        self.facturar(otra, 5, dias_atras=1)
        todo = self.datos(categoria=None, vista='todos', texto='ZZMV')
        self.assertIn('ZZMV OTRA CATEGORIA', {f['nombre'] for f in todo['productos']})
        propia = self.datos(vista='todos')
        self.assertNotIn('ZZMV OTRA CATEGORIA', {f['nombre'] for f in propia['productos']})
        por_texto = self.datos(vista='todos', texto='sube')
        self.assertEqual([f['nombre'] for f in por_texto['productos']], ['ZZMV SUBE'])
        self.assertEqual(self.datos(vista='todos', texto='sube')['vistas'][-1]['productos'], 6,
                         'buscar un nombre no cambia los botones de la categoría')
        with self.assertRaises(UserError):
            self.datos(categoria='no-existe')
        self.assertLessEqual(len(self.datos(categoria=None, vista='todos')['productos']), 100)

    # --- El resumen y el gráfico ---------------------------------------------------------------------------------

    def test_el_resumen_compara_los_dos_periodos(self):
        resumen = self.datos()['resumen']
        # Este periodo: 6 + 1 + 2 + 3 = 12 unidades; antes: 2 + 4 + 2 + 3 = 11.
        self.assertEqual(resumen['unidades'], {'a': 12.0, 'b': 11.0, 'cambio': 1.0, 'pct': 9.1})
        self.assertEqual(resumen['productos'], {'a': 4.0, 'b': 4.0, 'cambio': 0.0, 'pct': 0.0})
        # Facturas distintas con productos de la categoría: 5 en cada periodo (una por cada venta de arriba).
        self.assertEqual(resumen['pedidos'], {'a': 5, 'b': 5, 'cambio': 0, 'pct': 0.0})
        self.assertFalse(resumen['sin_ventas_de_comparacion'])
        # Ventas sin ITBMS (a $10 la unidad).
        self.assertEqual(resumen['monto'], {'a': 120.0, 'b': 110.0, 'cambio': 10.0, 'pct': 9.1})

    def test_si_no_hubo_ventas_antes_la_pantalla_lo_dice(self):
        datos = self.datos(periodo='30', contra='fechas', contra_desde=str(self.hoy - timedelta(days=400)),
                           contra_hasta=str(self.hoy - timedelta(days=380)))
        self.assertTrue(datos['resumen']['sin_ventas_de_comparacion'])
        self.assertIsNone(datos['resumen']['unidades']['pct'])
        todos = self.datos(vista='todos', periodo='30', contra='fechas',
                           contra_desde=str(self.hoy - timedelta(days=400)),
                           contra_hasta=str(self.hoy - timedelta(days=380)))
        self.assertTrue(all(f['estado'] == 'desperto' for f in todos['productos'] if f['vendidas_este'] > 0))

    def test_el_grafico_trae_una_serie_por_periodo_del_mismo_largo(self):
        grafico = self.datos()['grafico']
        self.assertEqual(grafico['por'], 'dia')
        self.assertEqual(len(grafico['este']), 30)
        self.assertEqual(len(grafico['otro']), 30)
        self.assertEqual(grafico['fechas_este'][0], str(self.hoy - timedelta(days=29)))
        self.assertEqual(grafico['fechas_este'][-1], str(self.hoy))
        self.assertEqual(grafico['fechas_otro'][0], str(self.hoy - timedelta(days=59)))
        self.assertEqual(sum(grafico['este']), 12.0)
        self.assertEqual(sum(grafico['otro']), 11.0)
        self.assertEqual(grafico['este'][0], 4.0, 'el primer día de este periodo (29 días atrás)')
        self.assertEqual(grafico['este'][-1], 2.0, 'hoy')
        self.assertEqual(grafico['otro'][-1], 5.0, '30 días atrás: sube (2) y enfría (3)')

    def test_pasados_31_dias_el_grafico_junta_por_semanas(self):
        grafico = self.datos(periodo='90')['grafico']
        self.assertEqual(grafico['por'], 'semana')
        self.assertEqual(len(grafico['este']), 13)
        self.assertEqual(sum(grafico['este']), 33.0, 'todo lo de los últimos 90 días: las 7 facturas de la categoría')
        self.assertEqual(sum(v for v in grafico['otro'] if v is not None), 0.0, '90 a 179 días atrás: nada')

    def test_el_grafico_respeta_la_categoria(self):
        otra = self.producto('ZZMV OTRA SERIE', stock=3, categoria=self.otra_categoria)
        self.facturar(otra, 9, dias_atras=2)
        self.assertEqual(sum(self.datos()['grafico']['este']), 12.0)
        self.assertEqual(sum(self.datos(categoria=self.otra_categoria.id)['grafico']['este']), 9.0)

    def test_lo_archivado_no_entra_ni_en_pedidos_ni_en_el_grafico(self):
        """Las ventas de un producto archivado o que ya no está a la venta no entran: ni en las unidades (que salen de
        los productos de la lista) ni en los pedidos y la gráfica (que salen de las facturas). Antes solo las
        unidades lo respetaban (revisión independiente del 2026-11-22)."""
        archivado = self.articulo('ZZMV ARCHIVADO', 3)
        self.facturar(archivado, 5, dias_atras=2)
        self.assertEqual(self.datos()['resumen']['pedidos']['a'], 6)
        archivado.active = False
        datos = self.datos()
        self.assertEqual(datos['resumen']['pedidos']['a'], 5, 'la factura del archivado ya no cuenta como pedido')
        self.assertEqual(datos['resumen']['unidades']['a'], 12.0)
        self.assertEqual(sum(datos['grafico']['este']), 12.0)
        fuera = self.articulo('ZZMV FUERA DE VENTA', 3)
        self.facturar(fuera, 4, dias_atras=2)
        fuera.sale_ok = False
        self.assertEqual(self.datos()['resumen']['pedidos']['a'], 5)
        self.assertEqual(sum(self.datos()['grafico']['este']), 12.0)

    # --- Permisos --------------------------------------------------------------------------------------------------

    def test_marketing_ve_unidades_pero_no_dinero(self):
        datos = self.datos(self.marketing_rol, vista='todos', orden='capital')
        self.assertFalse(datos['con_dinero'])
        self.assertNotEqual(datos['orden'], 'capital', 'sin dinero no se ordena por capital')
        self.assertNotIn('monto', datos['resumen'])
        for fila in datos['productos']:
            for clave in ('vendido_este', 'vendido_otro', 'capital'):
                self.assertNotIn(clave, fila)
        self.assertEqual(self.fila(datos, self.sube)['vendidas_este'], 6.0)

    def test_administradores_y_gerencia_ven_el_dinero(self):
        for usuario in (self.gerencia, self.admin):
            datos = self.datos(usuario, vista='todos')
            self.assertTrue(datos['con_dinero'])
            self.assertEqual(self.fila(datos, self.sube)['vendido_este'], 60.0)
            self.assertEqual(self.fila(datos, self.sube)['vendido_otro'], 20.0)

    def test_vendedora_y_bodega_no_entran(self):
        for usuario in (self.vendedora, self.bodega):
            with self.assertRaises(AccessError):
                self.datos(usuario)
            with self.assertRaises(AccessError):
                self.env['dcasa.movimiento_productos'].with_user(usuario)._excel()

    # --- Excel -----------------------------------------------------------------------------------------------------

    def leer_excel(self, **kw):
        from openpyxl import load_workbook  # noqa: PLC0415
        kw.setdefault('categoria', self.categoria_mv.id)
        usuario = kw.pop('usuario', self.gerencia)
        nombre, contenido = self.env['dcasa.movimiento_productos'].with_user(usuario)._excel(**kw)
        return nombre, load_workbook(io.BytesIO(contenido), data_only=False)

    def test_el_excel_trae_lo_mismo_que_la_pantalla_y_un_resumen(self):
        nombre, libro = self.leer_excel(vista='todos', orden='cambio')
        self.assertEqual(nombre, f'movimiento_todos_{self.hoy - timedelta(days=29)}_{self.hoy}.xlsx')
        self.assertEqual(libro.sheetnames, ['Comparación', 'Resumen'])
        hoja = libro['Comparación']
        self.assertIn('Este periodo:', hoja['A2'].value)
        self.assertIn('Comparado con:', hoja['A2'].value)
        filas = [[celda.value for celda in fila] for fila in hoja.iter_rows(min_row=5)]
        encabezado = filas[0]
        self.assertEqual(encabezado[0], 'Producto')
        for esperado in ('Vendidas este periodo', 'Vendidas en la comparación', 'Pedidos este periodo', 'Estado',
                         'Vendido este periodo', 'Capital parado'):
            self.assertIn(esperado, encabezado)
        productos = [fila[0] for fila in filas[1:] if fila[0]]
        self.assertEqual(productos, ['ZZMV SUBE', 'ZZMV DESPIERTA', 'ZZMV IGUAL', 'ZZMV QUIETO', 'ZZMV BAJA',
                                     'ZZMV ENFRIA'], 'del que más subió al que más bajó (a igualdad, por nombre)')
        columna = encabezado.index('Cambio')
        self.assertEqual([fila[columna] for fila in filas[1:]], [4, 3, 0, 0, -3, -3])
        resumen = [[c.value for c in f] for f in libro['Resumen'].iter_rows()]
        self.assertEqual(resumen[0][:3], ['Qué se cuenta', 'Este periodo', 'Comparación'])
        self.assertEqual(resumen[1][:4], ['Unidades vendidas', 12, 11, 1])

    def test_el_excel_sin_dinero_no_trae_importes(self):
        _nombre, libro = self.leer_excel(usuario=self.marketing_rol, vista='todos')
        encabezado = [c.value for c in next(libro['Comparación'].iter_rows(min_row=5, max_row=5))]
        for prohibido in ('Vendido este periodo', 'Vendido en la comparación', 'Capital parado'):
            self.assertNotIn(prohibido, encabezado)
        self.assertEqual(libro['Comparación'].max_column, 15, 'ni una celda de más: sin las 3 columnas de dinero')
        nombres = [fila[0].value for fila in libro['Resumen'].iter_rows(min_row=2, max_row=6)]
        self.assertNotIn('Vendido sin ITBMS', nombres)

    def test_un_nombre_que_parece_formula_sale_como_texto(self):
        self.facturar(self.articulo('=SUM(A1:A9) ZZMV FORMULA', 2), 1, dias_atras=2)
        _nombre, libro = self.leer_excel(vista='todos')
        celda = next(c for fila in libro['Comparación'].iter_rows(min_row=6) for c in fila
                     if c.value and 'ZZMV FORMULA' in str(c.value))
        self.assertEqual(celda.data_type, 's')

    def test_un_nombre_con_formula_de_matriz_tambien_sale_como_texto(self):
        """``strings_to_formulas=False`` de xlsxwriter no cubre «{=...}» (revisión independiente del 2026-11-22)."""
        # Solo es fórmula de matriz si TODA la celda es «{=...}»: el nombre es justo eso.
        self.facturar(self.articulo('{=1+1}', 2), 1, dias_atras=2)
        _nombre, libro = self.leer_excel(vista='todos')
        celdas = [c for fila in libro['Comparación'].iter_rows(min_row=6) for c in fila if c.value == '{=1+1}']
        self.assertEqual(len(celdas), 1)
        self.assertEqual(celdas[0].data_type, 's', 'texto, no fórmula de matriz')
