"""El transporte dentro de Odoo: qué sale por Resend y qué no, con la cola de correo de verdad (Resend simulado)."""
import os
from datetime import timedelta
from unittest.mock import patch

import requests

from odoo import fields
from odoo.tests import tagged

from ..models.resend import PREFIJO_NO_ENVIADO, PREFIJO_REINTENTAR
from .common import CLAVE, CorreoCase, respuesta


@tagged('post_install', '-at_install')
class TestTransporte(CorreoCase):

    def correo(self, destino='ana@example.com', modelo='account.move', autor=None, cabecera=None, tipo='comment'):
        """Un mail.mail en la cola, como los que deja Odoo al publicar un mensaje."""
        factura = self.factura()
        registro = factura if modelo == 'account.move' else self.env[modelo].browse()
        mensaje = self.env['mail.message'].sudo().create({
            'model': modelo, 'res_id': registro.id or False, 'message_type': tipo, 'body': '<p>Hola</p>',
            'author_id': (autor or self.env.ref('base.partner_root')).id, 'subject': 'Prueba de transporte'})
        valores = {'mail_message_id': mensaje.id, 'email_to': destino, 'body_html': '<p>Hola</p>',
                   'email_from': 'vendedora.correo@example.com', 'state': 'outgoing'}
        if cabecera:
            valores['headers'] = repr({'X-Dcasa-Correo': cabecera})
        return self.env['mail.mail'].sudo().create(valores)

    def test_sin_clave_no_sale_nada_y_odoo_queda_como_antes(self):
        correo = self.correo(autor=self.vendedora.partner_id)
        (salida,) = correo._prepare_outgoing_list()
        self.assertNotIn('X-Dcasa-Clase', salida['headers'], 'Sin clave no se marca nada')
        base = 'odoo.addons.base.models.ir_mail_server.IrMail_Server._connect__'
        with self.transporte(), patch(base, side_effect=ConnectionRefusedError('sin servidor')) as conectar:
            correo.send()
        self.assertTrue(conectar.called, 'Sin clave se usa el SMTP de Odoo, como hoy')
        self.post.assert_not_called()
        self.assertEqual(correo.state, 'exception')

    def test_interruptor_apagado_no_le_escribe_a_un_cliente(self):
        self.con_clave()
        correo = self.correo(autor=self.vendedora.partner_id)
        with self.transporte():
            correo.send()
        self.post.assert_not_called()
        self.assertEqual(correo.state, 'exception')
        self.assertIn(PREFIJO_NO_ENVIADO, correo.failure_reason)
        self.assertIn('apagados', correo.failure_reason)

    def test_la_prueba_al_correo_del_equipo_sale_aunque_este_apagado(self):
        self.con_clave()
        correo = self.correo(destino=self.admin.email, modelo='res.users', cabecera='prueba')
        with self.transporte():
            correo.send()
        (llamada,) = self.post.call_args_list
        self.assertEqual(llamada.kwargs['json']['to'], [self.admin.email])
        self.assertEqual(correo.state, 'sent')

    def test_la_prueba_a_un_cliente_no_sale(self):
        self.con_clave()
        correo = self.correo(destino='ana@example.com', modelo='res.users', cabecera='prueba')
        with self.transporte():
            correo.send()
        self.post.assert_not_called()
        self.assertIn('equipo', correo.failure_reason)

    def test_encendido_sale_con_el_remitente_y_responder_a_de_ajustes(self):
        self.encender()
        correo = self.correo(autor=self.vendedora.partner_id)
        (salida,) = correo._prepare_outgoing_list()
        self.assertEqual(salida['headers']['X-Dcasa-Clase'], 'documento')
        with self.transporte():
            correo.send()
        (llamada,) = self.post.call_args_list
        datos = llamada.kwargs['json']
        self.assertEqual(datos['from'], '"D\'CASA Panamá" <ventas@dcasapty.com>')
        self.assertEqual(datos['reply_to'], ['info@dcasapty.com'])
        self.assertEqual(datos['to'], ['ana@example.com'])
        self.assertEqual(llamada.kwargs['headers']['Authorization'], f'Bearer {CLAVE}')
        self.assertEqual(correo.state, 'sent')

    def test_encendido_el_correo_automatico_de_odoo_no_sale(self):
        self.encender()
        correo = self.correo(tipo='notification')
        (salida,) = correo._prepare_outgoing_list()
        self.assertEqual(salida['headers']['X-Dcasa-Clase'], 'odoo')
        with self.transporte():
            correo.send()
        self.post.assert_not_called()
        self.assertIn('Odoo sin permiso', correo.failure_reason)

    def test_staging_nunca_le_escribe_a_un_cliente(self):
        self.encender()
        correo = self.correo(cabecera='factura')
        with patch.dict(os.environ, {'DCASA_ENTORNO': 'staging'}), self.transporte():
            correo.send()
        self.post.assert_not_called()
        self.assertIn('Staging', correo.failure_reason)

    def test_un_429_se_reintenta_con_espera_y_tope(self):
        self.encender()
        correo = self.correo(cabecera='factura')
        with self.transporte(respuesta(429, {'message': 'Too many requests'})), self.errores_de_envio():
            correo.send()
        self.assertEqual(correo.state, 'exception')
        self.assertIn(PREFIJO_REINTENTAR, correo.failure_reason)
        self.post.reset_mock()
        Mail = self.env['mail.mail'].sudo()
        with self.transporte():
            self.assertEqual(Mail._dcasa_reintentar(), 0, 'Todavía no pasaron 5 minutos')
        self.post.assert_not_called()

        def envejecer(minutos):
            self.env.cr.execute('UPDATE mail_mail SET write_date = %s WHERE id = %s',
                                [fields.Datetime.now() - timedelta(minutes=minutos), correo.id])
            correo.invalidate_recordset(['write_date'])

        envejecer(6)
        with self.transporte(respuesta(500)), self.errores_de_envio():
            self.assertEqual(Mail._dcasa_reintentar(), 1)
        self.assertEqual((correo.state, correo.dcasa_intentos), ('exception', 1))
        envejecer(10)
        with self.transporte():
            self.assertEqual(Mail._dcasa_reintentar(), 0, 'El segundo intento espera 15 minutos')
        envejecer(16)
        with self.transporte():
            self.assertEqual(Mail._dcasa_reintentar(), 1)
        self.assertEqual((correo.state, correo.dcasa_intentos), ('sent', 2))
        # Con 5 intentos ya no se vuelve a intentar.
        correo.write({'state': 'exception', 'failure_reason': f'{PREFIJO_REINTENTAR} x', 'dcasa_intentos': 5})
        envejecer(1000)
        with self.transporte():
            self.assertEqual(Mail._dcasa_reintentar(), 0)

    def test_un_rechazo_definitivo_no_se_reintenta(self):
        self.encender()
        correo = self.correo(cabecera='factura')
        with self.transporte(respuesta(422, {'message': 'Invalid `to` field'})), self.errores_de_envio():
            correo.send()
        self.assertNotIn(PREFIJO_REINTENTAR, correo.failure_reason)
        self.assertIn('422', correo.failure_reason)
        self.env.cr.execute('UPDATE mail_mail SET write_date = %s WHERE id = %s',
                            [fields.Datetime.now() - timedelta(days=1), correo.id])
        correo.invalidate_recordset(['write_date'])
        with self.transporte():
            self.assertEqual(self.env['mail.mail'].sudo()._dcasa_reintentar(), 0)

    def test_si_el_primero_del_lote_no_responde_el_segundo_sale(self):
        self.encender()
        primero = self.correo(destino='ana@example.com', cabecera='factura')
        segundo = self.correo(destino='beto@example.com', cabecera='factura')
        with self.transporte(requests.Timeout('tardó'), respuesta()), self.errores_de_envio():
            (primero | segundo).send()
        self.assertEqual(len(self.post.call_args_list), 2)
        self.assertEqual(primero.state, 'exception')
        self.assertIn(PREFIJO_REINTENTAR, primero.failure_reason)
        self.assertEqual(segundo.state, 'sent')
