"""El gancho del pago: «el botón pagado» encola el correo de la factura, sin duplicados y sin tocar la contabilidad.

Lo más importante: el pago NUNCA falla por el correo (ni si Resend da 500, ni si no hay red, ni si encolar revienta)."""
import os
from unittest.mock import patch

import requests

from odoo import Command, fields
from odoo.tests import tagged

from ..models.resend import PREFIJO_REINTENTAR
from .common import CorreoCase, respuesta


def foto_contable(factura):
    """Todo lo contable de una factura y de sus pagos, para comparar dos facturas iguales."""
    lineas = sorted(factura.line_ids.mapped(lambda ln: (ln.account_id.id, ln.debit, ln.credit, ln.reconciled)))
    pagos = factura._get_reconciled_payments()
    lineas_pago = sorted(pagos.move_id.line_ids.mapped(
        lambda ln: (ln.account_id.id, ln.debit, ln.credit, ln.reconciled)))
    return {'lineas': lineas, 'estado': factura.payment_state, 'saldo': factura.amount_residual,
            'pagos': lineas_pago, 'cuantos_pagos': len(pagos)}


@tagged('post_install', '-at_install')
class TestPago(CorreoCase):

    def test_pago_completo_encola_la_factura_y_la_bienvenida_sin_duplicar(self):
        self.encender()
        factura = self.factura()
        self.pagar(factura)
        self.assertEqual(factura.payment_state, 'paid')
        envios = self.envios(move_id=factura.id)
        self.assertEqual(envios.mapped('tipo'), ['factura'])
        self.assertEqual(envios.huella, f'{factura.id}:0')
        self.assertEqual(envios.estado, 'pendiente')
        (bienvenida,) = self.envios(tipo='bienvenida')
        self.assertEqual(bienvenida.partner_id, self.ana)
        # El mismo saldo otra vez (p. ej. el banco pasa la factura de «en proceso» a «pagada»): nada nuevo.
        Envio = self.env['dcasa.correo.envio'].sudo()
        self.assertFalse(Envio._encolar_pagos({factura.id: 200.0}, factura.line_ids))
        self.assertEqual(len(self.envios()), 2)

    def test_abono_y_despues_el_pago_final(self):
        self.encender()
        factura = self.factura()
        self.pagar(factura, 80.0)
        self.assertEqual(factura.payment_state, 'partial')
        self.pagar(factura, 120.0)
        self.assertEqual(factura.payment_state, 'paid')
        envios = self.envios(move_id=factura.id)
        self.assertEqual(envios.mapped('tipo'), ['abono', 'factura'])
        self.assertEqual(envios.mapped('saldo_centavos'), [12000, 0])
        self.assertEqual(len(self.envios(tipo='bienvenida')), 1, 'La bienvenida, una sola vez')

    def test_la_contabilidad_no_cambia(self):
        """Dos facturas iguales: una pagada con el correo y otra sin él. Los asientos tienen que ser idénticos."""
        self.encender()
        con_correo = self.factura(self.ana)
        sin_correo = self.factura(self.ana)
        self.pagar(con_correo, 80.0)
        self.pagar(sin_correo, 80.0, contexto={'dcasa_sin_correo_auto': True})
        self.assertTrue(self.envios(move_id=con_correo.id))
        self.assertFalse(self.envios(move_id=sin_correo.id))
        self.assertEqual(foto_contable(con_correo), foto_contable(sin_correo))
        self.pagar(con_correo)
        self.pagar(sin_correo, contexto={'dcasa_sin_correo_auto': True})
        self.assertEqual(foto_contable(con_correo), foto_contable(sin_correo))
        self.assertEqual(con_correo.payment_state, 'paid')

    def test_el_pago_no_falla_si_encolar_revienta(self):
        self.encender()
        factura = self.factura()
        ruta = 'odoo.addons.dcasa_correo.models.correo_envio.DcasaCorreoEnvio._encolar_pagos'
        with patch(ruta, side_effect=Exception('se cayó la cola')), \
                self.assertLogs('odoo.addons.dcasa_correo.models.account_move_line', level='ERROR') as logs:
            self.pagar(factura)
        self.assertEqual(factura.payment_state, 'paid')
        self.assertTrue(factura._get_reconciled_payments())
        self.assertTrue(factura.dcasa_compra_ids, 'Los puntos de Socios se dieron igual')
        self.assertFalse(self.envios())
        self.assertIn('DCASA_CORREO', '\n'.join(logs.output))

    def test_dentro_del_pago_no_se_llama_a_resend(self):
        self.encender()
        factura = self.factura()
        with patch('requests.post', side_effect=AssertionError('nada de HTTP dentro del pago')) as post:
            self.pagar(factura)
        post.assert_not_called()
        self.assertEqual(factura.payment_state, 'paid')

    def test_el_pago_queda_aunque_resend_de_500_o_no_haya_red(self):
        self.encender()
        for numero, falla in enumerate((respuesta(500, {'message': 'Internal'}), requests.ConnectionError('sin red'))):
            with self.subTest(falla=numero):
                factura = self.factura()
                self.pagar(factura)
                self.procesar()
                correos = self.correos_de(factura)
                self.assertEqual(len(correos), 1)
                with self.transporte(falla), self.errores_de_envio():
                    correos.send()
                self.assertEqual(correos.state, 'exception')
                self.assertIn(PREFIJO_REINTENTAR, correos.failure_reason)
                self.assertEqual(factura.payment_state, 'paid')
                self.assertEqual(factura.state, 'posted')

    def test_apagado_o_sin_clave_no_se_encola_nada(self):
        self.con_clave()   # clave sí, interruptor apagado
        factura = self.factura()
        self.pagar(factura)
        self.assertFalse(self.envios())
        self.apagar()
        os.environ.pop('RESEND_API_KEY', None)
        self.ICP.set_param('dcasa_correo.enviar_a_clientes', 'True')   # encendido pero sin clave
        otra = self.factura()
        self.pagar(otra)
        self.assertFalse(self.envios())

    def test_sin_factura_al_pagar_no_se_encola(self):
        self.encender()
        self.ICP.set_param('dcasa_correo.al_pagar', False)
        factura = self.factura()
        self.pagar(factura)
        self.assertFalse(self.envios())

    def test_lo_que_no_es_un_pago_de_una_factura_de_cliente_no_manda_correo(self):
        self.encender()
        historica = self.factura(publicar=False)
        historica.dcasa_historica = True
        historica.action_post()
        self.pagar(historica)
        self.assertFalse(self.envios(move_id=historica.id), 'Una factura histórica no manda correo')

        cero = self.factura(precio=0.0)
        self.assertFalse(self.envios(move_id=cero.id), 'Una factura en 0 no manda correo')

        # Una nota de crédito aplicada baja el saldo pero no es un pago.
        factura = self.factura()
        nota = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': self.ana.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 50.0,
                                                 'tax_ids': [Command.clear()]})]})
        nota.action_post()
        (factura.line_ids | nota.line_ids).filtered(
            lambda ln: ln.account_id.account_type == "asset_receivable" and not ln.reconciled).reconcile()
        self.assertEqual(factura.amount_residual, 150.0)
        self.assertFalse(self.envios(move_id=factura.id), 'Una nota de crédito no manda correo')
        self.assertFalse(self.envios(move_id=nota.id), 'Ni la nota de crédito misma')
        # Devolverle el dinero al cliente (pagar una nota de crédito): tampoco.
        devolucion = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': self.ana.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 30.0,
                                                 'tax_ids': [Command.clear()]})]})
        devolucion.action_post()
        self.pagar(devolucion)
        self.assertEqual(devolucion.payment_state, 'paid')
        self.assertFalse(self.envios(move_id=devolucion.id))

    def test_el_cobro_por_codigo_como_brian_tambien_encola(self):
        self.encender()
        factura = self.factura()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'amount': 50.0, 'journal_id': self.diario.id, 'payment_date': fields.Date.today()})._create_payments()
        (envio,) = self.envios(move_id=factura.id)
        self.assertEqual((envio.tipo, envio.saldo_centavos), ('abono', 15000))

    def test_la_cajera_registra_el_pago_y_tambien_encola(self):
        self.encender()
        # El rol Caja: desde el 2026-10-17 solo Caja (y Gerencia o contabilidad) registra cobros.
        cajera = self.env['res.users'].create({
            'name': 'Cajera Correo', 'login': 'cajera_correo', 'email': 'cajera.correo@example.com',
            'group_ids': [Command.set([self.env.ref('base.group_user').id,
                                       self.env.ref('dcasa_base.group_caja').id])]})
        factura = self.factura()
        self.pagar(factura, usuario=cajera)
        self.assertEqual(factura.payment_state, 'paid')
        self.assertEqual(self.envios(move_id=factura.id).tipo, 'factura')
