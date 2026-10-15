"""Auditoría de los presupuestos: «presupuestado contra real» cruzado con un cálculo aparte en SQL.

Los datos son los de la auditoría de reportes (``datos_auditoria.py``: facturas pagadas, abonadas, vencidas, en borrador
y canceladas; notas de crédito de clientes y de proveedores; ventas repartidas entre dos canales). Lo real de cada línea
se compara con ``oraculo_presupuesto.py``, que lee los apuntes publicados directo de la base. Además:

* cifras calculadas a mano (papel y lápiz) que se suman a lo que la base ya tuviera;
* la variación con planeado en cero, el color por ingreso o gasto y el % de tiempo transcurrido;
* los totales separan ingresos de gastos y no cuentan dos veces el detalle por canal;
* los atajos de fechas de la lista, en sus fechas borde.
"""
from freezegun import freeze_time

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from . import oraculo_presupuesto as OP
from .test_auditoria import ANIO, HOY, VENTANAS, AuditoriaCommon, d


@tagged('post_install', '-at_install')
class TestPresupuestoContraSql(AuditoriaCommon):

    def setUp(self):
        super().setUp()
        self.Presupuesto = self.env['dcasa.presupuesto']
        datos = self.datos
        self.ingreso = datos.e1.invoice_line_ids.account_id            # ventas
        self.gasto = datos.e2.invoice_line_ids.account_id              # compras a proveedores
        self.gasto_manual = datos._gasto()                              # gastos pagados en caja

    def presupuesto(self, desde, hasta, lineas, **kw):
        """lineas: [(cuenta, planeado)] o [(cuenta, planeado, analitica)]"""
        comandos = []
        for cuenta, planeado, *analitica in lineas:
            comandos.append((0, 0, {'account_id': cuenta.id, 'monto_planeado': planeado,
                                    'analytic_account_id': analitica[0].id if analitica else False}))
        return self.Presupuesto.create({'name': f'Presupuesto {desde} a {hasta}', 'fecha_desde': desde,
                                        'fecha_hasta': hasta, 'line_ids': comandos, **kw})

    def assertCifra(self, real, esperado, msg=''):
        self.assertAlmostEqual(real, esperado, places=2, msg=f'{msg}: pantalla={real} referencia={esperado}')

    # ------------------------------------------------------------------
    # Contra el cálculo aparte
    # ------------------------------------------------------------------

    def test_lo_real_coincide_con_los_apuntes_en_cada_periodo(self):
        """9 periodos (un día, semana, mes, mes pasado, año a hoy, año, cruce de año, año anterior, mitad de mes) ×
        9 líneas: ingreso, gasto, ingreso por canal (dos canales), gasto por canal, banco, préstamo, capital,
        mobiliario."""
        d_ = self.datos
        cuentas = [(self.ingreso, None), (self.gasto, None), (self.ingreso, d_.tienda), (self.ingreso, d_.web),
                   (self.gasto_manual, d_.tienda), (d_.cuenta_banco, None), (d_.prestamo, None), (d_.capital, None),
                   (d_.mobiliario, None)]
        for nombre, (desde, hasta) in VENTANAS.items():
            presupuesto = self.presupuesto(desde, hasta, [(c, 1000.0, *([a] if a else [])) for c, a in cuentas])
            for linea, (cuenta, analitica) in zip(presupuesto.line_ids, cuentas, strict=True):
                etiqueta = f'{nombre} · {cuenta.code}' + (f' · {analitica.name}' if analitica else '')
                esperado = OP.real(self.env, self.company, cuenta, desde, hasta, analitica)
                self.assertCifra(linea.monto_real, esperado, etiqueta)
                self.assertCifra(linea.diferencia, 1000.0 - esperado, f'{etiqueta}: por ejecutar')
                self.assertAlmostEqual(linea.porcentaje, esperado / 1000.0 * 100, delta=0.051,
                                       msg=f'{etiqueta}: % ejecutado (con un decimal)')
                if analitica and cuenta.account_type == 'income':
                    # Segunda vía: las líneas analíticas que Odoo crea al publicar (otra tabla, otro camino).
                    self.assertCifra(OP.real_analitico_por_lineas(self.env, self.company, cuenta, analitica,
                                                                  desde, hasta), esperado, f'{etiqueta}: analítica')

    def test_lo_real_cifras_a_mano(self):
        """Papel y lápiz: en 2031 la base no tiene más movimientos que los de los datos de la auditoría."""
        d_ = self.datos
        # Octubre al 14: 950 + 300 + 400 + 150 de ventas; la factura en borrador (700) y la cancelada (600) NO cuentan.
        octubre = self.presupuesto(f'{ANIO}-10-01', HOY, [(self.ingreso, 5000), (self.ingreso, 5000, d_.tienda),
                                                          (self.ingreso, 5000, d_.web)])
        general, tienda, web = octubre.line_ids
        self.assertCifra(general.monto_real, 1800.0, 'ventas de octubre al 14')
        # Los canales: 60 % de 950 + 300 de la venta exenta = 870; 40 % de 950 + 400 de contado = 780.
        self.assertCifra(tienda.monto_real, 870.0, 'canal tienda física')
        self.assertCifra(web.monto_real, 780.0, 'canal tienda en línea')
        # Septiembre: 600 de una factura y una nota de crédito de 100 que RESTA.
        septiembre = self.presupuesto(f'{ANIO}-09-01', f'{ANIO}-09-30', [(self.ingreso, 500), (self.gasto, 500)])
        ventas, compras = septiembre.line_ids
        self.assertCifra(ventas.monto_real, 600.0 - 100.0, 'ventas de septiembre (la nota de crédito resta)')
        # Compras de septiembre: 500 de una factura y una nota de crédito de proveedor de 50.
        self.assertCifra(compras.monto_real, 500.0 - 50.0, 'compras de septiembre (la nota del proveedor resta)')
        # Tercer trimestre y año a hoy.
        trimestre = self.presupuesto(f'{ANIO}-07-01', f'{ANIO}-09-30', [(self.ingreso, 0)]).line_ids
        self.assertCifra(trimestre.monto_real, 1200.0 + 600.0 - 100.0, 'tercer trimestre')
        anio = self.presupuesto(f'{ANIO}-01-01', HOY, [(self.ingreso, 0), (self.gasto, 0)]).line_ids
        self.assertCifra(anio[0].monto_real, 800 + 1200 + 600 - 100 + 950 + 300 + 400 + 150, 'ventas del año a hoy')
        self.assertCifra(anio[1].monto_real, 300 + 500 - 50 + 200 + 80, 'compras del año a hoy (sin el borrador de 90)')
        # Periodo parcial: el mismo gasto en caja con el corte el 14 y con el mes completo (hay uno fechado el 20).
        parcial = self.presupuesto(f'{ANIO}-10-01', HOY, [(self.gasto_manual, 0)]).line_ids
        completo = self.presupuesto(f'{ANIO}-10-01', f'{ANIO}-10-31', [(self.gasto_manual, 0)]).line_ids
        self.assertCifra(completo.monto_real - parcial.monto_real, 100.0, 'el gasto del 20 solo entra al mes completo')
        self.assertCifra(parcial.monto_real, 120.0 + 0.0, 'gasto en caja del 13 de octubre')

    def test_borradores_y_cancelados_no_cuentan(self):
        presupuesto = self.presupuesto(f'{ANIO}-10-01', HOY, [(self.ingreso, 0)])
        sin = presupuesto.line_ids.monto_real
        self.datos.factura(self.datos.c1, 123, f'{ANIO}-10-12', publicar=False)         # borrador
        otra = self.datos.factura(self.datos.c1, 321, f'{ANIO}-10-12')                    # publicada y luego cancelada
        otra.button_draft()
        otra.button_cancel()
        presupuesto.invalidate_recordset()
        self.assertCifra(presupuesto.line_ids.monto_real, sin, 'ni borradores ni cancelados')
        # El cálculo aparte SÍ ve los borradores: la diferencia es justo lo que no debe contar (el borrador de 700 de
        # los datos de la auditoría y el de 123 de aquí).
        self.assertCifra(OP.real(self.env, self.company, self.ingreso, f'{ANIO}-10-01', HOY, borradores=True) - sin,
                         700.0 + 123.0, 'lo que quedó fuera')

    def test_un_cambio_en_los_asientos_se_nota_al_volver_a_leer(self):
        presupuesto = self.presupuesto(f'{ANIO}-10-01', HOY, [(self.ingreso, 0)])
        antes = presupuesto.line_ids.monto_real
        self.datos.factura(self.datos.c2, 77, f'{ANIO}-10-12')
        self.env.invalidate_all()        # otra petición: el real no se guarda, se calcula al leer
        self.assertCifra(presupuesto.line_ids.monto_real - antes, 77.0, 'una venta nueva suma')

    # ------------------------------------------------------------------
    # Variación con planeado en cero, color y totales
    # ------------------------------------------------------------------

    def test_planeado_en_cero_no_inventa_un_porcentaje(self):
        presupuesto = self.presupuesto(f'{ANIO}-10-01', HOY, [(self.ingreso, 0), (self.datos.depreciacion, 0)])
        con_movimiento, sin_movimiento = presupuesto.line_ids
        self.assertGreater(con_movimiento.monto_real, 0)
        self.assertEqual(con_movimiento.situacion, 'sin_plan')
        self.assertCifra(con_movimiento.diferencia, -con_movimiento.monto_real, 'por ejecutar')
        self.assertEqual(con_movimiento.porcentaje, 0.0)
        self.assertEqual(sin_movimiento.monto_real, 0.0)
        self.assertEqual(sin_movimiento.situacion, 'sin_movimiento')

    def test_un_ingreso_arriba_de_lo_planeado_es_bueno_y_un_gasto_arriba_es_malo(self):
        # Ventas de octubre al 14: 1800. Compras: 200 + 80 = 280.
        def situaciones(planeado_ingreso, planeado_gasto):
            presupuesto = self.presupuesto(f'{ANIO}-10-01', HOY, [(self.ingreso, planeado_ingreso),
                                                                  (self.gasto, planeado_gasto)])
            return tuple(presupuesto.line_ids.mapped('situacion'))

        self.assertEqual(situaciones(1500, 200), ('cumplido', 'excedido'))       # me pasé en los dos
        self.assertEqual(situaciones(2000, 300), ('en_camino', 'dentro'))        # me quedé corto en los dos
        self.assertEqual(situaciones(1800, 280), ('cumplido', 'dentro'))         # justo en el límite
        presupuesto = self.presupuesto(f'{ANIO}-10-01', HOY, [(self.ingreso, 1500), (self.gasto, 200)])
        ingreso, gasto = presupuesto.line_ids
        self.assertCifra(ingreso.diferencia, -300.0, 'ingreso: superó la meta por 300')
        self.assertCifra(gasto.diferencia, -80.0, 'gasto: se pasó por 80')
        self.assertCifra(ingreso.porcentaje, 120.0, '% de la meta de ventas')
        self.assertCifra(gasto.porcentaje, 140.0, '% del tope de gastos')

    def test_los_totales_separan_ingresos_de_gastos_y_no_cuentan_el_detalle_dos_veces(self):
        d_ = self.datos
        presupuesto = self.presupuesto(f'{ANIO}-10-01', HOY, [
            (self.ingreso, 2000), (self.ingreso, 1000, d_.tienda), (self.gasto, 300), (d_.cuenta_banco, 100)])
        general, tienda, gasto, banco = presupuesto.line_ids
        self.assertEqual(tienda.es_detalle, True)
        self.assertEqual((general.es_detalle, gasto.es_detalle, banco.es_detalle), (False, False, False))
        self.assertEqual((general.naturaleza, gasto.naturaleza, banco.naturaleza), ('ingreso', 'gasto', 'balance'))
        self.assertCifra(presupuesto.ingresos_planeado, 2000.0, 'el detalle por canal no se suma otra vez')
        self.assertCifra(presupuesto.ingresos_real, general.monto_real, 'ingresos reales')
        self.assertCifra(presupuesto.gastos_planeado, 300.0, 'gastos planeados')
        self.assertCifra(presupuesto.gastos_real, gasto.monto_real, 'gastos reales')
        self.assertCifra(presupuesto.resultado_planeado, 2000.0 - 300.0, 'resultado planeado')
        self.assertCifra(presupuesto.resultado_real, general.monto_real - gasto.monto_real, 'resultado real')
        self.assertTrue(presupuesto.aviso)
        # Sin la línea general, el canal ya no es un detalle y sí suma.
        general.unlink()
        self.assertFalse(tienda.es_detalle)
        self.assertCifra(presupuesto.ingresos_planeado, 1000.0)
        self.assertFalse(presupuesto.aviso)

    def test_los_totales_contra_el_estado_de_resultados(self):
        """Un presupuesto con TODAS las cuentas de resultados del periodo suma lo mismo que el Estado de resultados."""
        desde, hasta = f'{ANIO}-01-01', HOY
        resultados = self.reportes.estado_resultados(desde, hasta)
        cuentas = self.env['account.account']
        for seccion in resultados['secciones']:
            cuentas |= self.env['account.account'].browse([f['id'] for f in seccion['filas'] if f['id']])
        presupuesto = self.presupuesto(desde, hasta, [(c, 0) for c in cuentas])
        self.assertCifra(presupuesto.resultado_real, resultados['resumen']['utilidad_neta'], 'utilidad neta')

    def test_la_misma_cuenta_dos_veces_no_se_permite_pero_con_otra_analitica_si(self):
        d_ = self.datos
        presupuesto = self.presupuesto(f'{ANIO}-10-01', HOY, [(self.ingreso, 100), (self.ingreso, 50, d_.tienda),
                                                              (self.ingreso, 50, d_.web)])
        with self.assertRaises(ValidationError) as error:
            presupuesto.write({'line_ids': [(0, 0, {'account_id': self.ingreso.id, 'monto_planeado': 5})]})
        self.assertIn('ya está en este presupuesto', str(error.exception))
        with self.assertRaises(ValidationError):
            presupuesto.write({'line_ids': [(0, 0, {'account_id': self.ingreso.id, 'monto_planeado': 5,
                                                    'analytic_account_id': d_.web.id})]})

    def test_tiempo_transcurrido(self):
        with freeze_time(f'{ANIO}-10-14 15:00:00'):          # martes 14, 10 a. m. en Panamá
            octubre = self.presupuesto(f'{ANIO}-10-01', f'{ANIO}-10-31', [])
            # Se muestra sin decimales (45 %): 14 de 31 días son 45.16 %.
            self.assertAlmostEqual(octubre.avance_tiempo, 14 / 31 * 100, delta=0.5, msg='octubre: 14 de 31 días')
            self.assertEqual(self.presupuesto(f'{ANIO}-10-14', f'{ANIO}-10-14', []).avance_tiempo, 100.0, 'hoy solo')
            self.assertEqual(self.presupuesto(f'{ANIO}-10-15', f'{ANIO}-10-31', []).avance_tiempo, 0.0,
                             'aún no empieza')
            self.assertEqual(self.presupuesto(f'{ANIO}-01-01', f'{ANIO}-09-30', []).avance_tiempo, 100.0, 'ya pasó')
            anio = self.presupuesto(f'{ANIO}-01-01', f'{ANIO}-12-31', [])
            self.assertAlmostEqual(anio.avance_tiempo, 287 / 365 * 100, delta=0.5,
                                   msg='el año: el 14 de octubre es el día 287 de 365')
        with freeze_time(f'{ANIO}-10-15 02:00:00'):          # 9 p. m. del 14 en Panamá, ya es 15 en UTC
            self.assertEqual(self.presupuesto(f'{ANIO}-10-15', f'{ANIO}-10-31', []).avance_tiempo, 0.0,
                             'sigue siendo el 14 en Panamá')


