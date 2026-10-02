"""Fase 1 de la contabilidad: comparativos, flujo de efectivo, antigüedad de saldos, resumen,
cierre de mes con bloqueo, reglas de conciliación e importación de extractos (CSV con formato,
OFX y CAMT)."""
import base64
from datetime import date

from odoo.addons.dcasa_contabilidad.controllers.main import libro_excel
from odoo.addons.dcasa_contabilidad.wizard.importar_extracto import leer_camt, leer_csv, leer_ofx
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .test_contabilidad import DESDE, HASTA, ContabilidadCommon

OFX = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX>
<BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>USD
<BANKTRANLIST><DTSTART>20300301<DTEND>20300331
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20300320120000<TRNAMT>107.00<FITID>BG-0001<NAME>ACH RECIBIDO<MEMO>%s
</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20300321<TRNAMT>-1.25<FITID>BG-0002<NAME>COMISION ACH
</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL><BALAMT>9999.99<DTASOF>20300331</LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1>
</OFX>
"""

CAMT = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt><Stmt>
<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="USD">500.00</Amt><CdtDbtInd>CRDT</CdtDbtInd></Bal>
<Ntry><Amt Ccy="USD">40.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2030-03-22</Dt></BookgDt>
<AcctSvcrRef>C-1</AcctSvcrRef><NtryDtls><TxDtls><RmtInf><Ustrd>PAGO LUZ</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
<Ntry><Amt Ccy="USD">15.50</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2030-03-23</Dt></BookgDt>
<AcctSvcrRef>C-2</AcctSvcrRef><AddtlNtryInf>INTERESES</AddtlNtryInf></Ntry>
</Stmt></BkToCstmrStmt></Document>
"""


