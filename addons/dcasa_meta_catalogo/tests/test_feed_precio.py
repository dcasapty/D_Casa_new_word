"""El precio del catálogo es el mismo número que dibuja la ficha del producto (hoy sin ITBMS)."""
import re
from datetime import timedelta
from urllib.parse import urlsplit

from odoo import fields
from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from .common import BASE, MetaComun, leer_csv


def precio_de_la_ficha(html):
    """(precio que paga, precio tachado o None) que dibuja la ficha, como texto «39.99».

    El tachado (``oe_default_price``) siempre está en la página; sin descuento va escondido con ``d-none``.
    """
    paga = re.search(r'class="oe_price"[^>]*>.*?oe_currency_value">([\d.,]+)<', html, re.S)
    tachado = re.search(r'class="([^"]*oe_default_price[^"]*)"[^>]*>.*?oe_currency_value">([\d.,]+)<', html, re.S)
    visible = tachado and 'd-none' not in tachado.group(1).split()
    return paga.group(1).replace(',', ''), (tachado.group(2).replace(',', '') if visible else None)


@tagged('post_install', '-at_install')
class TestFeedPrecio(MetaComun, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Sin impuesto explícito: nace con el ITBMS de venta por defecto, que se suma al precio (test_itbms.py).
        cls.mesa = cls._producto('Mesa precio prueba Meta', 39.99)
        cls.cama, cls.queen, cls.king = cls._cama_con_tamanos('Cama precio prueba Meta', 300.0, 50.0)

    def _filas_por_ruta(self):
        respuesta = self.url_open(self.feed.url.removeprefix(BASE))
        self.assertEqual(respuesta.status_code, 200, respuesta.text[:300])
        return {fila['id']: fila for fila in leer_csv(respuesta.content)}

    def _ficha(self, fila):
        partes = urlsplit(fila['link'])
        self.assertEqual(f'{partes.scheme}://{partes.netloc}', BASE)
        ruta = partes.path + (f'?{partes.query}' if partes.query else '')
        self.opener.cookies.clear()  # un visitante que llega por primera vez, como el que ve el anuncio
        respuesta = self.url_open(ruta)
        self.assertEqual(respuesta.status_code, 200, ruta)
        return precio_de_la_ficha(respuesta.text)

    def test_mismo_precio_que_la_ficha_y_sin_itbms(self):
        self.assertTrue(self.mesa.taxes_id, 'la mesa lleva ITBMS (se suma aparte)')
        self.assertFalse(self.mesa.taxes_id.price_include)
        filas = self._filas_por_ruta()
        fila = filas[str(self.mesa.product_variant_id.id)]
        self.assertEqual(fila['price'], '39.99 USD', 'sin ITBMS, como dice la web «$39.99 + ITBMS»')
        self.assertNotIn('42.79', fila['price'])
        paga, tachado = self._ficha(fila)
        self.assertEqual(paga, '39.99')
        self.assertIsNone(tachado)

    def test_variante_con_precio_extra(self):
        filas = self._filas_por_ruta()
        for variante, esperado in ((self.queen, '300.00'), (self.king, '350.00')):
            with self.subTest(variante.display_name):
                fila = filas[str(variante.id)]
                self.assertEqual(fila['price'], f'{esperado} USD')
                self.assertIn('attribute_values=', fila['link'])
                paga, _tachado = self._ficha(fila)
                self.assertEqual(paga, esperado, 'la ficha de esa variante dibuja el mismo precio')

    def _descuento(self, tarifa, porcentaje=10):
        self.env['product.pricelist.item'].create({
            'pricelist_id': tarifa.id, 'applied_on': '1_product', 'product_tmpl_id': self.mesa.id,
            'compute_price': 'percentage', 'percent_price': porcentaje,
            'date_start': fields.Datetime.now() - timedelta(days=1),
            'date_end': fields.Datetime.now() + timedelta(days=10),
        })

    def test_descuento_de_la_tarifa_sale_como_sale_price(self):
        self.env.user.group_ids += self.env.ref('product.group_product_pricelist')
        tienda = self.env['product.pricelist'].create({
            'name': 'Tarifa de la tienda en línea (prueba)', 'website_id': self.website.id, 'selectable': True})
        self._descuento(tienda)
        fila = self._filas_por_ruta()[str(self.mesa.product_variant_id.id)]
        self.assertEqual(fila['price'], '39.99 USD', 'el precio normal')
        self.assertEqual(fila['sale_price'], '35.99 USD', '10 % menos')
        self.assertRegex(fila['sale_price_effective_date'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}[+-]\d{2}:\d{2}/'
                                                            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}[+-]\d{2}:\d{2}$')
        paga, tachado = self._ficha(fila)
        self.assertEqual((paga, tachado), ('35.99', '39.99'), 'la ficha dibuja los mismos dos precios')
        # Sin descuento, la cama no lleva sale_price.
        self.assertEqual(self._filas_por_ruta()[str(self.king.id)]['sale_price'], '')

    def _igual_que_la_ficha(self, **valores_tarifa):
        """Con otra tarifa (la que sea que Odoo le dé al visitante), el catálogo dice lo mismo que la ficha."""
        self.env.user.group_ids += self.env.ref('product.group_product_pricelist')
        self._descuento(self.env['product.pricelist'].create({'sequence': 1, **valores_tarifa}), 30)
        fila = self._filas_por_ruta()[str(self.mesa.product_variant_id.id)]
        paga, tachado = self._ficha(fila)
        esperado = (f'{tachado} USD', f'{paga} USD') if tachado else (f'{paga} USD', '')
        self.assertEqual((fila['price'], fila['sale_price']), esperado)
        return paga, tachado

    def test_tarifa_elegible_igual_que_la_ficha(self):
        paga, tachado = self._igual_que_la_ficha(name='Tarifa elegible (prueba)', selectable=True)
        self.assertEqual((paga, tachado), ('27.99', '39.99'), 'la prueba de verdad compara un descuento')

    def test_tarifa_de_uso_interno_igual_que_la_ficha(self):
        self._igual_que_la_ficha(name='Tarifa interna (prueba)', selectable=False)

    def test_combo_con_precio(self):
        piezas = self.env['product.combo'].create({
            'name': 'Combo prueba Meta', 'combo_item_ids': [Command.create({'product_id': self.queen.id})]})
        combo = self._producto('Combo cama prueba Meta', 499.0, type='combo', combo_ids=[Command.set(piezas.ids)])
        fila = self._filas_por_ruta()[str(combo.product_variant_id.id)]
        self.assertEqual(fila['price'], '499.00 USD')
        self.assertEqual(fila['custom_label_2'], 'disponible', 'un combo no controla inventario')
