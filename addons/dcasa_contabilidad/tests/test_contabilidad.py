import base64
from datetime import date

from psycopg2.errors import CheckViolation

from odoo.addons.dcasa_contabilidad.controllers.main import libro_excel
from odoo.addons.dcasa_contabilidad.models.conciliacion import leer_fecha, leer_monto
from odoo.addons.dcasa_contabilidad.wizard.importar_extracto import leer_csv
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

# Periodo aislado: nada más en la base tiene movimientos en marzo de 2030.
DESDE, HASTA = '2030-03-01', '2030-03-31'


class ContabilidadCommon(TransactionCase):
    """Datos y ayudas comunes de los tests contables."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        Tax = cls.env['account.tax']
        cls.itbms_venta = cls.company.account_sale_tax_id  # el de por defecto: se suma al precio
        cls.itbms_compra = Tax.search([('company_id', '=', cls.company.id), ('type_tax_use', '=', 'purchase'),
                                       ('amount', '=', 7), ('price_include', '=', False)], limit=1)
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente Prueba Contable'})
        cls.proveedor = cls.env['res.partner'].create({'name': 'Proveedor Prueba Contable'})
        cls.banco = cls.env['account.journal'].search([('type', '=', 'bank'), ('company_id', '=', cls.company.id)],
                                                      limit=1)
        cls.tienda = cls.env.ref('dcasa_contabilidad.cuenta_tienda_fisica')
        cls.reportes = cls.env['dcasa.reporte.contable']

    def _factura(self, monto=100.0, fecha='2030-03-10', tipo='out_invoice', analitica=None):
        compra = tipo == 'in_invoice'
        linea = {'name': 'Mueble de prueba', 'quantity': 1, 'price_unit': monto,
                 'tax_ids': [(6, 0, (self.itbms_compra if compra else self.itbms_venta).ids)]}
        if analitica:
            linea['analytic_distribution'] = {str(analitica.id): 100}
        factura = self.env['account.move'].create({
            'move_type': tipo, 'partner_id': (self.proveedor if compra else self.cliente).id,
            'invoice_date': fecha, 'date': fecha, 'invoice_date_due': fecha, 'invoice_line_ids': [(0, 0, linea)],
        })
        factura.action_post()
        return factura

    def _movimiento(self, monto, concepto, fecha='2030-03-15', partner=None):
        return self.env['account.bank.statement.line'].create({
            'journal_id': self.banco.id, 'date': fecha, 'amount': monto, 'payment_ref': concepto,
            'partner_id': partner.id if partner else False,
        })


@tagged('post_install', '-at_install')
class TestContabilidad(ContabilidadCommon):

    # ------------------------------------------------------------------
    # Reportes
    # ------------------------------------------------------------------

    def test_reportes_cuadran(self):
        self._factura(100.0)
        self._factura(50.0, fecha='2030-03-12', tipo='in_invoice')

        comprobacion = self.reportes.balance_comprobacion(DESDE, HASTA)
        self.assertTrue(comprobacion['cuadra'])
        self.assertAlmostEqual(comprobacion['totales']['debe'], comprobacion['totales']['haber'])
        self.assertAlmostEqual(comprobacion['totales']['debe'], 107.0 + 53.5)

        resultados = self.reportes.estado_resultados(DESDE, HASTA)
        ventas = next(s for s in resultados['secciones'] if s['clave'] == 'ventas')
        self.assertAlmostEqual(ventas['total'], 100.0)
        self.assertAlmostEqual(resultados['resumen']['utilidad_neta'], 50.0)

        general = self.reportes.balance_general(HASTA)
        self.assertTrue(general['cuadra'])
        self.assertAlmostEqual(general['totales']['activo'], general['totales']['pasivo_y_patrimonio'])

        itbms = self.reportes.itbms(DESDE, HASTA)
        self.assertAlmostEqual(itbms['resumen']['debito_fiscal'], 7.0)
        self.assertAlmostEqual(itbms['resumen']['credito_fiscal'], 3.5)
        self.assertAlmostEqual(itbms['resumen']['a_pagar'], 3.5)
        venta = next(f for f in itbms['filas'] if f['tipo'] == 'venta')
        self.assertAlmostEqual(venta['base'], 100.0)

    def test_itbms_incluye_ventas_exentas(self):
        exento = self.env['account.tax'].create({
            'name': 'ITBMS 0% exento (prueba)', 'amount': 0, 'type_tax_use': 'sale', 'company_id': self.company.id})
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2030-03-10',
            'invoice_line_ids': [(0, 0, {'name': 'Exento', 'quantity': 1, 'price_unit': 60.0,
                                         'tax_ids': [(6, 0, exento.ids)]})],
        })
        factura.action_post()
        fila = next(f for f in self.reportes.itbms(DESDE, HASTA)['filas'] if f['id'] == exento.id)
        self.assertAlmostEqual(fila['base'], 60.0)
        self.assertAlmostEqual(fila['impuesto'], 0.0)

    def test_libro_mayor_saldo_corrido(self):
        factura = self._factura(100.0)
        cxc = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable').account_id
        mayor = self.reportes.libro_mayor(DESDE, HASTA, cuenta_ids=cxc.ids)
        [cuenta] = mayor['cuentas']
        self.assertAlmostEqual(cuenta['final'] - cuenta['inicial'], 107.0)
        self.assertAlmostEqual(cuenta['lineas'][-1]['saldo'], cuenta['final'])
        self.assertEqual(cuenta['lineas'][-1]['asiento'], factura.name)

    def test_borradores_solo_si_se_piden(self):
        borrador = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': '2030-03-05',
            'invoice_line_ids': [(0, 0, {'name': 'x', 'quantity': 1, 'price_unit': 40.0, 'tax_ids': []})],
        })
        self.assertEqual(borrador.state, 'draft')
        sin = self.reportes.estado_resultados(DESDE, HASTA)
        con = self.reportes.estado_resultados(DESDE, HASTA, borradores=True)
        self.assertAlmostEqual(con['secciones'][0]['total'] - sin['secciones'][0]['total'], 40.0)

    def test_analitica_y_presupuesto(self):
        factura = self._factura(100.0, analitica=self.tienda)
        analitica = self.reportes.analitica(DESDE, HASTA)
        fila = next(f for f in analitica['filas'] if f['id'] == self.tienda.id)
        self.assertAlmostEqual(fila['ingresos'], 100.0)

        ingreso = factura.invoice_line_ids.account_id
        presupuesto = self.env['dcasa.presupuesto'].create({
            'name': 'Ventas marzo 2030', 'fecha_desde': DESDE, 'fecha_hasta': HASTA,
            'line_ids': [(0, 0, {'account_id': ingreso.id, 'monto_planeado': 200.0}),
                         (0, 0, {'account_id': ingreso.id, 'analytic_account_id': self.tienda.id,
                                 'monto_planeado': 100.0})],
        })
        general, por_canal = presupuesto.line_ids
        self.assertGreaterEqual(general.monto_real, 100.0)
        self.assertAlmostEqual(por_canal.monto_real, 100.0)
        self.assertAlmostEqual(por_canal.porcentaje, 100.0)
        self.assertAlmostEqual(por_canal.diferencia, 0.0)
        with self.assertRaises(CheckViolation), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            presupuesto.write({'fecha_hasta': '2029-01-01'})
            presupuesto.flush_recordset()

    def test_exportaciones(self):
        self._factura(100.0)
        for reporte in self.reportes.REPORTES:
            datos = self.reportes.obtener(reporte, desde=DESDE, hasta=HASTA)
            self.assertTrue(libro_excel(datos).startswith(b'PK'), reporte)
            html, _formato = self.env['ir.actions.report']._render_qweb_html(
                'dcasa_contabilidad.reporte_contable', self.company.ids,
                data={'reporte': reporte, 'desde': DESDE, 'hasta': HASTA})
            self.assertIn(datos['titulo'], html.decode(), reporte)

    def test_sin_permiso_no_ve_reportes(self):
        usuario = self.env['res.users'].create({
            'name': 'Vendedor sin contabilidad', 'login': 'vendedor_sin_conta',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        with self.assertRaises(AccessError):
            self.reportes.with_user(usuario).obtener('balance_general')

    # ------------------------------------------------------------------
    # Conciliación bancaria
    # ------------------------------------------------------------------

    def test_conciliar_con_factura(self):
        factura = self._factura(100.0)
        movimiento = self._movimiento(107.0, f'TRANSFERENCIA {factura.name}')
        candidatos, puntaje = movimiento.dcasa_candidatos()
        self.assertEqual(candidatos[0].move_id, factura)
        self.assertGreaterEqual(puntaje(candidatos[0]), 7)
        movimiento.dcasa_conciliar([candidatos[0].id])
        self.assertTrue(movimiento.is_reconciled)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        # Deshacer deja todo como estaba.
        self.env['dcasa.conciliacion'].deshacer(movimiento.id)
        self.assertFalse(movimiento.is_reconciled)
        self.assertEqual(factura.payment_state, 'not_paid')

    def test_conciliar_pago_ya_registrado(self):
        """El pago registrado en la factura (Recibos pendientes) se cruza con el depósito del banco."""
        factura = self._factura(100.0)
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids,
        ).create({'payment_date': '2030-03-11', 'journal_id': self.banco.id})._create_payments()
        movimiento = self._movimiento(107.0, 'DEPOSITO', partner=self.cliente)
        candidatos = self.env['dcasa.conciliacion'].candidatos(movimiento.id)
        pago = next(c for c in candidatos if c['tipo'] == 'pago')
        self.assertTrue(pago['sugerido'])
        self.env['dcasa.conciliacion'].conciliar(movimiento.id, apunte_ids=[pago['id']])
        self.assertTrue(movimiento.is_reconciled)
        self.assertEqual(factura.payment_state, 'paid')

    def test_transacciones_del_tablero_abren_la_conciliacion(self):
        accion = self.banco.open_action()
        self.assertEqual(accion['tag'], 'dcasa_conciliacion')
        self.assertEqual(accion['params']['journal_id'], self.banco.id)
        ventas = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        self.assertEqual(ventas.open_action()['type'], 'ir.actions.act_window')

    def test_conciliacion_parcial(self):
        factura = self._factura(100.0)
        movimiento = self._movimiento(50.0, 'ABONO', partner=self.cliente)
        apunte = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        self.env['dcasa.conciliacion'].conciliar(movimiento.id, apunte_ids=apunte.ids)
        self.assertTrue(movimiento.is_reconciled)
        self.assertAlmostEqual(factura.amount_residual, 57.0)

    def test_completar_una_conciliacion_parcial(self):
        """Depósito mayor que la factura: primero la factura, luego el resto a otra cuenta; nada se pierde."""
        factura = self._factura(100.0)
        movimiento = self._movimiento(150.0, f'DEPOSITO {factura.name}', partner=self.cliente)
        apunte = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        movimiento.dcasa_conciliar(apunte.ids)
        self.assertFalse(movimiento.is_reconciled)
        self.assertAlmostEqual(self.env['dcasa.conciliacion'].pendientes(self.banco.id)[0]['pendiente'], 43.0)
        self.assertEqual(factura.payment_state, 'paid')
        otros = self.env['account.account'].search([('account_type', '=', 'income_other'),
                                                    ('company_ids', 'in', self.company.ids)], limit=1)
        movimiento.dcasa_conciliar(cuenta_id=otros.id, etiqueta='Anticipo')
        self.assertTrue(movimiento.is_reconciled)
        self.assertEqual(factura.payment_state, 'paid')  # la primera parte sigue conciliada

    def test_conciliar_comision_sin_factura(self):
        gasto = self.env['account.account'].search([('account_type', '=', 'expense'),
                                                    ('company_ids', 'in', self.company.ids)], limit=1)
        movimiento = self._movimiento(-5.0, 'CARGO POR SERVICIO')
        grupos = self.env['dcasa.conciliacion'].cuentas_rapidas()
        self.assertEqual(grupos[0]['grupo'], 'Gastos')
        self.assertIn(gasto.id, [c['id'] for c in grupos[0]['cuentas']])
        self.env['dcasa.conciliacion'].conciliar(movimiento.id, cuenta_id=gasto.id, etiqueta='Comisión bancaria')
        self.assertTrue(movimiento.is_reconciled)
        linea_gasto = movimiento.move_id.line_ids.filtered(lambda ln: ln.account_id == gasto)
        self.assertAlmostEqual(linea_gasto.debit, 5.0)
        self.assertEqual(linea_gasto.name, 'Comisión bancaria')
        with self.assertRaises(UserError):
            movimiento.dcasa_conciliar(cuenta_id=gasto.id)

    def test_conciliacion_automatica_solo_lo_seguro(self):
        factura = self._factura(80.0)
        seguro = self._movimiento(85.6, f'YAPPY {factura.name}')
        dudoso = self._movimiento(85.6, 'DEPOSITO')
        hechos = (seguro | dudoso).dcasa_conciliar_automatico()
        self.assertEqual(hechos, seguro)
        self.assertTrue(seguro.is_reconciled)
        self.assertFalse(dudoso.is_reconciled)
        pantalla = self.env['dcasa.conciliacion']
        self.assertIn(dudoso.id, [ln['id'] for ln in pantalla.pendientes(self.banco.id)])
        self.assertTrue(any(d['id'] == self.banco.id for d in pantalla.diarios()))

    # ------------------------------------------------------------------
    # Extractos CSV
    # ------------------------------------------------------------------

    def test_leer_montos_y_fechas(self):
        self.assertEqual(leer_monto('1,234.56'), 1234.56)
        self.assertEqual(leer_monto('1.234,56'), 1234.56)
        self.assertEqual(leer_monto('(45.00)'), -45.0)
        self.assertEqual(leer_monto('-$ 12.50'), -12.5)
        self.assertEqual(leer_monto('B/. 7'), 7.0)
        self.assertEqual(leer_monto(''), 0.0)
        self.assertEqual(leer_fecha('15/03/2030'), date(2030, 3, 15))
        self.assertEqual(leer_fecha('2030-03-15'), date(2030, 3, 15))
        with self.assertRaises(ValueError):
            leer_fecha('mañana')

    def test_leer_csv_debito_credito(self):
        contenido = ('Fecha;Descripción;Débito;Crédito;Referencia\n'
                     '15/03/2030;DEPOSITO YAPPY;;1.070,00;A1\n'
                     '16/03/2030;COMISION;2,50;;B2\n'
                     '17/03/2030;SIN MONTO;;;C3\n').encode('utf-8-sig')
        filas = leer_csv(contenido)
        self.assertEqual([f['monto'] for f in filas], [1070.0, -2.5])
        self.assertEqual(filas[0]['concepto'], 'DEPOSITO YAPPY')
        self.assertEqual(filas[1]['referencia'], 'B2')
        with self.assertRaises(UserError):
            leer_csv(b'Columna,Otra\n1,2\n')

    def test_importar_extracto(self):
        factura = self._factura(100.0)
        csv = (f'Fecha,Descripcion,Monto\n20/03/2030,ACH {factura.name},107.00\n'
               '21/03/2030,COMISION ACH,-1.25\n').encode()
        asistente = self.env['dcasa.importar.extracto'].create({
            'journal_id': self.banco.id, 'archivo': base64.b64encode(csv), 'nombre_archivo': 'extracto.csv'})
        accion = asistente.action_importar()
        self.assertEqual(accion['tag'], 'dcasa_conciliacion')
        lineas = self.env['account.bank.statement.line'].search([('journal_id', '=', self.banco.id),
                                                                 ('date', '>=', '2030-03-20')])
        self.assertEqual(len(lineas), 2)
        self.assertEqual(len(lineas.statement_id), 1)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))  # se concilió sola
        # Volver a subir el mismo archivo no duplica nada.
        otra = asistente.copy({'archivo': base64.b64encode(csv)})
        with self.assertRaises(UserError):
            otra.action_importar()

    # ------------------------------------------------------------------
    # Cheques y configuración
    # ------------------------------------------------------------------

    def test_cheque_en_letras_y_formato(self):
        self.assertEqual(self.company.account_check_printing_layout, 'dcasa_contabilidad.accion_cheque')
        metodo = self.banco.outbound_payment_method_line_ids.filtered(lambda m: m.code == 'check_printing')
        self.assertTrue(metodo)
        pago = self.env['account.payment'].create({
            'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': self.proveedor.id,
            'amount': 1250.50, 'journal_id': self.banco.id, 'payment_method_line_id': metodo[:1].id,
            'date': '2030-03-20',
        })
        self.assertEqual(pago.check_amount_in_words, 'Mil Doscientos Cincuenta Dólares con 50/100')
        pago.action_post()
        html, _formato = self.env['ir.actions.report']._render_qweb_html('dcasa_contabilidad.accion_cheque', pago.ids)
        html = html.decode()
        self.assertIn('Páguese a la orden de', html)
        self.assertIn('Proveedor Prueba Contable', html)

    def test_configuracion(self):
        self.assertIn(self.env.ref('account.group_account_user'),
                      self.env.ref('account.group_account_manager').implied_ids)
        self.assertEqual(self.tienda.plan_id, self.env.ref('dcasa_contabilidad.plan_canal'))
        self.assertTrue(self.reportes.periodos())
