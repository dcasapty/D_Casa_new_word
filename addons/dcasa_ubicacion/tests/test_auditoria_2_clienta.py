"""Auditoría 2 de lo que vive la clienta en el navegador (2026-11-25): cada prueba fija un hallazgo arreglado, por su
número.

* Por HTTP: el servidor exige el «📍 Es aquí» del aviso de cruce (1), la tarjeta «¿Le entregamos ahí?» de
  /shop/checkout con el punto del chat (4), WhatsApp sin ``wa.me`` (5), la invitada que vuelve atrás (8), «Marcar mi
  casa» antes de firmar o pagar y «Cambiar» de 48 px (9, 11), Andrés con un GPS impreciso guarda la casa (17), el
  motorizado con un punto aproximado llama primero y de usted (18, 19) y el tope de visitas con su plantilla (3, 21).
* En Chrome (el teléfono emulado, con un Google Maps falso cuando hace falta): «Confirmar» no se salta el cruce (1), un
  arrastre sin querer no cambia la casa (2), sin señal y sin permiso (3, 7), «Escribir» (14) y la página /u (3, 6, 7,
  12, 15, 16).
"""
import json
import os
import re
from unittest.mock import patch
from urllib.parse import unquote

from odoo.addons.dcasa_base import whatsapp
from odoo.addons.dcasa_brian_tienda.tests.common import TiendaCase
from odoo.addons.dcasa_envios.controllers.choferes import reiniciar_limite
from odoo.addons.website_dcasa.tests.chrome_movil import ChromeMovilCase
from odoo.tests import HttpCase, new_test_user, tagged

from ..controllers import checkout
from ..motor import casa, geo
from .common import CERCA
from .test_auditoria_clienta import LISTO, WHATSAPP_TIENDA, _preparar_tabla, _SinClaves

NUEVA_FICCION = (8.9314, -79.8314)       # «Barriada Nueva Ficción» del fixture (Arraiján)
CLAVE_FALSA = 'AIzaSyDePruebaFalsa0123456789'


