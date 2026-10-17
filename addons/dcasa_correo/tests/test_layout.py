"""El correo con la marca (reglas de CLAUDE.md): el amarillo solo sobre azul, sistema plano, un solo CTA de WhatsApp,
logo con la dirección pública y el pie que sale de la empresa (nada escrito a mano)."""
import re

from lxml import html

from odoo.tests import tagged

from .common import CorreoCase


def estilo(elemento):
    return re.sub(r'\s+', '', (elemento.get('style') or '') + ';bgcolor:' + (elemento.get('bgcolor') or '')).lower()


@tagged('post_install', '-at_install')
class TestLayout(CorreoCase):

    def cuerpo(self, partner=None):
        """El correo de bienvenida tal como queda en la cola (con el layout ya aplicado)."""
        partner = partner or self.ana
        self.encender()
        correo = self.env['dcasa.correo'].sudo()
        correo._postear(partner, self.env.ref('dcasa_correo.plantilla_bienvenida'), partner, tipo='bienvenida')
        (mail,) = self.correos_de(partner)[-1:]
        return mail.body_html

    def test_el_amarillo_solo_va_dentro_de_una_celda_azul(self):
        arbol = html.fromstring(self.cuerpo())
        amarillos = [e for e in arbol.iter() if isinstance(e.tag, str) and 'fed00f' in estilo(e)]
        self.assertTrue(amarillos, 'El botón amarillo existe')
        for elemento in amarillos:
            ancestros = [a for a in elemento.iterancestors() if 'background-color:#1340b1' in estilo(a)]
            self.assertTrue(ancestros, f'Amarillo fuera del azul: {html.tostring(elemento)[:200]}')

    def test_sistema_plano_sin_scripts_ni_estilos_externos(self):
        cuerpo = self.cuerpo().lower()
        for prohibido in ('gradient', 'box-shadow', '<script', '<style', '<link', 'javascript:'):
            with self.subTest(prohibido=prohibido):
                self.assertNotIn(prohibido, cuerpo)
        self.assertIn('name="color-scheme" content="light"', self.cuerpo())

    def test_un_solo_cta_de_whatsapp_y_sin_enlaces_con_token(self):
        cuerpo = self.cuerpo()
        self.assertEqual(cuerpo.count('Escríbenos por WhatsApp'), 1)
        arbol = html.fromstring(cuerpo)
        (boton,) = [a for a in arbol.iter('a') if a.text_content().strip() == 'Escríbenos por WhatsApp']
        self.assertTrue(boton.get('href').startswith(('https://wa.me/', 'http')), boton.get('href'))
        for enlace in arbol.iter('a'):
            self.assertNotIn('access_token', enlace.get('href') or '')
        self.assertNotIn('o_mail_notification_btn', cuerpo, 'No usa el botón de acceso de Odoo')

    def test_el_logo_es_una_direccion_publica(self):
        base = self.ICP.get_param('web.base.url').rstrip('/')
        arbol = html.fromstring(self.cuerpo())
        (logo,) = arbol.iter('img')
        self.assertEqual(logo.get('src'), f'{base}/dcasa_base/static/img/logo.png')
        self.assertEqual(logo.get('alt'), "D'CASA")

    def test_el_pie_sale_de_la_empresa(self):
        self.company.write({'phone': '+507 6999-0001'})
        cuerpo = self.cuerpo()
        self.assertIn('+507 6999-0001', cuerpo)
        self.assertIn(self.company.name, html.fromstring(cuerpo).text_content())
        self.company.write({'phone': '+507 6999-0002'})
        self.assertIn('+507 6999-0002', self.cuerpo(self.beto))

    def test_el_titular_va_en_la_banda_azul(self):
        arbol = html.fromstring(self.cuerpo())
        (titular,) = arbol.iter('h1')
        self.assertEqual(titular.text_content().strip(), '¡TE DAMOS LA BIENVENIDA!')
        self.assertTrue(any('background-color:#1340b1' in estilo(a) for a in titular.iterancestors()))
        self.assertIn('color:#ffffff', estilo(titular))
