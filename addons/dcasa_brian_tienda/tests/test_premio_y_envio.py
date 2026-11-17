"""Un premio de Socios nunca puede salirle más caro al socio que su descuento (la dueña, 2026-11-17).

La revisión adversarial de Andrés vendedor encontró esto: si un socio usa un premio de puntos en el carrito web y con
eso la compra baja del mínimo de la promoción de envío, **pierde el envío gratis**. Con las cifras de hoy: carrito de
$205 sin ITBMS, premio de $10 → la compra medida queda en $195.65 (la línea del premio rebaja la base sin impuesto,
$9.35, no los $10 de su cara), la promoción se borra y paga $45 de envío. Gastaba puntos para pagar más.

La dueña eligió (2026-11-17) **avisarle y no dejar canjear**: se le dice en palabras simples cuánto pagaría de envío y
cuánto le descuenta el premio, y el canje ni se pide (sus puntos no se mueven). Si el premio le sigue conviniendo
—descuenta más de lo que perdería de envío— se deja pasar, porque ahí sí sale ganando.

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
PIN = '913772'
CLAVE = 'zzpe-socia-2026'


@tagged('post_install', '-at_install')
class TestPremioFrenteAlEnvio(TiendaCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = new_test_user(cls.env, login='zzpe_ger', name='ZZPE Gerencia',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        importar(cls.env, cls.gerencia)
        cls.env['dcasa.envio.tarifa'].search([], limit=1).with_user(cls.gerencia).action_aprobar()
        Lugar = cls.env['dcasa.envio.lugar']
        cls.costa = Lugar.search([('name', '=', 'Costa Inventada')])     # $45 normal; gratis con la promoción
        cls.colon = Lugar.search([('name', '=', 'Barrio Simulado')])     # $105 normal; abono de $20
        impuesto = cls.env['brian.herramientas']._b_itbms_venta()
        # $205 sin ITBMS: pasa el mínimo de $200 por poco, que es donde vive el problema.
        cls.sofa = cls.env['product.template'].create({
            'name': 'ZZPE SOFÁ', 'type': 'consu', 'sale_ok': True, 'is_published': True, 'list_price': 205.0,
            'taxes_id': [Command.set(impuesto.ids)]})
        pais = cls.env.ref('base.pa')
        cls.usuaria = new_test_user(cls.env, login='zzpe_socia', password=CLAVE, groups='base.group_portal',
                                    name='ZZPE Socia Inventada')
        cls.socia = cls.usuaria.partner_id
        cls.socia.write({'phone': '6000-0077', 'email': 'zzpe.socia@example.com', 'street': 'Calle Inventada 7',
                         'city': 'La Chorrera', 'country_id': pais.id, 'zip': '0000'})

    def setUp(self):
        super().setUp()
        # Un día dentro de la promoción de noviembre de 2026 (viene cargada: más de $200, Costa gratis, Colón $20).
        self.startPatcher(patch(HOY, return_value=date(2026, 11, 16)))
        self.startPatcher(patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'}))

    # ------------------------------------------------------------------ ayudas

    def socia_con_puntos(self, puntos=60000):
        self.socia._dcasa_asegurar_ficha()
        self.socia._dcasa_guardar_pin(PIN)
        self.env['dcasa.movimiento']._asentar(self.socia, 'ajuste', puntos, 'test', motivo='Saldo de prueba')
        self.authenticate('zzpe_socia', CLAVE)

    def orden(self):
        return self.env['sale.order'].sudo().search([('website_id', '!=', False)], order='id desc', limit=1)

    def agregar(self, plantilla, cantidad=1):
        datos = self.post('carrito/agregar',
                          {'producto_id': plantilla.product_variant_id.id, 'cantidad': cantidad}).json()
        self.assertTrue(datos['ok'], datos)
        return datos

    def sumar(self, lugar):
        datos = self.post('carrito/envio', {'lugar_id': lugar.id}).json()
        self.assertTrue(datos['ok'], datos)
        return datos

    def promocion_puesta(self, orden=None):
        return bool((orden or self.orden()).order_line.filtered('dcasa_promocion_envio_id'))

    def premio(self, ref):
        return self.env.ref(f'dcasa_socios.{ref}')

    def carrito_con_envio(self, lugar=None):
        """Un carrito de $205 sin ITBMS con el envío puesto y la promoción aplicada."""
        self.agregar(self.sofa)
        self.sumar(lugar or self.costa)
        orden = self.orden()
        self.assertTrue(self.promocion_puesta(orden), 'la promoción está puesta antes del premio')
        return orden

    # ------------------------------------------------------------------ lo que NO se deja

    def test_el_premio_que_cuesta_el_envio_gratis_no_se_canjea_y_se_le_avisa(self):
        """El caso que encontró la revisión: carrito de $205 sin ITBMS con el envío a Costa Inventada gratis por la
        promoción. Un premio de $10 dejaría la compra en $195.65 y le costaría $45 de envío. No se canjea, se le
        avisa con las dos cifras y sus puntos no se mueven."""
        self.socia_con_puntos()
        saldo = self.socia.dcasa_saldo
        orden = self.carrito_con_envio()
        with self.assertRaises(UserError) as cm:
            orden._dcasa_usar_puntos_web(premio=self.premio('premio_desc_10'))
        aviso = str(cm.exception)
        self.assertIn('$45.00', aviso, 'le dice cuánto pagaría de envío')
        self.assertIn('$10.00', aviso, 'le dice cuánto le descuenta el premio')
        self.assertFalse(orden.order_line.filtered('dcasa_canje_id'), 'el premio no entró')
        self.assertTrue(self.promocion_puesta(orden), 'la promoción sigue puesta')
        self.assertEqual(self.socia.dcasa_saldo, saldo, 'no se le movió ni un punto')
        self.assertFalse(self.env['dcasa.canje'].sudo().search([('partner_id', '=', self.socia.id)]),
                         'el canje ni se pidió')

    def test_tampoco_se_deja_un_premio_de_25_que_cuesta_45_de_envio(self):
        """Mismo carrito y mismo envío gratis de $45: un premio de $25 también le saldría más caro."""
        self.socia_con_puntos()
        orden = self.carrito_con_envio()
        with self.assertRaisesRegex(UserError, 'promoción del envío'):
            orden._dcasa_usar_puntos_web(premio=self.premio('premio_desc_25'))
        self.assertFalse(orden.order_line.filtered('dcasa_canje_id'))

    # ------------------------------------------------------------------ lo que sí se deja

    def test_si_el_premio_descuenta_mas_de_lo_que_perderia_si_se_canjea(self):
        """Mismo carrito y mismo envío gratis de $45, pero un premio de $50: aunque pierda la promoción, el socio
        sale ganando $5. Se canjea, y la línea de la promoción se va porque la compra ya no pasa del mínimo."""
        self.socia_con_puntos()
        orden = self.carrito_con_envio()
        orden._dcasa_usar_puntos_web(premio=self.premio('premio_desc_50'))
        self.assertTrue(orden.order_line.filtered('dcasa_canje_id'), 'el premio entró')
        self.assertFalse(self.promocion_puesta(orden), 'la promoción se fue: la compra ya no pasa del mínimo')

    def test_donde_la_promocion_solo_abona_20_un_premio_de_25_si_conviene(self):
        """A Colón el envío cuesta $105 y la promoción solo abona $20. Un premio de $25 le hace perder ese abono,
        pero descuenta más: le conviene y se deja."""
        self.socia_con_puntos()
        orden = self.carrito_con_envio(self.colon)
        orden._dcasa_usar_puntos_web(premio=self.premio('premio_desc_25'))
        self.assertTrue(orden.order_line.filtered('dcasa_canje_id'), 'el premio entró')

    def test_sin_envio_en_el_carrito_el_premio_se_usa_como_siempre(self):
        """Un carrito sin envío sumado no tiene promoción que perder: el premio entra igual que antes de este
        cambio. Es la regresión que importa, porque así son casi todos los carritos."""
        self.socia_con_puntos()
        self.agregar(self.sofa)
        orden = self.orden()
        self.assertFalse(self.promocion_puesta(orden))
        orden._dcasa_usar_puntos_web(premio=self.premio('premio_desc_10'))
        self.assertTrue(orden.order_line.filtered('dcasa_canje_id'), 'el premio entró')

    def test_con_la_compra_lejos_del_minimo_el_premio_se_usa_como_siempre(self):
        """Carrito de $274.99 sin ITBMS: el premio de $10 lo deja en $265.64, muy por encima del mínimo, así que no
        hay nada que avisar y la promoción se queda."""
        self.socia_con_puntos()
        self.agregar(self.sofa)
        self.agregar(self.base_cama)
        self.sumar(self.costa)
        orden = self.orden()
        orden._dcasa_usar_puntos_web(premio=self.premio('premio_desc_10'))
        self.assertTrue(orden.order_line.filtered('dcasa_canje_id'), 'el premio entró')
        self.assertTrue(self.promocion_puesta(orden), 'la promoción sigue puesta')

    # ------------------------------------------------------------- si el carrito cambia DESPUÉS

    def carrito_grande_con_premio(self):
        """Carrito de $274.99 con el envío gratis y un premio de $10 bien puesto (la compra queda en $265.64)."""
        self.agregar(self.sofa)
        self.agregar(self.base_cama)
        self.sumar(self.costa)
        orden = self.orden()
        orden._dcasa_usar_puntos_web(premio=self.premio('premio_desc_10'))
        self.assertTrue(orden.order_line.filtered('dcasa_canje_id'))
        self.assertTrue(self.promocion_puesta(orden))
        return orden

    def test_si_el_carrito_se_achica_despues_los_puntos_vuelven_antes_de_pagar(self):
        """El premio entró con un carrito de $274.99 y después el socio quitó la cama: la compra queda en $205 y con
        el premio en $195.65, así que el premio le costaría los $45 del envío gratis. Antes de enseñarle o cobrarle
        el carrito, los puntos vuelven y se le avisa."""
        self.socia_con_puntos()
        saldo = self.socia.dcasa_saldo
        orden = self.carrito_grande_con_premio()
        self.assertLess(self.socia.dcasa_saldo, saldo, 'los puntos quedaron reservados')
        orden.order_line.filtered(
            lambda line: line.product_id == self.base_cama.product_variant_id).sudo().unlink()
        aviso = orden._dcasa_limpiar_premios_web()
        self.assertIn('promoción del envío', aviso or '')
        self.assertFalse(orden.order_line.filtered('dcasa_canje_id'), 'el premio salió del carrito')
        self.assertEqual(self.socia.dcasa_saldo, saldo, 'los puntos volvieron enteros')
        self.assertTrue(self.promocion_puesta(orden), 'y conserva el envío gratis')

    def test_el_carrito_de_la_tienda_tambien_devuelve_los_puntos(self):
        """Lo mismo, pero por donde pasa el socio de verdad: al abrir el carrito de la tienda."""
        self.socia_con_puntos()
        saldo = self.socia.dcasa_saldo
        orden = self.carrito_grande_con_premio()
        orden.order_line.filtered(
            lambda line: line.product_id == self.base_cama.product_variant_id).sudo().unlink()
        carrito = self.url_open(f'{RAIZ}/carrito').json()['carrito']
        self.assertFalse([e for e in carrito['extras'] if e['tipo'] == 'premio'], 'el premio no sale en el carrito')
        self.assertEqual(self.socia.dcasa_saldo, saldo, 'los puntos volvieron enteros')

    # ------------------------------------------------------------- la cuenta del impuesto

    def test_la_linea_del_premio_baja_la_base_no_su_valor_de_cara(self):
        """El aviso se mide con lo mismo que mueve la línea de verdad: la base sin ITBMS ($9.35 para un premio de
        $10) y el valor entero con ITBMS. Si las dos cuentas se separaran, el aviso mentiría."""
        self.socia_con_puntos()
        orden = self.carrito_grande_con_premio()
        premio = orden.order_line.filtered('dcasa_canje_id')
        _impuestos, base = self.env['dcasa.canje']._dcasa_impuestos_y_base(10.0, orden.company_id)
        self.assertAlmostEqual(premio.price_subtotal, -base, places=2, msg='la línea rebaja la base')
        self.assertAlmostEqual(premio.price_total, -10.0, places=2, msg='base + ITBMS = el valor del premio')
