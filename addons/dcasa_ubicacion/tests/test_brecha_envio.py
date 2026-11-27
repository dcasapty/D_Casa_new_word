"""Cerrar la brecha del envío (el dueño, 2026-11-25: «el dolor número uno son los pedidos devueltos»): el número de casa
y las indicaciones siempre, el aviso al equipo en el chat, el enlace con tres pasos y el botón nativo de WhatsApp, el
enlace desde la página del pedido (el link de pago) y el punto del chat de la tienda guardado en el carrito."""
import json
from unittest.mock import patch

from odoo.addons.dcasa_brian_tienda.tests.common import TiendaCase
from odoo.addons.dcasa_envios.controllers.choferes import reiniciar_limite
from odoo.addons.dcasa_envios.tests.common import importar
from odoo.tests import new_test_user, tagged

from .common import CERCA, LEJOS, UbicacionCase


@tagged('post_install', '-at_install')
class TestChatDeJuan(UbicacionCase):

    def test_el_enlace_trae_tres_pasos_y_en_whatsapp_oficial_el_boton(self):
        conv = self.conversacion(id_externo='50761230010')
        datos = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)._juan_enlace_de_ubicacion()
        for paso in ('1️⃣', '2️⃣', '3️⃣', datos['enlace']):
            self.assertIn(paso, datos['frase_para_el_cliente'])
        self.assertNotIn('boton_whatsapp', datos, 'el botón nativo solo existe en la API oficial')
        conv.sudo().write({'canal': 'whatsapp_cloud'})
        datos = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)._juan_enlace_de_ubicacion()
        self.assertTrue(datos['boton_whatsapp'])

    def test_para_otra_casa_no_usa_el_gps_ni_el_boton(self):
        conv = self.conversacion(id_externo='50761230013')
        conv.sudo().write({'canal': 'whatsapp_cloud'})
        Herramientas = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)
        datos = Herramientas._juan_enlace_de_ubicacion(para_otra_casa=True)
        self.assertNotIn('boton_whatsapp', datos, 'el botón mandaría la ubicación del teléfono, no la de esa casa')
        self.assertIn('Busca la barriada', datos['frase_para_el_cliente'])
        self.assertNotIn('Mi ubicación', datos['frase_para_el_cliente'])
        for linea in datos['frase_para_el_cliente'].split('\n')[1:]:
            self.assertRegex(linea, r'^[123]️⃣ ', 'un paso por línea: el Worker conserva así sus íconos')

    def test_cotizar_sin_lugar_ni_punto_no_es_un_error(self):
        conv = self.conversacion(id_externo='50761230014')
        datos = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)._j_cotizar_envio()
        self.assertEqual(datos['estado'], 'sin_ubicacion')
        self.assertIn('enlace_de_ubicacion', datos['instruccion'])
        self.assertNotIn('ubicacion_guardada', datos)

    def test_el_listo_repite_la_casa_para_no_volver_a_preguntarla(self):
        conv = self.conversacion(id_externo='50761230015')
        self.configurar_worker()
        enlace, _url = self.env['dcasa.ubicacion.enlace']._crear(conv.partner_id, conversacion=conv, creado_por='juan')
        enlace._confirmar(*CERCA, 'gps', precision=9, referencia='Casa 24, portón negro')
        mensaje = self.env['dcasa.mensaje'].sudo().search([('conversacion_id', '=', conv.id), ('origen', '=', 'odoo'),
                                                           ('tipo', '=', 'mensaje')], order='id desc', limit=1)
        self.assertIn('🏠 Casa 24, portón negro.', mensaje.texto)
        self.assertLess(mensaje.texto.index('🏠'), mensaje.texto.index('🚚'))

    def test_guardar_indicaciones(self):
        conv = self.conversacion(id_externo='50761230011')
        Herramientas = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)
        datos = Herramientas._juan_guardar_indicaciones(texto='  Casa 24,   portón negro ')
        self.assertTrue(datos['guardado'])
        self.assertEqual(conv.partner_id.dcasa_referencia, 'Casa 24, portón negro')
        self.assertIn('enlace_de_ubicacion', datos['instruccion'], 'sin punto todavía: que lo pida')
        aviso = self.env['dcasa.mensaje'].sudo().search([('conversacion_id', '=', conv.id), ('tipo', '=', 'aviso')],
                                                         order='id desc', limit=1)
        self.assertIn('Casa 24, portón negro', aviso.texto)

    def test_al_llegar_la_ubicacion_el_equipo_ve_el_aviso_sin_coordenadas(self):
        conv = self.conversacion(id_externo='50761230012')
        self.configurar_worker()
        enlace, _url = self.env['dcasa.ubicacion.enlace']._crear(conv.partner_id, conversacion=conv, creado_por='juan')
        enlace._confirmar(*CERCA, 'gps', precision=9, referencia='Casa 3')
        avisos = self.env['dcasa.mensaje'].sudo().search([('conversacion_id', '=', conv.id), ('tipo', '=', 'aviso')])
        texto = ' '.join(avisos.mapped('texto'))
        self.assertIn('Ubicación de entrega: Villa Prueba II', texto)
        self.assertIn('🏠 Casa 3', texto)
        self.assertIn('Envío', texto)
        self.assertNotIn('8.9012', texto, 'nunca las coordenadas en el chat')


