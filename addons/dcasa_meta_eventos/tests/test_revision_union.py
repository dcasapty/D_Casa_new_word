"""Hallazgos de la revisión adversarial de la unión de los dos paquetes de Meta (catálogo + píxel y ventas).

Cada prueba falla con el código de antes del arreglo:

1. Retirar el consentimiento no alcanzaba lo que quedó «con error» (con el correo y el celular cifrados): «Reintentar
   ahora» lo mandaba igual. Tampoco quitaba la casilla del checkout de un pedido web aún sin pagar (el pago lo
   reportaba con correo y celular) ni borraba los datos de lo ya enviado.
2. Una factura que vuelve a borrador o se cancela dejaba lo «con error» listo para reintentar: se reportaba una venta
   anulada.
3. El píxel se dibujaba en páginas con datos de la persona en la dirección (portal con ``access_token``, búsqueda con
   un correo o un celular) o a la vista (cuenta, inicio de sesión): el píxel de Meta manda la dirección completa.
4. Quien retiraba el consentimiento de las cookies después del checkout seguía con sus datos del navegador en el
   pedido, y salían con la compra.
5. Un fallo al tomar los datos del navegador tumbaba el checkout (la venta).
6. Si la política de privacidad no se podía dibujar sola, con el píxel encendido se caían TODAS las páginas.
7. Fusionar dos fichas mezclaba el registro del consentimiento (la fecha de una, «quién lo registró» de la otra).
8. Al encender el aviso, el pie llevaba a la «Política de cookies» genérica de Odoo (Google Analytics, anuncios de
   Google), que no describe a D'CASA.
9. En el celular, «Eventos enviados a Meta» escondía el estado y el motivo (la lista se salía de lado).
"""
import json
import re
import unittest
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from .common import MetaCase
from .test_render import UA, SitioMetaCase, galletas


@tagged('post_install', '-at_install')
class TestRetirarConsentimientoCompleto(MetaCase):

    def compra_en_cola(self):
        self.encender()
        self.aceptar()
        factura = self.factura()
        self.pagar(factura)
        fila = self.fila(factura)
        self.assertEqual(fila.estado, 'pendiente')
        return factura, fila

    def retirar(self):
        self.cliente.with_user(self.gerencia).action_dcasa_meta_retirar_consentimiento()
        self.cliente.invalidate_recordset()

    def test_lo_que_quedo_con_error_tampoco_sale_y_reintentar_no_lo_revive(self):
        _factura, fila = self.compra_en_cola()
        fila.write({'estado': 'error', 'intentos': 2, 'motivo': 'Meta rechazó el evento'})
        self.retirar()
        self.assertEqual(fila.estado, 'cancelado')
        self.assertFalse(fila.datos, 'Sin los datos cifrados de quien retiró')
        Evento = self.env['dcasa.meta.evento'].with_user(self.gerencia)
        Evento.browse().action_dcasa_meta_reintentar()           # la cabecera: «todo lo que tiene error»
        Evento.browse(fila.id).action_dcasa_meta_reintentar()    # o marcándola
        self.assertEqual(fila.estado, 'cancelado')
        self.responder()
        self.Evento._dcasa_cron_enviar()
        self.post.assert_not_called()

    def test_se_borran_los_datos_de_lo_ya_enviado(self):
        _factura, fila = self.compra_en_cola()
        fila.write({'estado': 'enviado'})
        self.retirar()
        self.assertEqual(fila.estado, 'enviado', 'Lo enviado no se retracta (Meta no tiene cómo)')
        self.assertFalse(fila.datos, 'Pero sus datos cifrados no se guardan más')

    def test_la_casilla_de_un_pedido_web_sin_pagar_tambien_se_quita(self):
        self.encender()
        self.aceptar()
        pedido = self.pedido_web()
        pedido.sudo().write({'dcasa_meta_consentimiento_compra': fields.Datetime.now()})
        pedido._dcasa_meta_guardar_navegador('fb.1.1700000000000.1234567890', None, 'Mozilla/5.0 (prueba)',
                                             '203.0.113.7', 'https://tienda.example/shop/checkout')
        self.retirar()
        pedido.invalidate_recordset()
        self.assertFalse(pedido.sudo().dcasa_meta_consentimiento_compra)
        self.assertFalse(pedido.sudo()._dcasa_meta_navegador(), 'Ni los datos del navegador de ese pedido')
        factura = self.facturar(pedido)
        self.pagar(factura)
        fila = self.fila(factura)
        self.assertEqual(fila.estado, 'omitido', 'Pagado después de retirar: no se reporta')
        self.assertFalse(fila.datos)


