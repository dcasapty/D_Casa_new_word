"""La compra pagada hacia la cola de Meta: cuándo se encola, con qué datos y que nunca rompe un cobro."""
import hashlib
import json
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import CELULAR, CORREO, MetaCase


def sha(texto):
    return hashlib.sha256(texto.encode()).hexdigest()


@tagged('post_install', '-at_install')
class TestCompraPagada(MetaCase):

    def test_apagado_de_fabrica_no_se_encola_nada(self):
        self.aceptar()
        factura = self.factura()
        self.pagar(factura)
        self.assertEqual(factura.payment_state, 'paid')
        self.assertFalse(self.fila(factura))
        self.post.assert_not_called()

    def test_un_fallo_en_la_cola_no_hace_fallar_el_pago(self):
        self.encender()
        self.aceptar()
        factura = self.factura()
        ruta = 'odoo.addons.dcasa_meta_eventos.models.meta_evento.DcasaMetaEvento._dcasa_encolar_compra'
        with patch(ruta, side_effect=Exception('Meta se cayó')), \
                self.assertLogs('odoo.addons.dcasa_meta_eventos.models.account_move', level='ERROR') as logs:
            self.pagar(factura)
        self.assertEqual(factura.payment_state, 'paid')
        self.assertTrue(factura._get_reconciled_payments(), 'El pago quedó registrado')
        self.assertFalse(self.fila(factura))
        self.assertIn('no se pudo encolar', '\n'.join(logs.output))

    def test_dentro_del_cobro_no_hay_http(self):
        self.encender()
        self.aceptar()
        factura = self.factura()
        self.pagar(factura)  # requests.post lanza AssertionError si alguien lo llamara
        self.post.assert_not_called()
        self.assertEqual(self.fila(factura).estado, 'pendiente')

    def test_tienda_con_consentimiento_lleva_correo_y_celular_cifrados(self):
        self.encender()
        self.aceptar()
        factura = self.factura(lineas=[(self.mueble, 2, 300.0), (self.flete, 1, 20.0)])
        self.pagar(factura)
        fila = self.fila(factura)
        self.assertEqual((fila.estado, fila.origen, fila.action_source), ('pendiente', 'tienda', 'physical_store'))
        evento = json.loads(fila.datos)
        self.assertEqual(evento['event_name'], 'Purchase')
        self.assertEqual(evento['event_id'], f'factura-{factura.id}')
        self.assertEqual(evento['action_source'], 'physical_store')
        self.assertIsInstance(evento['event_time'], int)
        self.assertNotIn('event_source_url', evento)
        datos_usuario = evento['user_data']
        self.assertEqual(datos_usuario['em'], sha('cliente.prueba@example.com'))
        self.assertEqual(datos_usuario['ph'], sha('50760001234'))
        self.assertEqual(datos_usuario['external_id'], sha(f'dcasa-{self.cliente.id}'))
        self.assertEqual(datos_usuario['country'], sha('pa'))
        for campo in ('fn', 'ln', 'client_ip_address', 'client_user_agent', 'fbp'):
            self.assertNotIn(campo, datos_usuario)
        compra = evento['custom_data']
        self.assertEqual(compra['content_ids'], [str(self.mueble.id)], 'El flete (servicio) no cuenta')
        self.assertEqual(compra['contents'], [{'id': str(self.mueble.id), 'quantity': 2, 'item_price': 300.0}])
        self.assertEqual(compra['content_type'], 'product')
        self.assertEqual(compra['value'], factura.amount_untaxed)
        self.assertEqual(compra['currency'], factura.currency_id.name)
        self.assertEqual(compra['num_items'], 2)
        self.assertEqual(compra['order_id'], factura.name)

    def test_ningun_dato_en_claro_en_la_cola(self):
        self.encender()
        self.aceptar()
        factura = self.factura()
        self.pagar(factura)
        datos = self.fila(factura).datos
        for claro in (CORREO, CORREO.lower(), CELULAR, '60001234', '50760001234', 'CLIENTE META PRUEBA'):
            self.assertNotIn(claro, datos)

    def test_tienda_sin_consentimiento_queda_omitido_sin_datos(self):
        self.encender()
        factura = self.factura(partner=self.otro)
        self.pagar(factura)
        fila = self.fila(factura)
        self.assertEqual(fila.estado, 'omitido')
        self.assertFalse(fila.datos)
        self.assertIn('consentimiento', fila.motivo)

    def test_con_consentimiento_pero_sin_correo_ni_celular_queda_omitido(self):
        self.encender()
        self.aceptar(self.otro)
        factura = self.factura(partner=self.otro)
        self.otro.sudo().write({'email': False, 'phone': False})  # una ficha vieja a la que le falta todo
        self.pagar(factura)
        fila = self.fila(factura)
        self.assertEqual(fila.estado, 'omitido')
        self.assertFalse(fila.datos)
        self.assertIn('emparejar', fila.motivo)

    def test_el_interruptor_de_cada_origen_manda(self):
        self.encender(tienda=False)
        self.aceptar()
        factura = self.factura()
        self.pagar(factura)
        self.assertFalse(self.fila(factura), '«Ventas de la tienda» apagado')

    def test_pago_parcial_no_cuenta_y_al_quedar_pagada_si(self):
        self.encender()
        self.aceptar()
        factura = self.factura()
        self.pagar(factura, 100.0)
        self.assertEqual(factura.payment_state, 'partial')
        self.assertFalse(self.fila(factura), 'Un abono no es una compra')
        self.pagar(factura)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        fila = self.fila(factura)
        self.assertEqual(fila.estado, 'pendiente')
        self.assertEqual(json.loads(fila.datos)['custom_data']['value'], 300.0)

    def test_pagar_dos_veces_no_duplica(self):
        self.encender()
        self.aceptar()
        factura = self.factura()
        self.pagar(factura)
        factura._invoice_paid_hook()
        factura._invoice_paid_hook()
        self.assertEqual(len(self.fila(factura)), 1)

    def test_historica_nota_de_credito_y_monto_cero_no_se_envian(self):
        self.encender()
        self.aceptar()
        historica = self.factura()
        historica.dcasa_historica = True
        self.pagar(historica)
        self.assertFalse(self.fila(historica))
        nota = self.factura(tipo='out_refund')
        self.pagar(nota)
        self.assertFalse(self.Evento.search([('move_id', '=', nota.id)]))
        gratis = self.factura(lineas=[(self.mueble, 1, 0.0)])
        self.assertIn(gratis.payment_state, ('paid', 'in_payment', 'not_paid'))
        gratis._invoice_paid_hook()
        self.assertFalse(self.fila(gratis))

    def test_solo_anticipo_o_servicios_no_es_una_compra_de_productos(self):
        self.encender()
        self.aceptar()
        factura = self.factura(lineas=[(self.flete, 1, 20.0)])
        self.pagar(factura)
        fila = self.fila(factura)
        self.assertEqual(fila.estado, 'omitido')
        self.assertFalse(fila.datos)

    def test_volver_a_borrador_o_cancelar_cancela_lo_pendiente(self):
        self.encender()
        self.aceptar()
        factura = self.factura()
        self.pagar(factura)
        fila = self.fila(factura)
        factura.line_ids.remove_move_reconcile()
        factura.button_draft()
        self.assertEqual(fila.estado, 'cancelado')
        factura.action_post()
        self.pagar(factura)
        self.assertEqual(fila.estado, 'pendiente', 'Pagada otra vez: vuelve a la cola, sin duplicar')
        self.assertEqual(len(self.fila(factura)), 1)
        factura.line_ids.remove_move_reconcile()
        factura.button_cancel()
        self.assertEqual(fila.estado, 'cancelado')

    def test_lo_ya_enviado_no_se_toca_al_cancelar(self):
        self.encender()
        self.aceptar()
        factura = self.factura()
        self.pagar(factura)
        fila = self.fila(factura)
        fila.estado = 'enviado'
        factura.line_ids.remove_move_reconcile()
        factura.button_draft()
        self.assertEqual(fila.estado, 'enviado', 'Meta no tiene cómo retractar un evento')


