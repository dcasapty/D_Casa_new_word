"""Tus opiniones (/mi-cuenta/opiniones), como el navegador: opina solo quien compró y pagó por completo, una vez por
producto, con sesión; queda por revisar y no sale en la ficha hasta que Gerencia la publica."""
from odoo.tests import HttpCase, new_test_user, tagged

from .common import CLAVE, MiCuentaComun

OPINIONES = '/mi-cuenta/opiniones'


@tagged('post_install', '-at_install')
class TestOpinionesMiCuenta(MiCuentaComun, HttpCase):

    def setUp(self):
        super().setUp()
        self.preparar()
        # La factura del pedido de la socia va en abono (a medias): se paga lo que falta para poder opinar del sofá.
        self._pagar(self.factura, self.factura.amount_residual, self.inicio_abono)
        self.assertIn(self.factura.payment_state, ('paid', 'in_payment'))
        self.Resena = self.env['dcasa.resena'].sudo()
        self.usuario = new_test_user(self.env, login='mc_opina', password=CLAVE, groups='base.group_portal',
                                     partner_id=self.socia.id, name=self.socia.name)

    def opinar(self, producto=None, estrellas='5', texto='Quedó perfecto en la sala.'):
        return self.post(OPINIONES, producto_id=str((producto or self.sofa).product_tmpl_id.id), estrellas=estrellas,
                         texto=texto)

    def mias(self):
        return self.Resena.search([('partner_id', '=', self.socia.id)])

    def test_sin_sesion_va_a_entrar_y_no_guarda_nada(self):
        self.authenticate(None, None)
        self.assertEqual(self.ruta(self.url_open(OPINIONES)), '/mi-cuenta')
        self.assertEqual(self.ruta(self.opinar()), '/mi-cuenta')
        self.assertFalse(self.mias())

    def test_quien_compro_y_pago_opina_y_queda_por_revisar(self):
        self.authenticate(self.usuario.login, CLAVE)
        respuesta = self.url_open(OPINIONES)
        self.assertEqual(respuesta.headers.get('Cache-Control'), 'no-store')
        html = respuesta.text
        self.assertIn('Sofá Milán de Prueba', html)
        self.assertIn(f'name="producto_id" value="{self.sofa.product_tmpl_id.id}"', html)
        self.assertNotIn(f'value="{self.cojin.product_tmpl_id.id}"', html, 'El cojín no está en la tienda')
        respuesta = self.opinar()
        self.assertEqual(self.ruta(respuesta), OPINIONES)
        self.assertIn('¡Gracias por contarnos!', respuesta.text)
        self.assertIn('La estamos leyendo', respuesta.text)
        self.assertNotIn(f'name="producto_id" value="{self.sofa.product_tmpl_id.id}"', respuesta.text,
                         'Ya opinó: el formulario de ese producto ya no sale')
        (resena,) = self.mias()
        self.assertEqual((resena.estado, resena.estrellas, resena.texto),
                         ('pendiente', 5, 'Quedó perfecto en la sala.'))
        # por revisar: la ficha no la enseña
        self.assertNotIn('Quedó perfecto en la sala.', self.url_open(self.sofa.website_url).text)
        # una sola vez
        self.assertIn('una vez por producto', self.opinar(estrellas='1').text)
        self.assertEqual(len(self.mias()), 1)

    def test_con_pin_tambien_opina(self):
        self.authenticate(None, None)
        self.entrar(origen='mi-cuenta')
        self.assertEqual(self.ruta(self.opinar(estrellas='4')), OPINIONES)
        self.assertEqual(self.mias().estrellas, 4)

    def test_quien_no_compro_no_opina(self):
        otro = new_test_user(self.env, login='mc_no_compro', password=CLAVE, groups='base.group_portal',
                             name='Portal Sin Compras')
        self.authenticate(otro.login, CLAVE)
        html = self.url_open(OPINIONES).text
        self.assertIn('Cuando una compra tuya quede pagada por completo', html)
        self.assertNotIn('name="producto_id"', html)
        respuesta = self.opinar()
        self.assertIn('Puedes opinar de lo que compraste y ya pagaste', respuesta.text)
        self.assertFalse(self.Resena.search([('product_tmpl_id', '=', self.sofa.product_tmpl_id.id)]))

    def test_lo_de_otro_cliente_no_cuenta(self):
        """El otro cliente tiene el sofá facturado (sin pagar): ni él opina ni la socia por él."""
        usuario_otro = new_test_user(self.env, login='mc_otro_op', password=CLAVE, groups='base.group_portal',
                                     partner_id=self.otro.id, name=self.otro.name)
        self.authenticate(usuario_otro.login, CLAVE)
        self.opinar()
        self.assertFalse(self.Resena.search([('partner_id', '=', self.otro.id)]))

    def test_estrellas_fuera_de_rango_o_sin_csrf(self):
        self.authenticate(self.usuario.login, CLAVE)
        self.assertIn('Elige de 1 a 5 estrellas', self.opinar(estrellas='9').text)
        sin_token = self.url_open(OPINIONES, data={'producto_id': str(self.sofa.product_tmpl_id.id), 'estrellas': '5'})
        self.assertNotEqual(sin_token.status_code, 200)
        self.assertFalse(self.mias())

    def test_inicio_y_compras_invitan_a_opinar(self):
        self.authenticate(self.usuario.login, CLAVE)
        self.assertIn('href="/mi-cuenta/opiniones"', self.url_open('/mi-cuenta').text)
        self.assertIn('href="/mi-cuenta/opiniones"', self.url_open('/mi-cuenta/compras').text)
        self.opinar()
        self.assertNotIn('Dejar mi opinión', self.url_open('/mi-cuenta').text, 'Ya no le queda nada por opinar')
