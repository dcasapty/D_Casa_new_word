"""Armar el catálogo no puede crecer en muchas consultas por producto (el contenedor es chico)."""
from odoo.addons.website_sale.tests.common import MockRequest
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from .common import MetaComun, foto, leer_csv

# Medido el 2026-10-17: 36 consultas para 20 productos y las mismas 36 para 60 (todo va por lotes); con tarifas del
# sitio, 56 y 96 (las reglas de precio de cada ficha). Los topes dejan margen, pero una consulta de más por producto
# (de 20 a 60 son 40 consultas más) los rompe.
TOPE_20 = 60
TOPE_60 = 60
MAXIMO_POR_PRODUCTO = 0.5


@tagged('post_install', '-at_install')
class TestRendimientoFeed(MetaComun, TransactionCase):

    def _catalogo(self, cuantos):
        categoria = self.env['product.public.category'].create({'name': f'Rendimiento {cuantos}'})
        imagen = foto(ancho=64, alto=64)
        self.env['product.template'].create([{
            'name': f'Producto rendimiento {cuantos}-{i}', 'list_price': 10.0 + i, 'is_published': True,
            'image_1920': imagen, 'public_categ_ids': [Command.set(categoria.ids)],
            'description_sale': f'Descripción {i}',
        } for i in range(cuantos)])
        return self.env['product.feed'].create({
            'name': f'Meta {cuantos}', 'target': 'meta', 'website_id': self.website.id, 'dcasa_activo': True,
            'product_category_ids': [Command.set(categoria.ids)],
        })

    def _medir(self, feed, tope):
        """Consultas para armar el CSV con la caché de registros vacía (las cachés del servidor ya calientes)."""
        with MockRequest(self.env, website=self.website):
            feed._dcasa_meta_csv()  # calienta las cachés del servidor (parámetros, grupos, vistas)
            self.env.invalidate_all()
            antes = self.cr.sql_log_count
            with self.assertQueryCount(tope):
                contenido = feed._dcasa_meta_csv()
            return self.cr.sql_log_count - antes, len(leer_csv(contenido))

    def test_tope_de_consultas_para_20_y_60_productos(self):
        consultas_20, filas_20 = self._medir(self._catalogo(20), TOPE_20)
        consultas_60, filas_60 = self._medir(self._catalogo(60), TOPE_60)
        self.assertEqual((filas_20, filas_60), (20, 60))
        por_producto = (consultas_60 - consultas_20) / 40
        self.assertLessEqual(
            por_producto, MAXIMO_POR_PRODUCTO,
            f'{consultas_20} consultas para 20 productos y {consultas_60} para 60: {por_producto:.2f} por producto')

    def test_con_tarifas_del_sitio_tampoco_crece_mucho(self):
        """Si la tienda usa tarifas, el precio de cada ficha busca sus reglas: a lo sumo ~1 consulta por producto."""
        self.env.user.group_ids += self.env.ref('product.group_product_pricelist')
        self.env['product.pricelist'].create({'name': 'Tienda (rendimiento)', 'website_id': self.website.id,
                                              'selectable': True})
        consultas_20, _filas = self._medir(self._catalogo(20), TOPE_20 + 30)
        consultas_60, _filas = self._medir(self._catalogo(60), TOPE_60 + 70)
        por_producto = (consultas_60 - consultas_20) / 40
        self.assertLessEqual(por_producto, 1.5, f'{consultas_20} → {consultas_60}: {por_producto:.2f} por producto')
