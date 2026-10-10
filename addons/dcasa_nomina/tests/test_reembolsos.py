"""Reembolsos en nómina: el flujo completo y quién puede hacer qué."""
import base64

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged

from .common import NominaCommon


@tagged('post_install', '-at_install')
class TestReembolsos(NominaCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_ana = new_test_user(cls.env, login='ana_reembolsos', name='Ana Reembolsos', groups='base.group_user')
        cls.user_beto = new_test_user(cls.env, login='beto_reembolsos', name='Beto Reembolsos',
                                      groups='base.group_user')
        cls.ana.user_id = cls.user_ana
        cls.beto.user_id = cls.user_beto
        cls.cliente_ajeno = cls.env['res.partner'].create({'name': 'Cliente ajeno prueba nómina'})

    def _recibo(self, usuario=None):
        # como en la pantalla: la foto la sube el propio colaborador
        return self.env['ir.attachment'].with_user(usuario or self.user_ana).create({
            'name': 'recibo.png', 'raw': base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')})

    def _reembolso(self, usuario=None, monto=25.0, **extra):
        entorno = self.env(user=usuario or self.user_ana)
        return entorno['dcasa.nomina.reembolso'].create({
            'empleado_id': self.ana.id, 'concepto': 'Taxi a la bodega', 'monto': monto, **extra})

    def _aprobado(self, monto=25.0):
        reembolso = self._reembolso(monto=monto)
        reembolso.recibo_ids = self._recibo()
        reembolso.action_enviar()
        reembolso.with_user(self.usuario).action_aprobar()
        return reembolso

    # ------------------------------------------------------------------
    # Flujo
    # ------------------------------------------------------------------

    def test_el_colaborador_registra_envia_y_la_administracion_aprueba(self):
        reembolso = self._reembolso()
        self.assertEqual(reembolso.estado, 'borrador')
        self.assertEqual(reembolso.cuenta_gasto_id, self.c_reembolso)  # la de la configuración
        with self.assertRaisesTexto(UserError, 'foto del recibo'):
            reembolso.action_enviar()
        reembolso.recibo_ids = self._recibo()
        reembolso.action_enviar()
        self.assertEqual(reembolso.estado, 'enviado')
        reembolso.with_user(self.usuario).action_aprobar()
        self.assertEqual(reembolso.estado, 'aprobado')
        self.assertEqual(reembolso.aprobado_por, self.usuario)

    def test_rechazar_pide_motivo_y_el_colaborador_puede_corregir_y_reenviar(self):
        reembolso = self._reembolso()
        reembolso.recibo_ids = self._recibo()
        reembolso.action_enviar()
        admin = reembolso.with_user(self.usuario)
        with self.assertRaisesTexto(UserError, 'motivo'):
            admin.action_rechazar()
        admin.motivo_rechazo = 'El recibo no se lee'
        admin.action_rechazar()
        self.assertEqual(reembolso.estado, 'rechazado')
        reembolso.action_enviar()  # lo reenvía después de corregir
        self.assertEqual(reembolso.estado, 'enviado')
        self.assertFalse(reembolso.motivo_rechazo)

    def test_la_administracion_ve_la_foto_del_recibo_que_subio_el_colaborador(self):
        recibo = self._recibo()
        reembolso = self._reembolso()
        reembolso.recibo_ids = recibo
        self.assertEqual((recibo.res_model, recibo.res_id), ('dcasa.nomina.reembolso', reembolso.id))
        self.assertEqual(recibo.with_user(self.usuario).name, 'recibo.png')   # la nómina la lee
        with self.assertRaises(AccessError):                                  # otro colaborador, no
            recibo.with_user(self.user_beto).read(['name'])

    def test_un_adjunto_que_ya_tiene_dueno_no_se_reasigna_como_recibo(self):
        ajeno = self.env['ir.attachment'].create({'name': 'factura.pdf', 'raw': b'x', 'res_model': 'res.partner',
                                                  'res_id': self.cliente_ajeno.id})
        reembolso = self._reembolso()
        reembolso.recibo_ids = ajeno  # un adjunto que ya tiene dueño no se reasigna, aunque se pueda leer
        self.assertEqual((ajeno.res_model, ajeno.res_id), ('res.partner', self.cliente_ajeno.id))

    def test_monto_cero_o_negativo(self):
        with self.assertRaises(ValidationError):
            self._reembolso(monto=0.0)

    def test_la_planilla_suma_los_aprobados_al_neto_sin_pagar_aportes_sobre_ellos(self):
        reembolso = self._aprobado(25.0)
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        self.assertEqual(reembolso.estado, 'en_planilla')
        ana = self._linea(planilla, self.ana)
        self.assertEqual(ana.reembolsos, 25.0)
        self.assertEqual(ana.devengado, 600.0)            # el reembolso no es salario
        self.assertEqual(ana.css_trabajador, 58.5)        # ni paga aportes
        self.assertEqual(ana.neto, 537.75)                # 512.75 + 25
        # recalcular no lo cuenta dos veces
        planilla.action_calcular()
        self.assertEqual(self._linea(planilla, self.ana).reembolsos, 25.0)

    def test_confirmar_contabiliza_el_gasto_y_lo_marca(self):
        reembolso = self._aprobado(25.0)
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        planilla.action_confirmar()
        self.assertEqual(reembolso.estado, 'contabilizado')
        sumas = self._sumas(planilla.move_id)
        self.assertEqual(sumas[self.c_reembolso], (25.0, 0.0))
        self.assertEqual(sumas[self.c_por_pagar][1], 777.03)  # 752.03 + 25 de reembolso
        self.assertAlmostEqual(sum(planilla.move_id.line_ids.mapped('debit')),
                               sum(planilla.move_id.line_ids.mapped('credit')))

    def test_cancelar_la_planilla_libera_el_reembolso(self):
        reembolso = self._aprobado()
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        planilla.action_cancelar()
        self.assertEqual(reembolso.estado, 'aprobado')
        self.assertFalse(reembolso.linea_id)
        # y vuelve a entrar en la planilla siguiente
        otra = self._planilla(entorno=self.entorno)
        otra.action_calcular()
        self.assertEqual(reembolso.estado, 'en_planilla')

    def test_cancelar_una_confirmada_tambien_lo_libera(self):
        reembolso = self._aprobado()
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        planilla.action_confirmar()
        planilla.action_cancelar()
        self.assertEqual(reembolso.estado, 'aprobado')

    def test_sin_cuenta_de_gasto_no_se_aprueba(self):
        self.config.cuenta_reembolsos_id = False
        reembolso = self._reembolso()
        reembolso.recibo_ids = self._recibo()
        reembolso.action_enviar()
        with self.assertRaisesTexto(UserError, 'cuenta de gasto'):
            reembolso.with_user(self.usuario).action_aprobar()

    # ------------------------------------------------------------------
    # Quién puede qué
    # ------------------------------------------------------------------

    def test_nadie_aprueba_su_propio_reembolso(self):
        reembolso = self._reembolso()
        reembolso.recibo_ids = self._recibo()
        reembolso.action_enviar()
        with self.assertRaises(AccessError):
            reembolso.action_aprobar()
        with self.assertRaises(AccessError):
            reembolso.action_rechazar()

    def test_el_estado_no_se_escribe_por_rpc(self):
        reembolso = self._reembolso()
        for campo, valor in (('estado', 'aprobado'), ('aprobado_por', self.user_ana.id), ('linea_id', False)):
            with self.subTest(campo=campo), self.assertRaises(AccessError):
                reembolso.write({campo: valor})

    def test_un_reembolso_enviado_ya_no_se_edita(self):
        reembolso = self._reembolso()
        reembolso.recibo_ids = self._recibo()
        reembolso.action_enviar()
        with self.assertRaisesTexto(UserError, 'ya no se edita'):
            reembolso.write({'monto': 999.0})

    def test_solo_registra_reembolsos_a_su_nombre(self):
        with self.assertRaises(AccessError):
            self.env(user=self.user_beto)['dcasa.nomina.reembolso'].create({
                'empleado_id': self.ana.id, 'concepto': 'A nombre de otra persona', 'monto': 10.0})

    def test_no_se_puede_crear_ya_aprobado(self):
        with self.assertRaises(AccessError):
            self.env(user=self.user_ana)['dcasa.nomina.reembolso'].create({
                'empleado_id': self.ana.id, 'concepto': 'Colado', 'monto': 10.0, 'estado': 'aprobado'})

    def test_cada_quien_ve_solo_los_suyos_y_la_nomina_ve_todos(self):
        mio = self._reembolso()
        otro = self.env(user=self.user_beto)['dcasa.nomina.reembolso'].create({
            'empleado_id': self.beto.id, 'concepto': 'Del otro', 'monto': 5.0})
        Reembolso = self.env['dcasa.nomina.reembolso']
        self.assertEqual(Reembolso.with_user(self.user_ana).search([('id', 'in', (mio + otro).ids)]), mio)
        self.assertEqual(Reembolso.with_user(self.user_beto).search([('id', 'in', (mio + otro).ids)]), otro)
        self.assertEqual(Reembolso.with_user(self.usuario).search([('id', 'in', (mio + otro).ids)]), mio + otro)
        with self.assertRaises(AccessError):
            otro.with_user(self.user_ana).read(['monto'])

    def test_solo_se_borra_un_borrador(self):
        reembolso = self._reembolso()
        reembolso.recibo_ids = self._recibo()
        reembolso.action_enviar()
        with self.assertRaisesTexto(UserError, 'Solo se borra'):
            reembolso.unlink()
        reembolso.action_borrador()
        reembolso.unlink()
