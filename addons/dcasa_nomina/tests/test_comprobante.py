"""Comprobante de pago (G4): el PDF con la marca, claro, y su envío por correo respetando el interruptor."""
import ast
from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import NominaCommon

LINEA = 'odoo.addons.dcasa_nomina.models.comprobante.DcasaNominaLinea'


@tagged('post_install', '-at_install')
class TestComprobante(NominaCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ana.write({'private_email': 'ana.prueba.nomina@example.com', 'identification_id': '8-000-0000',
                       'job_title': 'Vendedora de prueba'})
        cls.beto.write({'private_email': False, 'work_email': False})
        cls.c_prestamos = cls.env['account.account'].create({
            'name': 'Anticipo al personal prueba', 'code': '9N0012', 'account_type': 'asset_current'})
        cls.config.cuenta_prestamos_id = cls.c_prestamos
        gerencia = new_test_user(cls.env, login='gerencia_comprobante', name='Gerencia Comprobante',
                                 groups='base.group_user,dcasa_base.group_gerencia')
        prestamo = cls.env['dcasa.nomina.prestamo'].create({
            'empleado_id': cls.ana.id, 'monto': 300.0, 'cuotas': 2, 'fecha': date(2030, 2, 20),
            'diario_id': cls.banco.id})
        prestamo.with_user(gerencia).action_aprobar()
        prestamo.action_entregar()
        cls.otro = new_test_user(cls.env, login='otro_comprobante', name='Otro Comprobante', groups='base.group_user')

    def _html(self, linea):
        html, _tipo = self.env['ir.actions.report']._render_qweb_html('dcasa_nomina.comprobante_pago', linea.ids)
        return html.decode()

    def _planilla_lista(self, confirmar=True):
        planilla = self._planilla(entorno=self.entorno)
        planilla.action_calcular()
        if confirmar:
            planilla.action_confirmar()
        return planilla

    def test_el_comprobante_es_claro_y_lleva_la_marca(self):
        planilla = self._planilla_lista()
        html = self._html(self._linea(planilla, self.ana))
        for texto in ('Comprobante de pago', 'Ana Prueba Nómina', '8-000-0000', 'Vendedora de prueba',
                      'Salario del periodo', 'Seguro social', 'Seguro educativo', 'Impuesto sobre la renta',
                      'Adelanto de sueldo', 'cuota 1 de 2', 'Te queda por pagar', 'Recibes', 'Recibí conforme',
                      'o_dcasa_comprobante_neto', 'o_dcasa_rejilla'):
            with self.subTest(texto=texto):
                self.assertIn(texto, html)
        self.assertIn('362.75', html)          # 512.75 − 150 de la cuota
        self.assertIn('150.00', html)          # lo que le queda después de esta quincena
        self.assertNotIn('BORRADOR', html)

    def test_el_comprobante_de_una_planilla_sin_confirmar_dice_borrador(self):
        planilla = self._planilla_lista(confirmar=False)
        self.assertIn('BORRADOR', self._html(self._linea(planilla, self.ana)))

    def test_el_reporte_sale_por_la_accion_de_imprimir(self):
        # En las pruebas Odoo devuelve el HTML en vez del PDF (sin wkhtmltopdf); el PDF real se revisa en las capturas.
        planilla = self._planilla_lista()
        accion = self.env.ref('dcasa_nomina.accion_comprobante_pago')
        contenido, tipo = self.env['ir.actions.report']._render_qweb_pdf(accion, self._linea(planilla, self.ana).ids)
        self.assertIn(tipo, ('pdf', 'html'))
        self.assertTrue(contenido)
        self.assertEqual(accion.report_type, 'qweb-pdf')

    def test_se_envia_por_correo_a_quien_tiene_correo(self):
        planilla = self._planilla_lista()
        with patch(f'{LINEA}._motivo_correo_apagado', return_value=''):
            aviso = planilla.action_enviar_comprobantes()
        correo = self.env['mail.mail'].search([('email_to', '=', 'ana.prueba.nomina@example.com')])
        self.assertEqual(len(correo), 1)
        self.assertEqual(ast.literal_eval(correo.headers)['X-Dcasa-Correo'], 'nomina')
        self.assertEqual(correo.attachment_ids.mimetype, 'application/pdf')
        self.assertTrue(correo.attachment_ids.name.endswith('.pdf'))
        self.assertTrue(correo.attachment_ids.raw)
        self.assertIn('Tu comprobante de pago', correo.body_html)
        ana = self._linea(planilla, self.ana)
        self.assertEqual(ana.comprobante_enviado_a, 'ana.prueba.nomina@example.com')
        self.assertTrue(ana.comprobante_enviado_el)
        # Beto no tiene correo: no se le manda y el aviso lo nombra
        self.assertFalse(self._linea(planilla, self.beto).comprobante_enviado_el)
        self.assertIn('Beto Prueba Nómina', aviso['params']['message'])
        self.assertEqual(aviso['params']['type'], 'warning')

    def test_con_los_correos_apagados_no_sale_nada_y_dice_por_que(self):
        planilla = self._planilla_lista()
        antes = self.env['mail.mail'].search_count([])
        with patch(f'{LINEA}._motivo_correo_apagado', return_value='Los correos están apagados (prueba).'):
            with self.assertRaisesTexto(UserError, 'apagados'):
                planilla.action_enviar_comprobantes()
        self.assertEqual(self.env['mail.mail'].search_count([]), antes)
        self.assertFalse(self._linea(planilla, self.ana).comprobante_enviado_el)

    def test_sin_confirmar_no_se_envia(self):
        planilla = self._planilla_lista(confirmar=False)
        with patch(f'{LINEA}._motivo_correo_apagado', return_value=''):
            with self.assertRaisesTexto(UserError, 'confirmada'):
                self._linea(planilla, self.ana).action_enviar_comprobante()

    def test_solo_la_nomina_envia_comprobantes(self):
        planilla = self._planilla_lista()
        with self.assertRaises(AccessError):
            planilla.with_user(self.otro).action_enviar_comprobantes()
        with self.assertRaises(AccessError):
            self._linea(planilla, self.ana).with_user(self.otro).action_enviar_comprobante()

    def test_si_esta_el_modulo_de_correo_usa_su_interruptor(self):
        """Con dcasa_correo instalado y sin clave de Resend (como en las pruebas), el motivo es el suyo."""
        if self.env.get('dcasa.correo') is None:
            self.skipTest('dcasa_correo no está instalado en esta base')
        linea = self._linea(self._planilla_lista(), self.ana)
        self.assertEqual(linea._motivo_correo_apagado(), self.env['dcasa.correo']._motivo_apagado())
        self.assertTrue(linea._motivo_correo_apagado())
