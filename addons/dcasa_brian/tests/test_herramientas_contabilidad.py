"""Herramientas contables nuevas de Brian: resumen, antigüedad de saldos, comparativos y cierre de mes."""
from datetime import date

from odoo import Command
from odoo.addons.dcasa_contabilidad.tests import oraculo_sql as O
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestHerramientasContabilidad(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupos):
            return Usuarios.create({'name': login, 'login': login, 'group_ids': [
                Command.set([cls.env.ref(g).id for g in ('base.group_user', *grupos)])]})

        cls.vendedor = usuario('brian_c_vendedor', ('sales_team.group_sale_salesman',))
        cls.contador = usuario('brian_c_contador', ('account.group_account_user',))
        cls.gerente = usuario('brian_c_gerente', ('account.group_account_manager',))
        cls.cliente = cls.env['res.partner'].create({'name': 'Brianzeta Deudor', 'phone': '6123-4599'})
        impuesto = cls.env['brian.herramientas']._b_itbms_venta()
        cls.factura = cls.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cls.cliente.id, 'invoice_date': '2030-03-05',
            'invoice_date_due': '2030-03-05',
            'date': '2030-03-05',
            'invoice_line_ids': [Command.create({'name': 'Sofá', 'quantity': 1, 'price_unit': 100.0,
                                                 'tax_ids': [Command.set(impuesto.ids)]})]})
        cls.factura.action_post()

    def ejecutar(self, usuario, nombre, argumentos=None):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos or {})

    def ok(self, respuesta):
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']

    def test_vendedor_no_las_ve(self):
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedor).catalogo()}
        for nombre in ('resumen_contable', 'antiguedad_saldos', 'comparar_periodos', 'cerrar_mes'):
            self.assertNotIn(nombre, nombres)
        # cerrar_mes es de la gerencia contable: el contador no la tiene.
        del_contador = {h['name'] for h in self.env['brian.herramientas'].with_user(self.contador).catalogo()}
        self.assertIn('resumen_contable', del_contador)
        self.assertNotIn('cerrar_mes', del_contador)

    def test_cuanto_gane_y_quien_me_debe(self):
        datos = self.ok(self.ejecutar(self.contador, 'resumen_contable', {'desde': '01/03/2030',
                                                                           'hasta': '31/03/2030'}))
        self.assertEqual(datos['ventas']['monto'], '$100.00')
        self.assertEqual(datos['utilidad']['periodo_anterior'], '$0.00')
        # Ventas sin costo de ventas registrado: Brian no presenta la utilidad como ganancia.
        self.assertIn('no es ganancia', datos['utilidad']['aviso'])
        self.assertTrue(any('costo de ventas está en cero' in a for a in datos['alertas']), datos['alertas'])
        self.assertIn('a_favor_de_clientes', datos)
        resultados = self.ok(self.ejecutar(self.contador, 'reporte_contable', {
            'reporte': 'estado_resultados', 'desde': '01/03/2030', 'hasta': '31/03/2030'}))
        self.assertIn('no es la ganancia real', resultados['aviso'])
        self.assertIn('ITBMS por pagar: $7.00', datos['itbms'])
        self.assertIn('Brianzeta Deudor', [d['cliente'] for d in datos['quien_debe_mas']])
        deuda = self.ok(self.ejecutar(self.contador, 'antiguedad_saldos', {'fecha': '30/04/2030'}))
        fila = next(f for f in deuda['detalle'] if f['tercero'] == 'Brianzeta Deudor')
        self.assertEqual(fila['total'], '$107.00')
        self.assertEqual(fila['vencido'], '$107.00')
        self.assertIn('31 a 60 días', fila['tramos'])
        self.assertTrue(self.ok(self.ejecutar(self.contador, 'antiguedad_saldos', {'tipo': 'por_pagar'})))

    def test_comparar_y_flujo(self):
        datos = self.ok(self.ejecutar(self.contador, 'comparar_periodos', {
            'reporte': 'estado_resultados', 'desde': '01/03/2030', 'hasta': '31/03/2030'}))
        self.assertIn('Periodo anterior', datos['comparado_con'])
        ventas = datos['variaciones'][0]
        self.assertEqual((ventas['actual'], ventas['comparado'], ventas['variacion_pct']),
                         ('$100.00', '$0.00', 'sin base'))
        flujo = self.ok(self.ejecutar(self.contador, 'reporte_contable', {
            'reporte': 'flujo_efectivo', 'desde': '01/03/2030', 'hasta': '31/03/2030'}))
        self.assertEqual(flujo['cuadra'], 'sí')
        respuesta = self.ejecutar(self.contador, 'comparar_periodos', {'reporte': 'itbms'})
        self.assertFalse(respuesta['ok'])

    def test_cerrar_mes_pide_confirmacion(self):
        fin = '2030-03-31'
        self.env['account.bank.statement.line'].search([('is_reconciled', '=', False), ('date', '<=', fin)]).unlink()
        self.env['account.move'].search([('state', '=', 'draft'), ('date', '<=', fin)]).unlink()
        respuesta = self.ejecutar(self.gerente, 'cerrar_mes', {'mes': '03/2030'})
        self.assertTrue(respuesta.get('requiere_confirmacion'), respuesta)
        self.assertFalse(self.env.company.fiscalyear_lock_date)  # nada pasa sin el clic
        datos = self.ok(self.env['brian.herramientas'].with_user(self.gerente).confirmar(respuesta['accion_id']))
        self.assertIn('Marzo 2030 cerrado', datos['mensaje'])
        self.assertEqual(self.env.company.fiscalyear_lock_date, date(2030, 3, 31))
        guia = self.ok(self.ejecutar(self.gerente, 'guia_cierre_mes', {'mes': '03/2030'}))
        self.assertEqual(guia['mes_cerrado'], 'sí')
        otra = self.env['brian.herramientas'].with_user(self.gerente).confirmar(
            self.ejecutar(self.gerente, 'cerrar_mes', {'mes': '03/2030'})['accion_id'])
        self.assertFalse(otra['ok'])
        self.assertIn('ya está cerrado', otra['error'])

    def _cobro_en_caja_sin_cruzar(self, monto=50.0):
        """«Registrar pago» en efectivo: queda en Recibos pendientes hasta que se cruza con el movimiento de la caja."""
        efectivo = self.env['account.journal'].search([('type', '=', 'cash'),
                                                       ('company_id', '=', self.env.company.id)], limit=1)
        pagos = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=self.factura.ids).create({
                'payment_date': '2030-03-20', 'journal_id': efectivo.id, 'amount': monto})._create_payments()
        # Que no quede nada más por conciliar en el extracto: solo el cobro de la caja espera.
        self.env['account.bank.statement.line'].search(
            [('is_reconciled', '=', False), ('date', '<=', '2030-03-31')]).unlink()
        return pagos

    def test_la_guia_de_cierre_ve_los_cobros_registrados_sin_cruzar(self):
        """Antes solo contaba los movimientos del extracto: con el extracto al día decía «Todo conciliado»."""
        pago = self._cobro_en_caja_sin_cruzar(50.0)
        guia = self.ok(self.ejecutar(self.contador, 'guia_cierre_mes', {'mes': '03/2030'}))
        paso = guia['pasos'][0]
        self.assertEqual(paso['tarea'], 'Conciliar bancos, Yappy y caja')
        self.assertEqual(paso['estado'], 'pendiente')
        self.assertIn('1 cobro sin cruzar ($50.00)', paso['detalle'])
        self.assertIn('Cobros y pagos sin movimiento', paso['como'])
        self.assertNotIn('Todo conciliado', paso['detalle'])
        # Es lo mismo que dice el paso del cierre de mes y la tarjeta del Resumen (una sola fuente).
        cierre = self.env['dcasa.cierre.mes'].create({'mes': '2030-03-01'})
        detalle = cierre.paso_ids.filtered(lambda p: p.codigo == 'conciliacion').detalle
        self.assertEqual(paso['detalle'], detalle)
        # Cerrar el mes tampoco pasa por alto el cobro.
        respuesta = self.ejecutar(self.gerente, 'cerrar_mes', {'mes': '03/2030'})
        resultado = self.env['brian.herramientas'].with_user(self.gerente).confirmar(respuesta['accion_id'])
        self.assertFalse(resultado['ok'])
        self.assertIn('1 cobro sin cruzar ($50.00)', resultado['error'])
        self.assertFalse(self.env.company.fiscalyear_lock_date)
        # Se cruza con el movimiento de la caja y el paso queda listo.
        self.env['dcasa.conciliacion'].cruzar_pago(pago.id)
        guia = self.ok(self.ejecutar(self.contador, 'guia_cierre_mes', {'mes': '03/2030'}))
        self.assertEqual((guia['pasos'][0]['estado'], guia['pasos'][0]['detalle']), ('listo', 'Todo conciliado'))

    # ------------------------------------------------------------------
    # ITBMS acumulado
    # ------------------------------------------------------------------

    def _itbms_con_historia(self):
        """Marzo trae una venta con ITBMS (la del setUp: $7.00). Se suman una venta de febrero ($14.00, mes anterior) y
        un pago de $5.00 a la DGI el 20 de marzo. Devuelve el acumulado de los apuntes al 31/03 ANTES de eso."""
        empresa = self.env.company
        antes = sum(O.itbms_acumulado(self.env, empresa, '2030-03-31').values())
        impuesto = self.env['brian.herramientas']._b_itbms_venta()
        self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2030-02-10',
            'invoice_date_due': '2030-02-10', 'date': '2030-02-10',
            'invoice_line_ids': [Command.create({'name': 'Mesa', 'quantity': 1, 'price_unit': 200.0,
                                                 'tax_ids': [Command.set(impuesto.ids)]})]}).action_post()
        self._pagar_itbms(5.0)
        return antes

    def _pagar_itbms(self, monto, fecha='2030-03-20'):
        empresa = self.env.company
        cuenta = self.env['account.account'].browse(sorted(O.itbms_acumulado(self.env, empresa, fecha))[0])
        banco = self.env['account.journal'].search([('type', '=', 'bank'), ('company_id', '=', empresa.id)], limit=1)
        diario = self.env['account.journal'].search([('type', '=', 'general'), ('company_id', '=', empresa.id)],
                                                    limit=1)
        self.env['account.move'].create({
            'move_type': 'entry', 'date': fecha, 'journal_id': diario.id, 'line_ids': [
                Command.create({'account_id': cuenta.id, 'debit': monto, 'credit': 0.0, 'name': 'Pago de ITBMS'}),
                Command.create({'account_id': banco.default_account_id.id, 'debit': 0.0, 'credit': monto,
                                'name': 'Pago de ITBMS'})]}).action_post()

    def test_itbms_acumulado_en_el_resumen_y_en_el_reporte(self):
        """«¿Cuánto ITBMS debo EN TOTAL?»: el del periodo ($7.00 de marzo) no es el total: falta febrero y el pago."""
        antes = self._itbms_con_historia()
        total = sum(O.itbms_acumulado(self.env, self.env.company, '2030-03-31').values())
        self.assertAlmostEqual(total - antes, 14.0 - 5.0, places=2, msg='febrero suma 14 y el pago resta 5')
        esperado = f'Acumulado por pagar al 31/03/2030: ${total:,.2f}'
        resumen = self.ok(self.ejecutar(self.contador, 'resumen_contable', {'desde': '01/03/2030',
                                                                             'hasta': '31/03/2030'}))
        self.assertEqual(resumen['itbms_acumulado'], esperado)
        self.assertEqual(resumen['itbms_acumulado_por_pagar'], f'${total:,.2f}')
        self.assertEqual(resumen['itbms_saldo_a_favor'], '$0.00')
        self.assertIn('ITBMS por pagar: $7.00', resumen['itbms'], 'lo del periodo sigue como estaba')
        self.assertIn('itbms_acumulado', resumen['nota'])
        reporte = self.ok(self.ejecutar(self.contador, 'reporte_contable', {
            'reporte': 'itbms', 'desde': '01/03/2030', 'hasta': '31/03/2030'}))
        self.assertEqual(reporte['itbms_acumulado'], esperado)
        self.assertEqual(reporte['a_pagar'], '$7.00')
        self.assertIn('del periodo', reporte['a_pagar_es_del_periodo'])
        self.assertEqual(reporte['debito_fiscal_ventas'], '$7.00')
        self.assertTrue(reporte['cuentas_de_itbms'], 'dice en qué cuentas está el saldo')
        # La fecha del acumulado es la fecha final que se pidió (el 15 de marzo aún no había pago).
        a_mitad = self.ok(self.ejecutar(self.contador, 'resumen_contable', {'desde': '01/03/2030',
                                                                             'hasta': '15/03/2030'}))
        al_15 = sum(O.itbms_acumulado(self.env, self.env.company, '2030-03-15').values())
        self.assertEqual(a_mitad['itbms_acumulado'], f'Acumulado por pagar al 15/03/2030: ${al_15:,.2f}')

    def test_itbms_saldo_a_favor(self):
        self._itbms_con_historia()
        total = sum(O.itbms_acumulado(self.env, self.env.company, '2030-03-31').values())
        self._pagar_itbms(total + 25.0, fecha='2030-03-25')       # se pagó de más
        resumen = self.ok(self.ejecutar(self.contador, 'resumen_contable', {'desde': '01/03/2030',
                                                                             'hasta': '31/03/2030'}))
        self.assertEqual(resumen['itbms_acumulado'], 'Saldo a favor al 31/03/2030: $25.00')
        self.assertEqual((resumen['itbms_acumulado_por_pagar'], resumen['itbms_saldo_a_favor']), ('$0.00', '$25.00'))
        reporte = self.ok(self.ejecutar(self.contador, 'reporte_contable', {
            'reporte': 'itbms', 'desde': '01/03/2030', 'hasta': '31/03/2030'}))
        self.assertEqual(reporte['itbms_acumulado'], 'Saldo a favor al 31/03/2030: $25.00')
        self.assertIn('ITBMS por pagar: $7.00', resumen['itbms'], 'el periodo sigue «por pagar»')

    def test_las_herramientas_de_itbms_dicen_como_preguntar_el_total(self):
        catalogo = {h['name']: h for h in self.env['brian.herramientas'].with_user(self.contador).catalogo()}
        for nombre in ('resumen_contable', 'reporte_contable'):
            texto = catalogo[nombre]['description']
            self.assertIn('acumulado', texto, nombre)
            self.assertIn('ITBMS debo en total', texto, nombre)
        # Un vendedor no ve ninguna de las dos (nivel lectura contable).
        vendedor = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedor).catalogo()}
        self.assertFalse({'resumen_contable', 'reporte_contable'} & vendedor)

    # ------------------------------------------------------------------
    # Movimientos por conciliar: también los cobros y pagos que esperan su movimiento
    # ------------------------------------------------------------------

    def _sql_sin_cruzar(self):
        """{tipo: (cantidad, monto)} de los cobros y pagos registrados sin su movimiento, directo de la base."""
        self.env.flush_all()
        self.env.cr.execute("""
            SELECT p.payment_type, COUNT(*), COALESCE(SUM(p.amount), 0)
              FROM account_payment p JOIN account_journal j ON j.id = p.journal_id
             WHERE p.is_matched IS NOT TRUE AND p.state IN ('in_process', 'paid') AND j.type IN ('bank', 'cash')
               AND p.company_id = %s
             GROUP BY p.payment_type""", [self.env.company.id])
        return {tipo: (n, float(monto)) for tipo, n, monto in self.env.cr.fetchall()}

    def _pago_a_proveedor_sin_cruzar(self, monto=30.0):
        proveedor = self.env['res.partner'].create({'name': 'Brianzeta Proveedor'})
        compra = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': proveedor.id, 'invoice_date': '2030-03-08', 'date': '2030-03-08',
            'invoice_line_ids': [Command.create({'name': 'Flete', 'quantity': 1, 'price_unit': 100.0,
                                                 'tax_ids': [Command.clear()]})]})
        compra.action_post()
        banco = self.env['account.journal'].search([('type', '=', 'bank'),
                                                    ('company_id', '=', self.env.company.id)], limit=1)
        return self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=compra.ids).create({
                'payment_date': '2030-03-21', 'journal_id': banco.id, 'amount': monto})._create_payments()

    def test_movimientos_por_conciliar_suma_los_cobros_y_pagos_sin_cruzar(self):
        efectivo_pago = self._cobro_en_caja_sin_cruzar(50.0)
        self._pago_a_proveedor_sin_cruzar(30.0)
        banco = self.env['account.journal'].search([('type', '=', 'bank'),
                                                    ('company_id', '=', self.env.company.id)], limit=1)
        self.env['account.bank.statement.line'].create({
            'journal_id': banco.id, 'date': '2030-03-22', 'amount': 250.0, 'payment_ref': 'DEPOSITO SUELTO'})
        sql = self._sql_sin_cruzar()
        datos = self.ok(self.ejecutar(self.contador, 'movimientos_por_conciliar'))
        # Lo de siempre: los movimientos del extracto.
        self.assertEqual(datos['por_conciliar'], 1)
        self.assertEqual([m['concepto'] for m in datos['movimientos']], ['DEPOSITO SUELTO'])
        # Lo nuevo: cuántos cobros y pagos esperan su movimiento y de cuánto (contra el conteo aparte en SQL).
        self.assertEqual(datos['cobros_sin_cruzar']['cantidad'], sql['inbound'][0])
        self.assertEqual(datos['pagos_sin_cruzar']['cantidad'], sql['outbound'][0])
        self.assertEqual(datos['cobros_sin_cruzar']['monto'], f'${sql["inbound"][1]:,.2f}')
        self.assertEqual(datos['pagos_sin_cruzar']['monto'], f'${sql["outbound"][1]:,.2f}')
        self.assertIn('$50.00', datos['cobros_sin_cruzar']['monto'])
        self.assertEqual({(f['tipo'], f['monto']) for f in datos['cobros_y_pagos']}, {('cobro', '$50.00'),
                                                                                    ('pago', '$30.00')})
        cobro = next(f for f in datos['cobros_y_pagos'] if f['tipo'] == 'cobro')
        self.assertEqual((cobro['banco'], cobro['tercero'], cobro['factura']),
                         (efectivo_pago.journal_id.name, 'Brianzeta Deudor', self.factura.name))
        por_banco = {b['banco']: b for b in datos['por_banco']}
        self.assertEqual(por_banco[efectivo_pago.journal_id.name]['cobros_y_pagos_sin_cruzar'], 1)
        self.assertEqual(por_banco[banco.name]['cobros_y_pagos_sin_cruzar'], 1)
        self.assertIn('Cobros y pagos sin movimiento', datos['como_cruzarlos'])

    def test_movimientos_por_conciliar_respeta_el_banco_y_el_limite(self):
        pago = self._cobro_en_caja_sin_cruzar(50.0)
        self._pago_a_proveedor_sin_cruzar(30.0)
        solo_caja = self.ok(self.ejecutar(self.contador, 'movimientos_por_conciliar',
                                          {'banco': pago.journal_id.name}))
        self.assertEqual((solo_caja['cobros_sin_cruzar']['cantidad'], solo_caja['pagos_sin_cruzar']['cantidad']),
                         (1, 0))
        self.assertEqual([f['tipo'] for f in solo_caja['cobros_y_pagos']], ['cobro'])
        # El límite recorta la lista, no las cuentas.
        corto = self.ok(self.ejecutar(self.contador, 'movimientos_por_conciliar', {'limite': 1}))
        self.assertEqual(len(corto['cobros_y_pagos']), 1)
        self.assertEqual(corto['cobros_sin_cruzar']['cantidad'] + corto['pagos_sin_cruzar']['cantidad'], 2)

    def test_sin_cobros_pendientes_no_hay_nada_que_cruzar(self):
        datos = self.ok(self.ejecutar(self.contador, 'movimientos_por_conciliar'))
        self.assertEqual(datos['cobros_sin_cruzar'], {'cantidad': 0, 'monto': '$0.00'})
        self.assertEqual(datos['cobros_y_pagos'], [])
        self.assertNotIn('como_cruzarlos', datos)
        pago = self._cobro_en_caja_sin_cruzar(50.0)
        self.env['dcasa.conciliacion'].cruzar_pago(pago.id)
        despues = self.ok(self.ejecutar(self.contador, 'movimientos_por_conciliar'))
        self.assertEqual(despues['cobros_sin_cruzar'], {'cantidad': 0, 'monto': '$0.00'})

    def test_movimientos_por_conciliar_sigue_siendo_solo_para_contabilidad(self):
        self._cobro_en_caja_sin_cruzar(50.0)
        respuesta = self.ejecutar(self.vendedor, 'movimientos_por_conciliar')
        self.assertFalse(respuesta['ok'], respuesta)
        self.assertNotIn('cobros_y_pagos', str(respuesta))
