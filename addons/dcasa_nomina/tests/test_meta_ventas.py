"""Bono por meta de ventas (decisión del jefe, 2026-10-16): 1 % de TODO lo cobrado en el mes si se llega a la meta;
solo lo cobrado completo, sin ITBMS, en el mes del último pago; las devoluciones restan; participa quien está en el
departamento de Ventas con usuario; entra en la primera planilla quincenal del mes siguiente.

En estas pruebas la meta es de 1,000 y el bono del 1 % (cifras de PRUEBA, desde enero de 2030)."""
from datetime import date

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import new_test_user, tagged

from .common import NominaCommon

MARZO, ABRIL = date(2030, 3, 1), date(2030, 4, 1)


@tagged('post_install', '-at_install')
class TestMetaVentas(NominaCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.regla = cls.env['dcasa.nomina.meta.regla'].create({
            'company_id': cls.company.id, 'fecha_desde': '2030-01-01', 'meta_mensual': 1000, 'porcentaje': 1,
            'meta_diaria': 100})
        Departamento = cls.env['hr.department']
        cls.ventas = Departamento.create({'name': 'Ventas prueba meta', 'dcasa_meta_ventas': True,
                                         'company_id': cls.company.id})
        cls.otro_depto = Departamento.create({'name': 'Marketing prueba meta', 'company_id': cls.company.id})
        cls.u_vera = new_test_user(cls.env, login='meta_vera', name='Vera Meta',
                                   groups='base.group_user,dcasa_base.group_vendedora')
        cls.u_otto = new_test_user(cls.env, login='meta_otto', name='Otto Meta', groups='base.group_user')
        cls.vera = cls._empleado('Vera Meta', 1200, '2029-01-01', department_id=cls.ventas.id, user_id=cls.u_vera.id)
        cls.otto = cls._empleado('Otto Meta', 1200, '2029-01-01', department_id=cls.otro_depto.id,
                                 user_id=cls.u_otto.id)
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente meta de ventas'})
        cls.itbms = cls.company.account_sale_tax_id
        cls.Bono = cls.env['dcasa.nomina.meta.bono']

    def factura(self, monto, fecha, usuario=None, pagar_en=None, abono=None):
        """Factura de ``monto`` SIN ITBMS (se le suma el ITBMS de la empresa). ``pagar_en``: la paga completa ese
        día (o solo ``abono`` con ITBMS si se da)."""
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fecha,
            'invoice_user_id': (usuario or self.u_vera).id,
            'invoice_line_ids': [Command.create({'name': 'Mueble', 'quantity': 1, 'price_unit': monto,
                                                 'tax_ids': [Command.set(self.itbms.ids)]})]})
        factura.action_post()
        if pagar_en:
            self.pagar(factura, pagar_en, abono)
        return factura

    def pagar(self, factura, fecha, monto=None):
        valores = {'payment_date': fecha}
        if monto:
            valores['amount'] = monto
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create(valores)._create_payments()

    def bono(self, mes=MARZO, empleado=None):
        return self.Bono._calcular(empleado or self.vera, mes, self.company)

    # ------------------------------------------------------------------
    # La regla
    # ------------------------------------------------------------------

    def test_sin_llegar_a_la_meta_no_hay_bono(self):
        self.factura(900, '2030-03-05', pagar_en='2030-03-06')
        bono = self.bono()
        self.assertAlmostEqual(bono.cobrado, 900.0)
        self.assertFalse(bono.cumplio)
        self.assertEqual(bono.monto, 0.0)

    def test_al_llegar_a_la_meta_cobra_el_porcentaje_de_todo(self):
        self.factura(600, '2030-03-05', pagar_en='2030-03-06')
        self.factura(400, '2030-03-07', pagar_en='2030-03-07')
        bono = self.bono()
        self.assertAlmostEqual(bono.cobrado, 1000.0, msg='sin ITBMS')
        self.assertTrue(bono.cumplio, 'llegar justo a la meta cuenta')
        self.assertEqual(bono.monto, 10.0)
        self.factura(1000, '2030-03-20', pagar_en='2030-03-21')
        bono = self.bono()
        self.assertEqual((bono.cobrado, bono.monto), (2000.0, 20.0), 'el 1 % de TODO, no solo de lo que pasa la meta')
        self.assertEqual(bono.regla_id, self.regla)

    def test_cuenta_lo_cobrado_completo_en_el_mes_del_ultimo_pago(self):
        apartado = self.factura(1200, '2030-02-10', pagar_en='2030-02-10', abono=500)
        self.factura(300, '2030-03-02')                                  # sin pagar: no cuenta
        self.assertEqual(self.bono(date(2030, 2, 1)).cobrado, 0.0, 'el abono solo no cuenta')
        self.assertEqual(self.bono().cobrado, 0.0)
        self.pagar(apartado, '2030-03-15')                               # caja recibe el resto en marzo
        bono = self.bono()
        self.assertAlmostEqual(bono.cobrado, 1200.0)
        self.assertEqual(bono.factura_ids, apartado)
        self.assertEqual(self.bono(date(2030, 2, 1)).cobrado, 0.0, 'cuenta en marzo, no en febrero')

    def test_las_notas_de_credito_restan(self):
        factura = self.factura(1500, '2030-03-05', pagar_en='2030-03-06')
        nota = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': self.cliente.id, 'invoice_date': '2030-03-10',
            'reversed_entry_id': factura.id, 'invoice_user_id': self.u_vera.id,
            'invoice_line_ids': [Command.create({'name': 'Devolución', 'quantity': 1, 'price_unit': 600,
                                                 'tax_ids': [Command.set(self.itbms.ids)]})]})
        nota.action_post()
        bono = self.bono()
        self.assertAlmostEqual(bono.cobrado, 900.0)
        self.assertFalse(bono.cumplio)
        self.assertEqual(bono.nota_ids, nota)

    def test_la_nota_aplicada_a_la_factura_resta_aunque_no_este_enlazada(self):
        factura = self.factura(2000, '2030-03-05')
        nota = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': self.cliente.id, 'invoice_date': '2030-03-08',
            'invoice_line_ids': [Command.create({'name': 'Descuento', 'quantity': 1, 'price_unit': 1500,
                                                 'tax_ids': [Command.set(self.itbms.ids)]})]})
        nota.action_post()
        self.assertFalse(nota.reversed_entry_id)
        linea_nota = nota.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        factura.js_assign_outstanding_line(linea_nota.id)
        self.pagar(factura, '2030-03-10')
        self.assertEqual(factura.payment_state, 'paid')
        bono = self.bono()
        self.assertAlmostEqual(bono.cobrado, 500.0, msg='caja recibió 500 sin ITBMS, no 2000')
        self.assertEqual((bono.factura_ids, bono.nota_ids), (factura, nota))

    def test_la_devolucion_de_una_venta_que_nunca_conto_no_resta(self):
        # Pagada antes de que rigiera la primera meta de la empresa (la de fábrica rige desde octubre de 2026).
        vieja = self.factura(800, '2026-09-10', pagar_en='2026-09-11')
        self.factura(1100, '2030-03-05', pagar_en='2030-03-06')
        nota = vieja._reverse_moves([{'date': '2030-03-15', 'invoice_date': '2030-03-15'}])
        nota.action_post()
        bono = self.bono()
        self.assertEqual((bono.cobrado, bono.monto), (1100.0, 11.0))
        self.assertFalse(bono.nota_ids)

    def test_solo_participa_el_departamento_de_ventas_con_usuario(self):
        participantes = self.Bono._participantes(self.company)
        self.assertIn(self.vera, participantes)
        self.assertNotIn(self.otto, participantes, 'otro departamento')
        sin_usuario = self._empleado('Sin usuario meta', 1200, '2029-01-01', department_id=self.ventas.id)
        self.assertNotIn(sin_usuario, self.Bono._participantes(self.company))
        # Lo que vende otra persona no cuenta para Vera.
        self.factura(5000, '2030-03-05', usuario=self.u_otto, pagar_en='2030-03-06')
        self.assertEqual(self.bono().cobrado, 0.0)

    def test_el_departamento_ventas_se_marca_una_sola_vez(self):
        Departamento = self.env['hr.department']
        ventas = Departamento.create({'name': 'VENTAS', 'company_id': self.company.id})
        self.env['ir.config_parameter'].sudo().set_param('dcasa_nomina.meta_ventas_inicializada', False)
        Departamento._dcasa_marcar_ventas()
        self.assertTrue(ventas.dcasa_meta_ventas)
        ventas.dcasa_meta_ventas = False                                  # Gerencia lo desmarca
        Departamento._dcasa_marcar_ventas()
        self.assertFalse(ventas.dcasa_meta_ventas, 'no se vuelve a marcar solo')

    # ------------------------------------------------------------------
    # La planilla
    # ------------------------------------------------------------------

    def test_entra_en_la_primera_quincena_del_mes_siguiente_y_paga_aportes(self):
        self.factura(1300, '2030-03-05', pagar_en='2030-03-06')
        planilla = self._planilla(date(2030, 4, 1), date(2030, 4, 15))
        planilla.action_calcular()
        linea = self._linea(planilla, self.vera)
        self.assertEqual(linea.comision_meta, 13.0)
        self.assertAlmostEqual(linea.devengado, linea.salario + 13.0)
        self.assertAlmostEqual(linea.css_trabajador, round(linea.devengado * 9.75 / 100, 2))
        bono = self.bono()
        self.assertEqual((bono.estado, bono.linea_id), ('en_planilla', linea))
        self.assertEqual(self._linea(planilla, self.ana).comision_meta, 0.0)
        planilla.action_calcular()                                         # recalcular no lo duplica
        self.assertEqual(self._linea(planilla, self.vera).comision_meta, 13.0)
        segunda = self._planilla(date(2030, 4, 16), date(2030, 4, 30))
        segunda.action_calcular()
        self.assertEqual(self._linea(segunda, self.vera).comision_meta, 0.0, 'solo la primera quincena')
        planilla.action_confirmar()
        self.assertEqual(bono.estado, 'pagado')
        tarde = self.factura(5000, '2030-03-25', pagar_en='2030-03-26')    # llega tarde, con fecha de marzo
        self.assertEqual(self.bono().monto, 13.0, 'el bono pagado no cambia')
        abril = self.bono(ABRIL)
        self.assertEqual((abril.cobrado, abril.factura_ids), (5000.0, tarde), 'cuenta en el primer mes abierto')
        linea = self._linea(planilla, self.vera)
        devengado = linea.devengado
        planilla.action_cancelar()
        self.assertEqual(bono.estado, 'abierto', 'si se reversa la planilla, el bono vuelve a quedar por pagar')
        self.assertEqual((linea.comision_meta, linea.devengado), (13.0, devengado),
                         'la planilla cancelada sigue igual a su asiento')
        self.assertEqual(self.bono().cobrado, 6300.0, 'marzo vuelve a estar abierto: la factura tardía es de marzo')
        self.assertEqual(self.bono(ABRIL).cobrado, 0.0, 'y ya no cuenta en abril: una sola vez')

    def test_sin_salario_el_bono_queda_por_pagar_y_entra_en_la_proxima_primera_quincena(self):
        sin_salario = self._empleado('Sin salario meta', 0, '2029-01-01', department_id=self.ventas.id,
                                     user_id=new_test_user(self.env, login='meta_sin_salario',
                                                           groups='base.group_user').id)
        self.factura(1300, '2030-03-05', usuario=sin_salario.user_id, pagar_en='2030-03-06')
        planilla = self._planilla(date(2030, 4, 1), date(2030, 4, 15))
        planilla.action_calcular()
        self.assertIn('queda por pagar', planilla.avisos)
        bono = self.bono(empleado=sin_salario)
        self.assertEqual((bono.monto, bono.estado), (13.0, 'abierto'))
        planilla.action_confirmar()
        # Gerencia le carga el salario y la saca de Ventas antes de la planilla de mayo: el bono ganado igual se paga.
        sin_salario.write({'wage': 1000, 'department_id': self.otro_depto.id})
        mayo = self._planilla(date(2030, 5, 1), date(2030, 5, 15))
        mayo.action_calcular()
        self.assertEqual(bono.linea_id, self._linea(mayo, sin_salario))
        self.assertEqual(self._linea(mayo, sin_salario).comision_meta, 13.0)

    def test_un_mes_cerrado_en_cero_no_se_pierde_lo_que_llega_tarde(self):
        self.factura(500, '2030-03-05', pagar_en='2030-03-06')
        planilla = self._planilla(date(2030, 4, 1), date(2030, 4, 15))
        planilla.action_calcular()
        marzo = self.bono()
        self.assertEqual((marzo.monto, marzo.estado), (0.0, 'en_planilla'), 'cero también cierra el mes')
        planilla.action_confirmar()
        tarde = self.factura(800, '2030-03-20', pagar_en='2030-03-28')
        self.factura(300, '2030-04-10', pagar_en='2030-04-10')
        abril = self.bono(ABRIL)
        self.assertEqual((abril.cobrado, abril.monto), (1100.0, 11.0))
        self.assertIn(tarde, abril.factura_ids)
        self.assertEqual(marzo.cobrado, 500.0)

    def test_un_pago_anulado_y_registrado_otro_mes_no_paga_dos_veces(self):
        factura = self.factura(1300, '2030-03-05', pagar_en='2030-03-06')
        planilla = self._planilla(date(2030, 4, 1), date(2030, 4, 15))
        planilla.action_calcular()
        planilla.action_confirmar()
        pago = factura._get_reconciled_payments()
        pago.action_draft()
        pago.action_cancel()
        self.assertEqual(factura.payment_state, 'not_paid')
        self.pagar(factura, '2030-04-02')
        self.assertEqual(self.bono(ABRIL).cobrado, 0.0, 'ya se pagó en el bono de marzo')
        self.assertEqual(self.bono().monto, 13.0)

    def test_una_planilla_que_deja_de_ser_primera_quincena_suelta_el_bono(self):
        self.factura(1300, '2030-03-05', pagar_en='2030-03-06')
        planilla = self._planilla(date(2030, 4, 1), date(2030, 4, 15))
        planilla.action_calcular()
        bono = self.bono()
        self.assertEqual(bono.estado, 'en_planilla')
        planilla.action_borrador()
        planilla.write({'fecha_desde': '2030-04-16', 'fecha_hasta': '2030-04-30', 'fecha_pago': '2030-04-30'})
        planilla.action_calcular()
        self.assertEqual((bono.estado, self._linea(planilla, self.vera).comision_meta), ('abierto', 0.0))

    def test_el_comprobante_de_pago_muestra_el_bono(self):
        self.factura(1300, '2030-03-05', pagar_en='2030-03-06')
        planilla = self._planilla(date(2030, 4, 1), date(2030, 4, 15))
        planilla.action_calcular()
        html, _tipo = self.env['ir.actions.report']._render_qweb_html(
            'dcasa_nomina.accion_comprobante_pago', self._linea(planilla, self.vera).ids)
        self.assertIn('Bono por meta de ventas', html.decode())
        html, _tipo = self.env['ir.actions.report']._render_qweb_html(
            'dcasa_nomina.accion_comprobante_pago', self._linea(planilla, self.ana).ids)
        self.assertNotIn('Bono por meta de ventas', html.decode())

    def test_una_meta_sin_bonos_pagados_se_puede_borrar(self):
        self.factura(1300, '2030-03-05', pagar_en='2030-03-06')
        otra = self.env['dcasa.nomina.meta.regla'].create({
            'company_id': self.company.id, 'fecha_desde': '2030-03-01', 'meta_mensual': 2000, 'porcentaje': 2})
        self.assertEqual((self.bono().regla_id, self.bono().monto), (otra, 0.0))
        otra.unlink()                       # su bono por pagar se borra y se vuelve a calcular con la meta que queda
        bono = self.bono()
        self.assertEqual((bono.regla_id, bono.monto), (self.regla, 13.0))

    def test_la_meta_solo_cambia_hacia_adelante(self):
        self.factura(1300, '2030-03-05', pagar_en='2030-03-06')
        planilla = self._planilla(date(2030, 4, 1), date(2030, 4, 15))
        planilla.action_calcular()
        planilla.action_confirmar()
        with self.assertRaises(ValidationError):
            self.regla.meta_mensual = 500
        with self.assertRaises(ValidationError):
            self.env['dcasa.nomina.meta.regla'].create({
                'company_id': self.company.id, 'fecha_desde': '2030-03-01', 'meta_mensual': 500, 'porcentaje': 2})
        nueva = self.env['dcasa.nomina.meta.regla'].create({
            'company_id': self.company.id, 'fecha_desde': '2030-04-01', 'meta_mensual': 500, 'porcentaje': 2})
        self.assertEqual(self.env['dcasa.nomina.meta.regla']._vigente(ABRIL, self.company), nueva)
        with self.assertRaises(ValidationError):
            self.env['dcasa.nomina.meta.regla'].create({
                'company_id': self.company.id, 'fecha_desde': '2030-06-15', 'meta_mensual': 500, 'porcentaje': 2})

    # ------------------------------------------------------------------
    # Lo que ve la vendedora (solo lo suyo)
    # ------------------------------------------------------------------

    @freeze_time('2030-03-20 15:00:00')
    def test_la_vendedora_ve_solo_su_meta(self):
        self.factura(1300, '2030-03-05', pagar_en='2030-03-10')
        self.factura(200, '2030-03-20', pagar_en='2030-03-20')
        self.factura(9000, '2030-03-05', usuario=self.u_otto, pagar_en='2030-03-10')
        meta = self.Bono.with_user(self.u_vera)._para_inicio(self.u_vera, date(2030, 3, 20))
        self.assertEqual((meta['cobrado'], meta['meta'], meta['faltan'], meta['hoy']), (1500.0, 1000.0, 0.0, 200.0))
        self.assertTrue(meta['cumplio'])
        self.assertEqual((meta['bono'], meta['porcentaje'], meta['avance']), (15.0, '1', 100.0))
        self.assertEqual(meta['mes'], 'marzo')
        self.assertIsNone(self.Bono._para_inicio(self.u_otto, date(2030, 3, 20)), 'Otto no está en Ventas')
        tablero = self.env.get('dcasa.tablero')
        if tablero is not None:
            datos = tablero.with_user(self.u_vera).obtener_datos()
            self.assertEqual(datos['meta']['cobrado'], 1500.0)
            self.assertNotIn(9000.0, [datos['meta'][k] for k in ('cobrado', 'hoy', 'bono')])
