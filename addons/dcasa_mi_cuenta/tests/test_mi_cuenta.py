"""Mi cuenta de punta a punta, como el navegador: quién entra, qué ve (lo que falta pagar de un abono, las compras,
los puntos, sus datos), qué no ve (lo de otra persona, los carritos, el PDF y la dirección si entró con PIN) y a dónde
llevan ahora los caminos viejos (/socios, /my, la cabecera y el pie)."""
import re
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import quote

from dateutil.relativedelta import relativedelta

from odoo.addons.dcasa_socios.models import reglas as R
from odoo.tests import HttpCase, new_test_user, tagged

from ..models.mi_cuenta import TEXTO_AL_TERMINAR, correo_tapado, dia_mes, fecha_corta, monto
from .common import CALLE, CELULAR, CLAVE, CORREO, PIN, MiCuentaComun


def _cabecera(html):
    return re.search(r'<header id="top".*?</header>', html, re.S).group(0)


@tagged('post_install', '-at_install')
class TestMiCuentaHttp(MiCuentaComun, HttpCase):

    def setUp(self):
        super().setUp()
        self.preparar()
        self.authenticate(None, None)   # visitante, como el QR de la tienda

    # --- Entrar ------------------------------------------------------------------------------------

    def test_sin_sesion_se_ve_la_entrada(self):
        respuesta = self.url_open('/mi-cuenta')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers.get('Cache-Control'), 'no-store')
        html = respuesta.text
        self.assertIn('Entra a tu cuenta', html)
        self.assertIn('action="/socios/entrar"', html)
        self.assertIn('data-captcha="socios_entrar"', html, 'El mismo Turnstile que /socios')
        self.assertIn('name="origen" value="mi-cuenta"', html)
        self.assertIn('href="/web/login?redirect=/mi-cuenta"', html)
        self.assertIn('href="/socios/registro"', html)
        self.assertIn('¿Olvidaste tu PIN? Escríbenos por WhatsApp', html)
        self.assertNotIn('o_dcasa_mc_nav', html, 'Sin sesión no hay barra de secciones')
        # Las secciones sin sesión mandan a entrar (también un id cualquiera: no se distingue nada).
        for ruta in ('/mi-cuenta/compras', '/mi-cuenta/puntos', '/mi-cuenta/datos',
                     f'/mi-cuenta/compras/{self.pedido.id}', f'/mi-cuenta/facturas/{self.suelta.id}',
                     f'/mi-cuenta/compras/{self.ajeno.id}'):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.ruta(self.url_open(ruta)), '/mi-cuenta')

    def test_pin_equivocado_se_queda_en_la_misma_entrada(self):
        malo = self.entrar(pin='111222', origen='mi-cuenta')
        self.assertIn('no coinciden', malo.text)
        self.assertIn('Entra a tu cuenta', malo.text)
        self.assertNotIn(self.socia.dcasa_socio_codigo, malo.text)

    # --- Inicio ------------------------------------------------------------------------------------

    def test_con_pin_el_inicio_dice_cuanto_falta_y_hasta_cuando(self):
        respuesta = self.entrar(origen='mi-cuenta')
        self.assertEqual(self.ruta(respuesta), '/mi-cuenta')
        html = respuesta.text
        estado = self.factura._dcasa_estado_abono()
        self.assertIn('Hola, Ana', html)
        self.assertIn('Te falta', html)
        self.assertIn(monto(estado['saldo']), html)
        pagaste = f"Pagaste <strong>{monto(estado['pagado'])}</strong> de <strong>{monto(estado['total'])}</strong>"
        self.assertIn(pagaste, html)
        self.assertIn(fecha_corta(self.inicio_abono + timedelta(days=30)), html,
                      '30 días continuos desde el primer abono (decisión de la gerencia A3)')
        self.assertIn(self.socia.dcasa_socio_codigo, html, 'Su código de socio, para la caja')
        self.assertIn('Socios D', html)
        self.assertIn('Escríbenos por WhatsApp', html)
        self.assertIn('o_dcasa_mc_activa', html, 'La barra de abajo reemplaza al botón flotante')
        self.assertEqual(html.count('<h1'), 1, 'Un solo h1 por página')
        self.assertNotIn('ANA MICUENTA', re.search(r'<title>(.*?)</title>', html, re.S).group(1),
                         'La pestaña no lleva el nombre de la persona')

    # --- Compras -----------------------------------------------------------------------------------

    def test_compras_agrupadas_sin_carritos_ni_compras_ajenas(self):
        self.entrar()
        html = self.url_open('/mi-cuenta/compras').text
        for nombre in (self.pedido.name, self.apartado.name, self.anulado.name, self.suelta.name):
            self.assertIn(nombre, html)
        self.assertNotIn(f'>{self.carrito.name} ·', html, 'El carrito de la web (borrador) no es una compra')
        self.assertNotIn(f'/mi-cuenta/compras/{self.carrito.id}"', html)
        self.assertNotIn(self.ajeno.name, html)
        self.assertNotIn(self.suelta_ajena.name, html)
        self.assertIn('Por pagar', html)
        self.assertIn('Canceladas', html)
        self.assertIn(f'Apartado hasta el {dia_mes(self.apartado.dcasa_apartado_vence)}', html)
        # El cliente lee el nombre en formato título (F5); por dentro sigue en MAYÚSCULAS.
        self.assertIn('Sofá Milán de Prueba', html)
        self.assertNotIn('SOFÁ MILÁN DE PRUEBA', html)
        self.assertIn('y 1 cosa más', html, 'el mueble principal y el resto')

    def test_el_apartado_de_la_web_dice_que_es_por_pagina_web(self):
        """Decisión de la dueña (2026-10-17): un apartado de la tienda en línea se llama así en todo el sistema."""
        self.apartado.website_id = self.website
        self.entrar()
        html = self.url_open('/mi-cuenta/compras').text
        self.assertIn(f'Apartado por página web hasta el {dia_mes(self.apartado.dcasa_apartado_vence)}', html)
        self.assertEqual(self.apartado.dcasa_apartado_origen, 'Apartado por página web')
        self.apartado.website_id = False
        self.assertEqual(self.apartado.dcasa_apartado_origen, 'Apartado en la tienda')

    def test_detalle_con_abonos_sin_pdf_ni_datos_personales_para_pin(self):
        self.entrar()
        respuesta = self.url_open(f'/mi-cuenta/compras/{self.pedido.id}')
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.text
        # El medio es el nombre del diario, que se traduce: se lee en el idioma de la página.
        estado = self.factura.with_context(lang='es_419')._dcasa_estado_abono()
        abono = estado['abonos'][0]
        self.assertIn(f'Compra {self.pedido.name}', html)
        self.assertIn(monto(estado['saldo']), html)
        self.assertIn(fecha_corta(self.inicio_abono), html, 'la fecha de cada abono')
        self.assertIn(monto(abono['monto']), html)
        if abono['medio']:
            self.assertIn(abono['medio'], html, 'con qué se pagó')
        self.assertIn('Tus abonos', html)
        self.assertIn(f'Tienes hasta el <strong>{fecha_corta(estado["vence"])}</strong>', html)
        self.assertIn('Pagando: te falta', html, 'la línea de tiempo')
        self.assertIn('ITBMS', html)
        # Con PIN: ni PDF ni datos personales; la factura se pide por WhatsApp con el número de la compra.
        self.assertNotIn('report_type=pdf', html)
        self.assertNotIn('/my/orders', html)
        self.assertNotIn(CALLE, html)
        self.assertNotIn(CORREO, html)
        self.assertIn('¿Necesitas tu factura? Escríbenos por WhatsApp', html)
        self.assertIn(quote(f"necesito la factura de mi compra {self.pedido.name}"), html)

    def test_apartado_cancelado_y_factura_suelta(self):
        self.entrar()
        apartado = self.url_open(f'/mi-cuenta/compras/{self.apartado.id}').text
        self.assertIn(f'Apartado hasta el {dia_mes(self.apartado.dcasa_apartado_vence)}: pasa a pagarlo antes de esa '
                      'fecha.', apartado)
        anulado = self.url_open(f'/mi-cuenta/compras/{self.anulado.id}').text
        self.assertIn(f'Se anuló porque venció el apartado el {dia_mes(self.anulado.dcasa_apartado_vence)}.', anulado)
        suelta = self.url_open(f'/mi-cuenta/facturas/{self.suelta.id}')
        self.assertEqual(suelta.status_code, 200)
        self.assertIn(f'Factura {self.suelta.name}', suelta.text)
        self.assertIn(monto(self.suelta.amount_total), suelta.text)
        # La factura de un pedido se ve dentro del pedido.
        del_pedido = self.url_open(f'/mi-cuenta/facturas/{self.factura.id}')
        self.assertEqual(self.ruta(del_pedido), f'/mi-cuenta/compras/{self.pedido.id}')

    def test_lo_de_otra_persona_responde_404_como_lo_que_no_existe(self):
        self.entrar()
        for ruta in (f'/mi-cuenta/compras/{self.ajeno.id}', f'/mi-cuenta/compras/{self.carrito.id}',
                     '/mi-cuenta/compras/2147483000', f'/mi-cuenta/facturas/{self.suelta_ajena.id}',
                     f'/mi-cuenta/facturas/{self.factura_ajena.id}', '/mi-cuenta/facturas/2147483000'):
            with self.subTest(ruta=ruta):
                respuesta = self.url_open(ruta)
                self.assertEqual(respuesta.status_code, 404)
                self.assertNotIn(self.otro.name, respuesta.text)

    def test_confirmado_sin_factura_no_inventa_saldo(self):
        sin_factura = self._pedido(self.socia, [(self.cojin, 1)])
        sin_factura.action_confirm()
        self.entrar()
        html = self.url_open(f'/mi-cuenta/compras/{sin_factura.id}').text
        self.assertIn('Tu factura y tus pagos aparecen aquí cuando se emita.', html)
        self.assertIn(monto(sin_factura.amount_total), html)
        self.assertNotIn('Te falta', html)

    def test_entrega_hecha_dice_cuando_y_nunca_la_fecha_prevista(self):
        salidas = self.pedido.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        self.assertTrue(salidas)
        prevista = fecha_corta(salidas[0].scheduled_date + relativedelta(days=9))
        salidas.write({'scheduled_date': salidas[0].scheduled_date + relativedelta(days=9)})
        self.entrar()
        html = self.url_open(f'/mi-cuenta/compras/{self.pedido.id}').text
        self.assertNotIn(prevista, html, 'La fecha prevista de Odoo no es una promesa')
        for salida in salidas:
            for movimiento in salida.move_ids:
                movimiento.quantity = movimiento.product_uom_qty
                movimiento.picked = True
            salida.button_validate()
        self.assertTrue(all(s.state == 'done' for s in salidas))
        html = self.url_open(f'/mi-cuenta/compras/{self.pedido.id}').text
        self.assertIn(f'Entregado el {fecha_corta(max(salidas.mapped("date_done")))}', html)

    def test_con_saldo_no_se_anuncia_lista_hasta_pagar_completo(self):
        """El mueble se entrega pagado completo (decisión de la dueña, 2026-10-17): aunque ya esté apartado en la
        bodega, con saldo la compra no dice «Listo» ni marca el paso «Lista»."""
        salidas = self.pedido.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        self.assertTrue(salidas.filtered(lambda p: p.state == 'assigned'), 'la mercancía ya está apartada en bodega')
        self.entrar()
        html = self.url_open(f'/mi-cuenta/compras/{self.pedido.id}').text
        self.assertIn(TEXTO_AL_TERMINAR, html)
        self.assertNotIn('Listo: te escribimos', html)
        resumen = self.env['dcasa.mi.cuenta']._mc_resumen_pedido(self.pedido, self.website)
        self.assertEqual([paso['estado'] for paso in resumen['pasos']], ['hecho', 'actual', 'pendiente', 'pendiente'])

        self._pagar(self.factura, self.factura.amount_residual, self.inicio_abono)
        html = self.url_open(f'/mi-cuenta/compras/{self.pedido.id}').text
        self.assertIn('Listo: te escribimos para coordinar la entrega o el retiro.', html)
        self.assertNotIn(TEXTO_AL_TERMINAR, html)

    # --- Usuario de la tienda ----------------------------------------------------------------------

    def test_usuario_de_la_tienda_ve_sus_compras_con_el_pdf(self):
        usuario = self.usuario_de_la_tienda()
        pedido = self._pedido(usuario.partner_id, [(self.sofa, 1)])
        pedido.action_confirm()
        factura = pedido._create_invoices()
        factura.action_post()
        self.authenticate(usuario.login, CLAVE)
        inicio = self.url_open('/my', allow_redirects=False)
        self.assertIn(inicio.status_code, (301, 302, 303))
        self.assertTrue(inicio.headers['Location'].endswith('/mi-cuenta'), '/my del cliente va a Mi cuenta')
        self.assertTrue(self.url_open('/my/home', allow_redirects=False).headers['Location'].endswith('/mi-cuenta'))
        self.assertIn('Hola, Tienda', self.url_open('/mi-cuenta').text)
        html = self.url_open(f'/mi-cuenta/compras/{pedido.id}').text
        self.assertIn(f'/my/orders/{pedido.id}?report_type=pdf&amp;download=true', html)
        self.assertIn(f'/my/invoices/{factura.id}?report_type=pdf&amp;download=true', html)
        self.assertNotIn('access_token', html, 'Nunca se crean enlaces con token')
        # Lo de la socia (otra ficha) no es suyo.
        self.assertEqual(self.url_open(f'/mi-cuenta/compras/{self.pedido.id}').status_code, 404)
        # El portal de Odoo que sigue existiendo: sin «Con la tecnología de Odoo».
        portal = self.url_open(f'/my/orders/{pedido.id}').text
        self.assertNotIn('utm_medium=portal', portal)
        # Sus datos completos (es su cuenta de la tienda) y los accesos de la tienda.
        datos = self.url_open('/mi-cuenta/datos').text
        self.assertIn('/my/security', datos)
        self.assertIn('/my/addresses', datos)

    def test_el_equipo_sigue_yendo_a_su_my(self):
        new_test_user(self.env, login='mc_equipo', password=CLAVE, groups='base.group_user', name='Equipo MiCuenta')
        self.authenticate('mc_equipo', CLAVE)
        respuesta = self.url_open('/my', allow_redirects=False)
        self.assertNotIn('/mi-cuenta', respuesta.headers.get('Location', ''))

    # --- Puntos y datos ----------------------------------------------------------------------------

    def test_puntos_ordenados_para_el_mostrador(self):
        self.env['dcasa.movimiento']._asentar(self.socia, 'ajuste', 1500, 'test', motivo='Saldo de prueba')
        canje = self.env['dcasa.canje']._pedir(self.socia, self.env.ref('dcasa_socios.premio_desc_5'))
        self.entrar()
        html = self.url_open('/mi-cuenta/puntos').text
        saldo = self.socia.dcasa_saldo
        self.assertIn(R.como_puntos(saldo), html)
        self.assertIn(canje.codigo, html)
        self.assertLess(html.index(canje.codigo), html.index('id="mc_saldo"'), 'Los premios por recoger van arriba')
        self.assertIn(self.socia.dcasa_socio_codigo, html)
        self.assertIn(f'/r/{self.socia.dcasa_socio_codigo}', html, 'Su enlace para invitar')
        self.assertIn('data-dcasa-copiar', html)
        self.assertIn('<details', html, 'El QR, plegado')
        reglas = R.cargar_reglas()
        self.assertIn(f'equivalen a <strong>{R.como_dolares(R.centavos_de_puntos(saldo, reglas))}</strong>', html)
        # «Equivalen a» sale de canje.puntosPorDolar, no de suponer 100 puntos = $1.
        reglas['canje']['puntosPorDolar'] = 250
        with patch('odoo.addons.dcasa_socios.models.reglas.cargar_reglas', return_value=reglas):
            otra = self.url_open('/mi-cuenta/puntos').text
        self.assertIn(f'equivalen a <strong>{R.como_dolares(saldo * 100 // 250)}</strong>', otra)

    def test_mis_datos_sin_correo_entero_ni_direccion_para_pin(self):
        self.socia.dcasa_cumple = '02-14'
        self.entrar()
        html = self.url_open('/mi-cuenta/datos').text
        self.assertIn(CELULAR, html)
        self.assertIn(correo_tapado(CORREO), html)
        self.assertNotIn(CORREO, html)
        self.assertNotIn(CALLE, html)
        self.assertIn('14 de febrero', html)
        self.assertIn(self.socia.dcasa_socio_codigo, html)
        self.assertIn('href="/socios/pin"', html)
        self.assertIn('action="/socios/salir"', html)
        self.assertIn('Para cambiar tus datos escríbenos por WhatsApp', html)
        self.assertNotIn('/my/security', html, 'Con PIN no hay contraseña de la tienda')

    def test_pin_temporal_primero_cambia_el_pin(self):
        self.socia._dcasa_guardar_pin(PIN, temporal=True)
        self.entrar()
        self.assertEqual(self.ruta(self.url_open('/mi-cuenta')), '/socios/pin')
        self.assertEqual(self.ruta(self.url_open('/mi-cuenta/compras')), '/socios/pin')

    # --- Los caminos viejos llevan a Mi cuenta ------------------------------------------------------

    def test_redirecciones_de_socios(self):
        self.entrar()
        self.assertEqual(self.ruta(self.url_open('/socios')), '/mi-cuenta/puntos')
        self.assertEqual(self.ruta(self.url_open('/socios/cuenta')), '/mi-cuenta/puntos')
        guardado = self.post('/socios/pin', actual=PIN, nuevo='739164', nuevo2='739164')
        self.assertEqual(self.ruta(guardado), '/mi-cuenta/datos')
        self.assertIn('Tu PIN nuevo quedó guardado', guardado.text)
        salir = self.post('/socios/salir')
        self.assertEqual(self.ruta(salir), '/mi-cuenta')
        self.assertIn('Entra a tu cuenta', salir.text)
        self.assertNotIn(self.socia.dcasa_socio_codigo, salir.text)
        nuevo = self.post('/socios/registro', nombre='Luis', apellido='Nuevo', celular='6100-3003', pin='482915',
                          pin2='482915', acepta='on')
        self.assertEqual(self.ruta(nuevo), '/mi-cuenta')
        self.assertIn('Ya eres socio', nuevo.text)

    def test_iniciar_sesion_del_sitio_lleva_a_mi_cuenta_y_nunca_al_panel(self):
        """«Iniciar sesión» (cabecera, pie, checkout, carrito, crear cuenta) lleva a Mi cuenta; el equipo entra por
        /master (docs/PUERTA_MASTER.md). Ninguna página pública enlaza al login del panel ni a /odoo."""
        for ruta in ('/', '/shop', '/socios', '/web/signup', '/web/signup?redirect=/shop/checkout', '/mi-cuenta'):
            with self.subTest(ruta=ruta):
                html = self.url_open(ruta).text
                self.assertNotRegex(html, r'href="/odoo', 'Ninguna página pública enlaza al panel')
                enlaces = re.findall(r'href="(/web/login[^"]*)"', html)
                permitidos = ('/web/login?redirect=/mi-cuenta', '/web/login?redirect=/shop/')
                self.assertTrue(all(e.startswith(permitidos) for e in enlaces), enlaces)
        registro = self.url_open('/web/signup?redirect=/shop/checkout').text
        self.assertIn('href="/mi-cuenta?redirect=%2Fshop%2Fcheckout"', registro)
        self.assertIn('¿Ya tienes cuenta?', registro)
        # Desde la tienda, «Entra con tu correo» devuelve a la tienda; cualquier otro destino, a Mi cuenta.
        for pedido, destino in (('/shop/checkout', '/shop/checkout'), ('/shop/cart', '/shop/cart'),
                                ('/odoo', '/mi-cuenta'), ('https://malo.example/x', '/mi-cuenta'),
                                ('//malo.example', '/mi-cuenta'), ('/web/login', '/mi-cuenta')):
            with self.subTest(redirect=pedido):
                html = self.url_open(f'/mi-cuenta?redirect={quote(pedido, safe="")}').text
                self.assertIn(f'href="/web/login?redirect={destino}"', html)
        # El checkout y el carrito (plantillas: piden un carrito con productos para dibujarse).
        from lxml import etree
        checkout = etree.tostring(self.env.ref('website_sale.address')._get_combined_arch(), encoding='unicode')
        self.assertIn('/mi-cuenta?redirect=/shop/checkout', checkout)
        self.assertIn('Entra a tu cuenta', checkout)
        self.assertNotIn('/web/login', checkout)
        carrito = etree.tostring(self.env.ref('dcasa_socios.carrito_puntos')._get_combined_arch(), encoding='unicode')
        self.assertEqual(carrito.count('/mi-cuenta?redirect=/shop/cart'), 2)
        self.assertNotIn('/web/login', carrito)

    def test_cabecera_y_pie_enlazan_mi_cuenta(self):
        html = self.url_open('/shop').text
        cabecera = _cabecera(html)
        self.assertRegex(cabecera, r'<a href="/mi-cuenta"[^>]*>Mi cuenta</a>')
        self.assertNotIn('href="/web/login"', cabecera)
        pie = re.search(r'<footer.*?</footer>', html, re.S).group(0)
        self.assertIn('href="/mi-cuenta"', pie)
        self.assertNotIn('href="/my"', pie)
        # /socios conserva su portada pública (el CI busca «Tus puntos»).
        self.assertIn('Tus puntos', self.url_open('/socios').text)
