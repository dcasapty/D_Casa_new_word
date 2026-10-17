"""El transporte de Resend sin base de datos: cómo se traduce un correo de Odoo y cómo se tratan los errores."""
import base64
import email.policy
import logging
import smtplib
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import requests

from odoo.tests import BaseCase, tagged

from ..models import resend
from ..models.resend import PREFIJO_NO_ENVIADO, PREFIJO_REINTENTAR, SesionResend

CLAVE = 're_secreta_456'


def mensaje(para='Ana <ana@example.com>', copia=None, adjunto=True, clase='factura'):
    """Un correo como lo arma Odoo (``_build_email__``): texto y HTML, y el PDF adjunto."""
    msg = EmailMessage(policy=email.policy.SMTP)
    msg['Message-Id'] = '<123.456-account.move-7@dcasa>'
    msg['Subject'] = 'Recibimos tu abono · Factura INV/2026/00007'
    msg['From'] = 'Vendedora <vendedora@dcasapty.com>'
    msg['Reply-To'] = 'vendedora@dcasapty.com'
    msg['To'] = para
    if copia:
        msg['Cc'] = copia
    msg['References'] = '<1@dcasa> <2@dcasa>'
    msg['X-Dcasa-Correo'] = clase
    msg['X-Dcasa-Clase'] = clase
    msg['X-Odoo-Objects'] = 'account.move-7'
    msg['MIME-Version'] = '1.0'
    msg.add_alternative('Hola Ana', subtype='plain', charset='utf-8')
    msg.add_alternative('<p>Hola Ana</p>', subtype='html', charset='utf-8')
    if adjunto:
        msg.add_attachment(b'%PDF-1.4 abono', 'application', 'pdf', filename='Abono INV-2026-00007.pdf')
    return msg


def sesion(a_clientes=True, entorno='produccion', internos=('duena@example.com',)):
    return SesionResend(CLAVE, {'remitente': 'ventas@dcasapty.com', 'nombre': "D'CASA Panamá",
                                'responder_a': 'info@dcasapty.com', 'a_clientes': a_clientes,
                                'entorno': entorno}, internos)


def ok():
    r = MagicMock(status_code=200)
    r.json.return_value = {'id': 'resend-abc'}
    return r


def falla(estado, mensaje_resend='Algo pasó'):
    r = MagicMock(status_code=estado)
    r.json.return_value = {'name': 'error', 'message': mensaje_resend}
    return r


