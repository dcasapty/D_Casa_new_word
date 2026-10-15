"""Cierre de mes y conciliación: un cobro registrado que espera su movimiento ya no pasa como «Todo conciliado».

El punto ciego: el paso «Bancos conciliados» del cierre (y la guía de cierre de Brian) solo miraban los movimientos del
extracto sin conciliar. Un cobro registrado con «Registrar pago» queda en «Recibos pendientes» y no suma al dinero del
banco hasta que se cruza con su movimiento; con el extracto al día, el cierre decía «Todo conciliado» y el cobro
quedaba fuera de la vista. Aquí se comprueba, contra un conteo hecho aparte en SQL, que el cierre, la tarjeta del
Resumen y la pantalla de Conciliación ven lo mismo, y que lo que esperaba se puede cruzar desde la pantalla.
"""
from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .test_auditoria import ANIO, HOY, AuditoriaCommon


def f(mes, dia):
    return f'{ANIO}-{mes:02d}-{dia:02d}'


class CierreCommon(AuditoriaCommon):

    def setUp(self):
        super().setUp()
        self.Cierre = self.env['dcasa.cierre.mes']
        self.Conc = self.env['dcasa.conciliacion']

    # -- el cálculo de referencia, directo en SQL ------------------------------------------------------------------

    def sql_por_cruzar(self, fin):
        """{diario_id: {'movimientos', 'cobros', 'monto_cobros', 'egresos', 'monto_egresos'}} con fecha hasta ``fin``."""
        self.env.flush_all()        # el SQL lee la base: que el ORM escriba antes lo pendiente
        cr = self.env.cr
        resultado = {}
        cr.execute("""
            SELECT l.journal_id, COUNT(*)
              FROM account_bank_statement_line l JOIN account_move m ON m.id = l.move_id
             WHERE NOT l.is_reconciled AND m.date <= %s AND m.company_id = %s
             GROUP BY l.journal_id""", [fin, self.company.id])
        for diario, n in cr.fetchall():
            resultado.setdefault(diario, {})['movimientos'] = n
        cr.execute("""
            SELECT p.journal_id, p.payment_type, COUNT(*), COALESCE(SUM(p.amount), 0)
              FROM account_payment p
              JOIN account_journal j ON j.id = p.journal_id
             WHERE p.is_matched IS NOT TRUE AND p.state IN ('in_process', 'paid') AND j.type IN ('bank', 'cash')
               AND p.date <= %s AND p.company_id = %s
             GROUP BY p.journal_id, p.payment_type""", [fin, self.company.id])
        for diario, tipo, n, monto in cr.fetchall():
            clave = 'cobros' if tipo == 'inbound' else 'egresos'
            resultado.setdefault(diario, {})[clave] = n
            resultado[diario]['monto_' + clave] = float(monto)
        return resultado

    def esperado(self, fin):
        """El mismo texto del cierre, armado a mano a partir del SQL (solo diarios con algo pendiente)."""
        diarios = self.env['account.journal'].browse(self.sql_por_cruzar(fin))
        partes = []
        for diario in diarios.sorted(lambda d: d.id):
            nums = self.sql_por_cruzar(fin)[diario.id]
            cosas = []
            if nums.get('movimientos'):
                cosas.append(f"{nums['movimientos']} movimiento{'s' if nums['movimientos'] != 1 else ''} sin conciliar")
            if nums.get('cobros'):
                cosas.append(f"{nums['cobros']} cobro{'s' if nums['cobros'] != 1 else ''} sin cruzar "
                             f"(${nums['monto_cobros']:,.2f})")
            if nums.get('egresos'):
                cosas.append(f"{nums['egresos']} pago{'s' if nums['egresos'] != 1 else ''} sin cruzar "
                             f"(${nums['monto_egresos']:,.2f})")
            partes.append(f'{diario.name}: {" · ".join(cosas)}')
        return partes

    def paso_bancos(self, cierre):
        return cierre.paso_ids.filtered(lambda p: p.codigo == 'conciliacion')