@tagged('post_install', '-at_install')
class TestCompraWeb(MetaCase):

    def navegador(self, pedido, fbp='fb.1.1700000000000.1234567890'):
        pedido._dcasa_meta_guardar_navegador(fbp, None, 'Mozilla/5.0 (prueba)', '203.0.113.7',
                                             'https://tienda.example/shop/confirmation')

    def test_web_con_solo_el_navegador_sale_sin_correo_ni_celular(self):
        self.encender()
        pedido = self.pedido_web()
        self.navegador(pedido)
        factura = self.facturar(pedido)
        self.pagar(factura)
        fila = self.fila(factura)
        self.assertEqual((fila.estado, fila.origen, fila.action_source), ('pendiente', 'web', 'website'))
        evento = json.loads(fila.datos)
        datos_usuario = evento['user_data']
        self.assertNotIn('em', datos_usuario)
        self.assertNotIn('ph', datos_usuario)
        self.assertEqual(datos_usuario['fbp'], 'fb.1.1700000000000.1234567890')
        self.assertEqual(datos_usuario['client_user_agent'], 'Mozilla/5.0 (prueba)')
        self.assertEqual(datos_usuario['client_ip_address'], '203.0.113.7')
        self.assertEqual(evento['event_source_url'], 'https://tienda.example/shop/confirmation')
        self.assertEqual(evento['custom_data']['content_ids'], [str(self.mueble.id)])
        # Al encolar se borran los datos del navegador del pedido.
        self.assertFalse(pedido.sudo().dcasa_meta_ua)
        self.assertFalse(pedido.sudo().dcasa_meta_fbp)

    def test_web_con_la_casilla_lleva_tambien_correo_y_celular(self):
        self.encender()
        pedido = self.pedido_web()
        self.navegador(pedido)
        pedido.sudo().dcasa_meta_consentimiento_compra = '2026-10-17 10:00:00'
        factura = self.facturar(pedido)
        self.pagar(factura)
        datos_usuario = json.loads(self.fila(factura).datos)['user_data']
        self.assertEqual(datos_usuario['em'], sha('cliente.prueba@example.com'))
        self.assertEqual(datos_usuario['ph'], sha('50760001234'))
        self.assertIn('fbp', datos_usuario)

    def test_web_sin_ningun_consentimiento_queda_omitido(self):
        self.encender()
        pedido = self.pedido_web(partner=self.otro)
        factura = self.facturar(pedido)
        self.pagar(factura)
        fila = self.fila(factura)
        self.assertEqual((fila.estado, fila.origen), ('omitido', 'web'))
        self.assertFalse(fila.datos)

    def test_web_usa_su_interruptor(self):
        self.encender(web=False)
        self.aceptar()
        pedido = self.pedido_web()
        factura = self.facturar(pedido)
        self.pagar(factura)
        self.assertFalse(self.fila(factura), '«Ventas de la web» apagado')

    def test_pedido_de_tienda_sin_sitio_web_es_venta_de_tienda(self):
        self.encender()
        self.aceptar()
        pedido = self.pedido_web()
        pedido.website_id = False
        factura = self.facturar(pedido)
        self.pagar(factura)
        fila = self.fila(factura)
        self.assertEqual((fila.origen, fila.action_source), ('tienda', 'physical_store'))


