"""Auditoría de la consolidación: cada cifra se cruza con un cálculo INDEPENDIENTE en SQL (``oraculo_consolidacion``).

Dos empresas del grupo, con ventas y compras externas, facturas reales entre ellas (con ITBMS, sin ITBMS, en las dos
direcciones, con nota de crédito, de un año anterior, fuera del periodo, en borrador y con un contacto de la otra
empresa como tercero) y cobros que esperan su movimiento. Se comprueba que:

* el estado de resultados consolidado = la suma de las empresas − lo eliminado, sección por sección;
* el balance consolidado cuadra (activo = pasivo + patrimonio) y cada sección es la suma − lo eliminado;
* el balance de comprobación consolidado cuadra y su debe y haber son la suma menos lo eliminado;
* el ITBMS de una factura entre empresas no se elimina ni genera un aviso falso;
* las cuentas que solo tiene una empresa no se pierden y la nota lo dice;
* los atajos de fechas del formulario ponen las fechas correctas.
"""
from freezegun import freeze_time

from odoo import Command
from odoo.tests import Form, tagged

from . import oraculo_consolidacion as O
from .common import ConsolidacionCommon

# Sección del estado de resultados -> (tipos de cuenta, signo con el que se presenta)
SECCIONES_RESULTADOS = {
    'ventas': (('income',), -1), 'costo': (('expense_direct_cost',), 1), 'otros_ingresos': (('income_other',), -1),
    'gastos': (('expense',), 1), 'depreciacion': (('expense_depreciation',), 1),
    'otros_gastos': (('expense_other',), 1),
}
# Sección del balance -> (tipos de cuenta, signo)
SECCIONES_BALANCE = {
    'activo_corriente': (('asset_cash', 'asset_receivable', 'asset_current', 'asset_prepayments'), 1),
    'activo_no_corriente': (('asset_non_current', 'asset_fixed'), 1),
    'pasivo_corriente': (('liability_payable', 'liability_credit_card', 'liability_current'), -1),
    'pasivo_no_corriente': (('liability_non_current',), -1),
    'patrimonio': (('equity', 'equity_unaffected'), -1),
}
VENTANAS = {
    'marzo': ('2030-03-01', '2030-03-31'),
    'mitad': ('2030-02-15', '2030-03-15'),
    'dia': ('2030-03-12', '2030-03-12'),
    'anio': ('2030-01-01', '2030-12-31'),
    'anio_anterior': ('2029-01-01', '2029-12-31'),
    'antes_de_la_factura': ('2030-03-01', '2030-03-11'),
    'despues_de_la_factura': ('2030-03-13', '2030-03-31'),
}
CORTES = ('2029-12-31', '2030-02-19', '2030-02-28', '2030-03-11', '2030-03-12', '2030-03-15', '2030-03-31',
          '2030-04-30', '2030-12-31')