@tagged('post_install', '-at_install')
class TestFase1(ContabilidadCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Cuenta = cls.env['account.account']
        cls.gasto = Cuenta.search([('account_type', '=', 'expense'), ('company_ids', 'in', cls.company.ids)],
                                  limit=1)
        cls.capital = Cuenta.create({'name': 'Capital prueba', 'code': '9T0001', 'account_type': 'equity'})
        cls.mobiliario = Cuenta.create({'name': 'Mobiliario prueba', 'code': '9T0002', 'account_type': 'asset_fixed'})
        cls.caja_banco = cls.banco.default_account_id

    def _asiento(self, fecha, lineas):
        """Asiento manual publicado: [(cuenta, debe, haber)]."""
        asiento = self.env['account.move'].create({
            'move_type': 'entry', 'date': fecha, 'journal_id': self.env['account.journal'].search(
                [('type', '=', 'general'), ('company_id', '=', self.company.id)], limit=1).id,
            'line_ids': [(0, 0, {'account_id': cuenta.id, 'debit': debe, 'credit': haber, 'name': 'prueba'})
                         for cuenta, debe, haber in lineas],
        })
        asiento.action_post()
        return asiento

    def _cobrar(self, factura, fecha='2030-03-15', monto=None):
        movimiento = self._movimiento(monto or factura.amount_total, f'PAGO {factura.name}', fecha=fecha)
        apunte = factura.line_ids.filtered(lambda ln: ln.account_id.account_type in ('asset_receivable',
                                                                                      'liability_payable'))
        movimiento.dcasa_conciliar(apunte.ids)
        return movimiento

    def _limpiar_hasta(self, fin):
        """Deja la base sin borradores ni movimientos sin conciliar hasta ``fin`` (datos de otros módulos)."""
        self.env['account.bank.statement.line'].search([('is_reconciled', '=', False), ('date', '<=', fin)]).unlink()
        self.env['account.move'].search([('state', '=', 'draft'), ('date', '<=', fin)]).unlink()

    # ------------------------------------------------------------------
    # Comparativos
    # ------------------------------------------------------------------

    def test_periodo_comparado(self):
        comparado = self.reportes._periodo_comparado
        d = date
        self.assertEqual(comparado(d(2030, 3, 1), d(2030, 3, 31), 'periodo_anterior'), (d(2030, 2, 1), d(2030, 2, 28)))
        self.assertEqual(comparado(d(2030, 10, 1), d(2030, 10, 15), 'periodo_anterior'),
                         (d(2030, 9, 1), d(2030, 9, 15)))
        self.assertEqual(comparado(d(2030, 1, 1), d(2030, 3, 31), 'periodo_anterior'),
                         (d(2029, 10, 1), d(2029, 12, 31)))
        self.assertEqual(comparado(d(2030, 3, 10), d(2030, 3, 19), 'periodo_anterior'),
                         (d(2030, 2, 28), d(2030, 3, 9)))
        self.assertEqual(comparado(d(2028, 2, 1), d(2028, 2, 29), 'anio_anterior'), (d(2027, 2, 1), d(2027, 2, 28)))
        self.assertEqual(comparado(d(2029, 2, 1), d(2029, 2, 28), 'anio_anterior'), (d(2028, 2, 1), d(2028, 2, 29)))

    def test_estado_resultados_comparativo(self):
        self._factura(100.0)
        self._factura(60.0, fecha='2030-02-10')
        self._factura(40.0, fecha='2029-03-10')
        datos = self.reportes.obtener('estado_resultados', DESDE, HASTA, comparar='periodo_anterior')
        ventas = datos['secciones'][0]
        self.assertAlmostEqual(ventas['total'], 100.0)
        self.assertAlmostEqual(ventas['comparado'], 60.0)
        self.assertAlmostEqual(ventas['variacion'], 40.0)
        self.assertAlmostEqual(ventas['variacion_pct'], 66.7)
        self.assertEqual(datos['comparado']['desde'], '2030-02-01')
        self.assertAlmostEqual(datos['comparado']['resumen']['utilidad_neta'], 60.0)
        anual = self.reportes.obtener('estado_resultados', DESDE, HASTA, comparar='anio_anterior')
        self.assertAlmostEqual(anual['secciones'][0]['comparado'], 40.0)
        # Una cuenta que solo se movió en el periodo comparado también aparece (con 0 en el actual).
        solo_antes = self.reportes.obtener('estado_resultados', '2030-04-01', '2030-04-30', comparar='periodo_anterior')
        fila = solo_antes['secciones'][0]['filas'][0]
        self.assertEqual((fila['monto'], fila['comparado']), (0.0, 100.0))
        # El balance general también compara y cada lado sigue cuadrando.
        balance = self.reportes.obtener('balance_general', DESDE, HASTA, comparar='periodo_anterior')
        self.assertTrue(balance['cuadra'])
        self.assertEqual(balance['comparado']['hasta'], '2030-02-28')
        self.assertIn('activo', balance['comparado']['totales'])
        with self.assertRaises(ValueError):
            self.reportes.obtener('estado_resultados', DESDE, HASTA, comparar='siglo_pasado')

    def test_exportar_comparativos_y_nuevos(self):
        self._factura(100.0)
        for reporte in ('estado_resultados', 'balance_general', 'flujo_efectivo'):
            datos = self.reportes.obtener(reporte, DESDE, HASTA, comparar='anio_anterior')
            self.assertTrue(libro_excel(datos).startswith(b'PK'), reporte)
            html, _formato = self.env['ir.actions.report']._render_qweb_html(
                'dcasa_contabilidad.reporte_contable', self.company.ids,
                data={'reporte': reporte, 'desde': DESDE, 'hasta': HASTA, 'comparar': 'anio_anterior'})
            self.assertIn('Variación', html.decode(), reporte)

    # ------------------------------------------------------------------
    # Flujo de efectivo
    # ------------------------------------------------------------------

    def test_flujo_de_efectivo_cuadra_con_el_banco(self):
        factura = self._factura(100.0)
        self._cobrar(factura)                                                    # entra 107
        self._asiento('2030-03-02', [(self.caja_banco, 1000, 0), (self.capital, 0, 1000)])  # aporte de capital
        self._asiento('2030-03-05', [(self.mobiliario, 300, 0), (self.caja_banco, 0, 300)])  # compra de mobiliario
        flujo = self.reportes.flujo_efectivo(DESDE, HASTA)
        self.assertTrue(flujo['cuadra'])
        total = {s['clave']: s['total'] for s in flujo['secciones']}
        self.assertAlmostEqual(total['operacion'], 107.0)   # utilidad 100 + ITBMS cobrado aún por pagar 7
        self.assertAlmostEqual(total['inversion'], -300.0)
        self.assertAlmostEqual(total['financiamiento'], 1000.0)
        r = flujo['resumen']
        self.assertAlmostEqual(r['variacion'], 807.0)
        self.assertAlmostEqual(r['efectivo_final'] - r['efectivo_inicial'], 807.0)

    def test_flujo_actividad_elegida_por_el_contador(self):
        """Un préstamo de corto plazo (pasivo corriente) va a financiamiento si el contador lo marca."""
        prestamo = self.env['account.account'].create({
            'name': 'Préstamo bancario prueba', 'code': '9T0004', 'account_type': 'liability_current'})
        self._asiento('2030-03-03', [(self.caja_banco, 500, 0), (prestamo, 0, 500)])
        total = {s['clave']: s['total'] for s in self.reportes.flujo_efectivo(DESDE, HASTA)['secciones']}
        self.assertAlmostEqual(total['operacion'], 500.0)
        prestamo.dcasa_actividad_flujo = 'financiamiento'
        flujo = self.reportes.flujo_efectivo(DESDE, HASTA)
        total = {s['clave']: s['total'] for s in flujo['secciones']}
        self.assertAlmostEqual(total['operacion'], 0.0)
        self.assertAlmostEqual(total['financiamiento'], 500.0)
        self.assertTrue(flujo['cuadra'])

    def test_flujo_con_depreciacion(self):
        depreciacion = self.env['account.account'].create({
            'name': 'Depreciación prueba', 'code': '9T0003', 'account_type': 'expense_depreciation'})
        self._asiento('2030-03-05', [(self.mobiliario, 300, 0), (self.caja_banco, 0, 300)])
        self._asiento('2030-03-31', [(depreciacion, 10, 0), (self.mobiliario, 0, 10)])
        flujo = self.reportes.flujo_efectivo(DESDE, HASTA)
        self.assertTrue(flujo['cuadra'])
        total = {s['clave']: s['total'] for s in flujo['secciones']}
        self.assertAlmostEqual(total['operacion'], 0.0)       # −10 de utilidad + 10 de depreciación
        self.assertAlmostEqual(total['inversion'], -300.0)    # la compra, sin la depreciación

    # ------------------------------------------------------------------
    # Antigüedad de saldos
    # ------------------------------------------------------------------

    def _fila(self, datos, partner):
        return next(f for f in datos['filas'] if f['id'] == partner.commercial_partner_id.id)

    def test_antiguedad_por_cobrar(self):
        vieja = self._factura(100.0, fecha='2030-01-10')    # vence el mismo día: 80 días al 31/03
        nueva = self._factura(50.0, fecha='2030-03-25')     # 6 días
        futura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2030-03-30',
            'invoice_date_due': '2030-04-30',
            'invoice_line_ids': [(0, 0, {'name': 'x', 'quantity': 1, 'price_unit': 10.0, 'tax_ids': []})]})
        futura.action_post()
        self._cobrar(vieja, fecha='2030-04-05', monto=57.0)  # abono DESPUÉS del corte
        datos = self.reportes.por_cobrar(hasta=HASTA)
        fila = self._fila(datos, self.cliente)
        self.assertAlmostEqual(fila['tramos']['d61_90'], 107.0, msg=fila)  # el abono de abril no cuenta al 31/03
        self.assertAlmostEqual(fila['tramos']['d1_30'], 53.5)
        self.assertAlmostEqual(fila['tramos']['por_vencer'], 10.0)
        self.assertAlmostEqual(fila['total'], 170.5)
        self.assertAlmostEqual(fila['vencido'], 160.5)
        self.assertEqual({d['documento'] for d in fila['documentos']}, {vieja.name, nueva.name, futura.name})
        # Partida doble: el total coincide con el saldo de la cuenta por cobrar del cliente a esa fecha.
        saldo = sum(self.env['account.move.line'].search([
            ('partner_id', '=', self.cliente.id), ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'), ('date', '<=', HASTA)]).mapped('balance'))
        self.assertAlmostEqual(fila['total'], saldo)
        # Al 30/04 el abono ya cuenta.
        abril = self._fila(self.reportes.por_cobrar(hasta='2030-04-30'), self.cliente)
        self.assertAlmostEqual(abril['total'], 170.5 - 57.0)

    def test_antiguedad_por_pagar(self):
        self._factura(50.0, fecha='2030-03-01', tipo='in_invoice')
        datos = self.reportes.obtener('por_pagar', hasta=HASTA)
        fila = self._fila(datos, self.proveedor)
        self.assertAlmostEqual(fila['total'], 53.5)
        self.assertAlmostEqual(fila['tramos']['d1_30'], 53.5, msg=fila)
        self.assertTrue(libro_excel(datos).startswith(b'PK'))

    # ------------------------------------------------------------------
    # Resumen de la dueña
    # ------------------------------------------------------------------

    def test_resumen(self):
        self._factura(100.0)
        self._factura(80.0, fecha='2030-02-10')
        datos = self.reportes.obtener('resumen', DESDE, HASTA)
        tarjetas = {t['clave']: t for t in datos['tarjetas']}
        self.assertAlmostEqual(tarjetas['ventas']['valor'], 100.0)
        self.assertAlmostEqual(tarjetas['ventas']['comparado'], 80.0)
        self.assertAlmostEqual(tarjetas['utilidad']['valor'],
                               self.reportes.estado_resultados(DESDE, HASTA)['resumen']['utilidad_neta'])
        cobrar = self.reportes.por_cobrar(hasta=HASTA)['totales']['total']
        self.assertAlmostEqual(tarjetas['por_cobrar']['valor'], cobrar)
        self.assertAlmostEqual(tarjetas['itbms']['valor'], 7.0)
        self.assertIn(self.banco.id, [b['id'] for b in datos['bancos']])
        self.assertEqual(datos['periodo_comparado']['desde'], '2030-02-01')

    # ------------------------------------------------------------------
    # Cierre de mes y fecha de bloqueo
    # ------------------------------------------------------------------

    def test_cierre_de_mes_y_bloqueo(self):
        self._limpiar_hasta(HASTA)
        factura = self._factura(100.0)
        pendiente = self._movimiento(107.0, f'PAGO {factura.name}')
        abierta = self._factura(30.0, fecha='2030-03-20')  # sin pagar: sirve para probar el bloqueo
        cierre = self.env['dcasa.cierre.mes'].create({'mes': '2030-03-17'})
        self.assertEqual(cierre.mes, date(2030, 3, 1))
        self.assertEqual(cierre.fecha_fin, date(2030, 3, 31))
        self.assertEqual(cierre.name, 'Marzo 2030')
        pasos = {p.codigo: p for p in cierre.paso_ids}
        self.assertEqual(pasos['conciliacion'].estado, 'pendiente')
        self.assertEqual(pasos['comprobacion'].estado, 'listo')
        self.assertEqual(pasos['itbms'].estado, 'info')
        self.assertTrue(pasos['conciliacion'].action_ver()['domain'])
        with self.assertRaises(UserError):
            cierre.action_cerrar()
        self.assertEqual(cierre.estado, 'abierto')

        pendiente.dcasa_conciliar(factura.line_ids.filtered(
            lambda ln: ln.account_id.account_type == 'asset_receivable').ids)
        # Solo la gerencia contable cierra.
        contador = new_test_user(self.env, login='conta_cierre', groups='base.group_user,account.group_account_user')
        with self.assertRaises(AccessError):
            cierre.with_user(contador).action_cerrar()
        cierre.bloquear_itbms = True
        cierre.action_cerrar()
        self.assertEqual(cierre.estado, 'cerrado')
        self.assertEqual(self.company.fiscalyear_lock_date, date(2030, 3, 31))
        self.assertEqual(self.company.tax_lock_date, date(2030, 3, 31))
        with self.assertRaises(UserError):  # el mes cerrado no se toca
            abierta.button_draft()
        with self.assertRaises(UserError):
            cierre.unlink()

        with self.assertRaises(UserError):  # reabrir pide motivo
            cierre.action_reabrir()
        cierre.motivo_reapertura = 'Factura de proveedor que llegó tarde'
        cierre.action_reabrir()
        self.assertEqual(cierre.estado, 'abierto')
        self.assertFalse(self.company.fiscalyear_lock_date)  # no quedaba ningún mes cerrado
        self.assertFalse(self.company.tax_lock_date)
        abierta.button_draft()
        self.assertEqual(abierta.state, 'draft')

    def test_cierre_con_borradores_no_cierra(self):
        self._limpiar_hasta(HASTA)
        self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.proveedor.id, 'invoice_date': '2030-03-05',
            'date': '2030-03-05',
            'invoice_line_ids': [(0, 0, {'name': 'Flete', 'quantity': 1, 'price_unit': 20.0, 'tax_ids': []})]})
        cierre = self.env['dcasa.cierre.mes'].create({'mes': '2030-03-01'})
        self.assertEqual(cierre.pendientes, 1)
        paso = cierre.paso_ids.filtered(lambda p: p.codigo == 'borrador_in_invoice')
        self.assertEqual(paso.estado, 'pendiente')
        with self.assertRaises(UserError):
            cierre.action_cerrar()
        self.assertFalse(self.company.fiscalyear_lock_date and self.company.fiscalyear_lock_date >= date(2030, 3, 1))

    # ------------------------------------------------------------------
    # Reglas de conciliación
    # ------------------------------------------------------------------

    def _regla(self, **valores):
        return self.env['account.reconcile.model'].create({'name': 'Regla de prueba', **valores})

    def test_regla_automatica_de_comision(self):
        self._regla(name='Comisión ACH', match_label='contains', match_label_param='COMISION ACH',
                    trigger='auto_reconcile',
                    line_ids=[(0, 0, {'account_id': self.gasto.id, 'amount_type': 'percentage',
                                      'amount_string': '100', 'label': 'Comisión bancaria'})])
        comision = self._movimiento(-1.25, 'COMISION ACH 0001')
        otro = self._movimiento(-30.0, 'PAGO LUZ')
        hechos = (comision | otro).dcasa_conciliar_automatico()
        self.assertEqual(hechos, comision)
        linea = comision.move_id.line_ids.filtered(lambda ln: ln.account_id == self.gasto)
        self.assertAlmostEqual(linea.debit, 1.25)
        self.assertEqual(linea.name, 'Comisión bancaria')
        self.assertFalse(otro.is_reconciled)

    def test_regla_manual_monto_fijo_y_condiciones(self):
        regla = self._regla(name='Cargo fijo Yappy', match_label='match_regex', match_label_param=r'yappy\s+cargo',
                            match_amount='lower', match_amount_max=10,
                            line_ids=[(0, 0, {'account_id': self.gasto.id, 'amount_type': 'fixed',
                                              'amount_string': '1'})])
        otro_banco = self.env['account.journal'].create({'name': 'Banco prueba 2', 'code': 'BP2', 'type': 'bank'})
        self._regla(name='Solo otro banco', match_journal_ids=[(6, 0, otro_banco.ids)], match_label='contains',
                    match_label_param='YAPPY',
                    line_ids=[(0, 0, {'account_id': self.gasto.id, 'amount_string': '100'})])
        movimiento = self._movimiento(-3.0, 'YAPPY  CARGO servicio')
        grande = self._movimiento(-50.0, 'YAPPY CARGO servicio')
        pantalla = self.env['dcasa.conciliacion']
        self.assertEqual([r['id'] for r in pantalla.reglas(movimiento.id)], [regla.id])
        self.assertFalse(pantalla.reglas(grande.id))  # más de 10: no aplica
        self.assertFalse(movimiento.dcasa_conciliar_automatico())  # manual: no se aplica sola
        resultado = pantalla.aplicar_regla(movimiento.id, regla.id)
        self.assertFalse(resultado['conciliado'])  # $1 de $3: el resto sigue pendiente
        fila = next(p for p in pantalla.pendientes(self.banco.id) if p['id'] == movimiento.id)
        self.assertAlmostEqual(fila['pendiente'], -2.0)
        with self.assertRaises(UserError):
            pantalla.aplicar_regla(grande.id, regla.id)

    def test_regla_asigna_tercero(self):
        self._regla(name='Yappy de Ana', match_label='contains', match_label_param='ANA PRUEBA',
                    line_ids=[(0, 0, {'partner_id': self.cliente.id, 'amount_string': '100'})])
        factura = self._factura(100.0)
        movimiento = self._movimiento(107.0, 'YAPPY DE ANA PRUEBA')
        # Sin tercero ni referencia no es seguro; con el tercero de la regla, sí (monto + cliente).
        hechos = movimiento.dcasa_conciliar_automatico()
        self.assertEqual(movimiento.partner_id, self.cliente)
        self.assertEqual(hechos, movimiento)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))

    # ------------------------------------------------------------------
    # Extractos: CSV con formato, OFX y CAMT
    # ------------------------------------------------------------------

    def test_csv_con_filas_de_titulo_y_formato(self):
        contenido = ('BANCO DE PRUEBA\nCuenta 04-00-00-000000-0\n\n'
                     'F. Contable;Concepto;Detalle;Cargos;Abonos\n'
                     '20/03/2030;DEPÓSITO;Juan;;1.070,00\n'
                     '21/03/2030;COMISIÓN;ACH;2,50;\n'
                     ';Total;;2,50;1.070,00\n').encode('cp1252')
        with self.assertRaises(UserError):  # «F. Contable» y «Cargos/Abonos» sin formato: no se adivinan
            leer_csv(contenido)
        formato = self.env['dcasa.formato.extracto'].create({
            'name': 'Banco de prueba', 'journal_ids': [(6, 0, self.banco.ids)], 'separador': 'punto_coma',
            'filas_omitir': 3, 'col_fecha': 'F. Contable', 'col_concepto': 'Concepto + Detalle',
            'col_debito': 'Cargos', 'col_credito': '5', 'decimal': 'coma', 'formato_fecha': 'dd/mm/aaaa'})
        filas = leer_csv(contenido, formato._como_dict())
        self.assertEqual([f['monto'] for f in filas], [1070.0, -2.5])
        self.assertEqual(filas[0]['concepto'], 'DEPÓSITO Juan')
        # Las columnas comunes se reconocen aunque haya filas de título arriba.
        auto = leer_csv('Extracto de prueba\nFecha,Descripción,Monto\n20/03/2030,DEP,5.00\n'.encode())
        self.assertEqual(auto[0]['monto'], 5.0)
        # El asistente elige el formato del banco y muestra la vista previa antes de importar.
        asistente = self.env['dcasa.importar.extracto'].new({'journal_id': self.banco.id})
        asistente._onchange_journal_id()
        self.assertEqual(asistente.formato_id, formato)
        asistente.archivo = base64.b64encode(contenido)
        self.assertIn('2 nuevos', asistente.vista_previa)

    def test_leer_ofx_y_camt(self):
        filas, saldo = leer_ofx(OFX % b'REF 1')
        self.assertEqual([(f['fecha'], f['monto'], f['id']) for f in filas],
                         [(date(2030, 3, 20), 107.0, 'BG-0001'), (date(2030, 3, 21), -1.25, 'BG-0002')])
        self.assertEqual(filas[0]['concepto'], 'ACH RECIBIDO REF 1')
        self.assertAlmostEqual(saldo, 9999.99)
        filas, saldo = leer_camt(CAMT)
        self.assertEqual([(f['monto'], f['concepto'], f['id']) for f in filas],
                         [(-40.0, 'PAGO LUZ', 'C-1'), (15.5, 'INTERESES', 'C-2')])
        self.assertAlmostEqual(saldo, 500.0)

    def test_importar_ofx_sin_duplicar(self):
        factura = self._factura(100.0)
        archivo = base64.b64encode(OFX % factura.name.encode())
        asistente = self.env['dcasa.importar.extracto'].create({
            'journal_id': self.banco.id, 'archivo': archivo, 'nombre_archivo': 'extracto.ofx'})
        accion = asistente.action_importar()
        self.assertEqual(accion['params']['aviso_tipo'], 'warning')  # el saldo del banco no coincide
        lineas = self.env['account.bank.statement.line'].search(
            [('dcasa_id_importacion', 'in', ('BG-0001', 'BG-0002'))])
        self.assertEqual(len(lineas), 2)
        self.assertAlmostEqual(lineas.statement_id.balance_end_real, 9999.99)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))  # se concilió sola por la referencia
        # El mismo archivo otra vez (aunque cambie la descripción) no duplica: manda el FITID.
        otra = self.env['dcasa.importar.extracto'].create({
            'journal_id': self.banco.id, 'archivo': base64.b64encode(OFX % b'OTRO TEXTO'),
            'nombre_archivo': 'extracto.ofx'})
        with self.assertRaises(UserError):
            otra.action_importar()

    def test_importar_camt(self):
        asistente = self.env['dcasa.importar.extracto'].create({
            'journal_id': self.banco.id, 'archivo': base64.b64encode(CAMT), 'nombre_archivo': 'camt.xml'})
        asistente.action_importar()
        lineas = self.env['account.bank.statement.line'].search([('dcasa_id_importacion', 'in', ('C-1', 'C-2'))])
        self.assertEqual(sorted(lineas.mapped('amount')), [-40.0, 15.5])

    # ------------------------------------------------------------------
    # Seguridad
    # ------------------------------------------------------------------

    def test_vendedora_no_usa_reglas_ni_cierre(self):
        vendedora = new_test_user(self.env, login='ventas_fase1',
                                  groups='base.group_user,sales_team.group_sale_salesman')
        regla = self._regla(match_label='contains', match_label_param='X',
                            line_ids=[(0, 0, {'account_id': self.gasto.id, 'amount_string': '100'})])
        movimiento = self._movimiento(-5.0, 'X')
        for metodo, args in (('reglas', [movimiento.id]), ('aplicar_regla', [movimiento.id, regla.id])):
            with self.subTest(metodo=metodo), self.assertRaises(AccessError):
                getattr(self.env['dcasa.conciliacion'].with_user(vendedora), metodo)(*args)
        with self.assertRaises(AccessError):
            self.env['dcasa.cierre.mes'].with_user(vendedora).create({'mes': '2030-03-01'})
