"""Adelantos y préstamos (G7): Gerencia autoriza, se entregan desde el banco, la planilla descuenta sola cada cuota,
nunca más de lo que se debe, y el saldo baja solo con planillas confirmadas."""
from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, new_test_user, tagged

from .common import NominaCommon

Q1 = (date(2030, 3, 1), date(2030, 3, 15))
Q2 = (date(2030, 3, 16), date(2030, 3, 31))
Q3 = (date(2030, 4, 1), date(2030, 4, 15))


@tagged('post_install', '-at_install')
class TestPrestamos(NominaCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.c_prestamos = cls.env['account.account'].create({
            'name': 'Anticipo al personal prueba', 'code': '9N0011', 'account_type': 'asset_current'})
        cls.config.cuenta_prestamos_id = cls.c_prestamos
        cls.gerencia = new_test_user(cls.env, login='gerencia_prestamos', name='Gerencia Préstamos',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        cls.colaborador = new_test_user(cls.env, login='colaborador_prestamos', name='Colaborador Préstamos',
                                        groups='base.group_user')

    def _prestamo(self, monto=300.0, cuotas=2, empleado=None, entregar=True, **extra):
        prestamo = self.entorno['dcasa.nomina.prestamo'].create({
            'empleado_id': (empleado or self.ana).id, 'monto': monto, 'cuotas': cuotas, 'fecha': date(2030, 2, 20),
            'diario_id': self.banco.id, **extra})
        if entregar:
            prestamo.with_user(self.gerencia).action_aprobar()
            prestamo.action_entregar()
        return prestamo

    def _calculada(self, periodo=Q1):
        planilla = self._planilla(desde=periodo[0], hasta=periodo[1], entorno=self.entorno)
        planilla.action_calcular()
        return planilla

    def _confirmada(self, periodo=Q1):
        planilla = self._calculada(periodo)
        planilla.action_confirmar()
        return planilla

    # ------------------------------------------------------------------
    # Autorizar y entregar
    # ------------------------------------------------------------------

    def test_gerencia_autoriza_y_se_entrega_desde_el_banco(self):
        prestamo = self._prestamo(entregar=False)
        self.assertEqual(prestamo.estado, 'borrador')
        self.assertEqual(prestamo.cuota, 150.0)
        with self.assertRaisesTexto(AccessError, 'Gerencia'):
            prestamo.action_aprobar()     # quien administra la nómina registra; no autoriza
        with self.assertRaisesTexto(UserError, 'autoriza'):
            prestamo.action_entregar()    # sin autorizar no se entrega
        prestamo.with_user(self.gerencia).action_aprobar()
        self.assertEqual((prestamo.estado, prestamo.aprobado_por), ('aprobado', self.gerencia))
        prestamo.action_entregar()
        self.assertEqual(prestamo.estado, 'entregado')
        pago = prestamo.payment_id
        self.assertIn(pago.state, ('in_process', 'paid'))
        self.assertEqual((pago.amount, pago.payment_type), (300.0, 'outbound'))
        self.assertEqual(pago.destination_account_id, self.c_prestamos)
        self.assertEqual(pago.partner_id, self.ana.work_contact_id)
        self.assertEqual((prestamo.saldo, self.ana.dcasa_prestamos_saldo), (300.0, 300.0))

    def test_sin_la_cuenta_de_adelantos_no_se_entrega(self):
        self.config.cuenta_prestamos_id = False
        prestamo = self._prestamo(entregar=False)
        prestamo.with_user(self.gerencia).action_aprobar()
        with self.assertRaisesTexto(UserError, 'Adelantos y préstamos al personal'):
            prestamo.action_entregar()

    def test_un_colaborador_no_registra_ni_ve_adelantos(self):
        with self.assertRaises(AccessError):
            self.env(user=self.colaborador)['dcasa.nomina.prestamo'].create({
                'empleado_id': self.ana.id, 'monto': 50.0, 'cuotas': 1})
        prestamo = self._prestamo(entregar=False)
        with self.assertRaises(AccessError):
            prestamo.with_user(self.colaborador).read(['monto'])

    def test_autorizado_no_cambia_de_monto_ni_el_estado_por_rpc(self):
        prestamo = self._prestamo(entregar=False)
        with self.assertRaises(AccessError):
            prestamo.write({'estado': 'entregado'})
        prestamo.with_user(self.gerencia).action_aprobar()
        with self.assertRaisesTexto(UserError, 'ya no cambia'):
            prestamo.write({'monto': 999.0})
        prestamo.write({'notas': 'Lo pidió para la escuela'})     # las notas sí

    def test_monto_y_cuotas_validos(self):
        with self.assertRaises(ValidationError):
            self._prestamo(monto=0.0, entregar=False)
        with self.assertRaises(ValidationError):
            self._prestamo(cuotas=0, entregar=False)

    # ------------------------------------------------------------------
    # La planilla lo descuenta sola
    # ------------------------------------------------------------------

    def test_la_planilla_descuenta_la_cuota_y_la_contabiliza_a_su_nombre(self):
        prestamo = self._prestamo(monto=300.0, cuotas=2)
        planilla = self._calculada()
        ana = self._linea(planilla, self.ana)
        self.assertEqual(ana.prestamos, 150.0)
        self.assertEqual(ana.neto, 512.75 - 150.0)
        self.assertEqual(planilla.total_prestamos, 150.0)
        self.assertEqual((prestamo.en_planilla, prestamo.saldo), (150.0, 300.0))   # reservado, no descontado
        planilla.action_confirmar()
        self.assertEqual(self._sumas(planilla.move_id)[self.c_prestamos], (0.0, 150.0))
        apunte = planilla.move_id.line_ids.filtered(lambda ln: ln.account_id == self.c_prestamos)
        self.assertEqual(apunte.partner_id, self.ana.work_contact_id)
        debe = sum(planilla.move_id.line_ids.mapped('debit'))
        self.assertAlmostEqual(debe, sum(planilla.move_id.line_ids.mapped('credit')), places=2)
        self.assertEqual((prestamo.descontado, prestamo.saldo, prestamo.estado), (150.0, 150.0, 'entregado'))

    def test_en_tres_quincenas_los_centavos_no_dejan_saldo_y_queda_pagado(self):
        prestamo = self._prestamo(monto=100.0, cuotas=3)
        cuotas = []
        for periodo in (Q1, Q2, Q3):
            planilla = self._confirmada(periodo)
            cuotas.append(self._linea(planilla, self.ana).prestamos)
        self.assertEqual(cuotas, [33.33, 33.33, 33.34])
        self.assertEqual((prestamo.saldo, prestamo.estado, prestamo.cuotas_descontadas), (0.0, 'pagado', 3))
        self.assertEqual(self.ana.dcasa_prestamos_saldo, 0.0)
        # una cuarta quincena ya no descuenta nada
        cuarta = self._calculada((date(2030, 4, 16), date(2030, 4, 30)))
        self.assertEqual(self._linea(cuarta, self.ana).prestamos, 0.0)

    def test_nunca_descuenta_mas_de_lo_que_debe(self):
        prestamo = self._prestamo(monto=200.0, cuotas=1)
        primera = self._calculada(Q1)
        self.assertEqual(self._linea(primera, self.ana).prestamos, 200.0)
        # otra planilla sin confirmar no vuelve a descontar lo que ya está reservado en la primera
        segunda = self._calculada(Q2)
        self.assertEqual(self._linea(segunda, self.ana).prestamos, 0.0)
        # ni a mano
        with self.assertRaisesTexto(ValidationError, 'más de lo que'):
            self.env['dcasa.nomina.prestamo.descuento'].create({
                'prestamo_id': prestamo.id, 'linea_id': self._linea(segunda, self.ana).id, 'monto': 1.0})
        with self.assertRaises(ValidationError):
            self.env['dcasa.nomina.prestamo.descuento'].create({
                'prestamo_id': prestamo.id, 'linea_id': self._linea(segunda, self.beto).id, 'monto': 1.0})

    def test_empieza_a_descontar_en_la_quincena_elegida(self):
        self._prestamo(monto=80.0, cuotas=1, primera_quincena=date(2030, 3, 31))
        self.assertEqual(self._linea(self._calculada(Q1), self.ana).prestamos, 0.0)

    def test_el_decimo_no_descuenta_adelantos(self):
        self._prestamo(monto=80.0, cuotas=1)
        decimo = self.entorno['dcasa.nomina.planilla'].create({'tipo': 'decimo', 'anio': 2030, 'partida': '1'})
        decimo.action_calcular()
        self.assertFalse(decimo.linea_ids.prestamo_descuento_ids)
        self.assertFalse(any(decimo.linea_ids.mapped('prestamos')))

    def test_recalcular_no_duplica_la_cuota(self):
        self._prestamo(monto=300.0, cuotas=2)
        planilla = self._calculada()
        planilla.action_calcular()
        planilla.action_calcular()
        self.assertEqual(len(planilla.linea_ids.prestamo_descuento_ids), 1)
        self.assertEqual(self._linea(planilla, self.ana).prestamos, 150.0)

    # ------------------------------------------------------------------
    # Volver atrás
    # ------------------------------------------------------------------

    def test_cancelar_una_planilla_devuelve_la_cuota(self):
        prestamo = self._prestamo(monto=100.0, cuotas=1)
        sin_confirmar = self._calculada(Q1)
        sin_confirmar.action_cancelar()
        self.assertFalse(sin_confirmar.linea_ids.prestamo_descuento_ids)
        self.assertEqual((prestamo.en_planilla, prestamo.saldo), (0.0, 100.0))
        confirmada = self._confirmada(Q2)
        self.assertEqual(prestamo.estado, 'pagado')
        confirmada.action_cancelar()   # se reversa el asiento: la cuota ya no cuenta
        self.assertEqual((prestamo.saldo, prestamo.estado), (100.0, 'entregado'))
        otra = self._calculada(Q3)
        self.assertEqual(self._linea(otra, self.ana).prestamos, 100.0)

    def test_entregado_no_se_cancela_ni_se_borra(self):
        prestamo = self._prestamo()
        with self.assertRaisesTexto(UserError, 'no se cancela'):
            prestamo.action_cancelar()
        with self.assertRaises(UserError):
            prestamo.unlink()

    def test_por_autorizar_se_cancela_y_se_borra(self):
        prestamo = self._prestamo(entregar=False)
        prestamo.action_cancelar()
        self.assertEqual(prestamo.estado, 'cancelado')
        prestamo.action_borrador()
        prestamo.unlink()

    # ------------------------------------------------------------------
    # Pantalla
    # ------------------------------------------------------------------

    def test_registrar_desde_el_formulario(self):
        with Form(self.entorno['dcasa.nomina.prestamo']) as form:
            form.empleado_id = self.beto
            form.tipo = 'prestamo'
            form.monto = 500.0
            form.cuotas = 4
            form.fecha = '2030-03-02'
            self.assertEqual(form.cuota, 125.0)
            self.assertEqual(str(form.primera_quincena), '2030-03-02')
            form.motivo = 'Emergencia'
        self.assertEqual((form.record.estado, form.record.name), ('borrador', 'Préstamo · Beto Prueba Nómina'))
        vistas = self.entorno['dcasa.nomina.prestamo'].get_views([(False, 'list'), (False, 'form'), (False, 'search')])
        self.assertIn('saldo', vistas['views']['list']['arch'])

    def test_la_propuesta_encuentra_la_cuenta_del_plan_de_panama_con_sus_7_digitos(self):
        """El plan instalado guarda «134» como «1340000»: la propuesta la encuentra (antes buscaba el código exacto y
        no proponía ninguna cuenta)."""
        anticipo = self.env['account.account'].search([('code', '=like', '134%')], order='code', limit=1)
        if not anticipo:
            self.skipTest('El plan de cuentas de Panamá no está cargado en esta base')
        propuesta = self.env['dcasa.nomina.config']._propuesta(self.company)
        self.assertEqual(propuesta['cuenta_prestamos_id'], anticipo.id)
