"""Un visitante sin cuenta que escribe en la tienda el celular, el correo o el RUC de otra persona no entra en la
ficha de esa persona (revisión adversarial, 2026-10-17).

El atajo de «una persona, una ficha» colgaba la dirección del visitante de la ficha que ya tenía ese dato. Odoo, a quien
cuelga de una ficha, le enseña y le deja usar en el checkout TODAS las direcciones de esa ficha: cualquiera que supiera
el celular de una clienta veía su nombre, sus direcciones, sus teléfonos y sus correos, podía editarlas o mandar la
compra a la casa de ella, y la compra le aparecía a ella en «Mi cuenta». El formulario normal de dirección no pasa por
ese atajo (Odoo 19 crea la dirección en el portal), pero la ruta del pago exprés sí, y responde a cualquiera con un
carrito aunque la tienda no tenga pago exprés."""
import re

from requests.exceptions import HTTPError

from odoo.tests import HttpCase, tagged
from odoo.tests.common import JsonRpcException

CALLE = 'Calle Privada 55'
PLAYA = 'Casa de Playa 9'
CORREO = 'victima.privada@correo.com'
CORREO_PLAYA = 'playa.privada@correo.com'
TELEFONO_PLAYA = '6777-0303'
PRIVADOS = (CALLE, PLAYA, CORREO, CORREO_PLAYA, TELEFONO_PLAYA, 'VICTIMA PRIVADA', 'Victima en la playa')