@tagged('post_install', '-at_install')
class TestPresupuestoMulticompania(AuditoriaCommon):
    """Un presupuesto lee solo los apuntes de su empresa, aunque haya varias activas a la vez."""

    def test_cada_presupuesto_cuenta_lo_de_su_empresa(self):
        usd = self.env.ref('base.USD')
        otra = self.env['res.company'].create({'name': 'Zona Libre Presupuesto SA', 'currency_id': usd.id})
        self.env['account.chart.template'].try_loading('pa', otra, install_demo=False)
        otra.currency_id = usd
        cuentas = self.env['account.account'].with_company(otra)
        cxc = cuentas.search([('account_type', '=', 'asset_receivable'), ('company_ids', 'in', otra.ids)], limit=1)
        ventas = cuentas.search([('account_type', '=', 'income'), ('company_ids', 'in', otra.ids)], limit=1)
        diario = self.env['account.journal'].search([('company_id', '=', otra.id), ('type', '=', 'general')], limit=1)
        self.env['account.move'].with_company(otra).create({
            'move_type': 'entry', 'company_id': otra.id, 'journal_id': diario.id, 'date': f'{ANIO}-10-12',
            'line_ids': [(0, 0, {'account_id': cxc.id, 'debit': 999, 'name': 'otra empresa',
                                 'partner_id': self.datos.c1.id}),
                         (0, 0, {'account_id': ventas.id, 'credit': 999, 'name': 'otra empresa'})]}).action_post()
        Presupuesto = self.env['dcasa.presupuesto'].with_context(allowed_company_ids=[self.company.id, otra.id])
        ingreso_a = self.datos.e1.invoice_line_ids.account_id
        de_a = Presupuesto.create({'name': 'A', 'fecha_desde': f'{ANIO}-10-01', 'fecha_hasta': HOY,
                                   'company_id': self.company.id,
                                   'line_ids': [(0, 0, {'account_id': ingreso_a.id, 'monto_planeado': 1})]})
        de_b = Presupuesto.create({'name': 'B', 'fecha_desde': f'{ANIO}-10-01', 'fecha_hasta': HOY,
                                   'company_id': otra.id,
                                   'line_ids': [(0, 0, {'account_id': ventas.id, 'monto_planeado': 1})]})
        self.assertEqual(de_a.line_ids.monto_real, 1800.0)
        self.assertEqual(de_b.line_ids.monto_real, 999.0)
        self.assertEqual(OP.real(self.env, otra, ventas, f'{ANIO}-10-01', HOY), 999.0)


