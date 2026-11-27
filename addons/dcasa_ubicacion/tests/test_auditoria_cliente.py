"""Auditoría 1 (lo que vive el cliente en el navegador): cada prueba fija un hallazgo arreglado.

* El checkout de verdad, por HTTP (``UbicacionCheckout.shop_address_submit`` no tenía ninguna prueba): el camino feliz,
  el punto que vino de WhatsApp (se acepta y conserva su origen; «Escribir» no lo borra), la dirección de facturación
  (sin mapa ni número de casa) y el punto que dio en el chat de la tienda (gana sobre el viejo de la ficha).
* Las páginas sueltas: sin precio con la venta confirmada, salida por WhatsApp de un enlace vencido o usado, los pasos
  del chat, el chofer sin punto (primero «Llamar» y buscar la dirección) y el pedido del portal con el mismo
  criterio que «¡Gracias!».
* Andrés no guarda un GPS de ±800 m.
* En Chrome (el teléfono emulado): el mapa sin la clave buena, lo buscado que hay que mover, el GPS impreciso sin
  mapa y «Confirmar» en el checkout (cuenta como el «sí»; si falta algo, lo dice en el bloque).
"""
import json
import os
import re
from unittest.mock import patch

from odoo.addons.dcasa_brian_tienda.tests.common import TiendaCase
from odoo.addons.dcasa_envios.controllers.choferes import reiniciar_limite
from odoo.addons.dcasa_envios.tests.common import importar
from odoo.addons.website_dcasa.tests.chrome_movil import ChromeMovilCase
from odoo.tests import HttpCase, new_test_user, tagged

from ..controllers.checkout import FALTA_EL_PUNTO, FALTAN_INDICACIONES
from .common import CERCA

SIN_CLAVES = {'GOOGLE_MAPS_CLAVE_NAVEGADOR': '', 'GOOGLE_MAPS_CLAVE_SERVIDOR': ''}
WHATSAPP_TIENDA = '+507 6026-1919'


def _preparar_tabla(env, login):
    gerencia = new_test_user(env, login=login, name='Gerencia Auditoría Cliente',
                             groups='base.group_user,dcasa_base.group_gerencia')
    importar(env, gerencia)
    env['dcasa.envio.tarifa'].search([], limit=1).with_user(gerencia).action_aprobar()


class _SinClaves:
    """Sin claves de Google y con el límite por IP limpio."""

    def setUp(self):
        super().setUp()
        reiniciar_limite()
        self.addCleanup(reiniciar_limite)
        entorno = patch.dict(os.environ, SIN_CLAVES)
        entorno.start()
        self.addCleanup(entorno.stop)