@tagged('post_install', '-at_install')
class TestAuditoria2Http(_SinClaves, HttpCase):
    """El checkout y las páginas sueltas por HTTP, con una clienta con cuenta (portal)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _preparar_tabla(cls.env, 'ger_aud2_clienta_http')
        cls.domicilio = cls.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        cls.domicilio.website_published = True
        cls.website = cls.env['website'].search([], limit=1)
        cls.website.dcasa_whatsapp_number = WHATSAPP_TIENDA
        cls.producto = cls.env['product.product'].create({'name': 'Pañal auditoría 2', 'list_price': 20,
                                                          'type': 'consu', 'sale_ok': True, 'is_published': True})
        cls.usuario = new_test_user(cls.env, login='aud2_clienta', name='Wanda Auditoría', groups='base.group_portal',
                                    email='wanda.aud2@example.com')
        cls.partner = cls.usuario.partner_id
        cls.partner.write({'phone': '+507 6123-4511', 'street': 'Villa Prueba II, casa 1', 'city': 'La Chorrera',
                           'country_id': cls.env.ref('base.pa').id})

    def setUp(self):
        super().setUp()
        self.orden = self.env['sale.order'].sudo().create({
            'partner_id': self.partner.id, 'website_id': self.website.id,
            'order_line': [(0, 0, {'product_id': self.producto.id})]})
        self.orden._set_delivery_method(self.domicilio)
        self.authenticate('aud2_clienta', 'aud2_clienta')

    def csrf(self, url):
        pagina = self.url_open(url)
        self.assertEqual(pagina.status_code, 200, url)
        return pagina.text, re.search(r'name="csrf_token" value="([^"]+)"', pagina.text).group(1)

    def enviar(self, token, **campos):
        datos = {'csrf_token': token, 'name': 'Wanda Auditoría', 'email': 'wanda.aud2@example.com',
                 'phone': '+507 6123-4511', 'street': 'Villa Prueba II, casa 1', 'city': 'La Chorrera',
                 'country_id': str(self.env.ref('base.pa').id), 'partner_id': str(self.partner.id),
                 'address_type': 'delivery', 'use_delivery_as_billing': 'True'}
        datos.update(campos)
        respuesta = self.url_open('/shop/address/submit', data=datos)
        self.assertEqual(respuesta.status_code, 200, respuesta.text[:300])
        return json.loads(respuesta.text)

    def mapa(self, token, lat, lon, **campos):
        return self.enviar(token, dcasa_ubic_modo='mapa', dcasa_ubic_lat=str(lat), dcasa_ubic_lon=str(lon),
                           dcasa_ubic_origen='gps', dcasa_ubic_precision='10', dcasa_ubic_confirmada='1',
                           dcasa_referencia='Casa 8', **campos)

    # --- 1: el aviso de cruce ---------------------------------------------------------------------------------------

    def test_1_el_servidor_exige_el_es_aqui_del_cruce(self):
        """Escribió San Miguelito (la casa de la mamá) y el punto está en La Chorrera: sin «📍 Es aquí» no se guarda."""
        _html, token = self.csrf(f'/shop/address?partner_id={self.partner.id}&address_type=delivery')
        regalo = {'street': 'San Ensayito, calle 8', 'city': 'San Miguelito'}
        r = self.mapa(token, *CERCA, **regalo)
        self.assertTrue(r.get('messages'), r)
        self.assertIn('escribió San Miguelito', r['messages'][0])
        self.partner.invalidate_recordset()
        self.assertFalse(self.partner.dcasa_ubic_origen, 'sin el «sí» del cruce no se guardó nada')
        r = self.mapa(token, *CERCA, dcasa_ubic_cruce_ok='1', **regalo)
        self.assertFalse(r.get('invalid_fields') or r.get('messages'), r)
        self.partner.invalidate_recordset()
        self.assertEqual((self.partner.dcasa_ubic_origen, self.partner.street), ('gps', 'San Ensayito, calle 8'))
        # Lo que llenó el mapa (la barriada y el distrito del punto) no es un cruce.
        r = self.mapa(token, *CERCA, street='Villa Prueba II, Barrio Prueba', city='La Chorrera')
        self.assertFalse(r.get('messages'), r)

    def test_1_lo_que_lleno_el_mapa_no_cuenta_y_sin_mapa_no_dice_mueva_el_mapa(self):
        distritos = ['Colón', 'La Chorrera', 'San Miguelito']
        zona = {'barriada': 'Barrio Colón', 'corregimiento': 'Barrio Colón', 'distrito': 'La Chorrera'}
        # La calle la llenó el mapa (nombra «Colón») y la ciudad la escribió ella sin el nombre del distrito: la página
        # no ve cruce, así que el servidor tampoco puede rechazarlo (si no, no tendría salida).
        lleno = {'street': 'Barrio Colón, Barrio Colón', 'city': 'Chorrera'}
        self.assertEqual(checkout.texto_escrito(lleno, zona), 'Chorrera')
        self.assertEqual(checkout.cruce_sin_responder(lleno, zona, distritos), '')
        escrito = {'street': 'Calle 8', 'city': 'San Miguelito'}
        self.assertIn('escribió San Miguelito', checkout.cruce_sin_responder(escrito, zona, distritos))
        con_mapa = geo.aviso_de_cruce('Calle 8, San Miguelito', zona, distritos)
        sin_mapa = geo.aviso_de_cruce('Calle 8, San Miguelito', zona, distritos, con_mapa=False)
        self.assertIn('Mueva el mapa o corrija la dirección.', con_mapa)
        self.assertIn('Busque la barriada o corrija la dirección.', sin_mapa)
        self.assertNotIn('mapa o', sin_mapa)
        datos = self.make_jsonrpc_request('/tienda/ubicacion/zona', {'lat': CERCA[0], 'lon': CERCA[1],
                                                                     'texto': 'Calle 3, Arraiján', 'con_mapa': False})
        self.assertIn('Busque la barriada', datos['aviso'])

    # --- 4: el punto que dio en el chat de la tienda, con cuenta ------------------------------------------------------

    def poner_pendiente(self, lat, lon, referencia='Oficina 3'):
        self.orden.write({'dcasa_ubic_pend_lat': lat, 'dcasa_ubic_pend_lon': lon, 'dcasa_ubic_pend_precision': 9,
                          'dcasa_ubic_pend_referencia': referencia})

    def test_4_la_tarjeta_del_chat_en_el_checkout(self):
        self.partner._dcasa_poner_ubicacion(*CERCA, 'gps', precision=9, confirmada=True, referencia='Casa 1')
        self.orden.partner_shipping_id = self.partner
        self.poner_pendiente(*NUEVA_FICCION)
        html = self.url_open('/shop/checkout').text
        self.assertIn('id="o_dcasa_chat_pendiente"', html, 'Andrés decía «Listo» y el punto nunca llegaba')
        self.assertIn('Barriada Nueva Ficción, Oficina 3', html)
        self.assertIn('No, en Villa Prueba II', html)
        url_si = f'/shop/address?partner_id={self.partner.id}&amp;address_type=delivery&amp;dcasa_chat=1'
        self.assertIn(url_si, html)
        self.assertNotIn(f'{NUEVA_FICCION[0]}', html, 'sin coordenadas en la tarjeta')
        # «Sí»: su dirección de entrega con el punto del chat y la casa (la calle y la ciudad las cambia el mapa).
        editar = self.url_open(url_si.replace('&amp;', '&')).text
        self.assertIn(f'data-lat="{NUEVA_FICCION[0]}"', editar)
        self.assertIn('data-del-chat="1"', editar)
        self.assertIn('value="Oficina 3"', editar)
        # «Agregar dirección» (la de la mamá) no trae lo del chat (auditoría 2: abría con su propia casa).
        nueva = self.url_open('/shop/address?address_type=delivery&use_delivery_as_billing=False').text
        self.assertIn('div_dcasa_ubicacion', nueva)
        self.assertNotIn(f'data-lat="{NUEVA_FICCION[0]}"', nueva)
        self.assertNotIn('Oficina 3', nueva)
        # El mismo sitio que la dirección de entrega (a menos de 30 m): no hay qué preguntar.
        self.poner_pendiente(CERCA[0] + 0.0001, CERCA[1])
        self.assertIsNone(self.orden._dcasa_ubic_chat_distinto())
        self.assertNotIn('o_dcasa_chat_pendiente', self.url_open('/shop/checkout').text)

    def test_4_no_lo_olvida(self):
        self.partner._dcasa_poner_ubicacion(*CERCA, 'gps', precision=9, confirmada=True, referencia='Casa 1')
        self.orden.partner_shipping_id = self.partner
        self.poner_pendiente(*NUEVA_FICCION)
        html, token = self.csrf('/shop/checkout')
        self.assertIn('o_dcasa_chat_no', html)
        respuesta = self.url_open('/tienda/ubicacion/olvidar-chat', data={'csrf_token': token},
                                  allow_redirects=False)
        self.assertEqual(respuesta.status_code, 303)
        self.assertTrue(respuesta.headers['Location'].endswith('/shop/checkout'))
        self.orden.invalidate_recordset()
        self.assertFalse(self.orden._dcasa_ubic_hay_pendiente())
        self.assertNotIn('o_dcasa_chat_pendiente', self.url_open('/shop/checkout').text)
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner._dcasa_ubic_punto(), CERCA, 'su casa de siempre sigue igual')

    # --- 5: WhatsApp sin wa.me ---------------------------------------------------------------------------------------

    def test_5_whatsapp_sin_wa_me(self):
        texto = 'Hola 👋 Ya llegué 📦'
        enlace = whatsapp.enlace('+507 6026-1919', texto)
        self.assertTrue(enlace.startswith('https://api.whatsapp.com/send?phone=50760261919&text='), enlace)
        self.assertEqual(unquote(enlace.split('&text=', 1)[1]), texto, 'los emojis llegan enteros')
        self.assertEqual(whatsapp.numero_del_enlace(enlace), '50760261919')
        self.assertEqual(whatsapp.enlace(None, 'Hola'), 'https://api.whatsapp.com/send?text=Hola')
        self.assertEqual(casa.enlace_whatsapp('', 'x'), '', 'sin número no hay enlace')
        self.assertTrue(self.website._dcasa_whatsapp_url('Hola').startswith(
            'https://api.whatsapp.com/send?phone=50760261919&text='))
        self.assertEqual(self.website._dcasa_brian_datos()['whatsapp'], '50760261919', 'Andrés arma su enlace')
        _enlace, url = self.env['dcasa.ubicacion.enlace']._crear(self.partner)
        pagina = self.url_open('/u/' + url.rsplit('/u/', 1)[1]).text
        self.assertIn('data-base="https://api.whatsapp.com/send?phone=50760261919&amp;text="', pagina)
        self.assertNotIn('wa.me', pagina)
        self.assertNotIn('wa.me', self.url_open('/u/inventado1234567890').text)

    # --- 9 y 11: el link de pago -------------------------------------------------------------------------------------

    def test_9_11_marcar_mi_casa_antes_de_firmar_o_pagar(self):
        cliente = self.env['res.partner'].create({'name': 'Lola Pago', 'phone': '+507 6555-6610', 'street': 'Calle 9',
                                                  'city': 'La Chorrera'})
        orden = self.env['sale.order'].create({'partner_id': cliente.id, 'carrier_id': self.domicilio.id,
                                               'order_line': [(0, 0, {'product_id': self.producto.id})]})
        orden._set_delivery_method(self.domicilio)
        orden.action_quotation_sent()
        self.authenticate(None, None)
        html = self.url_open(orden.get_portal_url()).text
        self.assertIn('Marcar mi casa en el mapa', html)
        self.assertLess(html.index('Marcar mi casa en el mapa'), html.index('id="sale_order_sidebar_button"'),
                        'la tarjeta va antes de «Aceptar y firmar» / «Pagar»')
        cliente._dcasa_poner_ubicacion(*CERCA, 'gps', precision=9, confirmada=True, referencia='Casa 44')
        html = self.url_open(orden.get_portal_url()).text
        self.assertNotIn('Marcar mi casa en el mapa', html)
        cambiar = re.search(r'<a [^>]*o_dcasa_ubic_cambiar[^>]*>Cambiar</a>', html)
        self.assertTrue(cambiar, '«Cambiar» es un botón (48 px), no un enlace de 26')
        self.assertIn('btn btn-outline-primary', cambiar.group(0))

    # --- 18, 19 y 21: el motorizado ----------------------------------------------------------------------------------

    def test_18_19_el_motorizado_con_punto_aproximado_llama_primero(self):
        buscada = self.env['res.partner'].create({'name': 'Bea Aproximada', 'phone': '+507 6777-8812',
                                                  'street': 'Calle 1', 'city': 'La Chorrera'})
        buscada._dcasa_poner_ubicacion(*CERCA, 'busqueda', referencia='Casa 3')
        orden = self.env['sale.order'].create({'partner_id': buscada.id, 'carrier_id': self.domicilio.id,
                                               'order_line': [(0, 0, {'product_id': self.producto.id})]})
        orden.action_confirm()
        entrega = self.env['dcasa.ubicacion.entrega']._de_la_venta(orden, crear=False)
        html = self.url_open('/entrega/' + entrega.sudo().token).text
        llamar = re.search(r'<a [^>]*id="o_dcasa_llamar"[^>]*>', html).group(0)
        self.assertIn('class="boton"', llamar, '«Llamar» arriba y como botón principal')
        self.assertLess(html.index('id="o_dcasa_llamar"'), html.index('Abrir en Waze'))
        self.assertRegex(html, r'class="boton contorno"[^>]*href="https://waze\.com/')
        self.assertIn('llame para confirmarlo', html)
        for tu in ('confírmalo', 'llama antes', 'Pide el comprobante', 'tienda'):
            self.assertNotIn(tu, html, 'de usted y sin «tienda»: Baby Caleb vende en línea')
        vencida = self.url_open('/entrega/inventadoXXXXXXXXXXXXXXXX').text
        self.assertIn('<h1 class="grande">Este código ya no sirve</h1>', vencida)
        self.assertIn('Pida el comprobante otra vez.', vencida)
        self.assertNotIn('tienda', vencida)

    # --- 3 y 21: el tope de visitas y el h1 --------------------------------------------------------------------------

    def test_3_21_el_tope_sale_con_la_plantilla(self):
        _enlace, url = self.env['dcasa.ubicacion.enlace']._crear(self.partner)
        ruta = '/u/' + url.rsplit('/u/', 1)[1]
        self.authenticate(None, None)
        inventado = self.url_open('/u/inventado1234567890').text
        self.assertIn('<h1 class="grande">Este enlace ya no sirve</h1>', inventado)
        with patch('odoo.addons.dcasa_ubicacion.controllers.publico._limite', return_value=True):
            respuesta = self.url_open(ruta)
            zona = self.url_open(ruta + '/zona', data=json.dumps({'lat': CERCA[0], 'lon': CERCA[1]}),
                                 headers={'Content-Type': 'application/json'})
            motorizado = self.url_open('/entrega/inventadoXXXXXXXXXXXXXXXX')
        self.assertEqual(respuesta.status_code, 429)
        self.assertEqual(respuesta.headers['Retry-After'], '60')
        self.assertIn('text/html', respuesta.headers['Content-Type'], 'antes: texto plano sin estilos')
        self.assertIn('<h1 class="grande">⏳ Un momento</h1>', respuesta.text)
        self.assertIn(f'href="{ruta}"', respuesta.text, '«Reintentar» vuelve a la misma página')
        self.assertIn('https://api.whatsapp.com/send?phone=50760261919&amp;text=', respuesta.text)
        self.assertNotIn(' style="', respuesta.text, 'la CSP sin mapa no deja atributos style')
        self.assertEqual((zona.status_code, zona.json()['motivo']), (429, 'tope'))
        self.assertEqual(motorizado.status_code, 429)
        self.assertIn('<h1 class="grande">⏳ Un momento</h1>', motorizado.text)


@tagged('post_install', '-at_install')
class TestAuditoria2Invitada(_SinClaves, HttpCase):
    """8: la invitada que vuelve atrás desde «Método de entrega» no pierde el punto, la casa ni quién recibe."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _preparar_tabla(cls.env, 'ger_aud2_invitada')
        cls.domicilio = cls.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        cls.domicilio.website_published = True
        cls.producto = cls.env['product.product'].create({'name': 'Toallitas auditoría 2', 'list_price': 9,
                                                          'type': 'consu', 'sale_ok': True, 'is_published': True})

    def test_8_volver_atras_abre_su_direccion(self):
        self.authenticate(None, None)
        self.make_jsonrpc_request('/shop/cart/add', {'product_template_id': self.producto.product_tmpl_id.id,
                                                     'product_id': self.producto.id, 'quantity': 1})
        pagina = self.url_open('/shop/address')
        token = re.search(r'name="csrf_token" value="([^"]+)"', pagina.text).group(1)
        datos = {'csrf_token': token, 'name': 'Ana Atrás', 'email': 'ana.atras@example.com', 'phone': '6123-9876',
                 'street': 'Villa Prueba II', 'city': 'La Chorrera', 'country_id': str(self.env.ref('base.pa').id),
                 'address_type': 'billing', 'use_delivery_as_billing': '', 'dcasa_ubic_modo': 'mapa',
                 'dcasa_ubic_lat': str(CERCA[0]), 'dcasa_ubic_lon': str(CERCA[1]), 'dcasa_ubic_origen': 'gps',
                 'dcasa_ubic_precision': '12', 'dcasa_ubic_confirmada': '1', 'dcasa_referencia': 'Casa 24',
                 'dcasa_recibe': 'Carmen'}
        r = self.url_open('/shop/address/submit', data=datos).json()
        self.assertFalse(r.get('invalid_fields') or r.get('messages'), r)
        destino = self.env['res.partner'].search([('email', '=', 'ana.atras@example.com')], limit=1)
        self.assertEqual(destino.dcasa_referencia, 'Casa 24')
        # Atrás del navegador: «/shop/address» sin nada. Antes, una dirección NUEVA vacía.
        atras = self.url_open('/shop/address', allow_redirects=False)
        self.assertEqual(atras.status_code, 303)
        self.assertIn(f'/shop/address?partner_id={destino.id}&address_type=delivery', atras.headers['Location'])
        html = self.url_open(atras.headers['Location']).text
        self.assertIn(f'data-lat="{CERCA[0]}"', html)
        self.assertIn('value="Casa 24"', html)
        self.assertIn('value="Carmen"', html)
        # Lo que pide otra cosa (con su consulta) no se toca.
        self.assertEqual(self.url_open('/shop/address?address_type=billing', allow_redirects=False).status_code, 200)