@tagged('post_install', '-at_install')
class TestFacturaAnuladaConError(MetaCase):

    def test_borrador_y_cancelar_tambien_cancelan_lo_que_tenia_error(self):
        self.encender()
        self.aceptar()
        for accion in ('button_draft', 'button_cancel'):
            with self.subTest(accion=accion):
                factura = self.factura()
                self.pagar(factura)
                fila = self.fila(factura)
                fila.write({'estado': 'error', 'intentos': 2})
                factura.line_ids.remove_move_reconcile()
                getattr(factura, accion)()
                self.assertEqual(fila.estado, 'cancelado')
                self.env['dcasa.meta.evento'].with_user(self.gerencia).browse().action_dcasa_meta_reintentar()
                self.assertEqual(fila.estado, 'cancelado', '«Reintentar ahora» no reporta una venta anulada')


@tagged('post_install', '-at_install')
class TestFusionDelConsentimiento(MetaCase):

    def fusionar(self, queda, se_va):
        self.env['base.partner.merge.automatic.wizard'].sudo()._merge(
            (queda | se_va).ids, dst_partner=queda, extra_checks=False)
        queda.invalidate_recordset()

    def test_la_que_queda_conserva_su_consentimiento_sin_mezclas(self):
        publico = self.env.ref('base.public_user')
        self.cliente.sudo()._dcasa_meta_registrar_consentimiento('web', publico)  # en la web: sin usuario
        fecha_web = self.cliente.dcasa_meta_consentimiento_fecha
        self.aceptar(self.otro)  # la otra ficha: en la tienda, la vendedora
        self.fusionar(self.cliente, self.otro)
        self.assertEqual(self.cliente.dcasa_meta_consentimiento_fecha, fecha_web)
        self.assertEqual(self.cliente.dcasa_meta_consentimiento_origen, 'web')
        self.assertFalse(self.cliente.dcasa_meta_consentimiento_usuario_id,
                         'Nadie «registró» una aceptación hecha en la web')

    def test_si_la_que_queda_no_acepto_recibe_el_de_la_otra_completo(self):
        self.aceptar(self.cliente)
        fecha = self.cliente.dcasa_meta_consentimiento_fecha
        self.fusionar(self.otro, self.cliente)
        self.assertEqual(self.otro.dcasa_meta_consentimiento_fecha, fecha)
        self.assertEqual(self.otro.dcasa_meta_consentimiento_origen, 'tienda')
        self.assertEqual(self.otro.dcasa_meta_consentimiento_usuario_id, self.vendedora)


