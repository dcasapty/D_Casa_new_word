"""Sitio web › Brian de la tienda (contrato §5): quién lo ve y lo cambia, lo que le llega al Worker en /config, el
gasto en su propio renglón de Costos de IA, la burbuja en lugar de la de WhatsApp, la Guía y la privacidad."""
import json
import re
from pathlib import Path
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from ..models.juan import tienda_de_costos
from .common import TiendaCase


@tagged('post_install', '-at_install')
class TestAjustes(TiendaCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = new_test_user(cls.env, login='zzbt_gerencia', name='ZZBT Gerencia',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        cls.vendedora = new_test_user(cls.env, login='zzbt_vendedora', name='ZZBT Vendedora',
                                      groups='base.group_user,dcasa_base.group_vendedora')
        cls.portal = new_test_user(cls.env, login='zzbt_portal_aj', name='ZZBT Portal', groups='base.group_portal')

    def test_de_fabrica_encendido_con_30_usd_y_eso_le_llega_al_worker(self):
        self.assertEqual(self.env.ref('dcasa_brian_tienda.parametro_activo').value, 'True')
        datos = self.env['dcasa.juan.ajustes'].obtener().como_json()['brian_tienda']
        self.assertEqual(datos, {'activo': True, 'presupuesto_mes_usd': 30, 'tope_sesion_hora': 20,
                                 'tope_red_hora': 60, 'tope_dia': 1000})

    def test_gerencia_y_administradores_cambian_y_llega_al_worker(self):
        for usuario in (self.gerencia, self.env.ref('base.user_admin')):
            with self.subTest(usuario=usuario.login):
                self.env['ir.config_parameter'].sudo().set_param('dcasa_brian_tienda.activo', 'True')
                ajustes = self.env['dcasa.brian.tienda.ajustes'].with_user(usuario).create({})
                self.assertTrue(ajustes.activo)
                ajustes.write({'presupuesto_mes_usd': 25, 'tope_dia': 500, 'activo': False})
                self.assertEqual(ajustes.execute()['tag'], 'reload')
                datos = self.env['dcasa.juan.ajustes'].obtener().como_json()['brian_tienda']
                self.assertEqual((datos['activo'], datos['presupuesto_mes_usd'], datos['tope_dia']), (False, 25, 500))
        ajustes = self.env['dcasa.brian.tienda.ajustes'].with_user(self.gerencia).create({'tope_red_hora': 999999})
        with self.assertRaises(UserError):
            ajustes.execute()

    def test_vendedora_portal_y_visitante_no(self):
        for usuario in (self.vendedora, self.portal, self.env.ref('base.public_user')):
            with self.subTest(usuario=usuario.login):
                with self.assertRaises(AccessError):
                    self.env['dcasa.brian.tienda.ajustes'].with_user(usuario).create({})
                with self.assertRaises(AccessError):
                    self.env['dcasa.brian.tienda.ajustes'].with_user(usuario)._dcasa_exigir()
                with self.assertRaises(AccessError):
                    self.env['dcasa.brian.tienda.calificacion'].with_user(usuario).search([])
                with self.assertRaises(AccessError):
                    self.env['dcasa.brian.tienda.cupo'].with_user(usuario).search([])
        menu = self.env.ref('dcasa_brian_tienda.menu_dcasa_brian_tienda')
        self.assertEqual(set(menu.group_ids.mapped(lambda g: g.get_external_id()[g.id])),
                         {'dcasa_base.group_gerencia', 'base.group_system'})

    def test_las_calificaciones_nadie_las_crea_ni_las_cambia_por_la_interfaz(self):
        fila = self.env['dcasa.brian.tienda.calificacion'].sudo().create({'estrellas': 5})
        Calificacion = self.env['dcasa.brian.tienda.calificacion'].with_user(self.gerencia)
        self.assertEqual(Calificacion.search([]), fila.with_user(self.gerencia), 'Gerencia las ve')
        for hacer in (lambda: Calificacion.create({'estrellas': 1}), lambda: fila.with_user(self.gerencia).write(
                {'estrellas': 1}), lambda: fila.with_user(self.gerencia).unlink()):
            with self.assertRaises(AccessError):
                hacer()
        ajustes = self.env['dcasa.brian.tienda.ajustes'].with_user(self.gerencia).create({})
        self.assertEqual((ajustes.calificaciones_mes, ajustes.promedio_mes), (1, '5,0 de 5'))

    def test_el_gasto_en_su_renglon_y_sin_dato_nunca_cero(self):
        self.assertEqual(tienda_de_costos({}), {'sin_dato': True})
        self.assertEqual(tienda_de_costos({'tienda': {'usd': 'mucho'}}), {'sin_dato': True})
        datos = tienda_de_costos({'tienda': {'usd': 1.234, 'turnos': 45, 'presupuesto_usd': 30, 'por_modelo': [
            {'modelo': 'muse-spark-1.3', 'usd': 1.234, 'turnos': 45, 'estimado': False}, 'basura']}})
        self.assertEqual((datos['usd'], datos['turnos'], datos['presupuesto_usd']), (1.23, 45, 30))
        self.assertEqual(len(datos['por_modelo']), 1)
        # En Costos de IA: un renglón aparte; el gasto de Juan y «Por pagar a Meta» no cambian.
        Panel = self.env['dcasa.juan.panel']
        self.assertEqual(Panel._costos_extra({'tienda': {'usd': 2.5}})['tienda']['usd'], 2.5)
        self.assertEqual(Panel._costos_extra({})['tienda'], {'sin_dato': True})
        Cliente = type(self.env['dcasa.juan.cliente'])
        con_tienda = {'conectado': True, 'error': None, 'cuerpo': {'tienda': {'usd': 4.5, 'turnos': 12}}}
        with patch.object(Cliente, 'configurado', return_value=True), patch.object(Cliente, 'costos',
                                                                                   return_value=con_tienda):
            ajustes = self.env['dcasa.brian.tienda.ajustes'].with_user(self.gerencia).create({})
            self.assertEqual(ajustes.gasto_mes, '$4.50 en 12 respuestas')
        with patch.object(Cliente, 'configurado', return_value=False):
            ajustes = self.env['dcasa.brian.tienda.ajustes'].with_user(self.gerencia).create({})
            self.assertIn('Sin dato', ajustes.gasto_mes)

    def test_la_guia_tiene_la_pantalla(self):
        ruta = Path(__file__).resolve().parents[2] / 'dcasa_guia' / 'data' / 'guia.json'
        texto = json.dumps(json.loads(ruta.read_text(encoding='utf-8')), ensure_ascii=False)
        self.assertIn('dcasa_brian_tienda.menu_dcasa_brian_tienda', texto)


@tagged('post_install', '-at_install')
class TestLaPagina(TiendaCase):

    def test_la_burbuja_reemplaza_la_de_whatsapp(self):
        html = self.url_open('/').text
        self.assertIn('id="o_dcasa_brian"', html)
        self.assertNotIn('o_dcasa_wa_float', html)
        self.assertIn('Escríbenos por WhatsApp', html, 'los botones de WhatsApp de la página se quedan')
        self.assertIn('data-whatsapp="', html)
        self.assertIn('/dcasa_brian_tienda/static/src/img/poses/', html)
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian_tienda.activo', 'False')
        html = self.url_open('/').text
        self.assertNotIn('id="o_dcasa_brian"', html)
        self.assertIn('o_dcasa_wa_float', html, 'apagado, vuelve la de WhatsApp')

    def test_en_el_pago_no_sale_y_en_el_carrito_si(self):
        self.assertIn('id="o_dcasa_brian"', self.url_open('/shop/cart').text)
        self.assertIn('id="o_dcasa_brian"', self.url_open(self.colchon.website_url).text)
        self.assertIn('id="o_dcasa_brian"', self.url_open('/shop').text)
        sitio = self.env['website'].browse(self.website.id)
        for ruta in ('/shop/payment', '/shop/checkout', '/my', '/my/orders', '/mi-cuenta', '/mi-cuenta/compras'):
            self.assertFalse(sitio._dcasa_brian_en_esta_pagina(ruta), ruta)
        for ruta in ('/', '/shop', '/shop/cart', '/socios', '/visitanos'):
            self.assertTrue(sitio._dcasa_brian_en_esta_pagina(ruta), ruta)

    def test_la_pagina_es_la_misma_para_todo_visitante(self):
        """Se guarda en el borde: nada de la sesión (ni el sid, ni el carrito, ni un pase) va en el HTML."""
        antes = self.url_open('/').text
        self.post('pase')
        self.post('carrito/agregar', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 1})
        despues = self.url_open('/').text
        burbuja = lambda html: html[html.index('id="o_dcasa_brian"'):].split('</aside>')[0]  # noqa: E731
        self.assertEqual(burbuja(antes), burbuja(despues))
        self.assertNotIn('dcasa_brian_sid', despues)

    def test_con_el_editor_del_sitio_las_paginas_abren(self):
        """La trampa del lote 1: con el editor, un t-call metido por xpath en una plantilla de Odoo daba error 500."""
        self.authenticate('admin', 'admin')
        for ruta in ('/', '/shop', self.colchon.website_url, '/shop/cart', '/privacidad', '/visitanos'):
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn('id="o_dcasa_brian"', respuesta.text)

    def test_privacidad_dice_lo_del_chat_y_su_fecha(self):
        html = ' '.join(self.url_open('/privacidad').text.split())
        self.assertIn('id="brian-de-la-tienda"', html)
        for frase in ('No guardamos la conversación', 'Usar mi ubicación', 'no se guarda',
                      'solo el número de estrellas y la fecha'):
            self.assertIn(frase, html)
        self.assertIn('13 de noviembre de 2026', html)

    def test_el_js_no_anida_plantillas_de_texto(self):
        """El minificador de Odoo (rjsmin) no entiende `…${`…`}…`: se come los espacios de la de adentro."""
        ruta = Path(__file__).resolve().parents[1] / 'static' / 'src' / 'js' / 'brian_tienda.js'
        codigo = [linea for linea in ruta.read_text(encoding='utf-8').splitlines()
                  if not linea.lstrip().startswith(('*', '/*', '//'))]
        anidadas = [linea.strip() for linea in codigo if re.search(r'\$\{[^}`]*`', linea)]
        self.assertEqual(anidadas, [])

    def test_el_borde_no_guarda_las_rutas_del_chat(self):
        for ruta in ('/dcasa/brian/v1/carrito',):
            respuesta = self.url_open(ruta)
            self.assertEqual(respuesta.headers['Cache-Control'], 'no-store')
            self.assertEqual(respuesta.headers['X-Robots-Tag'], 'noindex')