@tagged('post_install', '-at_install')
class TestAuditoria2Andres(TiendaCase):
    """17: con un GPS impreciso, la casa que escribió en el chat sí pasa al checkout."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _preparar_tabla(cls.env, 'ger_aud2_andres')

    def setUp(self):
        super().setUp()
        reiniciar_limite()
        self.addCleanup(reiniciar_limite)

    def test_17_gps_impreciso_guarda_la_casa(self):
        malo = self.post('carrito/ubicacion', {'lat': CERCA[0], 'lon': CERCA[1], 'precision': 800,
                                               'referencia': 'Casa 24, portón negro'})
        self.assertEqual(malo.status_code, 422)
        self.assertEqual((malo.json()['motivo'], malo.json()['casa_guardada']), ('impreciso', True))
        orden = self.env['sale.order'].sudo().search([('dcasa_ubic_pend_referencia', '=', 'Casa 24, portón negro')])
        self.assertEqual(len(orden), 1)
        self.assertIsNone(orden._dcasa_ubic_pendiente(), 'el punto de ±800 m no se guarda')
        self.assertEqual(orden._dcasa_ubic_pend_casa(), 'Casa 24, portón negro')
        # El formulario de la invitada (carrito anónimo) la trae escrita.
        orden.order_line = [(0, 0, {'product_id': self.colchon.product_variant_id.id})]
        html = self.url_open('/shop/address').text
        self.assertIn('value="Casa 24, portón negro"', html)


# --- En Chrome, con el teléfono emulado -------------------------------------------------------------------------------

# Un Google Maps de mentira (sin red), puesto antes que la página: mapa_entrega.js lo usa en vez de cargar el de Google.
# Guarda sus opciones; ``arrastrar`` es un dedo que mueve el mapa y ``reposar`` un «idle» sin movimiento (Satélite).
MAPA_FALSO = """
(() => {
    function LatLng(lat, lng) { this._lat = lat; this._lng = lng; }
    LatLng.prototype.lat = function () { return this._lat; };
    LatLng.prototype.lng = function () { return this._lng; };
    function Map(el, op) {
        this.op = op; this.c = new LatLng(op.center.lat, op.center.lng); this.z = op.zoom; this.l = {};
        window.mapaFalso = this;
        setTimeout(() => this.disparar('idle'), 30);
    }
    Map.prototype.addListener = function (n, fn) {
        (this.l[n] = this.l[n] || []).push(fn);
        return { remove() {} };
    };
    Map.prototype.disparar = function (n) { (this.l[n] || []).slice().forEach((fn) => fn()); };
    Map.prototype.getCenter = function () { return this.c; };
    Map.prototype.getZoom = function () { return this.z; };
    Map.prototype.idle = function () {
        clearTimeout(this.reloj);
        this.reloj = setTimeout(() => this.disparar('idle'), 60);
    };
    Map.prototype.setCenter = function (p) { this.c = new LatLng(p.lat, p.lng); this.idle(); };
    Map.prototype.setZoom = function (z) {
        if (z !== this.z) { this.z = z; this.disparar('zoom_changed'); }
        this.idle();
    };
    Map.prototype.arrastrar = function (dlat, dlng) {
        this.disparar('dragstart'); this.c = new LatLng(this.c.lat() + dlat, this.c.lng() + dlng); this.idle();
    };
    Map.prototype.reposar = function () { this.idle(); };
    window.google = { maps: { Map: Map, LatLng: LatLng } };
})();
"""

# Lo común de los recorridos del checkout: llenar lo de Odoo, el GPS, esperar, leer, «Confirmar» y si sigue ahí.
AYUDA = """
window.esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
window.$ = (s) => document.querySelector(s);
window.poner = (n, v) => {
    const c = document.querySelector(`form.address_autoformat [name=${n}]`);
    c.value = v;
    c.dispatchEvent(new Event('input', { bubbles: true }));
    c.dispatchEvent(new Event('change', { bubbles: true }));
};
window.llenar = async () => {
    poner('name', 'Ana Navegador Dos'); poner('email', 'ana.nav2@example.com'); poner('phone', '6123-9877');
    const pais = $('[name=country_id]');
    pais.value = [...pais.options].find((o) => o.getAttribute('code') === 'PA').value;
    pais.dispatchEvent(new Event('change', { bubbles: true }));
    await esperar(1800);   // Odoo espera 500 ms, pregunta al servidor y vuelve a marcar lo obligatorio
};
window.gps = (accuracy) => {
    navigator.geolocation.getCurrentPosition = (ok) =>
        ok({ coords: { latitude: 8.9012, longitude: -79.8013, accuracy } });
};
window.sinPermiso = () => { navigator.geolocation.getCurrentPosition = (_ok, mal) => mal({ code: 1 }); };
window.hasta = async (cond, ms = 6000) => {
    for (let i = 0; i < ms / 50 && !cond(); i++) await esperar(50);
    return cond();
};
window.visible = (s) => { const e = $(s); return !!e && !e.classList.contains('d-none') && !!e.offsetParent; };
window.confirmarOdoo = () => document.querySelector('[name=website_sale_main_button]').click();
true;
"""

SIGUE_EN_LA_DIRECCION = """
(async () => {
    for (let i = 0; i < 25; i++) {
        if (location.pathname !== '/shop/address') return false;
        await new Promise((ok) => setTimeout(ok, 100));
    }
    return location.pathname === '/shop/address';
})()
"""

# 1: el regalo. Escribe San Miguelito, toca «Mi ubicación» en La Chorrera, «Confirmar» no cuenta; «Es otra casa» va al
# buscador; «Es aquí» sí.
CRUCE = """
(async () => {
    await llenar();
    poner('street', 'San Ensayito, calle 8'); poner('city', 'San Miguelito');
    const s = { mini: $('.o_dcasa_ubic_mini').textContent.trim(), alto_gps: $('.o_dcasa_ubic_gps').offsetHeight };
    gps(10);
    $('.o_dcasa_ubic_gps').click();
    await hasta(() => /San Miguelito/.test($('.o_dcasa_ubic_cruce').textContent));
    s.cruce = $('.o_dcasa_ubic_cruce').textContent;
    s.botones = [visible('.o_dcasa_ubic_si'), visible('.o_dcasa_ubic_cruce_si'), visible('.o_dcasa_ubic_cruce_no')];
    s.alto_es_aqui = $('.o_dcasa_ubic_cruce_si').offsetHeight;
    poner('dcasa_referencia', 'Casa 8');
    confirmarOdoo();
    s.tras_confirmar = [$('[name=dcasa_ubic_confirmada]').value, $('[name=dcasa_ubic_cruce_ok]').value,
                        document.activeElement.className];
    $('.o_dcasa_ubic_cruce_no').click();
    s.otra_casa = [document.activeElement.className, $('.o_dcasa_ubic_aviso').textContent];
    $('.o_dcasa_ubic_cruce_si').click();
    s.es_aqui = [$('[name=dcasa_ubic_confirmada]').value, $('[name=dcasa_ubic_cruce_ok]').value,
                 visible('.o_dcasa_ubic_ok')];
    return s;
})()
"""

# 2: con mapa. GPS de ±300 m (zoom 16), GPS bueno, «Sí», Satélite, un arrastre de ~230 m y «Confirmar».
ARRASTRE = """
(async () => {
    await llenar();
    const m = window.mapaFalso;
    const s = { gesto: m.op.gestureHandling, alto: $('.o_dcasa_ubic_mapa').offsetHeight,
                pista: $('.o_dcasa_ubic_pista').textContent.trim() };
    gps(300);
    $('.o_dcasa_ubic_gps').click();
    await esperar(300);
    s.zoom_impreciso = m.z;
    gps(10);
    window.scrollTo(0, 0);
    $('.o_dcasa_ubic_gps').click();
    await hasta(() => /Villa/.test($('.o_dcasa_ubic_zona').textContent) && !$('.o_dcasa_ubic_si').disabled);
    await esperar(900);   // el desplazamiento suave
    const barra = [...document.querySelectorAll('[name=website_sale_main_button]')].map((b) => {
        let e = b;
        while (e && !['fixed', 'sticky'].includes(getComputedStyle(e).position)) e = e.parentElement;
        return e ? e.getBoundingClientRect().top : innerHeight;
    });
    const mapa = $('.o_dcasa_ubic_mapa').getBoundingClientRect();
    s.a_la_vista = [Math.round(mapa.top + mapa.height / 2),
                    Math.round($('.o_dcasa_ubic_tarjeta').getBoundingClientRect().bottom),
                    Math.round(Math.min(innerHeight, ...barra))];
    s.zoom = m.z;
    s.alto_si = $('.o_dcasa_ubic_si').offsetHeight;
    $('.o_dcasa_ubic_si').click();
    poner('dcasa_referencia', 'Casa 24');
    m.reposar();
    await esperar(300);
    s.satelite = [$('[name=dcasa_ubic_confirmada]').value, visible('.o_dcasa_ubic_ok')];
    m.arrastrar(-0.002, 0.0005);
    await esperar(300);
    await hasta(() => !$('.o_dcasa_ubic_si').disabled);
    s.arrastrado = $('[name=dcasa_ubic_confirmada]').value;
    confirmarOdoo();
    s.confirmar = [$('[name=dcasa_ubic_confirmada]').value, $('.o_dcasa_ubic_falta_tarjeta').textContent,
                   document.activeElement.className];
    $('.o_dcasa_ubic_si').click();
    s.si = $('[name=dcasa_ubic_confirmada]').value;
    return s;
})()
"""

# 3 y 7 en el checkout: sin permiso de ubicación, y sin señal al pedir la zona (vuelve con «Confirmar»).
SENAL_Y_PERMISO = """
(async () => {
    await llenar();
    const s = {};
    sinPermiso();
    $('.o_dcasa_ubic_gps').click();
    await esperar(200);
    poner('dcasa_referencia', 'Casa 2');
    confirmarOdoo();
    s.sin_permiso = [$('.o_dcasa_ubic_falta_punto').textContent, document.activeElement.className,
                     $('.o_dcasa_ubic_aviso').textContent, $('.o_dcasa_ubic_permiso').textContent];
    // Sin señal: la vista previa de la zona no llega.
    window.cortar = true;
    const abrir = XMLHttpRequest.prototype.open, enviar = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (m, url) { this.url_ = String(url); return abrir.apply(this, arguments); };
    XMLHttpRequest.prototype.send = function () {
        if (window.cortar && this.url_.includes('/tienda/ubicacion/zona')) {
            setTimeout(() => this.dispatchEvent(new ProgressEvent('error')), 20);
            return;
        }
        return enviar.apply(this, arguments);
    };
    gps(10);
    $('.o_dcasa_ubic_gps').click();
    await hasta(() => visible('.o_dcasa_ubic_reintentar'));
    s.sin_senal = [visible('.o_dcasa_ubic_reintentar'), $('.o_dcasa_ubic_reintentar').textContent.trim(),
                   visible('.o_dcasa_ubic_zona')];
    window.cortar = false;
    poner('dcasa_referencia', '');   // así, al llegar la zona, dice lo que falta en lugar de seguir solo
    confirmarOdoo();
    s.confirmar = $('.o_dcasa_ubic_falta_punto').textContent;
    await hasta(() => /Villa/.test($('.o_dcasa_ubic_zona').textContent));
    s.volvio = [$('.o_dcasa_ubic_zona').textContent, visible('.o_dcasa_ubic_falta_punto'),
                visible('.o_dcasa_ubic_reintentar')];
    await hasta(() => visible('.o_dcasa_ubic_falta_casa'));
    s.casa = $('.o_dcasa_ubic_falta_casa').textContent;
    return s;
})()
"""

# 14: «Escribir»: el número de casa después de la ciudad, la calle sin «y número» y sin «Departamento».
ESCRIBIR = """
(async () => {
    await llenar();
    const casa = $('.o_dcasa_ubic_casa'), sigue = Node.DOCUMENT_POSITION_FOLLOWING;
    const s = { calle: $('label[for=o_street]').textContent.trim(), depto: visible('#div_street2'),
                mapa_dentro: !!casa.closest('#div_dcasa_ubicacion') };
    $('#o_dcasa_modo_escrita').click();
    await esperar(100);
    s.escrita = [!!casa.closest('#div_dcasa_ubicacion'),
                 !!($('#div_city').compareDocumentPosition(casa) & sigue),
                 !!(casa.compareDocumentPosition($('#div_country')) & sigue),
                 $('label[for=o_street]').textContent.trim(), $('[name=dcasa_referencia]').required];
    $('#o_dcasa_modo_mapa').click();
    await esperar(100);
    s.de_vuelta = !!casa.closest('#div_dcasa_ubicacion');
    return s;
})()
"""

# La página /u: sin permiso y una barriada que no está (6, 7), sin señal (3), guardar lento que falla (15, 16).
PAGINA_U = """
(async () => {
    const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const $ = (s) => document.querySelector(s);
    const hasta = async (cond) => { for (let i = 0; i < 120 && !cond(); i++) await esperar(50); return cond(); };
    const s = {};
    navigator.geolocation.getCurrentPosition = (_ok, mal) => mal({ code: 1 });
    $('#o_dcasa_gps').click();
    await esperar(100);
    s.sin_permiso = [$('#o_dcasa_falta').textContent, document.activeElement.id, $('#o_dcasa_permiso').textContent,
                     $('#o_dcasa_wa_dir').hidden];
    $('#o_dcasa_buscar').value = 'Altos de Cerro Azul';
    $('#o_dcasa_buscar').dispatchEvent(new Event('input'));
    await hasta(() => /No lo encontramos/.test($('#o_dcasa_lista').textContent));
    $('#o_dcasa_referencia').value = 'Casa 14, portón rojo';
    $('#o_dcasa_referencia').dispatchEvent(new Event('input'));
    document.addEventListener('click', (e) => e.preventDefault());   // que no se vaya a WhatsApp
    $('#o_dcasa_wa_dir').click();
    s.whatsapp = [$('#o_dcasa_wa_dir').hidden, decodeURIComponent($('#o_dcasa_wa_dir').getAttribute('href'))];
    // Sin señal al pedir la zona; vuelve con el evento «online».
    const fetchDeVerdad = window.fetch;
    window.fetch = (url, op) => (/\\/(zona|guardar)$/.test(String(url)) && window.cortar
        ? new Promise((_ok, mal) => setTimeout(() => mal(new TypeError('Failed to fetch')), window.lento || 10))
        : fetchDeVerdad(url, op));
    window.cortar = true;
    navigator.geolocation.getCurrentPosition = (ok) =>
        ok({ coords: { latitude: 8.9012, longitude: -79.8013, accuracy: 10 } });
    $('#o_dcasa_gps').click();
    await hasta(() => !$('#o_dcasa_reintentar').hidden);
    s.sin_senal = [$('#o_dcasa_reintentar').hidden, $('#o_dcasa_reintentar').textContent,
                   $('#o_dcasa_falta').textContent];
    window.cortar = false;
    window.dispatchEvent(new Event('online'));
    await hasta(() => /Villa/.test($('#o_dcasa_zona').textContent) && !$('#o_dcasa_confirmar').disabled);
    s.volvio = [$('#o_dcasa_reintentar').hidden, $('#o_dcasa_confirmar').disabled, $('#o_dcasa_wa_dir').hidden];
    // Guardar con la red lenta, y que falla.
    window.cortar = true;
    window.lento = 600;
    $('#o_dcasa_confirmar').click();
    await esperar(100);
    s.guardando = $('#o_dcasa_confirmar').textContent.trim();
    await hasta(() => !!$('#o_dcasa_error').textContent);
    const boton = $('#o_dcasa_confirmar').getBoundingClientRect().top, respaldo = $('#o_dcasa_respaldo');
    s.fallo = [$('#o_dcasa_error').textContent, respaldo.hidden, respaldo.getBoundingClientRect().top > boton,
               $('#o_dcasa_confirmar').textContent.trim()];
    return s;
})()
"""

# 12: en la computadora (sin táctil), un GPS de ±2 km sin mapa.
COMPUTADORA = """
(async () => {
    navigator.geolocation.getCurrentPosition = (ok) =>
        ok({ coords: { latitude: 8.9012, longitude: -79.8013, accuracy: 2000 } });
    document.querySelector('#o_dcasa_gps').click();
    await new Promise((ok) => setTimeout(ok, 300));
    return [matchMedia('(pointer: coarse)').matches, document.querySelector('#o_dcasa_aviso').textContent];
})()
"""


# Staging, 2026-11-26: escribió la calle justo después del «sí» y tocó «Confirmar» mientras la página volvía a mirar la
# zona (con la calle nueva, por si nombra otro distrito). Salía «⏳ Un momento» y había que tocarlo otra vez: parecía
# que no hacía nada. Ahora sigue solo cuando llega la zona. La red, lenta: la vista previa tarda 700 ms.
SIGUE_SOLO = """
(async () => {
    await llenar();
    gps(10);
    $('.o_dcasa_ubic_gps').click();
    await hasta(() => /Villa/.test($('.o_dcasa_ubic_zona').textContent));
    poner('dcasa_referencia', 'Casa 5');
    $('.o_dcasa_ubic_si').click();
    const abrir = XMLHttpRequest.prototype.open, enviar = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (m, url) { this.url_ = String(url); return abrir.apply(this, arguments); };
    XMLHttpRequest.prototype.send = function () {
        if (this.url_.includes('/tienda/ubicacion/zona')) {
            const args = arguments;
            setTimeout(() => enviar.apply(this, args), 700);
            return;
        }
        return enviar.apply(this, arguments);
    };
    poner('street', 'Villa Prueba II, calle 3');
    await hasta(() => $('[name=dcasa_ubic_confirmada]').value === '');
    const s = { sin_si: $('[name=dcasa_ubic_confirmada]').value };
    confirmarOdoo();
    s.espera = $('.o_dcasa_ubic_falta_punto').textContent;
    return s;
})()
"""


# Staging, 2026-11-26: un GPS «Fuera de nuestra lista» (lejos de todos los lugares de la tabla, o sin tabla) no llena la
# barriada ni la ciudad. «Confirmar» no avanzaba y el aviso del navegador salía encima de la barra fija: la clienta no
# veía qué faltaba. Ahora la página trae ese campo al centro y le pone el foco.
CALLE_VACIA = """
(async () => {
    await llenar();
    navigator.geolocation.getCurrentPosition = (ok) =>
        ok({ coords: { latitude: 8.95, longitude: -79.70, accuracy: 10 } });
    $('.o_dcasa_ubic_gps').click();
    await hasta(() => !!$('.o_dcasa_ubic_zona').textContent.trim() && $('.o_dcasa_ubic_zona').textContent !== '…');
    // Lo que deja el mapa cuando no sabe la barriada ni el distrito (sin tabla, como en staging): los dos vacíos.
    poner('street', ''); poner('city', '');
    poner('dcasa_referencia', 'Casa 3');
    const s = { zona: $('.o_dcasa_ubic_zona').textContent.trim() };
    window.scrollTo(0, 0);
    confirmarOdoo();
    await hasta(() => document.activeElement.name === 'street', 5000);
    const r = $('[name=street]').getBoundingClientRect();
    s.foco = document.activeElement.name;
    s.centro = [Math.round(r.top), Math.round(r.bottom), innerHeight];
    s.confirmada = $('[name=dcasa_ubic_confirmada]').value;
    poner('street', 'Barriada lejana, calle 2');
    poner('city', 'Vista Lejana');   // ningún distrito: que no salte el aviso de cruce
    await esperar(1500);   // la vista previa con la calle nueva (por si nombra otro distrito)
    return s;
})()
"""


@tagged('post_install', '-at_install')
class TestNavegadorAuditoria2(_SinClaves, ChromeMovilCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _preparar_tabla(cls.env, 'ger_aud2_nav')
        cls.clienta = cls.env['res.partner'].create({'name': 'Eva Navegador Dos', 'phone': '+507 6555-0313'})
        cls.producto = cls.env['product.product'].create({
            'name': 'Caja del navegador dos', 'list_price': 20, 'type': 'consu', 'sale_ok': True,
            'is_published': True})
        cls.env['website'].search([]).write({'dcasa_whatsapp_number': WHATSAPP_TIENDA})
        # Lo que el navegador manda a «/shop/cart/add», leído aquí: con el navegador abierto, el servidor de la prueba
        # usa el mismo cursor y leer la base a la vez fallaba al azar («no results to fetch», un AccessError raro).
        cls.carrito = json.dumps({'product_template_id': cls.producto.product_tmpl_id.id,
                                  'product_id': cls.producto.id, 'quantity': 1})

    def abrir_checkout(self, browser, mapa_falso=False):
        if mapa_falso:
            browser._websocket_request('Page.addScriptToEvaluateOnNewDocument', params={'source': MAPA_FALSO})
        browser.navigate_to(self.base_url() + '/shop/cart', wait_stop=True)
        self.assertTrue(browser._wait_ready())
        self._evaluar(browser, f"""fetch('/shop/cart/add', {{method: 'POST', headers: {{'Content-Type':
            'application/json'}}, body: JSON.stringify({{jsonrpc: '2.0', method: 'call', params: {self.carrito}}})}})
            .then((r) => r.status)""")
        browser.navigate_to(self.base_url() + '/shop/checkout', wait_stop=True)
        self.assertTrue(browser._wait_ready())
        self.assertEqual(self._evaluar(browser, LISTO), 'true')
        self.assertEqual(self._evaluar(browser, 'location.pathname'), '/shop/address')
        self.assertTrue(self._evaluar(browser, AYUDA))

    def test_1_confirmar_con_cruce_no_es_el_si(self):
        with self._chrome_movil(390) as browser:
            self.abrir_checkout(browser)
            r = self._evaluar(browser, CRUCE)
            self.assertTrue(self._evaluar(browser, SIGUE_EN_LA_DIRECCION), '«Confirmar» con cruce no siguió')
            self._evaluar(browser, 'confirmarOdoo(), true')
            avanzo = browser._wait_ready("location.pathname === '/shop/checkout'", timeout=15)
        self.assertEqual(r['mini'], '¿Es para otra casa? Búsquela 👇')
        self.assertGreaterEqual(r['alto_gps'], 56, 'punto 10: «Mi ubicación» de 56 px (no 44)')
        self.assertIn('escribió San Miguelito', r['cruce'])
        self.assertIn('Busque la barriada o corrija la dirección.', r['cruce'], 'sin mapa no dice «mueva el mapa»')
        self.assertEqual(r['botones'], [False, True, True], '«📍 Es aquí» / «🏠 Es otra casa» en lugar de «Sí»')
        self.assertGreaterEqual(r['alto_es_aqui'], 48)
        confirmada, cruce_ok, foco = r['tras_confirmar']
        self.assertEqual((confirmada, cruce_ok), ('', ''), '«Confirmar» no cuenta como el sí con el cruce')
        self.assertIn('o_dcasa_ubic_cruce_si', foco)
        self.assertIn('o_dcasa_ubic_buscar', r['otra_casa'][0], '«Es otra casa» lleva al buscador')
        self.assertIn('Busque la barriada de esa casa', r['otra_casa'][1])
        self.assertEqual(r['es_aqui'], ['1', '1', True])
        self.assertTrue(avanzo, 'con «Es aquí», «Confirmar» sigue')
        destino = self.env['res.partner'].search([('email', '=', 'ana.nav2@example.com')], limit=1)
        self.assertEqual((destino.street, destino.dcasa_ubic_origen), ('San Ensayito, calle 8', 'gps'))

    def test_2_un_arrastre_sin_querer_no_cambia_la_casa(self):
        with patch.dict(os.environ, {'GOOGLE_MAPS_CLAVE_NAVEGADOR': CLAVE_FALSA}), self._chrome_movil(390) as browser:
            self.abrir_checkout(browser, mapa_falso=True)
            r = self._evaluar(browser, ARRASTRE)
            self._evaluar(browser, 'confirmarOdoo(), true')
            avanzo = browser._wait_ready("location.pathname === '/shop/checkout'", timeout=15)
        self.assertEqual(r['gesto'], 'cooperative', 'en el teléfono el mapa se mueve con dos dedos')
        self.assertLessEqual(r['alto'], 300, 'mapa más bajo en el teléfono')
        self.assertEqual(r['pista'], 'Mueva el mapa con dos dedos')
        self.assertEqual(r['zoom_impreciso'], 16, 'punto 13: GPS impreciso a zoom 16')
        self.assertEqual(r['zoom'], 18)
        centro, tarjeta, barra = r['a_la_vista']
        self.assertLess(centro, barra, 'el pin, encima de la barra fija')
        self.assertLessEqual(tarjeta, barra, 'la tarjeta del punto, encima de la barra fija')
        self.assertGreaterEqual(r['alto_si'], 56, 'punto 10: «Sí, aquí es» de 56 px')
        self.assertEqual(r['satelite'], ['1', True], 'un «idle» sin movimiento no des-confirma')
        self.assertEqual(r['arrastrado'], '')
        confirmada, falta, foco = r['confirmar']
        self.assertEqual(confirmada, '', '«Confirmar» tras un arrastre de 230 m no cuenta como el sí')
        self.assertEqual(falta, '👆 Movió el pin. ¿Es aquí?')
        self.assertIn('o_dcasa_ubic_si', foco)
        self.assertEqual(r['si'], '1')
        self.assertTrue(avanzo)
        destino = self.env['res.partner'].search([('email', '=', 'ana.nav2@example.com')], limit=1)
        self.assertEqual(destino.dcasa_ubic_origen, 'pin', 'el punto que eligió con su «sí»')

    def test_3_7_sin_permiso_y_sin_senal(self):
        with self._chrome_movil(390) as browser:
            self.abrir_checkout(browser)
            r = self._evaluar(browser, SENAL_Y_PERMISO)
        falta, foco, aviso, permiso = r['sin_permiso']
        self.assertEqual(falta, '🔍 Busque su barriada (o toque «Escribir»)')
        self.assertIn('o_dcasa_ubic_buscar', foco, 'el foco va al buscador')
        self.assertIn('Sin permiso de ubicación', aviso)
        self.assertIn('permita la ubicación', permiso)
        self.assertEqual(r['sin_senal'], [True, '📶 Sin señal. Toque para reintentar', False])
        self.assertEqual(r['confirmar'], '⏳ Un momento: estamos viendo su zona', '«Confirmar» la vuelve a pedir')
        self.assertIn('Villa Prueba II', r['volvio'][0])
        self.assertEqual(r['volvio'][1:], [False, False])
        self.assertEqual(r['casa'], '🏠 Escriba su número de casa', 'al llegar la zona, «Confirmar» dice lo que falta')

    def test_confirmar_que_esperaba_la_zona_sigue_solo(self):
        with self._chrome_movil(390) as browser:
            self.abrir_checkout(browser)
            r = self._evaluar(browser, SIGUE_SOLO)
            avanzo = browser._wait_ready("location.pathname === '/shop/checkout'", timeout=15)
        self.assertEqual(r['sin_si'], '', 'la calle nueva vuelve a mirar la zona')
        self.assertEqual(r['espera'], '⏳ Un momento: estamos viendo su zona')
        self.assertTrue(avanzo, 'al llegar la zona, «Confirmar» siguió solo')
        destino = self.env['res.partner'].search([('email', '=', 'ana.nav2@example.com')], limit=1)
        self.assertEqual((destino.street, destino.dcasa_ubic_origen), ('Villa Prueba II, calle 3', 'gps'))

    def test_sin_barriada_confirmar_lleva_al_campo_que_falta(self):
        with self._chrome_movil(390) as browser:
            self.abrir_checkout(browser)
            r = self._evaluar(browser, CALLE_VACIA)
            seguia = self._evaluar(browser, SIGUE_EN_LA_DIRECCION)
            self._evaluar(browser, 'confirmarOdoo(), true')
            avanzo = browser._wait_ready("location.pathname === '/shop/checkout'", timeout=15)
        self.assertTrue(r['zona'], 'el punto (a 12 km de la tabla) vale')
        self.assertEqual(r['confirmada'], '1', '«Confirmar» contó como el «sí» del punto')
        self.assertTrue(seguia, 'sin la barriada no se manda')
        self.assertEqual(r['foco'], 'street', 'el foco va a «Barriada o calle»')
        arriba, abajo, alto = r['centro']
        self.assertGreaterEqual(arriba, 0)
        self.assertLess(abajo, alto * 0.75, 'el campo queda a la vista, lejos de la barra fija de abajo')
        self.assertTrue(avanzo, 'con la barriada y la ciudad escritas, sigue')
        destino = self.env['res.partner'].search([('email', '=', 'ana.nav2@example.com')], limit=1)
        self.assertEqual((destino.street, destino.dcasa_ubic_origen), ('Barriada lejana, calle 2', 'gps'))

    def test_14_escribir_pide_la_casa_despues_de_la_ciudad(self):
        with self._chrome_movil(390) as browser:
            self.abrir_checkout(browser)
            r = self._evaluar(browser, ESCRIBIR)
        self.assertEqual(r['calle'], 'Barriada o calle')
        self.assertFalse(r['depto'], '«Departamento, suite, etc.» vacío no sale')
        self.assertTrue(r['mapa_dentro'])
        self.assertEqual(r['escrita'], [False, True, True, 'Barriada o calle', True])
        self.assertTrue(r['de_vuelta'])

    def abrir_enlace(self, browser):
        _enlace, url = self.env['dcasa.ubicacion.enlace']._crear(self.clienta)
        browser.navigate_to(self.base_url() + '/u/' + url.rsplit('/u/', 1)[1], wait_stop=True)
        self.assertTrue(browser._wait_ready())

    def test_3_6_7_15_16_la_pagina_del_enlace(self):
        with self._chrome_movil(390) as browser:
            self.abrir_enlace(browser)
            r = self._evaluar(browser, PAGINA_U)
        falta, foco, permiso, wa_oculto = r['sin_permiso']
        self.assertEqual(falta, '🔍 Busque su barriada arriba 👆', 'punto 7: sin decir «toque Mi ubicación»')
        self.assertEqual(foco, 'o_dcasa_buscar')
        self.assertIn('permita la ubicación', permiso)
        self.assertFalse(wa_oculto, 'punto 6: hay salida por WhatsApp')
        oculto, enlace = r['whatsapp']
        self.assertFalse(oculto)
        self.assertTrue(enlace.startswith('https://api.whatsapp.com/send?phone=50760261919&text='), enlace)
        self.assertIn('📍 Altos de Cerro Azul', enlace)
        self.assertIn('🏠 Casa 14, portón rojo', enlace)
        self.assertEqual(r['sin_senal'], [False, '📶 Sin señal. Toque para reintentar',
                                          '📶 Sin señal. Toque para reintentar 👆'],
                         'punto 3: no «Ese punto no sirve»')
        self.assertEqual(r['volvio'], [True, False, True], 'con «online» vuelve sola; el punto bueno quita la salida')
        self.assertEqual(r['guardando'], '⏳ Guardando…', 'punto 15')
        error, respaldo_oculto, debajo, boton = r['fallo']
        self.assertIn('aquí abajo 👇', error, 'punto 16: el respaldo está junto al error')
        self.assertFalse(respaldo_oculto)
        self.assertTrue(debajo, 'el respaldo va debajo de «Sí, aquí es» (al salir no corre el botón)')
        self.assertEqual(boton, 'Sí, aquí es')

    def test_12_en_la_computadora(self):
        with self._chrome_movil(390) as browser:
            browser._websocket_request('Emulation.setTouchEmulationEnabled', params={'enabled': False})
            browser._websocket_request('Emulation.setDeviceMetricsOverride', params={
                'width': 1280, 'height': 800, 'deviceScaleFactor': 1, 'mobile': False})
            self.abrir_enlace(browser)
            tactil, aviso = self._evaluar(browser, COMPUTADORA)
        self.assertFalse(tactil)
        self.assertIn('La computadora no da la ubicación exacta', aviso)
        self.assertNotIn('Su teléfono', aviso)