@tagged('post_install', '-at_install')
class TestCheckoutHttp(_SinClaves, HttpCase):
    """El checkout de verdad, por HTTP, con un cliente con cuenta (portal)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _preparar_tabla(cls.env, 'ger_aud_cliente_ck')
        cls.domicilio = cls.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        cls.domicilio.website_published = True
        cls.website = cls.env['website'].search([], limit=1)
        cls.producto = cls.env['product.product'].create({'name': 'Chupón web', 'list_price': 20, 'type': 'consu',
                                                          'sale_ok': True, 'is_published': True})
        cls.usuario = new_test_user(cls.env, login='aud_cliente_ck', name='Ana Checkout', groups='base.group_portal',
                                    email='ana.checkout.cliente@example.com')
        cls.partner = cls.usuario.partner_id
        cls.partner.write({'phone': '+507 6123-4500', 'street': 'Calle 1', 'city': 'La Chorrera',
                           'country_id': cls.env.ref('base.pa').id})
        cls.villa = cls.env['dcasa.envio.lugar'].search([('name', '=', 'Villa Prueba II')], limit=1)

    def setUp(self):
        super().setUp()
        self.orden = self.env['sale.order'].sudo().create({
            'partner_id': self.partner.id, 'website_id': self.website.id,
            'order_line': [(0, 0, {'product_id': self.producto.id})]})
        self.orden._set_delivery_method(self.domicilio)
        self.authenticate('aud_cliente_ck', 'aud_cliente_ck')

    def formulario(self, url):
        pagina = self.url_open(url)
        self.assertEqual(pagina.status_code, 200, url)
        return pagina.text, re.search(r'name="csrf_token" value="([^"]+)"', pagina.text).group(1)

    def enviar(self, token, **campos):
        datos = {'csrf_token': token, 'name': 'Ana Checkout', 'email': 'ana.checkout.cliente@example.com',
                 'phone': '+507 6123-4500', 'street': 'Villa Prueba II, casa 1', 'city': 'La Chorrera',
                 'country_id': str(self.env.ref('base.pa').id)}
        datos.update(campos)
        respuesta = self.url_open('/shop/address/submit', data=datos)
        self.assertEqual(respuesta.status_code, 200, respuesta.text[:300])
        return json.loads(respuesta.text)

    def entrega(self, token, **campos):
        return self.enviar(token, partner_id=str(self.partner.id), address_type='delivery',
                           use_delivery_as_billing='True', **campos)

    def mapa(self, token, lat, lon, origen, referencia='Casa 1', **campos):
        return self.entrega(token, dcasa_ubic_modo='mapa', dcasa_ubic_lat=str(lat), dcasa_ubic_lon=str(lon),
                            dcasa_ubic_origen=origen, dcasa_ubic_confirmada='1', dcasa_referencia=referencia,
                            **campos)

    def url_entrega(self):
        return f'/shop/address?partner_id={self.partner.id}&address_type=delivery'

    def test_feliz_el_mapa_guarda_el_punto_y_el_precio(self):
        _html, token = self.formulario(self.url_entrega())
        r = self.mapa(token, *CERCA, 'gps', referencia='Casa 1, portón azul', dcasa_ubic_precision='9')
        self.assertFalse(r.get('invalid_fields'), r)
        self.partner.invalidate_recordset()
        self.assertEqual((self.partner.dcasa_ubic_origen, self.partner.dcasa_ubic_precision_m), ('gps', 9))
        self.assertTrue(self.partner.dcasa_ubic_confirmada)
        self.assertEqual(self.partner.dcasa_referencia, 'Casa 1, portón azul')
        precio = self.env['dcasa.envio.tarifa'].sudo().cotizar_lugar(self.villa)['total']
        envio = self.orden.order_line.filtered(lambda ln: ln.is_delivery and not ln.dcasa_promocion_envio_id)
        self.assertEqual(envio.price_unit, precio, 'el envío del carrito sale del punto')
        self.assertEqual(envio.dcasa_envio_lugar_id, self.villa)

    def test_sin_si_ni_casa_no_guarda_nada(self):
        _html, token = self.formulario(self.url_entrega())
        r = self.entrega(token, dcasa_ubic_modo='mapa', dcasa_ubic_lat=str(CERCA[0]), dcasa_ubic_lon=str(CERCA[1]),
                         dcasa_ubic_origen='pin', dcasa_ubic_confirmada='', dcasa_referencia='Casa 1')
        self.assertIn(FALTA_EL_PUNTO, r.get('messages', []), r)
        r = self.mapa(token, *CERCA, 'pin', referencia='  ')
        self.assertEqual(r.get('invalid_fields'), ['dcasa_referencia'], r)
        self.assertIn(FALTAN_INDICACIONES, r.get('messages', []))
        self.partner.invalidate_recordset()
        self.assertFalse(self.partner.dcasa_ubic_origen)

    def test_el_punto_de_whatsapp_se_acepta_y_conserva_su_origen(self):
        """Auditoría 1, punto 2 (y A): el checkout abre con el punto del chat («whatsapp») y ella dice «sí»."""
        self.partner._dcasa_poner_ubicacion(*CERCA, 'whatsapp', confirmada=True, referencia='Casa 1')
        html, token = self.formulario(self.url_entrega())
        self.assertIn('data-origen="whatsapp"', html)
        r = self.mapa(token, *CERCA, 'whatsapp', referencia='Casa 1, portón azul')
        self.assertFalse(r.get('invalid_fields') or r.get('messages'), r)
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.dcasa_ubic_origen, 'whatsapp', 'decir «sí» no lo vuelve «pin»')
        self.assertEqual(self.partner.dcasa_referencia, 'Casa 1, portón azul')
        # Un «enlace» o «whatsapp» con OTRO punto ya no es el del chat: lo confirmó en el mapa.
        r = self.mapa(token, CERCA[0] + 0.0005, CERCA[1], 'enlace')
        self.assertFalse(r.get('invalid_fields') or r.get('messages'), r)
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.dcasa_ubic_origen, 'pin')
        # Lo que nunca viene de la página sigue sin valer.
        r = self.mapa(token, *CERCA, 'escrita')
        self.assertIn(FALTA_EL_PUNTO, r.get('messages', []), r)

    def test_escribir_no_borra_el_punto_confiable(self):
        """La otra auditoría (A): con el punto de WhatsApp, «Escribir» lo borraba."""
        self.partner._dcasa_poner_ubicacion(*CERCA, 'whatsapp', confirmada=True, referencia='Casa 1')
        _html, token = self.formulario(self.url_entrega())
        # La MISMA calle que tiene guardada: si escribe otra, se mudó y el punto viejo se va (auditoría 2 de datos,
        # test_auditoria_2.py: test_h9). Antes esta prueba mandaba otra calle y chocaba con esa regla.
        r = self.entrega(token, dcasa_ubic_modo='escrita', dcasa_referencia='Casa 1, portón azul', street='Calle 1')
        self.assertFalse(r.get('invalid_fields'), r)
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.dcasa_ubic_origen, 'whatsapp')
        self.assertTrue(self.partner._dcasa_ubic_punto(), 'el punto que mandó por WhatsApp sigue')
        self.assertEqual(self.partner.dcasa_referencia, 'Casa 1, portón azul')
        # Si lo escrito nombra otro distrito, ese punto ya no es su casa: queda escrita.
        r = self.entrega(token, dcasa_ubic_modo='escrita', dcasa_referencia='Casa 9', street='Calle 3',
                         city='Arraiján')
        self.assertFalse(r.get('invalid_fields'), r)
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.dcasa_ubic_origen, 'escrita')
        self.assertFalse(self.partner._dcasa_ubic_punto())

    def test_la_direccion_de_facturacion_no_pide_el_mapa(self):
        """La otra auditoría (B): el bloque salía (y se exigía) en la dirección de facturación."""
        html, token = self.formulario('/shop/address?address_type=billing')
        self.assertNotIn('div_dcasa_ubicacion', html, 'la de facturación no lleva mapa ni número de casa')
        html_entrega, _token = self.formulario(self.url_entrega())
        self.assertIn('div_dcasa_ubicacion', html_entrega, 'la de entrega sí')
        r = self.enviar(token, address_type='billing', name='Empresa Aud SA', dcasa_ubic_modo='mapa',
                        dcasa_referencia='')
        self.assertFalse(r.get('invalid_fields'), r)
        self.assertNotIn(FALTA_EL_PUNTO, r.get('messages', []))
        self.assertNotIn(FALTAN_INDICACIONES, r.get('messages', []))

    def test_el_punto_nuevo_del_chat_de_la_tienda_gana_al_viejo(self):
        """La otra auditoría (C): el checkout abría en la casa vieja con la referencia vieja."""
        self.partner._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa vieja')
        otro = self.env['dcasa.envio.lugar'].search([('lat', '!=', False), ('id', '!=', self.villa.id)], limit=1)
        self.orden.write({'dcasa_ubic_pend_lat': otro.lat, 'dcasa_ubic_pend_lon': otro.lon,
                          'dcasa_ubic_pend_precision': 8, 'dcasa_ubic_pend_referencia': 'Casa nueva 7'})
        pendiente = self.orden._dcasa_ubic_pendiente()
        html, token = self.formulario(self.url_entrega())
        self.assertIn(f'data-lat="{pendiente["lat"]}"', html, 'el mapa abre en lo que dijo hoy')
        self.assertIn('data-origen="gps"', html)
        self.assertIn('Casa nueva 7', html)
        self.assertNotIn('Casa vieja', html)
        # Lo escrito (La Chorrera) no es el distrito de ese lugar: en la página sale el aviso de cruce y ella toca
        # «📍 Es aquí» (auditoría 2: sin eso, el servidor no lo guarda).
        r = self.mapa(token, pendiente['lat'], pendiente['lon'], 'gps', referencia='Casa nueva 7',
                      dcasa_ubic_precision='8', dcasa_ubic_cruce_ok='1')
        self.assertFalse(r.get('invalid_fields') or r.get('messages'), r)
        self.orden.invalidate_recordset()
        self.assertIsNone(self.orden._dcasa_ubic_pendiente(), 'guardado, el pendiente no vuelve a ganar')
        html, _token = self.formulario(self.url_entrega())
        self.assertIn('Casa nueva 7', html)

    def test_la_tarjeta_de_la_direccion_muestra_la_casa(self):
        self.partner._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 24, portón negro')
        self.orden.partner_shipping_id = self.partner
        pagina = self.url_open('/shop/checkout')
        self.assertEqual(pagina.status_code, 200)
        self.assertIn('o_dcasa_tarjeta_casa', pagina.text)
        self.assertIn('Casa 24, portón negro', pagina.text)


@tagged('post_install', '-at_install')
class TestPaginasDelCliente(_SinClaves, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _preparar_tabla(cls.env, 'ger_aud_cliente_pag')
        cls.env['website'].search([]).write({'dcasa_whatsapp_number': WHATSAPP_TIENDA})
        cls.cliente = cls.env['res.partner'].create({'name': 'Dora Prueba', 'phone': '+507 6555-0202'})
        cls.domicilio = cls.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        cls.producto = cls.env['product.product'].create({'name': 'Caja del cliente', 'list_price': 20,
                                                          'type': 'consu', 'sale_ok': True})

    def ruta(self, url):
        return '/u/' + url.rsplit('/u/', 1)[1]

    def post_json(self, ruta, cuerpo):
        return self.url_open(ruta, data=json.dumps(cuerpo), headers={'Content-Type': 'application/json'})

    def venta(self, partner=None):
        return self.env['sale.order'].create({'partner_id': (partner or self.cliente).id,
                                              'carrier_id': self.domicilio.id,
                                              'order_line': [(0, 0, {'product_id': self.producto.id})]})

    def test_con_la_venta_confirmada_no_dice_precio(self):
        """Punto 9: el enlace de una venta ya confirmada mostraba «Envío $15»."""
        orden = self.venta()
        _enlace, url = self.env['dcasa.ubicacion.enlace']._crear(self.cliente, orden=orden)
        borrador = self.post_json(self.ruta(url) + '/zona', {'lat': CERCA[0], 'lon': CERCA[1]}).json()
        self.assertTrue(borrador['precio'], 'sin confirmar, el precio ayuda a decidir')
        orden.action_confirm()
        _enlace, url = self.env['dcasa.ubicacion.enlace']._crear(self.cliente, orden=orden, creado_por='aviso')
        datos = self.post_json(self.ruta(url) + '/zona', {'lat': CERCA[0], 'lon': CERCA[1]}).json()
        self.assertIn('Villa Prueba II', datos['zona'])
        self.assertIsNone(datos['precio'])
        self.assertIs(datos['mostrar_precio'], False)

    def test_vencido_y_usado_tienen_salida_por_whatsapp(self):
        """Punto 16: callejones sin salida."""
        enlace, url = self.env['dcasa.ubicacion.enlace']._crear(self.cliente)
        enlace._confirmar(*CERCA, 'pin', referencia='Casa 2')
        usado = self.url_open(self.ruta(url))
        self.assertIn('Ya la tenemos', usado.text)
        self.assertIn('id="o_dcasa_cambiar"', usado.text)
        self.assertIn('href="https://api.whatsapp.com/send?phone=50760261919&amp;text=', usado.text)
        enlace.sudo().vence = enlace.create_date.replace(year=2000)
        vencido = self.url_open(self.ruta(url))
        self.assertEqual(vencido.status_code, 404)
        self.assertIn('Pedir otro enlace por WhatsApp', vencido.text)
        self.assertIn('href="https://api.whatsapp.com/send?phone=50760261919&amp;text=', vencido.text)
        self.assertNotIn('Dora', vencido.text, 'vencido no dice de quién es')
        self.assertNotIn(' style="', vencido.text + usado.text, 'la CSP sin mapa no deja atributos style')

    def test_los_pasos_de_la_pagina_son_los_del_chat(self):
        """Punto 14: el chat dice 1️⃣ abra, 2️⃣ «Mi ubicación», 3️⃣ la casa y «Sí»; la página empezaba en 1."""
        _enlace, url = self.env['dcasa.ubicacion.enlace']._crear(self.cliente)
        html = self.url_open(self.ruta(url)).text
        pasos = re.findall(r'<span class="paso" aria-hidden="true">(\d)</span>', html)
        self.assertEqual(pasos, ['2', '3'])
        self.assertLess(html.index('>2</span>'), html.index('Mi ubicación'))
        self.assertLess(html.index('>3</span>'), html.index('Número de casa e indicaciones'))
        self.assertIn('id="o_dcasa_falta"', html, '«Sí, aquí es» apagado dice qué falta')
        self.assertRegex(html, r'id="o_dcasa_respaldo" hidden', 'el respaldo no sale de entrada')

    def test_el_chofer_sin_punto_primero_llama_y_busca(self):
        """Punto 15: sin punto, el botón principal no puede ser «Avisar que llegué»."""
        escrita = self.env['res.partner'].create({'name': 'Pepa Escrita', 'phone': '+507 6444-5555',
                                                  'street': 'Calle 5, Nuevo Arraiján', 'city': 'Arraiján'})
        escrita._dcasa_poner_escrita(referencia='Casa 12')
        orden = self.venta(escrita)
        orden.action_confirm()
        entrega = self.env['dcasa.ubicacion.entrega']._de_la_venta(orden, crear=False)
        html = self.url_open('/entrega/' + entrega.sudo().token).text

        def clase(id_):
            return re.search(rf'<a [^>]*id="{id_}"[^>]*>', html).group(0)

        self.assertLess(html.index('id="o_dcasa_llamar"'), html.index('id="o_dcasa_llegue"'))
        self.assertIn('class="boton"', clase('o_dcasa_llamar'), '«Llamar» es el botón principal')
        self.assertIn('class="boton contorno"', clase('o_dcasa_llegue'))
        self.assertIn('https://www.google.com/maps/search/?api=1&amp;query=Calle%205%2C%20Nuevo%20Arraij',
                      clase('o_dcasa_buscar_maps'))
        # Con punto, todo como antes: Waze y Google Maps arriba y «Avisar que llegué» como botón principal.
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Portón negro')
        orden = self.venta()
        orden.action_confirm()
        entrega = self.env['dcasa.ubicacion.entrega']._de_la_venta(orden, crear=False)
        html = self.url_open('/entrega/' + entrega.sudo().token).text
        self.assertIn('class="boton"', clase('o_dcasa_llegue'))
        self.assertNotIn('o_dcasa_buscar_maps', html)
        self.assertNotIn('o_dcasa_llamar', html)

    def test_el_pedido_del_portal_usa_el_criterio_de_gracias(self):
        """Punto 5: una barriada buscada sin mover el pin pasaba como lista en el pedido (no en «¡Gracias!»)."""
        buscada = self.env['res.partner'].create({'name': 'Bea Búsqueda', 'phone': '+507 6777-8888'})
        buscada._dcasa_poner_ubicacion(*CERCA, 'busqueda', referencia='Casa 3')
        orden = self.venta(buscada)
        orden._portal_ensure_token()
        self.assertTrue(orden._dcasa_ubic_falta_la_casa())
        self.assertTrue(orden._dcasa_ubic_url_para_marcar())
        self.assertIn('Marcar mi casa en el mapa', self.url_open(orden.get_portal_url()).text)
        buscada._dcasa_poner_ubicacion(*CERCA, 'gps', precision=800, referencia='Casa 3')
        self.assertTrue(orden._dcasa_ubic_falta_la_casa(), 'un GPS de ±800 m tampoco es su casa')
        buscada._dcasa_poner_ubicacion(*CERCA, 'gps', precision=9, referencia='Casa 3')
        self.assertFalse(orden._dcasa_ubic_falta_la_casa())
        self.assertFalse(orden._dcasa_ubic_url_para_marcar())
        pagina = self.url_open(orden.get_portal_url()).text
        self.assertNotIn('Marcar mi casa en el mapa', pagina)
        self.assertIn('Cambiar', pagina)


@tagged('post_install', '-at_install')
class TestAndresUbicacion(TiendaCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _preparar_tabla(cls.env, 'ger_aud_cliente_andres')

    def setUp(self):
        super().setUp()
        reiniciar_limite()
        self.addCleanup(reiniciar_limite)

    def test_no_guarda_un_gps_de_800_metros(self):
        """Punto 7: Andrés guardaba un GPS de ±800 m y decía «Listo»."""
        malo = self.post('carrito/ubicacion', {'lat': CERCA[0], 'lon': CERCA[1], 'precision': 800,
                                               'referencia': 'Casa 24'})
        self.assertEqual((malo.status_code, malo.json()['motivo'], malo.json()['precision']), (422, 'impreciso', 800))
        # El punto no se guarda; la casa que escribió, sí (auditoría 2, punto 17: test_auditoria_2_cliente.py).
        orden = self.env['sale.order'].sudo().search([('dcasa_ubic_pend_referencia', '=', 'Casa 24')])
        self.assertEqual(len(orden), 1)
        self.assertIsNone(orden._dcasa_ubic_pendiente(), 'sin el punto de ±800 m')
        bueno = self.post('carrito/ubicacion', {'lat': CERCA[0], 'lon': CERCA[1], 'precision': 100,
                                                'referencia': 'Casa 24'})
        self.assertTrue(bueno.json()['ok'], bueno.text)


# --- En Chrome, con el teléfono emulado ------------------------------------------------------------------------------

# Un Google de mentira (sin red): el mapa se crea y avisa lo que se le pide. ``centro`` decide qué da getCenter().
GOOGLE_FALSO = """
    window.google = { maps: { Map: function (el, op) {
        this.oyentes = {};
        this.c = op.center; this.z = op.zoom;
        this.addListener = (ev, fn) => { this.oyentes[ev] = fn; };
        this.setCenter = (c) => { this.c = c; };
        this.setZoom = (z) => { this.z = z; };
        this.getZoom = () => this.z;
        this.getCenter = () => window.centroRoto ? undefined : { lat: () => this.c.lat, lng: () => this.c.lng };
        window.mapaFalso = this;
    } } };