@tagged('post_install', '-at_install')
class TestCierreVeLosCobrosSinCruzar(CierreCommon):

    def test_el_paso_de_bancos_cuenta_movimientos_cobros_y_pagos_contra_sql(self):
        # Un pago a proveedor también espera su movimiento (sale de «Pagos pendientes»).
        self.datos.pago_registrado(self.datos.e5, f(10, 10), monto=100, diario=self.datos.banco)
        cierre = self.Cierre.create({'mes': f'{ANIO}-10-01'})
        paso = self.paso_bancos(cierre)
        sql = self.sql_por_cruzar(f(10, 31))
        efectivo, banco = sql[self.datos.efectivo.id], sql[self.datos.banco.id]
        # Lo que los datos de prueba agregan: el cobro de $200 en la caja, el pago de $100 en el banco y el
        # depósito suelto de $250 sin conciliar.
        self.assertGreaterEqual(efectivo['monto_cobros'], 200.0)
        self.assertGreaterEqual(banco['monto_egresos'], 100.0)
        self.assertEqual(paso.estado, 'pendiente')
        self.assertTrue(paso.bloquea)
        for parte in self.esperado(f(10, 31)):
            self.assertIn(parte, paso.detalle, 'el detalle dice lo mismo que el conteo aparte')
        total = sum(v.get('movimientos', 0) + v.get('cobros', 0) + v.get('egresos', 0) for v in sql.values())
        datos = self.Cierre._bancos_por_cruzar(f(10, 31))
        self.assertEqual(datos['pendientes'], total)
        self.assertEqual(datos['cobros'], sum(v.get('cobros', 0) for v in sql.values()))
        self.assertEqual(datos['egresos'], sum(v.get('egresos', 0) for v in sql.values()))
        self.assertAlmostEqual(datos['monto_cobros'], sum(v.get('monto_cobros', 0) for v in sql.values()), places=2)
        self.assertAlmostEqual(datos['monto_egresos'], sum(v.get('monto_egresos', 0) for v in sql.values()), places=2)

    def test_con_el_extracto_al_dia_el_cobro_registrado_ya_no_se_pierde(self):
        """El caso del hallazgo: extracto sin nada por conciliar y $200 de caja esperando su movimiento."""
        otros = self.env['account.account'].search([('account_type', '=', 'income_other'),
                                                    ('company_ids', 'in', self.company.ids)], limit=1)
        self.datos.deposito_suelto.dcasa_conciliar(cuenta_id=otros.id, etiqueta='Intereses')
        self.env['account.bank.statement.line'].search(
            [('is_reconciled', '=', False), ('date', '<=', f(10, 31))]).unlink()   # nada del extracto por conciliar
        movimientos_viejo = self.env['account.bank.statement.line'].search_count(
            [('is_reconciled', '=', False), ('date', '<=', f(10, 31))])
        self.assertEqual(movimientos_viejo, 0, 'así lo veía el cierre antes: todo conciliado')
        cierre = self.Cierre.create({'mes': f'{ANIO}-10-01'})
        paso = self.paso_bancos(cierre)
        self.assertEqual(paso.estado, 'pendiente')
        self.assertNotEqual(paso.detalle, 'Todo conciliado')
        self.assertIn(f'{self.datos.efectivo.name}: ', paso.detalle)
        self.assertIn('sin cruzar ($', paso.detalle)
        with self.assertRaises(UserError) as error:
            cierre.action_cerrar()
        self.assertIn('Bancos, Yappy, tarjeta y caja conciliados', str(error.exception))

    def test_cruzar_el_cobro_deja_el_paso_listo(self):
        """Con el cobro cruzado y el depósito conciliado, el paso queda como estaba la base antes de los datos."""
        base = {d: v for d, v in self.sql_por_cruzar(f(10, 31)).items()}
        otros = self.env['account.account'].search([('account_type', '=', 'income_other'),
                                                    ('company_ids', 'in', self.company.ids)], limit=1)
        self.datos.deposito_suelto.dcasa_conciliar(cuenta_id=otros.id, etiqueta='Intereses')
        self.Conc.cruzar_pago(self.datos.abono_caja.id)
        despues = self.sql_por_cruzar(f(10, 31))
        self.assertEqual(despues.get(self.datos.efectivo.id, {}).get('cobros', 0),
                         base.get(self.datos.efectivo.id, {}).get('cobros', 0) - 1)
        cierre = self.Cierre.create({'mes': f'{ANIO}-10-01'})
        paso = self.paso_bancos(cierre)
        if not despues:        # base limpia: no queda nada por cruzar en ningún diario
            self.assertEqual((paso.estado, paso.detalle), ('listo', 'Todo conciliado'))
        else:
            for parte in self.esperado(f(10, 31)):
                self.assertIn(parte, paso.detalle)
            self.assertNotIn('cobro sin cruzar ($200.00)', paso.detalle)

    def test_el_cierre_la_tarjeta_y_la_pantalla_ven_lo_mismo(self):
        datos = self.Cierre._bancos_por_cruzar(HOY)
        tarjeta = next(t for t in self.reportes.obtener('resumen', f(10, 1), HOY)['tarjetas'] if t['clave'] == 'bancos')
        self.assertEqual(datos['movimientos'], tarjeta['sin_conciliar'])
        self.assertEqual(datos['cobros'] + datos['egresos'], tarjeta['pagos_sin_cruzar'])
        self.assertAlmostEqual(datos['monto_cobros'] - datos['monto_egresos'], tarjeta['monto_sin_cruzar'], places=2)
        # La pantalla: lo que lista «Cobros y pagos sin movimiento» es lo que cuentan el cierre y la tarjeta.
        pantalla = self.Conc.diarios()
        self.assertEqual(sum(d['pagos_sin_cruzar'] for d in pantalla), datos['cobros'] + datos['egresos'])
        mostrados = [p for d in pantalla for p in self.Conc.pagos_por_cruzar(d['id'])]
        self.assertEqual(len(mostrados), datos['cobros'] + datos['egresos'])
        self.assertAlmostEqual(sum(p['monto'] for p in mostrados), datos['monto_cobros'] - datos['monto_egresos'],
                               places=2)
        # Y la lista por diario es la misma regla que la cuenta del reporte (no se separan con el tiempo).
        for fila in self.reportes._saldos_bancos(HOY):
            if fila['id']:
                esperando = self.env['account.payment']._dcasa_esperan_su_movimiento(
                    hasta=HOY, diarios=self.env['account.journal'].browse(fila['id']))
                entradas = esperando.filtered(lambda p: p.payment_type == 'inbound')
                self.assertEqual((fila['cobros'], fila['egresos']), (len(entradas), len(esperando - entradas)),
                                 fila['nombre'])
                self.assertAlmostEqual(fila['monto_cobros'], sum(entradas.mapped('amount_signed')), places=2)

    def test_ver_abre_la_pantalla_de_conciliacion(self):
        cierre = self.Cierre.create({'mes': f'{ANIO}-10-01'})
        accion = self.paso_bancos(cierre).action_ver()
        self.assertEqual((accion['type'], accion['tag']), ('ir.actions.client', 'dcasa_conciliacion'))

    def test_el_cierre_de_una_empresa_no_mezcla_las_otras(self):
        """El paso de bancos mira solo la empresa que se cierra, aunque haya otra empresa activa."""
        otra = self.env['res.company'].create({'name': 'Otra empresa del cierre'})
        datos = self.Cierre.with_context(allowed_company_ids=[self.company.id, otra.id])._bancos_por_cruzar(
            HOY, self.company)
        solo = self.Cierre._bancos_por_cruzar(HOY, self.company)
        self.assertEqual(datos['pendientes'], solo['pendientes'])
        self.assertEqual(datos['detalle'], solo['detalle'])