@tagged('post_install', '-at_install')
class TestMensajeAResend(BaseCase):

    def test_from_y_reply_to_siempre_los_de_ajustes(self):
        datos = resend.mensaje_a_resend(mensaje(), ['ana@example.com'], 'ventas@dcasapty.com', "D'CASA Panamá",
                                        'info@dcasapty.com')
        self.assertEqual(datos['from'], '"D\'CASA Panamá" <ventas@dcasapty.com>')
        self.assertEqual(datos['reply_to'], ['info@dcasapty.com'])
        self.assertEqual(datos['subject'], 'Recibimos tu abono · Factura INV/2026/00007')
        self.assertEqual(datos['to'], ['ana@example.com'])
        self.assertNotIn('cc', datos)
        self.assertNotIn('bcc', datos)

    def test_to_cc_y_bcc_solo_con_quien_de_verdad_recibe(self):
        msg = mensaje(para='Ana <ana@example.com>, Otro Cliente <otro@example.com>', copia='Beto <beto@example.com>')
        datos = resend.mensaje_a_resend(msg, ['ana@example.com', 'beto@example.com', 'oculto@example.com'],
                                        'ventas@dcasapty.com', 'D', 'info@dcasapty.com')
        self.assertEqual(datos['to'], ['ana@example.com'], 'otro@ está en To pero no recibe: no se expone')
        self.assertEqual(datos['cc'], ['beto@example.com'])
        self.assertEqual(datos['bcc'], ['oculto@example.com'], 'Odoo ya quitó la cabecera Bcc: sale de la lista')

    def test_sin_destinatario_visible_no_sale(self):
        msg = mensaje(para='Nadie <nadie@example.com>')
        datos = resend.mensaje_a_resend(msg, ['unico@example.com'], 'ventas@dcasapty.com', 'D', '')
        self.assertEqual(datos['to'], ['unico@example.com'])
        with self.assertRaisesRegex(RuntimeError, PREFIJO_NO_ENVIADO):
            resend.mensaje_a_resend(msg, ['a@example.com', 'b@example.com'], 'ventas@dcasapty.com', 'D', '')

    def test_html_texto_y_adjuntos_en_base64_con_su_nombre(self):
        datos = resend.mensaje_a_resend(mensaje(), ['ana@example.com'], 'ventas@dcasapty.com', 'D', '')
        self.assertEqual(datos['html'].strip(), '<p>Hola Ana</p>')
        self.assertEqual(datos['text'].strip(), 'Hola Ana')
        (adjunto,) = datos['attachments']
        self.assertEqual(adjunto['filename'], 'Abono INV-2026-00007.pdf')
        self.assertEqual(base64.b64decode(adjunto['content']), b'%PDF-1.4 abono')
        self.assertNotIn('attachments', resend.mensaje_a_resend(
            mensaje(adjunto=False), ['ana@example.com'], 'ventas@dcasapty.com', 'D', ''))

    def test_las_cabeceras_de_dcasa_no_salen(self):
        datos = resend.mensaje_a_resend(mensaje(), ['ana@example.com'], 'ventas@dcasapty.com', 'D', '')
        self.assertEqual(datos['headers'], {'References': '<1@dcasa> <2@dcasa>'})
        self.assertNotIn('X-Dcasa', repr(datos))
        self.assertNotIn('X-Odoo', repr(datos))

    def test_la_clave_de_idempotencia_es_estable(self):
        uno = resend.idempotencia('<a@b>', ['Ana@Example.com', 'beto@example.com'])
        self.assertEqual(uno, resend.idempotencia('<a@b>', ['beto@example.com', 'ana@example.com']))
        self.assertNotEqual(uno, resend.idempotencia('<otro@b>', ['ana@example.com', 'beto@example.com']))
        self.assertNotEqual(uno, resend.idempotencia('<a@b>', ['ana@example.com']))
        self.assertLessEqual(len(uno), 64)

    def test_que_errores_se_reintentan(self):
        for estado, esperado in ((429, 'temporal'), (500, 'temporal'), (503, 'temporal'), (403, 'definitivo'),
                                 (422, 'definitivo'), (401, 'definitivo'), (400, 'definitivo')):
            with self.subTest(estado=estado):
                self.assertEqual(resend.clasificar_error(estado), esperado)
        self.assertEqual(resend.clasificar_error(excepcion=requests.Timeout()), 'temporal')
        self.assertEqual(resend.clasificar_error(excepcion=requests.ConnectionError()), 'temporal')
        self.assertEqual(resend.clasificar_error(excepcion=ValueError()), 'definitivo')


