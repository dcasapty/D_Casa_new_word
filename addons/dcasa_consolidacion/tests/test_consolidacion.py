from markupsafe import escape
from psycopg2.errors import CheckViolation, UniqueViolation

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.service.model import get_public_method
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import DESDE, HASTA, ConsolidacionCommon


@tagged('post_install', '-at_install')
class TestConsolidacion(ConsolidacionCommon):

    # ------------------------------------------------------------------
    # Ayudas
    # ------------------------------------------------------------------

    def assertConsolidadoEsLaSuma(self, consolidacion, campo='importe'):
        """Consolidado = suma de las empresas + eliminaciones, fila por fila."""
        tabla = self.tabla(consolidacion, campo)
        self.assertTrue(tabla)
        for fila, columnas in tabla.items():
            esperado = sum(valor for columna, valor in columnas.items() if columna != 'consolidado')
            self.assertAlmostEqual(columnas['consolidado'], esperado, places=2, msg=f'{fila}: {columnas}')

    def assertEmpresaIgualAlMotor(self, consolidacion, empresa):
        """La columna de la empresa es lo que da dcasa.reporte.contable para esa empresa sola."""
        if consolidacion.tipo_reporte == 'comprobacion':
            datos = self.motor_de(empresa, 'balance_comprobacion', desde=DESDE, hasta=HASTA)
            esperado = {f['codigo'] or f['nombre']: (f['inicial'], f['debe'], f['haber'], f['final'])
                        for f in datos['filas']}
            lineas = consolidacion.linea_ids.filtered(
                lambda ln: ln.tipo_columna == 'empresa' and ln.columna == empresa.name)
            obtenido = {ln.codigo or ln.nombre: (ln.inicial, ln.debe, ln.haber, ln.importe) for ln in lineas}
            self.assertEqual(set(obtenido), set(esperado), f'Filas de {empresa.name}')
            for fila, valores in esperado.items():
                campos = zip(('inicial', 'debe', 'haber', 'final'), valores, obtenido[fila], strict=True)
                for campo, monto, calculado in campos:
                    self.assertAlmostEqual(calculado, monto, places=2, msg=f'{empresa.name} {fila} {campo}')
            return
        if consolidacion.tipo_reporte == 'resultados':
            datos = self.motor_de(empresa, 'estado_resultados', desde=DESDE, hasta=HASTA)
            esperado = {(s['clave'], f['codigo']): f['monto'] for s in datos['secciones'] for f in s['filas']}
        else:
            datos = self.motor_de(empresa, 'balance_general', hasta=HASTA)
            esperado = {(s['clave'], f['codigo'] or f['nombre']): f['monto'] for s in datos['secciones']
                        for f in s['filas']}
        obtenido = {fila: columnas[empresa.name] for fila, columnas in self.tabla(consolidacion).items()
                    if empresa.name in columnas}
        self.assertEqual(set(obtenido), set(esperado), f'Filas de {empresa.name}')
        for fila, monto in esperado.items():
            self.assertAlmostEqual(obtenido[fila], monto, places=2, msg=f'{empresa.name} {fila}')

    # ------------------------------------------------------------------
    # Invariante: sin eliminaciones, Consolidado = suma de cada empresa = motor de cada empresa
    # ------------------------------------------------------------------

    def test_estado_de_resultados_suma_las_empresas(self):
        consolidacion = self.consolidacion('resultados')
        self.assertEqual(consolidacion.estado, 'calculada')
        tabla = self.tabla(consolidacion)
        ventas = tabla[('ventas', self.cuenta(self.empresa_a, 'income').code)]
        # A: 1000 en marzo (el borrador de 777 no cuenta); B: 500. Lo de otros meses no entra.
        self.assertAlmostEqual(ventas[self.empresa_a.name], 1000.0)
        self.assertAlmostEqual(ventas[self.empresa_b.name], 500.0)
        self.assertAlmostEqual(ventas['consolidado'], 1500.0)
        self.assertFalse(consolidacion.linea_ids.filtered(lambda ln: ln.tipo_columna == 'eliminaciones'))
        self.assertFalse(consolidacion.advertencias)
        self.assertConsolidadoEsLaSuma(consolidacion)
        for empresa in self.grupo:
            self.assertEmpresaIgualAlMotor(consolidacion, empresa)
        # La utilidad neta consolidada: (1000 − 300) + (500 − 120)
        self.assertAlmostEqual(consolidacion.utilidad_neta, 1080.0)

    def test_balance_general_suma_las_empresas_y_cuadra(self):
        consolidacion = self.consolidacion('balance')
        tabla = self.tabla(consolidacion)
        nombres = {fila[1] for fila in tabla}
        self.assertIn('Resultados de ejercicios anteriores', nombres)  # el 2029 de A y de B pasa al patrimonio
        self.assertIn('Resultado del ejercicio', nombres)
        self.assertFalse(consolidacion.linea_ids.filtered(lambda ln: ln.tipo_columna == 'eliminaciones'))
        self.assertConsolidadoEsLaSuma(consolidacion)
        for empresa in self.grupo:
            self.assertEmpresaIgualAlMotor(consolidacion, empresa)
        self.assertTrue(consolidacion.cuadra)
        self.assertAlmostEqual(consolidacion.diferencia, 0.0)
        # Activo = pasivo + patrimonio también columna por columna (cada empresa cuadra sola).
        matriz = consolidacion._matriz()
        activo, pasivo_patrimonio, diferencia = (fila['valores'] for fila in matriz['resumen'])
        self.assertEqual(activo, pasivo_patrimonio)
        self.assertTrue(all(v == 0 for v in diferencia))

    def test_balance_de_comprobacion_suma_las_empresas(self):
        consolidacion = self.consolidacion('comprobacion')
        for campo in ('importe', 'inicial', 'debe', 'haber'):
            self.assertConsolidadoEsLaSuma(consolidacion, campo)
        for empresa in self.grupo:
            self.assertEmpresaIgualAlMotor(consolidacion, empresa)
        nombres = {fila[1] for fila in self.tabla(consolidacion)}
        self.assertIn('Resultados no asignados de ejercicios anteriores', nombres)
        consolidado = consolidacion.linea_ids.filtered(lambda ln: ln.tipo_columna == 'consolidado')
        self.assertAlmostEqual(sum(consolidado.mapped('debe')), sum(consolidado.mapped('haber')))
        self.assertAlmostEqual(sum(consolidado.mapped('importe')), 0.0)  # todo el mayor, con el patrimonio
        self.assertTrue(consolidacion.cuadra)

    # ------------------------------------------------------------------
    # Eliminaciones entre empresas
    # ------------------------------------------------------------------

    def test_elimina_por_cobrar_y_por_pagar_entre_empresas(self):
        sin_ventas = self.consolidacion('balance')
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0)
        consolidacion = self.consolidacion('balance')
        tabla, antes = self.tabla(consolidacion), self.tabla(sin_ventas)
        cxc = ('activo_corriente', self.cuenta(self.empresa_a, 'asset_receivable').code)
        cxp = ('pasivo_corriente', self.cuenta(self.empresa_a, 'liability_payable').code)
        self.assertAlmostEqual(tabla[cxc]['eliminaciones'], -1000.0)
        self.assertAlmostEqual(tabla[cxp]['eliminaciones'], -1000.0)
        # Cada empresa sigue mostrando lo suyo (A cobra 1000 más; B debe 1000 más)...
        self.assertAlmostEqual(tabla[cxc][self.empresa_a.name] - antes[cxc][self.empresa_a.name], 1000.0)
        self.assertAlmostEqual(tabla[cxp][self.empresa_b.name] - antes[cxp][self.empresa_b.name], 1000.0)
        # ...pero el consolidado no cuenta dos veces lo que se hacen entre ellas.
        self.assertAlmostEqual(tabla[cxc]['consolidado'], antes[cxc]['consolidado'])
        self.assertAlmostEqual(tabla[cxp]['consolidado'], antes[cxp]['consolidado'])
        self.assertConsolidadoEsLaSuma(consolidacion)
        self.assertFalse(consolidacion.advertencias)
        self.assertTrue(consolidacion.cuadra)
        for empresa in self.grupo:
            self.assertEmpresaIgualAlMotor(consolidacion, empresa)

    def test_elimina_ingresos_y_gastos_entre_empresas(self):
        sin_ventas = self.consolidacion('resultados')
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0)
        consolidacion = self.consolidacion('resultados')
        tabla, antes = self.tabla(consolidacion), self.tabla(sin_ventas)
        ventas = ('ventas', self.cuenta(self.empresa_a, 'income').code)
        gastos = ('gastos', self.cuenta(self.empresa_a, 'expense').code)
        self.assertAlmostEqual(tabla[ventas]['eliminaciones'], -1000.0)
        self.assertAlmostEqual(tabla[gastos]['eliminaciones'], -1000.0)
        self.assertAlmostEqual(tabla[ventas][self.empresa_a.name], antes[ventas][self.empresa_a.name] + 1000.0)
        self.assertAlmostEqual(tabla[gastos][self.empresa_b.name], antes[gastos][self.empresa_b.name] + 1000.0)
        self.assertAlmostEqual(tabla[ventas]['consolidado'], antes[ventas]['consolidado'])
        self.assertAlmostEqual(tabla[gastos]['consolidado'], antes[gastos]['consolidado'])
        # Quitar ingreso y gasto por igual no cambia la utilidad.
        self.assertAlmostEqual(consolidacion.utilidad_neta, sin_ventas.utilidad_neta)
        self.assertFalse(consolidacion.advertencias)
        self.assertConsolidadoEsLaSuma(consolidacion)

    def test_el_tercero_de_la_propia_empresa_no_se_elimina(self):
        """«Entre empresas» es contra OTRA empresa del grupo: la ficha de la propia empresa no cuenta."""
        self.asiento(self.empresa_a, '2030-03-17', [
            (self.cuenta(self.empresa_a, 'asset_receivable'), 100, 0, self.empresa_a.partner_id),
            (self.cuenta(self.empresa_a, 'income'), 0, 100, self.empresa_a.partner_id)])
        for tipo in ('resultados', 'balance', 'comprobacion'):
            consolidacion = self.consolidacion(tipo)
            self.assertFalse(consolidacion.linea_ids.filtered(lambda ln: ln.tipo_columna == 'eliminaciones'), tipo)
            self.assertFalse(consolidacion.advertencias, tipo)

    def test_la_tabla_dinamica_suma_el_consolidado(self):
        """En la tabla dinámica (sin la columna «Consolidado») el total de cada cuenta ES el consolidado."""
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0, pagar=900.0)
        for tipo in ('resultados', 'balance'):
            consolidacion = self.consolidacion(tipo)
            consolidado = {ln.cuenta: ln.importe for ln in consolidacion.linea_ids
                           if ln.tipo_columna == 'consolidado'}
            grupos = self.env['dcasa.consolidacion.linea']._read_group(
                [('consolidacion_id', '=', consolidacion.id), ('tipo_columna', '!=', 'consolidado')],
                ['cuenta'], ['importe:sum'])
            self.assertEqual({cuenta for cuenta, _total in grupos}, set(consolidado))
            for cuenta, total in grupos:
                self.assertAlmostEqual(total, consolidado[cuenta], places=2, msg=f'{tipo} {cuenta}')

    def test_comprobacion_con_eliminaciones_cuadra(self):
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0)
        consolidacion = self.consolidacion('comprobacion')
        eliminaciones = consolidacion.linea_ids.filtered(lambda ln: ln.tipo_columna == 'eliminaciones')
        self.assertEqual(len(eliminaciones), 4)  # por cobrar, por pagar, ventas y gastos
        for campo in ('importe', 'inicial', 'debe', 'haber'):
            self.assertConsolidadoEsLaSuma(consolidacion, campo)
        consolidado = consolidacion.linea_ids.filtered(lambda ln: ln.tipo_columna == 'consolidado')
        self.assertAlmostEqual(sum(consolidado.mapped('debe')), sum(consolidado.mapped('haber')))
        self.assertAlmostEqual(sum(eliminaciones.mapped('debe')), sum(eliminaciones.mapped('haber')))
        self.assertTrue(consolidacion.cuadra)
        self.assertFalse(consolidacion.advertencias)
        for empresa in self.grupo:
            self.assertEmpresaIgualAlMotor(consolidacion, empresa)

    def test_elimina_tambien_lo_de_periodos_anteriores(self):
        """Una venta entre empresas de febrero sigue abierta en marzo: el balance y el saldo inicial de la
        comprobación la eliminan; el estado de resultados de marzo (solo marzo) no tiene nada que eliminar."""
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0, fecha='2030-02-20')
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 400.0, fecha='2029-11-10')  # año anterior
        resultados = self.consolidacion('resultados')
        self.assertFalse(resultados.linea_ids.filtered(lambda ln: ln.tipo_columna == 'eliminaciones'))
        balance = self.consolidacion('balance')
        eliminaciones = balance.linea_ids.filtered(lambda ln: ln.tipo_columna == 'eliminaciones')
        self.assertEqual(sorted(eliminaciones.mapped('importe')), [-1400.0, -1400.0])  # por cobrar y por pagar
        self.assertTrue(balance.cuadra)
        self.assertFalse(balance.advertencias)
        comprobacion = self.consolidacion('comprobacion')
        cobrar = comprobacion.linea_ids.filtered(
            lambda ln: ln.tipo_columna == 'eliminaciones' and ln.seccion == 'activo_corriente')
        self.assertAlmostEqual(cobrar.inicial, -1400.0)
        self.assertAlmostEqual(cobrar.debe, 0.0)
        self.assertAlmostEqual(cobrar.importe, -1400.0)
        self.assertTrue(comprobacion.cuadra)
        self.assertFalse(comprobacion.advertencias)
        for empresa in self.grupo:
            self.assertEmpresaIgualAlMotor(comprobacion, empresa)
            self.assertEmpresaIgualAlMotor(balance, empresa)

    def test_facturas_reales_entre_empresas(self):
        """Una factura de A a B y la factura de proveedor de B a A se eliminan sin tocar las demás cifras."""
        sin_facturas = self.consolidacion('balance')
        factura = self.env['account.move'].with_company(self.empresa_a).create({
            'move_type': 'out_invoice', 'company_id': self.empresa_a.id, 'partner_id': self.empresa_b.partner_id.id,
            'invoice_date': '2030-03-12', 'date': '2030-03-12',
            'invoice_line_ids': [Command.create({'name': 'Muebles', 'quantity': 1, 'price_unit': 250.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        compra = self.env['account.move'].with_company(self.empresa_b).create({
            'move_type': 'in_invoice', 'company_id': self.empresa_b.id, 'partner_id': self.empresa_a.partner_id.id,
            'invoice_date': '2030-03-12', 'date': '2030-03-12',
            'invoice_line_ids': [Command.create({'name': 'Muebles', 'quantity': 1, 'price_unit': 250.0,
                                                 'tax_ids': [Command.clear()]})]})
        compra.action_post()
        balance = self.consolidacion('balance')
        eliminaciones = balance.linea_ids.filtered(lambda ln: ln.tipo_columna == 'eliminaciones')
        self.assertEqual(sorted(eliminaciones.mapped('importe')), [-250.0, -250.0])
        self.assertFalse(balance.advertencias)
        self.assertTrue(balance.cuadra)
        for fila, columnas in self.tabla(balance).items():  # las demás cuentas no cambian
            if 'eliminaciones' not in columnas:
                self.assertAlmostEqual(columnas['consolidado'], self.tabla(sin_facturas)[fila]['consolidado'], places=2)
        resultados = self.consolidacion('resultados')
        self.assertEqual(sorted(resultados.linea_ids.filtered(lambda ln: ln.tipo_columna == 'eliminaciones')
                                .mapped('importe')), [-250.0, -250.0])
        self.assertFalse(resultados.advertencias)

    # ------------------------------------------------------------------
    # Descuadres: se avisan, no se esconden ni se arreglan
    # ------------------------------------------------------------------

    def test_descuadre_de_por_cobrar_y_por_pagar_se_avisa(self):
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0, pagar=900.0)
        consolidacion = self.consolidacion('balance')
        dinero = self.empresa_a.currency_id
        self.assertIn(f'Descuadre entre {self.empresa_a.name} y {self.empresa_b.name} de {dinero.format(100.0)}',
                      consolidacion.advertencias)
        tabla = self.tabla(consolidacion)
        # Cada lado se elimina por su propio importe: nada se arregla a escondidas...
        self.assertAlmostEqual(tabla[('activo_corriente', self.cuenta(self.empresa_a, 'asset_receivable').code)]
                               ['eliminaciones'], -1000.0)
        self.assertAlmostEqual(tabla[('pasivo_corriente', self.cuenta(self.empresa_a, 'liability_payable').code)]
                               ['eliminaciones'], -900.0)
        # ...y el balance consolidado lo muestra: no cuadra por esos 100.
        self.assertFalse(consolidacion.cuadra)
        self.assertAlmostEqual(consolidacion.diferencia, -100.0)
        self.assertConsolidadoEsLaSuma(consolidacion)

    def test_descuadre_de_ingresos_y_gastos_se_avisa(self):
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0, pagar=900.0)
        consolidacion = self.consolidacion('resultados')
        dinero = self.empresa_a.currency_id
        self.assertIn(f'Descuadre entre {self.empresa_a.name} y {self.empresa_b.name} de {dinero.format(100.0)}',
                      consolidacion.advertencias)
        self.assertIn('requiere contador', consolidacion.advertencias)
        tabla = self.tabla(consolidacion)
        self.assertAlmostEqual(tabla[('ventas', self.cuenta(self.empresa_a, 'income').code)]['eliminaciones'], -1000.0)
        self.assertAlmostEqual(tabla[('gastos', self.cuenta(self.empresa_a, 'expense').code)]['eliminaciones'], -900.0)
        # Utilidad: lo de cada empresa menos 1000 de ingresos y 900 de gastos eliminados (100 menos, a la vista).
        suma_de_empresas = 1080.0 + 1000.0 - 900.0
        self.assertAlmostEqual(consolidacion.utilidad_neta, suma_de_empresas - 100.0)

    def test_no_avisa_si_cuadra_en_los_dos_sentidos(self):
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0)
        self.venta_entre_empresas(self.empresa_b, self.empresa_a, 300.0)
        for tipo in ('resultados', 'balance', 'comprobacion'):
            consolidacion = self.consolidacion(tipo)
            self.assertFalse(consolidacion.advertencias, tipo)

    def test_avisa_de_saldos_entre_empresas_que_no_se_eliminan(self):
        """Un préstamo entre empresas no es por cobrar ni por pagar: no se elimina, pero tampoco se calla."""
        prestamo = self.cuenta(self.empresa_a, 'asset_current', 1)
        banco_b = self.cuenta(self.empresa_b, 'asset_current', 1)
        self.asiento(self.empresa_a, '2030-03-20', [(prestamo, 400, 0, self.empresa_b.partner_id),
                                                    (self.cuenta(self.empresa_a, 'asset_current', 2), 0, 400, None)])
        self.asiento(self.empresa_b, '2030-03-20', [(banco_b, 400, 0, None),
                                                    (self.cuenta(self.empresa_b, 'liability_current', 1), 0, 400,
                                                     self.empresa_a.partner_id)])
        consolidacion = self.consolidacion('balance')
        self.assertIn('no es por cobrar ni por pagar', consolidacion.advertencias)
        self.assertIn(self.empresa_a.name, consolidacion.advertencias)
        self.assertFalse(consolidacion.linea_ids.filtered(lambda ln: ln.tipo_columna == 'eliminaciones'))
        self.assertConsolidadoEsLaSuma(consolidacion)

    def test_dinero_en_banco_con_otra_empresa_no_es_deuda(self):
        """Lo que entra a un banco con la ficha de la otra empresa no se avisa como deuda entre empresas."""
        bancos = self.env['account.account'].with_company(self.empresa_a).search(
            [('account_type', '=', 'asset_cash'), ('company_ids', 'in', self.empresa_a.id)], order='code', limit=1)
        self.assertTrue(bancos, 'La empresa principal debería tener su cuenta de banco')
        self.asiento(self.empresa_a, '2030-03-21', [(bancos, 80, 0, self.empresa_b.partner_id),
                                                    (self.cuenta(self.empresa_a, 'income_other'), 0, 80, None)])
        self.assertNotIn('no es por cobrar ni por pagar', self.consolidacion('balance').advertencias or '')

    # ------------------------------------------------------------------
    # Mapa de cuentas
    # ------------------------------------------------------------------

    def _cuenta_nueva(self, empresa, codigo, nombre, tipo):
        return self.env['account.account'].with_company(empresa).create({
            'name': nombre, 'code': codigo, 'account_type': tipo, 'company_ids': [Command.set(empresa.ids)]})

    def test_une_por_codigo_y_una_cuenta_de_una_sola_empresa_aparece(self):
        propia = self._cuenta_nueva(self.empresa_b, '4999.ZL', 'Ventas exclusivas de la zona libre', 'income')
        self.asiento(self.empresa_b, '2030-03-22', [
            (self.cuenta(self.empresa_b, 'asset_receivable'), 90, 0, self.cliente), (propia, 0, 90, self.cliente)])
        consolidacion = self.consolidacion('resultados')
        tabla = self.tabla(consolidacion)
        codigo = self.cuenta(self.empresa_a, 'income').code
        # El mismo código en las dos empresas es UNA sola fila con las dos columnas.
        self.assertEqual(set(tabla[('ventas', codigo)]), {self.empresa_a.name, self.empresa_b.name, 'consolidado'})
        self.assertEqual(len(consolidacion.linea_ids.filtered(lambda ln: ln.codigo == codigo and
                                                              ln.tipo_columna == 'consolidado')), 1)
        # La cuenta que solo existe en B aparece igual, con el nombre que tiene.
        fila = tabla[('ventas', '4999.ZL')]
        self.assertEqual(set(fila), {self.empresa_b.name, 'consolidado'})
        self.assertAlmostEqual(fila['consolidado'], 90.0)
        self.assertEqual(consolidacion.linea_ids.filtered(lambda ln: ln.codigo == '4999.ZL')[:1].nombre,
                         'Ventas exclusivas de la zona libre')
        self.assertEmpresaIgualAlMotor(consolidacion, self.empresa_b)

    def test_el_mapa_manual_une_planes_distintos(self):
        propia = self._cuenta_nueva(self.empresa_b, '4999.ZL', 'Ventas de la zona libre', 'income')
        self.asiento(self.empresa_b, '2030-03-22', [
            (self.cuenta(self.empresa_b, 'asset_receivable'), 90, 0, self.cliente), (propia, 0, 90, self.cliente)])
        codigo_a = self.cuenta(self.empresa_a, 'income').code
        sin_mapa = self.tabla(self.consolidacion('resultados'))
        self.assertIn(('ventas', '4999.ZL'), sin_mapa)
        self.env['dcasa.consolidacion.mapa'].create({
            'company_id': self.empresa_b.id, 'account_id': propia.id, 'codigo_consolidado': f' {codigo_a} '})
        tabla = self.tabla(self.consolidacion('resultados'))
        self.assertNotIn(('ventas', '4999.ZL'), tabla)  # ya no sale aparte
        fila = tabla[('ventas', codigo_a)]
        self.assertAlmostEqual(fila[self.empresa_b.name], 500.0 + 90.0)
        self.assertAlmostEqual(fila['consolidado'], 1000.0 + 500.0 + 90.0)
        guardado = self.env['dcasa.consolidacion.mapa'].search([('account_id', '=', propia.id)])
        self.assertEqual(guardado.codigo_consolidado, codigo_a)  # se guarda sin espacios

    def test_el_mapa_manda_sobre_el_codigo(self):
        """Dos cuentas con el MISMO código no se unen si el mapa dice que una va a otro lado."""
        ventas_b = self.cuenta(self.empresa_b, 'income')
        codigo = ventas_b.with_company(self.empresa_b).code
        self.assertEqual(codigo, self.cuenta(self.empresa_a, 'income').code)
        self.env['dcasa.consolidacion.mapa'].create({
            'company_id': self.empresa_b.id, 'account_id': ventas_b.id, 'codigo_consolidado': '4000.ZL',
            'nombre_consolidado': 'Ventas de la zona libre'})
        consolidacion = self.consolidacion('resultados')
        tabla = self.tabla(consolidacion)
        self.assertEqual(set(tabla[('ventas', codigo)]), {self.empresa_a.name, 'consolidado'})
        self.assertAlmostEqual(tabla[('ventas', codigo)]['consolidado'], 1000.0)
        self.assertAlmostEqual(tabla[('ventas', '4000.ZL')]['consolidado'], 500.0)
        self.assertEqual(consolidacion.linea_ids.filtered(lambda ln: ln.codigo == '4000.ZL')[:1].nombre,
                         'Ventas de la zona libre')

    def test_el_mapa_tambien_alinea_las_eliminaciones(self):
        """Con planes distintos, lo que se elimina cae en la misma fila consolidada que lo de cada empresa."""
        gasto_propio = self._cuenta_nueva(self.empresa_b, '5999.ZL', 'Compras a la casa matriz', 'expense')
        gasto_a = self.cuenta(self.empresa_a, 'expense')
        self.env['dcasa.consolidacion.mapa'].create({
            'company_id': self.empresa_b.id, 'account_id': gasto_propio.id, 'codigo_consolidado': gasto_a.code})
        self.asiento(self.empresa_a, '2030-03-15', [
            (self.cuenta(self.empresa_a, 'asset_receivable'), 600, 0, self.empresa_b.partner_id),
            (self.cuenta(self.empresa_a, 'income'), 0, 600, self.empresa_b.partner_id)])
        self.asiento(self.empresa_b, '2030-03-15', [
            (gasto_propio, 600, 0, self.empresa_a.partner_id),
            (self.cuenta(self.empresa_b, 'liability_payable'), 0, 600, self.empresa_a.partner_id)])
        consolidacion = self.consolidacion('resultados')
        fila = self.tabla(consolidacion)[('gastos', gasto_a.code)]
        self.assertAlmostEqual(fila['eliminaciones'], -600.0)
        self.assertAlmostEqual(fila[self.empresa_b.name], 120.0 + 600.0)
        self.assertFalse(consolidacion.advertencias)
        self.assertConsolidadoEsLaSuma(consolidacion)

    def test_avisa_si_un_mismo_codigo_cae_en_secciones_distintas(self):
        corriente_a = self.cuenta(self.empresa_a, 'asset_current', 3)
        no_corriente_b = self._cuenta_nueva(self.empresa_b, '1999.ZL', 'Activo no corriente de la zona libre',
                                            'asset_non_current')
        self.env['dcasa.consolidacion.mapa'].create({
            'company_id': self.empresa_b.id, 'account_id': no_corriente_b.id, 'codigo_consolidado': corriente_a.code})
        self.asiento(self.empresa_a, '2030-03-22', [(corriente_a, 10, 0, None),
                                                    (self.cuenta(self.empresa_a, 'equity'), 0, 10, None)])
        self.asiento(self.empresa_b, '2030-03-22', [(no_corriente_b, 70, 0, None),
                                                    (self.cuenta(self.empresa_b, 'equity'), 0, 70, None)])
        consolidacion = self.consolidacion('balance')
        self.assertIn(f'La cuenta consolidada {corriente_a.code} cae en secciones distintas',
                      consolidacion.advertencias)
        # Cada parte se queda en su sección: nada se mezcla a escondidas.
        secciones = set(consolidacion.linea_ids.filtered(lambda ln: ln.codigo == corriente_a.code).mapped('seccion'))
        self.assertEqual(secciones, {'activo_corriente', 'activo_no_corriente'})

    def test_validaciones_del_mapa(self):
        mapa = self.env['dcasa.consolidacion.mapa']
        ventas_a = self.cuenta(self.empresa_a, 'income')
        with self.assertRaises(ValidationError):  # una cuenta de A no puede mapearse como si fuera de B
            mapa.create({'company_id': self.empresa_b.id, 'account_id': ventas_a.id, 'codigo_consolidado': 'X'})
        mapa.create({'company_id': self.empresa_a.id, 'account_id': ventas_a.id, 'codigo_consolidado': 'X'})
        with self.assertRaises(UniqueViolation), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            mapa.create({'company_id': self.empresa_a.id, 'account_id': ventas_a.id, 'codigo_consolidado': 'Y'})

    # ------------------------------------------------------------------
    # Monedas, una sola empresa, borradores, recalcular
    # ------------------------------------------------------------------

    def test_monedas_distintas_no_se_consolidan(self):
        euro = self.env.ref('base.EUR')
        en_euros = self.env['res.company'].create({'name': 'Empresa en euros de prueba', 'currency_id': euro.id})
        consolidacion = self.consolidacion(empresas=self.empresa_a | en_euros, calcular=False)
        self.assertTrue(consolidacion.monedas_distintas)
        with self.assertRaisesRegex(UserError, 'todavía no se consolidan monedas distintas'):
            consolidacion.action_calcular()
        self.assertEqual(consolidacion.estado, 'borrador')
        self.assertFalse(consolidacion.linea_ids)

    def test_una_sola_empresa_funciona_y_avisa(self):
        consolidacion = self.consolidacion('resultados', empresas=self.empresa_a)
        self.assertTrue(consolidacion.una_empresa)
        self.assertIn('una sola empresa', consolidacion.advertencias)
        for fila, columnas in self.tabla(consolidacion).items():
            self.assertAlmostEqual(columnas['consolidado'], columnas[self.empresa_a.name], msg=str(fila))
        self.assertEmpresaIgualAlMotor(consolidacion, self.empresa_a)

    def test_solo_cuentan_los_asientos_publicados(self):
        ventas = ('ventas', self.cuenta(self.empresa_a, 'income').code)
        antes = self.tabla(self.consolidacion('resultados'))[ventas]['consolidado']
        self.venta_externa(self.empresa_a, 55, '2030-03-25', publicar=False)
        self.assertAlmostEqual(self.tabla(self.consolidacion('resultados'))[ventas]['consolidado'], antes)
        self.venta_externa(self.empresa_a, 55, '2030-04-25')
        self.assertAlmostEqual(self.tabla(self.consolidacion('resultados'))[ventas]['consolidado'], antes)  # otro mes
        self.venta_externa(self.empresa_a, 55, '2030-03-26')
        self.assertAlmostEqual(self.tabla(self.consolidacion('resultados'))[ventas]['consolidado'], antes + 55.0)

    def test_recalcular_no_duplica_las_lineas(self):
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0, pagar=900.0)
        consolidacion = self.consolidacion('balance')
        lineas, avisos = len(consolidacion.linea_ids), consolidacion.advertencias
        self.assertTrue(lineas)
        viejas = consolidacion.linea_ids.ids
        consolidacion.action_calcular()
        consolidacion.action_calcular()
        self.assertEqual(len(consolidacion.linea_ids), lineas)
        self.assertEqual(consolidacion.advertencias, avisos)
        self.assertFalse(set(viejas) & set(consolidacion.linea_ids.ids))
        en_la_base = self.env['dcasa.consolidacion.linea'].search_count([('consolidacion_id', '=', consolidacion.id)])
        self.assertEqual(en_la_base, lineas)
        # Si cambian los asientos, recalcular lo refleja (y las advertencias se van si ya cuadra).
        self.asiento(self.empresa_b, '2030-03-16', [
            (self.cuenta(self.empresa_b, 'expense'), 100, 0, self.empresa_a.partner_id),
            (self.cuenta(self.empresa_b, 'liability_payable'), 0, 100, self.empresa_a.partner_id)])
        consolidacion.action_calcular()
        self.assertFalse(consolidacion.advertencias)
        self.assertTrue(consolidacion.cuadra)

    def test_volver_a_borrador_y_cambiar_los_parametros(self):
        consolidacion = self.consolidacion('resultados')
        self.assertTrue(consolidacion.linea_ids)
        consolidacion.action_borrador()
        self.assertEqual(consolidacion.estado, 'borrador')
        self.assertFalse(consolidacion.linea_ids)
        self.assertFalse(consolidacion.advertencias)
        consolidacion.write({'tipo_reporte': 'balance'})
        consolidacion.action_calcular()
        self.assertEqual(consolidacion.tipo_reporte, 'balance')
        self.assertTrue(consolidacion.cuadra)

    def test_validaciones_de_la_consolidacion(self):
        with self.assertRaises(ValidationError):
            self.consolidacion(empresas=self.env['res.company'], calcular=False)
        with self.assertRaises(CheckViolation), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.consolidacion(calcular=False, fecha_desde='2030-04-01', fecha_hasta='2030-03-01')
            self.env.flush_all()
        copia = self.consolidacion('balance').copy()
        self.assertEqual((copia.estado, len(copia.linea_ids), copia.advertencias), ('borrador', 0, False))

    def test_calcular_no_toca_la_contabilidad(self):
        movimientos = self.env['account.move'].with_context(active_test=False).search_count([])
        lineas = self.env['account.move.line'].search_count([])
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0, pagar=900.0)
        movimientos_antes = self.env['account.move'].search_count([])
        self.assertGreater(movimientos_antes, movimientos)
        for tipo in ('resultados', 'balance', 'comprobacion'):
            self.consolidacion(tipo)
        self.assertEqual(self.env['account.move'].search_count([]), movimientos_antes)
        self.assertGreater(self.env['account.move.line'].search_count([]), lineas)

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    def test_el_pdf_se_genera_con_las_columnas_y_los_avisos(self):
        self.venta_entre_empresas(self.empresa_a, self.empresa_b, 1000.0, pagar=900.0)
        reporte = self.env['ir.actions.report']
        codigos = {'resultados': self.cuenta(self.empresa_a, 'income').code,
                   'balance': self.cuenta(self.empresa_a, 'asset_receivable').code,
                   'comprobacion': self.cuenta(self.empresa_a, 'liability_payable').code}
        for tipo, titulo in (('resultados', 'Estado de resultados consolidado'),
                             ('balance', 'Balance general consolidado'),
                             ('comprobacion', 'Balance de comprobación consolidado')):
            consolidacion = self.consolidacion(tipo)
            html, _formato = reporte._render_qweb_html('dcasa_consolidacion.reporte_consolidacion', consolidacion.ids)
            html = html.decode()
            self.assertIn(titulo, html, tipo)
            for nombre in (self.empresa_a.name, self.empresa_b.name, 'Eliminaciones', 'Consolidado'):
                self.assertIn(str(escape(nombre)), html, f'{tipo}: {nombre}')
            self.assertIn('Descuadre entre', html, tipo)
            self.assertIn(str(escape(codigos[tipo])), html, tipo)
            # El botón «Imprimir» usa esta misma ruta; en pruebas Odoo entrega el HTML en vez de llamar a wkhtmltopdf.
            contenido, _formato = reporte._render_qweb_pdf('dcasa_consolidacion.accion_reporte_consolidacion',
                                                           consolidacion.ids)
            self.assertIn(titulo, contenido.decode(), tipo)

    def test_no_se_imprime_lo_que_no_se_ha_calculado(self):
        consolidacion = self.consolidacion(calcular=False)
        with self.assertRaises(UserError):
            self.env['ir.actions.report']._render_qweb_html(
                'dcasa_consolidacion.reporte_consolidacion', consolidacion.ids)

    def test_el_motor_y_el_calculo_no_son_publicos(self):
        """Por RPC solo se llega a los botones (que piden el grupo contable); el motor y el cálculo son privados."""
        for modelo in ('dcasa.consolidacion.motor', 'dcasa.consolidacion', 'dcasa.consolidacion.linea',
                       'dcasa.consolidacion.mapa'):
            for metodo in ('_calcular', '_partes', '_sumas', '_avisos', '_matriz', '_valores_de_lineas', '_grupo'):
                if hasattr(self.env[modelo], metodo):
                    with self.assertRaises(AccessError, msg=f'{modelo}.{metodo}'):
                        get_public_method(self.env[modelo], metodo)
        publicos = {'action_calcular', 'action_borrador', 'action_ver_pivote'}
        for metodo in publicos:
            self.assertTrue(get_public_method(self.env['dcasa.consolidacion'], metodo))

    def test_las_vistas_cargan(self):
        self.env['dcasa.consolidacion'].get_views([(False, 'list'), (False, 'form'), (False, 'search')])
        self.env['dcasa.consolidacion.linea'].get_views([(False, 'pivot'), (False, 'list'), (False, 'search')])
        self.env['dcasa.consolidacion.mapa'].get_views([(False, 'list'), (False, 'search')])

    def test_menu_y_acciones(self):
        menu = self.env.ref('dcasa_consolidacion.menu_consolidacion')
        self.assertEqual(menu.parent_id, self.env.ref('dcasa_contabilidad.menu_reportes'))
        accion = self.consolidacion('balance').action_ver_pivote()
        self.assertEqual(accion['res_model'], 'dcasa.consolidacion.linea')
        self.assertIn('pivot', accion['view_mode'])
        self.assertTrue(self.env['dcasa.consolidacion.linea'].search(accion['domain']))
        self.assertEqual(self.env.ref('dcasa_consolidacion.accion_reporte_consolidacion').model, 'dcasa.consolidacion')
