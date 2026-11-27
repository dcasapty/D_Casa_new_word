"""«Retiro en tienda» (D'CASA tiene tienda física): marcar la casa en el mapa elige sola la entrega a domicilio, y
quien retira en la tienda no pide mapa, ni lleva el QR, ni recibe los avisos de entrega (docs/UBICACION.md)."""
from unittest.mock import patch

from odoo.tests import tagged

from .common import CERCA, UbicacionCase


@tagged('post_install', '-at_install')
class TestRetiroEnTienda(UbicacionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['website']._dcasa_entregas()
        Carrier = cls.env['delivery.carrier'].sudo()
        cls.domicilio = Carrier.search([('dcasa_por_cotizar', '=', True), ('is_published', '=', True)], limit=1)
        cls.retiro = Carrier.search([('dcasa_por_cotizar', '=', False), ('is_published', '=', True),
                                     ('delivery_type', '=', 'fixed')], limit=1)
        cls.producto = cls.env['product.product'].create(
            {'name': 'Mueble de prueba', 'type': 'consu', 'list_price': 100})

    def _carrito(self, carrier):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1})],
        })
        orden._set_delivery_method(carrier)
        return orden

    def test_hay_retiro_y_domicilio(self):
        self.assertTrue(self.domicilio and self.retiro, 'D\'CASA tiene las dos entregas')
        self.assertNotEqual(self.domicilio, self.retiro)

    def test_marcar_la_casa_elige_sola_la_entrega_a_domicilio(self):
        orden = self._carrito(self.retiro)
        self.assertEqual(orden.carrier_id, self.retiro)
        self.assertTrue(orden._dcasa_ubic_elegir_domicilio())
        self.assertEqual(orden.carrier_id, self.domicilio)
        self.assertTrue(orden._dcasa_va_a_domicilio())

    def test_si_ya_era_a_domicilio_no_cambia_nada(self):
        orden = self._carrito(self.domicilio)
        self.assertFalse(orden._dcasa_ubic_elegir_domicilio())
        self.assertEqual(orden.carrier_id, self.domicilio)

    def test_el_retiro_sigue_disponible_despues(self):
        orden = self._carrito(self.retiro)
        orden._dcasa_ubic_elegir_domicilio()
        orden._set_delivery_method(self.retiro)
        self.assertEqual(orden.carrier_id, self.retiro, 'el cliente puede volver a elegir «Retiro en tienda»')
        self.assertFalse(orden._dcasa_va_a_domicilio())

    def test_con_retiro_no_se_pide_mapa_ni_sale_el_qr_ni_los_avisos(self):
        orden = self._carrito(self.retiro)
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'gps', precision=9, referencia='Casa 24', confirmada=True)
        self.assertFalse(orden._dcasa_va_a_domicilio())
        self.assertEqual(orden._dcasa_ubic_url_para_marcar(), '', 'no se pide el mapa')
        self.assertFalse(orden._dcasa_entrega_chofer(crear=False), 'no hay QR para el chofer')
        orden.action_confirm()
        self.assertFalse(orden._dcasa_entrega_chofer(crear=False), 'ni al confirmar')
        self.assertFalse(orden.dcasa_va_a_domicilio, 'ni avisos de «Sale hoy» ni de pedir la ubicación')

    def test_con_un_pago_en_curso_no_se_cambia_el_metodo(self):
        orden = self._carrito(self.retiro)
        with patch.object(type(orden), '_dcasa_ubic_no_recalcular', return_value='pago'):
            self.assertFalse(orden._dcasa_ubic_elegir_domicilio())
        self.assertEqual(orden.carrier_id, self.retiro)


@tagged('post_install', '-at_install')
class TestUnErrorDelQrNoTumbaLaVenta(UbicacionCase):

    def test_si_armar_la_entrega_falla_la_venta_se_confirma_igual(self):
        self.env['website']._dcasa_entregas()
        domicilio = self.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        producto = self.env['product.product'].create({'name': 'Mueble de prueba 2', 'type': 'consu', 'list_price': 100})
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [(0, 0, {'product_id': producto.id, 'product_uom_qty': 1})],
        })
        orden._set_delivery_method(domicilio)
        with patch.object(type(orden), '_dcasa_entrega_chofer', side_effect=ValueError('prueba')):
            orden.action_confirm()
        self.assertEqual(orden.state, 'sale', 'un error del QR nunca hace fallar la venta')
