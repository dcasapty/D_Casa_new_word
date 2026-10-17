"""«Enviar» a mano: la factura (asistente de Odoo con la casilla de correo), la cotización (botón de la venta) y
«Enviar por correo» del panel de Conversaciones."""
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.modules.module import get_manifest
from odoo.service.model import call_kw
from odoo.tests import new_test_user, tagged

from .common import PDF, RUTA_PDF, CorreoCase

MODULO = Path(__file__).resolve().parent.parent


@tagged('post_install', '-at_install')
class TestFacturaManual(CorreoCase):

    def asistente(self, factura, usuario=None):
        Asistente = self.env['account.move.send.wizard']
        if usuario:
            Asistente = Asistente.with_user(usuario)
        return Asistente.with_context(active_model='account.move', active_ids=factura.ids).create({})

    def test_sin_clave_todo_es_como_antes(self):
        factura = self.factura()
        asistente = self.asistente(factura)
        self.assertEqual(asistente.template_id, self.env.ref('account.email_template_edi_invoice'))
        self.assertEqual(self.env['account.move.send']._get_mail_layout(),
                         'mail.mail_notification_layout_with_responsible_signature')
        self.assertNotIn('dcasa_correo_apagado', asistente.alerts or {})

    def test_apagado_deja_una_nota_y_no_crea_ningun_correo(self):
        self.con_clave()
        factura = self.factura()
        asistente = self.asistente(factura)
        self.assertIn('dcasa_correo_apagado', asistente.alerts)
        self.assertEqual(asistente.alerts['dcasa_correo_apagado']['level'], 'warning', 'No bloquea imprimir')
        asistente.action_send_and_print()
        self.assertFalse(self.correos_de(factura))
        self.assertTrue(factura.message_ids.filtered(
            lambda m: 'No se envió por correo' in (m.body or '') and m.subtype_id.internal))

    def test_encendido_sale_con_la_plantilla_y_el_layout_de_dcasa(self):
        self.encender()
        factura = self.factura()
        asistente = self.asistente(factura)
        self.assertEqual(asistente.template_id, self.env.ref('dcasa_correo.plantilla_factura'))
        self.assertNotIn('dcasa_correo_apagado', asistente.alerts or {})
        asistente.action_send_and_print()
        (correo,) = self.correos_de(factura)
        self.assertIn("'X-Dcasa-Correo': 'factura'", correo.headers)
        self.assertIn('Escríbenos por WhatsApp', correo.body_html)
        self.assertIn('TU FACTURA', correo.body_html)
        self.assertEqual(correo.subject, f"Tu factura {factura.name} de D'CASA")
        self.assertFalse(factura.access_token, 'Sin access_token: el enlace no da acceso a nadie')

    def test_reenviar_despues_de_un_abono_arma_un_pdf_nuevo_sin_borrar_el_anterior(self):
        self.encender()
        factura = self.factura()
        self.asistente(factura).action_send_and_print()
        viejo = factura.invoice_pdf_report_id
        self.assertTrue(viejo)
        self.pagar(factura, 80.0, contexto={'dcasa_sin_correo_auto': True})
        asistente = self.asistente(factura)
        asistente.action_send_and_print()
        nuevo = factura.invoice_pdf_report_id
        self.assertTrue(nuevo)
        self.assertNotEqual(nuevo, viejo)
        self.assertTrue(viejo.exists(), 'El PDF anterior no se borra: se aparta')
        self.assertFalse(viejo.res_field)
        self.assertIn('(anterior ', viejo.name)
        ultimo = self.correos_de(factura)[-1]
        self.assertEqual(ultimo.attachment_ids.mapped('name'), [nuevo.name], 'Solo el PDF nuevo va en el correo')
        self.assertIn("'X-Dcasa-Correo': 'abono'", ultimo.headers)


