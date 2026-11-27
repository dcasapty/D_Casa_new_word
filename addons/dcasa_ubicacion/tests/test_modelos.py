"""La ubicación en Odoo: la zona y el precio salen de la tabla, la ficha guarda el punto, el enlace de un solo uso
amarrado a la conversación, la entrega del motorizado (y su QR), el precio del envío en el carrito y las herramientas de
Juan y de Brian."""
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import new_test_user, tagged

from ..models.zona import UbicacionInvalida
from .common import CERCA, LEJOS, UbicacionCase


@tagged('post_install', '-at_install')
class TestZonaYFicha(UbicacionCase):

    def test_la_zona_y_el_precio_salen_de_la_tabla(self):
        Ubicacion = self.env['dcasa.ubicacion']
        _lat, _lon, zona = Ubicacion._validar(*CERCA)
        self.assertEqual(zona['lugar'], self.villa)
        self.assertEqual(zona['texto'], 'Villa Prueba II · Barrio Prueba · La Chorrera · Panamá Oeste')
        precio = Ubicacion._precio(zona['lugar'])
        self.assertTrue(precio['con_precio'])
        self.assertEqual(precio['total_txt'], self.precio_de(self.villa))

    def test_sin_tarifa_aprobada_no_hay_precio(self):
        self.tarifa.with_user(self.gerencia_envios).action_quitar_aprobacion()
        self.assertEqual(self.env['dcasa.ubicacion']._precio(self.villa),
                         {'con_precio': False, 'motivo': 'en_revision'})

    def test_un_punto_que_no_sirve(self):
        with self.assertRaises(UbicacionInvalida) as error:
            self.env['dcasa.ubicacion']._validar(*LEJOS)
        self.assertEqual(error.exception.motivo, 'fuera_de_panama')
        with self.assertRaises(UbicacionInvalida) as error:
            self.env['dcasa.ubicacion']._validar('8.9', -79.8)
        self.assertEqual(error.exception.motivo, 'coordenadas')

    def test_la_ficha_guarda_el_punto_y_su_origen(self):
        zona = self.clienta._dcasa_poner_ubicacion(*CERCA, 'gps', precision=14.6,
                                                   referencia='  Casa verde,  portón negro ')
        self.assertEqual(zona['lugar'], self.villa)
        c = self.clienta
        self.assertEqual((c.partner_latitude, c.partner_longitude), CERCA)
        self.assertEqual((c.dcasa_ubic_origen, c.dcasa_ubic_precision_m, c.dcasa_ubic_confirmada), ('gps', 15, True))
        self.assertEqual(c.dcasa_ubic_lugar_id, self.villa)
        self.assertEqual((c.dcasa_barriada, c.dcasa_distrito), ('Villa Prueba II', 'La Chorrera'))
        self.assertEqual(c.dcasa_referencia, 'Casa verde, portón negro')
        self.assertEqual(c.city, 'La Chorrera', 'sin ciudad escrita, se llena con el distrito')
        self.assertEqual(c.dcasa_ubic_etiqueta, 'Ubicación del teléfono (±15 m)')
        resumen = c._dcasa_ubic_resumen()
        self.assertTrue(resumen['tiene_punto'] and resumen['confiable'])
        self.assertIn('waze.com/ul?ll=8.9012000%2C-79.8013000', resumen['enlaces']['waze'])
        # La precisión solo cuenta con GPS; lo escrito a mano deja la ficha sin punto.
        c._dcasa_poner_ubicacion(*CERCA, 'pin', precision=500)
        self.assertFalse(c.dcasa_ubic_precision_m)
        c._dcasa_poner_escrita(referencia='Frente al chino')
        self.assertFalse(c._dcasa_ubic_punto())
        self.assertEqual(c.dcasa_ubic_origen, 'escrita')
        self.assertFalse(c._dcasa_ubic_resumen()['tiene_punto'])

    def test_lo_que_escribio_la_clienta_en_la_ciudad_manda(self):
        self.clienta.city = 'Mi ciudad'
        self.clienta._dcasa_poner_ubicacion(*CERCA, 'pin')
        self.assertEqual(self.clienta.city, 'Mi ciudad')

    def test_la_calle_de_google_solo_con_clave_y_sin_romper_nada(self):
        with patch.dict('os.environ', {'GOOGLE_MAPS_CLAVE_SERVIDOR': ''}):
            self.assertEqual(self.env['dcasa.ubicacion']._calle_de_google(*CERCA), '')
        respuesta = type('R', (), {'ok': True, 'json': lambda self: {'status': 'OK', 'results': [
            {'formatted_address': '7Q2F+3X La Chorrera'}, {'formatted_address': 'Calle 5, La Chorrera, Panamá'}]}})()
        with patch.dict('os.environ', {'GOOGLE_MAPS_CLAVE_SERVIDOR': 'A' * 39}), \
                patch('odoo.addons.dcasa_ubicacion.models.zona.requests.get', return_value=respuesta) as pedido:
            self.assertEqual(self.env['dcasa.ubicacion']._calle_de_google(8.91, -79.81), 'Calle 5, La Chorrera, Panamá')
            self.assertEqual(self.env['dcasa.ubicacion']._calle_de_google(8.91, -79.81), 'Calle 5, La Chorrera, Panamá')
        self.assertEqual(pedido.call_count, 1, 'el mismo punto no se le pregunta dos veces a Google')