@tagged('post_install', '-at_install')
class TestPaginasSinPixel(SitioMetaCase):

    REFERER = '<meta name="referrer" content="origin"'

    def test_paginas_con_datos_de_la_persona_no_llevan_pixel(self):
        self.encender_pixel()
        pedido = self.carrito_del_cliente()
        pedido.sudo().action_confirm()
        pedido.sudo()._portal_ensure_token()
        self.authenticate(None, None)
        rutas = (
            '/web/login',
            '/web/reset_password',
            f'/my/orders/{pedido.id}?access_token={pedido.sudo().access_token}',
            '/shop?search=cliente.web.meta%40example.com',
            '/shop?search=6000-7777',
        )
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                html = self.url_open(ruta).text
                self.assertNotIn('data-dcasa-meta-pixel', html)
                self.assertIn(self.REFERER, html, 'La página siguiente no recibe esta dirección')
        for ruta in ('/', '/shop?search=mesa', '/shop?fbclid=IwAR0123456789abcdef&utm_source=facebook'):
            with self.subTest(ruta=ruta):
                html = self.url_open(ruta).text
                self.assertIn('data-dcasa-meta-pixel', html, 'Las páginas de siempre sí miden')
                self.assertNotIn(self.REFERER, html)

    def test_el_aviso_nombra_a_meta_tambien_donde_no_hay_pixel(self):
        """Lo que la persona acepta en una página sin píxel vale para las demás: el aviso dice lo mismo en todas."""
        self.encender_pixel()
        html = ' '.join(self.url_open('/shop?search=6000-7777').text.split())
        self.assertNotIn('data-dcasa-meta-pixel', html)
        self.assertIn('Meta (Facebook e Instagram)', html)

    def test_la_politica_de_cookies_es_la_de_dcasa(self):
        """Al encender el aviso, Odoo publica /cookie-policy con su texto genérico (Google Analytics, anuncios de
        Google…) y su JS pone «Política de cookies» en el pie: tiene que llevar a la política de D'CASA."""
        self.encender_pixel()
        self.assertTrue(self.env['website.page'].search([('url', '=', '/cookie-policy')]), 'Odoo la crea')
        respuesta = self.url_open('/cookie-policy', allow_redirects=False)
        self.assertEqual(respuesta.status_code, 301)
        self.assertTrue(respuesta.headers['Location'].endswith('/privacidad#cookies'), respuesta.headers['Location'])
        self.assertIn('id="cookies"', self.url_open('/privacidad').text)

    def test_con_el_pixel_apagado_nada_cambia(self):
        self.website.cookies_bar = True
        for ruta in ('/web/login', '/shop?search=6000-7777'):
            with self.subTest(ruta=ruta):
                html = self.url_open(ruta).text
                self.assertNotIn(self.REFERER, html)
                self.assertNotIn('data-dcasa-meta-pixel', html)


@tagged('post_install', '-at_install')
class TestLaTiendaNoSeCaePorMeta(SitioMetaCase):

    def test_retirar_las_cookies_despues_del_checkout_borra_el_navegador(self):
        self.encender_ventas_web()
        pedido = self.carrito_del_cliente()
        self.url_open('/shop/checkout', headers={'User-Agent': UA}, cookies=galletas(True))
        pedido.invalidate_recordset()
        self.assertTrue(pedido.sudo()._dcasa_meta_navegador(), 'Con las cookies aceptadas se tomó')
        # Preferencias de cookies › Solo las necesarias, y vuelve al checkout.
        self.url_open('/shop/checkout', headers={'User-Agent': UA}, cookies=galletas(False))
        pedido.invalidate_recordset()
        self.assertFalse(pedido.sudo()._dcasa_meta_navegador(), 'Lo retiró: no sale con la compra')

    def test_un_fallo_al_tomar_el_navegador_no_rompe_el_checkout(self):
        self.encender_ventas_web()
        self.carrito_del_cliente()
        Pedido = type(self.env['sale.order'])
        with patch.object(Pedido, '_dcasa_meta_guardar_navegador',
                          side_effect=ValueError('falló con 203.0.113.5 y cliente.web.meta@example.com')), \
                self.assertLogs('odoo.addons.dcasa_meta_eventos.controllers.main', level='WARNING') as registro:
            respuesta = self.url_open('/shop/checkout', headers={'User-Agent': UA}, cookies=galletas(True))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('id="shop_checkout"', respuesta.text, 'El checkout se dibuja igual')
        salida = '\n'.join(registro.output)
        self.assertIn('no se pudo', salida)
        self.assertNotIn('203.0.113.5', salida, 'El registro no guarda la IP')
        self.assertNotIn('cliente.web.meta@example.com', salida, 'Ni el correo')

    def test_una_politica_que_no_se_dibuja_sola_no_tumba_el_sitio(self):
        self.encender_pixel()
        self.env['ir.ui.view'].create({
            'name': 'Prueba: la política pide una variable que no existe', 'type': 'qweb',
            'inherit_id': self.env.ref('website_dcasa.privacidad_cuerpo').id,
            'arch': '<xpath expr="." position="inside"><p t-out="variable_que_no_existe.name"/></xpath>'})
        respuesta = self.url_open('/')
        self.assertEqual(respuesta.status_code, 200, 'La portada no se cae')
        self.assertNotIn('data-dcasa-meta-pixel', respuesta.text, 'Sin poder revisar la política: sin píxel')
        self.assertFalse(self.env['website']._dcasa_meta_privacidad_lista(self.website.id))