@tagged('post_install', '-at_install')
class TestCotizacionManual(CorreoCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cama = cls.env['product.product'].create({'name': 'CAMA CORREO', 'type': 'consu', 'list_price': 300.0})

    def orden(self, partner=None, usuario=None):
        usuario = usuario or self.vendedora
        return self.env['sale.order'].with_user(usuario).create({
            'partner_id': (partner or self.ana).id, 'user_id': usuario.id,
            'order_line': [Command.create({'product_id': self.cama.id, 'product_uom_qty': 1})]})

    def test_sin_clave_el_boton_es_el_de_odoo(self):
        accion = self.orden().action_quotation_send()
        self.assertNotIn('dcasa_correo_sin_token', accion['context'])
        self.assertEqual(accion['context']['default_template_id'], self.env.ref('sale.email_template_edi_sale').id)

    def test_apagado_avisa_y_no_abre_el_asistente(self):
        self.con_clave()
        with self.assertRaisesRegex(UserError, 'Los correos a clientes están apagados'):
            self.orden().action_quotation_send()

    def test_sin_correo_avisa_con_el_texto_exacto(self):
        self.encender()
        orden = self.orden(self.sin_correo)
        with self.assertRaises(UserError) as error:
            orden.action_quotation_send()
        self.assertEqual(error.exception.args[0],
                         'Carla Sin Correo no tiene correo. Escríbelo en su ficha o envíasela por WhatsApp.')

    def test_encendido_el_asistente_sale_con_la_marca_y_sin_token(self):
        self.encender()
        orden = self.orden()
        accion = orden.with_user(self.vendedora).action_quotation_send()
        contexto = accion['context']
        self.assertEqual(contexto['default_email_layout_xmlid'], 'dcasa_correo.layout_correo')
        self.assertTrue(contexto['dcasa_correo_sin_token'])
        self.assertEqual(contexto['default_template_id'], self.env.ref('dcasa_correo.plantilla_cotizacion').id)
        with patch(RUTA_PDF, return_value=PDF):
            asistente = self.env['mail.compose.message'].with_user(self.vendedora).with_context(contexto).create({})
            asistente.action_send_mail()
        (correo,) = self.correos_de(orden)
        self.assertIn("'X-Dcasa-Correo': 'cotizacion'", correo.headers)
        self.assertIn('TU COTIZACIÓN', correo.body_html)
        self.assertIn(f'te enviamos la cotización <strong>{orden.name}</strong>', correo.body_html)
        self.assertEqual(correo.recipient_ids, self.ana)
        self.assertEqual(orden.state, 'sent')
        self.assertFalse(orden.access_token)


@tagged('post_install', '-at_install')
class TestPanelCorreo(CorreoCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cama = cls.env['product.product'].create({'name': 'CAMA PANEL', 'type': 'consu', 'list_price': 300.0})
        cls.interno = new_test_user(cls.env, login='correo_interno', email='interno.correo@example.com',
                                    groups='base.group_user')
        cls.portal = new_test_user(cls.env, login='correo_portal', email='portal.correo@example.com',
                                   groups='base.group_portal')

    def setUp(self):
        super().setUp()
        self.conv = self.conversacion(self.ana)
        self.panel = self.env['dcasa.conversacion'].with_user(self.vendedora)

    def conversacion(self, partner):
        datos = {'canal': 'whatsapp_qr', 'id_externo': '50760000091', 'id_mensaje': f'wamid.correo{partner.id}',
                 'direccion': 'entrante', 'autor': 'cliente', 'texto': 'Hola, quiero la cama',
                 'ts': datetime(2026, 10, 9, 15, 0), 'nombre': None, 'celular': None, 'adjuntos': []}
        conv = self.env['dcasa.conversacion']._registrar_mensaje(datos)[0]
        conv.partner_id = partner
        return conv

    def orden(self, partner=None):
        return self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': (partner or self.ana).id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.cama.id, 'product_uom_qty': 1})]})

    def enviar(self, *args):
        with patch(RUTA_PDF, return_value=PDF):
            return self.panel.enviar_cotizacion_correo(self.conv.id, *args)

    def test_solo_el_equipo_de_ventas_por_rpc(self):
        orden = self.orden()
        for usuario in (self.interno, self.portal):
            for metodo, args in (('correo_de_cotizacion', [self.conv.id]),
                                 ('enviar_cotizacion_correo', [self.conv.id, orden.id])):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    call_kw(self.env(user=usuario)['dcasa.conversacion'], metodo, list(args), {})
        self.assertFalse(self.envios())

    def test_el_estado_del_boton(self):
        self.orden()
        estado = self.panel.correo_de_cotizacion(self.conv.id)
        self.assertEqual(estado['puede'], False)
        self.assertIn('Todavía no hay clave', estado['motivo'])
        self.con_clave()
        self.assertIn('apagados', self.panel.correo_de_cotizacion(self.conv.id)['motivo'])
        self.encender()
        self.assertEqual(self.panel.correo_de_cotizacion(self.conv.id),
                         {'puede': True, 'motivo': '', 'destino': 'ana@example.com'})
        # cotizaciones_abiertas no cambia (es un contrato de dcasa_conversaciones).
        self.assertEqual(set(self.panel.cotizaciones_abiertas(self.conv.id)), {'cotizaciones', 'cliente'})
        sin = self.conversacion(self.sin_correo)
        self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.sin_correo.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.cama.id, 'product_uom_qty': 1})]})
        estado = self.panel.correo_de_cotizacion(sin.id)
        self.assertEqual((estado['puede'], estado['destino']), (False, ''))
        self.assertIn('Carla Sin Correo no tiene correo', estado['motivo'])

    def test_apagado_no_manda_nada(self):
        self.con_clave()
        self.orden()
        with self.assertRaisesRegex(UserError, 'apagados'):
            self.enviar()
        self.assertFalse(self.envios())

    def test_manda_la_cotizacion_borrador_pasa_a_enviada_y_la_oportunidad_avanza(self):
        self.encender()
        self.env['dcasa.juan.ajustes'].obtener().crm_automatico = True
        orden = self.orden()
        resultado = self.enviar(orden.id)
        self.assertEqual(resultado['correo']['destino'], 'ana@example.com')
        self.assertEqual(orden.state, 'sent')
        self.assertEqual(resultado['cotizacion']['estado'], 'sent')
        (envio,) = self.envios(tipo='cotizacion')
        self.assertEqual((envio.order_id, envio.estado, envio.correo), (orden, 'enviado', 'ana@example.com'))
        (adjunto,) = envio.message_id.attachment_ids
        self.assertTrue(adjunto.raw.startswith(b'%PDF'))
        (correo,) = self.correos_de(orden)
        self.assertIn("'X-Dcasa-Correo': 'cotizacion'", correo.headers)
        self.assertTrue(orden.message_ids.filtered(lambda m: 'Enviada por correo por' in (m.body or '')))
        self.assertTrue(orden.opportunity_id, 'Queda ligada a la oportunidad, como al mandarla por el chat')
        self.assertEqual(orden.opportunity_id.stage_id, self.env.ref('crm.stage_lead3'), 'enviada → «Propuesta»')
        self.assertFalse(orden.access_token)

    def test_antidoble_clic(self):
        self.encender()
        orden = self.orden()
        self.enviar(orden.id)
        with self.assertRaisesRegex(UserError, 'hace un momento'):
            self.enviar(orden.id)
        self.assertEqual(len(self.envios(tipo='cotizacion')), 1)

    def test_una_cotizacion_de_otro_cliente_no_se_manda(self):
        self.encender()
        ajena = self.orden(self.beto)
        with self.assertRaises(UserError):
            self.enviar(ajena.id)
        self.assertFalse(self.envios())

    def test_el_boton_del_dialogo(self):
        xml = (MODULO / 'static/src/xml/cotizacion_correo.xml').read_bytes()
        raiz = etree.fromstring(xml)
        (herencia,) = raiz.xpath('//t[@t-inherit="dcasa_conversaciones.Cotizacion"]')
        self.assertEqual(herencia.get('t-inherit-mode'), 'extension')
        (boton,) = herencia.xpath('.//button[@t-on-click="enviarPorCorreo"]')
        self.assertIn('Enviar por correo', ''.join(boton.itertext()))
        self.assertIn('correo.puede', boton.get('t-att-disabled'))
        js = (MODULO / 'static/src/js/cotizacion_correo.js').read_text()
        self.assertIn('enviarPorCorreo()', js)
        self.assertIn('"enviar_cotizacion_correo"', js)
        self.assertIn('"correo_de_cotizacion"', js)
        manifiesto = json.dumps(get_manifest('dcasa_correo')['assets'])
        self.assertIn('cotizacion_correo.js', manifiesto)
