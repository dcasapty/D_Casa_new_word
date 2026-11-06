"""«¿Te avisamos de lo nuevo? Sí, quiero» al pie del correo de la factura y de la bienvenida: un enlace firmado que
lleva a una página con la marca. Abrir el enlace no anota nada (los filtros de correo los abren solos): el «sí» queda
al tocar el botón de la página. Un error aquí nunca tumba el correo de la factura."""
import os
import re
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

from lxml import html as lxml_html

from odoo import Command, fields
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestEnlaceSiQuiero(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.ana = cls.env['res.partner'].create({'name': 'Ana Zzcm Enlace', 'email': 'ana.enlace.zzcm@example.com',
                                                 'phone': '6000-2001'})
        cls.mueble = cls.env['product.product'].create({'name': 'ZZCM MESA ENLACE', 'type': 'consu',
                                                        'list_price': 50.0, 'taxes_id': [Command.clear()]})

    def setUp(self):
        super().setUp()
        parche = patch.dict(os.environ, {'DCASA_ENTORNO': 'produccion', 'RESEND_API_KEY': 're_correo_prueba'})
        parche.start()
        self.addCleanup(parche.stop)
        post = patch('requests.post', MagicMock(side_effect=AssertionError('requests.post no debe llamarse')))
        post.start()
        self.addCleanup(post.stop)

    def factura(self):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.ana.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 50.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        return factura

    def cuerpo(self, registro, plantilla, tipo):
        destino = registro if registro._name == 'res.partner' else registro.partner_id
        self.env['dcasa.correo'].sudo()._postear(registro, self.env.ref(plantilla), destino, tipo=tipo)
        return self.env['mail.mail'].sudo().search(
            [('model', '=', registro._name), ('res_id', '=', registro.id)], order='id desc', limit=1).body_html

    def enlace(self, cuerpo):
        enlaces = lxml_html.fromstring(cuerpo).xpath("//a[contains(@class, 'o_camila_si_quiero')]")
        return enlaces[0].get('href') if enlaces else None

    def test_va_al_pie_de_la_factura_y_de_la_bienvenida(self):
        cuerpo = self.cuerpo(self.factura(), 'dcasa_correo.plantilla_factura', 'factura')
        self.assertIn('¿Te avisamos de lo nuevo?', lxml_html.fromstring(cuerpo).text_content())
        self.assertRegex(self.enlace(cuerpo), r'/novedades/si\?t=\d+\.f\.\d+\.[0-9a-f]{40}$')
        self.assertNotIn('fed00f', cuerpo.lower(), 'Sin amarillo en el correo de la factura')
        bienvenida = self.cuerpo(self.ana, 'dcasa_correo.plantilla_bienvenida', 'bienvenida')
        self.assertRegex(self.enlace(bienvenida), r'/novedades/si\?t=\d+\.b\.')

    def test_no_va_si_ya_dijo_que_si_o_se_dio_de_baja_ni_en_la_cotizacion(self):
        orden = self.env['sale.order'].create({
            'partner_id': self.ana.id, 'order_line': [Command.create({'product_id': self.mueble.id})]})
        self.assertIsNone(self.enlace(self.cuerpo(orden, 'dcasa_correo.plantilla_cotizacion', 'cotizacion')))
        self.ana.sudo()._dcasa_promos_registrar('tienda')
        self.assertIsNone(self.enlace(self.cuerpo(self.factura(), 'dcasa_correo.plantilla_factura', 'factura')))

    def test_un_error_de_camila_nunca_tumba_el_correo_de_la_factura(self):
        factura = self.factura()
        with patch('odoo.addons.dcasa_camila.models.envio.DcasaCamila._enlace_si', side_effect=RuntimeError('x')), \
                self.assertLogs('odoo.addons.dcasa_camila.models.correo', level='WARNING'):
            cuerpo = self.cuerpo(factura, 'dcasa_correo.plantilla_factura', 'factura')
        self.assertIn(factura.name, cuerpo)
        self.assertIsNone(self.enlace(cuerpo))

    def test_abrir_el_enlace_no_anota_y_tocar_si_quiero_si(self):
        ruta = urlsplit(self.enlace(self.cuerpo(self.factura(), 'dcasa_correo.plantilla_factura', 'factura')))
        pagina = self.url_open(f'{ruta.path}?{ruta.query}')
        self.assertEqual(pagina.status_code, 200)
        self.assertEqual(pagina.headers.get('Cache-Control'), 'no-store')
        self.assertIn('noindex', pagina.headers.get('X-Robots-Tag', ''))
        self.assertIn('¿Te avisamos de lo nuevo?', pagina.text)
        self.ana.invalidate_recordset()
        self.assertEqual(self.ana.dcasa_promos_estado, 'sin', 'Abrir el enlace no es decir que sí')
        token_csrf = re.search(r'name="csrf_token" value="([^"]+)"', pagina.text).group(1)
        token = ruta.query.removeprefix('t=')
        gracias = self.url_open('/novedades/si', data={'csrf_token': token_csrf, 't': token})
        self.assertIn('¡Listo, gracias!', gracias.text)
        self.assertIn('Escríbenos por WhatsApp', gracias.text)
        self.ana.invalidate_recordset()
        self.assertEqual((self.ana.dcasa_promos_estado, self.ana.dcasa_promos_origen), ('si', 'factura'))
        self.assertFalse(self.ana.dcasa_promos_usuario_id, 'Lo dijo el cliente, no alguien del equipo')
        otra_vez = self.url_open(f'{ruta.path}?{ruta.query}')
        self.assertIn('Ya estás en la lista', otra_vez.text)

    def test_sin_csrf_no_anota(self):
        ruta = urlsplit(self.enlace(self.cuerpo(self.factura(), 'dcasa_correo.plantilla_factura', 'factura')))
        respuesta = self.url_open('/novedades/si', data={'t': ruta.query.removeprefix('t=')})
        self.assertNotEqual(respuesta.status_code, 200)
        self.ana.invalidate_recordset()
        self.assertEqual(self.ana.dcasa_promos_estado, 'sin')

    def test_un_enlace_cambiado_vencido_o_de_otro_correo_no_sirve(self):
        enlace = self.enlace(self.cuerpo(self.factura(), 'dcasa_correo.plantilla_factura', 'factura'))
        token = urlsplit(enlace).query.removeprefix('t=')
        Camila = self.env['dcasa.camila']
        self.assertEqual(Camila._enlace_leer(token)[0], 'confirmar')
        partes = token.split('.')
        otra_ficha = self.env['res.partner'].create({'name': 'Otra Zzcm', 'email': 'otra.zzcm@example.com',
                                                     'phone': '6000-2002'})
        for malo in ('', 'basura', '.'.join([str(otra_ficha.id)] + partes[1:]), '.'.join(partes[:3] + ['0' * 40]),
                     '.'.join(partes[:1] + ['b'] + partes[2:])):
            with self.subTest(malo):
                self.assertEqual(Camila._enlace_leer(malo)[0], 'invalido')
                self.assertEqual(Camila._enlace_confirmar(malo), 'invalido')
        self.ana.sudo().email = 'ana.nueva.zzcm@example.com'
        self.assertEqual(Camila._enlace_leer(token)[0], 'invalido', 'El permiso es del correo que recibió el enlace')
        pagina = self.url_open('/novedades/si?t=basura')
        self.assertIn('Este enlace ya no sirve', pagina.text)

    def test_con_baja_no_se_vuelve_a_dar_de_alta(self):
        enlace = self.enlace(self.cuerpo(self.factura(), 'dcasa_correo.plantilla_factura', 'factura'))
        token = urlsplit(enlace).query.removeprefix('t=')
        self.ana.sudo()._dcasa_promos_baja('correo')
        self.assertEqual(self.env['dcasa.camila']._enlace_confirmar(token), 'baja')
        self.assertEqual(self.ana.dcasa_promos_estado, 'baja')
        self.assertIn('Te diste de baja', self.url_open(f'/novedades/si?t={token}').text)
