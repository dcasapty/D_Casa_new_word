"""El correo con la marca (CLAUDE.md y lo que pidió la dueña el 17/10/2026): limpio, un solo botón azul con letra
blanca, WhatsApp como enlace de texto, sin amarillo (así nunca toca el blanco), sistema plano, el logo con la dirección
pública del sitio y un pie corto que sale de la empresa (nada escrito a mano)."""
import re
from unittest.mock import patch

from lxml import html

from odoo import Command
from odoo.tests import tagged

from .common import CorreoCase


def estilo(elemento):
    return re.sub(r'\s+', '', (elemento.get('style') or '') + ';bgcolor:' + (elemento.get('bgcolor') or '')).lower()


@tagged('post_install', '-at_install')
class TestLayout(CorreoCase):

    def cuerpo(self, registro=None, plantilla='dcasa_correo.plantilla_bienvenida', tipo='bienvenida'):
        """El correo tal como queda en la cola (con el layout ya aplicado)."""
        registro = registro or self.ana
        destino = registro if registro._name == 'res.partner' else registro.partner_id
        self.encender()
        self.env['dcasa.correo'].sudo()._postear(registro, self.env.ref(plantilla), destino, tipo=tipo)
        return self.correos_de(registro)[-1].body_html

    def botones(self, arbol):
        """Las celdas con fondo azul que hacen de botón."""
        return [td for td in arbol.iter('td') if 'bgcolor:#1340b1' in estilo(td)]

    def test_sin_amarillo_y_sistema_plano(self):
        cuerpo = self.cuerpo().lower()
        self.assertNotIn('fed00f', cuerpo, 'Sin amarillo: así nunca toca el blanco')
        for prohibido in ('gradient', 'box-shadow', 'text-shadow', '<script', '<style', '<link', 'javascript:'):
            with self.subTest(prohibido=prohibido):
                self.assertNotIn(prohibido, cuerpo)
        self.assertIn('name="color-scheme" content="light"', self.cuerpo())

    def test_un_solo_boton_azul_con_letra_blanca_y_whatsapp_de_texto(self):
        cuerpo = self.cuerpo()
        arbol = html.fromstring(cuerpo)
        (celda,) = self.botones(arbol)
        (boton,) = celda.iter('a')
        self.assertEqual(boton.text_content().strip(), 'Entrar a Mi cuenta')
        self.assertIn('color:#ffffff', estilo(boton))
        self.assertIn('border-radius', estilo(celda), 'Esquinas suaves')
        self.assertEqual(cuerpo.count('Escríbenos por WhatsApp'), 1)
        (whatsapp,) = [a for a in arbol.iter('a') if 'WhatsApp' in a.text_content()]
        self.assertEqual(whatsapp.text_content().strip(), '¿Dudas? Escríbenos por WhatsApp')
        self.assertTrue(whatsapp.get('href').startswith(('https://wa.me/', 'http')), whatsapp.get('href'))
        self.assertFalse([a for a in whatsapp.iterancestors() if 'bgcolor:#1340b1' in estilo(a)], 'Es texto, no botón')
        for enlace in arbol.iter('a'):
            self.assertNotIn('access_token', enlace.get('href') or '')
        self.assertNotIn('o_mail_notification_btn', cuerpo, 'No usa el botón de acceso de Odoo')

    def test_la_factura_lleva_a_mi_cuenta_y_la_cotizacion_a_whatsapp(self):
        factura = self.factura()
        self.pagar(factura, contexto={'dcasa_sin_correo_auto': True})
        with patch('odoo.addons.dcasa_correo.models.correo.DcasaCorreo._mi_cuenta_instalado', return_value=True):
            arbol = html.fromstring(self.cuerpo(factura, 'dcasa_correo.plantilla_factura', 'factura'))
        (celda,) = self.botones(arbol)
        self.assertEqual(celda.text_content().strip(), 'Ver en Mi cuenta')
        self.assertEqual(next(celda.iter('a')).get('href'), f"{self.env['dcasa.correo']._base()}/mi-cuenta")
        orden = self.env['sale.order'].create({
            'partner_id': self.ana.id,
            'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1})]})
        cuerpo = self.cuerpo(orden, 'dcasa_correo.plantilla_cotizacion', 'cotizacion')
        (celda,) = self.botones(html.fromstring(cuerpo))
        self.assertEqual(celda.text_content().strip(), 'Escríbenos por WhatsApp')
        self.assertNotIn('¿Dudas?', cuerpo, 'Si el botón ya es WhatsApp, no se repite')

    def test_el_logo_usa_la_direccion_publica_del_sitio(self):
        website = self.env['website'].search([('company_id', '=', self.company.id)], limit=1)
        # Una copia sin ninguna dirección pública (como una base en una máquina): web.base.url tal cual.
        self.ICP.set_param('web.base.url', 'http://localhost:8069')
        self.company.website = False
        website.domain = False
        (logo,) = html.fromstring(self.cuerpo()).iter('img')
        self.assertEqual(logo.get('src'), 'http://localhost:8069/dcasa_base/static/img/logo.png')
        # Producción: la dirección pública del sitio, aunque web.base.url fuera una local.
        website.domain = 'https://dcasapty.com'
        (logo,) = html.fromstring(self.cuerpo(self.beto)).iter('img')
        self.assertEqual(logo.get('src'), 'https://dcasapty.com/dcasa_base/static/img/logo.png')
        self.assertEqual(logo.get('alt'), "D'CASA")

    def test_el_pie_corto_sale_de_la_empresa_y_del_sitio(self):
        website = self.env['website'].search([], order='sequence, id', limit=1)
        website.dcasa_whatsapp_number = '+507 6999-0001'
        self.company.write({'street': 'Frente al Parque de Prueba', 'street2': False, 'city': 'La Chorrera'})
        texto = html.fromstring(self.cuerpo()).text_content()
        self.assertIn(self.company.name, texto)
        self.assertIn('Frente al Parque de Prueba, La Chorrera', texto)
        self.assertIn('WhatsApp +507 6999-0001', texto)
        website.dcasa_whatsapp_number = '+507 6999-0002'
        self.assertIn('WhatsApp +507 6999-0002', html.fromstring(self.cuerpo(self.beto)).text_content())

    def test_el_titular_saluda_por_el_nombre_en_azul(self):
        arbol = html.fromstring(self.cuerpo())
        (titular,) = arbol.iter('h1')
        self.assertEqual(titular.text_content().strip(), '¡Te damos la bienvenida, Ana!')
        self.assertIn('color:#1340b1', estilo(titular))