class AuditoriaConsolidacion(ConsolidacionCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entre_empresas()

    # -- datos: lo que las empresas se hacen entre ellas --------------------------------------------------------------

    @classmethod
    def factura(cls, empresa, otra, tipo, monto, fecha, impuesto=True, publicar=True):
        compra = tipo in ('in_invoice', 'in_refund')
        tasa = (empresa.account_purchase_tax_id if compra else empresa.account_sale_tax_id) if impuesto \
            else cls.env['account.tax']
        mov = cls.env['account.move'].with_company(empresa).create({
            'move_type': tipo, 'company_id': empresa.id, 'partner_id': otra.partner_id.id,
            'invoice_date': fecha, 'date': fecha, 'invoice_date_due': fecha,
            'invoice_line_ids': [Command.create({'name': 'Muebles', 'quantity': 1, 'price_unit': monto,
                                                 'tax_ids': [Command.set(tasa.ids)]})]})
        if publicar:
            mov.action_post()
        return mov

    @classmethod
    def entre_las_dos(cls, vendedora, compradora, monto, fecha, impuesto=True, nota=False):
        """La factura (o nota de crédito) de ``vendedora`` y la factura de proveedor (o su nota) de ``compradora``."""
        return (cls.factura(vendedora, compradora, 'out_refund' if nota else 'out_invoice', monto, fecha, impuesto),
                cls.factura(compradora, vendedora, 'in_refund' if nota else 'in_invoice', monto, fecha, impuesto))

    @classmethod
    def entre_empresas(cls):
        a, b = cls.empresa_a, cls.empresa_b
        cls.venta_1, cls.compra_1 = cls.entre_las_dos(a, b, 1000, '2030-03-12')               # con ITBMS
        cls.entre_las_dos(a, b, 500, '2030-02-20', impuesto=False)                              # sin ITBMS, febrero
        cls.entre_las_dos(b, a, 300, '2030-03-18')                                              # al revés
        cls.entre_las_dos(a, b, 100, '2030-03-25', nota=True)                                   # nota de crédito
        cls.entre_las_dos(a, b, 200, '2029-10-10')                                              # año anterior
        cls.entre_las_dos(a, b, 150, '2030-04-10')                                              # después de marzo
        cls.factura(a, b, 'out_invoice', 777, '2030-03-20', publicar=False)                    # borrador: no cuenta
        # Un asiento manual cuyo tercero es una PERSONA de la otra empresa (un contacto de su ficha).
        contacto = cls.env['res.partner'].create({'name': 'Contacto de la zona libre', 'parent_id': b.partner_id.id,
                                                  'type': 'contact'})
        cls.asiento(a, '2030-03-14', [(cls.cuenta(a, 'asset_receivable'), 60, 0, contacto),
                                      (cls.cuenta(a, 'income'), 0, 60, contacto)])
        cls.asiento(b, '2030-03-14', [(cls.cuenta(b, 'expense'), 60, 0, a.partner_id),
                                      (cls.cuenta(b, 'liability_payable'), 0, 60, a.partner_id)])

    # -- ayudas de comparación ---------------------------------------------------------------------------------------

    def assertCifra(self, pantalla, referencia, msg=''):
        self.assertAlmostEqual(pantalla, referencia, places=2,
                               msg=f'{msg}: pantalla={pantalla} referencia={referencia}')

    @staticmethod
    def eliminado_por_tipo(consolidacion):
        """{tipo de cuenta: Σ importe} de la columna «Eliminaciones» (puede haber varias cuentas del mismo tipo)."""
        totales = {}
        for linea in consolidacion.linea_ids.filtered(lambda ln: ln.tipo_columna == 'eliminaciones'):
            totales[linea.tipo_cuenta] = totales.get(linea.tipo_cuenta, 0.0) + linea.importe
        return totales

    @staticmethod
    def por_seccion(consolidacion, columna='consolidado'):
        """{sección: Σ importe} de una columna (empresa por nombre, 'eliminaciones' o 'consolidado')."""
        totales = {}
        for linea in consolidacion.linea_ids:
            actual = linea.columna if linea.tipo_columna == 'empresa' else linea.tipo_columna
            if actual == columna:
                totales[linea.seccion] = totales.get(linea.seccion, 0.0) + linea.importe
        return totales


@tagged('post_install', '-at_install')
class TestEstadoDeResultadosConsolidado(AuditoriaConsolidacion):

    def test_cada_seccion_es_la_suma_de_las_empresas_menos_lo_eliminado(self):
        for nombre, (desde, hasta) in VENTANAS.items():
            consolidacion = self.consolidacion('resultados', fecha_desde=desde, fecha_hasta=hasta)
            empresas = O.por_empresa_y_tipo(self.env, self.grupo, desde, hasta, O.RESULTADOS)
            eliminado = O.eliminaciones(self.env, self.grupo, O.RESULTADOS, desde, hasta)
            consolidado = self.por_seccion(consolidacion)
            quitado = self.por_seccion(consolidacion, 'eliminaciones')
            utilidad = 0.0
            for seccion, (tipos, signo) in SECCIONES_RESULTADOS.items():
                suma = signo * O.neto(empresas, None, tipos)
                quita = signo * sum(eliminado.get(t, 0.0) for t in tipos)
                self.assertCifra(consolidado.get(seccion, 0.0), suma - quita, f'{nombre} {seccion}: consolidado')
                self.assertCifra(quitado.get(seccion, 0.0), -quita, f'{nombre} {seccion}: eliminaciones')
                for empresa in self.grupo:
                    self.assertCifra(self.por_seccion(consolidacion, empresa.name).get(seccion, 0.0),
                                     signo * O.neto(empresas, empresa.id, tipos), f'{nombre} {seccion}: {empresa.name}')
                utilidad += -signo * (suma - quita)
            self.assertCifra(consolidacion.utilidad_neta, utilidad, f'{nombre}: utilidad neta consolidada')
            # La utilidad no cambia por eliminar ventas y compras entre empresas por igual.
            sin = -(O.neto(empresas) - sum(eliminado.values()))
            self.assertCifra(consolidacion.utilidad_neta, sin, f'{nombre}: utilidad = −(suma − eliminado)')

    def test_cifras_a_mano_de_marzo(self):
        """Papel y lápiz. Marzo: A vende a B 1000 (12/3) y 60 (14/3) y le devuelve 100 (25/3); B le vende a A 300.
        Ventas externas: A 1000, B 500. Compras externas: A 300, B 120. Lo de abril, el borrador y febrero no entran."""
        consolidacion = self.consolidacion('resultados')
        a, b = self.empresa_a.name, self.empresa_b.name
        ventas = self.por_seccion(consolidacion)['ventas']
        suma_a, suma_b = self.por_seccion(consolidacion, a)['ventas'], self.por_seccion(consolidacion, b)['ventas']
        self.assertCifra(suma_a, 1000 + (1000 + 60 - 100), 'ventas de A (externas 1000 + a B 960)')
        self.assertCifra(suma_b, 500 + 300, 'ventas de B (externas 500 + a A 300)')
        self.assertCifra(self.por_seccion(consolidacion, 'eliminaciones')['ventas'], -(960 + 300),
                         'se elimina lo que A le vendió a B (960 netos) y lo que B le vendió a A (300)')
        self.assertCifra(ventas, 1000 + 500, 'ventas consolidadas = solo lo vendido a terceros')
        gastos = self.por_seccion(consolidacion)['gastos']
        self.assertCifra(gastos, 300 + 120, 'gastos consolidados = solo lo comprado a terceros')
        self.assertCifra(consolidacion.utilidad_neta, 1500 - 420, 'utilidad consolidada (1,080 de siempre)')

    def test_el_itbms_de_una_factura_entre_empresas_no_se_elimina_ni_avisa(self):
        consolidacion = self.consolidacion('resultados')
        self.assertFalse(consolidacion.advertencias)
        balance = self.consolidacion('balance', fecha_desde='2030-01-01', fecha_hasta='2030-03-31')
        self.assertFalse(balance.advertencias, 'antes salía «saldo acreedor con la otra empresa en ITBMS»')
        self.assertTrue(balance.cuadra)
        eliminadas = balance.linea_ids.filtered(lambda ln: ln.tipo_columna == 'eliminaciones')
        self.assertEqual(set(eliminadas.mapped('seccion')), {'activo_corriente', 'pasivo_corriente'})
        self.assertEqual(set(eliminadas.mapped('tipo_cuenta')), {'asset_receivable', 'liability_payable'})
        # El ITBMS lo deben (o lo cobran) las empresas a la DGI, no una a la otra: su cuenta no tiene eliminación.
        impuesto = balance.linea_ids.filtered(lambda ln: ln.tipo_cuenta == 'liability_current'
                                              and ln.tipo_columna == 'eliminaciones')
        self.assertFalse(impuesto)

    def test_un_contacto_de_la_otra_empresa_cuenta_como_la_otra_empresa(self):
        consolidacion = self.consolidacion('resultados', fecha_desde='2030-03-14', fecha_hasta='2030-03-14')
        self.assertCifra(self.por_seccion(consolidacion, 'eliminaciones')['ventas'], -60.0, 'ventas a un contacto de B')
        self.assertCifra(self.por_seccion(consolidacion, 'eliminaciones')['gastos'], -60.0, 'gastos de B con A')
        self.assertFalse(consolidacion.advertencias)

    def test_fechas_borde(self):
        """El día de la factura cuenta; el día anterior y el siguiente, no."""
        def eliminado(desde, hasta):
            c = self.consolidacion('resultados', fecha_desde=desde, fecha_hasta=hasta)
            return self.por_seccion(c, 'eliminaciones').get('ventas', 0.0)

        self.assertCifra(eliminado('2030-03-12', '2030-03-12'), -1000.0, 'el mismo día')
        self.assertCifra(eliminado('2030-03-01', '2030-03-11'), 0.0, 'terminando el día anterior')
        self.assertCifra(eliminado('2030-03-13', '2030-03-13'), 0.0, 'empezando el día siguiente')
        self.assertCifra(eliminado('2030-03-12', '2030-03-13'), -1000.0, 'desde ese día')

    def test_el_resultado_consolidado_cuadra_con_el_balance(self):
        """La utilidad del ejercicio del balance consolidado es la del estado de resultados del año fiscal."""
        resultados = self.consolidacion('resultados', fecha_desde='2030-01-01', fecha_hasta='2030-03-31')
        balance = self.consolidacion('balance', fecha_desde='2030-01-01', fecha_hasta='2030-03-31')
        fila = balance.linea_ids.filtered(lambda ln: ln.tipo_columna == 'consolidado'
                                          and ln.nombre == 'Resultado del ejercicio')
        self.assertCifra(fila.importe, resultados.utilidad_neta, 'resultado del ejercicio = utilidad del año')


@tagged('post_install', '-at_install')
class TestBalanceConsolidado(AuditoriaConsolidacion):

    def test_cada_seccion_cuadra_con_los_apuntes_y_el_balance_cuadra(self):
        for corte in CORTES:
            consolidacion = self.consolidacion('balance', fecha_desde='2029-01-01', fecha_hasta=corte)
            empresas = O.por_empresa_y_tipo(self.env, self.grupo, hasta=corte)
            eliminado = O.eliminaciones(self.env, self.grupo, O.ELIMINABLES_BALANCE, hasta=corte)
            consolidado = self.por_seccion(consolidacion)
            resultados = -O.neto(empresas, None, O.RESULTADOS)       # lo de TODOS los años pasa al patrimonio
            for seccion, (tipos, signo) in SECCIONES_BALANCE.items():
                esperado = signo * (O.neto(empresas, None, tipos) - sum(eliminado.get(t, 0.0) for t in tipos))
                if seccion == 'patrimonio':
                    esperado += resultados
                self.assertCifra(consolidado.get(seccion, 0.0), esperado, f'{corte} {seccion}')
            activo = consolidado.get('activo_corriente', 0.0) + consolidado.get('activo_no_corriente', 0.0)
            pasivo_y_patrimonio = sum(consolidado.get(s, 0.0) for s in
                                      ('pasivo_corriente', 'pasivo_no_corriente', 'patrimonio'))
            self.assertCifra(activo, pasivo_y_patrimonio, f'{corte}: activo = pasivo + patrimonio')
            self.assertTrue(consolidacion.cuadra, corte)
            self.assertCifra(consolidacion.diferencia, 0.0, f'{corte}: diferencia')
            # Cada empresa por separado también cuadra.
            for empresa in self.grupo:
                columna = self.por_seccion(consolidacion, empresa.name)
                a = columna.get('activo_corriente', 0.0) + columna.get('activo_no_corriente', 0.0)
                p = sum(columna.get(s, 0.0) for s in ('pasivo_corriente', 'pasivo_no_corriente', 'patrimonio'))
                self.assertCifra(a, p, f'{corte}: {empresa.name} cuadra sola')

    def test_cifras_a_mano_al_31_de_marzo(self):
        """Papel y lápiz. A le cobra a B: 1,070 (factura de marzo con ITBMS) + 500 (febrero, sin ITBMS) − 107 (nota de
        crédito con ITBMS) + 214 (octubre del año anterior con ITBMS) + 60 (asiento a un contacto de B) = 1,737.
        B le cobra a A: 321 (300 + 21 de ITBMS). Lo de abril (150) y el borrador (777) no entran. Cada lado se elimina:
        1,737 + 321 = 2,058 en por cobrar y lo mismo en por pagar."""
        consolidacion = self.consolidacion('balance', fecha_desde='2030-01-01', fecha_hasta='2030-03-31')
        eliminadas = self.eliminado_por_tipo(consolidacion)
        self.assertCifra(eliminadas['asset_receivable'], -2058.0, 'por cobrar entre empresas')
        self.assertCifra(eliminadas['liability_payable'], -2058.0, 'por pagar entre empresas')
        self.assertFalse(consolidacion.advertencias)
        # Con el corte al 30 de abril entra la venta de 150 + 10.50 de ITBMS, de las dos empresas.
        abril = self.consolidacion('balance', fecha_desde='2030-01-01', fecha_hasta='2030-04-30')
        eliminadas = self.eliminado_por_tipo(abril)
        self.assertCifra(eliminadas['asset_receivable'], -(2058.0 + 160.5), 'por cobrar al 30 de abril')
        self.assertCifra(eliminadas['liability_payable'], -(2058.0 + 160.5), 'por pagar al 30 de abril')


    def test_cada_empresa_pasa_sus_resultados_al_patrimonio_con_su_propio_anio_fiscal(self):
        """B cierra su año el 30 de junio: al 31 de marzo de 2030 su ejercicio en curso empezó el 1 de julio de 2029."""
        self.empresa_b.write({'fiscalyear_last_day': 30, 'fiscalyear_last_month': '6'})
        consolidacion = self.consolidacion('balance', fecha_desde='2030-01-01', fecha_hasta='2030-03-31')
        self.assertTrue(consolidacion.cuadra)
        filas = {(ln.nombre, ln.columna): ln.importe for ln in consolidacion.linea_ids
                 if ln.nombre in ('Resultado del ejercicio', 'Resultados de ejercicios anteriores')
                 and ln.tipo_columna == 'empresa'}
        b = self.empresa_b
        del_ejercicio_b = -O.neto(O.por_empresa_y_tipo(self.env, b, '2029-07-01', '2030-03-31', O.RESULTADOS))
        anteriores_b = -O.neto(O.por_empresa_y_tipo(self.env, b, None, '2029-06-30', O.RESULTADOS))
        self.assertCifra(filas.get(('Resultado del ejercicio', b.name), 0.0), del_ejercicio_b,
                         'B: ejercicio desde el 1 de julio')
        self.assertCifra(filas.get(('Resultados de ejercicios anteriores', b.name), 0.0), anteriores_b,
                         'B: hasta el 30 de junio (para B no hay nada anterior)')
        a = self.empresa_a                     # A cierra el 31 de diciembre
        self.assertCifra(filas.get(('Resultado del ejercicio', a.name), 0.0),
                         -O.neto(O.por_empresa_y_tipo(self.env, a, '2030-01-01', '2030-03-31', O.RESULTADOS)),
                         'A: ejercicio desde el 1 de enero')
        # Lo de B del 1 de julio al 31 de diciembre de 2029 es «ejercicio» para B y «anterior» para A: el total
        # (anteriores + ejercicio) de cada empresa es lo mismo que si las dos cerraran el mismo día.
        total = sum(filas.values())
        todo = -O.neto(O.por_empresa_y_tipo(self.env, self.grupo, None, '2030-03-31', O.RESULTADOS))
        self.assertCifra(total, todo, 'anteriores + ejercicio de las dos empresas')

    def test_el_periodo_se_dice_igual_en_la_lista_y_en_el_pdf(self):
        balance = self.consolidacion('balance', fecha_desde='2030-01-01', fecha_hasta='2030-03-31')
        self.assertEqual(balance.periodo_texto, 'Al 31/03/2030')
        self.assertEqual(balance._matriz()['periodo'], 'Al 31/03/2030')
        un_dia = self.consolidacion('resultados', fecha_desde='2030-03-12', fecha_hasta='2030-03-12')
        self.assertEqual(un_dia.periodo_texto, 'El 12/03/2030')
        marzo = self.consolidacion('resultados')
        self.assertEqual(marzo.periodo_texto, 'Del 01/03/2030 al 31/03/2030')
        self.assertEqual(marzo._matriz()['periodo'], marzo.periodo_texto)

    def test_el_mapa_muestra_el_tipo_de_cada_cuenta(self):
        ventas = self.cuenta(self.empresa_a, 'income')
        mapa = self.env['dcasa.consolidacion.mapa'].create({
            'company_id': self.empresa_a.id, 'account_id': ventas.id, 'codigo_consolidado': 'VENTAS'})
        self.assertEqual(mapa.tipo_cuenta, 'income')


@tagged('post_install', '-at_install')
class TestComprobacionConsolidada(AuditoriaConsolidacion):

    def test_debe_haber_y_saldos_contra_los_apuntes(self):
        for nombre, (desde, hasta) in VENTANAS.items():
            consolidacion = self.consolidacion('comprobacion', fecha_desde=desde, fecha_hasta=hasta)
            periodo = O.por_empresa_y_tipo(self.env, self.grupo, desde, hasta)
            quitar = O.entre_empresas(self.env, self.grupo, desde, hasta,
                                      O.ELIMINABLES_BALANCE + O.RESULTADOS)
            debe = sum(d for d, _h in periodo.values()) - sum(d for d, _h in quitar.values())
            haber = sum(h for _d, h in periodo.values()) - sum(h for _d, h in quitar.values())
            consolidado = consolidacion.linea_ids.filtered(lambda ln: ln.tipo_columna == 'consolidado')
            self.assertCifra(sum(consolidado.mapped('debe')), debe, f'{nombre}: debe consolidado')
            self.assertCifra(sum(consolidado.mapped('haber')), haber, f'{nombre}: haber consolidado')
            self.assertCifra(sum(consolidado.mapped('debe')) - sum(consolidado.mapped('haber')), 0.0,
                             f'{nombre}: debe = haber')
            self.assertCifra(sum(consolidado.mapped('importe')), 0.0, f'{nombre}: saldos finales suman cero')
            self.assertCifra(sum(consolidado.mapped('inicial')), 0.0, f'{nombre}: saldos iniciales suman cero')
            self.assertTrue(consolidacion.cuadra, nombre)
            for campo in ('importe', 'inicial', 'debe', 'haber'):
                for ln in consolidado:
                    suma = sum(otra[campo] for otra in consolidacion.linea_ids
                               if otra.fila == ln.fila and otra.tipo_columna != 'consolidado')
                    self.assertCifra(ln[campo], suma, f'{nombre}: {ln.cuenta} {campo} = empresas + eliminaciones')


@tagged('post_install', '-at_install')
class TestAvisosDelConsolidado(AuditoriaConsolidacion):

    def pagos_sin_cruzar(self):
        """B le paga 400 a A por la factura de marzo: cada una lo registra en su banco y queda en «pendientes»."""
        diarios = {e: self.env['account.journal'].search([('company_id', '=', e.id), ('type', '=', 'bank')], limit=1)
                   for e in self.grupo}
        for factura, diario in ((self.venta_1, diarios[self.empresa_a]), (self.compra_1, diarios[self.empresa_b])):
            self.env['account.payment.register'].with_company(factura.company_id).with_context(
                active_model='account.move', active_ids=factura.ids).create({
                    'payment_date': '2030-03-20', 'journal_id': diario.id, 'amount': 400}).with_company(
                        factura.company_id)._create_payments()

    def test_dinero_en_transito_entre_empresas_se_avisa_y_el_balance_cuadra(self):
        sin_pagos = self.consolidacion('balance', fecha_desde='2030-01-01', fecha_hasta='2030-03-31')
        self.pagos_sin_cruzar()
        consolidacion = self.consolidacion('balance', fecha_desde='2030-01-01', fecha_hasta='2030-03-31')
        self.assertTrue(consolidacion.cuadra)
        self.assertTrue(consolidacion.advertencias)
        avisos = consolidacion.advertencias.splitlines()
        self.assertEqual(len(avisos), 2, avisos)            # el recibo pendiente de A y el pago pendiente de B
        self.assertTrue(all('no es por cobrar ni por pagar' in a for a in avisos))
        self.assertFalse([a for a in avisos if 'ITBMS' in a], 'el ITBMS nunca avisa')
        # Lo cobrado baja lo que A le cobra a B y lo que B le debe a A, por igual: -400 en las dos eliminaciones.
        antes, despues = self.eliminado_por_tipo(sin_pagos), self.eliminado_por_tipo(consolidacion)
        self.assertCifra(despues['asset_receivable'] - antes['asset_receivable'], 400.0)
        self.assertCifra(despues['liability_payable'] - antes['liability_payable'], 400.0)

    def test_el_descuadre_de_una_sola_empresa_se_avisa_con_numeros(self):
        """B nunca registró la factura de 250 de A: A dice que le deben 250 y B dice que no debe nada."""
        self.factura(self.empresa_a, self.empresa_b, 'out_invoice', 250, '2030-03-28', impuesto=False)
        consolidacion = self.consolidacion('balance', fecha_desde='2030-01-01', fecha_hasta='2030-03-31')
        self.assertFalse(consolidacion.cuadra)
        self.assertCifra(consolidacion.diferencia, -250.0, 'se eliminó el lado de A y no hay lado de B')
        moneda = self.empresa_a.currency_id
        self.assertIn(f'Descuadre entre {self.empresa_a.name} y {self.empresa_b.name} de {moneda.format(250.0)}',
                      consolidacion.advertencias)

    def test_las_cuentas_que_solo_tiene_una_empresa_no_se_pierden_y_la_nota_lo_dice(self):
        propia = self.env['account.account'].with_company(self.empresa_b).create({
            'name': 'Ventas exclusivas de la zona libre', 'code': '4999.ZL', 'account_type': 'income',
            'company_ids': [Command.set(self.empresa_b.ids)]})
        self.asiento(self.empresa_b, '2030-03-22', [(self.cuenta(self.empresa_b, 'asset_receivable'), 90, 0,
                                                     self.cliente), (propia, 0, 90, self.cliente)])
        consolidacion = self.consolidacion('resultados')
        fila = next(ln for ln in consolidacion.linea_ids if ln.codigo == '4999.ZL' and ln.tipo_columna == 'consolidado')
        self.assertCifra(fila.importe, 90.0, 'la cuenta aparece, no se pierde')
        self.assertIn('4999.ZL', consolidacion.cuentas_sin_equivalente)
        self.assertIn(self.empresa_b.name, consolidacion.cuentas_sin_equivalente)
        self.assertNotIn(self.cuenta(self.empresa_a, 'income').code, consolidacion.cuentas_sin_equivalente,
                         'las cuentas que están en las dos empresas no se notan')
        self.assertFalse(consolidacion.advertencias, 'es una nota, no una advertencia: nada está mal')
        self.assertIn('4999.ZL', consolidacion._matriz()['notas'][0], 'la nota sale en el PDF')
        # Ya decidida en el mapa (aunque sea dejarla sola): no hay nota.
        self.env['dcasa.consolidacion.mapa'].create({'company_id': self.empresa_b.id, 'account_id': propia.id,
                                                     'codigo_consolidado': '4999.ZL'})
        self.assertFalse(self.consolidacion('resultados').cuentas_sin_equivalente)
        # Si es la misma cuenta que la de A con otro código, el mapa las junta en una sola fila.
        mapa = self.env['dcasa.consolidacion.mapa'].search([('account_id', '=', propia.id)])
        mapa.codigo_consolidado = self.cuenta(self.empresa_a, 'income').code
        unida = self.consolidacion('resultados')
        filas = [ln for ln in unida.linea_ids if ln.tipo_columna == 'consolidado' and ln.seccion == 'ventas']
        self.assertEqual(len(filas), 1)
        self.assertCifra(filas[0].importe, 1500.0 + 90.0, 'las dos cuentas se suman en la misma fila')

    def test_una_cuenta_de_una_empresa_sin_saldo_en_el_periodo_no_genera_nota(self):
        self.env['account.account'].with_company(self.empresa_b).create({
            'name': 'Cuenta sin movimiento', 'code': '4998.ZL', 'account_type': 'income',
            'company_ids': [Command.set(self.empresa_b.ids)]})
        self.assertFalse(self.consolidacion('resultados').cuentas_sin_equivalente)


@tagged('post_install', '-at_install')
class TestAtajosDeFechasDeLaConsolidacion(AuditoriaConsolidacion):
    """«Hoy · Esta semana · Esta quincena · Este mes · Mes pasado · Este trimestre · Este año fiscal» en el formulario y
    en la lista de consolidaciones (los mismos de la barra de los reportes: todos terminan hoy menos «Mes pasado»)."""

    def fechas_con(self, atajo, hoy):
        with freeze_time(f'{hoy} 15:00:00'):
            with Form(self.env['dcasa.consolidacion']) as forma:
                forma.atajo_fechas = atajo
                return str(forma.fecha_desde), str(forma.fecha_hasta)

    def test_el_formulario_llena_el_desde_y_el_hasta(self):
        # Martes 14 de octubre de 2031.
        hoy = '2031-10-14'
        self.assertEqual(self.fechas_con('hoy', hoy), (hoy, hoy))
        self.assertEqual(self.fechas_con('semana', hoy), ('2031-10-13', hoy))
        self.assertEqual(self.fechas_con('quincena', hoy), ('2031-10-01', hoy))
        self.assertEqual(self.fechas_con('mes', hoy), ('2031-10-01', hoy))
        self.assertEqual(self.fechas_con('mes_pasado', hoy), ('2031-09-01', '2031-09-30'))
        self.assertEqual(self.fechas_con('trimestre', hoy), ('2031-10-01', hoy))
        self.assertEqual(self.fechas_con('ejercicio', hoy), ('2031-01-01', hoy))

    def test_bordes_de_semana_quincena_y_trimestre(self):
        self.assertEqual(self.fechas_con('semana', '2031-01-02'), ('2030-12-30', '2031-01-02'))     # cruza de año
        self.assertEqual(self.fechas_con('quincena', '2031-02-28'), ('2031-02-16', '2031-02-28'))   # febrero
        self.assertEqual(self.fechas_con('quincena', '2032-02-29'), ('2032-02-16', '2032-02-29'))   # bisiesto
        self.assertEqual(self.fechas_con('mes_pasado', '2031-03-01'), ('2031-02-01', '2031-02-28'))
        self.assertEqual(self.fechas_con('mes_pasado', '2031-01-05'), ('2030-12-01', '2030-12-31'))
        self.assertEqual(self.fechas_con('trimestre', '2031-03-31'), ('2031-01-01', '2031-03-31'))
        self.assertEqual(self.fechas_con('trimestre', '2031-04-01'), ('2031-04-01', '2031-04-01'))

    def test_el_hoy_es_el_de_panama(self):
        """A las 9 p. m. del 14 en Panamá ya es el 15 en UTC."""
        with freeze_time('2031-10-15 02:00:00'):
            with Form(self.env['dcasa.consolidacion']) as forma:
                forma.atajo_fechas = 'hoy'
                self.assertEqual(str(forma.fecha_hasta), '2031-10-14')

    def test_el_atajo_calculado_se_puede_calcular(self):
        with freeze_time('2031-10-14 15:00:00'):
            with Form(self.env['dcasa.consolidacion']) as forma:
                forma.name = 'Consolidado de la semana'
                forma.atajo_fechas = 'semana'
                consolidacion = forma.save()
        self.assertEqual((str(consolidacion.fecha_desde), str(consolidacion.fecha_hasta)), ('2031-10-13', '2031-10-14'))
        consolidacion.action_calcular()
        self.assertEqual(consolidacion.estado, 'calculada')

    def test_la_lista_filtra_las_consolidaciones_que_tocan_ese_periodo(self):
        Consolidacion = self.env['dcasa.consolidacion']
        datos = {'septiembre': ('2031-09-01', '2031-09-30'), 'octubre': ('2031-10-01', '2031-10-31'),
                 'hoy': ('2031-10-14', '2031-10-14'), 'ayer': ('2031-10-13', '2031-10-13'),
                 'manana': ('2031-10-15', '2031-10-15'), 'anio_pasado': ('2030-01-01', '2030-12-31')}
        creadas = {n: Consolidacion.create({'name': n, 'fecha_desde': d, 'fecha_hasta': h,
                                            'company_ids': [Command.set(self.empresa_a.ids)]})
                   for n, (d, h) in datos.items()}
        with freeze_time('2031-10-14 15:00:00'):
            def buscar(clave):
                return set(Consolidacion.search([('id', 'in', [c.id for c in creadas.values()]),
                                                 ('periodo_atajo', '=', clave)]).mapped('name'))

            self.assertEqual(buscar('hoy'), {'octubre', 'hoy'})
            self.assertEqual(buscar('semana'), {'octubre', 'hoy', 'ayer'})
            self.assertEqual(buscar('mes'), {'octubre', 'hoy', 'ayer'})
            self.assertEqual(buscar('mes_pasado'), {'septiembre'})
            self.assertEqual(buscar('ejercicio'), {'septiembre', 'octubre', 'hoy', 'ayer'})
        vista = Consolidacion.get_view(self.env.ref('dcasa_consolidacion.consolidacion_search').id, 'search')['arch']
        for clave in ('hoy', 'semana', 'quincena', 'mes', 'mes_pasado', 'trimestre', 'ejercicio'):
            self.assertIn(f'name="periodo_{clave}"', vista)