@tagged('post_install', '-at_install')
class TestPresupuestoAtajosDeFechas(AuditoriaCommon):
    """Los filtros «Hoy … Este año fiscal» de la lista de presupuestos, en sus fechas borde."""

    HOY = f'{ANIO}-10-14'        # martes

    PRESUPUESTOS = {
        # nombre: (desde, hasta, atajos que toca; «todos terminan hoy» salvo «mes_pasado»)
        'hoy_exacto': (f'{ANIO}-10-14', f'{ANIO}-10-14',
                       {'hoy', 'semana', 'quincena', 'mes', 'trimestre', 'ejercicio'}),
        'ayer_lunes': (f'{ANIO}-10-13', f'{ANIO}-10-13', {'semana', 'quincena', 'mes', 'trimestre', 'ejercicio'}),
        'domingo_pasado': (f'{ANIO}-10-12', f'{ANIO}-10-12', {'quincena', 'mes', 'trimestre', 'ejercicio'}),
        'manana_en_adelante': (f'{ANIO}-10-15', f'{ANIO}-10-31', set()),
        'primero_de_octubre': (f'{ANIO}-10-01', f'{ANIO}-10-01', {'quincena', 'mes', 'trimestre', 'ejercicio'}),
        'septiembre': (f'{ANIO}-09-01', f'{ANIO}-09-30', {'mes_pasado', 'ejercicio'}),
        'ultimo_de_septiembre': (f'{ANIO}-09-30', f'{ANIO}-09-30', {'mes_pasado', 'ejercicio'}),
        'primero_de_septiembre': (f'{ANIO}-09-01', f'{ANIO}-09-01', {'mes_pasado', 'ejercicio'}),
        'agosto': (f'{ANIO}-08-01', f'{ANIO}-08-31', {'ejercicio'}),
        'todo_el_anio': (f'{ANIO}-01-01', f'{ANIO}-12-31', {'hoy', 'semana', 'quincena', 'mes', 'mes_pasado',
                                                            'trimestre', 'ejercicio'}),
        'primero_de_enero': (f'{ANIO}-01-01', f'{ANIO}-01-01', {'ejercicio'}),
        'ultimo_del_anio_anterior': (f'{ANIO - 1}-12-31', f'{ANIO - 1}-12-31', set()),
        'de_diciembre_a_enero': (f'{ANIO - 1}-12-15', f'{ANIO}-01-02', {'ejercicio'}),
    }

    def setUp(self):
        super().setUp()
        self.Presupuesto = self.env['dcasa.presupuesto']
        self.creados = {n: self.Presupuesto.create({'name': n, 'fecha_desde': desde, 'fecha_hasta': hasta})
                        for n, (desde, hasta, _t) in self.PRESUPUESTOS.items()}

    def buscar(self, dominio):
        return set(self.Presupuesto.search([('id', 'in', [p.id for p in self.creados.values()])] + dominio
                                           ).mapped('name'))

    def test_cada_atajo_muestra_los_presupuestos_que_toca(self):
        with freeze_time(f'{self.HOY} 15:00:00'):
            for clave, nombre in (('hoy', 'Hoy'), ('semana', 'Esta semana'), ('quincena', 'Esta quincena'),
                                  ('mes', 'Este mes'), ('mes_pasado', 'Mes pasado'), ('trimestre', 'Este trimestre'),
                                  ('ejercicio', 'Este año fiscal')):
                esperado = {n for n, (_d, _h, toca) in self.PRESUPUESTOS.items() if clave in toca}
                self.assertEqual(self.buscar([('periodo_atajo', '=', clave)]), esperado, nombre)

    def test_varios_atajos_a_la_vez_suman(self):
        with freeze_time(f'{self.HOY} 15:00:00'):
            esperado = {n for n, (_d, _h, toca) in self.PRESUPUESTOS.items() if toca & {'hoy', 'mes_pasado'}}
            self.assertEqual(self.buscar([('periodo_atajo', 'in', ['hoy', 'mes_pasado'])]), esperado)
            self.assertEqual(self.buscar([('periodo_atajo', 'in', [])]), set())
            with self.assertRaises(UserError):
                self.buscar([('periodo_atajo', '!=', 'hoy')])

    def test_el_dia_cambia_en_panama_no_en_utc(self):
        """A las 9 p. m. del 14 en Panamá ya es el 15 en UTC: «Hoy» sigue siendo el 14."""
        with freeze_time(f'{ANIO}-10-15 02:00:00'):
            self.assertEqual(self.buscar([('periodo_atajo', '=', 'hoy')]),
                             {n for n, (_d, _h, toca) in self.PRESUPUESTOS.items() if 'hoy' in toca})

    def test_semana_que_cruza_de_mes_y_trimestre_con_otro_cierre_fiscal(self):
        """Jueves 2 de enero de 2031: la semana empezó el lunes 30 de diciembre de 2030 (otro mes y otro año)."""
        with freeze_time(f'{ANIO}-01-02 15:00:00'):
            diciembre = self.Presupuesto.create({'name': 'fin de año', 'fecha_desde': f'{ANIO - 1}-12-30',
                                                 'fecha_hasta': f'{ANIO - 1}-12-30'})
            antes = self.Presupuesto.create({'name': 'domingo', 'fecha_desde': f'{ANIO - 1}-12-29',
                                             'fecha_hasta': f'{ANIO - 1}-12-29'})
            encontrados = self.Presupuesto.search([('periodo_atajo', '=', 'semana'),
                                                   ('id', 'in', (diciembre | antes).ids)])
            self.assertEqual(encontrados, diciembre)
        # Año fiscal de julio a junio: el trimestre de octubre empieza el 1 de octubre.
        self.company.write({'fiscalyear_last_day': 30, 'fiscalyear_last_month': '6'})
        with freeze_time(f'{self.HOY} 15:00:00'):
            self.assertEqual(self.buscar([('periodo_atajo', '=', 'ejercicio')]),
                             {n for n, (_d, h, _t) in self.PRESUPUESTOS.items() if h >= f'{ANIO}-07-01'
                              and self.PRESUPUESTOS[n][0] <= self.HOY})

    def test_la_lista_tiene_los_siete_filtros_con_los_nombres_de_siempre(self):
        vista = self.Presupuesto.get_view(self.env.ref('dcasa_contabilidad.presupuesto_search').id, 'search')
        arch = vista['arch']
        for clave, nombre in (('hoy', 'Hoy'), ('semana', 'Esta semana'), ('quincena', 'Esta quincena'),
                              ('mes', 'Este mes'), ('mes_pasado', 'Mes pasado'), ('trimestre', 'Este trimestre'),
                              ('ejercicio', 'Este año fiscal')):
            self.assertIn(f'name="periodo_{clave}"', arch)
            self.assertIn(f'string="{nombre}"', arch)
            self.assertIn(f"[(&quot;periodo_atajo&quot;, &quot;=&quot;, &quot;{clave}&quot;)]".replace('&quot;', "'"),
                          arch.replace('&quot;', "'"))
        self.assertEqual(d(self.HOY).weekday(), 1, 'el 14 de octubre de ese año es martes')