@tagged('post_install', '-at_install')
class TestCheckoutSinDatosAjenos(HttpCase):

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        self.panama = self.env.ref('base.pa')
        self.producto = self.env['product.product'].create({
            'name': 'MESA DE PRUEBA PRIVACIDAD', 'type': 'consu', 'list_price': 100.0, 'is_published': True,
            'sale_ok': True})
        self.victima = self.env['res.partner'].create({
            'name': 'VICTIMA PRIVADA', 'phone': '+507 6777-0202', 'email': CORREO,
            'street': CALLE, 'city': 'Arraiján', 'country_id': self.panama.id})
        self.playa = self.env['res.partner'].create({
            'name': 'Victima en la playa', 'parent_id': self.victima.id, 'type': 'delivery', 'street': PLAYA,
            'city': 'Coronado', 'country_id': self.panama.id, 'phone': TELEFONO_PLAYA, 'email': CORREO_PLAYA})
        self.authenticate(None, None)

    def _csrf(self):
        return re.search(r'csrf_token: "([^"]+)"', self.url_open('/socios/terminos').text).group(1)

    def _carrito(self):
        self.make_jsonrpc_request('/shop/cart/add', {
            'product_template_id': self.producto.product_tmpl_id.id, 'product_id': self.producto.id, 'quantity': 1})
        return self.env['sale.order'].search([('website_id', '=', self.website.id)], order='id desc', limit=1)

    def _expres_con_el_celular_de_la_victima(self):
        """El ataque: la ruta del pago exprés con el celular de otra persona (no hace falta tener pago exprés)."""
        orden = self._carrito()
        try:
            self.make_jsonrpc_request('/shop/express_checkout', {'billing_address': {
                'name': 'Quien no es la victima', 'email': 'otra.persona@correo.com', 'phone': '6777-0202',
                'street': 'Calle Cualquiera 1', 'city': 'La Chorrera', 'country': 'PA'}})
        except (JsonRpcException, HTTPError):
            pass   # rechazado: mejor todavía
        orden.invalidate_recordset()
        return orden

    def test_el_pago_expres_no_cuelga_al_visitante_de_la_ficha_ajena(self):
        orden = self._expres_con_el_celular_de_la_victima()
        self.assertNotEqual(orden.partner_id.commercial_partner_id, self.victima,
                            'Un celular escrito en la tienda no prueba que sea la persona')
        self.victima.invalidate_recordset()
        self.assertFalse(self.victima.child_ids - self.playa, 'Nada nuevo colgado de su ficha')
        self.assertFalse(self.env['sale.order'].search_count([('partner_id', 'child_of', self.victima.id)]),
                         'Una compra ajena no le aparece en «Mi cuenta»')

    def test_el_checkout_no_ensena_las_direcciones_de_la_ficha(self):
        self._expres_con_el_celular_de_la_victima()
        for ruta in ('/shop/checkout', '/shop/payment', '/shop/address?address_type=delivery',
                     '/shop/address?address_type=billing', f'/shop/address?partner_id={self.playa.id}',
                     f'/shop/address?partner_id={self.victima.id}'):
            with self.subTest(ruta=ruta):
                html = self.url_open(ruta).text
                for privado in PRIVADOS:
                    self.assertNotIn(privado, html)

    def test_no_edita_ni_usa_una_direccion_de_la_ficha(self):
        orden = self._expres_con_el_celular_de_la_victima()
        for partner in (self.playa, self.victima):
            with self.subTest(partner=partner.name):
                self.url_open('/shop/address/submit', data={
                    'csrf_token': self._csrf(), 'partner_id': partner.id, 'address_type': 'delivery',
                    'name': 'Cambiado', 'email': 'cambio@correo.com', 'phone': '6777-0909', 'street': 'Otra 2',
                    'city': 'Capira', 'country_id': self.panama.id})
                try:
                    self.make_jsonrpc_request('/shop/update_address', {
                        'partner_id': partner.id, 'address_type': 'delivery'})
                except (JsonRpcException, HTTPError):
                    pass
        (self.playa | self.victima).invalidate_recordset()
        orden.invalidate_recordset()
        self.assertEqual(self.playa.street, PLAYA, 'La dirección de la clienta no cambia')
        self.assertEqual(self.victima.street, CALLE)
        self.assertNotIn(orden.partner_shipping_id, self.playa | self.victima)
        self.assertNotIn(orden.partner_invoice_id, self.playa | self.victima)

    def test_el_aviso_de_dato_repetido_no_dice_de_quien_es(self):
        """El formulario normal con un celular que ya es de una ficha: el aviso no dice el nombre de esa persona."""
        self._carrito()
        respuesta = self.url_open('/shop/address/submit', data={
            'csrf_token': self._csrf(), 'address_type': 'delivery', 'use_delivery_as_billing': 'true',
            'name': 'Quien no es la victima', 'email': 'otra.persona@correo.com', 'phone': '6777-0202',
            'street': 'Calle Cualquiera 1', 'city': 'La Chorrera', 'country_id': self.panama.id})
        for privado in PRIVADOS:
            self.assertNotIn(privado, respuesta.text)
        self.victima.invalidate_recordset()
        self.assertFalse(self.victima.child_ids - self.playa)

    def test_el_celular_repetido_se_avisa_en_el_formulario(self):
        """Sin cuenta, el celular de otra ficha se avisa en el mismo formulario, sin decir de quién es (antes el
        candado fallaba al crear y «Confirmar» no avanzaba sin ningún mensaje)."""
        self._carrito()
        respuesta = self.url_open('/shop/address/submit', data={
            'csrf_token': self._csrf(), 'address_type': 'delivery', 'use_delivery_as_billing': 'true',
            'name': 'Quien no es la victima', 'email': 'otra.persona@correo.com', 'phone': '6777-0202',
            'street': 'Calle Cualquiera 1', 'city': 'La Chorrera', 'country_id': self.panama.id})
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertIn('phone', datos.get('invalid_fields', []))
        self.assertIn('Ese celular ya está registrado', ' '.join(datos.get('messages', [])))
        for privado in PRIVADOS:
            self.assertNotIn(privado, respuesta.text)

    def test_con_su_cuenta_la_clienta_si_ve_sus_direcciones(self):
        """Con la sesión de la tienda de la misma clienta todo sigue como en Odoo (ve y elige las suyas)."""
        usuario = self.env['res.users'].create({
            'name': 'VICTIMA PRIVADA', 'login': 'victima_privada', 'password': 'clave-victima-123',
            'partner_id': self.victima.id, 'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        self.authenticate(usuario.login, 'clave-victima-123')
        self._carrito()
        self.assertIn(PLAYA, self.url_open('/shop/checkout').text)
