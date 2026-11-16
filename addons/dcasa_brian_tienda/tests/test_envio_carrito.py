"""A2: el envío en la cotización del chat (``POST /dcasa/brian/v1/carrito/envio``). La página manda solo el lugar de la
tabla; Odoo pone la misma línea que pone dcasa_envios para Juan (el precio de la calculadora y la promoción con la
compra del carrito), el carrito y el PDF la traen, y la tienda no la vuelve $0 cuando el visitante cambia el carrito."""
from datetime import date
from unittest.mock import patch

from odoo.addons.dcasa_envios.tests.common import importar
from odoo.tests import new_test_user, tagged

from ..controllers import main as C
from ..models.venta import CONSERVAR_ENVIO
from .common import RAIZ, TiendaCase

HOY = 'odoo.addons.dcasa_envios.models.promocion.EnvioPromocion._hoy'


@tagged('post_install', '-at_install')
class TestEnvioEnElCarrito(TiendaCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = new_test_user(cls.env, login='zzbt_ger_envio', name='ZZBT Gerencia Envío',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        importar(cls.env, cls.gerencia)
        cls.tarifa = cls.env['dcasa.envio.tarifa'].search([], limit=1)
        cls.tarifa.with_user(cls.gerencia).action_aprobar()
        Lugar = cls.env['dcasa.envio.lugar']
        cls.costa = Lugar.search([('name', '=', 'Costa Inventada')])     # $45 normal; gratis con la promoción
        cls.colon = Lugar.search([('name', '=', 'Barrio Simulado')])     # $105; abono de $20

    def setUp(self):
        super().setUp()
        # La promoción de envío de noviembre de 2026 (viene cargada): un día dentro de ella.
        self.startPatcher(patch(HOY, return_value=date(2026, 11, 16)))

    # ------------------------------------------------------------------ ayudas

    def agregar(self, plantilla, cantidad=1):
        datos = self.post('carrito/agregar', {'producto_id': plantilla.product_variant_id.id, 'cantidad': cantidad})
        return datos.json()

    def sumar(self, lugar_o_id, **extra):
        lugar_id = lugar_o_id.id if hasattr(lugar_o_id, 'id') else lugar_o_id
        return self.post('carrito/envio', {'lugar_id': lugar_id, **extra})

    def orden(self):
        return self.env['sale.order'].sudo().search([('website_id', '!=', False)], order='id desc', limit=1)

    def envios(self, orden=None):
        return sorted((orden or self.orden()).order_line.filtered('is_delivery').mapped('price_unit'))

    # ------------------------------------------------------------------ lo que sí

    def test_suma_el_envio_con_la_promocion_y_los_numeros_salen_de_odoo(self):
        self.agregar(self.base_cama, 3)   # $209.97 sin ITBMS: pasa el mínimo de la promoción
        datos = self.sumar(self.costa).json()
        self.assertTrue(datos['ok'], datos)
        self.assertFalse(datos['ya_estaba'])
        carrito = datos['carrito']
        self.assertEqual(carrito['envio'], {'lugar_id': self.costa.id, 'lugar': 'Costa Inventada'})
        self.assertEqual([x['producto_id'] for x in carrito['lineas']], [self.base_cama.product_variant_id.id],
                         'el envío no va entre los productos')
        self.assertEqual(carrito['cantidad_total'], 3)
        (envio, promocion) = carrito['extras']
        self.assertEqual(envio['tipo'], 'envio')
        self.assertTrue(envio['nombre'].startswith('Envío a domicilio: Costa Inventada'), envio)
        self.assertEqual(envio['subtotal_texto'], '$45.00')
        self.assertEqual(promocion['tipo'], 'promocion')
        self.assertIn('envío gratis', promocion['nombre'])
        self.assertEqual(promocion['subtotal_texto'], '−$45.00')
        orden = self.orden()
        self.assertEqual(self.envios(orden), [-45.0, 45.0])
        self.assertEqual(orden.carrier_id, self.env['sale.order']._dcasa_envio_transportista())
        self.assertEqual(carrito['total_texto'], '$209.97 + ITBMS', 'el envío gratis: el total, el de Odoo')
        # Es la misma línea que pone dcasa_envios para Juan, con su marca del sistema.
        self.assertEqual(orden.order_line.filtered('dcasa_envio_lugar_id').dcasa_envio_lugar_id, self.costa)
        self.assertEqual(self.url_open(f'{RAIZ}/carrito').json()['carrito']['envio']['lugar_id'], self.costa.id)

    def test_sin_promocion_el_total_trae_el_envio_y_el_precio_nunca_lo_manda_el_navegador(self):
        self.agregar(self.base_cama, 1)   # $69.99: no pasa el mínimo
        carrito = self.sumar(self.costa, precio=1, total=1, price_unit=1).json()['carrito']
        self.assertEqual(self.envios(), [45.0], 'el precio de la calculadora, aunque el navegador mande otro')
        self.assertEqual(len(carrito['extras']), 1)
        self.assertEqual(carrito['total_texto'], '$114.99 + ITBMS')
        orden = self.orden()
        self.assertAlmostEqual(orden.amount_untaxed, 114.99)

    def test_otro_lugar_lo_reemplaza_y_el_mismo_ya_estaba(self):
        self.agregar(self.base_cama, 3)
        self.sumar(self.costa)
        otra_vez = self.sumar(self.costa).json()
        self.assertTrue(otra_vez['ya_estaba'])
        self.assertEqual(self.envios(), [-45.0, 45.0])
        datos = self.sumar(self.colon).json()
        self.assertEqual(datos['carrito']['envio']['lugar'], 'Barrio Simulado')
        self.assertEqual(self.envios(), [-20.0, 105.0])

    def test_cambiar_el_carrito_no_pone_el_envio_en_cero_y_la_promocion_sigue_a_la_compra(self):
        self.agregar(self.base_cama, 1)
        self.sumar(self.costa)
        self.assertEqual(self.envios(), [45.0])
        # Sube la cantidad desde el chat: la tienda revisa el carrito (el transportista dice $0) y el envío se queda.
        datos = self.post('carrito/cantidad', {'producto_id': self.base_cama.product_variant_id.id, 'cantidad': 3})
        self.assertEqual(self.envios(), [-45.0, 45.0], 'pasó el mínimo: la promoción se suma con la compra')
        self.assertEqual(datos.json()['carrito']['total_texto'], '$209.97 + ITBMS')
        # Baja otra vez: dcasa_envios quita la promoción; el envío sigue con su precio.
        self.post('carrito/cantidad', {'producto_id': self.base_cama.product_variant_id.id, 'cantidad': 1})
        self.assertEqual(self.envios(), [45.0])
        # Agregar otra cosa (como el «Agregar» de la página) tampoco lo pone en cero.
        self.agregar(self.colchon, 1)
        self.assertIn(45.0, self.envios())
        # Sin productos, el envío sale (como en Odoo).
        for plantilla in (self.base_cama, self.colchon):
            self.post('carrito/cantidad', {'producto_id': plantilla.product_variant_id.id, 'cantidad': 0})
        self.assertEqual(self.envios(), [])

    def test_la_tienda_de_odoo_tampoco_lo_pone_en_cero_y_la_marca_no_llega_por_rpc(self):
        self.agregar(self.base_cama, 1)
        self.sumar(self.costa)
        orden = self.orden()
        linea = orden.order_line.filtered(lambda sol: sol.product_id == self.base_cama.product_variant_id)
        orden._cart_update_line_quantity(line_id=linea.id, quantity=2)     # lo que hace /shop/cart al cambiar
        self.assertEqual(self.envios(orden), [45.0])
        envio = orden.order_line.filtered('dcasa_envio_lugar_id')
        envio.with_context(**{CONSERVAR_ENVIO: True}).write({'price_unit': 0.0})   # un contexto de RPC: un True
        self.assertEqual(envio.price_unit, 0.0, 'solo el objeto del servidor lo frena, nunca un valor de JSON')

    def test_el_pdf_trae_el_envio_y_su_promocion(self):
        self.agregar(self.base_cama, 3)
        self.sumar(self.costa)
        texto = ' '.join(self.url_open(f'{RAIZ}/carrito/cotizacion.pdf').text.split())
        self.assertIn('Envío a domicilio: Costa Inventada', texto)
        self.assertIn('envío gratis', texto)
        self.assertIn('El envío es el de nuestra tabla de envíos para el lugar indicado', texto)
        self.assertNotIn('el costo del envío y la fecha de entrega te los confirma', texto)

    # ------------------------------------------------------------------ lo que no

    def test_lo_que_no_se_suma(self):
        self.assertEqual(self.sumar(self.costa).json(), {'ok': False, 'motivo': 'sin_carrito'})
        self.agregar(self.base_cama, 1)
        self.assertEqual(self.sumar(99999999).json(), {'ok': False, 'motivo': 'lugar'})
        # Un lugar que agregó una vendedora: hasta que Gerencia lo revise no tiene precio para el cliente (como Juan).
        vendedora = new_test_user(self.env, login='zzbt_vend_envio', name='ZZBT Vendedora Envío',
                                  groups='base.group_user,dcasa_base.group_vendedora')
        sin_revisar = self.env['dcasa.envio.lugar'].with_user(vendedora).create({
            'name': 'ZZBT Residencial Sin Revisar', 'tipo': 'barrio', 'dist': 'Colón', 'corr': 'Barrio Simulado',
            'km': 1.0})
        self.assertEqual(self.sumar(sin_revisar).json(), {'ok': False, 'motivo': 'aparte'})
        sin_revisar.sudo().active = False
        self.assertEqual(self.sumar(sin_revisar).json(), {'ok': False, 'motivo': 'lugar'}, 'archivado')
        self.env['dcasa.juan.ajustes'].obtener().cotizar_envios = False
        self.assertEqual(self.sumar(self.costa).json(), {'ok': False, 'motivo': 'sin_tarifa'})
        self.env['dcasa.juan.ajustes'].obtener().cotizar_envios = True
        for lugar_id in (0, -1, '5', 1.5, True, None, 2 ** 31):
            with self.subTest(lugar_id=lugar_id):
                self.assertEqual(self.post('carrito/envio', {'lugar_id': lugar_id}).status_code, 400)
        self.assertEqual(self.post('carrito/envio', {'lugar_id': self.costa.id}, csrf=False).status_code, 403)
        self.assertEqual(self.envios(), [], 'nada de eso tocó el carrito')
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian_tienda.activo', 'False')
        self.assertEqual(self.sumar(self.costa).json(), {'ok': False, 'motivo': 'apagado'})

    def test_otro_visitante_no_toca_tu_carrito(self):
        self.agregar(self.base_cama, 1)
        mio = self.orden()
        self.otra_sesion()
        self.assertEqual(self.sumar(self.costa).json()['motivo'], 'sin_carrito')
        self.assertEqual(self.envios(mio), [])

    def test_los_topes_por_sesion_y_por_conexion(self):
        self.agregar(self.base_cama, 1)
        with patch.object(C, 'MAX_ENVIO_POR_HORA', 2):
            self.assertTrue(self.sumar(self.costa).json()['ok'])
            self.assertTrue(self.sumar(self.colon).json()['ok'])
            respuesta = self.sumar(self.costa)
        self.assertEqual((respuesta.status_code, respuesta.json()), (429, {'ok': False, 'motivo': 'tope'}))
        self.assertEqual(self.orden().order_line.filtered('dcasa_envio_lugar_id').dcasa_envio_lugar_id, self.colon)
        # Por conexión: una sesión nueva no da cupo nuevo.
        self.otra_sesion()
        self.agregar(self.base_cama, 1)
        with patch.object(C, 'MAX_ENVIO_POR_CONEXION_HORA', 2):
            respuesta = self.sumar(self.costa)
        self.assertEqual(respuesta.status_code, 429, 'la conexión ya sumó dos envíos en esta hora')
        self.assertEqual(self.env['dcasa.brian.tienda.cupo'].sudo().search_count([('llave', 'like', 'envio:%')]), 1)
