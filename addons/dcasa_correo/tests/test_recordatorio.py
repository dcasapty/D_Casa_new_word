"""D3: el correo que recuerda el abono unos días antes de que venza. Uno por abono y vencimiento, nunca repetido,
apagado mientras no haya clave de Resend (o con su interruptor apagado)."""
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from ..models.correo import P_RECORDATORIO
from .common import CorreoCase


@tagged('post_install', '-at_install')
class TestRecordatorioDeAbono(CorreoCase):

    def setUp(self):
        super().setUp()
        self.ICP.set_param(P_RECORDATORIO, 'True')
        self.ICP.set_param('dcasa_invoice.abono_dias', '30')
        self.hoy = fields.Date.context_today(self.env['account.move'])

    def _abono(self, partner=None, hace_dias=27):
        """Factura de $200 con un abono de $100 pagado hace ``hace_dias`` (27 → vence en 3 días)."""
        factura = self.factura(partner)
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'amount': 100.0, 'journal_id': self.diario.id,
                'payment_date': self.hoy - timedelta(days=hace_dias)}).action_create_payments()
        self.assertEqual(factura.payment_state, 'partial')
        return factura

    def _encolar(self):
        return self.env['dcasa.correo.envio'].sudo()._encolar_recordatorios()

    def test_uno_por_abono_y_vencimiento(self):
        self.encender()
        factura = self._abono()
        lejos = self._abono(self.beto, hace_dias=0)
        (envio,) = self._encolar()
        self.assertEqual(envio.tipo, 'recordatorio')
        self.assertEqual(envio.move_id, factura)
        self.assertEqual(envio.huella, f'{factura.id}:{(self.hoy + timedelta(days=3)).isoformat()}')
        self.assertFalse(self.envios(tipo='recordatorio', move_id=lejos.id))
        # Mañana sigue ahí: no se repite.
        self.assertFalse(self._encolar())
        self.procesar()
        self.assertEqual(envio.estado, 'enviado')
        self.assertEqual(envio.correo, 'ana@example.com')
        mensaje = envio.message_id
        self.assertIn('Tu abono vence el', mensaje.subject)
        self.assertIn('$100.00', mensaje.body)
        self.assertIn('Te falta', mensaje.body)
        self.assertIn('Enviado el', factura.dcasa_recordatorio)
        # Si el vencimiento cambia (otro plazo), es otro recordatorio.
        self.ICP.set_param('dcasa_invoice.abono_dias', '31')
        self.env['account.move']._dcasa_recalcular_vencimientos()
        self.assertEqual(len(self._encolar()), 1)

    def test_apagado_no_sale_nada(self):
        factura = self._abono()
        self.assertFalse(self._encolar(), 'sin clave de Resend no se encola nada')
        self.encender()
        self.ICP.set_param(P_RECORDATORIO, False)
        self.assertFalse(self._encolar(), 'con el recordatorio apagado tampoco')
        self.assertFalse(self.envios(tipo='recordatorio', move_id=factura.id))

    def test_sin_correo_se_omite_y_vuelve_si_lo_escriben(self):
        self.encender()
        factura = self._abono(self.sin_correo)
        (envio,) = self._encolar()
        self.procesar()
        self.assertEqual(envio.estado, 'omitido')
        self.assertEqual(envio.causa, 'sin_correo')
        self.sin_correo.email = 'carla@example.com'
        self.assertEqual(self._encolar(), envio)
        self.procesar()
        self.assertEqual(envio.estado, 'enviado')
        self.assertEqual(envio.move_id, factura)

    def test_si_se_paga_antes_de_armarlo_no_sale(self):
        self.encender()
        factura = self._abono()
        (envio,) = self._encolar()
        self.pagar(factura, 100.0)
        self.procesar()
        self.assertEqual(envio.estado, 'omitido')
        self.assertEqual(envio.causa, 'cambio')

    def test_el_cron_de_abonos_lo_encola(self):
        self.encender()
        factura = self._abono()
        self.env['account.move']._dcasa_cron_abonos()
        self.assertEqual(len(self.envios(tipo='recordatorio', move_id=factura.id)), 1)