@tagged('post_install', '-at_install')
class TestEnlaceDelChat(UbicacionCase):

    def test_el_enlace_guarda_la_huella_y_no_el_secreto(self):
        enlace, url = self.env['dcasa.ubicacion.enlace']._crear(self.clienta)
        token = url.rsplit('/u/', 1)[1]
        self.assertNotIn(token, enlace.sudo().huella)
        self.assertEqual(self.env['dcasa.ubicacion.enlace']._del_secreto(token), enlace)
        self.assertFalse(self.env['dcasa.ubicacion.enlace']._del_secreto(token[:-1] + 'x'))
        self.assertFalse(self.env['dcasa.ubicacion.enlace']._del_secreto('corto'))
        self.assertEqual(enlace.estado, 'vigente')
        enlace.sudo().vence = fields.Datetime.now() - timedelta(minutes=1)
        self.assertEqual(enlace.estado, 'vencido')

    def test_al_confirmar_juan_le_escribe_con_la_zona_y_el_precio(self):
        conv = self.conversacion(id_externo='50761230001')
        partner = conv.partner_id
        self.configurar_worker()
        enlace, _url = self.env['dcasa.ubicacion.enlace']._crear(partner, conversacion=conv, creado_por='juan')
        enlace._confirmar(*CERCA, 'pin', referencia='Casa verde')
        self.assertEqual(enlace.estado, 'usado')
        self.assertEqual(partner.dcasa_ubic_lugar_id, self.villa)
        mensaje = self.env['dcasa.mensaje'].sudo().search([('conversacion_id', '=', conv.id), ('origen', '=', 'odoo'),
                                                           ('tipo', '=', 'mensaje')], order='id desc', limit=1)
        self.assertEqual(mensaje.autor, 'bot', 'lo escribe el asistente: Juan sigue atendiendo')
        self.assertIn('Recibimos su ubicación: Villa Prueba II, La Chorrera.', mensaje.texto)
        self.assertIn('🚚 Envío', mensaje.texto)
        self.assertIn(self.precio_de(self.villa), mensaje.texto)
        self.assertNotIn('8.9012', mensaje.texto, 'nunca las coordenadas en el chat')
        self.assertEqual(conv.estado, 'bot', 'no la toma una vendedora')

    def test_un_punto_malo_deja_el_enlace_vigente(self):
        enlace, _url = self.env['dcasa.ubicacion.enlace']._crear(self.clienta)
        with self.assertRaises(UbicacionInvalida):
            enlace._confirmar(*LEJOS, 'pin')
        self.assertEqual(enlace.estado, 'vigente')


