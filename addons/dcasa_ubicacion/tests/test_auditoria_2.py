"""Lo que encontró la segunda auditoría (2026-11-25), ya arreglado: el auditor dejó cada hallazgo reproducido en una
prueba («pasa si el fallo existe»); aquí van al revés."""
import io
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from odoo import fields
from odoo.addons.dcasa_brian.models.registro import tapar
from odoo.addons.dcasa_envios.motor import choferes
from odoo.tests import tagged

from ..controllers import checkout
from ..motor import casa
from .common import CERCA, UbicacionCase


@tagged('post_install', '-at_install')
class TestAuditoria2(UbicacionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domicilio = cls.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        cls.producto = cls.env['product.product'].create({'name': 'Cuna aud2', 'list_price': 250, 'type': 'consu',
                                                          'sale_ok': True, 'is_published': True})
        cls.Enlace = cls.env['dcasa.ubicacion.enlace'].sudo()
        cls.OTRA = None
        for lugar in cls.env['dcasa.envio.lugar'].search([('lat', '!=', False), ('lon', '!=', False)]):
            if lugar.lat and lugar.lon and choferes.distancia_m(CERCA[0], CERCA[1], lugar.lat, lugar.lon) > 5000:
                cls.OTRA = (lugar.lat, lugar.lon)
                break

    def venta(self, partner, shipping=None):
        valores = {'partner_id': partner.id, 'order_line': [(0, 0, {'product_id': self.producto.id})]}
        if shipping:
            valores['partner_shipping_id'] = shipping.id
        orden = self.env['sale.order'].create(valores)
        orden.carrier_id = self.domicilio
        return orden

    def otra_casa_marcada(self, id_externo):
        if not self.OTRA:
            self.skipTest('la tabla de prueba no tiene un segundo lugar lejos')
        conv = self.conversacion(id_externo=id_externo)
        Herramientas = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)
        Herramientas._juan_enlace_de_ubicacion(para_otra_casa=True)
        enlace = self.Enlace.search([('conversacion_id', '=', conv.id)], order='id desc', limit=1)
        enlace._confirmar(*self.OTRA, 'pin', referencia='Casa de mamá')
        return conv, enlace, Herramientas

    def test_h1_la_otra_casa_no_es_la_direccion_por_defecto_de_sus_ventas(self):
        conv, enlace, Herramientas = self.otra_casa_marcada('50761230011')
        cliente, hija = conv.partner_id, enlace.partner_id
        self.assertEqual(hija.type, 'other')
        self.assertIn('Otra casa de', hija.name)
        orden = self.env['sale.order'].create({'partner_id': cliente.id,
                                               'order_line': [(0, 0, {'product_id': self.producto.id})]})
        self.assertNotEqual(orden.partner_shipping_id, hija, 'su compra no va a la casa de la mamá')
        cotizacion = Herramientas._j_crear_cotizacion(conv, [(self.producto, 1)])
        self.assertNotEqual(cotizacion.partner_shipping_id, hija)

    def test_h2_su_ubicacion_despues_no_mueve_el_regalo_ya_marcado(self):
        conv, enlace, _herramientas = self.otra_casa_marcada('50761230012')
        cliente, hija = conv.partner_id, enlace.partner_id
        regalo = self.venta(cliente, shipping=hija)
        regalo.action_confirm()
        entrega = regalo._dcasa_entrega_chofer()
        antes = entrega._para_el_chofer()['enlaces']['google']
        # Una hora después comparte SU ubicación con el clip: lo que hace POST /dcasa/juan/v1/ubicacion.
        destino = conv._dcasa_ubic_destino(para_punto=True)
        self.assertEqual(destino, cliente)
        destino._dcasa_poner_ubicacion(*CERCA, 'whatsapp', confirmada=True)
        self.assertEqual(entrega._para_el_chofer()['enlaces']['google'], antes, 'el regalo sigue yendo a la mamá')
        self.assertTrue(cliente._dcasa_ubic_punto())
        # Lo que no es un punto (el número de casa, cotizar sin lugar) sí sigue con la otra casa esas 24 horas.
        self.assertEqual(conv._dcasa_ubic_destino(), hija)

    def test_h3_dos_regalos_pendientes_son_dos_direcciones(self):
        if not self.OTRA:
            self.skipTest('la tabla de prueba no tiene un segundo lugar lejos')
        conv = self.conversacion(id_externo='50761230013')
        Herramientas = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)
        Herramientas._juan_enlace_de_ubicacion(para_otra_casa=True)    # la mamá
        Herramientas._juan_enlace_de_ubicacion(para_otra_casa=True)    # la hermana
        hermana, mama = self.Enlace.search([('conversacion_id', '=', conv.id)], order='id desc', limit=2)
        self.assertNotEqual(mama.partner_id, hermana.partner_id)
        mama._confirmar(*self.OTRA, 'pin', referencia='Mamá')
        hermana._confirmar(*CERCA, 'pin', referencia='Hermana')
        self.assertEqual(mama.partner_id.dcasa_referencia, 'Mamá')

    def test_h4_la_auditoria_tapa_el_pin_de_google_y_el_geohash_de_waze(self):
        tapado = tapar({'detalle': 'https://www.google.com/maps/place/Casa/data=!3m1!8m2!3d8.9012345!4d-79.8012345',
                        'waze': 'https://waze.com/ul/hd1u0p3x7w', 'enlace_mapa': 'https://maps.app.goo.gl/x'})
        self.assertNotIn('8.9012345', tapado['detalle'])
        self.assertNotIn('hd1u0p3x7w', tapado['waze'])
        self.assertEqual(tapado['enlace_mapa'], '[oculto]')
        resultado = self.env['brian.herramientas'].ejecutar('poner_ubicacion_de_entrega', {
            'cliente': self.cliente.phone,
            'enlace_mapa': f'https://www.google.com/maps/place/X/data=!4m2!3m1!8m2!3d{CERCA[0]}000!4d{CERCA[1]}000'})
        self.assertTrue(resultado['ok'], resultado)
        accion = self.env['brian.accion'].sudo().search([('herramienta', '=', 'poner_ubicacion_de_entrega')],
                                                         order='id desc', limit=1)
        self.assertNotIn(str(CERCA[0]), (accion.argumentos or '') + (accion.resultado or ''))

    def test_h5_el_qr_de_una_cancelada_no_revive_al_volver_a_borrador(self):
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 1')
        orden = self.venta(self.cliente)
        orden.action_confirm()
        token = orden._dcasa_entrega_chofer().sudo().token
        orden._action_cancel()
        orden.action_draft()
        self.assertFalse(self.env['dcasa.ubicacion.entrega']._del_secreto(token))

    def test_h6_el_qr_se_cierra_a_los_90_dias_aunque_la_salida_no_se_valide(self):
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 1')
        orden = self.venta(self.cliente)
        orden.action_confirm()
        entrega = orden._dcasa_entrega_chofer()
        token = entrega.sudo().token
        Entrega = self.env['dcasa.ubicacion.entrega']
        self.assertTrue(Entrega._del_secreto(token))
        orden.sudo().date_order = fields.Datetime.now() - timedelta(days=91)
        self.assertFalse(Entrega._del_secreto(token))
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa nueva')    # renovar no la revive
        self.assertFalse(Entrega._del_secreto(token))

    def test_h7_tope_de_fotos_por_ficha_y_por_dia(self):
        salida = io.BytesIO()
        Image.new('RGB', (40, 30), (120, 160, 90)).save(salida, 'JPEG')
        for _vez in range(casa.MAX_FOTOS_POR_DIA):
            self.cliente._dcasa_poner_fachada(salida.getvalue())
        with self.assertRaises(casa.FotoInvalida) as error:
            self.cliente._dcasa_poner_fachada(salida.getvalue())
        self.assertEqual(error.exception.motivo, 'muchas')

    def test_h8_un_pago_recien_abierto_en_borrador_frena_el_recalculo(self):
        barato = self.env['product.product'].create({'name': 'Chupón aud2b', 'list_price': 20, 'type': 'consu',
                                                     'sale_ok': True})
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id,
                                               'order_line': [(0, 0, {'product_id': barato.id})]})
        orden._set_delivery_method(self.domicilio)
        self.cliente._dcasa_poner_escrita(referencia='Casa 9')
        orden.action_quotation_sent()
        proveedor = self.env.ref('payment.payment_provider_transfer').sudo()
        proveedor.state = 'test'
        metodo = proveedor.payment_method_ids[:1] or self.env.ref('payment_custom.payment_method_wire_transfer')
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': proveedor.id, 'payment_method_id': metodo.id, 'reference': f'AUD2-{orden.id}',
            'amount': orden.amount_total, 'currency_id': orden.currency_id.id, 'partner_id': self.cliente.id,
            'sale_order_ids': [(6, 0, orden.ids)], 'operation': 'online_redirect'})
        self.assertEqual(tx.state, 'draft')
        debia = orden.amount_total
        enlace, _url = self.Enlace._crear(self.cliente, orden=orden)
        enlace._confirmar(*CERCA, 'pin', referencia='Casa 9')
        self.assertEqual(orden.amount_total, debia)

    def test_h9_escribir_otra_calle_no_conserva_el_punto_viejo(self):
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'whatsapp', confirmada=True)
        self.cliente.write({'street': 'Calle 2, casa 5', 'city': 'La Chorrera'})
        antes = checkout._calle(self.cliente)
        formulario = {'street': 'Calle 8, casa 77', 'street2': '', 'city': 'La Chorrera'}
        with patch.object(checkout, 'request', SimpleNamespace(env=self.env)):
            self.assertTrue(checkout.conservar_punto_al_escribir(self.cliente, formulario, antes),
                            'misma calle: el punto bueno se queda')
            self.cliente.write({'street': 'Calle 8, casa 77'})       # lo que guarda Odoo antes de llegar aquí
            self.assertFalse(checkout.conservar_punto_al_escribir(self.cliente, formulario, antes),
                             'se mudó: el punto viejo ya no es su casa')
