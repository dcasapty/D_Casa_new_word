"""Segunda revision adversarial, parte C: limites de la proteccion de «quien cobra no aprueba», la
tarifa del primer dia y el chatter de la ficha. Cifras y personas de PRUEBA."""
# ruff: noqa: E501, UP031, B007, B023, F841, PLW0108, RUF012  (pruebas de la segunda revision: se conservan tal como se escribieron)
from datetime import date

from odoo import Command
from odoo.tests import tagged

from .test_comision import ComisionReloj
from .test_endurecimiento import Liquida


@tagged('post_install', '-at_install')
class TestRevision2Proteccion(Liquida):

    def test_revision2_35_gerencia_y_nomina_no_crean_usuarios_ni_se_dan_roles(self):
        """Lo unico que deja a quien cobra aprobar lo suyo (rv_11) es un SEGUNDO usuario con rol de Nomina: solo lo
        puede crear quien administra usuarios (el tecnico). Gerencia y Nomina no."""
        for usuario in (self.u_gerencia, self.u_nomina):
            with self.subTest(usuario=usuario.login):
                self.rechaza(lambda: self.env['res.users'].with_user(usuario).with_context(no_reset_password=True).create({
                    'name': 'Segundo usuario rv2', 'login': 'segundo_rv2_%s' % usuario.id, 'email': 'seg.rv2@example.com',
                    'group_ids': [Command.set([self.env.ref('base.group_user').id,
                                               self.env.ref('dcasa_nomina.group_nomina').id])]}))
                self.rechaza(lambda: self.u_caja.with_user(usuario).write(
                    {'group_ids': [Command.link(self.env.ref('dcasa_nomina.group_nomina').id)]}))

    def test_revision2_36_el_receptor_cambia_su_ficha_y_aun_asi_no_aprueba(self):
        """Quien cobra suelta su usuario, su contacto de trabajo y los cambia por los de otra persona: sigue sin poder."""
        self.version(10.0)
        self.venta_web()
        self.avanzar('2030-04-02 15:00:00')
        liq = self.liquidar(usuario=self.u_nomina)
        self.ana.sudo().write({'user_id': False, 'work_contact_id': False})
        self.rechaza(lambda: liq.with_user(self.u_ana).action_aprobar())
        self.assertEqual(liq.estado, 'borrador')
        # y quien no cobra, si
        liq.with_user(self.u_nomina).action_aprobar()
        self.assertEqual(liq.estado, 'aprobada')

    def test_revision2_37_cualquiera_de_nomina_cancela_una_aprobada_y_la_vuelve_a_armar(self):
        """OBSERVACION: cancelar una aprobada (aunque quien cancela sea quien cobra) devuelve el saldo; lo que ya se haya
        pagado fuera del sistema antes de marcar «pagada» se volveria a pagar. Se documenta lo que pasa hoy."""
        self.version(10.0)
        self.venta_web()
        self.avanzar('2030-04-02 15:00:00')
        liq = self.liquidar(usuario=self.u_nomina)
        liq.with_user(self.u_nomina).action_aprobar()
        self.assertEqual(self.saldo(self.ana), 0)
        liq.with_user(self.u_ana).write({'motivo_cancelacion': 'rv2'})
        liq.with_user(self.u_ana).action_cancelar()          # quien cobra cancela la que aprobo otra persona
        self.assertEqual(self.saldo(self.ana), 6000, 'el saldo vuelve: se puede cobrar de nuevo')


@tagged('post_install', '-at_install')
class TestRevision2TarifaYChatter(ComisionReloj):

    def test_revision2_91_una_version_que_rige_el_dia_que_empieza_el_periodo_anota_la_tarifa_de_ese_periodo(self):
        """HALLAZGO (menor): la ayuda dice que «Rige desde» es el INICIO del dia (las ventas y las vendedoras lo usan
        asi), pero la tarifa compara la hora tecleada: una version guardada el lunes (periodo semanal) con la hora de
        ahora no anota la tarifa de ESE lunes, y una guardada con las 00:00 si."""
        self.version(0.0, tarifa=10.0, tarifa_periodo='semanal')           # lunes 4, con la hora de ahora
        anotadas = self.env['dcasa.web.movimiento']._cron_tarifa(hoy=date(2030, 3, 4))
        self.assertEqual(anotadas, 2, 'rige desde el inicio del lunes: la semana que empieza hoy ya cuenta')

    def test_revision2_92_el_cambio_de_usuario_de_la_ficha_deja_un_mensaje_real_en_el_chatter(self):
        """Los usuarios ligados son la base de «quien cobra no aprueba»: el cambio tiene que dejar rastro de verdad
        (la prueba del autor solo mira la bandera ``tracking`` del campo)."""
        ficha = self.ana.with_context(tracking_disable=False)
        antes = len(ficha.message_ids)
        ficha.user_id = self.u_caja
        self.env.flush_all()
        self.env.cr.precommit.run()          # el chatter se escribe al confirmar la transaccion
        ficha.invalidate_recordset()
        nuevos = ficha.message_ids.sorted('id')[antes:]
        self.assertTrue(any(v.field_id.name == 'user_id' for v in nuevos.tracking_value_ids),
                        'cambiar el usuario de la ficha no dejo rastro en el chatter')
