"""Revisión adversarial de Andrés vendedor (A2, 2026-11-16): el envío sumado desde el chat frente a los premios de
Socios, el pago de la tienda y los ajustes de Gerencia. Las escribió el revisor; quedan como guardianes.

Datos inventados. Cada prueba dice el escenario y lo que tiene que pasar."""
import os
from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.addons.dcasa_envios.tests.common import importar
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import RAIZ, TiendaCase

HOY = 'odoo.addons.dcasa_envios.models.promocion.EnvioPromocion._hoy'
PIN = '482915'
CLAVE = 'zzrv-socia-2026'


@tagged('post_install', '-at_install', 'rv_andres')
class TestRevisionVendedor(TiendaCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = new_test_user(cls.env, login='zzrv_ger', name='ZZRV Gerencia',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        importar(cls.env, cls.gerencia)
        cls.env['dcasa.envio.tarifa'].search([], limit=1).with_user(cls.gerencia).action_aprobar()
        Lugar = cls.env['dcasa.envio.lugar']
        cls.costa = Lugar.search([('name', '=', 'Costa Inventada')])     # $45; gratis con la promoción
        cls.colon = Lugar.search([('name', '=', 'Barrio Simulado')])     # $105
        impuesto = cls.env['brian.herramientas']._b_itbms_venta()
        cls.tornillo = cls.env['product.template'].create({
            'name': 'ZZRV TORNILLO', 'type': 'consu', 'sale_ok': True, 'is_published': True, 'list_price': 4.0,
            'taxes_id': [Command.set(impuesto.ids)]})
        pais = cls.env.ref('base.pa')
        cls.usuaria = new_test_user(cls.env, login='zzrv_socia', password=CLAVE, groups='base.group_portal',
                                    name='ZZRV Socia Inventada')
        cls.socia = cls.usuaria.partner_id
        cls.socia.write({'phone': '6000-0099', 'email': 'zzrv.socia@example.com', 'street': 'Calle Inventada 1',
                         'city': 'La Chorrera', 'country_id': pais.id, 'zip': '0000'})

    def setUp(self):
        super().setUp()
        self.startPatcher(patch(HOY, return_value=date(2026, 11, 16)))
        self.startPatcher(patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'}))

    def orden(self):
        return self.env['sale.order'].sudo().search([('website_id', '!=', False)], order='id desc', limit=1)

    def agregar(self, plantilla, cantidad=1):
        return self.post('carrito/agregar', {'producto_id': plantilla.product_variant_id.id, 'cantidad': cantidad})

    def sumar(self, lugar):
        return self.post('carrito/envio', {'lugar_id': lugar.id})

    # ------------------------------------------------------------------ 1. Socios: el premio cubierto por el envío
    def test_rv_premio_de_puntos_no_puede_pagar_el_envio_que_luego_se_va(self):
        """Una socia con $4.28 de productos suma el envío de $105 desde el chat y, con eso en el carrito, aplica un
        premio de $10 (antes: «Ese descuento es mayor que tu carrito»). Al pasar al pago (/shop/payment llama a
        ``_recompute_cart``) la tienda vuelve a poner «te cotizamos» ($0) y el carrito queda con total NEGATIVO y el
        premio puesto: la regla de Socios «nunca un total negativo» se rompe."""
        self.socia._dcasa_asegurar_ficha()
        self.socia._dcasa_guardar_pin(PIN)
        self.env['dcasa.movimiento']._asentar(self.socia, 'ajuste', 1500, 'test', motivo='Saldo de prueba')
        diez = self.env.ref('dcasa_socios.premio_desc_10')
        self.authenticate('zzrv_socia', CLAVE)
        self.assertTrue(self.agregar(self.tornillo).json()['ok'])
        orden = self.orden()
        self.assertEqual(orden.partner_id, self.socia)
        self.assertTrue(self.sumar(self.colon).json()['ok'])
        self.assertGreater(orden.amount_total, 100)
        # Arreglado: el premio se mide contra los PRODUCTOS ($4.28), no contra el carrito con el envío, así que no se
        # puede usar. La prueba ya no acepta las dos cosas (segunda revisión, 2026-11-16).
        with self.assertRaisesRegex(UserError, 'mayor que tu carrito'):
            orden._dcasa_usar_puntos_web(premio=diez)
        self.assertFalse(orden.order_line.filtered('dcasa_canje_id'), 'el premio no entró')
        self.assertGreaterEqual(orden.amount_total, 0.0)

    def test_rv_el_premio_de_socios_no_viaja_al_chat_como_un_producto(self):
        """El premio es una línea negativa que la tienda muestra en el carrito. No puede salir entre los productos
        que la página le manda al Worker: le contaría a Andrés que este visitante es socio y tiene un premio puesto, y
        Andrés podría proponer «quitarlo» (eso cancela el canje). Va en ``extras``, con el envío."""
        self.socia._dcasa_asegurar_ficha()
        self.socia._dcasa_guardar_pin(PIN)
        self.env['dcasa.movimiento']._asentar(self.socia, 'ajuste', 1500, 'test', motivo='Saldo de prueba')
        self.authenticate('zzrv_socia', CLAVE)
        self.assertTrue(self.agregar(self.base_cama).json()['ok'])
        orden = self.orden()
        orden._dcasa_usar_puntos_web(premio=self.env.ref('dcasa_socios.premio_desc_10'))
        premio = orden.order_line.filtered('dcasa_canje_id')
        self.assertTrue(premio, 'el premio está en la venta')
        carrito = self.url_open(f'{RAIZ}/carrito').json()['carrito']
        ids = [ln['producto_id'] for ln in carrito['lineas']]
        self.assertNotIn(premio.product_id.id, ids, 'el premio no va entre los productos del carrito')
        self.assertEqual(carrito['cantidad_total'], len(carrito['lineas']),
                         'la cuenta de artículos cuadra con lo que se pinta')
        extras = [e for e in carrito['extras'] if e['tipo'] == 'premio']
        self.assertEqual(len(extras), 1, 'el premio sale en «extras»')
        self.assertTrue(extras[0]['subtotal_texto'].startswith('−'), extras[0]['subtotal_texto'])

    # ------------------------------------------------------------------ 2. Después de elegir la entrega en el pago
    def test_rv_tras_elegir_entrega_a_domicilio_en_el_pago_se_puede_sumar_el_envio(self):
        """El visitante fue al pago, eligió «Entrega a domicilio: te cotizamos por WhatsApp» (la línea de $0 que pone
        la tienda, no una persona) y volvió al chat: «súmame el envío» queda en ``ajeno`` para siempre (Andrés dice
        «No pude sumar el envío ahorita… inténtalo otra vez»)."""
        self.agregar(self.base_cama)
        orden = self.orden()
        domicilio = self.env['sale.order']._dcasa_envio_transportista()
        orden._set_delivery_method(domicilio)            # lo que hace /shop/set_delivery_method (o /shop/checkout)
        self.assertEqual(orden.order_line.filtered('is_delivery').mapped('price_unit'), [0.0])
        datos = self.sumar(self.costa).json()
        self.assertTrue(datos.get('ok'), f'no se pudo sumar el envío tras pasar por el pago: {datos}')

    # ------------------------------------------------------------------ 3. El pago y la entrega de Odoo
    def test_rv_el_pago_vuelve_a_poner_la_entrega_de_odoo(self):
        """docs/BRIAN_TIENDA.md (la pregunta del pago sigue abierta con la dueña; el flujo no cambia): /shop/checkout
        solo rehace la entrega si el monto del envío no es el precio del transportista («te cotizamos», $0). Con el
        envío gratis por la promoción (monto $0) el envío sumado sigue en la página del pago; /shop/payment siempre
        vuelve a poner la de Odoo. Con un envío que cuesta, /shop/checkout ya lo cambia (y después se puede volver a
        sumar desde el chat)."""
        self.authenticate('zzrv_socia', CLAVE)
        self.agregar(self.base_cama, 3)                  # pasa el mínimo: envío gratis
        self.assertTrue(self.sumar(self.costa).json()['ok'])
        respuesta = self.url_open('/shop/checkout')
        self.assertTrue(respuesta.url.endswith('/shop/checkout'), respuesta.url)
        orden = self.orden()
        orden.invalidate_recordset()
        self.assertTrue(orden.order_line.filtered('dcasa_envio_lugar_id'),
                        'con el envío gratis (monto $0, el del transportista), /shop/checkout no lo rehace')
        orden._recompute_cart()                          # lo primero que hace /shop/payment
        orden.invalidate_recordset()
        self.assertFalse(orden.order_line.filtered('dcasa_envio_lugar_id'), '/shop/payment pone la de Odoo')
        self.assertEqual(orden.order_line.filtered('is_delivery').mapped('price_unit'), [0.0])
        # Con un envío que cuesta ($45: ya no pasa el mínimo), /shop/checkout lo cambia por «te cotizamos».
        self.post('carrito/cantidad', {'producto_id': self.base_cama.product_variant_id.id, 'cantidad': 1})
        self.assertTrue(self.sumar(self.costa).json()['ok'], 'después del pago se puede volver a sumar')
        orden.invalidate_recordset()
        self.assertEqual(orden.order_line.filtered('dcasa_envio_lugar_id').price_unit, 45.0)
        self.url_open('/shop/checkout')
        orden.invalidate_recordset()
        self.assertFalse(orden.order_line.filtered('dcasa_envio_lugar_id'))

    # ------------------------------------------------------------------ 4. Sin las reglas con que se sumó
    def test_rv_apagar_los_envios_no_deja_precios_viejos_pegados_en_el_carrito(self):
        """El visitante sumó el envío; después Gerencia apaga «Juan cotiza envíos» (o la tarifa vuelve a revisión, o
        el lugar se archiva). Sin las reglas que permitieron sumarlo, la tienda no lo conserva: en el siguiente cambio
        del carrito (o al pedir el carrito o su PDF) vuelve la entrega de Odoo, y el PDF no lo da como «el de nuestra
        tabla de envíos»."""
        self.agregar(self.base_cama)
        self.assertTrue(self.sumar(self.colon).json()['ok'])
        self.env['dcasa.juan.ajustes'].obtener().cotizar_envios = False
        self.post('carrito/cantidad', {'producto_id': self.base_cama.product_variant_id.id, 'cantidad': 2})
        orden = self.orden()
        orden.invalidate_recordset()
        self.assertFalse(orden.order_line.filtered('dcasa_envio_lugar_id'),
                         'con los envíos apagados, el precio sumado sigue pegado en el carrito y en el PDF')

    def test_rv_la_tarifa_en_revision_o_el_lugar_archivado_tampoco_y_el_pdf_lo_sabe(self):
        """Lo mismo con la tarifa en revisión (al pedir el carrito) y con el lugar archivado (al armar el PDF): el
        envío sumado sale y el PDF dice lo de siempre («el costo del envío… te lo confirma una vendedora»)."""
        self.agregar(self.base_cama)
        self.assertTrue(self.sumar(self.colon).json()['ok'])
        tarifa = self.env['dcasa.envio.tarifa'].search([], limit=1)
        with patch.object(type(tarifa), '_estado_publico', return_value={'configurada': True, 'aprobada': False,
                                                                            'aviso': ''}):
            carrito = self.url_open('/dcasa/brian/v1/carrito').json()['carrito']
        self.assertIsNone(carrito['envio'], 'con la tarifa en revisión, el carrito ya no trae el envío sumado')
        self.assertFalse(self.orden().order_line.filtered('dcasa_envio_lugar_id'))
        # Otra vez, y ahora el lugar se archiva: el PDF ya no lo trae.
        self.assertTrue(self.sumar(self.colon).json()['ok'])
        self.colon.sudo().active = False
        texto = ' '.join(self.url_open('/dcasa/brian/v1/carrito/cotizacion.pdf').text.split())
        self.assertNotIn('Barrio Simulado', texto)
        self.assertIn('el costo del envío y la fecha de entrega te los confirma una vendedora', texto)
        self.assertFalse(self.orden().order_line.filtered('dcasa_envio_lugar_id'))

    def test_rv_ajeno_si_el_envio_lo_puso_una_persona(self):
        """Un envío con precio que puso una persona (no la tienda ni el chat) no se cambia: «ajeno»."""
        self.agregar(self.base_cama)
        orden = self.orden()
        domicilio = self.env['sale.order']._dcasa_envio_transportista()
        orden.set_delivery_line(domicilio, 30.0)
        self.assertEqual(self.sumar(self.costa).json(), {'ok': False, 'motivo': 'ajeno'})
        self.assertEqual(orden.order_line.filtered('is_delivery').mapped('price_unit'), [30.0])