@tagged('post_install', '-at_install')
class TestEnlaceDelPedido(UbicacionCase):

    def test_al_confirmar_desde_el_pedido_se_recalcula_su_envio(self):
        domicilio = self.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        producto = self.env['product.product'].create({'name': 'Caja', 'list_price': 20, 'type': 'consu'})
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id,
                                               'order_line': [(0, 0, {'product_id': producto.id})]})
        orden._set_delivery_method(domicilio)
        enlace, _url = self.env['dcasa.ubicacion.enlace']._crear(self.cliente, orden=orden)
        enlace._confirmar(*CERCA, 'pin', referencia='Casa 9')
        envio = orden.order_line.filtered(lambda ln: ln.is_delivery and not ln.dcasa_promocion_envio_id)
        self.assertEqual(envio.dcasa_envio_lugar_id, self.villa)
        self.assertEqual(envio.price_unit, self.env['dcasa.envio.tarifa'].sudo().cotizar_lugar(self.villa)['total'])


@tagged('post_install', '-at_install')
class TestRutasDeLaBrecha(TiendaCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gerencia = new_test_user(cls.env, login='ger_brecha', name='Gerencia Brecha',
                                 groups='base.group_user,dcasa_base.group_gerencia')
        importar(cls.env, gerencia)
        cls.env['dcasa.envio.tarifa'].search([], limit=1).with_user(gerencia).action_aprobar()

    def setUp(self):
        super().setUp()
        reiniciar_limite()
        self.addCleanup(reiniciar_limite)

    def test_el_chat_de_la_tienda_guarda_el_punto_y_la_casa_en_el_carrito(self):
        sin_casa = self.post('carrito/ubicacion', {'lat': CERCA[0], 'lon': CERCA[1], 'precision': 8})
        self.assertEqual((sin_casa.status_code, sin_casa.json()['motivo']), (400, 'indicaciones'))
        lejos = self.post('carrito/ubicacion', {'lat': LEJOS[0], 'lon': LEJOS[1], 'referencia': 'Casa'})
        self.assertEqual((lejos.status_code, lejos.json()['motivo']), (422, 'fuera_de_panama'))
        sin_csrf = self.post('carrito/ubicacion', {'lat': CERCA[0], 'lon': CERCA[1], 'referencia': 'Casa'}, csrf=False)
        self.assertEqual(sin_csrf.status_code, 403)
        bien = self.post('carrito/ubicacion', {'lat': CERCA[0], 'lon': CERCA[1], 'precision': 8,
                                               'referencia': 'Casa 24, portón negro'})
        self.assertTrue(bien.json()['ok'], bien.text)
        self.assertIn('Villa Prueba II', bien.json()['zona'])
        orden = self.env['sale.order'].sudo().search([('dcasa_ubic_pend_referencia', '=', 'Casa 24, portón negro')],
                                                     limit=1)
        self.assertEqual(orden._dcasa_ubic_pendiente(), {'lat': CERCA[0], 'lon': CERCA[1], 'precision': 8,
                                                          'referencia': 'Casa 24, portón negro'})
        self.assertNotIn('8.9012', json.dumps(bien.json()), 'las coordenadas no vuelven')

    def test_el_link_de_pago_lleva_al_mapa_de_su_pedido(self):
        cliente = self.env['res.partner'].create({'name': 'Lina Pedido', 'phone': '+507 6999-1111'})
        producto = self.env['product.product'].create({'name': 'Caja', 'list_price': 20, 'type': 'consu'})
        domicilio = self.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        orden = self.env['sale.order'].create({'partner_id': cliente.id, 'carrier_id': domicilio.id,
                                               'order_line': [(0, 0, {'product_id': producto.id})]})
        orden._portal_ensure_token()
        pagina = self.url_open(orden.get_portal_url())
        self.assertIn('Marcar mi casa en el mapa', pagina.text)
        sin_permiso = self.url_open(f'/u/pedido/{orden.id}?access_token=malo', allow_redirects=False)
        self.assertEqual(sin_permiso.status_code, 404)
        with patch.dict('os.environ', {'GOOGLE_MAPS_CLAVE_NAVEGADOR': ''}):
            ida = self.url_open(f'/u/pedido/{orden.id}?access_token={orden.access_token}', allow_redirects=False)
        self.assertEqual(ida.status_code, 303)
        self.assertIn('/u/', ida.headers['Location'])
        enlace = self.env['dcasa.ubicacion.enlace'].sudo().search([('orden_id', '=', orden.id)])
        self.assertEqual(enlace.partner_id, orden.partner_shipping_id)
        destino = self.url_open(ida.headers['Location'])
        self.assertIn('Volver a mi pedido', destino.text)