@tagged('post_install', '-at_install')
class TestEntregaYCarrito(UbicacionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domicilio = cls.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        cls.producto = cls.env['product.product'].create({'name': 'Caja de prueba', 'list_price': 20, 'type': 'consu',
                                                          'sale_ok': True})

    def venta(self, partner=None, con_envio=True):
        orden = self.env['sale.order'].create({
            'partner_id': (partner or self.clienta).id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1})]})
        if con_envio:
            orden.carrier_id = self.domicilio
        return orden

    def test_al_confirmar_se_arma_la_entrega_del_motorizado(self):
        self.clienta._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Portón negro')
        orden = self.venta()
        orden.action_confirm()
        entrega = self.env['dcasa.ubicacion.entrega']._de_la_venta(orden, crear=False)
        self.assertTrue(entrega)
        token = entrega.sudo().token
        self.assertEqual(self.env['dcasa.ubicacion.entrega']._del_secreto(token), entrega)
        datos = entrega._para_el_motorizado()
        self.assertEqual((datos['pedido'], datos['nombre'], datos['telefono_tel']), (orden.name, 'Ana', '+50761234567'))
        self.assertEqual(datos['referencia'], 'Portón negro')
        self.assertIn('waze.com', datos['enlaces']['waze'])
        self.assertTrue(entrega._qr_src().startswith('data:image/png;base64,'))
        self.assertIn('/entrega/', entrega._url())
        # Entregada hace días: el mismo «ya no sirve» que un secreto inventado (sin entregar, sigue abriendo aunque
        # pase la vigencia: test_auditoria_datos).
        orden.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing').sudo().write(
            {'state': 'done', 'date_done': fields.Datetime.now() - timedelta(days=4)})
        self.assertFalse(self.env['dcasa.ubicacion.entrega']._del_secreto(token))

    def test_sin_domicilio_o_sin_direccion_no_hay_qr(self):
        orden = self.venta(con_envio=False)
        orden.action_confirm()
        self.assertFalse(orden._dcasa_entrega_motorizado(crear=False))
        sin_nada = self.env['res.partner'].create({'name': 'Sin Dirección'})
        otra = self.venta(partner=sin_nada)
        otra.action_confirm()
        self.assertFalse(otra._dcasa_entrega_motorizado(crear=False))
        # Cuando la clienta pone su punto, la venta confirmada queda con su entrega.
        sin_nada._dcasa_poner_ubicacion(*CERCA, 'whatsapp')
        self.assertTrue(otra._dcasa_entrega_motorizado(crear=False))

    def test_el_qr_del_comprobante_solo_lee(self):
        self.clienta._dcasa_poner_ubicacion(*CERCA, 'pin')
        orden = self.venta()
        orden.action_confirm()
        factura = orden._create_invoices()
        self.assertFalse(factura._dcasa_entrega_para_el_qr(), 'en borrador no lleva QR')
        factura.action_post()
        self.assertEqual(factura._dcasa_entrega_para_el_qr(),
                         self.env['dcasa.ubicacion.entrega']._de_la_venta(orden, crear=False))
        with patch.object(type(self.env['dcasa.ubicacion.entrega']), 'create',
                          side_effect=AssertionError('el PDF no crea nada')):
            self.assertTrue(factura._dcasa_entrega_para_el_qr())

    def test_el_carrito_cobra_el_envio_del_punto(self):
        orden = self.venta(con_envio=False)
        sin_punto = self.domicilio.fixed_rate_shipment(orden)
        self.clienta._dcasa_poner_ubicacion(*CERCA, 'gps', precision=10)
        con_punto = self.domicilio.fixed_rate_shipment(orden)
        total = self.env['dcasa.envio.tarifa'].sudo().cotizar_lugar(self.villa)['total']
        self.assertEqual(con_punto['price'], total)
        self.assertNotEqual(sin_punto['price'], total)
        orden._set_delivery_method(self.domicilio)
        envio = orden.order_line.filtered(lambda ln: ln.is_delivery and not ln.dcasa_promocion_envio_id)
        self.assertEqual(envio.price_unit, total)
        self.assertEqual(envio.dcasa_envio_lugar_id, self.villa)
        self.assertIn('Villa Prueba II', envio.name)

    def test_escrita_a_mano_sigue_por_cotizar(self):
        self.clienta._dcasa_poner_escrita()
        orden = self.venta(con_envio=False)
        self.assertIsNone(orden._dcasa_envio_por_ubicacion())


