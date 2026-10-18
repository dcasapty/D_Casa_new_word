"""Lo pagado y lo que falta de una factura con abonos (_dcasa_estado_abono): una sola fuente para el papel, las
Condiciones de abono, «Mi cuenta», los correos y Brian. Solo lee: los asientos de la factura y de los pagos quedan
iguales. El plazo es de 30 días continuos desde el primer abono (decisión de la gerencia A3, 2026-10-17)."""
import importlib.util
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

from ..models.account_move import PARAMETRO_DIAS_ABONO, PARAMETRO_MESES_VIEJO


@tagged('post_install', '-at_install')
class TestEstadoAbono(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env['res.partner'].create({'name': 'CLIENTE ABONO'})
        cls.mueble = cls.env['product.product'].create({
            'name': 'SOFÁ ABONO', 'type': 'consu', 'list_price': 200.0, 'taxes_id': [Command.clear()]})

    def _factura(self):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 200.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        return factura

    def _pagar(self, factura, monto, fecha):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'payment_date': fecha, 'amount': monto}).action_create_payments()

    def test_un_abono_dice_cuanto_falta_y_cuando_vence(self):
        factura = self._factura()
        inicio = fields.Date.today() - relativedelta(days=3)
        self._pagar(factura, 80.0, inicio)
        estado = factura._dcasa_estado_abono()
        self.assertTrue(estado['es_abono'])
        self.assertEqual((estado['total'], estado['pagado'], estado['saldo']), (200.0, 80.0, 120.0))
        self.assertEqual(estado['inicio'], inicio)
        self.assertEqual(estado['vence'], inicio + timedelta(days=30), 'la gerencia: 30 días continuos')
        self.assertFalse(estado['vencido'])
        self.assertEqual([a['monto'] for a in estado['abonos']], [80.0])

    def test_el_plazo_cuenta_desde_el_primer_abono_y_avisa_si_ya_paso(self):
        factura = self._factura()
        primero = fields.Date.today() - relativedelta(months=2)
        self._pagar(factura, 50.0, primero)
        self._pagar(factura, 50.0, fields.Date.today())
        estado = factura._dcasa_estado_abono()
        self.assertEqual(estado['inicio'], primero)
        self.assertEqual(estado['saldo'], 100.0)
        self.assertTrue(estado['vencido'])

    def test_pagada_por_completo_ya_no_es_abono_ni_vence(self):
        factura = self._factura()
        self._pagar(factura, 50.0, fields.Date.today())
        self._pagar(factura, 150.0, fields.Date.today())
        estado = factura._dcasa_estado_abono()
        self.assertFalse(estado['es_abono'])
        self.assertEqual(estado['saldo'], 0.0)
        self.assertFalse(estado['vence'])
        self.assertEqual(len(estado['abonos']), 2, 'los abonos siguen en la lista')

    def test_sin_pagos_no_es_abono(self):
        estado = self._factura()._dcasa_estado_abono()
        self.assertFalse(estado['es_abono'])
        self.assertEqual((estado['pagado'], estado['saldo']), (0.0, 200.0))
        self.assertFalse(estado['inicio'] or estado['vence'])

    def test_plazo_en_cero_no_muestra_vencimiento(self):
        self.env['ir.config_parameter'].sudo().set_param(PARAMETRO_DIAS_ABONO, '0')
        factura = self._factura()
        self._pagar(factura, 20.0, fields.Date.today())
        self.assertFalse(factura._dcasa_estado_abono()['vence'])

    @freeze_time('2026-10-14 15:00:00')
    def test_treinta_dias_exactos(self):
        """30 días continuos (no «un mes»): del 14/10 al 13/11; vence ese día, vencido desde el siguiente."""
        factura = self._factura()
        self._pagar(factura, 100.0, date(2026, 10, 14))
        estado = factura._dcasa_estado_abono()
        self.assertEqual((estado['inicio'], estado['vence']), (date(2026, 10, 14), date(2026, 11, 13)))
        self.assertEqual((estado['vence'] - estado['inicio']).days, 30)
        with freeze_time('2026-11-13 15:00:00'):
            self.assertFalse(factura._dcasa_estado_abono()['vencido'], 'el último día todavía no está vencido')
        with freeze_time('2026-11-14 15:00:00'):
            self.assertTrue(factura._dcasa_estado_abono()['vencido'])

    def test_treinta_dias_tambien_al_cambiar_de_mes(self):
        """Meses de 31, de 30 y febrero: siempre 30 días, nunca «el mismo día del mes que viene»."""
        casos = (
            (date(2026, 1, 31), date(2026, 3, 2), True),     # enero de 31 y febrero de 28
            (date(2026, 2, 15), date(2026, 3, 17), True),    # febrero
            (date(2028, 2, 15), date(2028, 3, 16), True),    # febrero de un año bisiesto
            (date(2026, 7, 31), date(2026, 8, 30), True),    # julio de 31
            (date(2026, 4, 30), date(2026, 5, 30), False),   # abril de 30: aquí coincide con «un mes»
            (date(2026, 12, 20), date(2027, 1, 19), True),   # cambia el año
        )
        for inicio, vence, distinto_de_un_mes in casos:
            with self.subTest(inicio=inicio):
                factura = self._factura()
                self._pagar(factura, 100.0, inicio)
                self.assertEqual(factura._dcasa_estado_abono()['vence'], vence)
                self.assertEqual((vence - inicio).days, 30)
                self.assertEqual(vence != inicio + relativedelta(months=1), distinto_de_un_mes)

    def test_el_parametro_de_dias(self):
        icp = self.env['ir.config_parameter'].sudo()
        Move = self.env['account.move']
        self.assertFalse(icp.get_param(PARAMETRO_DIAS_ABONO), 'de fábrica no se escribe: vale 30')
        self.assertEqual(Move._dcasa_dias_abono(), 30)
        for valor, dias in (('45', 45), (' 10 ', 10), ('0', 0), ('-3', 0), ('treinta', 30), ('', 30)):
            with self.subTest(valor=valor):
                icp.set_param(PARAMETRO_DIAS_ABONO, valor)
                self.assertEqual(Move._dcasa_dias_abono(), dias)

    def _migracion(self):
        spec = importlib.util.spec_from_file_location(
            'mig_abono_dias', file_path('dcasa_invoice/migrations/19.0.2.4.0/post-migrate.py'))
        migracion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migracion)
        return migracion

    def test_la_migracion_pasa_los_meses_a_dias(self):
        """Una base con el parámetro viejo («un mes») no se rompe: pasa a días y el viejo se borra."""
        icp = self.env['ir.config_parameter'].sudo()
        migracion = self._migracion()
        casos = (('1', '30'), ('0', '0'), ('2', '60'), ('un mes', '30'))
        for viejo, dias in casos:
            with self.subTest(viejo=viejo):
                icp.set_param(PARAMETRO_DIAS_ABONO, False)
                icp.set_param(PARAMETRO_MESES_VIEJO, viejo)
                migracion.migrate(self.env.cr, '19.0.2.3.0')
                self.assertEqual(icp.get_param(PARAMETRO_DIAS_ABONO), dias)
                self.assertFalse(icp.get_param(PARAMETRO_MESES_VIEJO), 'no quedan dos parámetros')
        # Con el viejo en «1», una factura en abono vence a los 30 días, no al mes.
        icp.set_param(PARAMETRO_DIAS_ABONO, False)
        icp.set_param(PARAMETRO_MESES_VIEJO, '1')
        migracion.migrate(self.env.cr, '19.0.2.3.0')
        factura = self._factura()
        self._pagar(factura, 100.0, date(2026, 1, 31))
        self.assertEqual(factura._dcasa_estado_abono()['vence'], date(2026, 3, 2))

    def test_la_migracion_respeta_los_dias_ya_escritos_y_se_puede_repetir(self):
        icp = self.env['ir.config_parameter'].sudo()
        migracion = self._migracion()
        icp.set_param(PARAMETRO_DIAS_ABONO, '45')
        icp.set_param(PARAMETRO_MESES_VIEJO, '1')
        migracion.migrate(self.env.cr, '19.0.2.3.0')
        self.assertEqual(icp.get_param(PARAMETRO_DIAS_ABONO), '45')
        self.assertFalse(icp.get_param(PARAMETRO_MESES_VIEJO))
        migracion.migrate(self.env.cr, '19.0.2.3.0')   # sin nada que pasar: no hace nada
        self.assertEqual(icp.get_param(PARAMETRO_DIAS_ABONO), '45')
        icp.set_param(PARAMETRO_DIAS_ABONO, False)
        self.assertIsNone(self.env['account.move']._dcasa_migrar_plazo_abono())
        self.assertFalse(icp.get_param(PARAMETRO_DIAS_ABONO), 'sin parámetro viejo, vale lo de fábrica')

    def test_no_toca_la_contabilidad(self):
        factura = self._factura()
        self._pagar(factura, 80.0, fields.Date.today())
        antes = [(linea.account_id.id, linea.debit, linea.credit, linea.amount_residual)
                 for linea in factura.line_ids.sorted('id')]
        factura._dcasa_estado_abono()
        despues = [(linea.account_id.id, linea.debit, linea.credit, linea.amount_residual)
                   for linea in factura.line_ids.sorted('id')]
        self.assertEqual(antes, despues)