@tagged('post_install', '-at_install')
class TestCruzarCobrosYPagos(CierreCommon):
    """La mejora de la pantalla de Conciliación: ver y cruzar lo que esperaba su movimiento."""

    def saldo(self, cuenta, **kw):
        sumas = self.env['account.move.line']._read_group(
            [('account_id', '=', cuenta.id), ('parent_state', '=', 'posted'), ('date', '<=', kw.get('hasta', HOY))],
            [], ['balance:sum'])
        return sumas[0][0] or 0.0

    def test_la_pantalla_lista_el_cobro_de_la_caja(self):
        filas = self.Conc.pagos_por_cruzar(self.datos.efectivo.id)
        fila = next(p for p in filas if p['id'] == self.datos.abono_caja.id)
        self.assertEqual((fila['tipo'], fila['monto'], fila['fecha']), ('cobro', 200.0, f(10, 6)))
        self.assertEqual(fila['tercero'], self.datos.c1.name)
        self.assertEqual(fila['facturas'], self.datos.e4.name)
        # El cobro del banco ya cruzado con su movimiento (pago_conciliado) NO aparece.
        banco = self.Conc.pagos_por_cruzar(self.datos.banco.id)
        self.assertNotIn(self.datos.pago_conciliado.id, [p['id'] for p in banco])
        por_diario = {d['id']: d['pagos_sin_cruzar'] for d in self.Conc.diarios()}
        self.assertEqual(por_diario[self.datos.efectivo.id], len(filas))

    def test_cruzar_un_cobro_mete_el_dinero_a_la_caja_y_lo_saca_de_recibos_pendientes(self):
        pago, efectivo = self.datos.abono_caja, self.datos.cuenta_caja
        pendientes = pago.outstanding_account_id
        caja_antes, pendientes_antes = self.saldo(efectivo), self.saldo(pendientes)
        factura_antes = self.datos.e4.amount_residual
        resultado = self.Conc.cruzar_pago(pago.id)
        self.assertTrue(resultado['conciliado'])
        self.assertFalse(resultado['fecha_ajustada'])
        self.assertAlmostEqual(self.saldo(efectivo) - caja_antes, 200.0, places=2, msg='entra a la caja')
        self.assertAlmostEqual(self.saldo(pendientes) - pendientes_antes, -200.0, places=2,
                               msg='sale de recibos pendientes')
        self.assertTrue(pago.is_matched)
        self.assertEqual(self.datos.e4.amount_residual, factura_antes, 'la factura no se toca: ya estaba abonada')
        linea = self.env['account.bank.statement.line'].search([('payment_ref', 'like', self.datos.c1.name),
                                                                 ('journal_id', '=', self.datos.efectivo.id)])
        self.assertEqual((linea.amount, str(linea.date), linea.is_reconciled), (200.0, f(10, 6), True))
        self.assertNotIn(pago.id, [p['id'] for p in self.Conc.pagos_por_cruzar(self.datos.efectivo.id)])
        # El dinero de la tarjeta sigue igual al efectivo de los apuntes (contra el cálculo aparte).
        tarjeta = next(t for t in self.reportes.obtener('resumen', f(10, 1), HOY)['tarjetas'] if t['clave'] == 'bancos')
        self.assertAlmostEqual(tarjeta['valor'], self.efectivo(hasta=HOY), places=2)
        with self.assertRaises(UserError):
            self.Conc.cruzar_pago(pago.id)       # ya no espera nada

    def test_cruzar_un_pago_a_proveedor_saca_el_dinero_del_banco(self):
        pago = self.datos.pago_registrado(self.datos.e5, f(10, 10), monto=100, diario=self.datos.banco)
        fila = next(p for p in self.Conc.pagos_por_cruzar(self.datos.banco.id) if p['id'] == pago.id)
        self.assertEqual((fila['tipo'], fila['monto']), ('pago', -100.0))
        banco_antes = self.saldo(self.datos.cuenta_banco)
        self.Conc.cruzar_pago(pago.id)
        self.assertAlmostEqual(self.saldo(self.datos.cuenta_banco) - banco_antes, -100.0, places=2)
        self.assertTrue(pago.is_matched)

    def test_en_un_mes_cerrado_el_movimiento_lleva_el_primer_dia_abierto(self):
        self.company.fiscalyear_lock_date = date(ANIO, 10, 6)
        resultado = self.Conc.cruzar_pago(self.datos.abono_caja.id)
        self.assertTrue(resultado['fecha_ajustada'])
        self.assertEqual(resultado['fecha'], f(10, 7))
        self.assertTrue(self.datos.abono_caja.is_matched)

    def test_solo_contabilidad_cruza(self):
        sin_permiso = new_test_user(self.env, login='sin_conta_cruzar', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.Conc.with_user(sin_permiso).pagos_por_cruzar(self.datos.efectivo.id)
        with self.assertRaises(AccessError):
            self.Conc.with_user(sin_permiso).cruzar_pago(self.datos.abono_caja.id)
        self.assertFalse(self.datos.abono_caja.is_matched)

    def test_un_pago_que_no_existe_no_se_cruza(self):
        with self.assertRaises(UserError):
            self.Conc.cruzar_pago(0)