@tagged('post_install', '-at_install')
class TestDatosDeLaPersonaSoloCifrados(MetaCase):
    """Revisión: en la cola nunca queda el correo ni el celular en claro, tampoco en una compra web con la casilla."""

    def test_compra_web_con_la_casilla(self):
        self.encender()
        pedido = self.pedido_web()
        pedido.sudo().write({'dcasa_meta_consentimiento_compra': fields.Datetime.now()})
        factura = self.facturar(pedido)
        self.pagar(factura)
        datos = self.fila(factura).datos
        evento = json.loads(datos)
        for clave in ('em', 'ph', 'external_id'):
            self.assertRegex(evento['user_data'][clave], r'^[0-9a-f]{64}$')
        self.assertNotIn('example.com', datos.lower())
        self.assertFalse(re.search(r'6000\D?1234', datos), 'El celular nunca en claro')


@tagged('post_install', '-at_install')
class TestGuiaYBrianEncuentranMeta(MetaCase):
    """La Guía (y Brian con ``buscar_en_guia``) lleva a las pantallas de Meta, cada quien solo a lo suyo. Faltaba la
    de Ajustes de Meta, la que el administrador busca para pegar el ID del píxel y mandar la prueba."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'dcasa.guia' not in cls.env:
            raise unittest.SkipTest('dcasa_guia no está instalado')

    def buscar(self, consulta, usuario):
        return [t['id'] for t in self.env['dcasa.guia'].with_user(usuario).buscar(consulta, limite=5)]

    def test_cada_quien_encuentra_su_pantalla_de_meta(self):
        self.assertIn('meta-eventos', self.buscar('ventas reportadas a meta', self.gerencia))
        self.assertIn('meta-pixel', self.buscar('pixel de meta', self.admin))
        self.assertNotIn('meta-pixel', self.buscar('pixel de meta', self.gerencia), 'Ajustes es del administrador')
        for consulta in ('ventas reportadas a meta', 'pixel de meta', 'anuncios en facebook'):
            with self.subTest(consulta=consulta):
                self.assertFalse([i for i in self.buscar(consulta, self.vendedora) if i.startswith('meta-')],
                                 'La Vendedora no tiene pantallas de Meta')
        menus = self.env['ir.ui.menu'].with_user(self.gerencia)._visible_menu_ids()
        self.assertIn(self.env.ref('dcasa_meta_eventos.menu_meta_eventos').id, menus,
                      'Gerencia ve «Eventos enviados a Meta»')

    def test_brian_da_la_ruta_de_eventos_enviados_a_meta(self):
        if 'brian.herramientas' not in self.env:
            self.skipTest('dcasa_brian no está instalado')
        respuesta = self.env['brian.herramientas'].with_user(self.gerencia).ejecutar(
            'buscar_en_guia', {'consulta': '¿dónde veo las ventas que se reportaron a Meta?'})
        self.assertTrue(respuesta.get('ok'), respuesta)
        rutas = {r['tarea']: r['donde'] for r in respuesta['datos']['resultados']}
        self.assertIn('Ver qué ventas se reportaron a Meta', rutas)
        self.assertIn('Eventos enviados a Meta', rutas['Ver qué ventas se reportaron a Meta'])


@tagged('post_install', '-at_install')
class TestEventosEnElCelular(MetaCase):

    def test_en_el_celular_abre_en_tarjetas_con_estado_y_motivo(self):
        accion = self.env.ref('dcasa_meta_eventos.action_dcasa_meta_eventos')
        self.assertEqual(accion.view_mode.split(',')[0], 'list', 'En la computadora sigue la lista')
        self.assertEqual(accion.mobile_view_mode, 'kanban')
        self.assertIn('kanban', accion.view_mode.split(','))
        vista = self.env['dcasa.meta.evento'].with_user(self.gerencia).get_views([(False, 'kanban')])
        arch = vista['views']['kanban']['arch']
        for campo in ('estado', 'motivo', 'move_id', 'valor'):
            self.assertIn(f'name="{campo}"', arch)
        self.assertNotIn('name="datos"', arch, 'El JSON con los datos cifrados no se muestra')
