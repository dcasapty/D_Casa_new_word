"""Revisión adversarial de «Mi cuenta» (equipo rojo, 2026-10-17): cada prueba es un intento de ver lo de otra persona,
de quedarse con una sesión que ya no vale o de sacar a alguien del sitio. Todas deben fallar para el atacante."""
import json
from datetime import timedelta
from urllib.parse import urlsplit

from odoo import Command, fields
from odoo.tests import HttpCase, new_test_user, tagged

from .common import CALLE, CELULAR, CLAVE, CORREO, PIN, MiCuentaComun

CEDULA = '8-888-8888'
CALLE_ENTREGA = 'Calle de la Entrega 77'
TELEFONO_FIJO = '+507 255-0000'


@tagged('post_install', '-at_install')
class TestMiCuentaAtaques(MiCuentaComun, HttpCase):

    def setUp(self):
        super().setUp()
        self.preparar()
        self.authenticate(None, None)

    # --- utilidades ------------------------------------------------------------------------------

    def paginas_de(self, pedido=None, factura=None):
        pedido = pedido or self.pedido
        factura = factura or self.suelta
        return ('/mi-cuenta', '/mi-cuenta/compras', f'/mi-cuenta/compras/{pedido.id}',
                f'/mi-cuenta/facturas/{factura.id}', '/mi-cuenta/puntos', '/mi-cuenta/datos')

    @staticmethod
    def cuerpo(html):
        """Solo el contenido de Mi cuenta: sin la cabecera, donde quien tiene sesión ve su propio nombre."""
        return html.split('o_dcasa_mc_cuerpo', 1)[-1].split('<footer', 1)[0]

    def assertNada(self, html, *textos):
        for texto in textos:
            self.assertNotIn(texto, html)

    # --- Dos sesiones de personas distintas -----------------------------------------------------------

    def test_pin_de_una_y_tienda_de_otra_no_mezcla_nada(self):
        """La socia entra con su PIN en un equipo donde ya había una sesión de la tienda de otra persona: se ve SOLO la
        socia, sin PDF ni los datos completos (la sesión de la tienda no es de ella)."""
        usuario = self.usuario_de_la_tienda('mc_tienda_otra')
        usuario.partner_id.write({'phone': TELEFONO_FIJO, 'street': 'Calle de la Tienda 9'})
        suyo = self._pedido(usuario.partner_id, [(self.sofa, 1)])
        suyo.action_confirm()
        suya = suyo._create_invoices()
        suya.action_post()
        self.authenticate(usuario.login, CLAVE)
        self.entrar()
        inicio = self.url_open('/mi-cuenta').text
        self.assertIn('Hola, Ana', inicio)
        self.assertNotIn('Hola, Tienda', inicio)
        for ruta in (f'/mi-cuenta/compras/{suyo.id}', f'/mi-cuenta/facturas/{suya.id}'):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.url_open(ruta).status_code, 404, 'Manda el PIN: lo de la tienda no se ve')
        compras = self.url_open('/mi-cuenta/compras').text
        self.assertIn(self.pedido.name, compras)
        self.assertNotIn(suyo.name, compras)
        detalle = self.url_open(f'/mi-cuenta/compras/{self.pedido.id}').text
        self.assertNotIn('report_type=pdf', detalle, 'Sin PDF: la sesión de la tienda no es de la socia')
        datos = self.cuerpo(self.url_open('/mi-cuenta/datos').text)
        self.assertIn('ANA MICUENTA', datos)
        self.assertNada(datos, CORREO, TELEFONO_FIJO, 'TIENDA MICUENTA', '/my/security', '/my/addresses')

    def test_un_usuario_interno_no_ve_lo_de_los_clientes(self):
        """Una vendedora con sesión en el sistema que abre /mi-cuenta ve su propia ficha, nunca la de un cliente."""
        new_test_user(self.env, login='mc_vendedora', password=CLAVE, name='VENDEDORA MICUENTA',
                      groups='base.group_user,sales_team.group_sale_salesman')
        self.authenticate('mc_vendedora', CLAVE)
        compras = self.url_open('/mi-cuenta/compras').text
        self.assertNada(compras, self.pedido.name, self.ajeno.name, self.suelta.name)
        for ruta in (f'/mi-cuenta/compras/{self.pedido.id}', f'/mi-cuenta/facturas/{self.suelta.id}',
                     f'/mi-cuenta/compras/{self.ajeno.id}'):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.url_open(ruta).status_code, 404)
        # Si una clienta entra con su PIN en el equipo de la tienda, manda el PIN y sin los accesos de la vendedora.
        self.entrar()
        detalle = self.url_open(f'/mi-cuenta/compras/{self.pedido.id}').text
        self.assertNotIn('report_type=pdf', detalle)
        datos = self.cuerpo(self.url_open('/mi-cuenta/datos').text)
        self.assertIn('ANA MICUENTA', datos)
        self.assertNada(datos, 'VENDEDORA', '/my/security')

    # --- Sesiones que dejan de valer ----------------------------------------------------------------------

    def _sesion_ya_no_vale(self):
        for ruta in self.paginas_de():
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertEqual(self.ruta(respuesta), '/mi-cuenta')
                self.assertIn('Entra a tu cuenta', respuesta.text)
                self.assertNada(respuesta.text, self.pedido.name, self.socia.dcasa_socio_codigo or 'DCA-sin-codigo')

    def test_socio_suspendido_pierde_la_sesion(self):
        self.entrar()
        self.assertIn(self.pedido.name, self.url_open('/mi-cuenta/compras').text)
        self.socia.dcasa_socio_estado = 'suspendido'
        self._sesion_ya_no_vale()

    def test_socio_archivado_pierde_la_sesion(self):
        self.entrar()
        self.socia.active = False
        self._sesion_ya_no_vale()

    def test_pin_reiniciado_corta_la_sesion_y_el_temporal_solo_lleva_a_cambiarlo(self):
        self.socia.sudo().dcasa_pin_cambiado_en = fields.Datetime.now() - timedelta(minutes=5)
        self.entrar()
        self.assertIn(self.pedido.name, self.url_open('/mi-cuenta/compras').text)
        # Gerencia le da un PIN temporal: la sesión abierta (p. ej. en un celular perdido) deja de valer.
        self.socia._dcasa_guardar_pin('739164', temporal=True)
        self._sesion_ya_no_vale()
        # Con el temporal, cualquier página de la cuenta lleva primero a elegir uno nuevo.
        self.entrar(pin='739164')
        for ruta in self.paginas_de():
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertEqual(self.ruta(respuesta), '/socios/pin')
                self.assertNotIn(self.pedido.name, respuesta.text)

    def test_ficha_fusionada_corta_la_sesion(self):
        """Gerencia une la ficha de la socia (la que se va) con otra: la sesión con el id viejo deja de valer."""
        self.entrar()
        destino = self.env['res.partner'].create({'name': 'ANA MICUENTA (DUPLICADA)'})
        self.env['base.partner.merge.automatic.wizard']._merge(
            [self.socia.id, destino.id], destino, extra_checks=False)
        self.assertFalse(self.socia.exists())
        for ruta in self.paginas_de():
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertEqual(self.ruta(respuesta), '/mi-cuenta')
                self.assertNotIn(self.pedido.name, respuesta.text)
        # Con su celular y su PIN entra otra vez, ya a la ficha que quedó (la fusión le pasó el programa y sus compras).
        self.entrar()
        self.assertIn(self.pedido.name, self.url_open('/mi-cuenta/compras').text)
        self.assertNotIn(self.ajeno.name, self.url_open('/mi-cuenta/compras').text)

    # --- Contactos hijos y lo que se le enseña a quien entra con PIN ----------------------------------------

    def test_contactos_hijos_propios_si_y_ajenos_no(self):
        entrega = self.env['res.partner'].create({
            'name': 'Ana (casa de la playa)', 'parent_id': self.socia.id, 'type': 'delivery', 'street': CALLE_ENTREGA})
        del_hijo = self._pedido(entrega, [(self.cojin, 1)])
        del_hijo.action_confirm()
        hijo_ajeno = self.env['res.partner'].create({'name': 'Oficina del otro', 'parent_id': self.otro.id})
        ajeno_hijo = self._pedido(hijo_ajeno, [(self.cojin, 1)])
        ajeno_hijo.action_confirm()
        self.entrar()
        self.assertEqual(self.url_open(f'/mi-cuenta/compras/{del_hijo.id}').status_code, 200)
        self.assertEqual(self.url_open(f'/mi-cuenta/compras/{ajeno_hijo.id}').status_code, 404)
        compras = self.url_open('/mi-cuenta/compras').text
        self.assertIn(del_hijo.name, compras)
        self.assertNotIn(ajeno_hijo.name, compras)

    def test_con_pin_nunca_cedula_direcciones_telefonos_ni_pdf(self):
        self.socia.write({'vat': CEDULA, 'phone': TELEFONO_FIJO})
        entrega = self.env['res.partner'].create({
            'name': 'Ana entrega', 'parent_id': self.socia.id, 'type': 'delivery', 'street': CALLE_ENTREGA})
        self.pedido.partner_shipping_id = entrega
        self.entrar()
        for ruta in self.paginas_de():
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertEqual(respuesta.status_code, 200)
                self.assertNada(respuesta.text, CEDULA, CALLE, CALLE_ENTREGA, TELEFONO_FIJO, CORREO,
                                'report_type=pdf', '/my/orders', '/my/invoices', 'access_token')

    # --- Cabeceras, tokens y RPC ------------------------------------------------------------------------

    def test_cada_pagina_con_sesion_es_privada_y_no_se_indexa(self):
        usuario = self.usuario_de_la_tienda('mc_tienda_cab')
        suyo = self._pedido(usuario.partner_id, [(self.sofa, 1)])
        suyo.action_confirm()
        suya = suyo._create_invoices()
        suya.action_post()
        suelta = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': usuario.partner_id.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.cojin.id, 'quantity': 1, 'price_unit': 50.0})]})
        suelta.action_post()
        sesiones = (('pin', self.entrar, self.paginas_de()),
                    ('tienda', lambda: self.authenticate(usuario.login, CLAVE), self.paginas_de(suyo, suelta)))
        tokens_antes = {r: r.access_token for r in (self.pedido, self.factura, self.suelta, suyo, suya, suelta)}
        for nombre, entrar, rutas in sesiones:
            self.authenticate(None, None)
            entrar()
            for ruta in rutas:
                with self.subTest(sesion=nombre, ruta=ruta):
                    respuesta = self.url_open(ruta)
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertEqual(respuesta.headers.get('Cache-Control'), 'no-store')
                    self.assertIn('noindex', respuesta.headers.get('X-Robots-Tag', ''))
                    self.assertNotIn('access_token', respuesta.text)
        for registro, antes in tokens_antes.items():
            registro.invalidate_recordset(['access_token'])
            self.assertEqual(registro.access_token, antes, f'{registro.display_name}: no se crean access_token')

    def test_nada_de_mi_cuenta_se_llama_por_rpc(self):
        usuario = self.usuario_de_la_tienda('mc_tienda_rpc')
        self.authenticate(usuario.login, CLAVE)
        for metodo, args in (('_mc_pedidos', [[]]), ('_mc_compras', [[]]), ('_mc_datos', [[]])):
            with self.subTest(metodo=metodo):
                respuesta = self.url_open('/web/dataset/call_kw', data=json.dumps({
                    'jsonrpc': '2.0', 'method': 'call', 'id': 1,
                    'params': {'model': 'dcasa.mi.cuenta', 'method': metodo, 'args': args, 'kwargs': {}},
                }), headers={'Content-Type': 'application/json'})
                cuerpo = respuesta.json()
                self.assertIn('error', cuerpo)
                self.assertNotIn(self.pedido.name, respuesta.text)

    # --- Redirecciones: nunca fuera del sitio -------------------------------------------------------------

    def test_ninguna_redireccion_sale_del_sitio(self):
        malo = 'https://malo.example.com/robar'
        self.entrar()
        intentos = [
            self.url_open(f'/mi-cuenta?redirect={malo}', allow_redirects=False),
            self.url_open(f'/socios?redirect={malo}', allow_redirects=False),
            self.url_open(f'/socios/cuenta?redirect={malo}', allow_redirects=False),
            self.url_open(f'/mi-cuenta/facturas/{self.factura.id}?redirect={malo}', allow_redirects=False),
            self.url_open(f'/terms?redirect={malo}', allow_redirects=False),
        ]
        datos = {'csrf_token': self.csrf(), 'redirect': malo, 'volver': malo}
        intentos.append(self.url_open('/socios/salir', data=datos, allow_redirects=False))
        self.authenticate(self.usuario_de_la_tienda('mc_tienda_red').login, CLAVE)
        intentos.append(self.url_open(f'/my?redirect={malo}', allow_redirects=False))
        intentos.append(self.url_open('/socios/salir', data=dict(datos, csrf_token=self.csrf()),
                                      allow_redirects=False))
        intentos.append(self.url_open('/socios/entrar', data={
            'csrf_token': self.csrf(), 'celular': CELULAR, 'pin': PIN, 'origen': malo, 'redirect': malo},
            allow_redirects=False))
        for respuesta in intentos:
            with self.subTest(url=respuesta.url):
                destino = respuesta.headers.get('Location', '')
                if destino:
                    partes = urlsplit(destino)
                    self.assertIn(partes.netloc, ('', urlsplit(self.base_url()).netloc), destino)
                    self.assertNotIn('malo.example.com', destino)
                    self.assertFalse(partes.path.startswith('//'), destino)

    def test_el_error_del_pin_no_refleja_html(self):
        respuesta = self.entrar(celular='"><script>alert(1)</script>', pin='000000', origen='mi-cuenta')
        self.assertIn('Entra a tu cuenta', respuesta.text)
        self.assertNotIn('<script>alert(1)</script>', respuesta.text)
        self.assertEqual(respuesta.headers.get('Cache-Control'), 'no-store')
