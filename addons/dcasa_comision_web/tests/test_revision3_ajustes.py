"""Tercera revisión: los ajustes a mano en el libro (monto inválido, tope que decide Gerencia) y «quien cobra no
aprueba». Cada prueba dice en su nombre lo que se intentó. Cifras y personas de PRUEBA."""
# ruff: noqa: E501, UP031, B007, B023, F841, PLW0108, RUF012

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_endurecimiento import Liquida


@tagged('post_install', '-at_install')
class TestAjustesYAprobacion(Liquida):

    def ajuste(self, usuario, empleado, monto, motivo='corrección'):
        asistente = self.env['dcasa.web.ajuste'].with_user(usuario).create({
            'empleado_id': empleado.id, 'concepto': 'comision', 'monto': monto, 'motivo': motivo})
        asistente.action_anotar()

    def test_ajuste_a_alguien_que_figuro_en_un_reparto_antiguo_entra_en_la_liquidacion_con_aviso(self):
        self.version(10.0)
        self.version(10.0, reparto=[(self.ana, 100.0)])     # Beto ya no figura, pero figuró
        self.venta_web()
        self.ajuste(self.u_ana, self.beto, 500.0, 'bono especial')
        self.avanzar('2030-03-05 15:00:00')
        liq = self.liquidar(usuario=self.u_nomina, hasta='2030-03-31')
        lineas = {ln.empleado_id.name: ln.centavos for ln in liq.sudo().linea_ids}
        self.assertEqual(lineas.get(self.beto.name), 50000)
        self.assertIn('bono especial', liq.avisos or '')
        self.assertIn(self.u_ana.login, liq.avisos or '')

    def test_ajuste_propio_se_marca_aunque_el_usuario_sea_el_contacto_de_trabajo(self):
        self.version(10.0)
        self.venta_web()
        self.ajuste(self.u_ana, self.ana, 500.0)
        self.avanzar('2030-03-05 15:00:00')
        liq = self.liquidar(usuario=self.u_nomina, hasta='2030-03-31')
        self.assertIn('MISMA PERSONA', liq.avisos or '')

    def test_ajuste_propio_con_otro_usuario_de_nomina_no_ligado_a_la_ficha_deja_al_menos_el_autor_en_el_aviso(self):
        """El límite honesto documentado: el mismo humano con OTRO usuario de Nómina no ligado."""
        self.version(10.0)
        self.venta_web()
        otro = self.env['res.users'].create({'name': 'Ana segundo usuario', 'login': 'ana_2do_usuario',
                                             'group_ids': [Command.set([self.env.ref('base.group_user').id,
                                                                        self.env.ref('dcasa_nomina.group_nomina').id])]})
        self.ajuste(otro, self.ana, 500.0)
        self.avanzar('2030-03-05 15:00:00')
        liq = self.liquidar(usuario=self.u_nomina, hasta='2030-03-31')
        self.assertIn('ana_2do_usuario', liq.avisos or '')

    def test_un_ajuste_sin_motivo_o_en_cero_se_rechaza(self):
        self.version(10.0)
        self.venta_web()
        for monto, motivo in ((500.0, ''), (500.0, '   '), (0.0, 'x'), (0.001, 'x')):
            with self.subTest(monto=monto, motivo=motivo):
                self.rechaza(lambda: self.ajuste(self.u_nomina, self.ana, monto, motivo))

    def test_un_monto_que_no_es_un_numero_o_no_cabe_en_el_libro_da_un_error_claro(self):
        """Antes: OverflowError, ValueError o NumericValueOutOfRange sin traducir."""
        self.version(10.0)
        self.venta_web()
        for monto in (1e12, -1e12, float('inf'), float('-inf'), float('nan')):
            with self.subTest(monto=monto):
                with self.assertRaises(UserError) as error, self.env.cr.savepoint():
                    self.ajuste(self.u_nomina, self.ana, monto)
                self.assertRegex(str(error.exception), 'no es un número válido|demasiado grande')
        self.assertFalse(self.libro(tipo='ajuste'))

    def test_sin_tope_un_ajuste_grande_entra_con_aviso_hasta_lo_que_cabe_en_el_libro(self):
        """Decisión pendiente de Gerencia: el sistema no trae tope. Un ajuste de 20 millones entra y la liquidación lo
        avisa con quién lo anotó y por qué."""
        self.version(10.0)
        self.venta_web()
        self.ajuste(self.u_nomina, self.ana, 20_000_000.0, 'ajuste enorme de prueba')
        self.avanzar('2030-03-05 15:00:00')
        liq = self.liquidar(usuario=self.u_gerencia, hasta='2030-03-31')
        self.assertIn('ajuste enorme de prueba', liq.avisos or '')

    def test_el_tope_que_pone_gerencia_en_las_reglas_rige_para_los_ajustes(self):
        self.version(10.0, tope_ajuste=1000.0)
        self.venta_web()
        self.ajuste(self.u_nomina, self.ana, 1000.0, 'justo el tope')
        self.ajuste(self.u_nomina, self.ana, -1000.0, 'justo el tope hacia el otro lado')
        for monto in (1000.01, -1000.01):
            with self.subTest(monto=monto):
                with self.assertRaisesRegex(UserError, 'no puede pasar de 1,000.00'), self.env.cr.savepoint():
                    self.ajuste(self.u_nomina, self.ana, monto, 'de más')
        self.version(10.0)         # una versión nueva sin tope lo quita (hacia adelante)
        self.ajuste(self.u_nomina, self.ana, 5000.0, 'sin tope otra vez')
        self.assertEqual(len(self.libro(tipo='ajuste')), 3)

    def test_un_tope_negativo_no_se_guarda(self):
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.version(10.0, tope_ajuste=-1.0)

    def test_hoy_quien_cobra_puede_cancelar_una_liquidacion_que_aprobo_otra_persona_decision_pendiente(self):
        """Constancia, NO una política: Ana cobra en la liquidación que aprobó la persona de Nómina, y Ana (con rol de
        Nómina) la cancela. Gerencia decide si debe poder (docs/COMISION_WEB.md, «Por decidir»): hoy se deja como está."""
        self.version(10.0)
        self.venta_web()
        self.avanzar('2030-03-05 15:00:00')
        liq = self.liquidar(usuario=self.u_nomina, hasta='2030-03-31')
        liq.with_user(self.u_nomina).action_aprobar()
        liq.with_user(self.u_ana).write({'motivo_cancelacion': 'ya se pagó por fuera'})
        liq.with_user(self.u_ana).action_cancelar()
        self.assertEqual(liq.estado, 'cancelada')

    def test_quien_cobra_no_aprueba_ni_con_la_ficha_cambiada_antes(self):
        self.version(10.0)
        self.venta_web()
        self.avanzar('2030-03-05 15:00:00')
        liq = self.liquidar(usuario=self.u_nomina, hasta='2030-03-31')
        self.ana.sudo().user_id = False
        self.rechaza(lambda: liq.with_user(self.u_ana).action_aprobar())

    def test_un_empleado_con_dos_fichas_una_dentro_y_otra_fuera_del_reparto(self):
        """La misma persona (el mismo usuario) con una segunda ficha que NO figura en el reparto: aprobar una liquidación
        donde cobra la primera ficha sigue bloqueado, y un ajuste a la segunda se rechaza."""
        self.version(10.0)
        self.venta_web()
        segunda = self._empleado('Ana segunda ficha', 1200, '2029-01-01', work_contact_id=self.u_ana.partner_id.id)
        self.rechaza(lambda: self.ajuste(self.u_nomina, segunda, 100.0))
        self.avanzar('2030-03-05 15:00:00')
        liq = self.liquidar(usuario=self.u_nomina, hasta='2030-03-31')
        self.rechaza(lambda: liq.with_user(self.u_ana).action_aprobar())