@tagged('post_install', '-at_install')
class TestSesionResend(BaseCase):

    def test_manda_un_post_con_la_clave_solo_en_la_cabecera(self):
        with patch('requests.post', return_value=ok()) as post:
            sesion().send_message(mensaje(), 'x@y', ['ana@example.com'])
        (llamada,) = post.call_args_list
        self.assertEqual(llamada.args[0], 'https://api.resend.com/emails')
        self.assertEqual(llamada.kwargs['headers']['Authorization'], f'Bearer {CLAVE}')
        self.assertTrue(llamada.kwargs['headers']['Idempotency-Key'].startswith('dcasa-'))
        self.assertEqual(llamada.kwargs['timeout'], (5, 30))
        self.assertNotIn(CLAVE, repr(llamada.kwargs['json']))
        self.assertNotIn(CLAVE, repr(sesion()))

    def test_errores_temporales_y_definitivos(self):
        casos = (
            (falla(429), PREFIJO_REINTENTAR), (falla(500), PREFIJO_REINTENTAR),
            (requests.Timeout('tardó'), PREFIJO_REINTENTAR), (requests.ConnectionError('sin red'), PREFIJO_REINTENTAR),
            (falla(403, 'The dcasapty.com domain is not verified'), 'Resend no aceptó el correo (403)'),
            (falla(422, 'Invalid `to` field'), 'Resend no aceptó el correo (422)'),
        )
        for respuesta_o_error, texto in casos:
            with self.subTest(caso=texto), patch('requests.post', side_effect=[respuesta_o_error]):
                with self.assertRaises(RuntimeError) as error:
                    sesion().send_message(mensaje(), 'x@y', ['ana@example.com'])
                self.assertIn(texto, str(error.exception))
                self.assertNotIsInstance(error.exception, smtplib.SMTPServerDisconnected)
                self.assertIsNone(error.exception.__cause__, 'Sin la excepción de requests encadenada')

    def test_la_clave_nunca_aparece_en_errores_ni_en_logs(self):
        eco = falla(401, f'API key {CLAVE} is invalid; write to ana@example.com')
        with patch('requests.post', return_value=eco), self.assertLogs(resend.__name__, level=logging.DEBUG) as logs:
            logging.getLogger(resend.__name__).debug('inicio')
            with self.assertRaises(RuntimeError) as error:
                sesion().send_message(mensaje(), 'x@y', ['ana@example.com'])
        self.assertNotIn(CLAVE, str(error.exception))
        self.assertNotIn('ana@example.com', str(error.exception), 'Sin direcciones de personas en el error')
        self.assertIn('***', str(error.exception))
        with patch('requests.post', return_value=ok()), self.assertLogs(resend.__name__, level=logging.INFO) as logs:
            sesion().send_message(mensaje(), 'x@y', ['ana@example.com'])
        texto = '\n'.join(logs.output)
        self.assertIn('DCASA_CORREO enviado', texto)
        self.assertIn('resend-abc', texto)
        self.assertNotIn(CLAVE, texto)
        self.assertNotIn('ana@example.com', texto)

    def test_la_politica_frena_sin_llamar_a_resend(self):
        casos = (
            (sesion(a_clientes=False), mensaje(clase='factura'), ['ana@example.com']),
            (sesion(entorno='staging'), mensaje(clase='factura'), ['ana@example.com']),
            (sesion(), mensaje(clase='odoo'), ['ana@example.com']),
            (sesion(a_clientes=False), mensaje(para='Ana <ana@example.com>', clase='prueba'), ['ana@example.com']),
        )
        for numero, (s, msg, destinos) in enumerate(casos):
            with self.subTest(caso=numero), patch('requests.post') as post:
                with self.assertRaisesRegex(RuntimeError, PREFIJO_NO_ENVIADO):
                    s.send_message(msg, 'x@y', destinos)
                post.assert_not_called()

    def test_la_prueba_sale_al_equipo_aunque_este_apagado(self):
        msg = mensaje(para='Dueña <duena@example.com>', clase='prueba')
        with patch('requests.post', return_value=ok()) as post:
            sesion(a_clientes=False).send_message(msg, 'x@y', ['duena@example.com'])
        self.assertEqual(post.call_args.kwargs['json']['to'], ['duena@example.com'])

    def test_sin_clase_cuenta_como_correo_de_odoo(self):
        msg = mensaje()
        del msg['X-Dcasa-Clase']
        with patch('requests.post') as post, self.assertRaisesRegex(RuntimeError, 'Correo automático de Odoo'):
            sesion().send_message(msg, 'x@y', ['ana@example.com'])
        post.assert_not_called()