"""

PROBAR_EL_MAPA = GOOGLE_FALSO + """
(async () => {
    const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const montar = (clave) => {
        const div = document.createElement('div'), aviso = document.createElement('p');
        document.body.append(div, aviso);
        const r = { aviso, sinMapa: null, ultimo: null };
        r.mapa = window.DcasaMapaEntrega.montar({ mapa: div, clave, aviso,
            alSinMapa: (m) => { r.sinMapa = m; }, alCambiar: (p) => { r.ultimo = p; } });
        return r;
    };
    const salida = {};
    // 1) Con mapa: lo buscado no es la puerta hasta moverlo.
    const a = montar('AIzaDePrueba');
    await espera(50);
    a.mapa.centrar(8.9012, -79.8013, 17, 'busqueda');
    salida.buscado = [a.mapa.conMapa(), a.ultimo.bueno, a.ultimo.motivo, a.aviso.textContent];
    window.mapaFalso.oyentes.dragstart();
    window.mapaFalso.oyentes.idle();
    salida.movido = [a.ultimo.bueno, a.ultimo.origen];
    // 2) Google no da el centro (clave rechazada): sin mapa, con el último punto, y nada se cuelga.
    window.centroRoto = true;
    a.mapa.centrar(8.9013, -79.8014, 18, 'gps', 12);
    salida.centro_roto = [a.mapa.conMapa(), a.sinMapa, a.ultimo.bueno, a.ultimo.lat];
    a.mapa.destruir();
    window.centroRoto = false;
    // 3) gm_authFailure con el mapa ya puesto: pasa al modo sin mapa.
    const b = montar('AIzaDePrueba');
    await espera(50);
    const antes = b.mapa.conMapa();
    window.gm_authFailure();
    salida.clave_rechazada = [antes, b.mapa.conMapa(), b.sinMapa, b.aviso.textContent];
    // 4) Sin mapa: el GPS de ±800 m no sirve; lo buscado vale, avisando que es aproximado.
    b.mapa.centrar(8.9012, -79.8013, 18, 'gps', 800);
    salida.impreciso = [b.ultimo.bueno, b.ultimo.motivo, b.aviso.textContent];
    b.mapa.centrar(8.9012, -79.8013, 17, 'busqueda');
    salida.aproximado = [b.ultimo.bueno, b.ultimo.aproximado, b.aviso.textContent];
    return salida;
})()
"""

# La página /u/ con un GPS de ±800 m (sin mapa) y luego de ±12 m: el precio y el respaldo solo con el bueno.
PROBAR_LA_PAGINA = """
(async () => {
    const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const $ = (s) => document.querySelector(s);
    const gps = (accuracy) => { navigator.geolocation.getCurrentPosition = (ok) =>
        ok({ coords: { latitude: 8.9012, longitude: -79.8013, accuracy } }); };
    const salida = { al_abrir: $('#o_dcasa_falta').textContent };
    gps(800);
    $('#o_dcasa_gps').click();
    await espera(900);
    salida.malo = [$('#o_dcasa_tarjeta').hidden, $('#o_dcasa_falta').textContent, $('#o_dcasa_confirmar').disabled,
                   $('#o_dcasa_respaldo').hidden, $('#o_dcasa_aviso').textContent];
    gps(12);
    $('#o_dcasa_gps').click();
    for (let i = 0; i < 100 && !/Villa/.test($('#o_dcasa_zona').textContent); i++) await espera(50);
    salida.bueno = [$('#o_dcasa_tarjeta').hidden, $('#o_dcasa_precio').textContent, $('#o_dcasa_falta').textContent,
                    $('#o_dcasa_respaldo').hidden];
    $('#o_dcasa_referencia').value = 'Casa 24';
    $('#o_dcasa_referencia').dispatchEvent(new Event('input'));
    salida.con_casa = [$('#o_dcasa_falta').textContent, $('#o_dcasa_confirmar').disabled];
    return salida;
})()
"""

LISTO = """
(async () => {
    for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) {
        await new Promise((ok) => setTimeout(ok, 50));
    }
    await new Promise((ok) => setTimeout(ok, 400));
    return document.body.getAttribute('is-ready');
})()
"""

# El checkout de una invitada: llena lo de Odoo y el número de casa (``casa``), pone el punto con el GPS (``punto``) y
# toca «Confirmar» SIN tocar «Sí, aquí es».
CHECKOUT = """
(async (punto, casa) => {
    const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const $ = (s) => document.querySelector(s);
    const poner = (n, v) => {
        const c = $(`form.address_autoformat [name=${n}]`);
        if (!c) return;
        c.value = v;
        c.dispatchEvent(new Event('input', { bubbles: true }));
        c.dispatchEvent(new Event('change', { bubbles: true }));
    };
    poner('name', 'Ana Navegador'); poner('email', 'ana.navegador@example.com'); poner('phone', '6123-9876');
    const pais = $('[name=country_id]');
    pais.value = [...pais.options].find((o) => o.getAttribute('code') === 'PA').value;
    pais.dispatchEvent(new Event('change', { bubbles: true }));
    await espera(1800);   // Odoo espera 500 ms, pregunta al servidor y vuelve a marcar lo obligatorio
    const salida = { casa_obligatoria: $('[name=dcasa_referencia]').required,
                     calle: $('label[for=o_street]').textContent.trim() };
    if (punto) {
        navigator.geolocation.getCurrentPosition = (ok) =>
            ok({ coords: { latitude: 8.9012, longitude: -79.8013, accuracy: 10 } });
        $('.o_dcasa_ubic_gps').click();
        for (let i = 0; i < 100 && $('.o_dcasa_ubic_si').disabled; i++) await espera(50);
        salida.zona = $('.o_dcasa_ubic_zona').textContent;
    } else {
        poner('street', 'Calle 3'); poner('city', 'La Chorrera');
    }
    poner('dcasa_referencia', casa);
    salida.confirmada_antes = $('[name=dcasa_ubic_confirmada]').value;
    window.scrollTo(0, document.body.scrollHeight);
    // El de la barra de abajo (el que se ve en el celular) o el del resumen: los dos son «Confirmar».
    document.querySelector('[name=website_sale_main_button]').click();
    // Lo que hace la página al tocarlo es inmediato; si todo está bien, Odoo manda el formulario y la página se va:
    // se devuelve ya, antes de que se vaya.
    salida.confirmada = $('[name=dcasa_ubic_confirmada]').value;
    salida.foco = document.activeElement.name || document.activeElement.className;
    const visible = (s) => !$(s).classList.contains('d-none');
    if (visible('.o_dcasa_ubic_falta_punto') || visible('.o_dcasa_ubic_falta_casa')) {
        await espera(900);   // el desplazamiento suave hasta el bloque
        const vista = (s) => {
            const r = $(s).getBoundingClientRect();
            return visible(s) && r.top >= 0 && r.bottom <= innerHeight;
        };
        salida.falta_punto = [vista('.o_dcasa_ubic_falta_punto'), $('.o_dcasa_ubic_falta_punto').textContent];
        salida.falta_casa = [vista('.o_dcasa_ubic_falta_casa'), $('.o_dcasa_ubic_falta_casa').textContent];
    }
    return salida;
})(%s, %s)
"""


SIGUE_EN_LA_DIRECCION = """
(async () => {
    for (let i = 0; i < 30; i++) {
        if (location.pathname !== '/shop/address') return true;
        await new Promise((ok) => setTimeout(ok, 100));
    }
    return location.pathname !== '/shop/address';
})()
"""


@tagged('post_install', '-at_install')
class TestNavegadorDelCliente(_SinClaves, ChromeMovilCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _preparar_tabla(cls.env, 'ger_aud_cliente_nav')
        cls.cliente = cls.env['res.partner'].create({'name': 'Eva Navegador', 'phone': '+507 6555-0303'})
        cls.producto = cls.env['product.product'].create({
            'name': 'Caja del navegador', 'list_price': 20, 'type': 'consu', 'sale_ok': True, 'is_published': True})

    def abrir_enlace(self, browser):
        _enlace, url = self.env['dcasa.ubicacion.enlace']._crear(self.cliente)
        browser.navigate_to(self.base_url() + '/u/' + url.rsplit('/u/', 1)[1], wait_stop=True)
        self.assertTrue(browser._wait_ready())

    def test_el_mapa_sin_la_clave_buena_y_lo_buscado(self):
        """Puntos 1, 5 y 6 en el motor del mapa (static/src/lib/mapa_entrega.js)."""
        with self._chrome_movil(390) as browser:
            self.abrir_enlace(browser)
            r = self._evaluar(browser, PROBAR_EL_MAPA)
        self.assertEqual(r['buscado'][:3], [True, False, 'buscado'])
        self.assertEqual(r['buscado'][3], '👆 Ahora mueve el mapa hasta tu puerta')
        self.assertEqual(r['movido'], [True, 'pin'], 'movido el mapa, ya es su puerta')
        self.assertEqual(r['centro_roto'], [False, 'centro', True, 8.9013], 'sin centro: sin mapa y con el GPS')
        self.assertEqual(r['clave_rechazada'][:3], [True, False, 'clave'])
        self.assertIn('El mapa no cargó', r['clave_rechazada'][3])
        self.assertEqual(r['impreciso'][:2], [False, 'impreciso_sin_mapa'])
        self.assertIn('Active la ubicación precisa y toque «Mi ubicación» en su puerta', r['impreciso'][2])
        self.assertNotIn('Use su celular', r['impreciso'][2])
        self.assertEqual(r['aproximado'][:2], [True, True])
        self.assertIn('aproximado', r['aproximado'][2])

    def test_la_pagina_del_enlace_con_un_gps_malo_y_uno_bueno(self):
        """Puntos 4, 6 y 17 en /u/: sin precio ni respaldo con un punto malo; «Sí» dice qué falta."""
        with self._chrome_movil(390) as browser:
            self.abrir_enlace(browser)
            r = self._evaluar(browser, PROBAR_LA_PAGINA)
        self.assertEqual(r['al_abrir'], '📍 Toca «Mi ubicación» o busca tu barriada')
        tarjeta_oculta, falta, apagado, respaldo_oculto, aviso = r['malo']
        self.assertTrue(tarjeta_oculta, 'sin precio con un GPS de ±800 m')
        self.assertEqual((falta, apagado, respaldo_oculto), ('📍 Falta tu ubicación exacta', True, True))
        self.assertIn('Su teléfono no da la ubicación exacta', aviso)
        tarjeta_oculta, precio, falta, respaldo_oculto = r['bueno']
        self.assertFalse(tarjeta_oculta)
        self.assertTrue(precio.startswith('Envío $'), precio)
        self.assertEqual(falta, '🏠 Escribe tu número de casa')
        self.assertTrue(respaldo_oculto, 'el respaldo sale solo si «guardar» falla o pasa un rato')
        self.assertEqual(r['con_casa'], ['', False])

    def checkout(self, punto, casa, avanza):
        # Leído antes de abrir el navegador: con él abierto, el servidor de la prueba usa el mismo cursor y leer la base
        # a la vez fallaba al azar («no results to fetch», un AccessError raro).
        carrito = json.dumps({'product_template_id': self.producto.product_tmpl_id.id,
                              'product_id': self.producto.id, 'quantity': 1})
        with self._chrome_movil(390) as browser:
            browser.navigate_to(self.base_url() + '/shop/cart', wait_stop=True)
            self.assertTrue(browser._wait_ready())
            self._evaluar(browser, f"""fetch('/shop/cart/add', {{method: 'POST', headers: {{'Content-Type':
                'application/json'}}, body: JSON.stringify({{jsonrpc: '2.0', method: 'call', params: {carrito}}})}})
                .then((r) => r.status)""")
            browser.navigate_to(self.base_url() + '/shop/checkout', wait_stop=True)
            self.assertTrue(browser._wait_ready())
            self.assertEqual(self._evaluar(browser, LISTO), 'true')
            self.assertEqual(self._evaluar(browser, 'location.pathname'), '/shop/address')
            r = self._evaluar(browser, CHECKOUT % (json.dumps(punto), json.dumps(casa)))
            if avanza:
                r['avanzo'] = browser._wait_ready("location.pathname === '/shop/checkout'", timeout=15)
            else:
                # _wait_ready no sirve para esperar que algo NO pase (su última consulta puede vencer): tres segundos
                # mirando que siga en la dirección (si la página se fuera, la evaluación falla y la prueba también).
                r['avanzo'] = self._evaluar(browser, SIGUE_EN_LA_DIRECCION)
        return r

    def test_confirmar_sin_tocar_si_cuenta_como_el_si(self):
        """Punto 3: «Confirmar» con el punto bueno y la zona lista llena el «sí» y sigue."""
        r = self.checkout(True, 'Casa 24, portón negro', avanza=True)
        self.assertEqual(r['calle'], 'Barriada o calle', 'punto 10: en modo mapa no pide el número otra vez')
        self.assertTrue(r['casa_obligatoria'], 'Odoo ya no le quita el «required» al cambiar el país')
        self.assertIn('Villa Prueba II', r['zona'])
        self.assertEqual((r['confirmada_antes'], r['confirmada']), ('', '1'))
        self.assertTrue(r['avanzo'], 'pasó a /shop/checkout')
        destino = self.env['res.partner'].search([('dcasa_referencia', '=', 'Casa 24, portón negro')])
        self.assertEqual((destino.dcasa_ubic_origen, destino.dcasa_ubic_precision_m), ('gps', 10))

    def test_confirmar_sin_punto_lo_dice_en_el_bloque(self):
        """Punto 3: sin el punto, no se envía; el aviso sale en el bloque, a la vista, y el foco va a «Mi ubicación»."""
        r = self.checkout(False, 'Casa 24', avanza=False)
        self.assertFalse(r['avanzo'])
        self.assertEqual(r['falta_punto'], [True, '📍 Toca «Mi ubicación» o busca tu barriada'])
        self.assertIn('o_dcasa_ubic_gps', r['foco'])

    def test_confirmar_sin_casa_lo_dice_en_el_bloque(self):
        """Punto 3: con el punto pero sin el número de casa, el aviso va junto al campo y el foco también."""
        r = self.checkout(True, '', avanza=False)
        self.assertFalse(r['avanzo'])
        self.assertEqual(r['falta_casa'], [True, '🏠 Escribe tu número de casa'])
        self.assertEqual(r['foco'], 'dcasa_referencia')