@tagged('post_install', '-at_install')
class TestConsentimientoFicha(MetaCase):

    def test_la_vendedora_marca_y_queda_quien_y_cuando_en_el_historial(self):
        self.encender()
        ficha = self.aceptar()
        self.env.flush_all()
        self.env.cr.precommit.run()  # el seguimiento se escribe al confirmar la transacción
        self.cliente.invalidate_recordset()
        self.assertTrue(self.cliente.dcasa_meta_consentimiento_fecha)
        self.assertEqual(self.cliente.dcasa_meta_consentimiento_origen, 'tienda')
        self.assertEqual(self.cliente.dcasa_meta_consentimiento_usuario_id, self.vendedora)
        cambios = self.env['mail.tracking.value'].sudo().search([
            ('mail_message_id.model', '=', 'res.partner'), ('mail_message_id.res_id', '=', self.cliente.id),
            ('field_id.name', '=', 'dcasa_meta_consentimiento_usuario_id')])
        self.assertTrue(cambios, 'El historial de la ficha dice quién lo marcó')
        self.assertEqual(cambios[:1].mail_message_id.author_id, self.vendedora.partner_id)
        self.assertTrue(ficha.dcasa_meta_consentimiento)

    def test_nadie_escribe_el_consentimiento_a_mano(self):
        with self.assertRaises(AccessError):
            self.cliente.with_user(self.vendedora).write({'dcasa_meta_consentimiento_fecha': '2026-01-01 00:00:00'})
        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.vendedora).create({
                'name': 'Otra ficha', 'phone': '6000-9999', 'dcasa_meta_consentimiento_origen': 'web'})

    def test_la_vendedora_no_retira_y_gerencia_si_y_cancela_lo_pendiente(self):
        self.encender()
        self.aceptar()
        factura = self.factura()
        self.pagar(factura)
        fila = self.fila(factura)
        self.assertEqual(fila.estado, 'pendiente')
        with self.assertRaises(AccessError):
            self.cliente.with_user(self.vendedora).action_dcasa_meta_retirar_consentimiento()
        self.cliente.with_user(self.gerencia).action_dcasa_meta_retirar_consentimiento()
        self.cliente.invalidate_recordset()
        self.assertFalse(self.cliente.dcasa_meta_consentimiento_fecha)
        self.assertEqual(fila.estado, 'cancelado')
        self.assertFalse(fila.datos)

    def test_la_casilla_solo_aparece_con_un_interruptor_encendido(self):
        self.assertFalse(self.cliente.dcasa_meta_casilla_visible, 'Apagado: no se le pide a nadie')
        self.encender(web=False, tienda=True)
        self.cliente.invalidate_recordset(['dcasa_meta_casilla_visible'])
        self.assertTrue(self.cliente.dcasa_meta_casilla_visible)

    def test_el_consentimiento_no_se_copia_al_duplicar(self):
        self.encender()
        self.aceptar()
        copia = self.cliente.sudo().copy({'phone': '6000-4321', 'email': 'copia.meta@example.com'})
        self.assertFalse(copia.dcasa_meta_consentimiento_fecha)