@tagged('post_install', '-at_install')
class TestHerramientas(UbicacionCase):

    def test_cotizar_envio_sin_lugar_usa_el_punto_guardado(self):
        conv = self.conversacion(id_externo='50761230002')
        Herramientas = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)
        conv.partner_id._dcasa_poner_ubicacion(*CERCA, 'whatsapp')
        datos = Herramientas._j_cotizar_envio()
        self.assertEqual(datos['estado'], 'precio')
        self.assertTrue(datos['por_ubicacion'])
        self.assertEqual(datos['lugar']['lugar_id'], self.villa.id)
        self.assertIn('Villa Prueba II', datos['ubicacion_guardada'])

    def test_enlace_de_ubicacion_para_juan(self):
        conv = self.conversacion(id_externo='50761230003')
        datos = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)._juan_enlace_de_ubicacion()
        self.assertIn('/u/', datos['enlace'])
        self.assertIn(datos['enlace'], datos['frase_para_el_cliente'])
        enlace = self.env['dcasa.ubicacion.enlace'].sudo().search([('conversacion_id', '=', conv.id)])
        self.assertEqual(enlace.creado_por, 'juan')

    def test_brian_pone_y_lee_la_ubicacion(self):
        vendedora = new_test_user(self.env, login='vend_ubic', name='Vendedora Ubicación',
                                  groups='base.group_user,sales_team.group_sale_salesman')
        Brian = self.env['brian.herramientas'].with_user(vendedora)
        datos = Brian._brian_poner_ubicacion_de_entrega(
            cliente='Ana Prueba', enlace_mapa='https://maps.google.com/?q=8.9012,-79.8013', referencia='Casa azul')
        self.assertEqual(datos['origen'], 'De un enlace de Google Maps o Waze')
        self.assertIn('Villa Prueba II', datos['zona'])
        self.assertEqual(self.clienta.dcasa_referencia, 'Casa azul')
        orden = self.env['sale.order'].create({'partner_id': self.clienta.id, 'user_id': vendedora.id})
        leido = Brian._brian_ubicacion_de_entrega(venta=orden.name)
        self.assertTrue(leido['tiene_punto'])
        self.assertNotIn('enlaces', leido, 'los botones llevan las coordenadas: no van al modelo')
        self.assertNotIn('8.9012', json.dumps(leido))
        self.assertEqual((leido['abrir']['modelo'], leido['abrir']['res_id']), ('sale.order', orden.id))
        enlace = Brian._brian_enlace_de_ubicacion_para_cliente(cliente='Ana Prueba')
        self.assertIn('/u/', enlace['enlace'])

    def test_la_auditoria_de_brian_no_guarda_coordenadas_secretos_ni_la_casa(self):
        # Auditoría 1: el registro de Brian no se edita ni se borra; lo privado entra tapado.
        vendedora = new_test_user(self.env, login='vend_auditoria', groups='sales_team.group_sale_salesman')
        Brian = self.env['brian.herramientas'].with_user(vendedora)
        hecho = Brian.ejecutar('poner_ubicacion_de_entrega', {'cliente': 'Ana Prueba', 'latitud': CERCA[0],
                                                               'longitud': CERCA[1], 'referencia': 'Casa azul 24'})
        self.assertTrue(hecho['ok'], hecho)
        enlace = Brian.ejecutar('enlace_de_ubicacion_para_cliente', {'cliente': 'Ana Prueba'})
        self.assertTrue(enlace['ok'], enlace)
        self.assertIn('/u/', enlace['datos']['enlace'], 'la persona sí recibe el enlace para mandarlo')
        acciones = self.env['brian.accion'].sudo().search([('create_uid', '=', vendedora.id)])
        self.assertEqual(len(acciones), 2)
        guardado = ' '.join((a.argumentos or '') + (a.resultado or '') for a in acciones)
        for privado in ('8.9012', '79.8013', 'Casa azul 24', enlace['datos']['enlace'].rsplit('/', 1)[-1]):
            self.assertNotIn(privado, guardado)
        self.assertIn('Villa Prueba II', guardado, 'la zona sí queda: sirve para revisar qué hizo Brian')
